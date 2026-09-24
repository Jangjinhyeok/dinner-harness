---
name: ue
description: Identify Unreal subsystem boundaries and apply relevant specialist guidance for substantial or cross-subsystem work.
---

# Unreal Guidance

Identify engine version, Blueprint/C++ boundary and affected systems from the actual project.
Read only relevant references:
[Blueprint](../../docs/specialists/ue-blueprint.md),
[GAS](../../docs/specialists/ue-gas.md),
[replication](../../docs/specialists/ue-replication.md),
[UMG](../../docs/specialists/ue-umg.md).
Preserve engine lifetime/ownership, gameplay invariants, replication/save compatibility and
frame/memory budgets. Apply project build, automation, PIE/multiplayer procedures as relevant;
state unavailable engine checks as not_run.
For UE5 interactive PIE validation, follow the user-vs-Computer-Use choice in
[verification guidance](../verification-loop/SKILL.md) before starting the validation.

The main session can design and implement authorized work. Use a native unreal-specialist only
when independent assistance adds value; no mandatory hub dispatch or per-file approval.
Significant HIGH changes retain independent review and human result acceptance.
