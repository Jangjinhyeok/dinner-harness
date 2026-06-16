# dinner-claude

개인 Claude Code 설정. `~/.claude/` 백업 및 동기화용 private repo.

## 구조

```
.
├── CLAUDE.md                  # User-level 행동 원칙 + Two-CLI workflow 규약
├── MCP-UNREAL-SETUP.md        # 엔진 MCP(UE 5.7) 구체 셋업 walkthrough + 트러블슈팅
├── HANDOFF.md                 # Architect → Builder 통신 (현재 빈 템플릿)
├── RESULT.md                  # Builder → Architect 통신 (현재 빈 템플릿)
├── settings.json.template     # hook 등록 템플릿 (실 settings.json은 machine-specific, git 제외)
├── agents/                    # User-level agents
│   ├── _core/                 # ECC 출신 (planner, code-reviewer, cpp-reviewer 등)
│   ├── _gamedev/              # Game Studios 출신 (gameplay, network, ui 등)
│   ├── _ue/                   # Unreal Engine 전용
│   └── _unity/                # Unity 전용
├── skills/                    # User-level skills (Claude Code는 skills/<name>/ 1-depth만 스캔)
│   ├── search-first/          # generic (think-before-coding, simplicity-first 등 다수)
│   ├── verification-loop/
│   ├── ue-umg-review/         # 본인 자작 (구 _personal/ — 2026-06-10 직하 이동, 나머지 둘은 중복 삭제)
│   └── harness-review/        # 본인 자작 (2026-06-16 — harness 구조 정합 리뷰, propose+apply)
├── roles/                     # Two-CLI workflow 역할 정의
│   ├── ROLE_ARCHITECT.md      # 설계·영향분석·검토 세션
│   └── ROLE_BUILDER.md        # 구현·빌드검증·self-review 세션
├── hooks/                     # PreToolUse(secret_scan, scope_check, suggest_compact) + PostToolUse(learning_log)
│   ├── launchers/             # 인자 없는 절대경로 BAT wrapper
│   ├── handlers/              # Python 핸들러 (secret_scan·scope_check·suggest_compact·learning_log)
│   ├── lib/                   # fail-open / timeout 공통 wrapper
│   ├── rules/                 # 패턴·스코프 룰셋 JSON
│   ├── tests/                 # run_handler 안전 계약 unittest (stdlib only)
│   └── logs/                  # JSON-lines 로그 (동기화·git 제외)
├── rules/                     # auto-load 영역 (paths 없으면 매 세션 로드)
│   ├── agent-routing.md       # 엔진 orchestration 라우팅 규칙 (always-on)
│   └── _mode/                 # architect/builder reminder (통신 파일 paths 매칭 inject)
├── templates/                 # 프로젝트로 복사하는 템플릿 (agent·skill이 참조하는 컨벤션)
│   ├── AGENTS.md              # project-root용 cross-tool 에이전트 진입점 (Codex/Gemini CLI 등 → CLAUDE.md 참조)
│   ├── mcp.json               # project-root .mcp.json 템플릿 — UE/Unity 엔진 MCP 등록 (project scope)
│   ├── engine-reference/      # unreal/·unity/ VERSION.md — "Engine Version Safety" ground truth
│   └── architecture/          # ADR 템플릿 (Architect 세션 산출물)
└── ecc-reference/             # ECC 룰셋 카탈로그 — auto-load 영역 밖, 필요 시 Read만
    └── common/                # coding-style, security, testing 등 10개
```

루트의 `HANDOFF.md` / `RESULT.md`, `roles/`, `rules/_mode/`는 Two-CLI workflow(Architect 세션 ↔ Builder 세션 분리 운용)의 통신·역할 인프라다. 큰 작업은 Architect가 `HANDOFF.md`로 명세를 넘기고 Builder가 `RESULT.md`로 결과를 돌려준다. 통신 파일이 컨텍스트에 들어오면 `rules/_mode/`의 reminder가 paths 매칭으로 자동 inject된다 (`HANDOFF.md`/`INPUT.md` → builder, `RESULT.md` → architect). 상세 규약은 `CLAUDE.md` §2 참조.

