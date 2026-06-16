---
name: learnings-review
description: "Review captured build/command failures (from the learning_log hook) and promote recurring ones into CLAUDE.md rules or memory. Use when the user says 'review learnings', 'what keeps failing', 'promote learnings', or periodically at a milestone."
argument-hint: "[project-path or 'all']"
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash, Edit, Write, AskUserQuestion
model: sonnet
---

# Learnings Review

The promotion half of the learning-persistence loop (gap #4 / ADR-0004). The
`learning_log` PostToolUse hook silently captures Bash **failure signals** to
`hooks/logs/learning_log.log` (JSON-lines). This skill turns that raw capture into
durable rules — it clusters recurring failures and proposes CLAUDE.md / memory entries
so the same mistake isn't re-made every session.

> The hook only *captures*; nothing is learned until you run this and promote. Without
> promotion, `learning_log.log` is just another log.

## Phase 1: Load Captures

Read `~/.claude/hooks/logs/learning_log.log` (JSON-lines; each line has
`signal`, `command`, `excerpt`, `cwd`, `session`, `timestamp`). If the file is
missing or empty, report "No captured failures — the learning_log hook may not be
wired yet (see hooks/README.md)" and stop.

Optionally filter by the argument: a project path (match `cwd`) or `all`.

## Phase 2: Cluster

Group captures into recurring patterns. Cluster by:
- `signal` (e.g. `msvc_compile`, `msvc_link`, `csharp`, `not_found`) AND
- normalized `excerpt` (strip file/line numbers, identifiers, paths so
  `Foo.cpp(42): error C2065: 'UFoo'` and `Bar.cpp(9): error C2065: 'UBar'` cluster).

Rank clusters by recurrence count (× distinct sessions). A failure that happened
once is noise; one that recurs across sessions is a candidate rule.

## Phase 3: Report

```markdown
## Learnings Review: [scope]
Captures: [N] across [M] sessions

### Recurring failures (candidates for promotion)
| Count | Sessions | Signal | Pattern | Likely rule |
|-------|----------|--------|---------|-------------|
| 7 | 4 | msvc_compile | C2065 on UCLASS forward-decl | "Include the generated .h / forward-declare with class U..." |
| 3 | 3 | not_found | `py` not on PATH in cwd X | "Use full python path / activate venv first" |

### One-offs (not promoting)
- [brief list — noise, no action]
```

## Phase 4: Promote (with approval)

For each recurring cluster, draft a concrete, minimal rule and ask where it belongs:

- **Project-specific** (this engine/project) → the project's `CLAUDE.md` (e.g. a
  "Build gotchas" or "Conventions" section). Default for engine/build specifics.
- **Cross-project** (a habit that applies everywhere) → a `feedback`/`reference`
  memory, or user-level `~/.claude/CLAUDE.md` if it's a genuine always-on rule.

Use `AskUserQuestion` to confirm destination + wording per cluster (batch related
ones). Then **ask before writing** ("May I add this to [path]?", CLAUDE.md §5) and
make the edit surgically — append to the relevant section, don't restructure.

Rules for good promotions:
- One actionable line, phrased as a directive ("Before X, do Y"), not a war story.
- Tie it to the trigger ("When you see `error C2065` on a UCLASS, ...").
- Don't promote one-offs or environment hiccups that won't recur.

## Phase 5: Prune

After promoting, offer to clear the promoted captures so the log doesn't re-surface
them next review:
> "Promoted [N] clusters. Clear `learning_log.log` now? [A] Yes  [B] Keep for history"

If [A], truncate the file (`: > ~/.claude/hooks/logs/learning_log.log`). The promoted
rules now live in CLAUDE.md/memory; the raw log has served its purpose.

### Notes
- This skill is the only consumer of `learning_log.log`. The hook is advisory and
  never blocks; if it isn't wired, this skill simply finds nothing.
- Keep promotions lean — a CLAUDE.md full of micro-rules is as useless as none.
