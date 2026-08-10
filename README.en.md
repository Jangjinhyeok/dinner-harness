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
- `refresh.py` — two-target refresh wrapper: preview by default; `--apply` is the explicit live-install signature.

## Install

```
py -3 install.py --target claude --dest C:/Users/<you>/.claude
py -3 install.py --target codex  --dest C:/Users/<you>/.codex
```

Defaults to `~/.<target>` when `--dest` is omitted; writing to the live dir requires
`--allow-live`. Use `--dry-run` to preview the plan without writing.

To refresh both targets together, use the wrapper below. Its default mode validates
the source and previews both targets; only an explicit `--apply` performs live writes.

```
py -3 refresh.py
py -3 refresh.py --apply
```

> **`--apply` is not transactional and creates no backup.** If the Codex refresh
> fails after Claude succeeds, the two live targets can be on different revisions.
> Check out the desired prior commit and rerun `refresh.py --apply` from it to recover.

- **claude** — verbatim copy of the full inclusion set; `settings.json` is generated
  from `settings.json.template` (substitute `<USERNAME>`, strip `_template`) and **merged**
  with the existing file so machine/runtime keys (e.g. `skipWorkflowUsageWarning`) survive.
  Live `HANDOFF.md` / `RESULT.md` are never clobbered (skip-if-exists).
