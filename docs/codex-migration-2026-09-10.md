# Codex 중심 전환 결과 — 2026-09-10

## 범위와 baseline

요청 문서: `dinner-harness-codex-migration-prompt.md`의 A1–E5. Source 기준 commit은
`f654772edd45806cd46f929061274f8ef3ee5a5c`, delivery branch는 기존 `main`이다.
시작 시 routing과 기존 test의 수정, untracked `HANDOFF_DELEGATE.md`를 보존했다.
이번 작업에서 실제 home 설치, 인증 변경, CLI upgrade, commit/push/merge/deploy는 하지 않았다.
이전 대화에서 설치했던 routing은 이번 source 변경과 별개이며 다시 설치해야 새 workflow가 적용된다.

Baseline Windows / Python 3.12.8: 전체 offline tests 284개, 실패 없음, 1 skip, 57.981초.
원격 Linux에서 보고된 directory-symlink 실패는 이 Windows baseline에서 재현되지 않았다.
WSL 조회 결과 Linux runtime이 설치되어 있지 않아 Linux 실행은 not_run이다.

## 최종 실행 구조와 모델

기본은 메인 Codex가 탐색·계획·구현·관련 검증을 이어가는 inline workflow다.
파일 수 때문에 Builder로 자동 전환하지 않는다. 독립 탐색과 중요한 검토에만 native agent를
선택하고, parallel writer는 독립 임시 복사본·소유 범위·parent 통합을 먼저 정한다.
이번 구현도 그 방식으로 분리했고 parent가 현재 branch에 통합했다.

| 역할 | 모델 | Effort | 적용 방식 |
|---|---|---|---|
| Main / Architect | gpt-6-astra | medium | Interactive 권장값; 실행 중 세션은 자동 변경하지 않음 |
| 작고 명확한 위임 | gpt-5.6-luna | medium | 선택한 LOW headless / native logical profile |
| 일반 구현 위임 | gpt-5.6-terra | medium | NORMAL headless / native implementation |
| 복잡한 구현 / HIGH 최소 compute | gpt-6-astra | high | 실제 dispatch profile |
| 중요한 독립 review | gpt-5.6-sol | high | 별도 context, read-only |
| HIGH design challenge | gpt-6-astra | high | 구현과 별도 read-only invocation |

초기 운영 정책이며 최적 조합을 입증한 benchmark 결과가 아니다. Concrete policy는
`content/routing.toml` 하나에서 관리한다. `hybrid`와 `claude_only`의 기존 역할은 보존했다.
Native agent 13개에는 model/effort/sandbox를 명시하며 Claude frontmatter 모델명을 추측 변환하지 않는다.

`challenge/build`는 다른 모델에 명확한 작업을 맡기거나 controller의 pinned scope/secret net이
필요할 때 선택한다. 새 dispatch는 HANDOFF에 선언된 gate를 숫자순으로 실행하되 첫 HIGH까지로
제한한다. 그 전체 prefix의 최대 risk/compute를 먼저 적용한다. 남은 작업은 새 HANDOFF로 명시한다.
이전 RESULT를 재개 상태로 신뢰하지 않는다. `run`은 explicit vendor/model 옵션을 사용하는
legacy/experimental 경로이며 routing/effort pipeline 지원을 주장하지 않는다.
Real HIGH 구현은 이 legacy 경로에서 거부하며 bound `challenge/build`를 사용한다.

## 항목별 상태와 수정 파일

아래 경로는 repository 기준이다. “적용”은 local source와 offline 계약 검증을 뜻하며 live 인증·
모델 접근·native hook enforcement까지 입증했다는 의미가 아니다.

