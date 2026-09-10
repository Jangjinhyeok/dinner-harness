---
name: delegate
description: Explicitly hand a bounded LOW task to the optional headless Builder and review its result.
---

# Optional Delegation

This compatibility skill is not the default Codex inline path. Use when the user explicitly wants
a bounded task delegated and headless controller checks are appropriate. The main session retains
completion responsibility. Follow [dispatch reference](../../rules/two-cli-reference.md).

Read the request, baseline and existing implementation. LOW risk is not a file-count threshold;
HIGH requires the corresponding challenge/review/acceptance contract. Write a self-contained
HANDOFF_DELEGATE.md only for this selected dispatch, preserving any existing HANDOFF.
Include exact scope (including report/verification artifacts), risk/compute and project checks.
Do not whitelist source documents when only derived outputs should change.

Invoke the active harness home's orchestrate.py build with an explicit repository and handoff.
Do not force a vendor pairing, open a visible shell, inspect private rollout files or use --last
as task identity. Keep one writer per tree. Review RESULT and the actual baseline delta after
dispatch; BUILT is not independent review or acceptance evidence.

Report no-op, partial edits, command/output failures and not_run reviews honestly.
Never retry implementation just to fabricate a changeset. Preserve branch and explicit commit/push
authority. Do not silently fallback to another vendor or a live installation.
