"""Learning-capture PostToolUse hook (advisory, Tier B — gap #4 / ADR-0004).

After a Bash tool call, scans the command output for strong failure signals
(compile/link errors, build failures, tracebacks, missing files, etc.) and, on a
match, appends one JSON line to ``hooks/logs/learning_log.log`` via ``log_event``.
It NEVER blocks — always exits 0. The captured failures are later reviewed and
promoted into CLAUDE.md rules by the ``learnings-review`` skill.

Installed in ``hooks/handlers/``; launcher at ``hooks/launchers/learning_log.cmd``.
Registered under ``PostToolUse`` (matcher ``Bash|PowerShell``) in ``settings.json``
and ``settings.json.template``. (``parent.parent`` is ``hooks/``, so ``lib.common``
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
_TARGET_TOOL = "Bash"
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

    for key in ("tool_response", "tool_result", "result", "output"):
        if key in payload:
            collect(payload[key])
    text = "\n".join(parts)
    return text[-_MAX_SCAN:] if len(text) > _MAX_SCAN else text


def _match(text: str):
    for name, pat in _FAILURE_PATTERNS:
        m = pat.search(text)
        if m:
            return name, m
    return None, None


def _excerpt(text: str, m: "re.Match") -> str:
    start = text.rfind("\n", 0, m.start()) + 1
    end = text.find("\n", m.end())
    if end == -1:
        end = len(text)
    return text[start:end].strip()[:300]


def main() -> None:
    payload = read_hook_input()

    if payload.get("tool_name") != _TARGET_TOOL:
        exit_allow()

    text = _extract_text(payload)
    if not text:
        exit_allow()

    name, m = _match(text)
    if not name:
        exit_allow()  # success / no strong failure signal — capture nothing

    cmd = ""
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        cmd = str(tool_input.get("command", ""))[:200]

    log_event(
        _HOOK_NAME,
        event=_EVENT,
        decision="capture",
        signal=name,
        command=cmd,
        excerpt=_excerpt(text, m),
        cwd=str(get_cwd(payload)),
        session=str(payload.get("session_id") or "default"),
    )

    # Advisory only — never blocks.
    exit_allow()


if __name__ == "__main__":
    run_handler(main, hook_name=_HOOK_NAME)
