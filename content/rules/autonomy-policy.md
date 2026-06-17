# Autonomy Policy (Risk-Tiered Gating)

이 규칙은 항상 주입된다. **중간 판단(inner-loop)을 사람이 게이트하느냐 agent가 게이트하느냐**를 정하는 단일 소스다. CLAUDE.md(§1.4·§5·§6)·roles(`ROLE_ARCHITECT`·`ROLE_BUILDER`)·`agent-routing.md`·`autonomous-loop`·`adversarial-review` skill이 전부 이 파일을 **경로로 참조**한다 — tier 정의를 다른 곳에서 재정의하지 않는다.

## 핵심 모델

작업의 판단은 세 군데서 일어난다 — **①진입(intent·성공 기준), ②중간(각 step·gate 통과 판정), ③종단(결과 수용)**. 이 하네스의 기본 자세:

- **②중간 판단은 agent에게 위임한다.** implement → 검증 → adversarial-review → self-correct 루프를 agent가 자율로 돈다.
- **사람은 ①진입과 ③종단 두 경계에만 선다.** 무엇을 할지·성공 기준을 정하고(시작), 결과를 수용/반려한다(종료).

단, **위험 등급(risk tier)에 따라 ③종단 게이트의 강제 여부가 갈린다.** 약한 고리는 "판단을 LLM에 위임" 자체이므로(조용히 틀림), 완화는 **judge 다양성**(→ `adversarial-review`)과 **이 tiering** 두 축으로 한다. deterministic 안전망(`scope_check`·`secret_scan` hook)은 tier 무관하게 항상 작동한다.

## 위험 등급

작업/게이트를 시작할 때 분류하고 기록한다.

### HIGH — blast-radius 큼 / 비가역 (사람 종단 서명 + jury 필수)

라이브 게임 서비스에서 잘못되면 player를 brick하거나 되돌리기 어려운 영역:

- **network replication / RPC / net serialization / relevancy / bandwidth**
- **save·serialization format / 영속 데이터 back-compat**
- **live config · feature flag · remote toggle** (런타임에 라이브로 나가는 값)
- **data migration · schema 변경 · 영속 스토어 마이그레이션**
- **security-sensitive** — auth, permission, crypto, trust boundary, anti-cheat
- **광범위·비가역** — public API/ABI, build·packaging 파이프라인, one-way migration

→ `adversarial-review` jury **필수**(우회 불가), 그리고 **사람 종단 서명 전까지 merge/apply/deploy 금지**. 게이트 자동 진행 안 함.

### LOW — blast-radius 작음 / 되돌리기 쉬움 (완전 자율 — inner-loop 사람 게이트 없음)

- 단일 시스템 **내부 로직 · 순수 함수 · 로컬 상태**
- **테스트** 코드
- **주석 · 문서 · 로깅**
- **비-렌더 UI 텍스트/레이아웃 · 에디터 전용 도구**
- **명백히 하위 호환인 추가**(새 optional 경로, 기존 caller 불변)

→ agent가 implement → 검증 → self-correct를 자율로 돌고(비-trivial이면 `adversarial-review` 포함, trivial이면 직접 self-review), PASS면 inner-loop 사람 승인 없이 진행, **종료 시 결과만 보고**한다.

## 판정 규칙

- **보수적 OR**: HIGH 신호를 *하나라도* 건드리면 작업 전체가 HIGH다.
- **모호하면 HIGH로 승급한다** — `surgical-changes`의 "확실하지 않으면 보수적으로"와 정합. 저평가(under-classify)가 과평가보다 위험하다.
- **tier label을 맹신하지 않는다**: `adversarial-review`는 caller가 넘긴 tier를 신뢰하지 말고 diff를 보고 **독립적으로 재분류**한다(저평가 교정의 마지막 방벽).
- 분류 결과는 작업/게이트마다 **기록**한다(Two-CLI에선 HANDOFF 게이트 태그·RESULT 보고에 명시).

## tier가 루프를 바꾸는 방식

| | LOW | HIGH |
|---|---|---|
| inner-loop 사람 게이트 | 없음 (자율 진행) | 없음 (자율 진행) — 단 jury 필수, 패널 FAIL/BLOCK 시 정지, 종단은 사람 서명 대기 |
| `adversarial-review` jury | 비-trivial 시 권장 | **필수·우회 불가** (만장일치 요구) |
| 종단 사람 서명 | 불필요 (결과 보고만) | **필수** — 서명 전 merge/apply/deploy 금지 |
| deterministic hook (`scope_check`·`secret_scan`) | 항상 작동 | 항상 작동 |

상세 절차는 `~/.claude/skills/autonomous-loop/SKILL.md`(루프)와 `~/.claude/skills/adversarial-review/SKILL.md`(jury) 참조.
