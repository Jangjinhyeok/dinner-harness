---
name: adversarial-review
description: Perform evidence-based independent review of important changes, adding specialists only for distinct unresolved risks.
---

# Independent Review

Read [autonomy policy](../../rules/autonomy-policy.md). Review is read-only.
Use the explicit `code-reviewer` role for general review or `cpp-reviewer` for C++ specialist review,
following [agent routing](../../rules/agent-routing.md). A review task name on a `default` agent does
not select the reviewer profile. Record the reason for an exceptional role/model choice; distinguish
independent review from requested/observed model agreement, and mark unavailable model evidence unknown.
Give one available native reviewer a fresh context with the latest requested outcome and completion
conditions, removal/change targets and constraints to preserve, baseline delta and unresolved findings.
Include the actual execution path/callers, revision plus staged/unstaged/untracked state, relevant
artifact or job/run, and executed checks with results and not_run limits. Use the existing dispatch
message or handoff; no new document is required. Missing essential inputs must remain explicit,
not be replaced by the author's desired verdict.
A design challenge examines the proposed approach; a post-implementation review examines the code.
Reassess risk from the actual diff rather than trusting the caller's label; retain HIGH
when either the declaration or supported review findings requires it.

Find demonstrable correctness, security, compatibility, ownership or performance defects.
Return PASS, FAIL with required fixes, or BLOCKED for unavailable essential evidence.
Support findings with file/line evidence and consequences. Do not invent defects or demand
rework for style preferences. Additional specialists need distinct unresolved review axes;
there is no fixed judge count or majority/unanimity vote.

Record who actually reviewed and the evidence. If delegation cannot run, record
`independent_review=not_run`; self-review does not satisfy HIGH independent review.
HIGH remains pending human acceptance. Builder `panel=PASS` is not proof of a reviewer.
REQUEST CHANGES/FAIL fixes are an author's response, not a re-review PASS. Record the original
verdict and `fixes applied; re-review pending` until an independent reviewer examines the changed
artifact and evidence. Keep design review separate from post-implementation review.
State which files, logs and images you actually inspected and which claims came from the parent.
Check that evidence targets the reviewed state; stale, blank or uninspected previews cannot support
visual PASS. Keep that check not_run unless the actual target was observed failing (FAIL).
Use the latest requested outcome: compile success does not justify retaining a removed feature
as hidden bindings/widgets or placeholders without a required compatibility contract.
Preserve controller repo/task challenge caps. Do not repeat review without relevant new changes
or missing evidence to resolve.
