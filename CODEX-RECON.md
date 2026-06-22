# CODEX-RECON — Cycle 1 Gate 3

codex adapter feasibility recon + adopt-vs-build decision. Feeds Cycle 2 scope.

> **⚠️ 이 문서는 2개 시점이 섞여 있다.** 아래 "Method & evidence"~"Open Questions"는 **Cycle 1 (2026-06-16) build-time recon** — rulesync 산출물 + Codex **0.111.0** 실측 기준의 historical 기록이다. 그 본문의 "Codex has no hook system / no native subagent execution" 류 판정은 **그 시점·그 버전 기준**이며, 바로 아래 **"2026-06 재-recon 갱신"** 섹션이 현행 Codex 기준으로 이를 **정정·supersede**한다. Cycle 2 확정 ground-truth는 `CODEX-COVERAGE.md`.

## 2026-06 재-recon 갱신 (현행 Codex — supersedes 'Codex-can't' framing below)

> **0.140 더 깊은 조사 (직전 commit `00e1dfe`의 매트릭스를 supersede):** 직전 갱신이 hub-leaf를 STILL-DEGRADED로 본 것은 **부정확**했다. Codex `0.140.0`의 subagent **orchestration**(spawn→wait→synthesise, `max_depth=1`, `max_threads=6`, prompt-driven)이 hub→leaf를 **지원**한다(depth-1 fit). 정정값은 (c)·(d), 실행 플랜은 아래 "Porting Plan" 섹션.

**헤드라인: 메커니즘을 따라잡았고 시맨틱도 대부분 맞다 — 잔존 한계는 depth-2 다중hop·세션페어뿐.** 아래 Cycle-1 본문이 "Codex가 hooks/subagent를 못 한다"고 한 것은 **아키텍처 불가가 아니라 당시 버전(0.111.0) 기준의 미지원**이었다. 현행 Codex(`0.140.0`)는 hooks·subagents가 **stable**이고 orchestration이 hub→leaf를 커버한다.

> **추후 갱신 — 세션페어(Two-CLI) 한계는 해소됨:** 아래 매트릭스가 "Two-CLI roles STILL-DEGRADED — 세션페어 없음"이라 한 것은 codex *adapter* 한계였다. 이후 추가된 **cross-vendor orchestrator**(`orchestrate.py` + `orchestrator/`)가 세션페어링을 외부에서 관리해 이를 복원했다 — 각 "세션"은 controller가 만드는 headless 호출(`codex exec`/`claude -p`)이다. 기본 운용은 인터랙티브 Claude(Architect)가 Codex Builder를 `orchestrate.py build`로 headless 자동 dispatch하는 **single-pane** 모드. 상세 = `orchestrator/README.md`.

### (a) Codex 현행 native capability (0.140.0 기준)
- **hooks** — `~/.codex/hooks.json` / config.toml `[hooks]`. 이벤트: PreToolUse·PostToolUse·UserPromptSubmit·SessionStart·SubagentStart/Stop 등. stdin JSON, exit 0/2, `type:"command"` + `commandWindows`. UserPromptSubmit는 `hookSpecificOutput.additionalContext`(+ plain stdout)로 context 주입. → Claude hook contract와 거의 동형(`lib/common.py` 재사용 가능).
- **custom agents + orchestration** — `~/.codex/agents/*.toml`(name·description·developer_instructions + model·sandbox_mode·mcp_servers). parent가 child를 **spawn→route→wait→synthesise consolidated response**(spawn_agent/wait/close_agent). **`max_depth=1`**(root→직접 children; grandchildren 차단), **`max_threads=6`**, **prompt-driven**(모델이 프롬프트 보고 spawn — 호스트 API 아님), parent↔child만(peer 없음). → **hub→leaf 위임은 depth-1로 fit**(Claude hub-leaf 1-hop과 동형). 잔존 한계 = **depth-2 다중hop**(gameplay-programmer→unreal-specialist→ue-gas류).
- **rules** — AGENTS.md + nested override(cwd-dir) + profiles. (출처: developers.openai.com/codex + Codex 0.140 KB.)

### (b) 버전 선결조건
최신 = Codex **`0.140.0`**(2026-06-15, hooks·subagents **stable**, GPT-5.5). 사용자 설치 = **0.111.0**(`~/.codex`에 `agents/`·`hooks.json` 부재) → **업그레이드(무료, ≠결제) 시 전부 가용**. 포팅 = **codex adapter v2**(`codex.py` 확장)로 repo canonical → `~/.codex` 생성(source-of-truth 유지).

