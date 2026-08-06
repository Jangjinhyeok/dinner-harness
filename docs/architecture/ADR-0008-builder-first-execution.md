# ADR-0008: Builder-first execution makes Codex dispatch observable and defaultable

- **Status:** Accepted for canonical source; live installation remains a separate human end-sign-off gate
- **Date:** 2026-08-06
- **Deciders:** user + Architect session

## Context

The intended default pairing is Claude = Architect and Codex = Builder. Local
Claude transcripts showed the opposite operational result: no observed
`orchestrate.py build` dispatches, while Claude performed the edits and called
Claude subagents. Natural-language routing advice is easy for an interactive
session to skip, so it cannot establish the intended token boundary or measure
whether the boundary was crossed.

The controller-side safety net is still required for a headless Codex Builder,
but it only judges a dispatch that happened. It does not cause the dispatch.

## Decision

Provide an opt-in **Builder-first** Claude Architect process:

```text
dh-architect.cmd
  -> DINNER_EXECUTION_MODE=builder-first
  -> Claude writes HANDOFF / ADR only
  -> builder_guard blocks direct Edit/Write implementation
  -> linked Builder worktree
  -> orchestrate.py build
  -> Codex Builder + controller net
  -> RESULT + diff review + receipt
```

`builder_guard` allows only root bus artifacts and `docs/architecture/*.md`.
It intentionally does not interpret arbitrary shell commands; this is an
honest-session workflow guard, not a hostile-agent sandbox. The existing linked
worktree and ADR-0007 controller net remain the containment and deterministic
post-turn decision mechanisms.

Every `build` writes an `attempted` JSONL audit event followed by a terminal
`built`, `blocked`, `timeout`, or `builder_bailed` receipt event. Events contain
metadata and SHA-256 fingerprints, not user prompts, bus contents, or changed
file content. They live under the harness runtime log directory rather than the
target repository so audit artifacts cannot change the delta being judged.

Two consecutive false read-only bails are terminal `BLOCKED`/`builder_bailed`.
They must not be reported as `BUILT`; the previous retry loop had that gap.

## Consequences

- Claude's direct structured code-edit path is visibly refused in Builder-first
  mode, preserving its budget for specification and review.
- Receipt data can measure attempted dispatches, outcomes, timeouts, and guard
  blocks without retaining task content.
- `BUILT` remains only a controller result. The Architect must still inspect
  `RESULT.md` and `git diff`; HIGH changes still require human end sign-off.
- This is not active until an authorized live install. Canonical files alone do
  not alter `~/.claude`.

## Alternatives considered

- **Documentation/nudge only:** rejected; the transcript evidence already
  showed that prose guidance did not actuate dispatch.
- **Fully headless Architect + Builder:** rejected as the default because it
  removes the interactive Claude review loop the user actively uses.
- **Write receipts into the Builder repository:** rejected because a receipt
  would enter `git status` and contaminate the safety-net witness it describes.
