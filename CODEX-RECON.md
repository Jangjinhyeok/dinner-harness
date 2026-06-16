# CODEX-RECON — Cycle 1 Gate 3

codex adapter feasibility recon + adopt-vs-build decision. Feeds Cycle 2 scope.

> **⚠️ 이 문서는 2개 시점이 섞여 있다.** 아래 "Method & evidence"~"Open Questions"는 **Cycle 1 (2026-06-16) build-time recon** — rulesync 산출물 + Codex **0.111.0** 실측 기준의 historical 기록이다. 그 본문의 "Codex has no hook system / no native subagent execution" 류 판정은 **그 시점·그 버전 기준**이며, 바로 아래 **"2026-06 재-recon 갱신"** 섹션이 현행 Codex 기준으로 이를 **정정·supersede**한다. Cycle 2 확정 ground-truth는 `CODEX-COVERAGE.md`.

## 2026-06 재-recon 갱신 (현행 Codex — supersedes 'Codex-can't' framing below)

**헤드라인: 메커니즘은 따라잡았으나 시맨틱은 부분적.** 아래 Cycle-1 본문이 "Codex가 hooks/subagent를 못 한다"고 한 것은 **아키텍처 불가가 아니라 당시 버전(0.111.0) 기준의 미지원**이었다. 현행 Codex는 둘 다 지원한다 — 단 orchestration·auto-routing·세션페어 시맨틱 부재로 **hooks만 완전 포팅 가치**가 있다. (실제 포팅은 별도 cycle; 본 갱신은 문서 정정만.)

### (a) Codex 현행 native capability
- **hooks** — `~/.codex/hooks.json` / config.toml `[hooks]`. 이벤트: PreToolUse·PostToolUse·UserPromptSubmit·SessionStart·SubagentStart/Stop 등. stdin JSON, exit 0/2, `type:"command"` + `commandWindows`. → Claude hook contract와 거의 동형(`lib/common.py` 재사용 가능).
- **custom agents** — `~/.codex/agents/*.toml`. 필드: name·description·developer_instructions + model·sandbox_mode·mcp_servers. **명시 호출만·max_depth=1·agent↔agent 없음**(Claude hub-leaf fan-out 불가).
- **rules** — AGENTS.md + nested override(cwd-dir) + profiles. (출처: developers.openai.com/codex.)

### (b) 버전 선결조건
사용자 설치 = Codex **0.111.0**. hooks ~v0.117·subagents ~v0.13x 이후 추가 → **현재 미지원**(`~/.codex`에 `agents/`·`hooks.json` 부재). **포팅 선결 = 업그레이드(무료, ≠결제).**

### (c) 포팅 feasibility 매트릭스
| 부품 | 판정 |
|---|---|
| **hooks 5** | 포팅 가치 — `secret_scan`·`suggest_compact`·`learning_log` **NATIVE**, `scope_check`·`route_nudge` caveat. contract 일치·`lib/common` 재사용 |
| **agents 21** | flat standalone만 — `_core`·`_gamedev` caveat, `_ue`·`_unity` hub-leaf **STILL-DEGRADED**(max_depth=1) |
| **rules·roles·routing 별칭** | **드롭 유지** (시맨틱 부재/중복) |
| **harness/learnings-review skill** | QOL caveat |

### (d) 권고 tier
- **GO**: hooks 포팅 (메커니즘·contract 일치).
- **MAYBE**: `_core`·`_gamedev` flat agents, learnings-review.
- **DON'T**: hub-leaf(`_ue`·`_unity`) agents, rules, roles, routing 별칭 — 시맨틱 부재로 드롭 유지.

### (e) 미검증 (실 포팅 cycle에서 확인)
hook stdout context 주입 · config syntax · max_depth hub→leaf 동작 · project override — 4건 전부 실 포팅 전 검증 필요.

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