`templates/`는 `~/.claude/` 동작과 무관한 **프로젝트 복사용 템플릿**이다. `_gamedev` agent들("Engine Version Safety" → `docs/engine-reference/<engine>/VERSION.md`)과 `architect`·`arch-review`(ADR → `docs/architecture/`)가 이미 참조하지만 비어 있던 프로젝트 컨벤션을 채운다. 새 프로젝트에서 해당 파일을 프로젝트 `docs/`로 복사해 쓴다. 상세는 `templates/README.md` 참조.

## 작동 방식 — 무엇이 어떻게 켜지는가

파일 목록보다 **각 부분이 어떤 방식으로 활성화되는가**가 핵심이다. 4가지뿐이다.

| 방식 | 누가 | 설명 |
|---|---|---|
| ① 항상 자동 로드 | `CLAUDE.md`, `rules/agent-routing.md`, `rules/` 중 `paths` 없는 파일 | 매 세션 시작 시 context에 박힘 |
| ② 조건부 자동 inject | `rules/_mode/*` (`paths: [글로브]`) | 매칭 파일이 context에 들어올 때만 (`HANDOFF`→builder, `RESULT`→architect) |
| ③ 명시 호출 | `skills/`, `agents/`, `roles/` | `/명령` · Task 위임 · "모드" 선언으로 직접 부름 |
| ④ 도구 호출 시 자동 발화 | `hooks/` | Edit/Write/Bash 직전 자동 검사 (allow/block) |

> **핵심 — `rules/`는 auto-load 영역이다.** `paths` 필드가 없으면 매 세션 무조건 로드, `paths: [글로브]`면 매칭 시에만 로드된다 (`paths: []` 빈 배열은 미정의 동작이라 의존 금지). 따라서 "매 세션 로드하지 않는 lookup-only 참고자료"는 `rules/` **밖**에 둬야 한다 — ECC 카탈로그를 `ecc-reference/`로 옮긴 이유다 (필요할 때만 Read).

**③ 명시 호출 심화:**
- **skills** — `/이름`으로 직접 부르거나, description의 트리거 문구를 모델이 인식하면 자동 발동. SKILL.md 본문은 호출 시점에만 context로 들어온다 (평소엔 이름·description만 인덱스). heavy-read 분석 skill(`scope-check`·`perf-profile`)은 frontmatter `context: fork`로 별도 subagent context에서 실행돼 대량 파일 읽기가 메인 context를 오염시키지 않는다.
- **agents** — Task 도구로 별도 context 세션에 위임 → 결과만 회수해 메인 context를 아낀다. 독립 작업은 병렬 호출. 코드 작성 agent는 frontmatter `skills:`로 메타 원칙(`simplicity-first`·`surgical-changes`)을 시작 시점에 preload해, trigger 인식 의존 없이 항상 적재되도록 보장한다.
- **roles** — "architect/builder 모드" 텍스트 선언 시 해당 ROLE 파일을 Read하여 규약 적재. ②의 `_mode` reminder가 백업으로 자동 박힌다.

**매일 관점**: 평소엔 ①(CLAUDE.md)과 ④(hooks)만 백그라운드로 돈다. ②③은 큰 작업/모드 진입 때만 등장한다. 가벼운 질문은 role 없이 일반 모드(필요하면 Plan Mode read-only)로 충분하다.

## hooks (PreToolUse + PostToolUse + UserPromptSubmit 안전망)

`hooks/`는 Claude Code가 도구 실행 직전(PreToolUse)·직후(PostToolUse) 및 프롬프트 제출 시(UserPromptSubmit)에 끼어드는 자작 안전망이다. 현재 차단형 hook 둘(`secret_scan`, `scope_check`)과 advisory-only hook 셋(`suggest_compact`, `learning_log`, `route_nudge`)이 있다.