### (c) 포팅 feasibility 매트릭스 (0.140 정정)
| 부품 | 판정 |
|---|---|
| **hooks 5** | **GO** — 전부 NATIVE-PORTABLE(`secret_scan`·`scope_check`·`suggest_compact`·`learning_log`·`route_nudge`). contract 일치·`lib/common` 재사용·stdin 필드 교집합 |
| **agents 21** (_core·_gamedev·**hub-leaf 포함**) | **PORTABLE-WITH-CAVEAT** — orchestration이 hub→leaf 지원. caveat = depth-1·prompt-driven(developer_instructions에 spawn 규칙 enumerate) |
| **agent-routing** | **부분복원** — `route_nudge` hook이 specialist nudge 주입 |
| **`_mode` 조건부** | STILL-DEGRADED — file-glob → cwd-dir override만 |
| **Two-CLI roles** | STILL-DEGRADED — 세션페어 없음 |
| **depth-2 다중hop** | **STILL-DROPPED** — grandchildren 차단(`max_depth=1`) |
| **routing 별칭 skills**(bp/gas/umg/ue/repl) | 중복 — prompt-driven spawn이 대체 |

### (d) 권고 tier (0.140 정정)
- **GO**: hooks 5 (전부 native-portable).
- **PORTABLE-WITH-CAVEAT**: agents 대부분 — `_core`·`_gamedev` flat + **`_ue`·`_unity` hub-leaf**(depth-1 orchestration), learnings-review.
- **STILL-DROPPED**: `_mode` file-glob 조건부 · Two-CLI 세션페어 · **depth-2 다중hop** · routing 별칭 skills.

### (e) 미검증 → 3 해소, 1 잔존 (0.140 조사)
- ✅ route_nudge stdout→context (`UserPromptSubmit.hookSpecificOutput.additionalContext` + plain stdout 수용)
- ✅ config syntax (config.toml `[hooks]` / hooks.json)
- ✅ hub→leaf depth (depth-1 fit)
- ⚠️ **잔존 = depth-2 다중hop 위임**(grandchildren 차단) — 실 포팅 cycle preflight에서 우회 설계.

## Porting Plan (Codex ≥0.140 업그레이드 후 실행 — codex adapter v2)

> **※ Cycle 3 구현 갱신 (2026-06-19):** 아래 Phase A(hooks)·Phase B(agents)가 `adapters/codex.py` v2로 **구현·로컬 검증**됨(Codex `0.141`). 산출물·검증·잔존 = `CODEX-COVERAGE.md` "Cycle 3 / adapter v2" 노트. **Preflight 완료**(증거 = `CODEX-COVERAGE.md` §6): hooks.json 스키마 native 일치 ✓ / 편집 tool = `apply_patch`(`tool_input.command` 패치) → 핸들러 배선·검증 완료 ✓ / hub→leaf depth-1 동작·depth-2 차단 ✓ / skill 경로 `~/.codex/skills` 유효 ✓. **핵심 정정**: Codex 0.141은 PreToolUse exit-2로 `apply_patch`를 hard block하지 않음 → 포팅 hooks는 **advisory**(hard enforce = sandbox/approval 레이어). **남은 후속**: Phase C(route_nudge Codex 표현)·env 이름(`CLAUDE_*`) Codex 정리·(원하면) approval-layer enforce.

> 실행 = **별도 cycle**(이 플랜이 그 HANDOFF의 기반). 본 cycle은 플랜 기록만.

**선결**: 사용자 Codex 0.111.0 → **≥0.140 업그레이드**(무료). 포팅은 hand-edit 아니라 **codex adapter v2(`codex.py` 확장)**로 repo canonical → `~/.codex` 생성(source-of-truth 유지).

**Preflight (업그레이드 직후 실증 → 최종 scope 확정)**:
1. hook 발화 — PreToolUse `exit 2` block, UserPromptSubmit `additionalContext` 렌더.
2. hub→leaf — prompt-driven spawn→wait→synthesise 실동작(depth-1).
3. depth-2 차단 확인 — grandchildren 거부.

**Phase A — hooks (GO)**: `assets/claude/hooks/handlers/*.py` + `lib/common.py` + `rules/*.json` → `~/.codex/hooks/`; `codex.py`가 `~/.codex/config.toml [hooks]`(or hooks.json) 등록 생성(matcher per hook·`commandWindows`). 이벤트 매핑 PreToolUse/PostToolUse/UserPromptSubmit. stdin 필드 교집합이라 핸들러 거의 무변경(검증). 비파괴+백업.

