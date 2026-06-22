# dinner-harness

[한국어](README.md) | **English**

Single source of truth for a custom Claude Code **and** Codex harness.

**Purpose: cut subscription cost.** Run Claude Pro + Codex instead of the pricier
Claude Max, splitting roles by vendor — low-volume design/review on Claude (Architect),
token-heavy implementation on Codex (Builder). The point is to land the token sink on
the higher-quota plan.

Hand-edit the canonical tree in this repo; **never hand-edit `~/.claude` or `~/.codex`
directly** — they are generated outputs. Regenerate a target with the installer.

## Layout

- `content/` — tool-neutral harness content (instructions, rules, skills, agents, roles,
  templates, ecc-reference, docs). The codex adapter transforms this; the claude adapter
  copies it verbatim.
- `assets/claude/` — claude-native raw (Python hooks, launchers, settings template,
  hand-written docs). Copied verbatim; the codex adapter ignores it.
- `assets/codex/` — codex-native raw (curated `AGENTS.md`).
- `adapters/` — per-target renderers (`claude.py`, `codex.py`).
- `harness.toml` — manifest: targets, template vars, copy / template(merge) / skip / exclude.
- `install.py` — CLI entry: `install --target claude|codex [--dest PATH] [--dry-run] [--allow-live]`.

## Install

```
py -3 install.py --target claude --dest C:/Users/<you>/.claude
py -3 install.py --target codex  --dest C:/Users/<you>/.codex
```

Defaults to `~/.<target>` when `--dest` is omitted; writing to the live dir requires
`--allow-live`. Use `--dry-run` to preview the plan without writing.

- **claude** — verbatim copy of the inclusion set (87 files); `settings.json` is generated
  from `settings.json.template` (substitute `<USERNAME>`, strip `_template`) and **merged**
  with the existing file so machine/runtime keys (e.g. `skipWorkflowUsageWarning`) survive.
  Live `HANDOFF.md` / `RESULT.md` are never clobbered (skip-if-exists).
- **codex** — transforms the portable subset to Codex-native paths: curated `AGENTS.md`,
  17 portable skills under `skills/`, reference dirs (`ecc-reference/`, `docs/`, `templates/`).
  Claude-machinery (subagent routing, hooks, `_mode` conditional inject, 7 Claude-machinery
  skills [5 routing + 2 harness]) is currently **dropped** by the codex adapter, but the
  **Two-CLI roles are cross-vendor curated into AGENTS.md §7** (bidirectional — see "Two-CLI
  collaboration" below). What's dropped is `_mode`'s file-glob auto-inject (no Codex equivalent →
  modes are entered by explicit declaration) plus hooks / subagent orchestration; the latter is
  supported by newer Codex but adapter porting is deferred (a design decision, not an architectural
  impossibility). See `CODEX-RECON.md` and `CODEX-COVERAGE.md`.

## Targets

- **claude** — implemented & live: repo is the source of truth for `~/.claude`. The inclusion
  set round-trips byte-identical (proven diff-0).
- **codex** — implemented & live: `~/.codex` deployed non-destructively (runtime preserved).

See `CODEX-RECON.md` for the codex feasibility analysis (build vs adopt) and
`CODEX-COVERAGE.md` for the per-content native/degraded/dropped accounting.

## Two-CLI collaboration (cross-vendor)

Large work is split into two roles — **Architect** (design/review) and **Builder**
(implementation). "Two-CLI" means **two roles / two CLI engines** (Claude·Codex), not two
interactive terminals you tend. Both roles are vendor-neutral; either Codex or Claude can play
either role. **Default: Claude=Architect / Codex=Builder** (the reverse also works) — the Builder
is the token sink, so it lands on the higher-quota plan (Codex) while the low-volume Architect runs
on the quota-constrained one (Claude Pro).

Three operating modes (all communicate through project-root `HANDOFF.md` / `RESULT.md` /
`INPUT.md` — a vendor-neutral bus needing no runtime IPC/MCP):
- **orchestrated single-pane (default)** — one interactive Claude session auto-dispatches the Codex
  Builder headless via `orchestrate.py build` after HANDOFF approval (**no separate Codex terminal**),
  then reviews RESULT in the same session.
- **manual dual-session** — a human opens both interactive sessions and couriers via the bus
  (reverse pairing, same-vendor, or fallback).
- **fully headless** — `orchestrate.py run` drives both sides headless.

- **Claude**: `content/roles/ROLE_{ARCHITECT,BUILDER}.md` + `rules/_mode/` (auto-injected when a
  communication file matches its paths glob).
- **Codex**: the same protocol is curated into `assets/codex/AGENTS.md` §7. Codex has no paths
  auto-inject, so modes are entered by **explicit declaration** ("architect/builder mode").

Being file-based, it works on Codex 0.111+; only the Architect's optional subagent delegation
uses 0.140+. Full protocol: `content/instructions/CLAUDE.md` §2.