- **codex** — transforms the portable subset to Codex-native paths: curated `AGENTS.md`,
  18 portable skills under `skills/`, reference dirs (`ecc-reference/`, `docs/`, `templates/`),
  and since adapter v2 (Cycle 3, Codex 0.141) **13 agents converted to `agents/*.toml` plus
  natively ported hooks** (`hooks/` copy + auto-generated `hooks.json` — advisory on Codex:
  hard blocking lives in the sandbox/approval layer). Claude-only `route_nudge` is deliberately
  excluded because standalone Codex cannot dispatch itself to a Codex Builder. Still dropped: `_mode`'s file-glob
  auto-inject (no Codex equivalent → modes are entered by explicit declaration) and 8
  Claude-machinery skills (5 routing aliases + 2 harness-only + 1 multi-judge). The **Two-CLI
  roles are cross-vendor curated into AGENTS.md §8** (bidirectional — see "Two-CLI
  collaboration" below). See `CODEX-RECON.md` and `CODEX-COVERAGE.md`.

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
- **Codex**: the same protocol is curated into `assets/codex/AGENTS.md` §8. Codex has no paths
  auto-inject, so modes are entered by **explicit declaration** ("architect/builder mode").

Being file-based, it works on Codex 0.111+; only the Architect's optional subagent delegation
uses 0.140+. Full protocol: `content/instructions/CLAUDE.md` §2.

## Usage

**Prerequisite**: `install.py` has generated `~/.claude` (+ `~/.codex`). To drive the Codex Builder
on the real backend you need the `codex` CLI authenticated + **codex 0.140+** (if it's
unauthenticated or fails, the dispatch below falls back to manual mode automatically).

### 1) Default — orchestrated single-pane (no separate Codex terminal)

In PowerShell, start Claude normally from the project directory:

```powershell
claude
```

Claude still reads code, searches, uses MCP, designs, and reviews HANDOFF/RESULT/diffs
in this session; every structured `Edit`/`Write` implementation-file write goes to the
Codex Builder. The normal `claude` command is therefore the strict Builder-first path.

For the rare session that genuinely needs Claude to edit directly, use the explicit
escape instead:

```powershell
& "$env:USERPROFILE\.claude\claude-direct.cmd"
```

`claude-direct.cmd` disables `builder_guard` only for that process; it does not provide
the strict token boundary.

Then state your intent in ordinary conversation:

1. Claude explores the codebase, then writes **`HANDOFF_DELEGATE.md`** for a single-purpose LOW task or **`HANDOFF.md`** (gates, scope, risk tier) otherwise.
2. The original LOW request is its start gate; a HIGH task waits for **HANDOFF approval**. Claude then auto-runs
   `py -3 "<CLAUDE_HOME>/orchestrate.py" build --repo "<ABSOLUTE_REPO_PATH>" --backend real`,
   **dispatching the Codex Builder headless**. The paths are resolved before the Bash call;
   it must not add `cd`, a pipe, or redirection.
3. Codex implements within scope and writes `RESULT.md`. The controller-side safety net (scope/secret) is the hard gate.
4. Claude **reviews `RESULT.md` + `git diff` in the same session**. For a HIGH gate it takes your **end sign-off** before merge/apply.
5. On `BLOCKED`/codex error it stops and points you to the manual fallback (③ below).

The branch you checked out before the session is the only delivery branch. Claude creates
no delivery branch; it stages and commits the accepted delta on your current branch only when you
explicitly authorize `commit` or `commit and push` in that conversation. Push likewise
requires that explicit authorization; task completion alone never authorizes it.

> Questions, reading, and searching stay with Claude in the strict session. Even a tiny file
> edit takes the Codex Builder route in that session.

### 2) Calling the orchestrator directly (optional)

In PowerShell, resolve the two placeholders to forward-slash absolute paths before
calling the command. This is copyable; do not add `cd`, a pipe, or redirection.

```
$claudeHome = ($env:USERPROFILE -replace '\\', '/') + '/.claude'
$repoPath = (Get-Location).Path -replace '\\', '/'

# Builder-only, once, from an existing HANDOFF.md (the command single-pane uses internally)
py -3 "$claudeHome/orchestrate.py" build --repo "$repoPath" --backend real

# Both Architect and Builder fully headless (human only at the boundaries)
py -3 ~/.claude/orchestrate.py run --goal "..." --backend real --repo .

# Offline smoke, no CLIs needed
py -3 "$claudeHome/orchestrate.py" build --repo "$repoPath" --backend mock
```

### 3) Manual dual-session (fallback / reverse pairing)

In one session write `HANDOFF.md` in `architect mode`; in **another session (e.g. a Codex terminal)**
run it in `builder mode` and return `RESULT.md`. Communication is via the project-root bus files.

### 4) Modifying the harness itself

Don't edit `~/.claude` / `~/.codex` directly — edit the repo's canonical tree (`content/`, `assets/`),
preview with `py -3 refresh.py`, then have a human explicitly run
`py -3 refresh.py --apply` to regenerate Claude and Codex together.

Run `check.py` **after** regenerating too — its install-drift axis compares the repo against the
live install and catches "edited but never installed" (which has bitten twice). `--no-install`
skips that axis.

> **Have the back-out ready before you install.** `install.py` overwrites in place and keeps
> **no backup** — the only undo is re-installing from the previous commit:
> `git stash && py -3 install.py --target claude --allow-live && git stash pop`
> (or check out the previous commit and install from there). `hooks/lib/common.py` is imported by
> **every** handler, so a bad copy there breaks every interactive hook at once. Details in
> `orchestrator/README.md`.

## What's inside (capabilities)

The skills, agents, and hooks this harness ships. _A frontmatter-derived snapshot — update
when skills/agents change._ For which items are native/degraded/dropped on the codex target,
see `CODEX-COVERAGE.md`.

### Skills (28)

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

**Workflow (7)**
- `delegate` — hand a LOW single-purpose task to the Codex Builder headless + inline review (no full ceremony)
- `changelog` — auto-generate a changelog from git commits (internal + player-facing)
- `hotfix` — emergency-fix workflow (severity, rollback plan, audit trail)
- `codebase-onboarding` — analyze an unfamiliar codebase into an onboarding guide (engine-aware)
- `arch-review` — architectural & quality code review (SOLID, testability, performance)
- `learnings-review` — promote recurring `learning_log` failures into CLAUDE.md/memory
- `walkthrough` — guided code tour of recent/specified changes (structure, flow, design intent + recall questions)

**UE routing (6)**
- `ue` — route multi-subsystem Unreal work to the `unreal-specialist` hub
- `bp` — route Blueprint work to the hub focused on `docs/specialists/ue-blueprint.md`
- `gas` — route GAS work to the hub focused on `docs/specialists/ue-gas.md`
- `umg` — route UMG/CommonUI work to the hub focused on `docs/specialists/ue-umg.md`
- `repl` — route replication/netcode work to the hub focused on `docs/specialists/ue-replication.md`
- `ue-umg-review` — review/design UMG widgets (UE5)

**Autonomous loop (2)**
- `autonomous-loop` — risk-tiered self-correcting loop (human sets start/end only; agent owns the middle)
- `adversarial-review` — default-to-reject multi-judge panel (mandatory for HIGH tier)

**Harness (1)**
- `harness-review` — review the dinner-harness repo itself through wiring + conformance lenses

### Agents (13)

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

**_ue (1)**
- `unreal-specialist` — single UE5 engine agent (deep GAS/BP/UMG/replication guidance lives in `docs/specialists/ue-*.md` reference docs it Reads on demand — leaf agents demoted 2026-07-02)

**_unity (1)**
- `unity-specialist` — single Unity engine agent (deep DOTS/shader/Addressables/UI guidance lives in `docs/specialists/unity-*.md` reference docs it Reads on demand — leaf agents demoted 2026-07-02)

### Hooks (6)

For the full firing flow and operating modes, see `assets/claude/README.md` + `assets/claude/hooks/README.md`.

- `secret_scan` (PreToolUse) — regex-detect secrets / sensitive file paths in input (enforce, blocking)
- `scope_check` (PreToolUse) — block out-of-scope edits + protect hook infra (dryrun, always-block hard-blocks)
- `suggest_compact` (PreToolUse) — suggest `/compact` once tool calls accumulate (advisory)
- `learning_log` (PostToolUse) — capture Bash failure signals → promote via `learnings-review` (advisory)
- `route_nudge` (Claude UserPromptSubmit only) — detect UE-domain signals in the prompt → inject a routing nudge: single domain suggests the `/alias` (hub + focus doc), multi-domain suggests architect mode + dispatch (advisory). It is deliberately excluded from Codex `hooks.json`.
- `builder_guard` (PreToolUse) — reserve structured code edits for Codex Builder by default; only the explicit `claude-direct.cmd` escape disables it
