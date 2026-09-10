# GPT-6 follow-up audit and installation — 2026-09-10

## 범위와 baseline

현재 `main`의 직전 migration 미커밋 변경을 baseline으로 보존했다. 기존 보고는
`codex-migration-2026-09-10.md`: Windows/Python 3.12.8, 348 tests OK / 2 skips.
Staged 변경은 없었고 기존 unstaged/untracked 및 사용자 `HANDOFF_DELEGATE.md`를 보존했다.
문서의 live 금지와 달리 이번 직접 메시지는 live 설치를 명시 승인했으므로 Codex target만
preview·백업·검증 후 설치한다. Claude home, 인증, CLI 버전, interactive model 설정,
branch/commit/push는 변경하지 않는다.

## 추가 delta

- `content/agents/_core/cpp-build-resolver.md`: 고정 CMake/도구 실행 대신 실제 build target,
  원 exit code 보존, 선택적 도구, UE runtime not_run.
- `content/agents/_core/cpp-reviewer.md`: 길이/스타일만으로 HIGH/BLOCK 금지. read-only에서
  build artifacts를 쓰지 않고 parent evidence 또는 not_run 사용.
- `content/agents/_core/architect.md`: ADR 직접 작성 지시를 parent에 추천/초안 반환으로 수정.
- `content/agents/_ue/unreal-specialist.md`, `_unity/unity-specialist.md`: 의무 consult 잔존 제거.
- `content/agents/_gamedev/gameplay-programmer.md`: 모든 상수·시스템을 config/interface화하는
  규칙을 실제 tuning/경계 필요에 한정. ADR 부재만으로 새 세션 요구하지 않음.
- `content/skills/perf-profile/SKILL.md`: M/L effort별 선택 질문 제거. 보고 요청은 추천으로
  마무리하고 측정 없는 impact는 unknown 허용.
- `content/skills/ue-umg-review/SKILL.md`: 일반 review가 skill 수정 권한을 만들지 않음.
- `adapters/codex.py`, `install.py`, `check.py`: manifest에서 빠진 discovery entrypoint 중
  receipt/hash 일치 파일만 백업 후 retire. 대상은 `skills/*/SKILL.md`, `agents/*.toml`.
  사용자 수정·미소유 파일은 보존, 경로 traversal/symlink는 거부, dry-run은 쓰지 않음.
  나머지 참고 문서/로그는 자동 삭제하지 않음. receipt 없는 legacy 파일은 추측 삭제하지 않음.
- `orchestrator/tests/test_installer_migration.py`: unchanged retirement/backup/idempotence,
  사용자 수정 보존, traversal 사전 거부 회귀 검증 추가.

전역 `assets/codex/AGENTS.md`는 이미 해결되어 수정하지 않았다: **4615 → 4615 bytes**.
직전 전환의 20778 → 4615 bytes와 이번 추가 효과를 혼동하지 않는다.
별도 호출 비용/모델 비교 benchmark는 수행하지 않았고 품질·token 절감 수치를 주장하지 않는다.

## Hook 감사표

현재 handler 경로는 `assets/claude/hooks/handlers/<name>.py`; Codex adapter가 공통 Python을
설치하고 target별 등록을 생성한다. 파일 존재 자체와 hook 등록을 구분했다.

| Hook | 실제 경로 | 시작 상태 / 최종 조치 | 이유·검증 |
|---|---|---|---|
| scope_check | native PreToolUse + headless delta net | 이미 해결됨 / 유지 | 보호 경로·payload 유지; offline handler 및 installer 검사 |
| secret_scan | native PreToolUse + headless delta net | 이미 해결됨 / 유지 | native 기본 dryrun과 net enforce/fail-closed 구분; 검사 제거 없음 |
| suggest_compact | Claude legacy 등록; Codex 미등록 | 이미 해결됨 / 기본 비활성 | edit 횟수는 context 잔량 아님; exact legacy 등록만 백업·교체 |
| learning_log | Claude PostToolUse; Codex opt-in, learnings-review 소비 | 이미 해결됨 / 기본 비활성 | raw command/output 저장 제거 유지; 사용자 로그 삭제 없음 |
| route_nudge | Claude UserPromptSubmit | 근거상 유지 / legacy Two-CLI 전용 | Codex inline에 이식하지 않음 |
| builder_guard | Claude structured write guard | 근거상 유지 / legacy Two-CLI 전용 | Claude 정책 보존, Codex 직접 구현 제한 아님 |

