---
name: codebase-onboarding
description: Analyze an unfamiliar codebase and produce a structured onboarding guide (architecture map, entry points, conventions) plus a starter project CLAUDE.md. Engine-aware for UE5/Unity. Use when opening a new repo, re-entering a project after a break, "help me understand this codebase", or "generate a CLAUDE.md".
origin: ECC (adapted — engine-aware)
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash, Write, Task
model: sonnet
---

# Codebase Onboarding

Systematically analyze an unfamiliar codebase and produce a structured onboarding
guide. Engine-aware: detects Unreal/Unity first, then general stacks. Designed for
opening a new project, re-entering one after a break, or setting up Claude Code in an
existing repo.

## When to Use

- First time opening a project, or re-entering a UE5/Unity module after weeks away
- "Help me understand this codebase" / "onboard me" / "walk me through this repo"
- "Generate a CLAUDE.md for this project"

## Phase 1: Reconnaissance

Gather signals without reading every file — use **Glob/Grep**, not Read on everything.

**Detect the engine first** (same signals as `rules/agent-routing.md`):
- **Unreal** → `*.uproject`, `Source/**/*.Build.cs`, `*.Target.cs`, `Config/Default*.ini`, `Plugins/**/*.uplugin`, `Content/`
- **Unity** → `ProjectSettings/ProjectVersion.txt`, `Packages/manifest.json`, `Assets/`, `**/*.asmdef`
- **Neither** → generic manifests: `package.json`, `go.mod`, `Cargo.toml`, `pyproject.toml`, `pom.xml`, `build.gradle`, `Gemfile`, `composer.json`

**Then gather in parallel:**

1. **Entry points**
   - UE: primary game module under `Source/<Project>/`, `GameMode`/`GameInstance`/`PlayerController`, `*GameModeBase`
   - Unity: bootstrap scene, `[RuntimeInitializeOnLoadMethod]`, top-level MonoBehaviours
   - Generic: `main.*`, `index.*`, `app.*`, `server.*`, `cmd/`, `src/main/`
2. **Module / assembly layout**
   - UE: module dependencies in each `.Build.cs`; Unity: the `.asmdef` graph; Generic: workspace/packages layout
3. **Config & tooling**
   - UE: `Config/*.ini`, `.uplugin`, target/build flags; Unity: `ProjectSettings/`, render pipeline asset, scripting backend; Generic: `tsconfig.json`, `Dockerfile`, `.github/workflows/`, linters
4. **Test structure**
   - UE: Automation specs (`*.spec.cpp`, `IMPLEMENT_*_AUTOMATION_TEST`); Unity: EditMode/PlayMode tests, `*.Tests.asmdef`; Generic: `tests/`, `*.test.*`, `*_test.go`
5. **Directory tree** (top 2 levels), ignoring generated dirs:
   - UE: `Binaries/ Intermediate/ Saved/ DerivedDataCache/`
   - Unity: `Library/ Temp/ obj/ Logs/`
   - Generic: `node_modules/ vendor/ .git/ dist/ build/ __pycache__/`

## Phase 2: Architecture Mapping

From the recon data, identify:

**Tech / engine stack** — language(s) and versions, engine version (cross-check
`docs/engine-reference/<engine>/VERSION.md` if present), major plugins/packages,
render pipeline, build tooling.

**Architecture pattern** — UE: module boundaries, Blueprint vs C++ split, GAS usage
(`AbilitySystemComponent`), replication model, key `Subsystem`s. Unity: MonoBehaviour
vs DOTS/ECS, scene/prefab structure, Addressables usage, assembly boundaries. Generic:
monolith/monorepo/services, API style.

**Key directories** — map each top-level dir to its purpose (skip the obvious; don't
explain `Source/` or `Assets/`).

**Data / gameplay flow** — trace one path end to end. UE: input → ability/gameplay
system → state/replication → presentation. Unity: input → system/MonoBehaviour/ECS →
state → render. Generic: request → validation → business logic → data store.

