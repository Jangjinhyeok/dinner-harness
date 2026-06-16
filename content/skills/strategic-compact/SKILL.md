---
name: strategic-compact
description: Suggests manual context compaction at logical intervals to preserve context through task phases rather than arbitrary auto-compaction.
origin: ECC
---

# Strategic Compact Skill

Suggests manual `/compact` at strategic points in your workflow rather than relying on arbitrary auto-compaction.

## When to Activate

- Running long sessions that approach context limits (200K+ tokens)
- Working on multi-phase tasks (research → plan → implement → test)
- Switching between unrelated tasks within the same session
- After completing a major milestone and starting new work
- When responses slow down or become less coherent (context pressure)

## Why Strategic Compaction?

Auto-compaction triggers at arbitrary points:
- Often mid-task, losing important context
- No awareness of logical task boundaries
- Can interrupt complex multi-step operations

Strategic compaction at logical boundaries:
- **After exploration, before execution** — Compact research context, keep implementation plan
- **After completing a milestone** — Fresh start for next phase
- **Before major context shifts** — Clear exploration context before different task

## How It Works

The `suggest_compact` PreToolUse hook (Edit/Write) runs on every matching tool call and:

1. **Tracks tool calls** — Counts per-session invocations (state under `hooks/logs/`)
2. **Threshold detection** — Suggests at configurable threshold (default: 50 calls)
3. **Periodic reminders** — Reminds every 25 calls after threshold
4. **Advisory only** — Writes the suggestion to stderr and always exits 0; it never blocks a tool call.

The skill is also usable **manually** via `/strategic-compact` — the hook only adds automatic interval reminders.

## Hook Setup (Windows)

This follows the project hook convention in `hooks/README.md` — a Python handler under `hooks/handlers/` invoked through an argument-free absolute-path `.cmd` launcher (required by the Windows hook command escaping workaround). The implementation is staged in this skill dir:

- `suggest_compact.py` → install to `hooks/handlers/suggest_compact.py`
- `suggest_compact.cmd` → install to `hooks/launchers/suggest_compact.cmd`

Because `hooks/handlers/`, `hooks/launchers/`, and `settings.json` are **always-block** under `scope_check`, installation requires the off-ceremony (see `hooks/README.md` → "off ceremony"): launch a fresh session with `CLAUDE_SCOPE_WHITELIST_MODE=off`, move the two staged files into place, then register the launcher in `settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [{ "type": "command", "command": "C:/Users/<USERNAME>/.claude/hooks/launchers/suggest_compact.cmd" }]
      }
    ]
  }
}
```

## Configuration

Environment variables:
- `COMPACT_THRESHOLD` — Tool calls before first suggestion (default: 50)

## Compaction Decision Guide

Use this table to decide when to compact:

| Phase Transition | Compact? | Why |
|-----------------|----------|-----|
| Research → Planning | Yes | Research context is bulky; plan is the distilled output |
| Planning → Implementation | Yes | Plan is in TodoWrite or a file; free up context for code |
| Implementation → Testing | Maybe | Keep if tests reference recent code; compact if switching focus |
| Debugging → Next feature | Yes | Debug traces pollute context for unrelated work |
| Mid-implementation | No | Losing variable names, file paths, and partial state is costly |
| After a failed approach | Yes | Clear the dead-end reasoning before trying a new approach |

## What Survives Compaction

Understanding what persists helps you compact with confidence:

| Persists | Lost |
|----------|------|
| CLAUDE.md instructions | Intermediate reasoning and analysis |
| TodoWrite task list | File contents you previously read |
| Memory files (`~/.claude/memory/`) | Multi-step conversation context |
| Git state (commits, branches) | Tool call history and counts |
| Files on disk | Nuanced user preferences stated verbally |

## Best Practices

1. **Compact after planning** — Once plan is finalized in TodoWrite, compact to start fresh
2. **Compact after debugging** — Clear error-resolution context before continuing
3. **Don't compact mid-implementation** — Preserve context for related changes
4. **Read the suggestion** — The hook tells you *when*, you decide *if*
5. **Write before compacting** — Save important context to files or memory before compacting
6. **Use `/compact` with a summary** — Add a custom message: `/compact Focus on implementing auth middleware next`

## Token Optimization Patterns

### Trigger-Table Lazy Loading
Instead of loading full skill content at session start, use a trigger table that maps keywords to skill paths. Skills load only when triggered, reducing baseline context by 50%+:

| Trigger | Skill | Load When |
|---------|-------|-----------|
| "test", "verify", "coverage" | verification-loop | User mentions testing/verification |
| "slow", "perf", "profile" | perf-profile | Performance work |
| "library", "reuse", "add X" | search-first | Before writing net-new code |

### Context Composition Awareness
Monitor what's consuming your context window:
- **CLAUDE.md files** — Always loaded, keep lean
- **Loaded skills** — Each skill adds 1-5K tokens
- **Conversation history** — Grows with each exchange
- **Tool results** — File reads, search results add bulk

### Duplicate Instruction Detection
Common sources of duplicate context:
- Same rules in both `~/.claude/rules/` and project `.claude/rules/`
- Skills that repeat CLAUDE.md instructions
- Multiple skills covering overlapping domains

### Context Optimization Tools
> These are optional MCP tools from the full ECC harness and are **not installed** in this config. Listed for awareness only — do not invoke them here.
- `token-optimizer` MCP — automated token reduction via content deduplication
- `context-mode` — context virtualization

## Related

- [The Longform Guide](https://x.com/affaanmustafa/status/2014040193557471352) — Token optimization section
- Memory persistence hooks — For state that survives compaction
