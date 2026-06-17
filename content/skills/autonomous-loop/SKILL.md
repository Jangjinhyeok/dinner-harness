---
name: autonomous-loop
description: "Risk-tiered self-correcting implementation loop. The human sets intent + success criteria at the START and accepts the outcome at the END; the agent owns the middle — implement, deterministic-verify, adversarial-review, self-correct — and repeats until criteria are met or it hits a hard BLOCK. Consults the risk tier to decide whether to auto-complete (LOW) or stop for a human sign-off (HIGH). Use for non-trivial work where you want autonomous inner-loop execution instead of per-step human approval."
argument-hint: "[task / goal]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash, Edit, Write, Task, AskUserQuestion
model: sonnet
origin: self
---

# Autonomous Loop — risk-tiered 자기수정 루프

사람은 **시작(intent·성공 기준)**과 **종단(결과 수용)** 두 경계에만 선다. 그 사이의 중간 판단(②)은 agent가 자율로 돈다 — implement → 검증 → adversarial-review → self-correct. tier 정의·게이트 강제는 `~/.claude/rules/autonomy-policy.md`가 단일 소스다.

> 약한 고리는 "판단을 LLM에 위임" 자체다. 그래서 중간 판단은 단일 self-review가 아니라 **`adversarial-review` jury**(judge 다양성)로 내리고, 고위험은 **HIGH tier 종단 게이트**로 사람을 다시 부른다.

## 언제 쓰나

- 비-trivial 작업에서 게이트마다 사람 승인을 받는 대신 inner-loop를 자율로 돌리고 싶을 때.
- Two-CLI Builder 세션이 게이트를 실행할 때(LOW 게이트 자동 진행, HIGH 게이트·종료는 서명 대기).
- trivial(한두 줄·단일 파일) 작업엔 과하다 — 그건 그냥 인라인으로 한다.

## 루프

### 1. START 게이트 (사람이 정한 intent 경계)
- `~/.claude/skills/goal-driven-execution/SKILL.md`로 작업을 **검증 가능한 성공 기준 + step별 검증 방법**으로 변환한다. 검증 방법 없는 step은 step이 아니다.
- `autonomy-policy.md`를 읽고 작업의 **risk tier(LOW/HIGH)를 분류·기록**한다(보수적 OR, 모호하면 HIGH).
- HIGH면 시작 시 **위험을 먼저 명시**한다(CLAUDE.md §5).

### 2. Implement
- `~/.claude/skills/surgical-changes/SKILL.md` 규율 하에 최소 변경. 요청 범위 밖 "겸사겸사" 수정 금지.
- Two-CLI라면 HANDOFF의 ` ```scope ` 화이트리스트를 준수한다(`scope_check` hook이 deterministic하게 강제).

### 3. Deterministic verify
- `~/.claude/skills/verification-loop/SKILL.md` 6-phase(build·type·lint·test·security·diff)를 돌린다.
- **deterministic 실패(빌드 깨짐 등)는 패널을 띄우기 전에 step 5로 short-circuit** — LLM 판단을 낭비하지 않는다.

### 4. Adversarial review (중간 판단 = agent jury)
- `~/.claude/skills/adversarial-review/SKILL.md`를 step 1의 tier와 함께 호출한다.
- 패널이 tier를 독립 재분류하므로, 여기서 **LOW→HIGH 승급**이 나오면 그 tier를 채택해 이후 종단 게이트에 반영한다.

### 5. Self-correct (bounded)
- verify 실패 또는 패널 FAIL이면 required changes를 반영하고 step 2~4를 반복한다.
- 반복은 `~/.claude/skills/eval-harness/SKILL.md`의 **pass@k 예산**으로 제한한다(기본 pass@3 권장).
- **예산 소진** 또는 **juror BLOCK** → **정지 → BLOCKED 상태로 사람에게 보고**한다. 강제 통과(force-pass) 금지 — 확신-오류 루프가 무한 self-correct로 가는 걸 막는 안전장치.

### 6. END 게이트 (tier 구동)
- **LOW + 전부 PASS → 자동 완료.** inner-loop 사람 승인 없이 종료하고 step 7로 보고만 한다. (이게 핵심 행동 전환이다.)
- **HIGH → 정지하고 사람 종단 서명을 받는다.** `AskUserQuestion`으로 **패널 verdict + diff 요약 + blast-radius 노트**를 제시하고, **서명 전까지 merge/apply/deploy 하지 않는다**.

### 7. 보고
- 최종 tier, self-correct 시도 횟수, 패널 verdict, 변경 파일을 보고한다. Two-CLI면 RESULT.md 형식(`ROLE_BUILDER` 참조)으로 남긴다.

## 재사용 맵

| 단계 | 재사용 |
|---|---|
| 1 START | `goal-driven-execution` + `autonomy-policy.md` |
| 2 implement | `surgical-changes` + `scope_check` hook |
| 3 verify | `verification-loop` (6-phase) |
| 4 review | `adversarial-review` (Task 패널) |
| 5 self-correct | `eval-harness` (pass@k 예산) |

## 주의

- **deterministic 안전망 상존**: tier·자율과 무관하게 `scope_check`·`secret_scan` hook은 항상 작동한다.
- **Codex degradation**: Codex엔 Task 패널이 없어 step 4가 inert가 된다. 그땐 step 3(deterministic verify)에 의존하고 **모든 비-trivial 결과를 사람이 검토**하며, HIGH는 매 게이트 명시 리뷰로 폴백한다(`assets/codex/AGENTS.md` §7). 그래서 이 skill은 codex에서 **degraded copy**로 설치된다(드롭 아님).
