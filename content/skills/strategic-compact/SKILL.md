---
name: strategic-compact
description: Preserve concise task state across genuine context compaction or session transitions.
---

# Context Continuity

Prefer native compaction. Edit-count reminders do not measure context. The Claude install
registers the advisory `suggest_compact` hook (Edit/Write count, `COMPACT_THRESHOLD` default 50,
then every 25); the Codex install does not. Treat its message as a prompt to assess state, not a
measurement; do not add further call-count hooks.

For a genuine transition preserve goal, accepted decisions, unfinished work, verification and
next action in the available summary or an authorized project note. Do not require a specific
vendor task tool, memory directory or transcript replay.

When relevant, include the current execution path and revision with uncommitted state or job/run;
confirmed environment blockers with evidence location and minimal identifiers; completed/failed/not_run
checks; next action, retry conditions and what invalidates the diagnosis. Changes to environment,
permissions, engine or target require reassessment; an old failure never permanently waives validation.
Preserve read instruction paths, scope, key constraints and necessary source locations, not full text.
Reuse unchanged guidance/source only while the needed content remains in context; a matching hash
does not establish that. After compaction/context loss or scope/instruction changes, reread relevant
parts. Do not add per-call hash hooks or a persistent cache. Prior approval does not authorize new work;
never retain sensitive log bodies or credentials in the summary.

Where the headless orchestrator is installed (Codex target), a continuing implementation may
resume an explicit thread ID bound to repo/task; never use `--last` as concurrent-task identity.
Independent review requires fresh context. Experimental vendor context-management features are
optional and must not be auto-enabled.
Never preserve credentials or private prompt dumps as continuity notes.
