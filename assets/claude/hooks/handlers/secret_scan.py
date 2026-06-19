"""ADR-0001 secret-scan PreToolUse hook.

Reads a Claude Code hook payload from stdin, scans Edit / Write / Bash
inputs against a small regex ruleset and emits allow / warn / block
based on ``CLAUDE_SECRET_SCAN_MODE``.

Default mode is ``dryrun`` — production rollout must never start in
enforce. Promotion to enforce is an explicit, separate step (Gate 4 in
HANDOFF).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import NamedTuple, Optional

# Make ``lib.common`` importable when this script is launched directly
# via ``py -3 <path>/handlers/secret_scan.py`` (settings.json hook
# command). Without this insert, sys.path[0] is ``handlers/`` and the
# ``lib`` sibling package is invisible.
_HANDLER_DIR = Path(__file__).resolve().parent
_HOOKS_ROOT = _HANDLER_DIR.parent
if str(_HOOKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_HOOKS_ROOT))

from lib.common import (  # noqa: E402  (sys.path insert above)
    exit_allow,
    exit_block,
    exit_warn,
    get_env_override,
    log_event,
    parse_apply_patch,
    read_hook_input,
    run_handler,
)


_HOOK_NAME = "secret_scan"
_EVENT = "PreToolUse"
_RULES_PATH = _HOOKS_ROOT / "rules" / "secret_patterns.json"
# "apply_patch" is Codex 0.141's file-edit tool (CODEX-PREFLIGHT.md §3); Claude
# never emits it, so listing it here is inert on Claude and active on Codex.
_TARGET_TOOLS = {"Edit", "Write", "Bash", "apply_patch"}


class Match(NamedTuple):
    pattern_name: str
    severity: str
    location: str  # file_path, "<content>", or "<command>"
    offset: int
    kind: str      # "content" | "path"


def _load_patterns() -> Optional[dict]:
    try:
        with _RULES_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        log_event(
            _HOOK_NAME,
            event=_EVENT,
            decision="error_internal",
            reason=f"ruleset load failed: {type(exc).__name__}: {exc}",
        )
        return None


def _scan_against(
    text: str,
    patterns: list,
    kind: str,
    location: str,
) -> Optional[Match]:
    if not text:
        return None
    for p in patterns:
        try:
            m = re.search(p["regex"], text)
        except re.error:
            continue
        if m:
            return Match(
                pattern_name=p["name"],
                severity=p.get("severity", "unknown"),
                location=location,
                offset=m.start(),
                kind=kind,
            )
    return None


def _scan(tool_name: str, tool_input: dict, patterns: dict) -> Optional[Match]:
    content_rules = patterns.get("content_patterns", [])
    path_rules = patterns.get("path_patterns", [])

    if tool_name == "Edit":
        file_path = tool_input.get("file_path", "") or ""
        new_string = tool_input.get("new_string", "") or ""
        m = _scan_against(file_path, path_rules, "path", file_path or "<file_path>")
        if m:
            return m
        return _scan_against(new_string, content_rules, "content", file_path or "<content>")

    if tool_name == "Write":
        file_path = tool_input.get("file_path", "") or ""
        content = tool_input.get("content", "") or ""
        m = _scan_against(file_path, path_rules, "path", file_path or "<file_path>")
        if m:
            return m
        return _scan_against(content, content_rules, "content", file_path or "<content>")

    if tool_name == "Bash":
        command = tool_input.get("command", "") or ""
        # Per HANDOFF Section 7.4: v1 policy applies path_patterns regex
        # to the entire command string (naive substring). No shell
        # tokenisation, no heredoc / pipe / redirection decomposition.
        m = _scan_against(command, path_rules, "path", "<command>")
        if m:
            return m
        return _scan_against(command, content_rules, "content", "<command>")

    if tool_name == "apply_patch":
        # Codex patch envelope: scan each referenced path (path_rules) and its
        # added "+" content (content_rules). First match wins.
        command = tool_input.get("command", "") or ""
        for path, added in parse_apply_patch(command):
            m = _scan_against(path, path_rules, "path", path or "<apply_patch path>")
            if m:
                return m
            m = _scan_against(added, content_rules, "content", path or "<apply_patch content>")
            if m:
                return m
        return None

    return None


def main() -> None:
    payload = read_hook_input()

    mode = get_env_override("CLAUDE_SECRET_SCAN_MODE", "dryrun")

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

    patterns = _load_patterns()
    if patterns is None:
        # error_internal already logged; safe-pass.
        exit_allow()

    tool_input = payload.get("tool_input") or {}
    match = _scan(tool_name, tool_input, patterns)
    if match is None:
        # No match — silent allow (HANDOFF Section 7.2 step 7).
        exit_allow()

    fields = {
        "event": _EVENT,
        "tool_name": tool_name,
        "match_pattern_name": match.pattern_name,
        "match_path": match.location,
        "match_offset": match.offset,
    }

    if mode == "enforce":
        log_event(
            _HOOK_NAME,
            decision="block",
            reason=f"{match.pattern_name} match in {match.kind}",
            **fields,
        )
        exit_block(f"[secret_scan:block] {match.pattern_name} in {match.location}")
    else:
        # dryrun (default) and any unknown mode value.
        log_event(
            _HOOK_NAME,
            decision="warn",
            reason=f"{match.pattern_name} match in {match.kind} (dryrun)",
            **fields,
        )
        exit_warn(f"[secret_scan:warn:dryrun] {match.pattern_name} in {match.location}")


if __name__ == "__main__":
    run_handler(main, hook_name=_HOOK_NAME)