**Phase B — agents (PORTABLE-WITH-CAVEAT)**: `content/agents/**.md` → `~/.codex/agents/*.toml`(body→developer_instructions·model·sandbox_mode·mcp_servers). hub agent는 developer_instructions에 "언제 어떤 leaf를 spawn"을 enumerate(prompt-driven, depth-1).

**Phase C — routing 부분복원**: Phase A의 `route_nudge`가 specialist nudge 주입(agent-routing 대체).

**Still-dropped (미포팅·문서화)**: `_mode` file-glob 조건부 · Two-CLI 세션페어 · **depth-2 다중hop** · routing 별칭 skills.

---

_(이하 Cycle 1 build-time recon — Codex 0.111.0·rulesync 기준 historical. 위 "2026-06 재-recon 갱신"이 현행 기준으로 정정함.)_

## Method & evidence

Grounded in three primary sources (not docs alone):

1. **Live `~/.codex` inspection** (read-only) — the user already runs OpenAI Codex CLI
   (`codex` on PATH, `~/.codex/` populated). Ground truth for Codex's real structure.
2. **Codex docs** — developers.openai.com/codex (AGENTS.md discovery, config.toml).
3. **rulesync v8.28.1 actual run** — `npx rulesync@latest init && generate --targets codexcli`
   in a scratch dir; inspected the emitted files. Not docs — observed output.

## Codex native structure (ground truth)

| Concept | Codex native location | Notes |
|---|---|---|
| global instructions | `~/.codex/AGENTS.override.md` → `~/.codex/AGENTS.md` (first non-empty) | 32 KiB combined cap (`project_doc_max_bytes`); one file per dir |
| path-scoped instructions | nested `<dir>/AGENTS.override.md` | **cwd-directory** scoped (active when working under that dir) |
| skills | `~/.codex/skills/<name>/SKILL.md` (+ optional `agents/openai.yaml`) | **same Agent-Skills frontmatter as Claude** (`name`/`description`/`metadata`); `.system/` = built-ins |
| config | `~/.codex/config.toml` | `model`, `personality`, `[projects.*]` trust, `[features]`, `[mcp_servers.*]` |
| MCP servers | `~/.codex/config.toml` `[mcp_servers.*]` | native |
| memory | `~/.codex/memories/` | native (Claude-memory analog) |
| subagents | — | **no native subagent execution** (no `agents/` dir) |
| hooks | — | **no hook system** (config.toml has no hook events) |

## rulesync `codexcli` output (observed, scratch run)

| feature | emitted path | native? |
|---|---|---|
| rules | `AGENTS.md` (all `.rulesync/rules/*.md` concatenated) | native (but merges → loses per-file structure, 32 KiB cap) |
| mcp | `.codex/config.toml` `[mcp_servers.*]` | native |
| subagents | `.codex/agents/<name>.toml` (`--simulate-subagents`) | **simulated** — Codex has no native subagent exec; live `~/.codex` has no `agents/` |
| skills | `.agents/skills/<name>/SKILL.md` (`--simulate-skills`) | **simulated to a divergent path** — NOT Codex's native `~/.codex/skills/` |
| commands | simulated (`--simulate-commands`) | simulated |
| hooks | not generated (no `--simulate-hooks`) | **dropped** |

Decisive: for `codexcli`, rulesync marks subagents/skills/commands as **simulated**, and emits
skills to `.agents/skills/` — which does **not** match the live Codex native `~/.codex/skills/`.
rulesync's codex skill model lags Codex's actual native Agent-Skills support.

## Coverage / gap matrix — our content types → Codex

| our content (`content/…`, `assets/claude/…`) | Codex target | verdict |
|---|---|---|
| `instructions/CLAUDE.md` | `~/.codex/AGENTS.md` (concat) | **native** (watch 32 KiB cap) |
| `rules/agent-routing.md` (always-on) | merged into `AGENTS.md` | **degraded** (no standalone always-on rule file; concat only) |
| `rules/_mode/{architect,builder}.md` (Claude `paths:` glob) | nested `AGENTS.override.md` | **degraded** (cwd-dir scope ≠ Claude file-glob on read/edit of HANDOFF/RESULT) |
| `skills/*/SKILL.md` | `~/.codex/skills/<name>/` | **native** (frontmatter already matches; near-verbatim copy) |
| `agents/**` (subagents) | — | **dropped / degraded** (no native exec; best-effort = describe roster in AGENTS.md) |
| `roles/` (Two-CLI ROLE files) | `AGENTS.md` section or a skill | **degraded** (Two-CLI is a Claude-session convention; fold to text) |
| `templates/`, `ecc-reference/` | plain files under `~/.codex/` | **native-copy** (no semantics; copy verbatim) |
| `assets/claude/hooks/**` | — | **dropped** (no enforcement; safety intent → advisory text in AGENTS.md at best) |
| `settings.json` (hooks+permissions) | `config.toml` (model/mcp/sandbox only) | **dropped** (hook/permission enforcement absent; only MCP maps) |
| MCP (`templates/mcp.json`) | `config.toml` `[mcp_servers.*]` | **native** |

