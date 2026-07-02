# CODEX-COVERAGE — Cycle 2

codex 타깃 설치의 콘텐츠 회계. 각 콘텐츠 타입을 **native / degraded / dropped**로 분류하고
Codex 표현 위치 또는 drop 사유를 기록한다. **무음 소실 0**이 목표 — 모든 항목이 여기 명시된다.

검증 기준: HANDOFF Cycle 2 §4의 8개 결정(D1~D8) + `content/skills/` 26개 전부 회계.

## 1. 매핑 회계 (D1~D8)

| # | our content | Codex 처리 | 위치 / 사유 |
|---|---|---|---|
| **D1** | `content/instructions/CLAUDE.md` | **native** (curated) | `assets/codex/AGENTS.md` → `~/.codex/AGENTS.md`. §1·3·4·5 keep, **§2(Two-CLI) → cross-vendor 역할 모드로 curate(AGENTS.md §7)**, §6 체크리스트만, §7 AGENTS framing. 10590 B (≤32 KiB) |
| **D2** | `content/rules/agent-routing.md` | **dropped** | Claude 서브에이전트 위임 라우팅 — Codex에 Task/subagent exec 부재. 인용 없이 drop |
| **D3** | `content/agents/**` (13 — 2026-07-02 leaf 8 강등 전 21) | **native** (adapter v2, Cycle 3) | `adapters/codex.py`가 전수를 `~/.codex/agents/*.toml`(name·description·developer_instructions)로 변환 (아래 Cycle 3 노트·전체 목록 §3). leaf 8개는 `content/docs/specialists/`로 이동 → D7 docs 경로로 native-copy |
| **D4** | `assets/claude/hooks/**` | **native** (adapter v2, Cycle 3) + 안전노트 | handlers·lib·rules → `~/.codex/hooks/` + `hooks.json` 자동생성(5 hook, 직접 Python 호출). launchers·tests·settings 제외. 잔존 리스크(apply_patch)=아래 Cycle 3 노트 |
| **D5** | MCP (config.toml `[mcp_servers]`) | **out of scope** | 변환할 canonical source 없음 (`content/templates/mcp.json`은 `<FILL IN>` 스텁). adapter 미생성. AGENTS.md 안전노트에 "머신별 수동 등록" 1줄 |
| **D6** | `content/roles/**` (2) + `content/rules/_mode/**` (2) | **roles: native-curate / `_mode`: dropped** | `ROLE_ARCHITECT`·`ROLE_BUILDER` 양 역할 프로토콜을 AGENTS.md §7(cross-vendor Two-CLI, 양방향)로 curate. `rules/_mode/`(2)만 dropped — Codex엔 paths-매칭 조건부 inject 기제 없음 → 모드 명시 선언 진입 (§3) |
| **D7** | `content/templates/`·`ecc-reference/`·`docs/` | **native-copy** | `~/.codex/{templates,ecc-reference,docs}/` verbatim. inert reference(auto-load 아님). templates/mcp.json 스텁도 inert 동봉 |
| **D8** | `content/skills/*` (26) | **8 clean + 10 degraded copy / 8 dropped** | §2 상세. 2026-07-02: 라우팅 별칭 4종(`bp`·`gas`·`umg`·`repl`)의 `agent:`가 leaf → `unreal-specialist` 허브로 재바인딩됐으나 여전히 Claude 라우팅 기제라 drop 유지 |

> **※ 2026-06 재-recon 정정 (D3·D4·D6 — §1 매트릭스 및 §3 dropped 인벤토리 공통; 0.140 갱신):** 위 "Codex native subagent 실행 메커니즘 없음"(D3)·"enforcement 부재"(D4)·"Codex 대응 기제 없음"(D6) 및 §3의 "Codex subagent exec 부재"·"Codex hook 부재" 류는 **Cycle 2 build-time(Codex 0.111.0) 기준**이며 *현 adapter의 상태 서술*로만 유효하다(영구 불가 아님). 현행 Codex(**`0.140.0`**)는 hooks·subagents가 stable이고 **subagent orchestration(spawn→wait→synthesise, `max_depth=1`)이 hub→leaf 위임을 지원** → **hooks·agents(hub-leaf 포함)는 포팅 가능**(현 adapter는 아직 미포팅, adapter v2 대기). still-dropped = `_mode` file-glob(조건부 inject)·**depth-2 다중hop**·routing 별칭 (Two-CLI roles 자체는 2026-06-17 AGENTS.md §7로 cross-vendor curate — D1·D6). 상세·실행 플랜 = `CODEX-RECON.md` "2026-06 재-recon 갱신" + **"Porting Plan"**.

