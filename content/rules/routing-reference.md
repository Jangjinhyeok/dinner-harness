# Multi-Model Routing — Reference Detail

이 문서는 ADR-0020(Multi-Model Routing)이 도입한 routing preset 시스템의
상세 참고 문서다. **자동 inject되지 않는다** — `content/instructions/
CLAUDE.md`의 포인터를 따라 필요할 때만 Read한다.

## 1. 두 분류 축 — Safety Risk와 Compute Tier는 별도다

**Safety Risk (`LOW`/`HIGH`)**: blast radius, reversibility, network/save/
security/build/public contract 영향, human sign-off 필요 여부를 가른다.
정의는 `~/.claude/rules/autonomy-policy.md`가 유일한 소스다.

**Compute Tier (`LOW`/`NORMAL`/`HIGH`)**: implementation complexity, 필요한
builder compute/model budget을 가른다.

이 둘은 **독립된 축**이다. `NORMAL`은 compute tier 값일 뿐 safety risk tier가
아니다 — `risk=NORMAL`이라는 값은 존재하지 않는다.

## 2. Routing invariant

| Risk | Compute | 결과 |
|---|---|---|
| LOW | LOW | `builder_low` |
| LOW | NORMAL | `builder_normal` |
| LOW | HIGH | `builder_high` |
| HIGH | (무관 — 강제 HIGH) | `challenger_high` → Architect adjudication → `builder_high` → Reviewer → **Human sign-off** |

- Risk ambiguity → **HIGH** (fail-closed, autonomy-policy.md와 동일 원칙)
- Compute missing/ambiguity → **NORMAL**
- Risk HIGH는 선언된 compute 값과 무관하게 항상 effective compute HIGH를
  강제한다(`orchestrator/bus.py`의 `effective_compute()`).

## 3. Logical profiles

controller/workflow는 concrete model이 아니라 아래 **logical profile 이름을**
기준으로 동작한다:

- `architect` — 설계·HANDOFF 작성·RESULT 리뷰
- `challenger_high` — HIGH-risk ADR/HANDOFF에 대한 read-only 비판(§7)
- `builder_low` — compute LOW 구현 dispatch
- `builder_normal` — compute NORMAL 구현 dispatch
- `builder_high` — compute HIGH 또는 risk HIGH 구현 dispatch
- `reviewer` — 결과 리뷰

## 4. Presets

현재 두 preset이 있다: `hybrid`(기본)와 `claude_only`. **concrete model
assignment는 configuration이지 workflow invariant가 아니다** — 아래 표의
Luna/Terra/Sol/Sonnet/Opus는 현재 `content/routing.toml`의 값일 뿐, logical
workflow 자체가 아니다. 모델이 바뀌면 이 표와 `routing.toml`만 바뀐다.

## 5. `hybrid` (기본)

| Logical profile | Vendor | Model | Effort |
|---|---|---|---|
| architect | claude | Claude Sonnet 5 | medium |
| challenger_high | claude | Claude Opus 5 | low |
| builder_low | codex | GPT-5.6 Luna | high |
| builder_normal | codex | GPT-5.6 Terra | medium |
| builder_high | codex | GPT-5.6 Sol | high |
| reviewer | claude | Claude Sonnet 5 | medium |

## 6. `claude_only`

| Logical profile | Vendor | Model | Effort |
|---|---|---|---|
| architect | claude | Claude Sonnet 5 | medium |
| challenger_high | claude | Claude Opus 5 | low |
| builder_low | claude | Claude Sonnet 5 | low |
| builder_normal | claude | Claude Sonnet 5 | medium |
| builder_high | claude | Claude Opus 5 | low |
| reviewer | claude | Claude Sonnet 5 | medium |

**`architect`/`reviewer`는 dispatch-controlled가 아니다.** primary
interactive path(`orchestrate.py build`)에서 이 두 profile은 **실제로
dispatch되지 않는다** — Architect/Reviewer는 사용자가 이미 열어 둔 인터랙티브
세션 자신이고, orchestrator는 그 세션의 model을 바꾸지 않는다. 이 두 profile
값은 그 인터랙티브 세션이 따라야 할 **recommended policy**를 기록해 둔
것뿐이다. `challenger_high`/`builder_low`/`builder_normal`/`builder_high`만
`orchestrate.py build`/`challenge`가 실제로 dispatch하는 profile이다.
`architect`/`reviewer`가 실제 dispatch profile로 쓰이는 경로는
secondary/experimental인 fully-headless `orchestrate.py run`뿐이다(이 경로는
아직 routing-aware하지 않다 — §11 참조).

