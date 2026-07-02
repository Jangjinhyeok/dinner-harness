---
name: adversarial-review
description: "Default-to-reject multi-judge review panel. Spawns several orthogonal judge agents (code-reviewer / architect / tdd-guide, plus a domain juror for HIGH-tier changes), each charged to REFUTE rather than rubber-stamp, then aggregates a PASS/FAIL verdict gated by the risk tier (LOW: majority approve; HIGH: unanimous). Replaces a single self-review for non-trivial or HIGH-risk changes. Use when an autonomous loop needs an intermediate-judgment gate, or whenever you would otherwise self-approve a non-trivial change."
argument-hint: "[path(s) or change description] [risk-tier: LOW|HIGH]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash, Task, AskUserQuestion
model: sonnet
origin: self
---

# Adversarial Review — judge-다양성 패널

단일 self-review는 자기 작업을 영합적으로 통과시키기 쉽다. 이 skill은 **직교 축의 여러 judge agent**를 **"기본 판정 = REJECT"** 헌장으로 띄워, 중간 판단(②)을 사람 대신 agent jury가 내리게 한다. tier 정의·강제 여부는 `~/.claude/rules/autonomy-policy.md`가 단일 소스다.

> 이 skill은 **판정만** 한다 — 파일을 쓰지 않는다(read-only). 수정은 호출자(`autonomous-loop` 또는 작업 세션)가 verdict를 받아 수행한다.

## 언제 쓰나

- `autonomous-loop`의 검증 단계(중간 게이트).
- 비-trivial 변경을 self-approve하려는 순간(CLAUDE.md §6이 여기로 보낸다).
- **HIGH-tier 변경에는 필수·우회 불가**(`autonomy-policy.md`).

## 패널 구성 (judge 다양성)

기존 `_core` agent를 **서로 다른 축**에 배치한다 — 같은 맹점을 공유하지 않도록 각자 **자기 축 체크리스트만** 받는다(opinion collapse 방지).

| juror | 축 | 본다 |
|---|---|---|
| `code-reviewer` | 품질 + security | 버그·취약점·에러 처리·자원 누수·입력 검증 |
| `architect` | 설계 + **blast-radius** | 경계·결합도·되돌릴 수 있나·라이브 영향 범위 |
| `tdd-guide` | testability + 검증 | 테스트 seam·관측 가능성·회귀 위험·커버리지 |
| 도메인 juror | 해당 도메인 | HIGH + 파일이 매치할 때만 추가 (netcode → `network-programmer`, 엔진 도메인 → `unreal-specialist`/`unity-specialist` 허브 등) |

## 절차

1. **Intake.** 대상 diff/파일을 Read. `autonomy-policy.md`를 읽는다.
2. **tier 독립 재분류.** caller가 넘긴 tier label을 **신뢰하지 않는다** — diff를 보고 직접 LOW/HIGH를 재도출한다(저평가 교정의 마지막 방벽). caller label과 다르면 **더 높은 쪽을 택한다**. HIGH면 도메인 juror를 패널에 추가.
3. **default-to-reject로 fan-out.** 각 juror를 **병렬 Task**로 띄운다(`arch-review` Phase 7 패턴). 각 Task 프롬프트에 아래 헌장 + 그 juror의 축 체크리스트 + 대상 diff/파일 + 성공 기준을 담는다:

   > 너는 적대적 reviewer다. **기본 판정은 REJECT**다. 네 축에서 (a) 변경이 명시된 성공 기준을 충족하고 (b) blast-radius 회귀를 만들지 않음을 **적극적으로 입증할 수 있을 때만** APPROVE하라. 입증 못 하거나 불확실하면 REJECT. 작성자의 의도에 영합하지 마라("아마 괜찮을 것"은 REJECT다). 라이브 player를 brick할 수 있는 비가역 위험을 발견하면 BLOCK.
   > 반환 형식: `VERDICT: APPROVE|REJECT|BLOCK` + 근거(파일:라인 인용) + severity(critical/high/medium/low). 근거 없는 APPROVE 금지.

4. **집계** (`autonomy-policy.md` 규칙):
   - **LOW**: 과반 APPROVE **그리고** BLOCK 0건 → PASS.
   - **HIGH**: **만장일치 APPROVE** → PASS. REJECT나 BLOCK이 하나라도 있으면 FAIL.
   - **BLOCK은 tier 무관 즉시 FAIL** — 비가역 위험 신호이므로 LOW/HIGH 어느 쪽이든 한 표만 나와도 정지.
   - **fail-closed**: juror 출력이 누락/파싱 불가면 그 표는 **REJECT**로 센다.
5. **Verdict 출력** (아래 형식). 쓰기 없음.
6. **HIGH PASS면** 출력 말미에 명시: **"HIGH tier — 사람 종단 서명 필요. 자동 merge/apply/deploy 금지."**

## 출력 형식

```
PANEL VERDICT: PASS | FAIL   (tier=LOW|HIGH, 재분류=caller와 동일|승급)
- code-reviewer (품질+security): APPROVE|REJECT|BLOCK — <한 줄 근거>
- architect (설계+blast-radius): APPROVE|REJECT|BLOCK — <한 줄 근거>
- tdd-guide (testability):       APPROVE|REJECT|BLOCK — <한 줄 근거>
- <도메인 juror> (HIGH만):        APPROVE|REJECT|BLOCK — <한 줄 근거>

required changes (FAIL 시): <juror별 핵심 수정 사항 통합 목록>
HIGH 종단 게이트: <PASS면 "사람 서명 필요"; LOW면 생략>
```

## 주의

- **read-only**: 이 skill은 verdict만 낸다. 수정·재시도는 호출자 책임.
- **Codex degradation**: Codex 설치엔 Task subagent 실행이 없어 이 패널이 붕괴한다 → 이 skill은 codex 타깃에서 **드롭**된다(`harness.toml skills_drop`). Codex에서 HIGH-tier는 **사람이 매 게이트를 명시 리뷰**하는 전환-전 동작으로 폴백한다(`assets/codex/AGENTS.md` §7).
