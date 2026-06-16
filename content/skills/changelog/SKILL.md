---
name: changelog
description: "Auto-generates a changelog from git commits (and optional planning docs). Produces both an internal and a player-facing version. Use for release notes / 'what changed since last version'."
argument-hint: "[version|tag|since-date]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash, Write
context: |
  !git log --oneline -30 2>/dev/null
  !git tag --list --sort=-v:refname 2>/dev/null | head -5
model: haiku
---

# Changelog

Generates an **internal** changelog (technical, for you) and a **player-facing**
changelog (community-ready) from git history.

## Phase 1: Parse Arguments

Read the argument for the target version, tag, or date range. If a version/tag is
given, use the corresponding git tag. If a date is given, use it as the lower bound.

Verify the repository is initialized: run `git rev-parse --is-inside-work-tree`. If
not a git repo, inform the user and abort gracefully.

---

## Phase 2: Gather Change Data

Read the git log since the last tag or the given bound:

```
git log --oneline [last-tag]..HEAD
```

If no tags exist, use a reasonable recent range (e.g. last 100 commits).

**Optional context (only if the project keeps them):** read any planning docs the
project maintains — `docs/architecture/` ADRs, a HANDOFF.md spec, or a design doc the
user points to — to understand the intent behind changes. Do not assume a specific
team-process layout exists; rely on the git log as the primary source.

---

## Phase 3: Categorize Changes

Categorize every change:

- **New Features**: new gameplay systems, modes, or content
- **Improvements**: enhancements to existing features, UX, performance
- **Bug Fixes**: corrections to broken behavior
- **Balance Changes**: tuning of gameplay values, difficulty, economy
- **Known Issues**: known but unresolved
- **Miscellaneous**: anything that doesn't fit, or commits too vague to classify

For each commit, note any task/issue reference (e.g. `#NNN`, `ADR-NNN`, an issue ID).
Count commits with no reference and report it in Metrics as `Commits without task reference: [N]`.

---

## Phase 4: Generate Internal Changelog

```markdown
# Internal Changelog: [Version]
Date: [Date]
Range: [first-hash]..[last-hash] ([Count] commits)

## New Features
- [Feature] -- [technical description, affected systems]
  - Commits: [hashes]
  - Reference: [ADR / issue if any]

## Improvements
- [Improvement] -- [what changed technically and why]
  - Commits: [hashes]

## Bug Fixes
- [Description and root cause]
  - Fix: [what changed]
  - Commits: [hashes]

## Balance Changes
- [What was tuned] -- [old -> new] -- [design intent]

## Technical Debt / Refactoring
- [What was cleaned up and why]
  - Commits: [hashes]

## Miscellaneous
- [Change that didn't fit, or vague commit]
  - Commits: [hashes]

## Known Issues
- [Issue] -- [Severity] -- [ETA if known]

## Metrics
- Total commits: [N]
- Files changed: [N]
- Lines +/-: [N] / [N]
- Commits without task reference: [N]
```

---

## Phase 5: Generate Player-Facing Changelog

```markdown
# What's New in [Version]

## New Features
- **[Feature]**: [player-friendly description — the experience, not the implementation]

## Improvements
- **[What improved]**: [how this makes the game better, no jargon]

## Bug Fixes
- Fixed an issue where [what the player experienced]

## Balance Changes
- [Player-understandable change + design intent. e.g. "Healing potions now restore
  50 HP (up from 30) — late-game encounters needed more recovery options."]

## Known Issues
- We're aware of [issue in player terms] and are working on a fix. [Workaround if any.]
```

---

## Phase 6: Output

Output both changelogs. The internal one is the working document; the player-facing
one is ready for community posting after your review.

---

## Phase 7: Offer File Write

Check whether `docs/CHANGELOG.md` exists, then ask:

> "May I write this changelog to `docs/CHANGELOG.md`?
> [A] Yes, append this entry (recommended if the file exists)
> [B] Yes, overwrite the file
> [C] No — I'll copy it manually"

- [A]: prepend the new internal entry to the top (newest first).
- [B]: overwrite.
- [C]: stop without writing.

After a successful write: Verdict: **CHANGELOG WRITTEN**. If declined: Verdict: **COMPLETE**.

---

## Phase 8: Next Steps

- Review the player-facing section before posting it publicly (strip any internal
  references, file paths, or names that slipped through).

### Guidelines

- Never expose internal code references, file paths, or developer names in the player-facing version.
- Group related changes; don't list raw individual commits.
- If a commit message is unclear, check the changed files for context.
- Balance changes should include the design reasoning, not just the numbers.
- Known issues should be honest — players appreciate transparency.
- If git history is messy (merges, reverts, fixups), write the narrative rather than listing every commit literally.
