"""Engine-routing nudge — UserPromptSubmit hook (advisory, never blocks).

On each user prompt, regex-scans for Unreal-domain signals and, on a match,
prints a one-line nudge to stdout (added to context) suggesting the matching
specialist agent. This makes the ``rules/agent-routing.md`` intent *deterministic*
at decision time, compensating for unreliable description auto-matching — but it
only NUDGES; Claude still decides whether to delegate (and should skip for
trivial one-line tasks per agent-routing.md).

Routing logic mirrors the "조건부 direct" discussion: exactly one leaf domain →
that leaf; two or more → the ``unreal-specialist`` hub (multi-subsystem triage);
generic UE signal only → the hub.

Installed in ``hooks/handlers/``; launcher at ``hooks/launchers/route_nudge.cmd``.
Registered under ``UserPromptSubmit`` in ``settings.json`` and ``settings.json.template``.
(``parent.parent`` is ``hooks/``, so ``lib.common`` resolves normally.)
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
    log_event,
    read_hook_input,
    run_handler,
)

_HOOK_NAME = "route_nudge"

# (key, reference doc under docs/specialists/, keyword pattern). key doubles as the slash alias (/umg …).
_UE_DOMAINS = [
    ("umg", "ue-umg.md",
     re.compile(r"\bUMG\b|\bUserWidget\b|\bCommonUI\b|\bSlate\b|\bwidget\b|위젯", re.IGNORECASE)),
    ("gas", "ue-gas.md",
     re.compile(r"\bGAS\b|GameplayAbility|GameplayEffect|AttributeSet|GameplayTag|\bability\b|어빌리티", re.IGNORECASE)),
    ("repl", "ue-replication.md",
     re.compile(r"replicat|\bRPC\b|DOREPLIFETIME|multiplayer|netcode|relevancy|복제", re.IGNORECASE)),
    ("bp", "ue-blueprint.md",
     re.compile(r"\bBlueprint\b|블루프린트|BlueprintNativeEvent|BlueprintCallable", re.IGNORECASE)),
]
# Generic UE signal with no specific leaf → route to the hub.
_UE_GENERIC = re.compile(
    r"\bUnreal\b|\bUE5\b|\.uasset\b|UPROPERTY|UFUNCTION|Niagara|\bcooking\b|\bpackaging\b",
    re.IGNORECASE,
)
# Intent gate (2026-06-16 conformance audit: 4/4 firings were false-positives on
# meta/harness prompts that merely *mentioned* specialist names). Nudge only on
# actual UE *work*, not discussion/audit/config-meta.
_META_GUARD = re.compile(
    r"\bharness\b|\baudit\b|감사|conformance|정합|route[_ ]?nudge|agent-routing|"
    r"\bsunset\b|일몰|\.claude|settings\.json|\bhooks?\b|specialist\s+(?:roster|목록)",
    re.IGNORECASE,
)
_WORK_INTENT = re.compile(
    r"구현|작성|수정|만들|고쳐|고치|짜|추가|리팩|디버그|버그|최적화|정리|개선|"
    r"\bimplement\b|\bwrite\b|\badd\b|\bfix\b|\brefactor\b|\bcreate\b|\bbuild\b|"
    r"\bdebug\b|\boptimi[sz]e\b",
    re.IGNORECASE,
)


def main() -> None:
    # Claude Code sends UTF-8 JSON on stdin; Windows' default is cp949, which would
    # mangle non-ASCII (e.g. Korean) keywords. Decode stdin as UTF-8 before
    # read_hook_input() consumes it. Silent no-op if the stream can't reconfigure.
    try:
        sys.stdin.reconfigure(encoding="utf-8")
    except Exception:
        pass
    # Windows console default is cp949; a non-ASCII char in the nudge (em-dash,
    # Korean) would crash on write. Force UTF-8 stdout too.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    payload = read_hook_input()
    prompt = str(payload.get("prompt") or "")
    if not prompt:
        exit_allow()
    # Skip meta/config-discussion prompts and prompts with no implementation
    # intent — they trip the domain regex without being real UE work.
    if _META_GUARD.search(prompt) or not _WORK_INTENT.search(prompt):
        exit_allow()
    matched = [(key, agent) for key, agent, pat in _UE_DOMAINS if pat.search(prompt)]

    msg = ""
    domains: list[str] = []
    if len(matched) == 1:
        key, agent = matched[0]
        domains = [key]
        msg = (
            f"[route-nudge] This looks like UE {key.upper()} work. Use `/{key}` "
            f"(unreal-specialist + docs/specialists/{agent}) for a focused pass - or if this "
            f"is heavy multi-file work, suggest `architect 모드` + Codex Builder dispatch "
            f"per CLAUDE.md 2. Skip if it's a trivial one-line change."
        )
    elif len(matched) >= 2:
        domains = [k for k, _ in matched]
        aliases = ", ".join(f"/{k}" for k, _ in matched)
        msg = (
            f"[route-nudge] This prompt spans multiple UE subsystems [{aliases}]. This is a "
            f"heavy-work signal - suggest `architect 모드` + Codex Builder dispatch per "
            f"CLAUDE.md 2, or `/ue` (hub reads docs/specialists/) if staying inline. "
            f"Skip if trivial."
        )
    elif _UE_GENERIC.search(prompt):
        domains = ["hub_generic"]
        msg = (
            "[route-nudge] This looks like substantial Unreal work. Per rules/agent-routing.md, "
            "consider the `unreal-specialist` hub (or `/ue`) as the entry point - skip if it's a "
            "small inline task."
        )

    if msg:
        sys.stdout.write(msg + "\n")
        sys.stdout.flush()
        log_event(_HOOK_NAME, event="UserPromptSubmit", decision="nudge", domains=domains)

    exit_allow()


if __name__ == "__main__":
    run_handler(main, hook_name=_HOOK_NAME)