## What's inside (capabilities)

The skills, agents, and hooks this harness ships. _A frontmatter-derived snapshot — update
when skills/agents change._ For which items are native/degraded/dropped on the codex target,
see `CODEX-COVERAGE.md`.

### Skills (26)

**Meta-principles (5)**
- `simplicity-first` — minimum-viable code; prevents over-engineering and speculative flexibility
- `surgical-changes` — no out-of-scope edits / unrelated refactors (critical for live service)
- `think-before-coding` — state assumptions, enumerate options, ask before implementing
- `goal-driven-execution` — turn vague tasks into verifiable goals
- `search-first` — search for existing implementations/libraries before writing custom code

**Context & verification (7)**
- `verification-loop` — session change-verification system
- `eval-harness` — eval-driven development framework
- `strategic-compact` — suggests manual context compaction at logical intervals
- `iterative-retrieval` — progressive context refinement (subagent context problem)
- `scope-check` — audit scope creep against the original plan
- `perf-profile` — bottleneck analysis, budget comparison, optimization ranking
- `tech-debt` — track, categorize, and schedule technical-debt repayment

**Workflow (5)**
- `changelog` — auto-generate a changelog from git commits (internal + player-facing)
- `hotfix` — emergency-fix workflow (severity, rollback plan, audit trail)
- `codebase-onboarding` — analyze an unfamiliar codebase into an onboarding guide (engine-aware)
- `arch-review` — architectural & quality code review (SOLID, testability, performance)
- `learnings-review` — promote recurring `learning_log` failures into CLAUDE.md/memory

**UE routing (6)**
- `ue` — route multi-subsystem Unreal work to the `unreal-specialist` hub
- `bp` — route Blueprint architecture directly to `ue-blueprint-specialist`
- `gas` — route GAS directly to `ue-gas-specialist`
- `umg` — route UMG/CommonUI directly to `ue-umg-specialist`
- `repl` — route replication/netcode directly to `ue-replication-specialist`
- `ue-umg-review` — review/design UMG widgets (UE5)

**Autonomous loop (2)**
- `autonomous-loop` — risk-tiered self-correcting loop (human sets start/end only; agent owns the middle)
- `adversarial-review` — default-to-reject multi-judge panel (mandatory for HIGH tier)

**Harness (1)**
- `harness-review` — review the dinner-harness repo itself through wiring + conformance lenses

### Agents (21)

**_core (6)**
- `architect` — system design, scalability, technical decisions
- `code-reviewer` — quality, security, maintainability review
- `cpp-build-resolver` — C++ build / CMake / linker / template error resolution (minimal change)
- `cpp-reviewer` — C++ memory safety, modern idioms, concurrency, performance review
- `planner` — planning for complex features and refactors
- `tdd-guide` — test-first methodology (80%+ coverage)

**_gamedev (5)**
- `gameplay-programmer` — game mechanics, combat, player systems
- `network-programmer` — multiplayer netcode, lag compensation, matchmaking
- `performance-analyst` — profiling, bottlenecks, optimization strategy
- `tools-programmer` — editor extensions, content tools, pipeline automation
- `ui-programmer` — menus, HUDs, inventory, UI widgets

**_ue (5)**
- `unreal-specialist` — UE5 hub (fans out to GAS/BP/UMG/replication sub-specialists)
- `ue-blueprint-specialist` — Blueprint architecture, BP/C++ boundary, optimization
- `ue-gas-specialist` — GAS: abilities, effects, attribute sets, tags, prediction
- `ue-replication-specialist` — property replication, RPCs, client prediction, relevancy
- `ue-umg-specialist` — UMG/CommonUI: widget hierarchy, data binding, input

**_unity (5)**
- `unity-specialist` — Unity hub (fans out to DOTS/shader/addressables/UI sub-specialists)
- `unity-dots-specialist` — DOTS/ECS, Jobs, Burst
- `unity-shader-specialist` — Shader Graph, VFX Graph, render pipeline (URP/HDRP)
- `unity-addressables-specialist` — asset loading, bundles, memory, content catalogs
- `unity-ui-specialist` — UI Toolkit, UGUI, data binding, runtime UI performance

### Hooks (5)

For the full firing flow and operating modes, see `assets/claude/README.md` + `assets/claude/hooks/README.md`.

- `secret_scan` (PreToolUse) — regex-detect secrets / sensitive file paths in input (enforce, blocking)
- `scope_check` (PreToolUse) — block out-of-scope edits + protect hook infra (dryrun, always-block hard-blocks)
- `suggest_compact` (PreToolUse) — suggest `/compact` once tool calls accumulate (advisory)
- `learning_log` (PostToolUse) — capture Bash failure signals → promote via `learnings-review` (advisory)
- `route_nudge` (UserPromptSubmit) — detect UE-domain signals in the prompt → inject a delegation nudge (advisory)
