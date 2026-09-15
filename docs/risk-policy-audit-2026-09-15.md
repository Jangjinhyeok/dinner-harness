# 단일 Codex 경로 Risk 정책 조사 — 2026-09-15

## 범위와 증거 수준

대상은 dinner-harness source, Codex adapter/manifest, 임시 생성물 및 이 컴퓨터의
`C:/Users/rockwonitglobal_1/.codex` 설치본이다. ASAN 게임 코드는 조사·수정하지 않았다.
시작 branch는 `main`, staged/unstaged 변경은 없었고 untracked `HANDOFF_DELEGATE.md`는
사용자 baseline으로 보존했다. 그 문서의 내용은 조사하지 않았다.

- **사용자 관찰**: ASAN 계획 세션 1건에서 원문 미열람, 시작 보고 계약 누락, HIGH 최종
  미충족 조건 노출 부족, Two-CLI 미사용 설명이 있었다. 원본 session/receipt를 제공받거나
  열람하지 않았으므로 해당 세션의 실제 도구 호출과 review 수행은 독립적으로 재확인하지 않았다.
- **직접 관찰**: 수정 전 `py -3 check.py --target codex` exit 0, source와 설치본 drift 없음.
  설치 실패로 생긴 차이가 아니라 동일한 정책 전달 구조가 배포되어 있었다.
- **원인 추정**: 원문 링크의 위치와 구체적 보고 계약 부재가 누락을 유발했을 가능성이 있다.
  한 세션의 행동을 harness 전체의 항상 재현되는 runtime 실패로 일반화하지 않는다.

## 확인된 정책과 재현 가능한 결함

| 영역 | 수정 전 근거 | 판단 / 보완 |
|---|---|---|
| Risk 값 | `content/rules/autonomy-policy.md`, `orchestrator/bus.py`의 `TIER_LOW/TIER_HIGH`, `parse_tiers`, `RESULT_SCHEMA` | Risk는 **LOW/HIGH 2단계**. MEDIUM을 추가하지 않음. 알 수 없는 HANDOFF Risk는 HIGH, invalid structured result는 거부 |
| Compute 값 | `content/rules/routing-reference.md`, `content/routing.toml`, `bus.effective_compute` | LOW/NORMAL/HIGH 3단계. Risk HIGH이면 effective Compute HIGH; Compute HIGH라고 Risk HIGH는 아님. model effort medium은 별도 축 |
| 기본 진입점 | `assets/codex/AGENTS.md`의 유일한 autonomy 원문 참조가 `선택적 경로` 아래 | 비단순 계획부터 원문을 읽도록 기본 절로 이동. 같은 세션에서 읽은 원문은 재사용 |
| 분류 기준 전달 | AGENTS는 HIGH 요약만 제공. controller `_TIER_RULE`에는 정책의 큰 blast radius가 없음 | 원문 진입점 강화, 프로젝트 template에 전체 범주, controller prompt에 누락 범주 추가 |
| 축 혼동 | legacy `tier`/bare `gate N: HIGH`, model `medium`, routing의 한정 없는 `Real HIGH 작업` 문장 | legacy schema는 호환 유지. 새 design prompt는 `risk=… compute=…`; routing 문장은 real **headless**로 한정 |
| 3단계 출력 잔재 | `content/skills/perf-profile/SKILL.md`의 `Risk: [Low/Med/High]` | 실제 배포되는 policy 불일치. LOW/HIGH로 수정. scope-check의 schedule/quality/integration 척도는 별도 보고 척도라고 명시 |
| 함수명 혼동 | `controller.compute_has_high()`는 Compute가 아니라 Risk HIGH를 판정 | import 호환 이름을 보존하되 docstring에 Risk 전용/compute는 동사임을 명시, 호출 변수 `has_high_risk`로 구별 |
| 계획·결과 상태 | 계획/구현/검증/독립 검토/사람 수용 및 REQUEST CHANGES 반영/재검토 구분이 명시적이지 않음 | 기본 AGENTS·정책·project template·관련 skills에 시작 계약과 최종 미충족 조건을 명시 |

재현 경로: 이전 `assets/codex/AGENTS.md`를 `## 선택적 경로` 앞뒤로 나누면 앞부분에
`rules/autonomy-policy.md`가 없다. 이전 `_TIER_RULE`에서 `blast radius`를 찾으면 없다.
새 회귀 검사는 이 두 조건을 직접 보호하고 custom home에 반복 생성한 정책 본문과 원문,
원문 참조가 실제로 존재하는지를 검사한다. 이는 지침 전달의 검사이며 모델 준수율 검사가 아니다.

Risk enum/parser/controller gate의 기존 기능 결함은 이번 조사에서 재현하지 못했다.
`MEDIUM`, `NORMAL`, 잘못된 Risk와 Compute HIGH/Risk LOW 조합을 회귀 검사에 추가했다.
legacy `tier`를 `risk`로 일괄 rename하거나 새 단계/설정/의존성을 추가하지 않았다.

## 단일 세션과 강제 검사 경계

