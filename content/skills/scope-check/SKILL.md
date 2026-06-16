---
name: scope-check
description: "Audit a feature or work cycle for scope creep by comparing current scope against the original plan. Flags additions, quantifies bloat, recommends cuts. Use when user says 'any scope creep', 'scope review', 'are we staying in scope'."
argument-hint: "[feature-name or cycle/milestone]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash
model: haiku
context: fork
agent: Explore
---

# Scope Check

> **Not the `scope_check` PreToolUse hook.** That hook enforces *file-level* edit
> scope during Builder cycles (settings.json wiring). This `/scope-check` skill is a
> manually-invoked *feature/cycle-level* scope-creep audit. Different mechanism, same
> spirit (it reinforces the surgical-changes principle, CLAUDE.md §1.3).

Read-only — reports findings, writes no files. Compares the original planned scope
against the current state to detect, quantify, and triage scope creep.

**Argument:** `$ARGUMENTS[0]` — feature name, work cycle, or milestone.

---

## Phase 1: Find the Original Plan

Locate the baseline scope for the given argument, in this order:

- The feature's **HANDOFF.md** spec (the `scope` codeblock / task description), if this
  was a Two-CLI cycle.
- A governing **ADR** under `docs/architecture/` for the feature/system.
- Any planning doc the user points to.
- If none exists, **ask the user to state the original intended scope** in one or two
  lines, and use that as the baseline.

Do not proceed without a baseline — "it feels bigger" is not auditable.

---

## Phase 2: Read the Current State

Check what was actually implemented or is in progress:

- Scan the codebase for files related to the feature/cycle.
- Read the git log for related commits (`git log --oneline --since=[start-date]`).
- Check TODO/FIXME comments that indicate unfinished or added scope.

---

## Phase 3: Compare Original vs Current

```markdown
## Scope Check: [Feature/Cycle]
Generated: [Date]

### Original Scope
[items from the baseline]

### Current Scope
[items currently implemented or in progress]

### Scope Additions (not in original plan)
| Addition | Source (commit) | When | Justified? | Effort |
|----------|-----------------|------|------------|--------|
| [item] | [hash] | [date] | [Yes/No/Unclear] | [S/M/L] |

### Scope Removals (in original but dropped)
| Removed Item | Reason | Impact |
|-------------|--------|--------|
| [item] | [why] | [what's affected] |

### Bloat Score
- Original items: [N] / Current items: [N]
- Added: [N] (+[X]%) / Removed: [N]
- Net scope change: [+/-N] ([X]%)

### Risk Assessment
- **Schedule Risk**: [Low/Med/High] — [why]
- **Quality Risk**: [Low/Med/High] — [why]
- **Integration Risk**: [Low/Med/High] — [why]

### Recommendations
1. **Cut**: [remove to stay on track]
2. **Defer**: [move to a later cycle/version]
3. **Keep**: [additions genuinely necessary]
4. **Flag**: [items needing a decision from the user / Architect session]
```

---

## Phase 4: Verdict

| Net Change | Verdict | Meaning |
|-----------|---------|---------|
| ≤10% | **PASS** | On track — within acceptable variance |
| 10–25% | **CONCERNS** | Minor creep — manageable with targeted cuts |
| 25–50% | **FAIL** | Significant creep — must cut or extend timeline |
| >50% | **FAIL** | Out of control — stop, re-plan |

```
**Scope Verdict: [PASS / CONCERNS / FAIL]**
Net change: [+X%] — [On Track / Minor Creep / Significant Creep / Out of Control]
```

---

## Phase 5: Next Steps

- **PASS** → no action. Suggest re-running before the next milestone.
- **CONCERNS** → identify the 2–3 additions with the best cut ratio; raise re-scoping with the user (Architect session).
- **FAIL** → raise with the user (Architect session) to re-baseline the plan or formally extend scope. Record the decision as an ADR if the change is structural.

Always end with:
> "Run `/scope-check [name]` again after cuts are made to verify the verdict improves."

---

### Rules

- Scope creep = additions without corresponding cuts or timeline extensions.
- Not all additions are bad — some are discovered requirements. But they must be acknowledged and accounted for.
- When recommending cuts, preserve the core player experience over nice-to-haves.
- Always quantify — "+35% items" is actionable, "it feels bigger" is not.