> For deep subsystem analysis (GAS internals, replication, DOTS, shaders), delegate to
> the engine hub via Task — `unreal-specialist` or `unity-specialist`. Onboarding maps
> the terrain; the hubs do the deep dives.

## Phase 3: Convention Detection

- **Naming** — file/class naming (UE `U`/`A`/`F`/`E` prefixes, Unity PascalCase), test file patterns.
- **Code patterns** — error handling, async (UE delegates/latent actions, Unity coroutines/async/UniTask), DI vs direct refs, BP/C++ boundary rules.
- **Git conventions** — branch + commit style from recent history. If history is shallow (`--depth 1`) or empty, note "Git history unavailable to detect conventions" and skip.

## Phase 4: Generate Onboarding Artifacts

Ask **"May I write this to [path]?"** before creating any file (CLAUDE.md §5).

### Output 1: Onboarding Guide

```markdown
# Onboarding Guide: [Project]

## Overview
[2-3 sentences: what it is, target platforms]

## Stack
| Layer | Tech | Version |
|-------|------|---------|
<!-- Example (UE5) — replace with detected -->
| Engine | Unreal Engine | 5.x (see docs/engine-reference/unreal/VERSION.md) |
| Language | C++ / Blueprint | C++20 |
| Gameplay | GAS | - |
| Tests | Automation | - |

## Architecture
[How modules/systems connect]

## Key Entry Points
<!-- Example (UE5) — replace with detected -->
- Game module: `Source/<Project>/`
- Game mode / instance: `Source/<Project>/Core/`
- Config: `Config/DefaultEngine.ini`

## Directory Map
[top-level dir → purpose]

## Gameplay/Request Lifecycle
[trace one path end to end]

## Conventions
- [naming] / [error handling] / [BP-C++ boundary] / [test pattern] / [git]

## Common Tasks
<!-- Example — replace with detected -->
- Build: `[detected]`  · Run tests: `[detected]`  · Generate project files: `[detected]`

## Where to Look
| I want to... | Look at... |
|--------------|-----------|
| Add a gameplay ability | [GAS dir] |
| Add a UI screen | [UMG/UI Toolkit dir] |
| Add a replicated property | [relevant actor/component] |
```

### Output 2: Starter / Updated CLAUDE.md

If `CLAUDE.md` exists, **read and enhance it** — preserve existing instructions, call
out what's added. Keep it under ~100 lines.

```markdown
# Project Instructions

## Stack
[engine + version, language, key plugins/packages]

## Code Style
[detected naming + patterns; BP/C++ or MonoBehaviour/DOTS boundary]

## Build & Run
- Build: `[detected]`  · Tests: `[detected]`

## Project Structure
[key dir → purpose]

## Conventions
[commit style, error handling, engine-specific rules]
```

### Recommend project conventions (UE5/Unity)

If the project lacks them, recommend setting up the conventions the `_gamedev` agents
expect (templates live in `~/.claude/templates/`):
- `docs/engine-reference/<engine>/VERSION.md` — pin the engine version; powers the agents' "Engine Version Safety".
- `docs/architecture/` — adopt the ADR template for design decisions.

## Best Practices

1. **Don't read everything** — recon via Glob/Grep; Read selectively for ambiguous signals.
2. **Verify, don't guess** — if config and actual code disagree, trust the code.
3. **Respect existing CLAUDE.md** — enhance, don't replace; call out what's new.
4. **Stay concise** — the guide should be scannable in ~2 minutes.
5. **Flag unknowns** — "could not determine test runner" beats a wrong answer.

## Anti-Patterns

- A CLAUDE.md longer than ~100 lines, or that lists every dependency.
- Explaining obvious dirs (`Source/`, `Assets/` need no explanation).
- Copying the README — add structural insight it lacks.
- Reading hundreds of files when Glob/Grep + a few targeted Reads suffice.
