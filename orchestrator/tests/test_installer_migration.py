"""Temporary-only installer contracts for the Codex-first migration."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib
from types import SimpleNamespace
import unittest
from unittest import mock

import check
import install
import refresh
from adapters import codex
from orchestrator.routing import load_routing_config, resolve_profile


ROOT = Path(__file__).resolve().parents[2]


class TestCodexInstallMigration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dh-install-test-")
        self.addCleanup(self.temp.cleanup)
        self.dest = Path(self.temp.name) / "한글 home"
        self.manifest = tomllib.loads((ROOT / "harness.toml").read_text(encoding="utf-8"))

    def render(self, *, dry_run=False, adopt=False):
        cfg = dict(self.manifest["targets"]["codex"], adopt_existing=adopt)
        return codex.install(ROOT, cfg, self.manifest.get("vars", {}), self.dest, "", dry_run)

    def test_toml_roundtrip_preserves_exact_text(self):
        original = '\n한글 C:\\Users\\name\\test """ quote\n\tbackslash\\end'
        self.assertEqual(tomllib.loads("text = " + codex._toml_multiline(original))["text"], original)

    @unittest.skipUnless(os.name == "nt", "PowerShell hook execution requires Windows")
    def test_windows_hook_commands_preserve_literal_paths_stdin_and_exit_codes(self):
        root = Path(self.temp.name) / "한글 space & $dollar 'quote'"
        handlers = root / "hooks/handlers"
        handlers.mkdir(parents=True)
        codex._write_hooks_json(root, [], False)
        groups = json.loads((root / "hooks.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
        for name, group in zip(("secret_scan", "scope_check"), groups):
            script = handlers / (name + ".py")
            script.write_text("import sys\ncode = int(sys.stdin.read())\nprint('fixture reached')\nsys.exit(code)\n")
            for code in (0, 1, 2):
                with self.subTest(handler=name, exit_code=code):
                    result = subprocess.run(
                        ["powershell.exe", "-NoProfile", "-Command", group["hooks"][0]["command"]],
                        input=str(code), capture_output=True, text=True,
                        encoding="utf-8", errors="replace", timeout=15,
                    )
                    self.assertEqual(result.returncode, code, result.stderr)
                    self.assertEqual(result.stdout.strip(), "fixture reached")
                    self.assertEqual(result.stderr, "")

        with mock.patch.object(codex, "sys", SimpleNamespace(executable=str(root / "missing-python.exe"))):
            codex._write_hooks_json(root, [], False)
        groups = json.loads((root / "hooks.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
        for group in groups:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", group["hooks"][0]["command"]],
                input="0", capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=15,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("CommandNotFoundException", result.stderr)
            self.assertNotIn("fixture reached", result.stdout)

    def test_posix_hook_commands_keep_shell_quoting(self):
        self.dest.mkdir()
        with mock.patch.object(codex, "os", SimpleNamespace(name="posix")):
            codex._write_hooks_json(self.dest, [], False)
        groups = json.loads((self.dest / "hooks.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
        for name, group in zip(("secret_scan", "scope_check"), groups):
            self.assertEqual(shlex.split(group["hooks"][0]["command"]), [
                Path(sys.executable).as_posix(),
                (self.dest / "hooks/handlers" / (name + ".py")).as_posix(),
            ])

    @unittest.skipUnless(os.name == "nt", "PowerShell hook execution requires Windows")
    def test_windows_generated_commands_preserve_handler_verdicts(self):
        self.dest.mkdir()
        for directory in ("handlers", "lib", "rules"):
            shutil.copytree(ROOT / "assets/claude/hooks" / directory,
                            self.dest / "hooks" / directory,
                            ignore=shutil.ignore_patterns("__pycache__"))
        codex._write_hooks_json(self.dest, [], False)
        groups = json.loads((self.dest / "hooks.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
        env = dict(os.environ, DINNER_HARNESS_HOME=str(self.dest),
                   CLAUDE_SECRET_SCAN_MODE="enforce", CLAUDE_SCOPE_WHITELIST_MODE="dryrun",
                   CLAUDE_SCOPE_FENCE=(self.dest / "allowed.txt").as_posix())
        cases = [
            (0, "Bash", {"command": "Write-Output harmless"}, 0),
            (0, "Write", {"file_path": str(self.dest / ".env"), "content": "harmless fixture"}, 2),
            (1, "apply_patch", {"command": "*** Begin Patch\n*** Add File: allowed.txt\n+harmless\n*** End Patch\n"}, 0),
            (1, "apply_patch", {"command": "*** Begin Patch\n*** Add File: .codex/hooks.json\n+harmless\n*** End Patch\n"}, 2),
        ]
        for index, tool, tool_input, expected in cases:
            name = ("secret_scan", "scope_check")[index]
            payload = json.dumps({"tool_name": tool, "tool_input": tool_input, "cwd": str(self.dest)})
            direct = [sys.executable, str(self.dest / "hooks/handlers" / (name + ".py"))]
            wrapped = ["powershell.exe", "-NoProfile", "-Command", groups[index]["hooks"][0]["command"]]
            for route, argv in (("direct", direct), ("generated", wrapped)):
                with self.subTest(handler=name, route=route, expected=expected):
                    result = subprocess.run(argv, input=payload, capture_output=True,
                                            text=True, encoding="utf-8", errors="replace",
                                            env=env, timeout=15)
                    self.assertEqual(result.returncode, expected, result.stderr)
                    if expected == 2:
                        self.assertIn("[" + name + ":block]", result.stderr)
        # Handlers inspect payloads; the proposed edits must never be applied.
        self.assertFalse((self.dest / "allowed.txt").exists())
        self.assertFalse((self.dest / ".env").exists())

    def test_agents_use_logical_policy_and_read_only_consult(self):
        self.render()
        routing = load_routing_config(ROOT / "content/routing.toml")
        agents = list((self.dest / "agents").glob("*.toml"))
        self.assertTrue(agents)
        for agent in agents:
            data = tomllib.loads(agent.read_text(encoding="utf-8"))
            role = routing["native_agents"][data["name"]]
            profile = resolve_profile(routing, "codex_only", role)
            self.assertEqual(data["model"], profile.model)
            self.assertEqual(data["model_reasoning_effort"], profile.effort)
            if role in {"architect", "reviewer", "explorer"}:
                self.assertEqual(data["sandbox_mode"], "read-only")

    def test_repeat_install_preserves_user_hooks_and_extra_skill(self):
        self.dest.mkdir()
        user_hook = {"matcher": "Bash", "hooks": [{"type": "command", "command": "user-script"}]}
        (self.dest / "hooks.json").write_text(json.dumps({"description": "mine", "hooks": {"PreToolUse": [user_hook]}}), encoding="utf-8")
        personal = self.dest / "skills/personal/SKILL.md"
        personal.parent.mkdir(parents=True)
        personal.write_text("user owned", encoding="utf-8")
        config = self.dest / "config.toml"
        config.write_text("# user config\n", encoding="utf-8")
        self.render()
        before = (self.dest / "hooks.json").read_bytes()
        self.render()
        self.assertEqual((self.dest / "hooks.json").read_bytes(), before)
        data = json.loads(before)
        self.assertEqual(data["description"], "mine")
        self.assertIn(user_hook, data["hooks"]["PreToolUse"])
        self.assertEqual(personal.read_text(), "user owned")
        self.assertEqual(config.read_text(), "# user config\n")
        self.assertNotIn("suggest_compact", before.decode())
        self.assertNotIn("learning_log", before.decode())
        self.assertNotIn("py -3", before.decode())
        self.assertIn(self.dest.resolve().as_posix(), before.decode())
        present, problems, leftovers = check.check_install("codex", self.dest)
        self.assertTrue(present)
        self.assertEqual(problems, [])
        self.assertIn(("skills/personal/SKILL.md", True), leftovers)
        # Installation equality and discovery collisions are separate axes.
        other = Path(self.temp.name) / "other-discovery/user-copy/SKILL.md"
        other.parent.mkdir(parents=True)
        other.write_text("---\nname: surgical-changes\n---\nuser text", encoding="utf-8")
        before_other = other.read_bytes()
        duplicates, errors = check.check_skill_duplicates([self.dest / "skills", other.parent.parent])
        self.assertIn("surgical-changes", duplicates)
        self.assertEqual(other.read_bytes(), before_other)
        # The intentionally metadata-free personal skill is diagnosed, preserved.
        self.assertEqual(len(errors), 1)

    def test_conflicts_fail_before_any_destination_writes(self):
        self.dest.mkdir()
        original = self.dest / "AGENTS.md"
        original.write_text("personal", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "conflicts"):
            self.render()
        self.assertEqual(sorted(p.name for p in self.dest.iterdir()), ["AGENTS.md"])
        self.assertEqual(original.read_text(), "personal")

    def test_removed_skill_is_backed_up_and_retired_only_when_unchanged(self):
        self.render()
        target = self.dest / "skills/tech-debt/SKILL.md"
        original = target.read_bytes()
        self.manifest["targets"]["codex"]["skills_drop"].append("tech-debt")
        preview = self.render(dry_run=True)
        self.assertIn(("retire_owned", target.resolve()), preview)
        self.assertEqual(target.read_bytes(), original)
        self.render()
        self.assertFalse(target.exists())
        backups = list((self.dest / ".dinner-harness-backups").glob("*/skills/tech-debt/SKILL.md"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        self.assertNotIn("skills/tech-debt/SKILL.md", json.loads((self.dest / codex.OWNERSHIP).read_text(encoding="utf-8"))["files"])
        self.assertFalse(any(action == "retire_owned" for action, _ in self.render()))

    def test_removed_user_modified_skill_is_preserved_even_with_adoption(self):
        self.render()
        target = self.dest / "skills/tech-debt/SKILL.md"
        target.write_text("personal modification", encoding="utf-8")
        self.manifest["targets"]["codex"]["skills_drop"].append("tech-debt")
        self.assertIn(("skip", target.resolve()), self.render(adopt=True))
        self.assertEqual(target.read_text(), "personal modification")

    def test_obsolete_receipt_traversal_fails_before_writes(self):
        self.render()
        receipt = self.dest / codex.OWNERSHIP
        state = json.loads(receipt.read_text(encoding="utf-8"))
        state["files"]["skills/../SKILL.md"] = "invalid"
        receipt.write_text(json.dumps(state), encoding="utf-8")
        before = (self.dest / "AGENTS.md").read_bytes()
        with self.assertRaisesRegex(RuntimeError, "invalid obsolete ownership path"):
            self.render(adopt=True)
        self.assertEqual((self.dest / "AGENTS.md").read_bytes(), before)
        self.assertFalse((self.dest / ".dinner-harness-backups").exists())

    def test_modified_owned_files_remain_protected(self):
        self.render()
        target = self.dest / "AGENTS.md"
        target.write_text("user modification", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "user-modified"):
            self.render()
        self.assertEqual(target.read_text(), "user modification")

    def test_hooks_directory_conflict_is_detected_before_writes(self):
        (self.dest / "hooks.json").mkdir(parents=True)
        with self.assertRaisesRegex(RuntimeError, "not a file"):
            self.render()
        self.assertEqual([path.name for path in self.dest.iterdir()], ["hooks.json"])

    def test_explicit_adoption_backs_up_only_conflicts(self):
        self.dest.mkdir()
        original = self.dest / "AGENTS.md"
        original.write_text("legacy instructions", encoding="utf-8")
        self.render(adopt=True, dry_run=True)
        self.assertEqual(list(self.dest.iterdir()), [original])
        self.render(adopt=True)
        backups = list((self.dest / ".dinner-harness-backups").glob("*/AGENTS.md"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), "legacy instructions")
        self.assertNotEqual(original.read_text(encoding="utf-8"), "legacy instructions")

    def test_custom_home_default_and_live_guard_agree(self):
        with mock.patch.dict(os.environ, {"CODEX_HOME": str(self.dest)}):
            self.assertEqual(install.default_dest("codex"), self.dest.resolve())
            self.assertTrue(install.is_live_dest("codex", self.dest))
            self.assertTrue(install.is_live_dest("codex", self.dest / "nested"))
            with self.assertRaises(SystemExit):
                install.main(["--target", "codex"])

    def test_codex_refresh_does_not_select_claude(self):
        with mock.patch.object(refresh.check, "main", return_value=0) as checks, \
             mock.patch.object(refresh.install, "main", return_value=0) as installs:
            self.assertEqual(refresh.refresh(apply=True, target="codex"), 0)
        self.assertEqual(checks.call_args_list, [mock.call(["--no-install", "--target", "codex"]), mock.call(["--target", "codex"])])
        self.assertEqual(installs.call_args_list, [mock.call(["--target", "codex", "--allow-live", "--dry-run"]), mock.call(["--target", "codex", "--allow-live"])])

    def test_codex_check_does_not_require_legacy_curation(self):
        with mock.patch.object(check, "check_catalog", return_value=({"Skills": 0, "Agents": 0, "Hooks": 0}, [])), \
             mock.patch.object(check, "check_curation", side_effect=AssertionError("Claude curation called")), \
             mock.patch.object(check, "check_codex_generated", return_value=[]):
            self.assertEqual(check.main(["--target", "codex", "--no-install"]), 0)

    def test_owned_hooks_remove_exact_prior_entries_only(self):
        old = {"matcher": "Edit", "hooks": [{"type": "command", "command": "old-managed"}]}
        user = {"matcher": "Edit", "hooks": [{"type": "command", "command": "user"}]}
        new = {"matcher": "Edit", "hooks": [{"type": "command", "command": "new-managed"}]}
        merged = codex._merge_hooks({"hooks": {"PreToolUse": [old, user]}}, {"hooks": {"PreToolUse": [new]}}, {"PreToolUse": [old]})
        self.assertEqual(merged["hooks"]["PreToolUse"], [user, new])

    def test_explicit_legacy_hook_adoption_backs_up_and_replaces_exact_definitions(self):
        self.dest.mkdir()
        hooks = {}
        for event, _, entry in codex._legacy_hooks(self.dest.resolve()):
            hooks.setdefault(event, []).append(entry)
        user = {"matcher": "Bash", "hooks": [{"type": "command", "command": "user-script"}]}
        hooks["PreToolUse"].append(user)
        modified = json.loads(json.dumps(hooks["PreToolUse"][2]))
        modified["hooks"][0]["timeout"] = 99
        hooks["PreToolUse"].append(modified)
        hook_file = self.dest / "hooks.json"
        original = json.dumps({"description": "user metadata", "hooks": hooks}).encode()
        hook_file.write_bytes(original)
        plan = self.render(adopt=True, dry_run=True)
        self.assertEqual(hook_file.read_bytes(), original)
        self.assertEqual(sum(action.startswith("retire_hook:") for action, _ in plan), 4)
        self.assertTrue(any(action == "backup" and path.name == "hooks.json" for action, path in plan))
        self.assertFalse((self.dest / ".dinner-harness-backups").exists())
        self.render(adopt=True)
        result = json.loads(hook_file.read_text(encoding="utf-8"))
        entries = result["hooks"]["PreToolUse"]
        self.assertEqual(len(entries), 4)  # 2 canonical plus 2 unrelated user entries.
        self.assertIn(user, entries)
        self.assertIn(modified, entries)
        self.assertEqual(result["hooks"]["PostToolUse"], [])
        self.assertEqual(result["description"], "user metadata")
        backups = list((self.dest / ".dinner-harness-backups").glob("*/hooks.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        for event, _, legacy in codex._legacy_hooks(self.dest.resolve()):
            self.assertNotIn(legacy, result["hooks"].get(event, []))

    def test_legacy_hook_default_install_does_not_infer_ownership(self):
        self.dest.mkdir()
        hooks = {}
        for event, _, entry in codex._legacy_hooks(self.dest.resolve()):
            hooks.setdefault(event, []).append(entry)
        (self.dest / "hooks.json").write_text(json.dumps({"hooks": hooks}), encoding="utf-8")
        self.render()
        result = json.loads((self.dest / "hooks.json").read_text(encoding="utf-8"))
        for event, _, legacy in codex._legacy_hooks(self.dest.resolve()):
            self.assertIn(legacy, result["hooks"][event])

    def test_parent_file_conflict_prevents_earlier_writes(self):
        self.dest.mkdir()
        (self.dest / "blocked").write_text("user file", encoding="utf-8")

        def fake_render(repo, cfg, variables, root, username, dry_run):
            first = root / "first.toml"
            first.write_text("first", encoding="utf-8")
            second = root / "blocked/second.toml"
            second.parent.mkdir()
            second.write_text("second", encoding="utf-8")
            return [("copy", first), ("copy", second)]

        with mock.patch.object(codex, "_render", side_effect=fake_render):
            with self.assertRaisesRegex(RuntimeError, "parent is not a directory"):
                self.render()
        self.assertFalse((self.dest / "first.toml").exists())
        self.assertFalse((self.dest / codex.OWNERSHIP).exists())
        self.assertEqual((self.dest / "blocked").read_text(), "user file")

    def test_backup_parent_file_conflict_prevents_all_writes(self):
        self.dest.mkdir()
        (self.dest / "AGENTS.md").write_text("legacy", encoding="utf-8")
        (self.dest / ".dinner-harness-backups").write_text("user file", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "parent is not a directory"):
            self.render(adopt=True)
        self.assertFalse((self.dest / "orchestrate.py").exists())
        self.assertEqual((self.dest / "AGENTS.md").read_text(), "legacy")

    def test_unknown_files_in_managed_directories_are_advisory(self):
        self.render()
        personal = self.dest / "roles/personal.md"
        personal.write_text("my rules", encoding="utf-8")
        _, problems, leftovers = check.check_install("codex", self.dest)
        self.assertEqual(problems, [])
        self.assertIn(("roles/personal.md", True), leftovers)

    def test_destination_symlink_is_rejected_without_touching_target(self):
        self.dest.mkdir()
        outside = Path(self.temp.name) / "outside.md"
        outside.write_text("user data", encoding="utf-8")
        try:
            (self.dest / "AGENTS.md").symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"symlink unavailable: {exc}")
        with self.assertRaisesRegex(RuntimeError, "symlink"):
            self.render(adopt=True)
        self.assertEqual(outside.read_text(), "user data")


if __name__ == "__main__":
    unittest.main()
