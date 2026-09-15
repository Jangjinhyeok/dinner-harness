---
name: goal-driven-execution
description: Turn unclear completion criteria into observable outcomes and a proportionate implementation plan.
---

# Goal-Driven Execution

Infer the outcome from the request and existing behavior, state material assumptions, and ask
only about choices changing scope or outcome. For multistep work give a short plan connecting
meaningful changes to verification; ordinary inline work needs no plan file or HANDOFF.
For nontrivial work, including planning-only requests, read the unchanged session copy or original
[autonomy policy](../../rules/autonomy-policy.md). Start with `Risk / rationale / verification /
acceptance conditions`. Risk LOW/HIGH is separate from Compute LOW/NORMAL/HIGH and applies
without Two-CLI. Report plan completion separately from implementation, actual verification,
independent review and HIGH human acceptance; keep unmet conditions visible.

A bug fix should reproduce failure and check corrected behavior. A refactor should preserve
relevant observable behavior. Add a useful regression test when justified; small reversible
changes can use inspection or existing targeted checks. UI/runtime work may need a manual scenario.
Compilation is one check, not the outcome itself. When a feature is removed, define the required
removal boundary across callers, bindings, hierarchy, references and metadata. Update obsolete
contracts together; keep a placeholder only for a stated compatibility requirement, not merely
to silence errors. Judge acceptance against the latest user requirement.

Continue authorized implementation and checks without repeated consent. Report actual outcomes,
pre-existing failures and unavailable checks separately.
