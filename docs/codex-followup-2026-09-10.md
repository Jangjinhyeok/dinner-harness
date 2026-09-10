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
