# ADR-0019: remove the pre-dispatch baseline-commit requirement

- **Status:** Accepted
- **Date:** 2026-08-31
- **Deciders:** user + Architect session

## Context

Four canonical docs — `content/instructions/CLAUDE.md`, `content/roles/ROLE_ARCHITECT.md`,
`content/skills/delegate/SKILL.md`, and `assets/codex/AGENTS.md` — instruct the
Architect to commit a clean baseline before dispatching the Builder, on the theory
that the subsequent `git diff` review needs a clean starting point. Independently,
`orchestrator/controller.py` (per ADR-0007) implements a before/after
`git status --porcelain` snapshot delta specifically engineered to isolate only the
Builder's own changes: a file that is already dirty at dispatch time sits in *both*
snapshots and therefore nets out of the delta, by construction — the mechanism
already tolerates a dirty tree correctly, and this is exercised by existing tests
(e.g. `test_orchestrator.py`'s coverage of a nested repo already dirty at dispatch,
and of a commit removing paths from both snapshots).

This makes the baseline-commit instruction redundant with already-working, already-
tested controller behavior for **tracked** pre-existing changes. It is also in
tension with `CLAUDE.md` §6's own Git-ownership policy, which forbids committing
without the user's explicit per-instance approval ("task 완료, LOW 판정, BUILT만으로
commit/push 권한이 생기지 않는다") — the baseline-commit instruction asks the
Architect to commit automatically as a dispatch precondition, which is exactly the
kind of unauthorized commit §6 exists to prevent.

The one real risk the instruction correctly (if too bluntly) protected against is
**untracked** files: an untracked file is not in `git status --porcelain`'s tracked
diff machinery in the way a modified tracked file is, and a Builder or later
operation could plausibly disturb or lose it with no commit to roll back to. That
risk is real and specific to untracked content, not a reason to require a commit for
every dispatch regardless of what state the tree is actually in.

## Decision

Remove the baseline-commit requirement from all four docs. Replace it with a
narrower, accurate statement: tracked pre-existing dirt is already handled safely by
the delta mechanism and needs no commit; an untracked file the user cares about
carries real rollback risk and committing it first is a user-optional safety
recommendation, not a protocol requirement. No change to `orchestrator/controller.py`
— its delta logic is already correct; only the four docs' prose changes.

## Implementation Guidelines

- `content/instructions/CLAUDE.md`: rewrite the "Builder 자동 dispatch (기본
  페어링)" paragraph's baseline-commit sentence to state dispatch proceeds directly
  after HANDOFF approval, with the delta/untracked-risk explanation.
- `content/roles/ROLE_ARCHITECT.md`: rewrite step 1 of the auto-dispatch numbered
  list the same way — dispatch directly, no baseline-commit precondition.
- `content/skills/delegate/SKILL.md`: rewrite the "commit a clean baseline first"
  sentence to state a baseline commit is optional, only for untracked files the user
  is not ready to risk losing.
- `assets/codex/AGENTS.md`: rewrite the auto-dispatch sentence the same way, keeping
  the rest of the paragraph (the exact dispatch command, ADR-0007 delta reference)
  unchanged.
- Do not touch `orchestrator/controller.py`, `orchestrator/safety.py`, or any test —
  the delta mechanism this ADR relies on is already implemented and tested; this
  gate is prose-only.

## Consequences

- **Positive:** removes an instruction that conflicted with `CLAUDE.md` §6's
  no-auto-commit policy and was redundant with already-tested controller behavior.
- **Positive:** the replacement guidance is more precise — it tells the Architect
  exactly which case (untracked files) still carries real risk, instead of a
  blanket "always commit first" that obscured the actual risk boundary.
- **Negative / trade-off:** an Architect session that was relying on the mechanical
  "always commit baseline" instruction as a simple rule now needs to make a small
  judgment call (does anything untracked matter here?) instead. This is an
  acceptable trade given the removed instruction's own conflict with §6.

## Alternatives considered

- **Keep the requirement but soften language only ("commit if you want"):** rejected
  as insufficiently precise — it doesn't tell the Architect the actual risk boundary
  (tracked vs. untracked) the way this ADR's replacement text does.
- **Leave as-is:** rejected — the instruction actively conflicts with CLAUDE.md §6's
  explicit-approval-required commit policy, which is a real inconsistency, not just
  stylistic redundancy.