[공식 Hooks](https://learn.chatgpt.com/docs/hooks)의 현재 설명은 unified exec를 Bash로,
apply_patch를 Edit/Write alias로 매칭하며 입력은 `tool_input.command`라고 명시한다.
현재 등록/파서는 이에 부합한다. 설치 CLI는 0.153.4이며 exit-2 지원 설명과 실제 native
발화·차단 실측은 별개다. 임시 home은 인증·exact hook trust가 없어 native runtime smoke는
not_run; 인증 복사, trust 우회, 실제 비밀값 실험은 하지 않았다. 이전 버전 관찰은 보존했다.

## Skill 감사표

현재 경로는 `content/skills/<name>/SKILL.md`. Codex adapter는 name/description을 보존하고
Claude 전용 frontmatter tool/model/fork를 native 실행 지시로 복사하지 않는다.
아래 행동 판정은 실제 요청→trigger→분기 **정적 검토**이며 모델 실행 측정이 아니다.

| Skill | 실제 사용 경로 | 시작 상태 / 최종 조치 | 이유·검증 |
|---|---|---|---|
| think-before-coding, goal-driven-execution | 비단순 구현의 짧은 가정/목표 | 이미 해결됨 / 필요 시 로드 | routine 승인 반복 없음 |
| simplicity-first, surgical-changes | 기존 구현 수정 | 이미 해결됨 / 유지 | 최소 변경·dirt 보호 |
| autonomous-loop | 승인된 구현·검증 반복 | 이미 해결됨 / 필요 시 로드 | inline, 위험별 review, 무제한 반복 없음 |
| hotfix, tech-debt | 명시 hotfix / debt 조사·등록 | 이미 해결됨 / 필요 시 로드 | branch 유지, 보고-only 쓰기 금지 |
| search-first, iterative-retrieval | repo 검색 / 부족한 context 탐색 | 이미 해결됨·근거상 유지 / 필요 시 로드 | repo-first, 자료 재사용, 검색 예산은 무한 반복 방지 |
| verification-loop, eval-harness | project checks / 명시 eval | 이미 해결됨 / 필요 시 로드 | 보편 coverage·도구 설치·일상 eval 문서 강제 없음 |
| adversarial-review, arch-review | 중요한 독립 검토 | 이미 해결됨 / 필요 시 로드 | evidence 기반, 미호출 review는 not_run |
| walkthrough, strategic-compact | 요청한 tour / 필요한 세션 인계 | 이미 해결됨 / 필요 시 로드 | 사소한 변경 구조문서·횟수 기반 compact 강제 없음 |
| codebase-onboarding | repo 안내 또는 요청한 AGENTS 생성 | 이미 해결됨 / 필요 시 로드 | guide-only는 policy 쓰기 아님 |
| harness-review, scope-check | 명시 harness/scope 감사 | 근거상 유지 / 필요 시 로드 | read-only 경계·실제 기준 필요 |
| learnings-review, changelog, cli-update | 로그 승격 / release note / 명시 CLI 관리 | 이미 해결됨 / 필요 시 로드 | 일반 구현에 자동 실행하지 않음 |
| ue, bp, gas, repl, umg | 관련 엔진 도메인 | 이미 해결됨 / 필요 시 로드 | 설치 specialist reference만 필요한 부분 읽음 |
| perf-profile | profiling 요청→budgets→후보·증거→추천 | 추가 수정 필요 / Codex용 수정 | M/L별 반복 선택 제거, unknown 측정 허용 |
| ue-umg-review | widget review→전문 checklist→findings | 추가 수정 필요 / Codex용 수정 | 자동 skill edit 제거, 도메인 checklist 보존 |
| delegate | 명시 Claude Builder dispatch | 근거상 유지 / legacy Two-CLI 전용 | Codex target 제외; 기존 미소유 파일은 추측 삭제 금지 |

## Agent 및 지침 감사표

Agent source는 `content/agents/<group>/<name>.md`, 생성 경로는 `agents/<name>.toml`이다.
현재 profile 연결을 재사용했고 모델 전면 통일이나 routing 재설계는 하지 않았다.

| Agent/지침 | 실제 사용 경로 | 시작 상태 / 최종 조치 | 검증 |
|---|---|---|---|
| architect | 선택적 설계 consult | 추가 수정 / read-only 초안 반환 | 정적 review + 생성 TOML |
| planner, tdd-guide | 선택적 계획/검증 설계 | 이미 해결됨 / 필요 시 로드 | 고정 coverage 없음; read-only |
| code-reviewer | 중요한 독립 구현 review | 이미 해결됨 / 유지 | self-review와 구별; read-only |
| cpp-reviewer | C++ 독립 검토 | 추가 수정 / 증거 기반 severity | style-only BLOCK 제거; read-only |
| cpp-build-resolver | 승인된 C++ build 수정 | 추가 수정 / project target 우선 | 고정 generic 명령 제거 |
| gameplay-programmer | 독립 gameplay 구현 | 추가 수정 / 필요 기반 config/interface | 기존 불변식·수명·소유권 지침 보존 |
| network-programmer, tools-programmer, ui-programmer | 선택한 독립 구현 | 이미 해결됨 / 필요 시 로드 | 동일 tree 병렬 writer 금지 유지 |
| performance-analyst | 독립 profiling 분석 | 이미 해결됨 / 필요 시 로드 | read-only profile |
| unreal-specialist, unity-specialist | 필요한 engine consult/구현 | 추가 수정 / 선택적 호출 | 전문 reference/버전/replication/save 지침 보존 |
| assets/codex/AGENTS.md, content/templates/AGENTS.md | 기본/프로젝트 지침 | 이미 해결됨 / 유지 | confirm-first 충돌 없음 |
| content/roles/*, rules/_mode/*, two-cli-reference | 명시 Two-CLI | 이미 해결됨 / legacy 전용 | HANDOFF·HIGH 계약 보존 |
| rules/agent-routing, autonomy-policy | 선택적 routing/review | 이미 해결됨 / 필요 시 로드 | 모든 작업에 challenge+jury 연쇄 없음 |

## 대표 요청의 정적 흐름

1. 단일 함수 bug: inline→필요한 가정→수정→관련 regression→self-review. HANDOFF/agent 강제 없음.
2. 관련 여러 파일 feature: 짧은 계획→동일 세션 구현→project checks. 파일 수로 분리하지 않음.
3. save/replication 불변식: 전문 reference→승인 범위 구현→검증→독립 review→HIGH 사람 수용.
4. explicit Two-CLI: 선택적 reference→Architect/Builder HANDOFF 계약→delta net·검토·수용.
5. 구현 중 보완: 목표·권한 내 가역적 설계 보완→검증 계속. 의미 있는 범위 변경만 질문.

## 검증 및 live 설치 기록

임시 생성 위치:
`C:/Users/rockwonitglobal_1/AppData/Local/Temp/dinner-followup-한글-531a0249ac424c12b89c17ca06c03180`

- 반복 설치 PASS: 13 agents, 28 skills, 기본 hook 2개, drift=0 / leftovers=0.
- 전체 offline suite: 350 tests, OK / 2 skips, 79.072초. 이후 추가한 traversal 회귀
  test도 별도로 PASS(1 test, 0.611초). 새 실패 없음. Installer suite는 당시 19 tests,
  OK / 1 skip이었으며 skip은 Windows symlink 생성 권한 부족이다.
- Python compileall, `git diff --check` PASS.
- Source check는 Codex 생성 TOML/JSON/reference/profile 및 Claude legacy hash 모두 PASS.
- 독립 reviewer가 7개 policy 수정 그룹과 retirement의 백업/권한 경계를 검토했다.
- Linux/UE/Unity runtime, 실제 Astra 모델 호출과 native sandbox/hook enforcement는 not_run.
  Windows offline·subprocess fake 성공을 실제 서비스 검증으로 표현하지 않는다.
- Skill quick_validate는 기존 환경의 PyYAML 부재로 not_run. 생성 frontmatter/reference 검사는 수행.

설치 순서:

```powershell
py -3 install.py --target codex --adopt-existing --dry-run
py -3 install.py --target codex --adopt-existing --allow-live
py -3 check.py --target codex
```

새 CLI 세션의 모델 선택: `codex -m gpt-6-astra -c model_reasoning_effort='"medium"'`.
앱은 지원하는 model/effort 선택기를 사용한다. 실행 중 세션의 모델을 변경하지 않았으며
새 설치 지침은 새 세션에서 로드한다. Hook 정의 변경은 정상 trust 확인 절차를 따른다.

### Live 결과와 남은 항목

`C:/Users/rockwonitglobal_1/.codex` 설치 완료. `py -3 check.py --target codex` exit 0,
repo == 설치본, drift 없음. Legacy hook 4개를 현재 기본 scope/secret 2개로 교체했다.
다른 사용자 hook은 exact-match ownership 규칙에 따라 보존한다. 이번 live 계획에는
obsolete skill/agent 파일 retirement가 없었고 사용자 파일을 임의 삭제하지 않았다.

기존 파일 54개 백업:
`C:/Users/rockwonitglobal_1/.codex/.dinner-harness-backups/0f22fad28695485191e4b83dd6d609ef`
백업 파일은 원래 상대경로를 보존하므로 필요 시 항목별 복구 가능하다. 복구하려면 변경된
ownership receipt와 hook trust도 함께 검토해야 하며 전체 home 덮어쓰기는 권장하지 않는다.

리뷰 완료, 추가 delta의 코드·정책 이슈 없음. 다만 **환경 후속 1건**:
`C:/Users/rockwonitglobal_1/.agents/skills`는 별도 실제 디렉터리이며 같은 이름의 이전 skill이
존재한다. 현재 manifest/receipt의 소유 대상이 아니므로 삭제·덮어쓰지 않았다.
이 세션의 discovery에도 해당 경로가 표시되므로 새 Codex home의 conformance PASS가
모든 discovery root의 중복 해소를 뜻하지 않는다. 이 경로를 계속 사용할지, 별도 백업 후
정리할지는 추가 소유권/사용자 의도 확인이 필요하다. native runtime not_run과 별개 항목이다.

## 091c1fb 이후 결함 수정 및 발견 경로 정리

이번 후속의 시작 HEAD는 `091c1fbdf886b94be2dd91e69c56c1e8fa9662e7`, branch는 `main`이다.
시작 시 staged/unstaged 변경은 없고 사용자 untracked `HANDOFF_DELEGATE.md`만 있었다.
해당 파일을 보존했으며 commit/push/branch 변경은 수행하지 않았다. 메인 Codex가 구현하고,
HIGH 결과 경계와 Git 검사 변경은 별도 read-only reviewer가 검토했다.

### Skill 발견·소유권·정리

- 이 프로세스의 `CODEX_HOME` 환경 변수는 미설정이며 설치 도구의 유효 기본 경로는
  `C:/Users/rockwonitglobal_1/.codex`다. `.agents/skills`와 `.codex/skills`는 서로 다른 실제
  디렉터리다. 기존 대화의 skill catalog에도 두 경로가 동시에 포함돼 있었다.
- 설치 CLI는 이번 조사 시 `0.154.0`이다. 앞 절의 `0.153.4`는 당시 관측으로 보존한다.
  이 작업에서 CLI를 업데이트하지 않았다.
- [공식 skill 문서](https://learn.chatgpt.com/docs/build-skills)는 user `.agents/skills`,
  CWD부터 Git root까지의 `.agents/skills`, admin/system 경로와 symlink 발견을 설명한다.
  같은 이름은 병합되지 않는다. 현재 `.codex/skills` 발견은 문서의 추정이 아니라 아래 RPC로 확인했다.
- 설치 CLI가 생성한 schema에 따라 새 app-server stdio 프로세스에서 `initialize` 후
  `skills/list`를 `cwds=[이 저장소]`, `forceReload=true`로 실행했다. thread/model turn은 호출하지 않았다.
  정리 전 **71 entries / errors 0**, 정리 후 **59 entries / errors 0**이었다.
  정리한 12개의 `.agents` entrypoint가 목록에서 빠지고 대응 `.codex` entrypoint는
  `enabled=true`로 남았다. 정리 후 `.agents` 15, `.codex/skills` 28, `.system` 6,
  bundled/runtime plugin skill 10개가 발견됐다.
- `.agents/skills/*/SKILL.md` 27개를 실제 파일 hash, 전체 내용 diff, Git의
  `content/skills` 전체 이력 blob과 비교했다. 이름·내용 유사성만으로 소유를 인정하지 않았다.
  확인한 파일은 모두 단일 hardlink이며 directory/file symlink가 아니었다.
  `.claude/skills`와 `.codex/skills`의 알려진 skill 디렉터리에도 이를 공유하는 link가 없었다.
- **12개 정리**: `bp`, `changelog`, `gas`, `goal-driven-execution`, `repl`, `simplicity-first`,
  `surgical-changes`, `tech-debt`, `think-before-coding`, `ue`, `ue-umg-review`, `umg`.
  CRLF/LF만 정규화한 전체 내용이 과거 source blob과 정확히 일치했다. 발견 경로 밖에
  백업하고 원본/백업 SHA-256을 대조한 뒤 해당 `SKILL.md`만 삭제했다. skill 폴더나 다른 파일은
  재귀 삭제하지 않았다. `simplicity-first`, `surgical-changes`는 현재 설치본과 본문이 같고
  frontmatter 표현이 달랐다. 나머지는 이전 routing·절차와 현재 Codex 지침의 내용 차이가 있다.
- **15개 보존**: `adversarial-review`, `arch-review`, `autonomous-loop`, `code-review`,
  `codebase-onboarding`, `eval-harness`, `harness-review`, `hotfix`, `iterative-retrieval`,
  `learnings-review`, `perf-profile`, `scope-check`, `search-first`, `strategic-compact`,
  `verification-loop`. `.Codex` 경로 치환, `agent:` binding, 과거 specialist 및 workflow 문구 등
  변경 흔적이 있으며 전체 내용과 일치하는 Git blob을 찾지 못했다. 사용자 수정 또는 별도
  도구의 변환본일 가능성을 배제하지 못하므로 임의 정리하지 않았다.
  `code-review`는 현재 설치본에 같은 이름이 없는 이전 alias 후보다. 나머지 **14개 동명 중복은 미해결**이다.

백업/증거 위치:
`C:/Users/rockwonitglobal_1/.dinner-harness-backups/2026-09-10-codex-followup/`

- `agents-skills/<name>/SKILL.md`: 정리한 원본 12개.
- `inventory.json`: 원래 절대 경로, hash, 일치하는 Git blob/path, 보존/정리 판정.
- `skill-comparison.md`: 27개 각 파일과 현재 Codex 설치본의 전체 diff.
- `runtime-before.json`, `runtime-after.json`: 새 프로세스가 반환한 name/path/enabled/scope만 저장.
- `discovery-after.json`, `check-live.txt`: read-only 진단 결과. 자격증명은 읽거나 저장하지 않았다.
- `RESTORE.md`: 기존 파일을 덮어쓰지 않고 entrypoint별로 복구하는 절차.

이는 **새 CLI 프로세스의 발견 목록을 확인한 결과**다. 실행 중 대화의 catalog가 갱신됐다는
증거, 새 interactive 모델 세션의 skill 본문 선택·실행 증거, 다른 앱/도구 전체의 로딩 증거는 아니다.
전체 중복 해소 또는 활성화 완료라고 판정하지 않는다.

`check.py`는 설치본 일치와 별도로 `[discovery:codex]`를 출력한다. 알려진 local roots의
`SKILL.md` name/path/hash와 동명 파일의 동일/상이 여부를 읽기 전용으로 진단하고, 접근 오류는
unknown으로 보고한다. symlink cycle과 같은 실제 경로의 중복 스캔을 방지한다. 소유권을
추정하거나 삭제하지 않으며, 동명 중복은 별도 advisory로 exit code를 바꾸지 않는다.
plugin/runtime 전용 root는 `--skill-root PATH`로 추가한다. 모든 plugin cache 버전을 활성 상태로
간주해 자동 스캔하지 않는다. `--no-install`은 기존 repo-only 의미를 유지하며,
`--skill-root`를 함께 주면 install drift 없이 discovery 진단을 추가할 수 있다.

### 유효 HIGH 경계와 receipt

각 gate의 유효 HIGH는 HANDOFF 선언 또는 Builder 보고 중 하나라도 HIGH이면 유지된다.
숫자 순서상 첫 유효 HIGH 이후의 `completed`는 `GateBoundaryError`이며 terminal **BLOCKED**다.
이는 출력 형식 오류가 아니므로 recovery/implementation 재호출을 하지 않는다. JSON의 extra field,
다중 legacy fence 같은 형식 문제와 위반이 같이 있어도 식별 가능한 gate 실행 주장을 먼저 검사한다.
이 관측용 추출은 완료 수용에 사용하지 않으며 정상 완료에는 기존 strict 계약 검증이 필요하다.

- LOW 1/LOW 2 → completed HIGH 1/completed LOW 2: BLOCKED, controller `completed_gates=[1]`,
  `remaining_gates=[2]`, `reported_completed_gates=[1,2]`, `contract_violation=true`.
  `remaining`은 controller가 완료로 인정하지 않았다는 뜻이지 실제 미수행을 뜻하지 않는다.
  원본 보고를 RESULT에 보존하고 scope/secret delta 검사와 관측 여부를 남긴다.
  이 위반을 이유로 rollback하지 않는다. 기존 별도 scope 위반의 복구 정책은 유지된다.
- LOW 1/LOW 2 → completed HIGH 1/pending LOW 2: 정상 중단으로 BUILT,
  `completed=[1]`, `pending=[2]`, `needs_review=[1]`. HIGH gate의 구현 보고와 독립 리뷰·사람 수용은 별개다.
- 선언 HIGH를 LOW로 보고해도 유효 HIGH다. LOW 연속 완료는 유지하고, 일반 blocked/pending
  dependency는 기존처럼 완료로 처리하지 않는다.

Outcome/receipt에 `effective_high_gates`, `reported_completed_gates`, `contract_violation`,
`implementation_observed`를 추가했다. 관측 불가 시 `implementation_observed=null`이며 미수행으로
단정하지 않는다. BUILT의 `built_high`/`built_low` 분류는 `effective_high_gates`로만 결정한다.
LOW의 `needs_review` 목록이나 사람이 읽는 reason 문구로 HIGH를 추측하지 않는다.
위반 receipt는 `status=blocked`, `reason_code=blocked_other`이며 built 분류를 받지 않는다.
기존 v1 receipt schema/status/code는 유지한다. 저장소의 receipt 소비 코드는 추가 metadata를
허용하며 challenge evidence 및 round-cap 소비는 기존 필드를 사용한다. 과거 receipt를 다시 쓰지 않았다.

**한계:** 이 gate 검사는 Builder 반환 후 사후 검증이다. Builder가 이미 수행한 후속 gate의
변경을 사전에 차단하거나 파일별 gate 귀속을 증명하지 않는다. native hook/sandbox enforcement의
대체 증거가 아니며, HIGH 결과의 독립 리뷰와 사람 수용은 호출 세션에 남는다.

### Git directory symlink

원인은 정상 fixture가 아니라 `_repo_relative()`가 Git의 leaf symlink `latest`를
`resolve()`로 target `builds`로 바꿔 `_opaque_dirs()`에 넘긴 것이었다. parent만 정규화해
Git이 보고한 leaf 경로를 보존했다. 내부의 정상 directory symlink는 통과시키고 실제 nested
repository/submodule은 계속 차단한다. 외부 target·broken/unresolved symlink는 Git witness로
그 내용을 검증할 수 없어 차단한다. symlink를 통한 repo 밖 쓰기는 검사 범위로 포함되지 않는다.
외부 링크를 사전/사후에 거부하는 테스트도 추가했다. 검사 불가 파일을 일괄 허용하지 않았다.

이 Windows 환경에서는 symlink 생성 권한이 없고 WSL도 설치되지 않았다. Linux 직접 실행은
`not_run`이다. Linux에서 다음 회귀를 실행해야 한다:

```text
python -m unittest orchestrator.tests.test_orchestrator.TestBuildFromHandoff.test_a_directory_symlink_does_not_refuse_the_dispatch orchestrator.tests.test_orchestrator.TestBuildFromHandoff.test_external_directory_symlink_is_refused_before_or_after_dispatch orchestrator.tests.test_orchestrator.TestBuildFromHandoff.test_a_real_nested_repo_is_still_refused -v
```

### 이번 검증 및 delivery 상태

최종 오프라인 검사와 독립 검토 결과는 아래에 기록한다. 앞 절의 역사적 테스트 수와 이번 실제
명령의 테스트 수는 별개 관측이다. 현재 승인 범위에서 skill 정리만 실제 환경에 반영했고,
HIGH controller 변경의 live 재설치·commit·push는 수행하지 않았다. 따라서 live install drift
검사는 `orchestrator/bus.py`, `orchestrator/controller.py` 2건을 별도로 보고한다.

- 최종 `python -m unittest discover -s orchestrator/tests`: **294 tests, OK / 4 skips**, 83.195초.
  skip은 installer symlink 1건, 내부 directory symlink 1건, 외부 symlink pre/post subtest 2건이다.
  기존 nested repository 차단 테스트는 PASS. 전체 실행 로그는 백업 폴더 `offline-tests.txt`에 있다.
- `python check.py --target codex --no-install`: exit 0. catalog와 생성 TOML/JSON/routing/reference 검사 PASS.
- 임시 Codex 설치를 두 번 수행하는 installer 회귀에서 사용자 config/hook/skill 보존,
  설치 drift 없음과 다른 discovery root의 충돌 진단이 독립적임을 확인했다.
- 실제 RPC에서 관측한 plugin skill roots까지 진단 입력에 추가해도 동명 **14건**, 접근/metadata 오류 0건.
  결과는 `discovery-with-observed-plugin-roots.txt`에 기록했다.
- 변경 Python compileall 및 `git diff --check`: PASS. 요청 범위의 변경 7파일에 기존
  scope/secret handler를 enforce로 실행: 차단 0건. 내용·비밀값을 출력하지 않았으며
  `scope-secret-check.json`에 파일 목록과 결과만 기록했다.
- self-review와 별도 code-reviewer 검토를 수행했다. reviewer가 발견한 malformed-schema
  recovery 우회, 외부 symlink 경계, 관측 metadata 누락, skill resource subtree 순회를 보완했다.
  재검토 결과: **리뷰 완료, 이슈 없음**. 독립 reviewer의 관련 33 tests(4 skips) 및 추가 핵심
  30 tests(1 skip) 검증도 통과했다. 이는 전체 suite와 별도의 실행 증거다.
- headless 실제 모델 호출, native hook/sandbox enforcement, 새 interactive 세션의 skill 선택·실행,
  Linux runtime은 `not_run`. HIGH 결과의 사람 수용은 아직 대기 상태다.

변경 파일은 `check.py`, `orchestrator/bus.py`, `orchestrator/controller.py`,
`orchestrator/tests/test_codex_followup.py`(신규), `orchestrator/tests/test_installer_migration.py`,
`orchestrator/tests/test_orchestrator.py`, 이 문서다. 라우팅·모델 정책·일반 inline 작업 절차는 변경하지 않았다.

### 후속 사용자 수용 및 live 적용

사용자가 위 결과에 대해 commit/push/live 적용을 명시 요청했다. `main`과 `origin/main`이
동일한 `091c1fb`임을 fetch 후 확인하고, `python install.py --target codex --dry-run` 다음
`python install.py --target codex --allow-live`를 실행했다. 실제 대상은
`C:/Users/rockwonitglobal_1/.codex`이며, 적용 후 `python check.py --target codex`는 exit 0,
**repo == 설치본, drift 0**이다. 앞 절의 controller live drift 2건은 이 적용으로 해소됐다.
소유 불명 skill 중복 14건은 그대로 advisory이며, native enforcement·interactive 로딩의
미검증 한계는 바뀌지 않았다. 커밋 대상은 위 7파일로 한정하고 사용자 `HANDOFF_DELEGATE.md`는 제외한다.
