---
name: perf-profile
description: "Structured performance profiling workflow. Identifies bottlenecks, measures against budgets, and generates optimization recommendations with priority rankings."
argument-hint: "[system-name or 'full']"
user-invocable: true
agent: performance-analyst
allowed-tools: Read, Glob, Grep, Bash
model: sonnet
context: fork
---

## Phase 1: Determine Scope

Read the argument:

- System name → focus profiling on that specific system
- `full` → run a comprehensive profile across all systems

---

## Phase 2: Load Performance Budgets

Check performance targets in project instructions (AGENTS.md or the selected vendor entrypoint) and design docs:

- Target FPS (e.g., 60fps = 16.67ms frame budget)
- Memory budget (total and per-system)
- Load time targets
- Draw call budgets
- Network bandwidth limits (if multiplayer)

---

## Phase 3: Analyze Codebase

**CPU Profiling Targets:**
- `_process()` / `Update()` / `Tick()` functions — inspect paths relevant to the requested workload
- Nested loops over large collections
- String operations in hot paths
- Allocation patterns in per-frame code
- Unoptimized search/sort over game entities
- Expensive physics queries (raycasts, overlaps) every frame

**Memory Profiling Targets:**
- Large data structures and their growth patterns
- Texture/asset memory footprint estimates
- Object pool vs instantiate/destroy patterns
- Leaked references (objects that should be freed but aren't)
- Cache sizes and eviction policies

**Rendering Targets (if applicable):**
- Draw call estimates
- Overdraw from overlapping transparent objects
- Shader complexity
- Unoptimized particle systems
- Missing LODs or occlusion culling

**I/O Targets:**
- Save/load performance
- Asset loading patterns (sync vs async)
- Network message frequency and size

---

## Phase 4: Generate Profiling Report

```markdown
## Performance Profile: [System or Full]
Generated: [Date]

### Performance Budgets
| Metric | Budget | Estimated Current | Status |
|--------|--------|-------------------|--------|
| Frame time | [16.67ms] | [estimate] | [OK/WARNING/OVER] |
| Memory | [target] | [estimate] | [OK/WARNING/OVER] |
| Load time | [target] | [estimate] | [OK/WARNING/OVER] |
| Draw calls | [target] | [estimate] | [OK/WARNING/OVER] |

### Hotspots Identified
| # | Location | Issue | Estimated Impact | Fix Effort |
|---|----------|-------|------------------|------------|

### Optimization Recommendations (Priority Order)
1. **[Title]** — [Description]
   - Location: [file:line]
   - Expected gain: [estimate]
   - Risk: [LOW/HIGH] — [rationale per autonomy policy]
   - Approach: [How to implement]

### Low-cost Improvements
- [Simple optimization 1]

### Requires Investigation
- [Area that needs actual runtime profiling to confirm impact]
```

Use [autonomy policy](../../rules/autonomy-policy.md) for Risk LOW/HIGH, independent review
and human acceptance. Risk is distinct from estimated effort or Compute LOW/NORMAL/HIGH.
Output the report with a summary: evidence-backed hotspots, estimated headroom vs budget, and recommended next action.

---

## Phase 5: Recommendations and Scope

Finish a profiling/report request with prioritized findings; medium/large effort alone
does not require a per-item decision or separate Architect session. Recommend implement,
investigate or defer with reasons. Do not write a register or begin optimization unless
requested. Existing implementation authorization covers routine in-scope refinements;
ask only for a material scope, compatibility or authority change.

---

## Phase 6: Next Steps

- If a recommendation would change scope or a meaningful invariant: describe the decision needed.
- If scope reduction is needed: discuss the trade-offs with the user.
- To schedule optimizations: note them as follow-up items for the user to prioritize.

### Rules
- Use measurements to select and validate optimizations; source inspection can identify candidates,
  but is not proof of runtime impact
- State measured impact or a clearly qualified estimate and confidence; unknown is valid when
  runtime evidence is unavailable. Do not invent headroom, timing or expected gains from source alone.
- Profile on target hardware, not just development machines
- Static analysis (this skill) identifies candidates; runtime profiling confirms
