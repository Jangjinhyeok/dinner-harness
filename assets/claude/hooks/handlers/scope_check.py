"""ADR-0005 scope-whitelist PreToolUse hook.

Reads a Claude Code hook payload from stdin. For ``Edit`` / ``Write``
calls, normalises ``file_path`` to an absolute POSIX path and runs two
policy layers:

  1. always-block: paths matching ``rules/scope_protect.json`` are
     blocked unconditionally inside ``~/.claude/`` (dryrun-exempt,
     immediate enforce). Mode ``off`` is the only escape.
  2. scope codeblock: paths must match an entry in the first
     ``` ```scope ``` codeblock of ``~/.claude/HANDOFF.md``. An absent
     or empty block is fail-open (compat with cycles that pre-date
     ADR-0005).

Mode is taken from ``CLAUDE_SCOPE_WHITELIST_MODE``. Default is
``dryrun``. Promotion to ``enforce`` is a separate, explicit gate.
"""
from __future__ import annotations

import fnmatch
import json
import re
import sys
from pathlib import Path
from typing import NamedTuple, Optional

# Make ``lib.common`` importable when launched directly as
# ``py -3 .../handlers/scope_check.py`` from the BAT wrapper. Mirrors
# ``secret_scan.py``.
_HANDLER_DIR = Path(__file__).resolve().parent
_HOOKS_ROOT = _HANDLER_DIR.parent
if str(_HOOKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_HOOKS_ROOT))

from lib.common import (  # noqa: E402  (sys.path insert above)
    exit_allow,
    exit_block,
    exit_warn,
    get_cwd,
    get_env_override,
    log_event,
    read_hook_input,
    run_handler,
)


_HOOK_NAME = "scope_check"
_EVENT = "PreToolUse"
_CLAUDE_HOME = Path.home() / ".claude"
_RULES_PATH = _HOOKS_ROOT / "rules" / "scope_protect.json"
_HANDOFF_PATH = _CLAUDE_HOME / "HANDOFF.md"
_TARGET_TOOLS = {"Edit", "Write"}

# Absolute-path detector. Matches Windows ``C:/...`` / ``C:\...`` and
# POSIX-style ``/...``. Used in place of ``PurePath.is_absolute`` to
# keep behaviour identical regardless of host platform.
_ABS_RE = re.compile(r"^[A-Za-z]:[\\/]|^[\\/]")

# First ``` ```scope ``` fenced block in HANDOFF.md.
_SCOPE_BLOCK_RE = re.compile(
    r"^```scope\s*$(.*?)^```\s*$",
    re.DOTALL | re.MULTILINE,
)


class Pattern(NamedTuple):
    raw: str          # original entry text (for log / stderr)
    normalized: str   # absolute POSIX form, lowercase drive letter
    match_type: str   # "exact" | "prefix" | "glob"


def _drive_lower(posix_path: str) -> str:
    """Lowercase a Windows drive letter on a POSIX-form path."""
    if len(posix_path) >= 2 and posix_path[1] == ":":
        return posix_path[0].lower() + posix_path[1:]
    return posix_path


_CLAUDE_HOME_POSIX = _drive_lower(_CLAUDE_HOME.as_posix()).rstrip("/")


def _classify_pattern(spec: str) -> str:
    if spec.endswith("/"):
        return "prefix"
    if any(ch in spec for ch in ("*", "?", "[")):
        return "glob"
    return "exact"


def _normalize_path(path_str: str, cwd: Path) -> str:
    """Return an absolute POSIX path with lowercase drive letter."""
    if _ABS_RE.match(path_str):
        p = Path(path_str)
    else:
        p = cwd / path_str
    try:
        resolved = p.resolve(strict=False)
    except OSError:
        resolved = p
    return _drive_lower(resolved.as_posix())


def _matches(abs_path: str, pattern: Pattern) -> bool:
    target = pattern.normalized
    if pattern.match_type == "exact":
        return abs_path == target
    if pattern.match_type == "prefix":
        return abs_path.startswith(target)
    if pattern.match_type == "glob":
        return fnmatch.fnmatchcase(abs_path, target)
    return False