| 항목 | 상태 | 실제 변경 / 판단 |
|---|---|---|
| A1 | 적용 | `assets/codex/AGENTS.md`, `content/roles/*`, `content/rules/{two-cli-reference,routing-reference,agent-routing}.md`: inline 기본, Two-CLI 명시 선택 시 역할 제한 |
| A2 | 적용 | `content/templates/{AGENTS,README}.md`, `content/skills/codebase-onboarding/SKILL.md`: self-contained AGENTS, 기존 파일 보존; guide-only 요청은 project policy 생성 금지 |
| A3 | 적용 | `assets/codex/AGENTS.md`: 20,778 → 4,615 bytes, 77.8% 감소; 상세 규약은 rules/roles로 이동 |
| A4 | 적용 | `think-before-coding`, `search-first`, `goal-driven-execution`, `hotfix`, `tech-debt`, `walkthrough`: repo 우선 탐색, 중요한 질문만, 비례 보고 |
| A5 | 적용 + runtime 검증 대기 | AGENTS, `CODEX-RECON.md`, `CODEX-COVERAGE.md`, `harness.toml`, autonomy/review skills, README: 날짜 있는 정정; 과거 실측 보존 |
| B1 | 적용 | `content/routing.toml`, `orchestrator/{routing,config}.py`, `orchestrate.py`: codex_only SSOT 기본, 권장/native/headless 분리 |
| B2 | 적용 | `orchestrator/{bus,controller}.py`: numeric prefix, 전체 실행 범위의 max policy, 중복/모호 declaration 검증 |
| B3 | 적용 + 계정 unknown | `routing.py`, `config.py`: 빈 모델·잘못된 필드·vendor/effort 형식 차단; CLI parsing과 model access 분리 |
| B4 | 적용 | `routing.py`, `controller.py`, routing TOML: active preset의 명시적 vendor fallback, 부분 override 채움과 receipt 기록; HIGH 최소 profile 유지 |
| B5 | 적용 | `orchestrate.py`, routing 주석·README: run을 legacy/experimental로 표시하고 지원하지 않는 routing/effort 옵션 거부 |
| B6 | 적용 | `adapters/codex.py`, routing native mapping, `content/agents/**`: model/effort/sandbox 생성; review/planner/architect read-only |
| C1 | 적용 | `receipt.py`, `controller.py`: repo/task/draft/policy binding, fsync 후 atomic evidence, 동일 timestamp append order, mock evidence 격리, task별 cap |
| C2 | 적용 | `bus.py`, `controller.py`: completed/blocked/pending/needs_review 분리, 숫자순 정렬, 누락/중복/미선언 verdict 거부 |
| C3 | 적용 | `bus.py`, `controller.py`, `vendors.py`: versioned JSON schema, controller RESULT 렌더링, Markdown compatibility parser; panel self-report와 독립 review 분리 |
| C4 | 적용 | `controller.py`, `vendors.py`: 한 번의 read-only format recovery, 기존 report 보존; blocked·no-op 재구현 금지 |
| C5 | 적용 + runtime 검증 대기 | `vendors.py`, `watch-builder.ps1`: JSONL thread/error/usage, clean `-o`, dispatch별 marker, 자연어 header/private rollout 의존 제거 |
| C6 | 적용 | `controller.py`, `vendors.py`: 실패/timeout/encoding 오류 뒤 delta/net; Windows suspended Job Object와 child 종료 확인; bounded stdin/reader |
| C7 | 적용 | `vendors.py`, `controller.py`: removed Windows feature flag 제거; 쓰기 강요·머신별 launcher 실패 문구 제거 |
| D1 | 적용 | `content/skills/**`, `adapters/codex.py`, `harness.toml`: portable 본문, native discovery frontmatter, 생성 reference 검사 |
| D2 | 적용 | domain/admin/review skill 복원; `learning_log.py`, `common.py`의 raw command/output/exception 저장 제거. Fresh learning hook은 opt-in |
| D3 | 적용 | routing/autonomy rules, review/autonomous skills, core agents: 구현자 검증·중요한 독립 리뷰 1회 기본, 추가 축만 specialist |
| D4 | 적용 | adapter hooks, strategic-compact: fresh install compact 알림 비활성화; exact legacy 정의는 명시 adoption+backup 시 교체 |
| D5 | 적용 + native 실행 대기 | `scope_check.py`, `scope_protect.json`, common/adapter: Codex home/project security 경로 보호, Windows case-insensitive; trusted hook runtime는 not_run |
| D6 | 적용 | verification-loop, planner/tdd agents, templates: 프로젝트/UE/Unity 명령 우선, baseline delta, exit code 보존, 강제 80% 제거 |
| E1 | 적용 | `refresh.py`, `check.py`, cli-update skill: selected `codex|claude|all`; Codex-only에 Claude live 의존 없음 |
| E2 | 적용 | install/adapter: actual Python path, custom home/live guard, TOML round-trip, 사용자 hooks 보존, 소유권·conflict preflight·명시 adoption backup |
| E3 | 적용 | `check.py`, manifest, README catalog: Codex 생성물·모델·sandbox·reference 검사; Claude hash는 legacy에 한정, re-bless로 통과시키지 않음 |
| E4 | 근거 있는 보류 | synthetic 1/10/50 files = 0.113/1.054/5.532초. 필수 전환과 분리해 batch safety 재작성 보류; 기존 fail-closed/timeout/pinned-scope 유지 |
| E5 | 적용 | `vendors.py`, `receipt.py`, `controller.py`, watcher/docs: 경로/model/effort/실제 review 여부/retry 이유/usage 기록; native는 지원 UI/tools로 관찰 |

## 유지한 경계와 검토

Scope/secret 검사, 사용자 dirt baseline/delta, HANDOFF 변조 감지, UTF-8, shell=False·stdin prompt,
branch ownership, HIGH 독립 검토·사람 수용을 유지했다. Inline native hooks와 headless 사후 검사는
동등한 all-I/O containment가 아니다. Builder의 PASS·BUILT나 challenge 완료를 수용 승인으로
사용하지 않는다. Controller가 수행한 검사는 scope/secret이며 Builder의 build/test PASS는
`verification_claim`이다. 실제 실행하지 않은 independent implementation review는 `not_run`이다.