> **※ Cycle 3 / adapter v2 구현·검증 (2026-06-19) — 위 "adapter v2 대기" supersede:** Codex `0.141`(`codex features list`: hooks·multi_agent stable) 대상 `adapters/codex.py` v2가 **구현·로컬 검증**됐다. D3·D4가 이제 native다(위 표 갱신 반영). scratch install 검증 결과:
> - **agents(D3)**: 21개 → `~/.codex/agents/*.toml`, 전부 `tomllib` parse·body fidelity OK(예 `ue-gas-specialist` developer_instructions 7533자). 변환기는 Claude Task/subagent 언급의 Codex 번역 + depth-1(grandchildren 금지) preamble 부착.
> - **hooks(D4)**: `handlers·lib·rules·README` → `~/.codex/hooks/` + `~/.codex/hooks.json`(5 hook) 자동생성. command = `py -3 "<dest>/hooks/handlers/X.py"` **직접 호출**(Claude launcher 경유 0, `.claude` 참조 0, 전부 install target). `scope_check`는 install root(`~/.codex`)에 키잉 — always-block 정상 발화 실증(보호경로 Edit→exit 2).
> - **still-dropped**: `_mode` glob inject(Codex 대응 기제 없음). routing 별칭 skills·`adversarial-review`는 §2 drop 표.
> - **preflight 반영 (§6) + 배선**: ① **apply_patch 배선 — 완료·검증.** Codex 편집은 `tool_name=apply_patch` + `tool_input.command`(패치 envelope), Claude식 `file_path` 아님(§6.2). `lib/common.parse_apply_patch`(envelope → `[(path, +content)]`) 추가 + `secret_scan`·`scope_check`·`suggest_compact`의 `_TARGET_TOOLS`에 `apply_patch` 추가 + path/content 추출 분기. 실 캡처 payload로 단위·핸들러 검증(보호경로 apply_patch→**exit 2 block**, `+`content fake key→**secret block**, Claude Edit 무회귀). **enforce 기제 = native sandbox/approval (확정, PreToolUse exit-2 아님)**: 정상 세션(`permission_mode=default`) 재검증(§6.3)에서도 exit-2가 apply_patch를 막지 못함(초기 측정 2회는 confound: ① bypass 모드 ② 훅이 code 1로 관측 + auto-accept 디버그 하니스). Codex가 approval 기반이라 apply_patch의 hard block은 **file-change approval(`FileChangeRequestApprovalResponse`: accept/decline)·sandbox·permission profile**이지 PreToolUse 훅 veto가 아님 → **Codex 포팅 hooks는 advisory(발화·로그·warn, hard block 아님)로 확정**(§4·AGENTS.md). 배선은 advisory를 정확화하는 데 유효. 스키마 사실: PermissionRequest 출력은 `{"decision":"decline"}` 거부, bare `"decline"` 수용(§6.4). ② **route_nudge Claude 전제(미완)** — `Task tool`·`/gas`·`agent-routing.md` 참조 → custom-agent spawn 표현 재작성 필요. ③ **skill path(완화)** — §6.6: Codex 0.141이 `~/.codex/skills` **와** `~/.agents/skills` **둘 다** 발견 → 현 `~/.codex/skills` 유효. ④ **hooks.json 스키마(OK)** — §6.1: native와 일치, 수정 불요. ⑤ subagent depth-1 동작·depth-2 차단 확인(§6.5) → hub는 leaf 직접 spawn 평탄화(agent preamble 반영됨).

## 2. skills 회계 (26 = 8 native + 10 degraded + 8 dropped)

설치됨 = **18** (clean 8 + degraded 10). 미설치 = **8** (dropped).

### COPY — clean native (8)
Claude-machinery 마커 없음(정밀 grep 0건). Codex에서 그대로 동작:
`eval-harness`, `goal-driven-execution`, `simplicity-first`, `surgical-changes`, `tech-debt`, `think-before-coding`, `ue-umg-review`, `verification-loop`