Native: instructions, skills, MCP, templates/ecc copy. Degraded: rules-merge, `_mode`
conditional, roles, subagents. Dropped: hooks, permission enforcement.

## Recommendation — **BUILD** (`adapters/codex.py`, stdlib, mirrors `claude.py`)

Do **not** adopt rulesync. Build a Python codex adapter in the same shape as the claude adapter.

**Rationale**
1. **Fidelity** — rulesync *simulates* the highest-value transforms to non-native paths
   (skills → `.agents/skills/`, subagents → `.codex/agents/`), diverging from the live Codex
   structure. Our own adapter targets Codex's **real** native paths — and skills become a
   near-verbatim copy because the SKILL.md frontmatter is already identical.
2. **Toolchain consistency** — `claude.py` is stdlib-only, zero-dep, dispatched by `install.py`.
   `codex.py` mirroring it keeps one input (`content/`), one CLI, one mental model. Adopting
   rulesync injects a Node/TS dependency and a second canonical format (`.rulesync/`) we'd have
   to convert our `content/` into — a double transform.
3. **Churn insulation** — rulesync: 249 releases, `geminicli` retiring 2026-06-18 (2 days out),
   `antigravity` deprecated. Coupling a durable source-of-truth to a tool that retires targets
   weekly is a liability. Our adapter has zero external surface.
4. **rulesync's real value-add is small** — only rules→AGENTS.md concat and MCP→config.toml are
   genuinely native, ~30 lines of Python each. The hard parts (subagents/hooks) it simulates
   badly or drops — exactly the calls we must hand-make regardless.

**Reserve clause** — if Cycle ≥3 needs *many* targets (cursor/copilot/cline/windsurf), rulesync's
breadth changes the math; revisit then. For a single codex target mirroring claude, build wins.

## Cycle 2 gate proposal

- **C2-G1** — `adapters/codex.py` (stdlib). Map: `instructions/CLAUDE.md` (+ `rules/agent-routing.md`)
  → `~/.codex/AGENTS.md` (concat, 32 KiB guard); `skills/*` → `~/.codex/skills/*` (verbatim,
  optional `openai.yaml`); `templates/`+`ecc-reference/` → copy; MCP → `config.toml` merge.
  Explicit decisions for the degraded/dropped set: subagents (roster note in AGENTS.md vs drop),
  hooks (advisory safety text vs drop), roles (AGENTS section vs skill), `_mode` (nested
  `AGENTS.override.md` vs always-on note). Add `targets.codex` block to `harness.toml`.
- **C2-G2** — install to **scratch** `~/.codex`; fidelity check by **coverage criteria** (not
  diff-0 — codex is a transform, not a copy): every native item present & discoverable; every
  degraded item has a defined representation; every dropped item logged.
- **C2-G3** — decide real-target deploy (the deferred Cycle-1 non-goal): overwrite real
  `~/.codex` and/or real `~/.claude` under explicit approval, with backups.

## Open Questions (§7) — answered

| question | answer (evidence) |
|---|---|
| rulesync Codex target id | **`codexcli`** (CLI `--targets`) |
| rulesync codex output paths | `AGENTS.md`, `.codex/config.toml`, `.codex/agents/*.toml` (sim subagents), `.agents/skills/` (sim skills) — observed run |
| Codex skills discover location | **`~/.codex/skills/<name>/SKILL.md`** native; frontmatter = `name`/`description`/`metadata` (live `~/.codex/skills/.system/*`) |
| Codex hooks emit | **none** — no hook system in config.toml; rulesync emits no hooks for codex → dropped |
| `rules/_mode` paths preservation | partial — nested `AGENTS.override.md` is **cwd-dir** scoped, not Claude file-glob `paths:` → degraded |

All Cycle-1 Open Questions resolved with primary evidence; none deferred as unresolved.