독립 리뷰에서 Windows orphan child, invalid/surrogate JSON 결과의 net 우회, Windows 보호 경로
case 변형, 설치 parent conflict, legacy hook 잔존, onboarding guide의 과도한 policy 생성이
발견되어 수정했다. Legacy real `run`의 중복 gate도 strict parser로 사전 거부하여 HIGH 우회를 막았다.
중요한 review는 vendor runner, installer, controller/evidence/hooks 및 정책
시나리오로 나눠 수행했다. 반복 style jury 대신 구체적 결함과 재현을 기준으로 수정했다.

## 검증 증거

- 최종 전체 offline suite: `py -3 -m unittest discover -q` — 348 tests, OK, 2 skips, 74.030초.
  Baseline 대비 추가 실패 없음. 마지막 legacy duplicate-gate 수정까지 포함한 최종 실행이다.
- 한글 임시 경로 설치를 반복했고 `check_install`의 drift/leftover가 모두 없었다.
- 최종 source check(`py -3 check.py --no-install`), Python compileall, `git diff --check`가 통과했다.
- Fresh 생성물: 13 native agents, 28 skills, scope/secret hook 2개, routing과 필요 rules/roles.
- Installer tests: custom home, Unicode/공백/escape, 사용자 hook 보존, 반복 설치, legacy adoption backup,
  ancestor conflict의 사전 차단을 검증한다. Windows symlink privilege 부족 case는 skip이다.
- Vendor tests는 실제 Python subprocess fake로 JSONL·stdin·`-o`·schema argv·exit/timeout·child 종료를
  검증한다. 실제 Astra 서비스 호출 성공이나 OS sandbox enforcement를 주장하지 않는다.
- Native policy 행동 검토: single-file fix, 3-file UI, HIGH save, explicit Architect, walkthrough,
  Codex onboarding 6개 시나리오. 필수 per-file HANDOFF·외부 조사·coverage loop 없이 동작한다.
- Bundled skill quick_validate는 PyYAML이 없어 not_run; 환경 설치 없이 자체 frontmatter/reference와
  생성 검증을 수행했다. 일반 Python compile 및 unittest 검증은 별도로 수행한다.

Installed CLI는 0.153.4, 로그인 상태는 ChatGPT로 확인했다. 인증 파일·token 본문은 읽지 않았다.
CLI help는 `--json`, `--output-schema`, read-only/workspace-write를 제공한다. Generated protocol schema의
ReasoningEffort는 nonempty string이며 nonsense 값도 일부 config 명령이 수용하므로 이것을 model 지원
증거로 사용하지 않았다. 중간/높은 effort 초기값의 실제 계정 접근성은 unknown이다.

Fresh temporary CODEX_HOME은 로그인되어 있지 않고 exact hook trust도 설정되지 않았다. 인증 복사나
trust bypass 없이 native hook firing/deny/reason/nested call, 실제 model dispatch와 sandbox enforcement는
not_run으로 남겼다. 공식 문서의 지원 설명과 로컬 실측을 혼동하지 않는다.
[Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents),
[Non-interactive output](https://learn.chatgpt.com/docs/non-interactive-mode),
[Hooks](https://learn.chatgpt.com/docs/hooks),
[Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox).

## 실제 설치 명령 — 이번 작업에서는 실행하지 않음

기존 legacy 설치는 아래 preview의 대상과 backup 계획을 검토한 뒤 명시 adoption을 사용한다.
사용자 변경은 backup하며, 정확히 일치하지 않는 사용자 hook은 보존한다. 이후 소유권 receipt로 갱신한다.

```powershell
py -3 check.py --target codex --no-install
py -3 install.py --target codex --adopt-existing --dry-run
py -3 install.py --target codex --adopt-existing --allow-live
py -3 check.py --target codex
```

후속 정상 갱신: `py -3 refresh.py --target codex --apply`.
새 interactive 세션: `codex -m gpt-6-astra -c model_reasoning_effort="medium"`.
앱에서는 지원되는 model/effort 선택기를 사용한다. Routing 변경은 열린 세션의 모델을 바꾸지 않는다.
Hook 정의가 바뀐 설치는 supported hook trust 절차로 확인하며 우회 flag를 자동 추가하지 않는다.

재사용하는 HANDOFF 파일의 새로운 작업에는 `challenge`와 `build` 양쪽에 같은 `--task-id`를 지정한다.
실험성 `run`, raw resume --last 또는 단일 global marker를 새로운 기본 workflow로 사용하지 않는다.

구조 결정은 [ADR-0022](architecture/ADR-0022-codex-inline-and-bound-dispatch.md),
사용자 진입점은 [README](../README.md), profile 원본은 [routing](../content/routing.toml)이다.
