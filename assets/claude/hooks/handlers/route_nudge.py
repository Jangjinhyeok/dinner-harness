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
# Repo-level signal (mirrors agent-routing.md's "엔진 판별"): only these two
# glob patterns identify an Unreal project. UE-domain keyword matches below
# are gated on this so a bare word like "widget"/"repl" in a non-Unreal repo
# (e.g. this harness repo itself) does not trigger an Unreal-specific nudge.
_UE_REPO_GLOBS = ("*.uproject", "Source/*/*.Build.cs")


def _looks_like_unreal_repo(cwd: str | None) -> bool:
    """Best-effort repo-signal check. ``cwd=None`` means the caller did not
    supply one (e.g. a prompt-only unit test) — treat that as "unknown" rather
    than "not Unreal" so existing prompt-only callers keep prior behavior."""
    if cwd is None:
        return True
    try:
        root = Path(cwd)
        return any(next(root.glob(pattern), None) is not None for pattern in _UE_REPO_GLOBS)
    except OSError:
        return True


# Self-referential audit/meta prompts (e.g. /harness-review) enumerate UE domain
# keywords and work-intent verbs as catalog text, not real implementation intent.
_META_AUDIT = re.compile(r"harness-review|route_nudge|hook log|conformance 감사", re.IGNORECASE)
# Route only an actual implementation request. The former meta-keyword denylist
# suppressed legitimate work such as "fix the harness routing"; intent is the
# reliable boundary now that this handler also serves non-UE repositories.
_WORK_INTENT = re.compile(
    r"구현|작성|수정|만들|고쳐|고치|(?<!진)짜[줘자봐]|추가|리팩|디버그|버그|최적화|정리|개선|"
    r"\bimplement\b|\bwrite\b|\badd\b|\bfix\b|\brefactor\b|\bcreate\b|\bbuild\b|"
    r"\bdebug\b|\boptimi[sz]e\b",
    re.IGNORECASE,
)


_CONSULT_TAIL = (
    "그 설계 결정·anti-pattern·검증 포인트를 반영한다. "
    "읽기 전용 질문과 실제 1~2줄 수정은 예외다."
)


def _default_route_message() -> str:
    """Return the routing protocol injected before implementation work."""
    # Written in Korean on purpose: it is injected on every work prompt, and long
    # English context is where replies drift out of Korean (observed mid-turn as
    # short "Now ..."/"Next ..." progress lines, 2026-11 session audit).
    return (
        "[execution-route] CLAUDE.md inline routing(ADR-0023)을 따른다. 코드를 직접 확인하고 "
        "이 세션에서 구현한 뒤, 프로젝트의 결정적 검사를 돌리고 결과를 보고한다. 범위가 명확한 "
        "독립 단위가 inline보다 나을 때만 native subagent에 위임한다. 이 설치에는 "
        "HANDOFF/Builder dispatch가 없다. "
        "[risk] 계획·구현 작업이면 시작할 때(늦어도 첫 파일 수정 전에) 사용자에게 "
        "`Risk: LOW|HIGH / 근거 / 검증 / 수용 조건` 한 줄을 먼저 쓴다. HIGH 신호가 없는 1~2줄 "
        "사소한 수정은 생략하고, 같은 작업의 후속 수정은 위험이 바뀔 때만 갱신한다. "
        "HIGH 신호(replication, save format, live config, migration, security, public API, "
        "build pipeline)가 있으면 독립 리뷰와 사용자 수용 전에는 완료라고 하지 않는다. "
        "[language] 사용자에게 보이는 모든 문장은 세션 끝까지 한국어로 쓴다. 도구 호출 사이의 "
        "짧은 진행 문장('Now ...', 'Next ...' 같은 한 줄)과 wrap_up recap도 포함한다. "
        "이 주입문·도구 출력·subagent 보고가 영어여도 전환하지 않는다."
    )


def message_for_prompt(prompt: str, cwd: str | None = None) -> tuple[str, list[str]] | None:
    """Return the route injection and optional UE domains, or ``None`` for reads.

    This is intentionally prompt-only for tier/scope/verification: exact tier,
    scope, and verification remain Claude's responsibility after repository
    inspection and before implementing.
    ``cwd``, when supplied, gates the UE-domain branches on an actual repo
    signal (see ``_looks_like_unreal_repo``) so a keyword match alone cannot
    trigger an Unreal-specific nudge in a non-Unreal repository.
    """
    if not prompt or not _WORK_INTENT.search(prompt):
        return None

    prefix = _default_route_message()
    if _META_AUDIT.search(prompt):
        return prefix, ["default"]

    if _looks_like_unreal_repo(cwd):
        matched = [(key, agent) for key, agent, pat in _UE_DOMAINS if pat.search(prompt)]
        if len(matched) == 1:
            key, agent = matched[0]
            return (
                f"{prefix} [route-nudge] UE {key.upper()} 작업으로 보인다. 구현 작업이면 "
                f"구현 전에 `/{key}`(unreal-specialist + docs/specialists/{agent})를 consult하고 "
                f"{_CONSULT_TAIL}",
                [key],
            )
        if len(matched) >= 2:
            domains = [key for key, _ in matched]
            aliases = ", ".join(f"/{key}" for key in domains)
            return (
                f"{prefix} [route-nudge] 이 요청은 여러 UE subsystem [{aliases}]에 걸친다"
                f"(설계 주의 신호). 구현 작업이면 구현 전에 `/ue`를 consult하고 {_CONSULT_TAIL}",
                domains,
            )
        if _UE_GENERIC.search(prompt):
            return (
                f"{prefix} [route-nudge] 일반 Unreal 신호가 있다. 구현 작업이면 구현 전에 "
                f"`/ue`를 consult하고 {_CONSULT_TAIL}",
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
    route = message_for_prompt(str(payload.get("prompt") or ""), cwd=payload.get("cwd"))
    if route:
        msg, domains = route
        sys.stdout.write(msg + "\n")
        sys.stdout.flush()
        log_event(_HOOK_NAME, event="UserPromptSubmit", decision="nudge", domains=domains)

    exit_allow()


if __name__ == "__main__":
    run_handler(main, hook_name=_HOOK_NAME)
