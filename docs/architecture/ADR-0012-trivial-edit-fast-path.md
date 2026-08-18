# ADR-0012: trivial-edit fast path narrows Builder-first for small Claude Edits

- **Status:** Accepted for canonical source; live installation remains a separate human end-sign-off gate
- **Date:** 2026-08-18
- **Deciders:** user + Architect session

## Context

ADR-0008 made ordinary `claude` sessions Builder-first: `builder_guard` blocks
every structured `Edit`/`Write` implementation-file write outside root bus
artifacts and `docs/architecture/*.md`, routing all of it — including a
single-line fix — through `/delegate` and a full `orchestrate.py build`
dispatch to Codex.

In practice this session hit that cost directly: three separate
`watch-builder.ps1` iterations (an encoding fix, then a readability fix) each
required writing a `HANDOFF_DELEGATE.md`, a full headless Codex turn
(~100s+ each), and a diff review — for changes that were, in the end, one or
two lines. The user asked to let genuinely trivial edits stay inline in the
default session, rather than pay Codex-dispatch latency for them.

`builder_guard` is a purely path-based allowlist today (`_allowed_path`); it
has no notion of edit size. `claude-direct.cmd`'s documented "1~2 line" inline
convention (CLAUDE.md) was never hook-enforced — that escape disables the
guard entirely via `DINNER_EXECUTION_MODE=direct`, so the line-count language
there was only ever Claude's own judgment call, not a technical boundary.

## Decision

Add a narrow, deterministic exception to `builder_guard.guarded_paths`,
active in every session (not just the escape):

- **Tool scope: `Edit` only.** `Write` and `apply_patch` are never exempted —
  `Write` has no diff concept the hook can size safely (small `content` could
  still be silently truncating a large existing file), and `apply_patch` is
  Codex's own tool, not one an interactive Claude session issues.
- **Size gate:** both `old_string` and `new_string` must span 2 lines or
  fewer (`text.count("\n") + 1 <= 2`). Missing either field (as any non-Edit
  payload naturally does) fails the check, so this cannot accidentally widen
  scope elsewhere.
- **Infrastructure exclusion, regardless of size:** `assets/claude/hooks/`,
  any `settings*.json`, `harness.toml`, `orchestrator/`, `orchestrate.py`, and
  anything resolving under the live `~/.claude` install (`CLAUDE_CONFIG_DIR`)
  outside the already-allowed `projects/*/memory/*.md` path stay Builder-only
  no matter how small the edit. Without this exclusion, a "trivial one-line
  edit" could disable `builder_guard` itself (a self-referential bypass) or
  quietly alter the live hook/settings tree the safety net depends on.

`route_nudge`'s injected routing message and CLAUDE.md's routing prose are
both updated to describe this exception, so neither keeps telling Claude a
blanket "every Edit/Write goes through Codex" rule that the hook no longer
enforces.

## Consequences

- A single-line fix (typo, one-line logic tweak, comment) in an ordinary
  project file no longer requires a `/delegate` round-trip; `builder_guard`
  allows it directly and `guarded_paths` returns an empty block list for it.
- The harness's own safety-net infrastructure (hooks, settings, orchestrator,
  `harness.toml`) keeps the full ADR-0008 Builder-first boundary at any edit
  size — this ADR narrows the boundary for ordinary project work only, not
  for the harness's own control surface.
- `Write`/`apply_patch` and any multi-line `Edit` are unaffected: they still
  route through `/delegate` (LOW) or the architect workflow (HIGH/multi-file),
  exactly as ADR-0008 established.
- This is not active until an authorized live install (`install.py --target
  claude --allow-live`); canonical source changes alone do not alter
  `~/.claude`.

## Alternatives considered

- **Loosen `claude-direct.cmd`'s prose threshold instead:** rejected — that
  escape already disables the guard entirely, so there was nothing to
  "loosen" there; the actual friction was in the default session, which had
  no exception at all.
- **Size-gate `Write` too, by content line count:** rejected — `Write`
  replacing an existing file can't be judged safe from content size alone (a
  2-line `Write` could be an accidental full-file truncation); only `Edit`'s
  `old_string`/`new_string` pair gives the hook enough context to be sure the
  change itself, not just the result, is small.
- **No infrastructure exclusion, size gate only:** rejected as a
  self-referential bypass risk — a "trivial" edit to `builder_guard.py` or
  `settings.json` could silently defeat the guard it is supposed to enforce.
