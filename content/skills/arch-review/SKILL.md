---
name: arch-review
description: Review a specified change for correctness, architecture, compatibility, testability and performance without modifying files.
---

# Architecture and Code Review

Read requested files, project instructions, relevant callers/tests and the baseline diff,
including staged, unstaged and untracked changes. Follow governing ADRs when present;
absence of an ADR alone is not a defect.
Find governing decisions through a supplied story/spec, file headers or relevant commit history.
Distinguish a rejected architectural pattern from lesser drift; if the design has changed,
recommend revising the governing ADR instead of creating a competing decision.

Trace ownership, lifetime, invariants, dependencies and failure handling. For games examine
frame costs, resource cleanup, threading, replication and save compatibility. Read relevant
specialist documents under the active harness install root's `docs/specialists/`.
Use actual project conventions, not universal line-count or interface requirements.

Evaluate behavioral test coverage and acceptance criteria. Report concrete defects with file/line
evidence, severity and consequence; distinguish optional style suggestions. PASS is appropriate
when no material defect is found; essential missing evidence is BLOCKED.
For manual UI/feel checks, verify that the required state is reachable and its result observable.

One fresh-context reviewer is useful for important changes. Add specialists only for distinct
unresolved risks. If unavailable, label a direct review honestly, not independent review.
This skill is read-only and ends with findings; do not request routine completion consent or
apply fixes unless implementation was also requested.
