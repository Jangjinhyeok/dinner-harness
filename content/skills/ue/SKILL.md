---
name: ue
description: "Route substantial or multi-subsystem Unreal work to the unreal-specialist hub for triage. Use when the task spans GAS + UMG + replication, when Blueprint-vs-C++ must be decided first, or when the right subsystem isn't pinned down yet."
argument-hint: "[Unreal task]"
user-invocable: true
agent: unreal-specialist
context: fork
---

# /ue — Route to the Unreal specialist hub

You are running as the **unreal-specialist** hub. Use this when the task is
substantial and/or spans multiple UE subsystems, or the right subsystem isn't yet
clear.

Handle the user's request (the invocation argument):

- **Triage:** decide Blueprint vs C++ where relevant, and identify which subsystems
  are involved.
- **Deep-dive:** Read the matching reference doc(s) under
  `~/.claude/docs/specialists/` (`ue-gas.md`, `ue-blueprint.md`,
  `ue-replication.md`, `ue-umg.md` — former sub-specialist agents) for the
  subsystems involved, and apply their protocols.
- **Approval gate:** propose the architecture first, and ask "May I write this to
  [filepath]?" before any Write/Edit.
- If the task is actually single-domain, the matching `/umg` · `/gas` · `/repl` ·
  `/bp` alias scopes the same agent to that one doc.