> **Open Q2 해소**: HANDOFF가 `ue-umg-review`를 degraded 예시로 들었으나, 실제 스캔 결과 `agent:`/`Task`/`specialist`/`~/.claude` 마커 **0건** → **clean**으로 분류(UMG 도메인 지식은 portable, Claude-tool 결합 없음). HANDOFF 가정이 미성립.

### COPY — degraded (10)
verbatim 복사하되, **Claude-specific frontmatter/본문이 Codex에서 무시됨**. 핵심 절차는 portable, 위임/Task 부분만 inert:

| skill | degraded 사유 (inert on Codex) |
|---|---|
| `scope-check` | frontmatter `context: fork` / `agent: Explore` + HANDOFF.md 참조 |
| `arch-review` | `agent: code-reviewer` + 엔진 specialist를 Task로 spawn |
| `codebase-onboarding` | `allowed-tools: Task` + `unreal/unity-specialist` 위임 + `~/.claude/templates/` 경로 |
| `hotfix` | `allowed-tools: Task` + `subagent_type: code-reviewer` |
| `search-first` | general-purpose research **subagent** 호출 |
| `changelog` | frontmatter `context: |` + HANDOFF 참조 |
| `perf-profile` | frontmatter `context: fork` / `agent:` |
| `strategic-compact` | Claude 컨텍스트/세션 관리 참조 |
| `iterative-retrieval` | subagent-context 패턴(Task fan-out) 참조 |
| `autonomous-loop` | step 4 `adversarial-review` 패널(Task fan-out)이 inert. 루프(goal 계약→implement→verification-loop→self-correct→tier 게이트)·risk tier 로직은 portable; Codex는 deterministic 검증+사람 종단 검토로 폴백 |

> degraded는 **drop이 아님** — skill 본문 절차는 Codex에서도 유효하며, Claude 전용 위임 지시만 무시된다.

### DROP (8)
core function이 Claude-harness 기제라 설치 제외(`harness.toml [targets.codex].skills_drop`):

| skill | drop 사유 |
|---|---|
| `bp` | `agent: unreal-specialist` `context: fork` + `docs/specialists/ue-blueprint.md` 포커스 — Claude 서브에이전트 라우팅 별칭 (2026-07-02 leaf→허브 재바인딩) |
| `gas` | `agent: unreal-specialist` + `docs/specialists/ue-gas.md` 포커스 라우팅 별칭 (동상) |
| `umg` | `agent: unreal-specialist` + `docs/specialists/ue-umg.md` 포커스 라우팅 별칭 (동상) |
| `ue` | `agent: unreal-specialist` 허브 라우팅 (2026-07-02부터 Task fan-out 대신 docs/specialists Read) |
| `repl` | `agent: unreal-specialist` + `docs/specialists/ue-replication.md` 포커스 라우팅 별칭 (동상) |
| `harness-review` | `~/.claude/` 배선 감사 — Claude 하네스 전용 |
| `learnings-review` | `learning_log` hook 산출물 → CLAUDE.md 승격 — Claude hook 전용 |
| `adversarial-review` | 직교 축 다중 judge를 Task로 fan-out하는 패널 — Codex subagent exec 부재로 붕괴 |

## 3. dropped 인벤토리 (무음 소실 0)

| 항목 | 수 | 사유 |
|---|---|---|
| `rules/agent-routing.md` (D2) | 1 | Claude subagent 라우팅 |
| ~~`agents/` (D3)~~ | ~~21~~ | **Cycle 3에서 native로 이동** — `~/.codex/agents/*.toml` 21개 변환(§1 D3). 더 이상 dropped 아님 |
| `assets/claude/hooks/` launchers·tests (D4 일부) | 2 | `launchers/`(Claude `~/.claude` 경유 BAT)·`tests/`만 제외. **handlers·lib·rules·README는 Cycle 3에서 native 복사**(§1 D4) |
| `rules/_mode/` (D6) | 2 | architect·builder (조건부 inject 기제 부재 — 모드 명시 선언 진입). **roles/(2)는 drop 아님** — AGENTS.md §7로 cross-vendor curate(§1 D6) |
| `settings.json(.template)` | — | hooks/permissions 설정 — Codex `config.toml`에 대응 개념 없음(D4 인접) |
| skills (D8) | 8 | §2 DROP 표 |

