"""Unit tests for Builder-first path exceptions (stdlib unittest only)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


_HOOKS_ROOT = Path(__file__).resolve().parent.parent
if str(_HOOKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_HOOKS_ROOT))

from handlers import builder_guard  # noqa: E402


def _edit_payload(cwd: Path, path: str) -> dict:
    return {
        "tool_name": "Edit",
        "cwd": str(cwd),
        "tool_input": {"file_path": path},
    }


def _trivial_edit_payload(
    cwd: Path, path: str, old_string: str = "old", new_string: str = "new"
) -> dict:
    return {
        "tool_name": "Edit",
        "cwd": str(cwd),
        "tool_input": {
            "file_path": path,
            "old_string": old_string,
            "new_string": new_string,
        },
    }


class BuilderGuardPaths(unittest.TestCase):
    def test_project_implementation_file_is_blocked(self):
        self.assertEqual(
            builder_guard.guarded_paths(_edit_payload(Path("C:/repo"), "src/feature.py")),
            ["src/feature.py"],
        )

    def test_root_bus_file_is_allowed(self):
        self.assertEqual(
            builder_guard.guarded_paths(_edit_payload(Path("C:/repo"), "HANDOFF.md")),
            [],
        )

    def test_project_architecture_document_is_allowed(self):
        self.assertEqual(
            builder_guard.guarded_paths(
                _edit_payload(Path("C:/repo"), "docs/architecture/foo.md")
            ),
            [],
        )

    def test_claude_memory_markdown_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            claude_home = Path(tmp) / ".claude"
            memory = claude_home / "projects" / "project-slug" / "memory" / "note.md"
            with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(claude_home)}):
                self.assertEqual(
                    builder_guard.guarded_paths(_edit_payload(Path("C:/repo"), str(memory))),
                    [],
                )

    def test_memory_path_traversal_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            claude_home = Path(tmp) / ".claude"
            escaped = claude_home / "projects" / "project-slug" / "memory" / ".." / ".." / "evil.md"
            with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(claude_home)}):
                self.assertEqual(
                    builder_guard.guarded_paths(_edit_payload(Path("C:/repo"), str(escaped))),
                    [str(escaped)],
                )

    def test_direct_mode_allows_every_path(self):
        with mock.patch.dict(os.environ, {"DINNER_EXECUTION_MODE": "direct"}):
            self.assertEqual(
                builder_guard.guarded_paths(_edit_payload(Path("C:/repo"), "src/feature.py")),
                [],
            )

    def test_trivial_edit_outside_infra_is_allowed(self):
        self.assertEqual(
            builder_guard.guarded_paths(
                _trivial_edit_payload(Path("C:/repo"), "src/feature.py")
            ),
            [],
        )

    def test_edit_over_line_threshold_is_blocked(self):
        self.assertEqual(
            builder_guard.guarded_paths(
                _trivial_edit_payload(
                    Path("C:/repo"), "src/feature.py", new_string="one\ntwo\nthree"
                )
            ),
            ["src/feature.py"],
        )

    def test_trivial_edit_to_harness_toml_is_blocked(self):
        self.assertEqual(
            builder_guard.guarded_paths(
                _trivial_edit_payload(Path("C:/repo"), "harness.toml")
            ),
            ["harness.toml"],
        )

    def test_trivial_edit_to_hooks_dir_is_blocked(self):
        path = "assets/claude/hooks/handlers/builder_guard.py"
        self.assertEqual(
            builder_guard.guarded_paths(_trivial_edit_payload(Path("C:/repo"), path)),
            [path],
        )

    def test_trivial_edit_to_case_variant_infra_path_is_blocked(self):
        path = "Assets/Claude/Hooks/handlers/builder_guard.py"
        self.assertEqual(
            builder_guard.guarded_paths(_trivial_edit_payload(Path("C:/repo"), path)),
            [path],
        )

    def test_expanded_infra_paths_are_not_trivial_fast_path_targets(self):
        base = Path(__file__).resolve().parents[4]
        claude_home = Path("C:/nonexistent-claude-home-for-this-check")
        for relative_path in [
            "install.py",
            "refresh.py",
            "check.py",
            "adapters/codex.py",
            "assets/codex/AGENTS.md",
            "content/rules/agent-routing.md",
            "content/roles/ROLE_BUILDER.md",
            "content/instructions/CLAUDE.md",
        ]:
            self.assertTrue(
                builder_guard._is_infra_path(base / relative_path, base, claude_home),
                relative_path,
            )

    def test_trivial_edit_to_settings_json_is_blocked(self):
        self.assertEqual(
            builder_guard.guarded_paths(
                _trivial_edit_payload(Path("C:/repo"), "settings.json")
            ),
            ["settings.json"],
        )

    def test_trivial_edit_under_claude_home_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            claude_home = Path(tmp) / ".claude"
            target = claude_home / "notes" / "note.txt"
            with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(claude_home)}):
                self.assertEqual(
                    builder_guard.guarded_paths(
                        _trivial_edit_payload(Path("C:/repo"), str(target))
                    ),
                    [str(target)],
                )

    def test_trivial_write_is_still_blocked(self):
        payload = {
            "tool_name": "Write",
            "cwd": "C:/repo",
            "tool_input": {"file_path": "src/feature.py", "content": "small"},
        }
        self.assertEqual(builder_guard.guarded_paths(payload), ["src/feature.py"])

    def test_trivial_replace_all_is_still_blocked(self):
        payload = _trivial_edit_payload(Path("C:/repo"), "src/feature.py")
        payload["tool_input"]["replace_all"] = True
        self.assertEqual(builder_guard.guarded_paths(payload), ["src/feature.py"])


if __name__ == "__main__":
    unittest.main()
