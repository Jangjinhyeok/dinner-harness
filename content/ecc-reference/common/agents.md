---
paths: []
---

# Agent Orchestration

## Available Agents

실제 설치된 agent는 `~/.claude/agents/` 하위 4개 묶음에 있다 (정본은 그 디렉터리):

- `_core/` — architect, code-reviewer, cpp-build-resolver, cpp-reviewer, planner, tdd-guide
- `_gamedev/` — gameplay-programmer, network-programmer, performance-analyst, tools-programmer, ui-programmer
- `_ue/` — unreal-specialist, ue-blueprint-specialist, ue-gas-specialist, ue-replication-specialist, ue-umg-specialist
- `_unity/` — unity-specialist, unity-addressables-specialist, unity-dots-specialist, unity-shader-specialist, unity-ui-specialist

## Immediate Agent Usage

No user prompt needed:
1. Complex feature requests - Use **planner** agent
2. Code just written/modified - Use **code-reviewer** agent
3. Bug fix or new feature - Use **tdd-guide** agent
4. Architectural decision - Use **architect** agent

## Parallel Task Execution

ALWAYS use parallel Task execution for independent operations:

```markdown
# GOOD: Parallel execution
Launch 3 agents in parallel:
1. Agent 1: Security analysis of auth module
2. Agent 2: Performance review of cache system
3. Agent 3: Type checking of utilities

# BAD: Sequential when unnecessary
First agent 1, then agent 2, then agent 3
```

## Multi-Perspective Analysis

For complex problems, use split role sub-agents:
- Factual reviewer
- Senior engineer
- Security expert
- Consistency reviewer
- Redundancy checker
