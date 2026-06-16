---
name: hotfix
description: "Emergency fix workflow that bypasses normal process with a full audit trail. Assesses severity, creates a hotfix record + branch, enforces a minimal-change discipline, and documents a rollback plan. Use only when invoked with /hotfix."
argument-hint: "[bug-id or description]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Write, Edit, Bash, Task, AskUserQuestion
model: sonnet
---

> **Explicit invocation only**: run only when the user requests `/hotfix`. Do not
> auto-invoke from context. The director/lead/QA tiers from the source studio model
> are **not installed here** — wherever the original needed sign-off from those roles,
> this version routes to **the user (Architect session)** or the installed
> `code-reviewer`. (See `rules/agent-routing.md`.)

## Phase 1: Assess Severity

Read the bug description/ID. Assess severity:

- **S1 (Critical)**: game unplayable, data loss, security vulnerability
- **S2 (Major)**: significant feature broken, workaround exists
- **S3 or lower**: minor — normal bug fix workflow applies

Confirm with `AskUserQuestion`:
- Prompt: "I've assessed this as **[severity]** — [rationale]. Confirm to proceed:"
- Options:
  - `[A] S1 (Critical) — unplayable / data loss / security`
  - `[B] S2 (Major) — significant feature broken, workaround exists`
  - `[C] S3 or lower — redirect to normal bug fix`

If [C]: stop. Verdict: **REDIRECTED** — use the normal bug fix workflow.

---

## Phase 2: Create Hotfix Record

Draft the record:

```markdown
## Hotfix: [Short Description]
Date: [Date]
Severity: [S1/S2]
Reporter: [who found it]
Status: IN PROGRESS

### Problem
[What is broken and the player impact]

### Root Cause
[Filled during investigation]

### Fix
[Filled during implementation]

### Testing
[What was tested and how]

### Approvals
- [ ] Fix reviewed (code-reviewer agent, or the user)
- [ ] Regression checked on affected + adjacent systems (the user confirms)
- [ ] Release approved (the user)

### Rollback Plan
[How to revert if the fix causes new issues]
```

Ask: "May I write this to `docs/hotfixes/hotfix-[date]-[short-name].md`?"
If yes, write the file, creating the directory if needed.

---

## Phase 3: Create Hotfix Branch

Check for git: `git rev-parse --is-inside-work-tree 2>/dev/null`. If it fails/empty,
note "Not a git repository — create the branch manually" and skip to Phase 4.

If git is present, confirm with `AskUserQuestion`:
- Prompt: "Create hotfix branch `hotfix/[short-name]` from [base-ref]?"
- Options: `[A] Yes — create branch` / `[B] Different base ref — I'll specify` / `[C] Skip — I'll branch myself`

Run `git checkout -b hotfix/[short-name] [base-ref]` only on [A]. On [B], ask for the
ref then run it. On [C], skip.

---

## Phase 4: Investigate and Implement

Focus on the **minimal change** that resolves the issue. Do NOT refactor, clean up, or
add features alongside the hotfix (surgical-changes, CLAUDE.md §1.3).

Validate by running targeted tests for the affected system. Check adjacent systems for
regressions. Update the hotfix record with root cause, fix, and test results.

---

## Phase 5: Review & Release Approval

The studio's parallel sign-off (lead-programmer / qa-tester / producer) is replaced by:

1. **Code review** — optionally spawn `code-reviewer` via Task to review the fix for
   correctness and side effects (`subagent_type: code-reviewer`). For C++ changes use
   `cpp-reviewer`. Address CRITICAL/HIGH findings before proceeding.
2. **Release approval** — present the fix + risk to **the user** and get an explicit
   go. The user (Architect session) owns the release decision.

If review surfaces unresolved CRITICAL/HIGH issues, do NOT proceed — fix first.

---

## Phase 5b: QA Re-Entry Gate

Before deploying, decide the QA scope (the user confirms):

- Use Grep to list callers of the changed files — enumerate every system that touches them.
- Run the targeted tests for the affected system.
- **Light fix, isolated** → a focused smoke pass of the affected flow is sufficient.
- **Touches core / many callers** → run the broader regression set for the impacted systems before deploying.

Do not skip this gate. A hotfix that breaks something else is worse than the original bug.

---

## Phase 6: Update Bug Status and Prepare Deploy

If a bug file exists, update its header:

```markdown
## Fix Record
**Fixed in**: hotfix/[branch] — [commit hash]
**Fixed date**: [date]
**Status**: Fixed — Pending Verification
```

Output a deployment summary:

```
## Hotfix Ready to Deploy: [short-name]

**Severity**: [S1/S2]
**Root cause**: [one line]
**Fix**: [one line]
**QA**: [smoke pass / regression set — result]
**Review**: code-reviewer ✓ / release approved by user ✓
**Rollback plan**: [from Phase 2]

Merge to: release branch AND development branch
```

---

## Phase 7: Post-Deploy Verification

After deploying, verify the fix resolved the issue in the deployed build.
- **Verified fixed** → close the bug record; set Status: Fixed — Verified.
- **Still present** → the hotfix failed: re-open, assess rollback (Phase 2 plan), and escalate to the user immediately.

Schedule a short post-incident note within 48h (what broke, why, prevention).

`AskUserQuestion`:
- Prompt: "Hotfix complete. Next step?"
- Options:
  - `[A] Document this hotfix with /changelog`
  - `[B] Write the post-incident note now`
  - `[C] Stop here`

### Rules

- Hotfixes must be the MINIMUM change — no cleanup, no refactoring.
- Every hotfix must have a documented rollback plan before deployment.
- Hotfix branches merge to BOTH the release branch AND the development branch.
- All hotfixes get a post-incident note within 48 hours.
- If the fix needs more than ~4 hours or grows structural, escalate to the user (Architect session) — it may not be a hotfix.
