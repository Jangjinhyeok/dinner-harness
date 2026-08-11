# ADR-0010: Engine hub consult becomes a required pre-HANDOFF step

- **Status:** Accepted
- **Date:** 2026-08-11
- **Deciders:** Architect session (dinner-harness)

## Context

The engine hubs (`unreal-specialist`, `unity-specialist`) are the last two
engine agents. ADR-era history around them is a sequence of shrinking:
2026-06-16 found real UE5.6 work handled ~89% inline with hub fan-out at zero;
2026-07-02 demoted eight leaf specialists to `docs/specialists/` reference docs
after measuring leaf delegation at one session in six weeks; 2026-08-08 found
hub invocation at zero for a second consecutive cycle, met the README sunset
criteria, and the human chose to defer one cycle because the UE5 project
(`Duckov_Like`) had started four days earlier and had not yet reached gameplay
implementation.

A 2026-08-11 re-measurement over this machine's full transcript history
(32 parent sessions + 8 subagent sessions, 2026-06-16 → 2026-08-11, 15 active
days) found 13 sessions carrying an engine signal and **zero** hub invocations.
All eight recorded subagent runs were `adversarial-review` jurors and
`harness-review` auditors. Router skill (`/ue` `/umg` `/gas` `/repl` `/bp`)
usage was also zero; the three textual matches were harness discussions of the
skills, not invocations.

Two facts prevent the obvious reading of that zero.

First, the counting method nearly produced a false conclusion. Claude Code
2.1.222 does not record `Task` tool_use blocks in the parent transcript; the
subagent runs live in a separate `subagents/` directory. Counting the parent
alone yields "no delegation of any kind ever happened", which is false. The
numbers above come from the subagent directory.

Second, and decisively: the path works. A live probe on 2026-08-11 invoked the
`unreal-specialist` hub with a GAS design question that deliberately withheld
any pointer to the reference docs. Its **first and only** tool call was
`Read C:\Users\zero9\.claude\docs\specialists\ue-gas.md` — the harness install
root, correctly resolved from the agent body's prose hint ("relative to the
harness install root"), and chosen over a copy of the same file sitting in the
session's own working directory. The answer then followed that document's
protocol and anti-pattern catalog. So the leaf knowledge is reachable, is
reached on the first move, and demonstrably shapes the output.

Non-use is therefore not a reachability failure. It is a positioning failure.
`route_nudge` detects engine signals correctly and fires, but tells the session
to use `/ue` "**only for** focused Architect analysis before the selected
execution route", while the same injection carries the always-on Builder-first
`[execution-route]` protocol that pushes every implementation request straight
to a HANDOFF and a Codex dispatch. `agent-routing.md` already records the
intent — "엔진 라우팅이 가치를 갖는 지점은 Architect의 설계 단계(HANDOFF 작성
전 triage)" — but records it as an observation, and `ROLE_ARCHITECT.md`'s work
flow goes from exploration (step 2) to authoring the HANDOFF (step 7) with no
consult step in between. An optional step standing beside a mandatory one is
not taken.

## Decision

Engine-signal implementation work must consult the engine hub **once, before
the HANDOFF is authored**, and the consult's output must be reflected in the
HANDOFF's constraints, gates, and verification criteria.

The rule is vendor-aware, because the hubs are Claude-side agents and a Codex
Architect cannot invoke them:

- **Claude Architect** — invoke the hub (`unreal-specialist` / `unity-specialist`)
  or the matching router skill.
- **Codex Architect** — Read the matching `docs/specialists/*.md` under its own
  install root (`~/.codex`) directly.

Exempt: read-only questions and exploration; genuinely one-to-two-line changes;
a re-dispatch whose design is already fixed by an earlier consult; and a session
that has already consulted the hub for the same design.

## Alternatives rejected

**Defer another cycle** (the 2026-08-08 choice). The next cycle would measure
the same optional-step condition and return the same zero. Repeating a
measurement whose result is already determined by the design is not evidence.

**Sunset the hubs** (agents 13 → 11), applying the leaf pattern one level up.
Rejected because the probe showed the hub produces document-grounded output
when it is actually called. Removing a working tool because a discretionary
step went untaken inverts cause and effect — the honest experiment is to make
the step non-discretionary first.

## Consequences

The cost is one additional subagent turn on engine work: measured at ~41k
tokens and ~110s for the probe. It is paid once per design, in the Architect
lane, not per gate — and the Architect lane is the low-volume half of the
token-economy split this harness is built on.

The risk is dead protocol: a mandatory step that is still skipped is worse than
an optional one, because it also makes the rule set untrustworthy. So the next
conformance audit measures hub invocations **per engine-signal session** rather
than in absolute terms. If that stays at zero under a binding rule, the honest
conclusion is sunset, and this ADR is superseded rather than re-argued.

This is the first harness rule whose actuation was measured both before the
change and by explicit probe of the mechanism it depends on. That order —
measure the wiring, then decide about the usage — is the reusable part.
