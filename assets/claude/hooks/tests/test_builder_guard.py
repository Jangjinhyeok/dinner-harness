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


if __name__ == "__main__":
    unittest.main()
