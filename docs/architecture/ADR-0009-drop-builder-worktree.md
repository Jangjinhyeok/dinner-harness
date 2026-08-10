# ADR-0009: Drop the Builder linked-worktree procedure

- **Status:** Accepted
- **Date:** 2026-08-10
- **Deciders:** Architect session (dinner-harness)

## Context

The documented default pairing created a linked Git worktree before every
headless Builder dispatch, copied the approved `HANDOFF.md` into it, then asked
the Architect to review that separate tree. The procedure added an isolation
story, but it was never a production requirement of `orchestrate.py`: its
`build --repo <path>` interface accepts a repository path and neither the
orchestrator nor its production call paths create or require a linked worktree.
Occurrences of the token in the implementation are unrelated Git index
`skip-worktree` handling, loose "working tree" language, or a regression test.

ADR-0007 already addresses the stated contamination concern. Its controller
captures a `before` changeset and witness fingerprint immediately before the
Builder turn, captures them again after the turn, and judges the union delta.
Pre-existing dirty paths are therefore excluded by construction. The claim that
an Architect's uncommitted edit necessarily becomes part of the Builder
changeset is no longer true.

A linked layout does not strengthen the actual security boundary. The sandbox
allows writes throughout the selected repository either way; the scope fence is
post-hoc in either layout; and Codex hooks are advisory rather than a veto.
The `/delegate` lane already invokes the same `orchestrate.py build` path in
place, so the two lanes have diverged only in ceremony.

The ceremony has a measured cost. On 2026-08-10, four uncleaned linked
directories and four orphan `builder/*` branches remained. A UE5 project copy
was 2,496 MB even excluding ignored build outputs; there were no unintegrated
commits or unique uncommitted edits to justify the retained copies. The protocol
also had no cleanup rule. Worse, the layout previously made
`rev-parse --git-dir` point at `.git/worktrees/<name>`, whose missing
`info/exclude` silently disabled part of the witness check until ADR-0007 moved
the check to `--git-common-dir`.

## Decision

The default Builder dispatch runs in the original repository. Before dispatch,
the Architect commits the approved baseline and leaves the tree clean. It then
runs `orchestrate.py build --repo <ABSOLUTE_REPO_PATH>`, and reviews the same
repository's `RESULT.md` and `git diff`.

The clean baseline replaces the former cheap-discard property: if the dispatch
fails, the resulting dirty delta is the Builder's entire delta and can be
discarded using the existing `/delegate` recovery rule (`git checkout .` plus
`git clean -fd`). The Architect must not edit that repository while the Builder
runs. Snapshot delta distinguishes before and after; it is not a concurrency
boundary during the turn.

## Consequences

- Documentation uses one in-place dispatch procedure for the default pairing
  and `/delegate` lane.
- `HANDOFF.md` remains in the repository's local bus without a copy step, and
  review happens against the repository's ordinary `RESULT.md` and `git diff`.
- Linked-worktree creation, `builder/*` isolation branches, and their
  common-directory-specific operating instructions are no longer part of the
  workflow.
- This decision supersedes the worktree procedure recorded as completed in the
  historical WORK-QUEUE entry. It does not modify ADR-0007's delta or witness
  mechanism, and it does not remove its linked-layout regression coverage.
- A repository-level sandbox remains the containment boundary; the controller
  net remains a deterministic review gate, not an isolation mechanism.
