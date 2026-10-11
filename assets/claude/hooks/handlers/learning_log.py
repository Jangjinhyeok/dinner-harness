"""Learning-capture PostToolUse hook (advisory, Tier B — gap #4 / ADR-0004).

After a Bash or PowerShell tool call, scans the command output for strong failure signals
(compile/link errors, build failures, tracebacks, missing files, etc.) and, on a
match, appends one JSON line to ``hooks/logs/learning_log.log`` via ``log_event``
(signal plus an optional ``diag`` class/code; failure text quoted from logs or
transcripts is not a capture).
It NEVER blocks — always exits 0. The captured failures are later reviewed and
promoted into CLAUDE.md rules by the ``learnings-review`` skill.

Installed in ``hooks/handlers/``; launcher at ``hooks/launchers/learning_log.cmd``.
Registered under ``PostToolUse`` and ``PostToolUseFailure`` (matcher ``Bash|PowerShell``)
in ``settings.json`` and ``settings.json.template``: a command that exits non-zero fires
only the failure event, so without it most real failures were never seen. (``parent.parent`` is ``hooks/``, so ``lib.common``
resolves normally.)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_HANDLER_DIR = Path(__file__).resolve().parent
_HOOKS_ROOT = _HANDLER_DIR.parent
if str(_HOOKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_HOOKS_ROOT))

from lib.common import (  # noqa: E402  (sys.path insert above)
    exit_allow,
    get_cwd,
    log_event,
    read_hook_input,
    run_handler,
)

_HOOK_NAME = "learning_log"
_EVENT = "PostToolUse"
_TARGET_TOOLS = {"Bash", "PowerShell"}
_MAX_SCAN = 40000  # cap response text scanned — stay within the 200ms budget

# Strong, specific failure signals only — keep the log low-noise. The
# learnings-review skill clusters; the human extracts. Order = priority.
_FAILURE_PATTERNS = [
    ("msvc_compile", re.compile(r"error C\d{4}")),
    ("msvc_link", re.compile(r"\bLNK\d{4}\b")),
    ("csharp", re.compile(r"\berror CS\d{4}\b")),
    ("typescript", re.compile(r"\berror TS\d+\b")),
    ("gcc_clang", re.compile(r": (?:fatal )?error:")),
    ("undefined_ref", re.compile(r"undefined reference to")),
    ("build_failed", re.compile(r"\bbuild failed\b", re.IGNORECASE)),
    ("python_trace", re.compile(r"Traceback \(most recent call last\):")),
    ("npm_err", re.compile(r"npm ERR!")),
]


def _extract_text(payload: dict) -> str:
    """Defensively gather all string fields from the tool response (schema
    varies by Claude Code version). Returns the tail, capped to _MAX_SCAN."""
    parts: list[str] = []

    def collect(v: object) -> None:
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, dict):
            for x in v.values():
                collect(x)
        elif isinstance(v, list):
            for x in v:
                collect(x)

    # PostToolUseFailure (non-zero exit) carries the command output in ``error``.
    for key in ("tool_response", "tool_result", "result", "output", "error"):
        if key in payload:
            collect(payload[key])
    text = "\n".join(parts)
    return text[-_MAX_SCAN:] if len(text) > _MAX_SCAN else text


def _match(text: str):
    for name, pat in _FAILURE_PATTERNS:
        for m in pat.finditer(text):
            if not _in_log_record(text, m.start()):
                return name, m
    return None, None


# Reading hook logs or transcripts echoes old failure text that is not a failure
# of this command; those re-captures were most of the noise in learnings-review.
_LOG_READ_COMMAND = re.compile(r"hooks[/\\]+logs|learning_log|\.jsonl\b", re.IGNORECASE)
# A JSON log/transcript record line ({"timestamp": ...}) quotes failures, it is not one.
_LOG_RECORD_LINE = re.compile(r'^\s*\{.*"timestamp"\s*:')
# Classification only: an exception class name or a fixed-format error code,
# never message text (log_event drops free-form fields for the same reason).
_EXC_LINE = re.compile(r"^([A-Za-z_][\w.]{0,80}(?:Error|Exception|Exit|Interrupt))(?::|\s*$)", re.M)
_ERROR_CODE = re.compile(r"\b(?:C|CS|TS)\d{4}\b|\bLNK\d{4}\b")


def _in_log_record(text: str, pos: int) -> bool:
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    return bool(_LOG_RECORD_LINE.match(text[start:end if end != -1 else len(text)]))


def _diagnostic(name: str, m: re.Match, text: str) -> str | None:
    if name == "python_trace":
        found = _EXC_LINE.findall(text, m.end())
        return found[-1] if found else None
    code = _ERROR_CODE.search(m.group(0))
    return code.group(0) if code else None


def main() -> None:
    payload = read_hook_input()

    if payload.get("tool_name") not in _TARGET_TOOLS:
        exit_allow()

    command = str((payload.get("tool_input") or {}).get("command") or "")
    if _LOG_READ_COMMAND.search(command):
        exit_allow()

    text = _extract_text(payload)
    if not text:
        exit_allow()

    name, m = _match(text)
    if not name:
        exit_allow()  # success / no strong failure signal — capture nothing

    fields = {}
    diag = _diagnostic(name, m, text)
    if diag:
        fields["diag"] = diag
    log_event(
        _HOOK_NAME,
        event=str(payload.get("hook_event_name") or _EVENT),
        decision="capture",
        signal=name,
        cwd=str(get_cwd(payload)),
        session=str(payload.get("session_id") or "default"),
        **fields,
    )

    # Advisory only — never blocks.
    exit_allow()


if __name__ == "__main__":
    run_handler(main, hook_name=_HOOK_NAME)
