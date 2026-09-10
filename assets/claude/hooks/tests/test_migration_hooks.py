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
from handlers import learning_log, scope_check


class MigrationHooks(unittest.TestCase):
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