def _load_always_block() -> list[Pattern]:
    """Load ``rules/scope_protect.json`` and return its ``always_block``
    list as normalised Pattern entries. On any error returns ``[]`` and
    logs ``error_internal`` — caller treats this as fail-open for the
    always-block layer (the scope-codeblock layer still runs).
    """
    try:
        with _RULES_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        log_event(
            _HOOK_NAME,
            event=_EVENT,
            decision="error_internal",
            reason=f"ruleset load failed: {type(exc).__name__}: {exc}",
        )
        return []

    out: list[Pattern] = []
    for entry in data.get("always_block", []) or []:
        match_type = entry.get("match")
        rel = entry.get("path", "") or ""
        if match_type not in {"exact", "prefix", "glob"} or not rel:
            log_event(
                _HOOK_NAME,
                event=_EVENT,
                decision="error_internal",
                reason=f"unknown match type {match_type!r} for path {rel!r}",
            )
            continue
        # Join ~/.claude/ prefix with the relative path. Both sides are
        # already canonical POSIX, so no resolve() is required.
        normalized = _CLAUDE_HOME_POSIX + "/" + rel.lstrip("/")
        out.append(Pattern(raw=rel, normalized=normalized, match_type=match_type))
    return out


def _match_always_block(
    abs_path: str, entries: list[Pattern]
) -> Optional[Pattern]:
    """Return the first matching always-block Pattern, else None.

    Always-block applies only inside ``~/.claude/`` (Section 2 / 6.4).
    """
    if not (
        abs_path == _CLAUDE_HOME_POSIX
        or abs_path.startswith(_CLAUDE_HOME_POSIX + "/")
    ):
        return None
    for entry in entries:
        if _matches(abs_path, entry):
            return entry
    return None


def _load_handoff_scope(cwd: Path) -> Optional[list[Pattern]]:
    """Parse the first ``` ```scope ``` block in HANDOFF.md and return
    its entries as normalised Pattern objects. Returns None when the
    file is missing, the block is absent, or the parsed block has no
    entries (fail-open semantics in the caller).
    """
    if not _HANDOFF_PATH.is_file():
        log_event(
            _HOOK_NAME,
            event=_EVENT,
            decision="error_internal",
            reason="HANDOFF.md not found",
        )
        return None
    try:
        # utf-8-sig tolerates a stray BOM (Open Question #4).
        text = _HANDOFF_PATH.read_text(encoding="utf-8-sig")
    except Exception as exc:
        log_event(
            _HOOK_NAME,
            event=_EVENT,
            decision="error_internal",
            reason=f"HANDOFF.md read failed: {type(exc).__name__}: {exc}",
        )
        return None

    m = _SCOPE_BLOCK_RE.search(text)
    if m is None:
        return None
    body = m.group(1)

    patterns: list[Pattern] = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(
            Pattern(
                raw=line,
                normalized=_normalize_path(line, cwd),
                match_type=_classify_pattern(line),
            )
        )
    return patterns if patterns else None


def main() -> None:
    payload = read_hook_input()

    mode_raw = get_env_override("CLAUDE_SCOPE_WHITELIST_MODE", "dryrun")
    mode = mode_raw if mode_raw in {"off", "dryrun", "enforce"} else "dryrun"

    if mode == "off":
        log_event(
            _HOOK_NAME,
            event=_EVENT,
            decision="allow",
            reason="mode=off",
        )
        exit_allow()

    tool_name = payload.get("tool_name")
    if tool_name not in _TARGET_TOOLS:
        # Out-of-scope tool — silent allow keeps log traffic down.
        exit_allow()

    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path", "") or ""
    if not file_path:
        # Empty path is Claude Code's responsibility.
        exit_allow()

    cwd = get_cwd(payload)
    abs_path = _normalize_path(file_path, cwd)

    always_entries = _load_always_block()
    hit = _match_always_block(abs_path, always_entries)
    if hit is not None:
        log_event(
            _HOOK_NAME,
            event=_EVENT,
            decision="block",
            reason=f"always_block:{hit.raw}",
            tool_name=tool_name,
            file_path=abs_path,
            match_pattern=hit.raw,
            match_type=hit.match_type,
            mode=mode,
        )
        exit_block(
            f"[scope_check:block] always-block: {abs_path} matched {hit.raw}"
        )

    scope_patterns = _load_handoff_scope(cwd)
    if not scope_patterns:
        # fail-open: codeblock absent / empty means this cycle opts out.
        exit_allow()

    for p in scope_patterns:
        if _matches(abs_path, p):
            exit_allow()

    fields = {
        "event": _EVENT,
        "tool_name": tool_name,
        "file_path": abs_path,
        "mode": mode,
    }

    if mode == "enforce":
        log_event(
            _HOOK_NAME,
            decision="block",
            reason="out_of_scope",
            **fields,
        )
        exit_block(f"[scope_check:block] {abs_path} not in HANDOFF.md scope")
    else:
        # dryrun (default) and any unknown mode value collapsed to dryrun.
        log_event(
            _HOOK_NAME,
            decision="warn",
            reason="out_of_scope (dryrun)",
            **fields,
        )
        exit_warn(f"[scope_check:warn:dryrun] {abs_path} not in HANDOFF.md scope")


if __name__ == "__main__":
    run_handler(main, hook_name=_HOOK_NAME)
