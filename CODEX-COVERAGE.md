# CODEX-COVERAGE — Cycle 2

codex 타깃 설치의 콘텐츠 회계. 각 콘텐츠 타입을 **native / degraded / dropped**로 분류하고
Codex 표현 위치 또는 drop 사유를 기록한다. **무음 소실 0**이 목표 — 모든 항목이 여기 명시된다.

검증 기준: HANDOFF Cycle 2 §4의 8개 결정(D1~D8) + `content/skills/` 24개 전부 회계.

## 1. 매핑 회계 (D1~D8)

| # | our content | Codex 처리 | 위치 / 사유 |
|---|---|---|---|
| **D1** | `content/instructions/CLAUDE.md` | **native** (curated) | `assets/codex/AGENTS.md` → `~/.codex/AGENTS.md`. §1·3·4·5 keep, §2(Two-CLI) strip, §6 체크리스트만, §7 AGENTS framing. 6675 B (≤32 KiB) |
| **D2** | `content/rules/agent-routing.md` | **dropped** | Claude 서브에이전트 위임 라우팅 — Codex에 Task/subagent exec 부재. 인용 없이 drop |
| **D3** | `content/agents/**` (21) | **dropped** | Codex native subagent 실행 메커니즘 없음 (전체 목록 §3) |
| **D4** | `assets/claude/hooks/**` | **dropped** + 안전노트 | enforcement 부재. AGENTS.md 안전노트(§4)로 advisory 명시 + 본 문서 회계 |
| **D5** | MCP (config.toml `[mcp_servers]`) | **out of scope** | 변환할 canonical source 없음 (`content/templates/mcp.json`은 `<FILL IN>` 스텁). adapter 미생성. AGENTS.md 안전노트에 "머신별 수동 등록" 1줄 |
| **D6** | `content/roles/**` (2) + `content/rules/_mode/**` (2) | **dropped** | Two-CLI는 Claude 세션 관례; `_mode`는 Claude 조건부 inject(paths 매칭) — Codex 대응 기제 없음 (§3) |
| **D7** | `content/templates/`·`ecc-reference/`·`docs/` | **native-copy** | `~/.codex/{templates,ecc-reference,docs}/` verbatim. inert reference(auto-load 아님). templates/mcp.json 스텁도 inert 동봉 |
| **D8** | `content/skills/*` (24) | **8 clean + 9 degraded copy / 7 dropped** | §2 상세 |

> **※ 2026-06 재-recon 정정 (D3·D4·D6 — §1 매트릭스 및 §3 dropped 인벤토리 공통; 0.140 갱신):** 위 "Codex native subagent 실행 메커니즘 없음"(D3)·"enforcement 부재"(D4)·"Codex 대응 기제 없음"(D6) 및 §3의 "Codex subagent exec 부재"·"Codex hook 부재" 류는 **Cycle 2 build-time(Codex 0.111.0) 기준**이며 *현 adapter의 상태 서술*로만 유효하다(영구 불가 아님). 현행 Codex(**`0.140.0`**)는 hooks·subagents가 stable이고 **subagent orchestration(spawn→wait→synthesise, `max_depth=1`)이 hub→leaf 위임을 지원** → **hooks·agents(hub-leaf 포함)는 포팅 가능**(현 adapter는 아직 미포팅, adapter v2 대기). still-dropped = `_mode` file-glob·Two-CLI 세션페어·**depth-2 다중hop**·routing 별칭. 상세·실행 플랜 = `CODEX-RECON.md` "2026-06 재-recon 갱신" + **"Porting Plan"**.

## 2. skills 회계 (24 = 8 native + 9 degraded + 7 dropped)

설치됨 = **17** (clean 8 + degraded 9). 미설치 = **7** (dropped).

### COPY — clean native (8)
Claude-machinery 마커 없음(정밀 grep 0건). Codex에서 그대로 동작:
`eval-harness`, `goal-driven-execution`, `simplicity-first`, `surgical-changes`, `tech-debt`, `think-before-coding`, `ue-umg-review`, `verification-loop`

> **Open Q2 해소**: HANDOFF가 `ue-umg-review`를 degraded 예시로 들었으나, 실제 스캔 결과 `agent:`/`Task`/`specialist`/`~/.claude` 마커 **0건** → **clean**으로 분류(UMG 도메인 지식은 portable, Claude-tool 결합 없음). HANDOFF 가정이 미성립.

### COPY — degraded (9)
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

> degraded는 **drop이 아님** — skill 본문 절차는 Codex에서도 유효하며, Claude 전용 위임 지시만 무시된다.

### DROP (7)
core function이 Claude-harness 기제라 설치 제외(`harness.toml [targets.codex].skills_drop`):

| skill | drop 사유 |
|---|---|
| `bp` | `agent: ue-blueprint-specialist` `context: fork` — Claude 서브에이전트 라우팅 별칭 |
| `gas` | `agent: ue-gas-specialist` 라우팅 별칭 |
| `umg` | `agent: ue-umg-specialist` 라우팅 별칭 |
| `ue` | `agent: unreal-specialist` 허브 라우팅 + Task fan-out |
| `repl` | `agent: ue-replication-specialist` 라우팅 별칭 |
| `harness-review` | `~/.claude/` 배선 감사 — Claude 하네스 전용 |
| `learnings-review` | `learning_log` hook 산출물 → CLAUDE.md 승격 — Claude hook 전용 |

## 3. dropped 인벤토리 (무음 소실 0)

| 항목 | 수 | 사유 |
|---|---|---|
| `rules/agent-routing.md` (D2) | 1 | Claude subagent 라우팅 |
| `agents/` (D3) | 21 | `_core` 6 (architect·code-reviewer·cpp-build-resolver·cpp-reviewer·planner·tdd-guide), `_gamedev` 5 (gameplay·network·performance-analyst·tools·ui-programmer), `_ue` 5 (ue-blueprint·ue-gas·ue-replication·ue-umg·unreal-specialist), `_unity` 5 (addressables·dots·shader·ui·unity-specialist). Codex subagent exec 부재 |
| `assets/claude/hooks/` (D4) | 1 tree | handlers·launchers·lib·rules·tests·README. Codex hook 부재 |
| `roles/` (D6) | 2 | ROLE_ARCHITECT·ROLE_BUILDER (Two-CLI 관례) |
| `rules/_mode/` (D6) | 2 | architect·builder (조건부 inject 기제 부재) |
| `settings.json(.template)` | — | hooks/permissions 설정 — Codex `config.toml`에 대응 개념 없음(D4 인접) |
| skills (D8) | 7 | §2 DROP 표 |

`content/` 중 codex 미반영 항목은 위가 전부. 그 외(instructions·skills 17·templates·ecc·docs)는 §1·§2에 설치로 회계됨.

## 4. hooks 안전 — 이중 위치 (D4)

enforcement 무음 상실 방지를 위해 두 곳에 명시:
1. **`~/.codex/AGENTS.md`** (설치본) 상단 "Codex 환경 안전 노트": `secret_scan`·`scope_check` enforcement는 Codex에서 작동 안 함 — secret/scope 보호는 advisory이며 사용자·Codex sandbox 책임.
2. **본 문서** §1 D4 + §3.

## 5. 검증 요약

- D1~D8 8개 매핑 전부 회계 ✓
- `content/skills/` 24개 전부 분류 (8 clean + 9 degraded + 7 drop) ✓
- dropped 인벤토리 enumerate, 무음 소실 0 ✓
- hooks 안전 AGENTS.md + 본 문서 양쪽 존재 ✓
