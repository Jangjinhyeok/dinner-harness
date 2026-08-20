"""Common utilities for Claude Code hooks (ADR-0001 infrastructure).

Standard-library only. Handler bugs must not block user work, so any
unexpected exception in a hook should ultimately fall through to
``sys.exit(0)`` (safe-pass). Helpers here favour that contract.

That contract is the INTERACTIVE one, and it inverts under the controller-side
net (``CLAUDE_HOOK_FAILS_CLOSED``), which is the only automatic defense against
a Builder whose own hooks cannot veto the edit: there, exit 0 is recorded as a
clean pass with no reason at all, so "I could not vet this" must not spell
itself the same way as
"I vetted this and it was clean". Use :func:`exit_no_verdict` for the former —
:func:`exit_allow` means the check ran.
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

    On parse failure: log ``error_input``, then allow interactively and block
    under the net (:func:`exit_no_verdict`). A malformed payload must never
    block the user; but a payload the net could not even parse is a change no
    handler read, and the net has nobody else to fall back on.
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
        exit_no_verdict("common", "hook payload could not be read or parsed")


def get_cwd(payload: dict) -> Path:
    cwd = payload.get("cwd")
    return Path(cwd) if cwd else Path(os.getcwd())


def get_env_override(name: str, default: Any = None) -> Any:
    return os.environ.get(name, default)


# Codex 0.148.0 sends file edits as tool_name="apply_patch" with the patch body in
# (re-verified 2026-08-20 against codex-cli 0.148.0 — see CODEX-COVERAGE.md §6.4)
# tool_input.command (a "*** Begin Patch ... *** End Patch" envelope) instead of
# Claude's Edit/Write file_path+content shape (verified: CODEX-COVERAGE.md §6.2).
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
#
# That budget belongs to an INTERACTIVE Claude hook, where a slow handler would
# stall the user's keystroke and answering "allow" is the right trade. The
# controller-side net is a different caller with a different bargain: it is the
# only automatic defense against a headless Codex Builder, it hands the handler
# whole file contents rather than one edit, and it already gives the subprocess
# 30 seconds. Under the interactive budget a large enough payload could not be
# read and parsed in time, so the watchdog answered "allow" — measured, an AWS
# key that blocks at 1 KiB shipped at 48 MiB, for scope_check and secret_scan
# alike, with no warning anywhere. Both knobs are set by safety.scan; unset,
# every interactive session behaves exactly as before.
_HANDLER_TIMEOUT_SECONDS = 0.2
try:
    _budget_ms = float(os.environ.get("CLAUDE_HOOK_TIMEOUT_MS", "") or 0)
    if _budget_ms > 0:
        _HANDLER_TIMEOUT_SECONDS = _budget_ms / 1000.0
except (TypeError, ValueError):
    pass  # garbled override -> keep the interactive default

# Does "the handler did not reach a verdict" mean allow or block? 0 == allow is
# the interactive default (never freeze the user over a slow or buggy handler).
# The net sets this, because there a non-verdict is recorded as a clean pass
# with no reason at all — indistinguishable from an approval nobody gave.
# Covers both non-verdict shapes: the watchdog firing, and an unhandled crash.
_FAILS_CLOSED = os.environ.get("CLAUDE_HOOK_FAILS_CLOSED") == "1"
_TIMEOUT_EXIT_CODE = 2 if _FAILS_CLOSED else 0


def exit_no_verdict(hook_name: str, reason: str) -> NoReturn:
    """The handler could not vet this change: allow interactively, block under the net.

    ``run_handler``'s two fail-closed paths cover the handler DYING — the
    watchdog firing, an unhandled crash. This covers the third shape, which
    neither reaches: a handler that runs to completion and chooses to allow
    because it has nothing to judge with. ``secret_scan`` whose ruleset will not
    load is the live case — it caught the error, logged it, and called
    ``exit_allow()``, so the net recorded exit 0 as a clean pass with an empty
    reason list and a run carrying an AWS key reported BUILT.

    Interactively the old answer is still the right one: a handler that cannot
    load its own ruleset must not stop the user editing their own files. Under
    ``CLAUDE_HOOK_FAILS_CLOSED`` (set by ``safety.scan`` and nowhere else) the
    same condition blocks, because there nobody else is looking.

    Logging stays with the caller — the existing sites already log their own
    decision, and a second record here would double-count them.
    """
    if _FAILS_CLOSED:
        try:
            sys.stderr.write(
                f"[{hook_name}:block] {reason} — cannot vet this change, failing closed\n"
            )
            sys.stderr.flush()
        except Exception:
            pass
        sys.exit(2)
    sys.exit(0)


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
            f"handler exceeded {int(_HANDLER_TIMEOUT_SECONDS * 1000)}ms safety margin"
            + (" (failing closed)" if _TIMEOUT_EXIT_CODE == 2 else ""),
            "",
        )
        if _TIMEOUT_EXIT_CODE == 2:
            # The caller reads stderr for the reason; the error log alone is not
            # on the path that reaches the operator.
            try:
                sys.stderr.write(
                    f"[{hook_name}:block] handler exceeded its "
                    f"{int(_HANDLER_TIMEOUT_SECONDS * 1000)}ms budget — "
                    "cannot vet this change, failing closed\n"
                )
                sys.stderr.flush()
            except Exception:
                pass
    finally:
        os._exit(_TIMEOUT_EXIT_CODE)


def run_handler(main_callable: Callable[[], None], *, hook_name: str) -> NoReturn:
    """Invoke ``main_callable`` under the standard hook safety contract.

    Exit code semantics (Section B.2):
      0 — allow (default for normal return, fail-open path, and any
          ``SystemExit`` whose code is not exactly 2)
      2 — block (only when ``main_callable`` raises ``SystemExit(2)``)

    Any other exception (including ``KeyboardInterrupt``) is logged to
    ``<hook_name>.error.log`` and converted to exit 0 — unless the caller asked
    to fail closed, in which case a handler that crashed is a handler that did
    not vet the change, and that is not an approval.
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
        # An interactive session fails OPEN here on purpose: a handler bug must
        # not stop the user from editing their own files. The controller-side
        # net has the opposite duty — it is the only thing vetting a Builder
        # whose own hooks cannot veto the edit, and exit 0 there is recorded as a
        # clean pass with
        # NO reason at all, so a crash reads as approval.
        crashed_closed = _FAILS_CLOSED
        label = "block" if crashed_closed else "internal_error"
        try:
            sys.stderr.write(
                f"[{hook_name}:{label}] {type(exc).__name__}: {exc}"
                + (" — cannot vet this change, failing closed\n" if crashed_closed else "\n")
            )
        except Exception:
            pass
        sys.exit(2 if crashed_closed else 0)
    else:
        # main returned without calling exit_* — treat as allow.
        timer.cancel()
        sys.exit(0)
