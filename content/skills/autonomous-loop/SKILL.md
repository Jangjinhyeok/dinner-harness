---
name: autonomous-loop
description: Complete authorized implementation with relevant checks and evidence-driven correction, preserving HIGH acceptance boundaries.
---

# Autonomous Implementation Loop

Read [autonomy policy](../../rules/autonomy-policy.md) for risk classification.
The user's request supplies the implementation authority already granted. Define observable
completion criteria, explain important risk and implement in the main session by default.
Ordinary clear tasks need no HANDOFF or role switch.
For nontrivial work, start with `Risk / rationale / verification / acceptance conditions`.
Risk is LOW/HIGH, distinct from Compute LOW/NORMAL/HIGH; this policy applies without Two-CLI.
At completion report planning, implementation, actual checks, independent review and human
acceptance separately, including unmet conditions. Planning alone leaves implementation/runtime
checks not_run. REQUEST CHANGES/FAIL fixes remain pending independent re-review, not PASS.

Preserve baseline user edits and requested scope. Follow the project's checks and
[verification-loop](../verification-loop/SKILL.md). Correct known deterministic failures
before spending review calls. Important changes benefit from one independent fresh-context
review; [adversarial-review](../adversarial-review/SKILL.md) describes the evidence contract.
More reviewers need distinct unresolved risks. Record self-review, execution records and
independent review separately, with not_run when unavailable.

Retry only with new evidence or a concrete correction; bound repeated external invocations
and report reasons. When blocked by unavailable scope/authority, preserve partial work.
LOW completion needs a result report. Authorized HIGH local implementation can proceed, then
requires independent review and human acceptance. Commit/push/deploy need their own authority.

Explicit headless dispatch retains its pinned HANDOFF/scope and controller delta checks.
Native hooks are capability-dependent and do not cover all I/O; inline is not automatically
equivalent to the controller net. Codex is not permanently missing native delegation.
