"""Default Builder-first guard for interactive Claude Architect sessions.

Claude may author the file bus and an ADR but must dispatch file implementation
to the Codex Builder. ``DINNER_EXECUTION_MODE=direct`` is the explicit escape
for a direct-edit session. This is an honest-session guard, not a sandbox: it
deliberately judges only structured file-edit tools and does not attempt to
parse arbitrary shell commands.
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

_HANDLER_DIR = Path(__file__).resolve().parent
_HOOKS_ROOT = _HANDLER_DIR.parent
if str(_HOOKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_HOOKS_ROOT))

from lib.common import (  # noqa: E402
    exit_allow,
    exit_block,
    get_cwd,
    get_env_override,
    log_event,
    parse_apply_patch,
    read_hook_input,
    run_handler,
)


_HOOK_NAME = "builder_guard"
_EVENT = "PreToolUse"
_DIRECT_MODE = "direct"
_TARGET_TOOLS = {"Edit", "Write", "apply_patch"}
_BUS_NAMES = {"HANDOFF.md", "RESULT.md", "INPUT.md"}


def _path_digest(path: str) -> str:
    return hashlib.sha256(path.encode("utf-8")).hexdigest()


def _extract_paths(tool_name: str, tool_input: dict) -> list[str]:
    if tool_name == "apply_patch":
        return [path for path, _ in parse_apply_patch(tool_input.get("command", "") or "")]
    path = tool_input.get("file_path", "") or ""
    return [path] if path else []


def _allowed_path(raw_path: str, cwd: Path) -> bool:
    """True only for Architect artifacts and Claude persistent-memory Markdown."""
    try:
        path = (Path(raw_path) if Path(raw_path).is_absolute() else cwd / raw_path).resolve(
            strict=False
        )
    except OSError:
        return False
    try:
        relative = path.relative_to(cwd.resolve()).as_posix()
    except (OSError, ValueError):
        relative = None
    if relative is not None:
        if relative in _BUS_NAMES:
            return True
        if relative.startswith("HANDOFF_") and relative.endswith(".md") and "/" not in relative:
            return True
        if relative.startswith("docs/architecture/") and relative.endswith(".md"):
            return True

    try:
        claude_home = Path(
            get_env_override("CLAUDE_CONFIG_DIR", Path.home() / ".claude")
        ).expanduser().resolve(strict=False)
        memory_relative = path.relative_to(claude_home)
    except (OSError, ValueError):
        return False
    parts = memory_relative.parts
    return (
        len(parts) >= 4
        and parts[0] == "projects"
        and parts[2] == "memory"
        and path.suffix.lower() == ".md"
    )


def guarded_paths(payload: dict) -> list[str]:
    """Return code-edit targets reserved for Codex outside direct-edit sessions."""
    if os.environ.get("DINNER_EXECUTION_MODE") == _DIRECT_MODE:
        return []
    tool_name = payload.get("tool_name")
    if tool_name not in _TARGET_TOOLS:
        return []
    paths = _extract_paths(tool_name, payload.get("tool_input") or {})
    if not paths:
        # A file edit whose target cannot be understood is not safe to classify
        # as an Architect artifact. Fail closed outside the explicit direct-edit
        # escape, where this guard is intentionally disabled.
        return ["<unparseable file edit>"]
    cwd = get_cwd(payload)
    return [path for path in paths if not _allowed_path(path, cwd)]


def main() -> None:
    payload = read_hook_input()
    blocked = guarded_paths(payload)
    if not blocked:
        exit_allow()
    target = blocked[0]
    log_event(
        _HOOK_NAME,
        event=_EVENT,
        decision="block",
        reason="builder_first_code_edit",
        tool_name=payload.get("tool_name", ""),
        blocked_path_sha256=_path_digest(target),
        blocked_path_count=len(blocked),
        mode="builder-first",
    )
    exit_block(
        "[builder_guard:block] Builder-first mode reserves implementation edits "
        "for Codex Builder. Write HANDOFF*.md, RESULT.md, INPUT.md, or "
        "docs/architecture/*.md; Claude persistent memory Markdown under "
        "<CLAUDE_CONFIG_DIR>/projects/*/memory/ is also allowed. Then dispatch "
        "orchestrate.py build. "
        f"Blocked: {target}"
    )


if __name__ == "__main__":
    run_handler(main, hook_name=_HOOK_NAME)
