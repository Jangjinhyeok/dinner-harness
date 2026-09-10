---
name: adversarial-review
description: Perform evidence-based independent review of important changes, adding specialists only for distinct unresolved risks.
---

# Independent Review

Read [autonomy policy](../../rules/autonomy-policy.md). Review is read-only.
Give one available native reviewer a fresh context with the requested outcome, baseline diff,
affected callers and actual verification records, not the author's desired verdict.
A design challenge examines the proposed approach; a post-implementation review examines the code.

Find demonstrable correctness, security, compatibility, ownership or performance defects.
Return PASS, FAIL with required fixes, or BLOCKED for unavailable essential evidence.
Support findings with file/line evidence and consequences. Do not invent defects or demand
rework for style preferences. Additional specialists need distinct unresolved review axes;
there is no fixed judge count or majority/unanimity vote.

Record who actually reviewed and the evidence. If delegation cannot run, record
`independent_review=not_run`; self-review does not satisfy HIGH independent review.
HIGH remains pending human acceptance. Builder `panel=PASS` is not proof of a reviewer.
Preserve controller repo/task challenge caps. Do not repeat review without relevant new changes
or missing evidence to resolve.
