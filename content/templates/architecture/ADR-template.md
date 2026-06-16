# ADR-NNN: <short decision title>

> Architecture Decision Record. Consumed by the `architect`, `gameplay-programmer`
> (ADR Compliance), and `arch-review` flows. Copy to
> `docs/architecture/ADR-NNN-<slug>.md` and number sequentially.
> In the Two-CLI workflow the **Architect session authors and owns ADRs**; the
> Builder / specialist agents follow the **Implementation Guidelines** section exactly.

- **Status:** Proposed | Accepted | Superseded by ADR-MMM | Deprecated
- **Date:** `<YYYY-MM-DD>`
- **Deciders:** `<you / Architect session>`

## Context

<The problem, constraints, and forces. Why a decision is needed now. Call out
live-service compatibility, frame/memory budgets, and platform (mobile + PC)
constraints where relevant.>

## Decision

<The choice made, stated plainly in one or two sentences.>

## Implementation Guidelines

<Concrete rules the implementation MUST follow — the Builder/specialist agents
follow this section verbatim. Module/file boundaries, patterns to use and avoid,
interfaces, data layout, perf budgets. Be specific enough to review against.>

## Consequences

- **Positive:** `<benefits gained>`
- **Negative / trade-offs:** `<costs accepted>`
- **Follow-ups:** `<migrations, tech-debt logged via /tech-debt, future ADRs>`

## Alternatives considered

- **`<Option B>`** — rejected because `<reason>`
- **`<Option C>`** — rejected because `<reason>`