| hook | 이벤트·matcher | 역할 | 출처 |
|---|---|---|---|
| `secret_scan` | Pre · Edit·Write·Bash | 입력에서 AWS key·GitHub PAT·`.env`/`.credentials` 류 시크릿·민감 파일경로를 regex로 검출 | ADR-0001 |
| `scope_check` | Pre · Edit·Write | cycle 스코프 밖 파일 수정 차단. always-block(보호 인프라 파일 블랙리스트) + scope codeblock(HANDOFF.md 화이트리스트) 2 layer | ADR-0005 |
| `suggest_compact` | Pre · Edit·Write | 도구 호출 누적(기본 50회, `COMPACT_THRESHOLD`) 시 stderr로 `/compact` 제안. 룰셋·차단 없음, 항상 exit 0 (advisory) | strategic-compact skill (ECC), 2026-06-01 |
| `learning_log` | Post · Bash | Bash 출력의 강한 실패 신호(컴파일/링크/빌드 에러 등)만 포착 → `learning_log.log`. `learnings-review` skill이 반복 항목을 CLAUDE.md로 승격. 차단 없음, 항상 exit 0 (advisory) | ADR-0004 / gap #4, 2026-06-01 |
| `route_nudge` | UserPromptSubmit | 프롬프트의 UE 도메인 신호를 regex 검출 → 위임 nudge 주입(단일 도메인→leaf, 멀티/일반→`unreal-specialist` 허브). 차단 없음, 항상 exit 0 (advisory) | 2026-06-16, commit 09aa4f9 |

공통 인프라: `settings.json` → 인자 없는 절대경로 BAT(`launchers/`) → `py -3` 핸들러(`handlers/`) → `lib/common.py`의 `run_handler` fail-open wrapper(200ms timeout, 예외 전건 catch, exit 0 기본). 정책 차단만 exit 2. 인자 없는 BAT 절대경로 패턴은 Claude Code Windows 빌드의 hook command argument escaping 결함 회피책이다.

모드는 각 환경변수(`CLAUDE_SECRET_SCAN_MODE` / `CLAUDE_SCOPE_WHITELIST_MODE`)로 `off`/`dryrun`/`enforce`를 정하며 새 세션부터 적용된다. **현재 `secret_scan`은 enforce, `scope_check`은 dryrun.** `secret_scan`은 1주 관찰(실사용 false-positive 0건) 후 2026-05-31 enforce로 승격했다(ADR-0001 Gate 4). `scope_check`은 always-block layer(`settings.json` + `hooks/` 본체 6 entries의 hook-integrity 핵심)만으로 dryrun에서도 즉시 차단이 작동하고, enforce는 ad-hoc 편집 마찰이 커서 **dryrun을 영구 유지**한다. 로그는 `hooks/logs/*.log`(JSON-lines, git·동기화 제외).

`suggest_compact`는 위 두 차단형과 달리 룰셋·모드·차단이 없는 advisory-only hook이다 — 도구 호출이 누적되면 stderr로 `/compact`를 제안만 하고 항상 exit 0이다. 핸들러·런처(`hooks/handlers/suggest_compact.py`·`hooks/launchers/suggest_compact.cmd`)가 배치됐고 `settings.json.template`·로컬 `settings.json`(`PreToolUse`) 양쪽에 등록 완료다(새 머신은 template로 자동 적용). `settings.json`은 scope_check always-block 대상이라, 활성화는 본인이 직접 hand-edit하거나(에디터로 직접 수정 시 hook이 발화하지 않음) off ceremony(`CLAUDE_SCOPE_WHITELIST_MODE=off` 새 세션)로 추가했다 — 추가 즉시 hot-reload된다. (출처: `strategic-compact` skill의 stderr-only 로직을 `run_handler` fail-open 계약으로 포팅. 결정 이력은 `hooks/README.md` 참조.)

