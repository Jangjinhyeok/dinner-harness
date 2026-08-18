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
import subprocess
import tempfile
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
_TRIVIAL_MAX_LINES = 2
_INFRA_REPO_RELATIVE_EXACT = {"harness.toml", "orchestrate.py"}
_INFRA_REPO_RELATIVE_PREFIXES = ("orchestrator/", "assets/claude/hooks/")


def _path_digest(path: str) -> str:
    return hashlib.sha256(path.encode("utf-8")).hexdigest()


def _extract_paths(tool_name: str, tool_input: dict) -> list[str]:
    if tool_name == "apply_patch":
        return [path for path, _ in parse_apply_patch(tool_input.get("command", "") or "")]
    path = tool_input.get("file_path", "") or ""
    return [path] if path else []


def _in_session_scratchpad(path: Path) -> bool:
    """True for the per-session scratchpad the harness itself designates for temp files.

    Layout: <tempdir>/claude/<project-slug>/<session-id>/scratchpad/...
    Throwaway analysis scripts there are not implementation files, so dispatching
    them to the Builder is meaningless; blocking them only forces a shell workaround.
    """
    try:
        relative = path.relative_to(Path(tempfile.gettempdir()).resolve(strict=False))
    except (OSError, ValueError):
        return False
    parts = relative.parts
    return len(parts) >= 5 and parts[0] == "claude" and parts[3] == "scratchpad"


def _repo_root(cwd: Path) -> Path:
    """Return the git worktree root, falling back to the hook's cwd."""
    try:
        fallback = cwd.resolve(strict=False)
    except Exception:  # noqa: BLE001 - a hook failure must not become a block
        fallback = cwd
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=2,
        )
        root = result.stdout.strip()
        return Path(root).resolve(strict=False) if root else fallback
    except Exception:  # noqa: BLE001 - git is only a best-effort base lookup
        return fallback


def _resolve_claude_home() -> Path:
    return Path(
        get_env_override("CLAUDE_CONFIG_DIR", Path.home() / ".claude")
    ).expanduser().resolve(strict=False)


def _allowed_path(raw_path: str, cwd: Path, base: Path) -> bool:
    """True only for Architect artifacts and Claude persistent-memory Markdown."""
    try:
        path = (Path(raw_path) if Path(raw_path).is_absolute() else cwd / raw_path).resolve(
            strict=False
        )
    except OSError:
        return False
    try:
        relative = path.relative_to(base).as_posix()
    except (OSError, ValueError):
        relative = None
    if relative is not None:
        if relative in _BUS_NAMES:
            return True
        if relative.startswith("HANDOFF_") and relative.endswith(".md") and "/" not in relative:
            return True
        if relative.startswith("docs/architecture/") and relative.endswith(".md"):
            return True

    if _in_session_scratchpad(path):
        return True

    try:
        claude_home = _resolve_claude_home()
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


def _line_span(text: str) -> int:
    return text.count("\n") + 1 if text else 1


def _is_infra_path(path: Path, base: Path, claude_home: Path) -> bool:
    """True for harness safety-net infrastructure, excluded from the trivial fast path."""
    if path.suffix.lower() == ".json" and path.name.lower().startswith("settings"):
        return True
    try:
        path.relative_to(claude_home)
        return True
    except (OSError, ValueError):
        pass
    try:
        relative = path.relative_to(base).as_posix().casefold()
    except (OSError, ValueError):
        return False
    if relative in _INFRA_REPO_RELATIVE_EXACT:
        return True
    return any(relative.startswith(prefix) for prefix in _INFRA_REPO_RELATIVE_PREFIXES)


def _is_trivial_edit(
    tool_name: str, tool_input: dict, raw_path: str, cwd: Path, base: Path, claude_home: Path
) -> bool:
    if tool_name != "Edit":
        return False
    old_string = tool_input.get("old_string")
    new_string = tool_input.get("new_string")
    if old_string is None or new_string is None:
        return False
    if tool_input.get("replace_all"):
        return False
    if (
        _line_span(old_string) > _TRIVIAL_MAX_LINES
        or _line_span(new_string) > _TRIVIAL_MAX_LINES
    ):
        return False
    try:
        path = (Path(raw_path) if Path(raw_path).is_absolute() else cwd / raw_path).resolve(
            strict=False
        )
    except OSError:
        return False
    return not _is_infra_path(path, base, claude_home)


def guarded_paths(payload: dict) -> list[str]:
    """Return code-edit targets reserved for Codex outside direct-edit sessions."""
    if os.environ.get("DINNER_EXECUTION_MODE") == _DIRECT_MODE:
        return []
    tool_name = payload.get("tool_name")
    if tool_name not in _TARGET_TOOLS:
        return []
    tool_input = payload.get("tool_input") or {}
    paths = _extract_paths(tool_name, tool_input)
    if not paths:
        # A file edit whose target cannot be understood is not safe to classify
        # as an Architect artifact. Fail closed outside the explicit direct-edit
        # escape, where this guard is intentionally disabled.
        return ["<unparseable file edit>"]
    cwd = get_cwd(payload)
    base = _repo_root(cwd)
    claude_home = _resolve_claude_home()
    blocked = []
    for path in paths:
        if _allowed_path(path, cwd, base):
            continue
        if _is_trivial_edit(tool_name, tool_input, path, cwd, base, claude_home):
            continue
        blocked.append(path)
    return blocked


def main() -> None:
    payload = read_hook_input()
    blocked = guarded_paths(payload)
    if not blocked:
        if payload.get("tool_name") in _TARGET_TOOLS:
            log_event(
                _HOOK_NAME,
                event=_EVENT,
                decision="allow",
                tool_name=payload.get("tool_name", ""),
                mode="builder-first",
            )
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
        "orchestrate.py build. Edits beyond the 2-line trivial fast path or targeting "
        "harness infrastructure remain blocked. "
        f"Blocked: {target}"
    )


if __name__ == "__main__":
    run_handler(main, hook_name=_HOOK_NAME)