## 7. HIGH Challenge flow

```
Draft ADR/HANDOFF
  → read-only challenger (challenger_high profile, 독립 invocation)
  → parent-owned CHALLENGE.md + evidence (orchestrator가 저장, challenger 자신이 아님)
  → interactive Architect가 읽고 Accept / Reject / Partially Accept 판정
  → Final ADR/HANDOFF
  → builder_high
  → Reviewer
  → Human sign-off
```

Challenger는 **read-only invocation**이다 — critique 파일이나 repository
파일을 직접 쓰지 않는다(`orchestrate.py challenge`가 stdout으로 받은 critique를
부모 프로세스가 `CHALLENGE.md`에 기록한다). Challenger와 동일 모델이 나중에
Builder로 쓰이더라도 반드시 **독립 invocation**이어야 한다 — 같은 context를
이어받지 않는다.

## 8. Preset 전환

**Persistent(기본 경로)**: `content/routing.toml`의 `[routing].preset`을
`"hybrid"` 또는 `"claude_only"`로 바꾸고 `py -3 refresh.py --apply`. 이
한 곳을 바꾸는 것만으로 workflow의 vendor 전략이 전환된다 —
`controller.py`·HANDOFF 포맷·risk policy는 그대로다.

**One-off**: `orchestrate.py build`/`challenge`의 `--routing-preset <name>`
플래그가 그 1회 dispatch에 한해 `content/routing.toml`의 `[routing].preset`
기본값을 override한다(`orchestrator/config.py`의 `Config.routing_preset`).

## 9. Explicit override precedence

- **risk=LOW**: 기존 `--builder claude|codex`, `--builder-model <name>`,
  `--builder-effort <level>`를 그대로 받아들인다 — 명시한 값이 routing
  preset보다 우선한다.
- **risk=HIGH**: arbitrary `--builder-model`/`--builder-effort` downgrade는
  **거부**한다(`BLOCKED`) — silent downgrade는 없다. `--builder claude|codex`로
  vendor만 override하는 것은 허용하되, 그 vendor의 `builder_high` logical
  profile로 resolve한다(임의 model 문자열이 아니다).
- override가 전혀 없으면 active preset의 해당 logical profile이 그대로
  적용된다.

## 10. Receipt / evidence

`orchestrator/receipt.py`의 `BuildAudit`은 매 dispatch의 terminal 기록에
`routing_preset`·`logical_profile`·`model`(concrete)·`effort`를 남긴다 —
content-free 원칙은 유지된다(HANDOFF/RESULT 텍스트나 prompt는 절대 기록하지
않는다, hash와 메타데이터만).

HIGH gate의 Builder dispatch는 매칭되는 challenge evidence가 없으면
**fail-closed로 BLOCKED**된다 — evidence는 challenged ADR/HANDOFF의 SHA-256
hash와 묶여 있어, 다른 내용(hash 불일치)에 대한 stale evidence는 거부된다.

## 11. 새 모델 출시 시 유지보수

새 GPT/Claude 모델이 나왔을 때 정상적인 작업은 다음으로 끝나야 한다:

1. VulcanBench 등 benchmark 재평가
2. 가격/속도/품질 검토
3. 실제 CLI compatibility 검증
4. `content/routing.toml`의 해당 profile mapping 변경
5. regression test(`orchestrator/tests/test_orchestrator.py`의 routing 테스트)
6. known-good compatibility 기록

다음을 수정해야 한다면 **abstraction failure**로 본다:

- `controller.py`의 routing algorithm
- HANDOFF contract
- safety risk policy(`autonomy-policy.md`)
- compute tier semantics(`bus.py`의 `effective_compute()`)

CLI invocation 방식 자체가 바뀌는 경우(새 flag, 새 auth 방식 등)에만
`orchestrator/vendors.py`의 backend/adapter 수정이 추가로 필요할 수 있다 —
이건 모델 mapping 변경과는 별개의, 드문 경우다.

## Remaining debt

`orchestrate.py run`(fully-headless, Architect+Builder 양쪽 headless)은 이
routing preset 시스템을 아직 쓰지 않는다 — `--builder`가 `"codex"` 고정
기본값이다. 이는 ADR-0020의 명시적 remaining debt다.
