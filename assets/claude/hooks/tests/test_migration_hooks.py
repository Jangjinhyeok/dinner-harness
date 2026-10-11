"""Offline protection and content-minimization regressions."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import common
from handlers import learning_log, scope_check, secret_scan


class MigrationHooks(unittest.TestCase):
    def test_notebook_edit_is_scanned_for_secret_content_and_paths(self):
        patterns = secret_scan._load_patterns()
        fake_key = "AKIA" + "A" * 16
        hit = secret_scan._scan("NotebookEdit", {"notebook_path": "C:/w/a.ipynb", "new_source": fake_key}, patterns)
        self.assertEqual(hit.pattern_name, "aws_access_key")
        hit = secret_scan._scan("NotebookEdit", {"notebook_path": "C:/w/.env", "new_source": "x = 1"}, patterns)
        self.assertEqual(hit.pattern_name, "env_file")
        self.assertIsNone(secret_scan._scan("NotebookEdit", {"notebook_path": "C:/w/a.ipynb",
                                                             "new_source": "print(1)"}, patterns))
        self.assertIn("NotebookEdit", secret_scan._TARGET_TOOLS)

    def test_llm_provider_api_keys_are_detected(self):
        patterns = secret_scan._load_patterns()
        # Built at runtime so this source file never contains a key-shaped literal.
        keys = {
            "anthropic_api_key": "sk-" + "ant-api03-" + "Ab_9-" * 18,
            "openai_api_key": "sk-" + "proj-" + "Ab_9-" * 12,
            "google_api_key": "AI" + "za" + "Sy" + "B" * 33,
        }
        for name, key in keys.items():
            with self.subTest(name=name):
                hit = secret_scan._scan("Write", {"file_path": "C:/w/a.py", "content": f"k = '{key}'"},
                                        patterns)
                self.assertEqual(hit.pattern_name, name)
                hit = secret_scan._scan("PowerShell", {"command": f"$env:K = '{key}'"}, patterns)
                self.assertEqual(hit.pattern_name, name)
        legacy_openai = "sk-" + "A" * 20 + "T3Blbk" + "FJ" + "B" * 20
        self.assertEqual(secret_scan._scan("Bash", {"command": f"echo {legacy_openai}"}, patterns).pattern_name,
                         "openai_api_key")
        variants = {
            "anthropic_api_key": "sk-" + "ant-ort01-" + "Ab_9-" * 18,
            "openai_api_key": "sk-" + "None-" + "Ab_9-" * 30,
        }
        for name, key in variants.items():
            with self.subTest(variant=name):
                self.assertEqual(secret_scan._scan("Bash", {"command": f"echo {key}"}, patterns).pattern_name,
                                 name)
        # Kebab-case identifiers that merely start with a key prefix (also runtime-built).
        sk = "sk-"
        for benign in ("sk-ant-api03-xxxx", "use the sk-proj- prefix", "task-ant-api03-short",
                       "AIza" + "B" * 10, "task-proj-alpha-implementation-plan-v2",
                       f'<div class="{sk}admin-dashboard-container-wrapper">',
                       f"git checkout feature/{sk}proj-migration-v2-cleanup",
                       f"--{sk}proj-feature-flag-long-name-x"):
            with self.subTest(benign=benign):
                self.assertIsNone(secret_scan._scan("Write", {"file_path": "C:/w/a.md", "content": benign},
                                                    patterns))

    def test_settings_template_routes_notebook_edit_to_safety_hooks(self):
        template = json.loads((Path(__file__).resolve().parents[2] / "settings.json.template")
                              .read_text(encoding="utf-8"))
        matchers = {entry["hooks"][0]["command"].rsplit("/", 1)[-1]: entry["matcher"].split("|")
                    for entry in template["hooks"]["PreToolUse"]}
        for launcher in ("secret_scan.cmd", "scope_check.cmd"):
            self.assertIn("NotebookEdit", matchers[launcher])
            self.assertIn("Edit", matchers[launcher])
            self.assertIn("Write", matchers[launcher])

    def test_settings_template_denies_env_reads_and_recursive_delete_in_powershell(self):
        template = json.loads((Path(__file__).resolve().parents[2] / "settings.json.template")
                              .read_text(encoding="utf-8"))
        deny = set(template["permissions"]["deny"])
        for rule in ("PowerShell(Remove-Item *-Recurse*)", "PowerShell(Get-Content *.env*)",
                     "PowerShell(gc *.env*)", "PowerShell(cat *.env*)", "PowerShell(type *.env*)",
                     "PowerShell(*>.env*)"):
            self.assertIn(rule, deny)

    def test_absent_unnamed_handoff_allows_without_error_log(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(scope_check, "_HANDOFF_PATH", Path(tmp) / "HANDOFF.md"), \
             mock.patch.object(scope_check, "_HANDOFF_NAME_EXPLICIT", False), \
             mock.patch.object(scope_check, "_FENCE_ENV", None), \
             mock.patch.object(scope_check, "log_event") as log:
            self.assertIsNone(scope_check._load_handoff_scope(Path(tmp)))
            log.assert_not_called()
            with mock.patch.object(scope_check, "_HANDOFF_NAME_EXPLICIT", True):
                self.assertIsNone(scope_check._load_handoff_scope(Path(tmp)))
            self.assertEqual(log.call_args.kwargs["decision"], "error_internal")

    def test_notebook_edit_on_protected_path_is_blocked(self):
        self.assertEqual(scope_check._extract_paths("NotebookEdit", {"notebook_path": "C:/w/a.ipynb"}),
                         ["C:/w/a.ipynb"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = {"tool_name": "NotebookEdit", "cwd": str(root),
                       "tool_input": {"notebook_path": str(root / "config.toml"), "new_source": "safe"}}
            env = dict(os.environ, CODEX_HOME=str(root), CLAUDE_SCOPE_WHITELIST_MODE="enforce",
                       CLAUDE_HOOK_FAILS_CLOSED="1", PYTHONUTF8="1")
            result = subprocess.run([sys.executable, str(Path(scope_check.__file__))],
                                    input=json.dumps(payload), encoding="utf-8",
                                    capture_output=True, env=env, timeout=5)
            self.assertEqual(result.returncode, 2)
            self.assertIn("always-block", result.stderr)

    def test_controller_cannot_allow_unreadable_scope_rules(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(common, "_FAILS_CLOSED", True), \
             mock.patch.object(common, "_LOGS_DIR", Path(tmp)), \
             mock.patch.object(scope_check, "_RULES_PATH", Path(tmp) / "missing.json"), \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                scope_check._load_always_block(Path(tmp))
            self.assertEqual(caught.exception.code, 2)

    def test_protected_path_blocks_even_with_matching_pinned_fence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = {"tool_name": "Write", "cwd": str(root),
                       "tool_input": {"file_path": str(root / "config.toml"), "content": "safe"}}
            env = dict(os.environ, CODEX_HOME=str(root),
                       CLAUDE_SCOPE_FENCE="config.toml", CLAUDE_SCOPE_WHITELIST_MODE="enforce",
                       CLAUDE_HOOK_FAILS_CLOSED="1", PYTHONUTF8="1")
            result = subprocess.run([sys.executable, str(Path(scope_check.__file__))],
                                    input=json.dumps(payload), encoding="utf-8",
                                    capture_output=True, env=env, timeout=5)
            self.assertEqual(result.returncode, 2)
            self.assertIn("always-block", result.stderr)

    def test_protected_install_and_project_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            custom = base / "custom codex"
            project = base / "project"
            with mock.patch.dict(os.environ, {"CODEX_HOME": str(custom)}):
                entries = scope_check._load_always_block(project)
                for root in (custom, project / ".codex"):
                    protected = ["config.toml", "hooks.json", "rules/default.rules",
                                 "agents/reviewer.toml", "hooks/handlers/scan.py"]
                    if os.name == "nt":
                        protected += ["CONFIG.TOML", "AGENTS/reviewer.toml"]
                    for path in protected:
                        normalized = scope_check._normalize_path(str(root / path), project)
                        self.assertIsNotNone(scope_check._match_always_block(normalized, entries))
                for path in (project / "config.toml", project / "rules" / "game.json",
                             base / "custom codex sibling" / "config.toml"):
                    normalized = scope_check._normalize_path(str(path), project)
                    self.assertIsNone(scope_check._match_always_block(normalized, entries))

    def test_learning_log_does_not_retain_command_or_output(self):
        fake = "FAKE_SECRET_FOR_TEST_ONLY"
        payload = {"tool_name": "Bash", "tool_input": {"command": fake},
                   "tool_response": "build failed " + fake}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(common, "_LOGS_DIR", Path(tmp)):
            with mock.patch.object(learning_log, "read_hook_input", return_value=payload):
                with self.assertRaises(SystemExit) as caught:
                    learning_log.main()
            self.assertEqual(caught.exception.code, 0)
            saved = (Path(tmp) / "learning_log.log").read_text(encoding="utf-8")
            self.assertNotIn(fake, saved)
            self.assertEqual(json.loads(saved)["signal"], "build_failed")

    def _run_learning_log(self, payload):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(common, "_LOGS_DIR", Path(tmp)):
            with mock.patch.object(learning_log, "read_hook_input", return_value=payload):
                with self.assertRaises(SystemExit) as caught:
                    learning_log.main()
            self.assertEqual(caught.exception.code, 0)
            log = Path(tmp) / "learning_log.log"
            return json.loads(log.read_text(encoding="utf-8")) if log.exists() else None

    def test_learning_log_records_only_classification_diagnostics(self):
        fake = "FAKE_SECRET_FOR_TEST_ONLY"
        trace = ("Traceback (most recent call last):\n  File \"x.py\", line 1, in <module>\n"
                 f"    raise KeyError('{fake}')\njson.decoder.JSONDecodeError: Expecting value {fake}\n")
        rec = self._run_learning_log({"tool_name": "Bash", "tool_input": {"command": "py -3 x.py"},
                                      "tool_response": trace})
        self.assertEqual((rec["signal"], rec["diag"]), ("python_trace", "json.decoder.JSONDecodeError"))
        self.assertNotIn(fake, json.dumps(rec))
        link = "a.obj : error " + "LNK" + "2019: unresolved external symbol " + fake
        rec = self._run_learning_log({"tool_name": "PowerShell", "tool_input": {"command": "msbuild"},
                                      "tool_response": link})
        self.assertEqual((rec["signal"], rec["diag"]), ("msvc_link", "LNK" + "2019"))
        rec = self._run_learning_log({"tool_name": "Bash", "tool_input": {"command": "make"},
                                      "tool_response": "BUILD FAILED"})
        self.assertEqual(rec["signal"], "build_failed")
        self.assertNotIn("diag", rec)

    def test_learning_log_ignores_quoted_failures_from_logs_and_transcripts(self):
        record = json.dumps({"timestamp": "2026-08-06T04:42:55Z", "signal": "python_trace",
                             "traceback": "Traceback (most recent call last):"})
        self.assertIsNone(self._run_learning_log({"tool_name": "Bash", "tool_input": {"command": "py -3 summarize.py"},
                                                  "tool_response": record + "\nok\n"}))
        for command in ("tail -n 5 ~/.claude/hooks/logs/learning_log.log",
                        "Get-Content C:\\Users\\me\\.claude\\hooks\\logs\\x.log",
                        "py -3 read.py session.jsonl"):
            with self.subTest(command=command):
                self.assertIsNone(self._run_learning_log({"tool_name": "Bash", "tool_input": {"command": command},
                                                          "tool_response": "build failed"}))
        # A real failure after a quoted record is still captured.
        rec = self._run_learning_log({"tool_name": "Bash", "tool_input": {"command": "py -3 x.py"},
                                      "tool_response": record + "\nTraceback (most recent call last):\nValueError: x\n"})
        self.assertEqual((rec["signal"], rec["diag"]), ("python_trace", "ValueError"))

    def test_exception_text_is_not_logged_or_returned(self):
        fake = "FAKE_EXCEPTION_SECRET_FOR_TEST_ONLY"
        def fail():
            raise ValueError(fake)
        for closed in (False, True):
            with tempfile.TemporaryDirectory() as tmp, mock.patch.object(common, "_LOGS_DIR", Path(tmp)):
                with mock.patch.object(common, "_FAILS_CLOSED", closed), contextlib.redirect_stderr(io.StringIO()) as err:
                    with self.assertRaises(SystemExit) as caught:
                        common.run_handler(fail, hook_name="probe")
                self.assertEqual(caught.exception.code, 2 if closed else 0)
                saved = (Path(tmp) / "probe.error.log").read_text(encoding="utf-8")
                self.assertNotIn(fake, saved + err.getvalue())
                self.assertEqual(json.loads(saved)["exception_type"], "ValueError")


if __name__ == "__main__":
    unittest.main()
