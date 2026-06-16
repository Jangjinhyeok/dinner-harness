---
name: arch-review
description: "Performs an architectural and quality code review on a specified file or set of files. Checks for coding standard compliance, architectural pattern adherence, SOLID principles, testability, and performance concerns."
argument-hint: "[path-to-file-or-directory]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash, Task, AskUserQuestion
model: sonnet
agent: code-reviewer
---

## Phase 1: Load Target Files

Read the target file(s) in full. Read CLAUDE.md for project coding standards.

---

## Phase 2: Identify Engine Specialists

Read `.claude/docs/technical-preferences.md`, section `## Engine Specialists`. Note:

- The **Primary** specialist (used for architecture and broad engine concerns)
- The **Language/Code Specialist** (used when reviewing the project's primary language files)
- The **Shader Specialist** (used when reviewing shader files)
- The **UI Specialist** (used when reviewing UI code)

If the section reads `[TO BE CONFIGURED]`, no engine is pinned — skip engine specialist steps.

---

## Phase 3: ADR Compliance Check

**Argument:** `/arch-review [file(s)]` may optionally include a story file path as the last argument (e.g., `/arch-review src/combat/attack.gd production/epics/combat/story-001.md`). If a story path is provided, read it to extract the governing ADR reference.

Search for ADR references in, in priority order:
1. The story file (if provided as argument)
2. Header comments at the top of the implementation files
3. Commit messages referencing these files (`git log --oneline -- [file]`)

Look for patterns like `ADR-NNN` or `docs/architecture/ADR-`.

If no ADR references found, note: "No ADR references found — ADR compliance check skipped. For full ADR compliance review, provide the story path: `/arch-review [files] [story-path]`."

For each referenced ADR: read the file, extract the **Decision** and **Consequences** sections, then classify any deviation:

- **ARCHITECTURAL VIOLATION** (BLOCKING): Uses a pattern explicitly rejected in the ADR
- **ADR DRIFT** (WARNING): Meaningfully diverges from the chosen approach without using a forbidden pattern
- **MINOR DEVIATION** (INFO): Small difference from ADR guidance that doesn't affect overall architecture

---

## Phase 4: Standards Compliance

Identify the system category (engine, gameplay, AI, networking, UI, tools) and evaluate:

- [ ] Public methods and classes have doc comments
- [ ] Cyclomatic complexity under 10 per method
- [ ] No method exceeds 40 lines (excluding data declarations)
- [ ] Dependencies are injected (no static singletons for game state)
- [ ] Configuration values loaded from data files
- [ ] Systems expose interfaces (not concrete class dependencies)

---

## Phase 5: Architecture and SOLID

**Architecture:**
- [ ] Correct dependency direction (engine <- gameplay, not reverse)
- [ ] No circular dependencies between modules
- [ ] Proper layer separation (UI does not own game state)
- [ ] Events/signals used for cross-system communication
- [ ] Consistent with established patterns in the codebase

**SOLID:**
- [ ] Single Responsibility: Each class has one reason to change
- [ ] Open/Closed: Extendable without modification
- [ ] Liskov Substitution: Subtypes substitutable for base types
- [ ] Interface Segregation: No fat interfaces
- [ ] Dependency Inversion: Depends on abstractions, not concretions

---

## Phase 6: Game-Specific Concerns

- [ ] Frame-rate independence (delta time usage)
- [ ] No allocations in hot paths (update loops)
- [ ] Proper null/empty state handling
- [ ] Thread safety where required
- [ ] Resource cleanup (no leaks)

---

## Phase 7: Specialist Reviews (Parallel)

Spawn all applicable specialists simultaneously via Task — do not wait for one before starting the next.

### Engine Specialists

If an engine is configured, determine which specialist applies to each file and spawn in parallel:

- Primary language files (`.gd`, `.cs`, `.cpp`) → Language/Code Specialist
- Shader files (`.gdshader`, `.hlsl`, shader graph) → Shader Specialist
- UI screen/widget code → UI Specialist
- Cross-cutting or unclear → Primary Specialist

Also spawn the **Primary Specialist** for any file touching engine architecture (scene structure, node hierarchy, lifecycle hooks).

### QA Testability Review

For Logic and Integration changes, evaluate **testability directly** as part of this review — this skill runs as the `code-reviewer` agent and no separate QA agent is installed. Consider the implementation files plus any test cases / acceptance criteria the user provided (if the project keeps them), and check:
- [ ] Are all test hooks and interfaces exposed (not hidden behind private/internal access)?
- [ ] Do the intended test cases map to testable code paths?
- [ ] Are any acceptance criteria untestable as implemented (e.g., hardcoded values, no seam for injection)?
- [ ] Does the implementation introduce new edge cases not covered by existing tests?
- [ ] Are there observable side effects that should have a test but don't?

For Visual/Feel and UI changes: review whether the manual verification steps are achievable with the implementation as written — e.g., "is the state the manual checker needs to reach actually reachable?"

Collect all specialist findings before producing output.

---

## Phase 8: Output Review

```
## Code Review: [File/System Name]

### Engine Specialist Findings: [N/A — no engine configured / CLEAN / ISSUES FOUND]
[Findings from engine specialist(s), or "No engine configured." if skipped]

### Testability: [N/A — Visual/Feel or Config story / TESTABLE / GAPS / BLOCKING]
[Testability findings: test hooks, coverage gaps, untestable paths, new edge cases]
[If BLOCKING: implementation must expose [X] before tests in ## QA Test Cases can run]

### ADR Compliance: [NO ADRS FOUND / COMPLIANT / DRIFT / VIOLATION]
[List each ADR checked, result, and any deviations with severity]

### Standards Compliance: [X/6 passing]
[List failures with line references]

### Architecture: [CLEAN / MINOR ISSUES / VIOLATIONS FOUND]
[List specific architectural concerns]

### SOLID: [COMPLIANT / ISSUES FOUND]
[List specific violations]

### Game-Specific Concerns
[List game development specific issues]

### Positive Observations
[What is done well -- always include this section]

### Required Changes
[Must-fix items before approval — ARCHITECTURAL VIOLATIONs always appear here]

### Suggestions
[Nice-to-have improvements]

### Verdict: [APPROVED / APPROVED WITH SUGGESTIONS / CHANGES REQUIRED]
```

This skill is read-only — no files are written.

---

## Phase 9: Next Steps

Use `AskUserQuestion`:
- Prompt: "Code review complete — verdict: [APPROVED / CHANGES REQUIRED / MAJOR REVISION]. How would you like to proceed?"
- Options (adjust based on verdict):
  - If APPROVED:
    - `[A] Mark the work complete and proceed`
    - `[B] Stop here`
  - If CHANGES REQUIRED or MAJOR REVISION:
    - `[A] Fix the issues and re-run /arch-review`
    - `[B] Accept the work with noted exceptions (record them for the user)`
    - `[C] Stop here`

If an ARCHITECTURAL VIOLATION is found:
- If the violation contradicts an **existing ADR** (`docs/architecture/[adr-file].md`, if the project keeps them): fix the implementation to comply. If the design has legitimately changed, raise it with the user (Architect session) to formally *revise* the existing ADR — do not create a competing one.
- If **no ADR exists** for the violated pattern: raise it with the user (Architect session) to decide and document the correct approach before fixing the code.
