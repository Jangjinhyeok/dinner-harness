# CODEX-RECON — Cycle 1 Gate 3

codex adapter feasibility recon + adopt-vs-build decision. Feeds Cycle 2 scope.

> ※ Cycle 1 feasibility recon. Cycle 2 확정 ground-truth는 `CODEX-COVERAGE.md`다 — 이 문서의 일부 degraded/merged 판정은 Cycle 2에서 최종 **dropped**로 갱신됐다(예: subagents, agent-routing, 7 routing skills).

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
