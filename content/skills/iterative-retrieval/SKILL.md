---
name: iterative-retrieval
description: Pattern for progressively refining context retrieval to solve the subagent context problem
origin: ECC
---

# Iterative Retrieval

Use when local exploration or a delegated task lacks specific context. Start with the request,
project instructions and known entry points; search repository terms and follow relevant callers,
types, ownership and tests. Do not exclude tests merely because they are not implementation.

After each useful search, identify what remains unknown and refine queries using discovered
names and dependencies. Revisit an excluded area if new evidence connects it to the task.
Stop when the required behavior, contracts and verification are understood, or when further
search has no concrete lead; report material gaps instead of guessing. Respect actual task/tool
budgets without imposing universal cycle counts, relevance scores or minimum file counts.

When an independent subtask is useful, send the bounded question, relevant files, constraints,
known evidence and remaining gaps. Return evidence and limitations to the parent. Native
agents are optional; the same retrieval works in the main session without an orchestration layer.
