---
name: eval-harness
description: Define behavioral capability and regression cases for agent workflows with explicit graders and measured attempts.
---

# Evaluation Harness

Use for prompt/agent evaluation or reusable acceptance cases; ordinary code edits need no new
framework. Define outcomes, allowed effects, baseline and grader before execution. Include
realistic capability and regression cases. Use existing eval storage or `docs/evals/` when
persistent artifacts were requested; do not require vendor homes or nonexistent commands.

Deterministic graders check observable behavior with project tooling. Model graders use a rubric
and independent context. Human graders handle required acceptance. Keep the evidence types
separate: a model's PASS statement is not a command execution record.

Record actual attempts, outcomes, latency and provided usage, with redacted summaries.
pass@k means at least one success in k attempts; pass^k requires every trial to succeed.
Do not infer reliability percentages from one successful run or impose universal thresholds.
Predeclare retry budgets for comparisons, keep cases consistent, and separate unavailable live
validation from fake subprocess/unit tests. Metrics do not grant release authority.
Include failure paths as well as happy paths, and keep evaluation cases separate from examples
used to tune the prompt. Distinguish flaky graders from agent failures; compare cost and latency
alongside pass rates rather than improving the score by hiding those tradeoffs.
