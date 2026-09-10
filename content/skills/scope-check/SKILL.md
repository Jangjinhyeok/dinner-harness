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
> spirit (it reinforces the surgical-changes principle).

Read-only — reports findings, writes no files. Compares the original planned scope
against the current state to detect, quantify, and triage scope creep.

**Argument:** `$ARGUMENTS[0]` — feature name, work cycle, or milestone.

---

## Phase 1: Find the Original Plan

Locate the baseline scope for the given argument, in this order:

- The accepted user request and corrections in the current conversation (ordinary inline work needs no HANDOFF).

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
4. **Flag**: [items needing a material scope decision from the user]
```

---

## Phase 4: Verdict

Use the project's accepted scope and tolerances to judge schedule, quality and integration
impact. Item counts describe the change; they do not establish severity or mandate stopping
by themselves. Report percentages only when baseline items are comparable and the denominator
is meaningful. Otherwise describe concrete additions, removals and their impact.

```
**Scope Verdict: [PASS / CONCERNS / FAIL]**
Net change: [+X%] — [On Track / Minor Creep / Significant Creep / Out of Control]
```

---

## Phase 5: Next Steps

- **PASS** → no action. Suggest re-running before the next milestone.
- **CONCERNS** → identify the additions whose removal best preserves the core outcome; recommend targeted cuts.
- **FAIL** → explain the material scope decision needed. A separate Architect session or new ADR is not required; follow existing project decision records when relevant.

After actual scope changes, recommend comparing them with the accepted baseline again.

---

### Rules

- Scope creep = additions without corresponding cuts or timeline extensions.
- Not all additions are bad — some are discovered requirements. But they must be acknowledged and accounted for.
- When recommending cuts, preserve the core player experience over nice-to-haves.
- Quantify comparable work where possible; do not invent precision for incomparable items.