`learning_log`은 첫 **PostToolUse** hook이다(예약돼 있던 ADR-0004 활성화 — gap #4). Bash 호출 직후 출력에서 강한 실패 신호만 골라 `learning_log.log`에 포착하고, `learnings-review` skill이 반복 항목을 CLAUDE.md 규칙/메모리로 **승격**한다(포착≠학습). advisory(항상 exit 0). off-ceremony로 `hooks/handlers/`·`hooks/launchers/`에 설치 + 로컬 `settings.json`의 `PostToolUse`에 등록 완료(2026-06-01). 새 머신은 `settings.json.template`의 `PostToolUse`로 자동 적용된다.

상세 발화 흐름·운영 모드·ceremony·패턴 추가법은 `hooks/README.md` 참조.

## MCP (외부 도구 연결)

MCP는 위 "작동 방식"의 4가지(①auto-load ②조건부 inject ③명시 호출 ④hook) 어디에도 안 들어가는 **별도 축 = tool layer**다. 외부 도구·데이터(문서 서버, 엔진 에디터 등)를 표준 프로토콜로 연결한다. 설정은 콘텐츠 레이어(L0–L5)와 무관하게 `~/.claude.json`(user scope) 또는 프로젝트 루트 `.mcp.json`(project scope)에 저장되며, **둘 다 토큰·절대경로를 포함해 git 제외**(project scope는 해당 프로젝트 repo에서 관리)다.

| scope | 적용 범위 | 저장 위치 | 예 | 등록 / 상세 |
|---|---|---|---|---|
| **user** | 모든 세션 (항상-on) | `~/.claude.json` | `context7` (버전별 최신 API 문서 → research-first §1.5 백킹) | 아래 설치 §6, `claude mcp add --scope user …` |
| **project** | 특정 프로젝트 (에디터 실행 전제) | `<프로젝트 루트>/.mcp.json` | UE/Unity 엔진 MCP (에디터 액터·BP·빌드·테스트 조작) | `templates/mcp.json` 복사 + `templates/README.md` "엔진 MCP 등록" / UE 구체 walkthrough는 `MCP-UNREAL-SETUP.md` |

**원칙**: 항상-on 원격 서버는 user scope, 특정 프로젝트·에디터에 묶이는 서버는 project scope. user scope에 엔진 MCP를 넣으면 다른 모든 세션에서 죽은 tool이 뜬다.

**사용**: 등록되면 해당 서버의 tool이 세션에 자동 노출되고, 자연어 요청 시 Claude가 호출한다. stdio 서버는 Claude Code가 세션 시작 시 직접 spawn하므로 별도 실행이 필요 없다(원격 HTTP 서버는 독립 실행 + URL 연결). `.mcp.json`은 **세션 시작 시점에 한 번** 읽히므로, 추가·수정 후엔 세션 재시작이 필요하다.

> ⚠️ **MCP는 hooks 안전망 밖이다.** `secret_scan`·`scope_check`은 Claude의 Edit/Write/Bash만 가로채므로, MCP가 에디터를 조작하거나 외부에 쓰는 동작은 검사되지 않는다. write 계열 MCP tool은 테스트 브랜치/사본에서 먼저 검증한다 (CLAUDE.md §5).

**runtime 인지**: 위 셋업/템플릿은 auto-load 밖이라, 엔진 MCP의 존재를 세션 중 에이전트가 인지하려면 always-on 진입점이 필요하다. `rules/agent-routing.md`의 "MCP-aware 라우팅" 절이 그 역할 — 엔진 MCP tool이 세션에 있을 때만 발동하는 conditional lane으로, text(specialist)/live(MCP) 분리와 read-only sweet spot을 규정한다.

## 설치 (새 PC)

1. 이 repo의 **Code → Download ZIP** 클릭
2. 압축을 풀고 내용을 `~/.claude/` 에 복사
   - Windows: `%USERPROFILE%\.claude\`
   - 기존 `~/.claude/`가 있으면 백업 후 복사
3. **Python 설치 확인** — hooks는 `py -3`로 핸들러를 실행하므로 Python이 필요하다. `py -3 --version`이 동작하지 않으면 [python.org](https://www.python.org/downloads/) 또는 `winget install Python.Python.3`로 설치한다 (공식 설치본에 `py` launcher 포함). Python이 없어도 hooks는 fail-open이라 작업을 막진 않지만 시크릿·스코프 검사 자체가 돌지 않는다.
4. `settings.json.template`을 `settings.json`으로 복사하고 `<USERNAME>`을 실제 Windows 사용자명으로 치환 — hook 등록이 여기서 켜진다. (`settings.json`은 절대경로가 박혀 machine-specific이라 git 제외)
5. Claude Code 재시작
6. **(선택) Context7 MCP** — `research-first`(CLAUDE.md §1.5)를 버전별 최신 API 문서로 강화한다. machine-specific이라 repo엔 없으니 새 머신마다 등록한다:
   ```
   claude mcp add --transport http --scope user context7 https://mcp.context7.com/mcp
   ```
   키 없이 동작하며(표준 rate limit), 더 높은 한도를 원하면 [context7.com/dashboard](https://context7.com/dashboard)에서 키를 발급받아 헤더로 추가한다(키는 본인 셸에서 직접 — 채팅/커밋에 노출 금지): `… https://mcp.context7.com/mcp --header "CONTEXT7_API_KEY: <key>"`. 등록은 `~/.claude.json`(user config, git 제외)에 저장된다.

## 동기화 방식

이 repo는 단순 백업이다. 로컬 `~/.claude/`를 직접 수정한 후, 의미 있는 변경은 주기적으로 GitHub 웹 UI를 통해 반영한다:

1. 변경된 파일을 GitHub repo의 해당 위치로 이동
2. "Add file → Upload files" 또는 "Edit this file"
3. Commit message 작성 후 commit

## Layer 구조

| Layer | 위치 | 출처 |
|---|---|---|
| L0 | `CLAUDE.md` | Karpathy 4원칙 + ECC research-first(§1.5) + 본인 워크플로우 |
| L1 | `agents/_core/`, `skills/` (generic) | ECC cherry-pick |
| L2 | `agents/_gamedev/` | Game Studios cherry-pick |
| L3 | `agents/_ue/`, `agents/_unity/` | Game Studios cherry-pick |
| L5 | `skills/ue-umg-review/`, `skills/harness-review/` 등 자작 skill (skills/ 직하) | 본인 자작 |

L4 (프로젝트 특화)는 이 repo에 포함되지 않는다. 각 프로젝트의 `.claude/`에 위치한다.

`hooks/`는 위 콘텐츠 레이어(L0–L5) 축과 별개인 런타임 enforcement 인프라다 — 본인 자작(ADR-0001 / ADR-0005). 상세는 위 "hooks" 절 및 `hooks/README.md` 참조.

`roles/`, `rules/_mode/`, 루트 `HANDOFF.md` / `RESULT.md` 역시 콘텐츠 레이어와 별개인 Two-CLI workflow 인프라다 (위 "구조" 절 참조).

**디렉터/리드 계층 비설치 — 조합 정합 모델.** Game Studios 원본의 Tier-1(creative/technical-director, producer)·Tier-2(lead-programmer, game-designer, art-director) 계층은 의도적으로 가져오지 않았다. **사람 + Architect 세션이 그 역할**(설계·아키텍처 결정·검토)을 한다. 이에 맞춰 ① specialist agent들의 보고·에스컬레이션 문구, ② gamedev skill의 `agent:` 바인딩(`code-review`→`code-reviewer`, `perf-profile`→`performance-analyst`), ③ skill·agent 본문의 명령/agent 참조가 모두 **실존 대상(사용자·Architect·설치된 agent)만** 가리키도록 정합돼 있다. 라우팅 진입 규칙은 `rules/agent-routing.md`. ECC 쪽도 같은 원칙으로 정리됐다 — research-first는 `CLAUDE.md §1.5`로 always-on 복원, 미설치 ECC skill·command·MCP를 가리키던 dangling 참조는 제거했다.

## 진화

- 같은 질문을 3번 이상 함 → skill로 박제
- 패턴이 반복됨 → review checklist에 추가
- 새 도메인 진입 → `skills/` 직하에 새 skill 시작 (하위 폴더는 스캔되지 않음 — `_personal/` 시절 3개 skill이 전부 휴면이었던 원인)

### 일몰 기준 (Sunset Criteria)

위 셋은 **추가** 기준이다. 짝이 되는 **제거** 기준이 없으면 구조는 단조 증가하고, skill/agent가 늘수록 인덱스·라우팅·유지보수 부담이 커진다. Harness engineering의 제1원칙 — *"모든 harness 부품은 모델이 혼자 못 하는 걸 메우려 존재하며, 모델이 좋아지면 불필요해진다"* — 을 이 구조 자체에 적용한 표다. 각 부품군이 **왜 존재하는지**와 **어떤 신호가 보이면 제거·축소를 검토하는지**를 명시한다. (출처: `awesome-harness-engineering`의 `HARNESS_CHECKLIST.md` "Removal Criteria Table". 본인의 `tech-debt`·`scope-check` 철학을 harness 자신에게 적용.)

이 표는 자동 삭제 트리거가 아니라 **주기적 점검용 lookup**이다. 제거 신호가 관찰되면 해당 부품을 dryrun으로 내리거나 description만 남기고 본문을 축소하는 식으로 단계적으로 sunset한다.

| 부품군 | 구성 | 왜 존재 (모델 한계) | 제거·축소 검토 신호 |
|---|---|---|---|
| 메타 원칙 skills | `simplicity-first`, `surgical-changes`, `think-before-coding`, `goal-driven-execution`, `search-first` | 모델이 과설계·범위이탈·추측·research 생략을 기본값으로 함 | base 모델이 prompting 없이도 최소·외과적·research-first를 기본으로 행동 → preload(`skills:` frontmatter) 먼저 해제, 그 다음 skill 본문 축소 |
| 컨텍스트·검증 skills | `verification-loop`, `eval-harness`, `strategic-compact`, `iterative-retrieval`, `scope-check`, `perf-profile`, `tech-debt` | 유한 context window + 내장 검증/압축 부재 | context가 사실상 무한 + 하네스가 검증·압축을 자동 수행 → 해당 skill 우선 일몰 |
| Engine specialist agents | `agents/_ue/*`, `agents/_unity/*` | 모델이 현행 버전 UE5/Unity API를 hallucination 없이 신뢰성 있게 모름 | base 모델이 타깃 엔진 버전 API를 안정적으로 정확히 다룸 → 허브만 남기고 하위 specialist 축소 |
| Domain agents | `agents/_gamedev/*`, `agents/_core/*` | 멀티도메인 대형 작업이 단일 context를 오염시킴 (token economy·역할 분리) | 단일 context가 대형 다영역 작업을 오염 없이 처리 → Task 위임 라우팅 축소 |
| Two-CLI workflow infra | `roles/`, 루트 `HANDOFF.md`/`RESULT.md`, `rules/_mode/` | 단일 세션이 깊은 설계+구현을 plan drift 없이 동시 보유 못 함 | 한 세션이 설계+구현 전체를 plan 손실 없이 보유 → 모드 분리 해제 |
| Orchestration rules | `rules/agent-routing.md` | 모델이 적합한 specialist topology를 자동 선택 못 함 | 모델이 최적 sub-agent 조합을 self-route → 라우팅 규칙 축소 |
| hooks (enforcement) | `secret_scan`, `scope_check`, `suggest_compact`, `learning_log` | 결정론적 안전망을 모델이 self-guarantee 못 함 | 부품별 개별 판정: 모델이 시크릿을 절대 방출 안 함→`secret_scan`, 범위를 절대 안 벗어남→`scope_check`, auto-compaction 신뢰→`suggest_compact`, 학습을 self-persist→`learning_log`. (단 `scope_check`는 always-block layer 가치가 모델 개선과 무관하므로 dryrun 영구 유지 — 위 "hooks" 절 참조) |

### 주요 변경 이력

세부 변경은 git log에 있다. 아래는 milestone 수준 요약이다.

**2026-06-16 — `harness-review` skill 추가 (2번째 L5 자작).** harness 구조(agents·skills·hooks·rules·CLAUDE.md) 자체의 배선 정합을 점검하는 전용 skill을 추가했다. 반복적으로 수행하던 구조 리뷰를 9개 카탈로그(Skill 배선·`skills:` preload 정합·`agent:` 바인딩·skill↔agent 중복/미연결·dangling 참조·휴면 skill·sync 부채·hook 무결성·일몰 대조)로 고정하고, DIAGNOSE(heavy-read는 Task→Explore 위임)→PROPOSE→APPROVE(게이트)→APPLY→REPORT 흐름으로 박제했다. user-invocable(`/harness-review`)이며, "승인 후 적용"이 메인 세션에서 일어나야 하므로 `context: fork`는 쓰지 않고 heavy-read만 격리한다. `arch-review`(소스 코드 SOLID/품질)와 구분되는 harness 전용 리뷰. always-block 인프라 파일은 자동 수정 대상에서 제외(수동 안내). (출처: 이 README '진화' 절의 "같은 질문 3번 이상 → skill로 박제" 규칙 — 반복된 구조 리뷰 요청을 crystallize.)

**2026-06-09 — 언리얼 MCP runtime-통합.** 엔진 MCP가 문서·템플릿(MCP-UNREAL-SETUP.md, README MCP 절, templates/mcp.json)으로만 존재해 auto-load 밖이라 세션 중 에이전트가 인지 못 하던 gap을, always-on `rules/agent-routing.md`에 "MCP-aware 라우팅" conditional 절로 통합했다. 엔진 MCP tool이 세션에 노출됐을 때만 발동하며, MCP-UNREAL-SETUP.md §7의 text(specialist)/live(MCP) 분리 원칙을 라우팅 규칙으로 승격한다(specialist `tools:` 무변경 — §7 보존). 보조로 `unreal-specialist`에 "MCP 직접 호출 금지" 포인터 1불릿, `search-first`에 UE5 doc-lookup(`lookup_docs`/`lookup_class`) 한 줄을 더했다. footprint=최소, CLAUDE.md/ROLE/settings 무변경. (출처: 사용자 요청 — 최근 mcp-unreal 셋업의 runtime 통합.)

**2026-06-07 (후속4) — `MCP-UNREAL-SETUP.md` 추가.** 루트 README의 MCP 절은 thin pointer라 엔진 MCP 상세가 생략돼 있던 걸, UE 5.7 + remiphilippe/mcp-unreal 실셋업 walkthrough(아키텍처 2-연결, 플러그인 빌드, RC API web server, 포트 검증, project-scope `.mcp.json`, 트러블슈팅 4종, 보안)로 별도 문서화했다. 루트 README MCP 절·구조 트리·`templates/README.md`에서 가리킨다(중복 없이 detail만 분리).

**2026-06-07 (후속3) — 루트 README에 MCP 통합 절 추가.** MCP 설정법이 설치 §6(context7)과 `templates/README.md`(엔진 MCP)에 흩어져 있던 걸, 루트 README에 "MCP (외부 도구 연결)" 통합 절로 묶었다 — tool layer가 활성화 4가지 밖의 별도 축임을 명시하고, user/project scope 구분·저장 위치·git 제외·세션 재시작 조건·hooks 안전망 밖 경고를 한 표로 정리하되 상세는 기존 두 위치를 가리킨다(중복 없음).

**2026-06-07 (후속2) — 엔진 MCP 등록 템플릿 추가.** UE(현 작업, 5.7)/Unity 엔진 MCP를 프로젝트마다 copy-paste로 등록하도록 `templates/mcp.json`(project-root `.mcp.json` 템플릿)과 등록 레시피(`templates/README.md`)를 추가했다. 엔진 MCP는 에디터 플러그인 ↔ 서버 2-파트 브릿지라 에디터 실행이 전제이고, 특정 프로젝트에 묶이므로 user scope(context7)와 달리 **project scope**로 둔다. 권장 기본: UE 5.7 → remiphilippe/mcp-unreal, Unity → CoplayDev/unity-mcp(템플릿은 server-agnostic). **주의**: MCP의 에디터 조작은 `scope_check`·`secret_scan` hook 밖이라 안전망이 없다 — 레시피에 명시. (출처: 사용자 요청 — `.claude` repo의 MCP 등록 용이화.)

**2026-06-07 (후속) — cross-tool `AGENTS.md` 템플릿 추가.** Codex/Gemini CLI 등 Claude 외 도구 병행 환경을 위해 project-root용 `templates/AGENTS.md`를 추가했다. AGENTS.md 표준은 작업 디렉터리 루트에서 읽히고 다른 도구는 `CLAUDE.md`를 자동 로드하지 않으므로, 이 템플릿이 `CLAUDE.md §1` 메타 원칙만 tool-neutral하게 inline으로 전달하고 나머지는 `./CLAUDE.md`를 읽도록 지시한다(중복 없는 cross-tool 베이스라인). 다른 템플릿과 달리 `docs/`가 아닌 **프로젝트 루트**로 복사한다. (출처: `awesome-harness-engineering`의 `templates/AGENTS.md` 구조를 본인 Two-CLI·engine-version-safety·self-review 워크플로우에 맞춰 적응.)

**2026-06-07 — 일몰 기준(Sunset Criteria) 도입.** 구조가 추가 기준만 갖고 제거 기준이 없어 단조 증가하던 문제를 보강했다. `awesome-harness-engineering`의 `HARNESS_CHECKLIST.md` "Removal Criteria Table"을 분석해, 7개 부품군별로 "왜 존재(모델 한계) + 제거·축소 검토 신호"를 README "진화" 절에 중앙 테이블로 추가했다. 40여 개 파일에 개별 sunset note를 산포하는 대안 대신, 제거 조건이 부품군별로 공유된다는 점·`simplicity-first` 원칙에 따라 중앙 1곳(lookup-only, auto-load 밖)에 집약했다. (출처: harness engineering 제1원칙을 본인 `tech-debt`·`scope-check` 철학으로 자기 구조에 적용.)

**2026-06-01 (후속) — skill 활성화 메커니즘 강화 (preload + fork 격리).** Claude Code의 두 메커니즘(`skills:` frontmatter preload, skill `context: fork`)을 검증한 뒤 채택해, 원칙 적재와 컨텍스트 격리를 강화했다. (출처: "A mental model for Claude Code skills, subagents, and plugins" — Dean Blank 검토 → 실재·syntax 검증된 둘만 선별 채택. 커밋 `0025716`·`ef5cbec`.)

- **메타 원칙 preload** — 코드 작성 agent 17개(`_core` 2·`_gamedev` 5·`_ue` 5·`_unity` 5)에 `skills: [simplicity-first, surgical-changes]` 추가. §1.2·§1.3 원칙을 auto-trigger 인식 의존이 아닌 **시작 시점 보장**으로 전환. reviewer/architect/planner는 코드 작성 권한이 없어 제외, `search-first`는 자체적으로 research subagent를 spawn(1-level nesting 충돌)하므로 제외.
- **분석 skill fork 격리** — `scope-check`→`context: fork`+`agent: Explore`(CLAUDE.md 불필요한 read-only), `perf-profile`→`context: fork`(기존 `agent: performance-analyst` 유지 — CLAUDE.md §4 frame-budget 컨텍스트 보존). heavy-read가 메인 세션 context를 오염시키지 않게 분리.

**2026-06-01 — 3-소스 조합 정합 + gap 보강.** Karpathy·ECC·Game Studios 조합이 의도대로 동작하는지 점검하고, 구조 전체를 비설치 모델로 맞춘 뒤 소스 대비 gap을 보강했다:

- **비설치 모델 정합** — Game Studios의 director/lead tier 미설치 전제를 모든 specialist agent·gamedev skill에 반영. 유령 상급자/미설치 명령 참조 제거, gamedev skill `agent:` 바인딩을 실존 agent로 수정(`code-review`→`code-reviewer`). 라우팅 진입 규칙 `rules/agent-routing.md` 추가.
- **ECC research-first 복원** — `CLAUDE.md §1.5` always-on 복원 + 미설치 ECC skill·MCP·command를 가리키던 dangling pointer 정리.
- **프로젝트 컨벤션 템플릿** — `templates/`에 엔진 `VERSION.md`·ADR 추가(agent가 참조하던 `docs/engine-reference`·`docs/architecture` 구현). research-first 백킹용 Context7 MCP 등록.
- **워크플로우 skill cherry-pick** — `scope-check`·`hotfix`·`changelog`(Game Studios), 엔진 인식 `codebase-onboarding`(ECC). 전부 비설치 모델로 적응.
- **학습 persistence** — 첫 PostToolUse hook `learning_log`(Bash 실패 포착) + `learnings-review` skill(CLAUDE.md 승격). 예약돼 있던 ADR-0004 활성화.
- **Karpathy 효과 확인 신호** — `CLAUDE.md §1`에 관찰 가능한 self-audit 추가.
