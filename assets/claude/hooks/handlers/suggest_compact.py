"""Strategic-compact PreToolUse hook (advisory only).

Counts tool calls per session and writes a `/compact` suggestion to
stderr at a threshold, then periodically. This hook NEVER blocks — it
always exits 0. The suggestion is advisory; the user decides whether to
compact (see skills/strategic-compact/SKILL.md decision guide).

Staged here in the skill dir because hooks/handlers/ is always-block
(scope_check). Install via the off-ceremony documented in
hooks/README.md: move this file to hooks/handlers/suggest_compact.py.

Config (env): COMPACT_THRESHOLD (default 50) — tool calls before the
first suggestion; reminders fire every 25 calls thereafter.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make ``lib.common`` importable when launched via
# ``py -3 <hooks>/handlers/suggest_compact.py``. After install this file
# lives in hooks/handlers/, so parent is hooks/ — same as the other
# handlers. (While staged in the skill dir this insert is harmless.)
_HANDLER_DIR = Path(__file__).resolve().parent
_HOOKS_ROOT = _HANDLER_DIR.parent
if str(_HOOKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_HOOKS_ROOT))

from lib.common import (  # noqa: E402  (sys.path insert above)
    exit_allow,
    get_env_override,
    log_event,
    read_hook_input,
    run_handler,
)

_HOOK_NAME = "suggest_compact"
_EVENT = "PreToolUse"
_TARGET_TOOLS = {"Edit", "Write"}
_DEFAULT_THRESHOLD = 50
_REMINDER_INTERVAL = 25
# Counter state lives under hooks/logs/ (gitignored, writable).
_LOGS_DIR = _HOOKS_ROOT / "logs"


def _threshold() -> int:
    raw = get_env_override("COMPACT_THRESHOLD", _DEFAULT_THRESHOLD)
    try:
        value = int(raw)
        return value if value > 0 else _DEFAULT_THRESHOLD
    except (TypeError, ValueError):
        return _DEFAULT_THRESHOLD


def _counter_path(session_id: str) -> Path:
    # Keep the filename filesystem-safe regardless of session_id shape.
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in session_id)
    return _LOGS_DIR / f".compact_count_{safe}.txt"


def _bump_counter(session_id: str) -> int:
    """Increment and return the per-session tool-call count. Fail-soft:
    any IO error returns 0 (no suggestion, never blocks)."""
    try:
        _LOGS_DIR.mkdir(parents=True, exist_ok=True)
        path = _counter_path(session_id)
        count = 0
        if path.exists():
            try:
                count = int(path.read_text(encoding="utf-8").strip() or "0")
            except (ValueError, OSError):
                count = 0
        count += 1
        path.write_text(str(count), encoding="utf-8")
        return count
    except OSError:
        return 0


def main() -> None:
    payload = read_hook_input()

    if payload.get("tool_name") not in _TARGET_TOOLS:
        exit_allow()

    session_id = str(
        payload.get("session_id")
        or get_env_override("CLAUDE_SESSION_ID", "")
        or "default"
    )
    threshold = _threshold()
    count = _bump_counter(session_id)

    suggest = False
    reason = ""
    if count == threshold:
        suggest = True
        reason = (
            f"{threshold} tool calls reached - consider /compact if "
            f"transitioning phases"
        )
    elif count > threshold and (count % _REMINDER_INTERVAL) == 0:
        suggest = True
        reason = (
            f"{count} tool calls - good checkpoint for /compact if context "
            f"is stale"
        )

    if suggest:
        log_event(_HOOK_NAME, event=_EVENT, decision="suggest", count=count)
        sys.stderr.write(f"[StrategicCompact] {reason}\n")

    # Advisory only — always allow.
    exit_allow()


if __name__ == "__main__":
    run_handler(main, hook_name=_HOOK_NAME)