`content/` 중 codex 미반영 항목은 위가 전부. 그 외(instructions·roles 2[AGENTS.md §7 curate]·skills 18·templates·ecc·docs)는 §1·§2에 설치로 회계됨.

## 4. hooks 안전 — 이중 위치 (D4)

enforcement 무음 상실 방지를 위해 두 곳에 명시:
1. **`~/.codex/AGENTS.md`** (설치본) 상단 "Codex 환경 안전 노트": 포팅된 `secret_scan`·`scope_check` 훅은 advisory(발화/warn)이며 PreToolUse exit-2로 hard block 못 함(verified, §6.3) — secret/scope 보호는 사용자 + Codex sandbox/approval 책임.
2. **본 문서** §1 D4 + §3.

## 5. 검증 요약

- D1~D8 8개 매핑 전부 회계 ✓
- `content/skills/` 26개 전부 분류 (8 clean + 10 degraded + 8 drop) ✓
- dropped 인벤토리 enumerate, 무음 소실 0 ✓
- hooks 안전 AGENTS.md + 본 문서 양쪽 존재 ✓

## 6. Preflight 증거 (consolidated)

> 2026-06-19 Codex `0.141.0` 런타임 실측. 구 `CODEX-PREFLIGHT.md`·`CODEX-PREFLIGHT-2.md`(일회성 검증 로그 2부작)를 본 절로 통합하고 두 standalone 문서는 제거했다. §1 D3·D4·§4의 결론이 이 증거에 기댄다. (verbatim raw payload 캡처는 git history에 남음.)

환경: `codex-cli 0.141.0`, `codex features list` → `hooks` stable·`multi_agent` stable. scratch install(`agents/*.toml` 21 + `hooks.json` + `hooks/{handlers,lib,rules}`) 성공.

1. **hooks.json 스키마 = native 일치** — adapter v2 생성 shape가 native 0.141과 일치(top-level `hooks` 키, event `PreToolUse`/`PostToolUse`/`UserPromptSubmit`, `matcher`+`hooks[]`, handler `type=command`/`command`/optional `timeout`·`commandWindows`). **JSON 스키마 수정 불요.**
2. **편집 tool payload contract** — Windows Codex 0.141의 파일 편집 hook payload는 `tool_name=apply_patch` + `tool_input.command`=패치 문자열(`*** Begin Patch … *** End Patch`)이다. Claude식 `tool_input.file_path`/`new_content`는 **없다**. → 핸들러는 apply_patch envelope를 파싱해야 한다(`lib/common.parse_apply_patch`). *(hook 핸들러 주석이 이 항목을 인용.)*
3. **PreToolUse exit-2 ≠ hard block** — 정상 `on-request`/`permission_mode=default` 세션에서 hook이 발화(`hook/started`)하고 종료해도 `apply_patch`가 그대로 적용된다(파일 변경 완료, hook은 `status=failed`/`exited with code 1`로만 기록). 즉 exit-2로 편집을 막지 못함 → **포팅 hooks는 advisory**. 실제 차단점 = file-change approval(`FileChangeRequestApprovalResponse`: accept/acceptForSession/decline/cancel)·sandbox·permission profile. *(초기 preflight의 block 결론은 `--dangerously-bypass-hook-trust`/`permission_mode=bypassPermissions`로 오염됐던 것을 정상 세션 재검증으로 정정.)*
4. **PermissionRequest 출력 스키마** — object `{"decision":"decline"}`는 invalid로 거부되고, bare JSON 문자열 `"decline"`은 수용된다. (단 테스트 app-server 경로는 downstream file-change 승인을 auto-accept해 user-visible deny는 미실증.)
5. **subagent depth** — depth-1 spawn 동작(`spawn_agent`→`wait`→child reply), depth-2 grandchild spawn은 차단(`agents.max_depth=1` 기본).
6. **skill path discovery** — 런타임이 `~/.codex/skills`와 `~/.agents/skills`를 **둘 다** 발견 → 현 `~/.codex/skills` 유효(매뉴얼의 `~/.agents/skills`-only 서술보다 최신).
