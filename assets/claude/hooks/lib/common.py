"""Common utilities for Claude Code hooks (ADR-0001 infrastructure).

Standard-library only. Handler bugs must not block user work, so any
unexpected exception in a hook should ultimately fall through to
``sys.exit(0)`` (safe-pass). Helpers here favour that contract.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, NoReturn

# Logs live alongside this package: ~/.claude/hooks/logs/
_LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"


def _now_iso_z() -> str:
    now = datetime.now(timezone.utc)
    return now.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def read_hook_input() -> dict:
    """Read a single JSON object from stdin.

    On parse failure: log ``error_input`` and ``sys.exit(0)`` — a
    malformed payload must never block the user.
    """
    try:
        raw = sys.stdin.read()
        return json.loads(raw)
    except Exception as exc:
        log_event(
            "common",
            event="PreToolUse",
            decision="error_input",
            reason=f"{type(exc).__name__}: {exc}",
        )
        sys.exit(0)


def get_cwd(payload: dict) -> Path:
    cwd = payload.get("cwd")
    return Path(cwd) if cwd else Path(os.getcwd())


def get_env_override(name: str, default: Any = None) -> Any:
    return os.environ.get(name, default)


# Codex 0.141 sends file edits as tool_name="apply_patch" with the patch body in
# tool_input.command (a "*** Begin Patch ... *** End Patch" envelope) instead of
# Claude's Edit/Write file_path+content shape (verified: CODEX-PREFLIGHT.md §3).
# File paths live on the "*** Add/Update/Delete File:" and "*** Move to:" marker
# lines; added content is the "+"-prefixed hunk lines.
_APPLY_PATCH_PATH_RE = re.compile(r"^\*\*\* (?:(?:Add|Update|Delete) File|Move to): (.+?)\s*$")


def parse_apply_patch(command: str) -> list[tuple[str, str]]:
    """Parse an apply_patch command body into ``[(path, added_text), ...]``.

    One entry per referenced path (``added_text`` is ``""`` for a delete or a
    rename-source marker). Best-effort: any non-marker, non-``+`` line is
    ignored, so malformed input degrades to fewer entries rather than raising
    (handlers fail-open regardless).
    """
    results: list[tuple[str, str]] = []
    cur_path: str | None = None
    added: list[str] = []

    def _flush() -> None:
        if cur_path is not None:
            results.append((cur_path, "\n".join(added)))

    for line in (command or "").splitlines():
        m = _APPLY_PATCH_PATH_RE.match(line)
        if m:
            _flush()
            cur_path = m.group(1).strip()
            added = []
        elif line.startswith("+"):
            added.append(line[1:])
    _flush()
    return results


def log_event(hook_name: str, **fields: Any) -> None:
    """Append one JSON line to ``~/.claude/hooks/logs/<hook_name>.log``.

    Injects ``timestamp`` (UTC ISO8601, ms precision, Z suffix) and
    ``hook_name``. Caller passes ``event``, ``decision``, ``reason``
    plus optional match metadata. Never propagates exceptions —
    logging failure must not break the handler.
    """
    try:
        _LOGS_DIR.mkdir(parents=True, exist_ok=True)
        record: dict[str, Any] = {
            "timestamp": _now_iso_z(),
            "hook_name": hook_name,
        }
        record.update(fields)
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        path = _LOGS_DIR / f"{hook_name}.log"
        with path.open("a", encoding="utf-8", newline="") as f:
            f.write(line)
    except Exception:
        pass


def exit_allow() -> NoReturn:
    sys.exit(0)


def exit_block(reason: str) -> NoReturn:
    sys.stderr.write(reason + "\n")
    sys.exit(2)


def exit_warn(reason: str) -> NoReturn:
    sys.stderr.write("[WARN] " + reason + "\n")
    sys.exit(0)


# ---------------------------------------------------------------------------
# Handler wrapper (HANDOFF Section B).
#
# Every handler entry point must be invoked via ``run_handler(main, hook_name=...)``.
# The wrapper guarantees:
#   * fail-open on any unhandled exception (Section B.3)
#   * 200ms timeout safety net (Section B.5)
#   * separate <name>.error.log file with full traceback (Section B.4)
#   * only ``sys.exit(2)`` from a real policy block reaches Claude Code
# ---------------------------------------------------------------------------

# 80% of the 250ms hook budget — leaves headroom for process teardown.
_HANDLER_TIMEOUT_SECONDS = 0.2


def _append_error_log(
    hook_name: str,
    exception_type: str,
    message: str,
    tb: str,
) -> None:
    """Append one JSON line to ``<hook_name>.error.log``. Never raises."""
    try:
        _LOGS_DIR.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": _now_iso_z(),
            "handler": hook_name,
            "exception_type": exception_type,
            "message": message,
            "traceback": tb,
        }
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        path = _LOGS_DIR / f"{hook_name}.error.log"
        with path.open("a", encoding="utf-8", newline="") as f:
            f.write(line)
    except Exception:
        pass


def _timeout_kill(hook_name: str) -> None:
    # Runs on the Timer thread once the safety budget is exhausted. We
    # record the event then hard-exit so Claude Code is never made to
    # wait on a runaway handler. ``os._exit`` skips atexit/finally on
    # purpose — by definition the main thread is no longer trustworthy.
    try:
        _append_error_log(
            hook_name,
            "TimeoutError",
            f"handler exceeded {int(_HANDLER_TIMEOUT_SECONDS * 1000)}ms safety margin",
            "",
        )
    finally:
        os._exit(0)


def run_handler(main_callable: Callable[[], None], *, hook_name: str) -> NoReturn:
    """Invoke ``main_callable`` under the standard hook safety contract.

    Exit code semantics (Section B.2):
      0 — allow (default for normal return, fail-open path, and any
          ``SystemExit`` whose code is not exactly 2)
      2 — block (only when ``main_callable`` raises ``SystemExit(2)``)

    Any other exception (including ``KeyboardInterrupt``) is logged to
    ``<hook_name>.error.log`` and converted to exit 0.
    """
    timer = threading.Timer(_HANDLER_TIMEOUT_SECONDS, _timeout_kill, args=(hook_name,))
    timer.daemon = True
    timer.start()
    try:
        main_callable()
    except SystemExit as exc:
        timer.cancel()
        code = exc.code if isinstance(exc.code, int) else 0
        sys.exit(2 if code == 2 else 0)
    except BaseException as exc:  # noqa: BLE001  (intentional fail-open catch-all)
        timer.cancel()
        tb = traceback.format_exc()
        _append_error_log(hook_name, type(exc).__name__, str(exc), tb)
        try:
            sys.stderr.write(
                f"[{hook_name}:internal_error] {type(exc).__name__}: {exc}\n"
            )
        except Exception:
            pass
        sys.exit(0)
    else:
        # main returned without calling exit_* — treat as allow.
        timer.cancel()
        sys.exit(0)
