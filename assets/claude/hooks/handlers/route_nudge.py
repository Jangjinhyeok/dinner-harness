"""Engine-routing nudge — UserPromptSubmit hook (advisory, never blocks).

On each user prompt, regex-scans for implementation intent. Every write intent
receives the default execution protocol; Unreal-domain signals add a focused
reference hint. The hook deliberately does not dispatch: it has no approved
HANDOFF, scope fence, or human HIGH-tier gate to give a Builder.

Routing logic mirrors the "조건부 direct" discussion: exactly one leaf domain →
that leaf; two or more → the ``unreal-specialist`` hub (multi-subsystem triage);
generic UE signal only → the hub.

Installed in ``hooks/handlers/``; launcher at ``hooks/launchers/route_nudge.cmd``.
Registered under ``UserPromptSubmit`` in ``settings.json`` and ``settings.json.template``.
(``parent.parent`` is ``hooks/``, so ``lib.common`` resolves normally.)
"""
from __future__ import annotations

import os
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
# Route only an actual implementation request. The former meta-keyword denylist
# suppressed legitimate work such as "fix the harness routing"; intent is the
# reliable boundary now that this handler also serves non-UE repositories.
_WORK_INTENT = re.compile(
    r"구현|작성|수정|만들|고쳐|고치|짜|추가|리팩|디버그|버그|최적화|정리|개선|"
    r"\bimplement\b|\bwrite\b|\badd\b|\bfix\b|\brefactor\b|\bcreate\b|\bbuild\b|"
    r"\bdebug\b|\boptimi[sz]e\b",
    re.IGNORECASE,
)


def _default_route_message() -> str:
    """Return the routing protocol injected before implementation work."""
    if os.environ.get("DINNER_EXECUTION_MODE") == "builder-first":
        return (
            "[execution-route] Apply CLAUDE.md strict Builder-first routing before source "
            "edits: keep read-only analysis in Claude, but every structured Edit/Write "
            "implementation-file write "
            "must go through Codex Builder. A clear single-purpose LOW change must run the "
            "delegate workflow now (write HANDOFF_DELEGATE.md, dispatch Codex Builder, then "
            "review RESULT.md plus the diff) without asking the user to type /delegate; "
            "multi-file, multi-gate, design, or HIGH-signal work must follow the architect "
            "workflow (draft HANDOFF, obtain the required human start approval, then dispatch "
            "Codex Builder). An explicit request for a small direct Claude edit cannot bypass "
            "a HIGH route. Do not treat ! as an override; it is Claude Code's shell-output "
            "fast path."
        )
    return (
        "[execution-route] Apply CLAUDE.md default-session routing before source edits: "
        "read-only work or a truly trivial one- or two-line single-file change may stay "
        "inline; a clear single-purpose LOW change must run the delegate workflow now "
        "(write HANDOFF_DELEGATE.md, dispatch Codex Builder, then review RESULT.md plus "
        "the diff) without asking the user to type /delegate; multi-file, multi-gate, "
        "design, or HIGH-signal work must follow the architect workflow (draft HANDOFF, "
        "obtain the required human start approval, then dispatch Codex Builder). An explicit "
        "request for a small direct Claude edit cannot bypass a HIGH route. Do not treat ! "
        "as an override; it is Claude Code's shell-output fast path."
    )


def message_for_prompt(prompt: str) -> tuple[str, list[str]] | None:
    """Return the route injection and optional UE domains, or ``None`` for reads.

    This is intentionally prompt-only: exact tier, scope, and verification
    remain Claude's responsibility after repository inspection and before a
    delegate or architect workflow writes its HANDOFF.
    """
    if not prompt or not _WORK_INTENT.search(prompt):
        return None

    matched = [(key, agent) for key, agent, pat in _UE_DOMAINS if pat.search(prompt)]
    prefix = _default_route_message()
    if len(matched) == 1:
        key, agent = matched[0]
        return (
            f"{prefix} [route-nudge] This also looks like UE {key.upper()} work. "
            f"Use `/{key}` (unreal-specialist + docs/specialists/{agent}) only for "
            "focused Architect analysis before the selected execution route.",
            [key],
        )
    if len(matched) >= 2:
        domains = [key for key, _ in matched]
        aliases = ", ".join(f"/{key}" for key in domains)
        return (
            f"{prefix} [route-nudge] This prompt spans multiple UE subsystems "
            f"[{aliases}], an additional architect-route signal. Use `/ue` only for "
            "focused Architect analysis before the HANDOFF.",
            domains,
        )
    if _UE_GENERIC.search(prompt):
        return (
            f"{prefix} [route-nudge] This also has a generic Unreal signal; use `/ue` "
            "only for focused Architect analysis when the selected route needs it.",
            ["hub_generic"],
        )
    return prefix, ["default"]


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
    route = message_for_prompt(str(payload.get("prompt") or ""))
    if route:
        msg, domains = route
        sys.stdout.write(msg + "\n")
        sys.stdout.flush()
        log_event(_HOOK_NAME, event="UserPromptSubmit", decision="nudge", domains=domains)

    exit_allow()


if __name__ == "__main__":
    run_handler(main, hook_name=_HOOK_NAME)