| 경로 | 실제 역할 | 보장하지 않는 것 |
|---|---|---|
| AGENTS/skills/prompt | Risk 판단·원문 읽기·시작/완료 보고·독립 검토·사람 수용을 모델에 지시 | 실제 원문 열람, 올바른 의미 분류, 지침 준수의 강제 집행 |
| Native PreToolUse | 지원 CLI/도구 event에서 secret/scope handler를 호출해 허용/차단 | 모든 shell/MCP/I/O containment, 의미적 Risk 분류, review/사람 수용 증명 |
| Headless controller | 선언 Risk 파싱, HIGH dispatch 경계, pinned HANDOFF 및 baseline/delta scope/secret 검사, 계약/안전 검사 실패 차단. Single-shot build의 Builder panel FAIL은 advisory로 보존 | 잘못 선언한 LOW의 의미적 탐지, 사전 write 차단, 독립 reviewer 실행/사람 수용의 자동 인증 |

`orchestrator/controller.py`의 build는 기존부터 `independent_review=not_run`,
`needs_review_gates`와 HIGH 수용 대기 사유를 반환한다. BUILT는 구현 보고이며 최종 수용이 아니다.
`content/rules/two-cli-reference.md`도 이 차이를 설명한다. 단일 세션이 이 controller를
통과한다고 주장할 수 없다. `safety.scan`을 수동 실행해도 전체 controller workflow를 실행한
것과 같지 않다. native hook 실제 발화 여부는 이 작업에서 새 CLI 세션으로 실증하지 않았다.

정책은 모든 경로에 적용되고 Two-CLI 선택은 실행 방식이다. 이를 Risk 적용 여부의 설명으로
사용하면 안 된다. 기존 승인 범위의 로컬 구현은 계속 진행하며 HIGH **결과** 수용은 남긴다.
계획만 요청되면 계획 결과를 검토·수용하고 구현/runtime 검증은 not_run 및 향후 조건이다.
REQUEST CHANGES/FAIL 반영은 원래 판정을 지우지 않으며, 변경과 증거를 본 독립 재검토 전에는
`수정 반영, 재검토 대기`다. reviewer의 APPROVE/PASS도 사람 수용을 대체하지 않는다.

## 검증 및 수용 기록

- Targeted unittest: 9개 PASS. 최초 추가 테스트는 정상 frontmatter quoting을 차이로 오인하여
  4개 subtest FAIL; 정책 본문 비교와 기존 generated conformance 검사를 사용하도록 수정 후 PASS.
- `py -3 check.py --no-install`: PASS. catalog, legacy curation hash, generated TOML/JSON/references 검사.
- 1차 수정 후 설치 전 Codex drift: 당시 변경에 해당하는 배포 파일 9개만 다름.
  독립 검토 수정 및 mock 파생 수정 후 배포 대상 변경은 12개다.
- 첫 전체 suite: 369개 중 7 FAIL, 4 skip. 새 design prompt의 review 문구를 mock의
  부분 문자열 분기가 검토 호출로 오인했다. MockBackend와 테스트용 _WritingArchitect를
  명시적 `REVIEW.` 접두사로 구분하도록 수정; 관련 재검사 10개 PASS. 실제 vendor 실행 로직은 변경 없음.
- 최종 전체 offline suite: `py -3 -m unittest discover -s . -p "test_*.py"`, exit 0,
  **369개 실행, 실패 0, skip 4**. mock controller/실제 hook handler 및 임시 installer 검사이며
  live vendor/ASAN engine 검증이 아니다.
- Scope/secret: 명시한 파일 15개의 추가 delta를 기존 `safety.scan`/handler로 enforce 검사,
  exit 0, block/diagnostic 0. 전체 controller를 실행했다는 뜻은 아니다.
- Baseline delta: `git diff --check` PASS; staged 변경 없음; 예상한 source/test/report만 변경.
  기존 HANDOFF_DELEGATE.md SHA-256 `9570554a3d1411f21151e0cfc03b898e4b9f8dd9cfafdc78b7b08d0054aa14b6` 유지.
- 독립 reviewer `risk_review`: 1차 REQUEST CHANGES(출력 Risk 잔재·routing 축·legacy 함수명
  혼동)를 반영했고, reviewer가 실제 source/code와 추가 검사를 재검토하여 해결을 확인했다.
  최종 source/tests/진단 문서 판정: **APPROVE (독립 implementation review PASS), material issue 0**.
  reviewer 직접 검사: generation/parser 3개, prompt/tier gate 25개, mock/delta 6개 PASS,
  diff whitespace PASS. self-review와 이 독립 재검토는 별개다. reviewer의 최종 응답에는
  live 설치 not_run이 남아 있었으며, 아래 설치 후 확인은 메인 세션이 수행한 별도 증거다.
- Live 설치 반영: `py -3 install.py --target codex --allow-live`, exit 0.
  `py -3 check.py --target codex`, exit 0, **source→생성물→설치본 drift 0**.
  수정 전 일치→변경 대상 12개 drift→반영 후 일치를 확인했다. Claude home에는 설치하지 않았다.
- Native hook 실제 CLI 발화 및 새로운 interactive 세션의 지침 준수: **not_run**.
- Risk HIGH. 사람의 결과 수용: **수용** — 사용자가 결과 보고 후 “커밋 푸쉬 진행하자”로
  결과 수용 및 이번 변경의 commit/push를 승인했다. deploy는 승인 범위에 포함하지 않는다.
