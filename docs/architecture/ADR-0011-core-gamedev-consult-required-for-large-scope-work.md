# ADR-0011: `_core`/`_gamedev` consult becomes required for large-scope work, gated by scale not domain signal

- **Status:** Proposed
- **Date:** 2026-08-11
- **Deciders:** Architect session (dinner-harness)

## Context

ADR-0010 made engine hub consult mandatory before HANDOFF for Unreal/Unity
signal work, and a live probe on `unity-specialist` (2026-08-11, same day)
confirmed the mechanism actuates: given a DOTS/ECS design question with no
document-location hint, the hub's first tool call was
`Read C:\Users\zero9\.claude\docs\specialists\unity-dots.md` — the install
root, before any project-detection command ran.

That success prompted the same question for the other 11 agents in this
harness (`_core`: `architect`, `code-reviewer`, `cpp-build-resolver`,
`cpp-reviewer`, `planner`, `tdd-guide`; `_gamedev`: `gameplay-programmer`,
`network-programmer`, `performance-analyst`, `tools-programmer`,
`ui-programmer`). Two checks were run.

**Check 1 — do the agents work when invoked directly?** All 11 were probed
with a domain-specific task (a planted linker bug for `cpp-build-resolver`, a
planted command-injection/SQL-injection script for `code-reviewer`, a planted
memory-safety bug for `cpp-reviewer`, a cooldown-ability implementation for
`gameplay-programmer`, etc.). All 11 behaved correctly within their granted
tool set. Two results stood out beyond "the persona matches": `planner` and
`network-programmer`, given tasks whose premises didn't hold in this
repository, investigated the actual repo state (adjacent UE5 project
`Duckov_Like`, its real design docs) and **refused to fabricate a plan against
a nonexistent `InventoryManager`** rather than inventing plausible-looking file
paths, and asked clarifying questions instead of guessing engine/scope
assumptions. That is `think-before-coding` propagating correctly into
subagents, not a failure.

**Check 2 — do these agents ever get invoked from ordinary conversation?** A
transcript audit (same method as ADR-0010: script over all parent-session
`.jsonl` files, `subagents/` directories excluded, matching `Agent` tool calls
with `subagent_type` in the 11-agent set, cross-referenced against the
immediately preceding user turn) found **19 total invocations across the
entire local history, zero of which were an organic response to a plain-chat
domain request**:

- 11 were this session's own explicit meta-request ("코어랑 게임데브까지
  검증해줘") — the Check-1 probes themselves.
- 8 were mechanical: `adversarial-review`'s jury step spawning
  `code-reviewer`/`architect`/`tdd-guide`/`tools-programmer` as orthogonal
  judges, in two prior sessions (2026-08-06, 2026-08-11). The preceding user
  turn in every one of those 8 was the `adversarial-review` skill body being
  loaded, not a user request.

This is not a reachability failure (Check 1 shows the agents work correctly
when called) — it is the same positioning failure ADR-0010 diagnosed for the
engine hubs: `agent-routing.md`'s delegation rule for `_core`/`_gamedev` is
unenforced prose, while `CLAUDE.md`'s Builder-first table, injected on every
turn by hook, tells the session to handle "질문, 코드 Read, 검색, MCP 조사,
설계, 리뷰" **directly** — precisely the categories these 11 agents exist to
own (design → `architect`/`planner`, review → `code-reviewer`/`cpp-reviewer`,
domain implementation → the five `_gamedev` agents).

**Why this is not simply "apply ADR-0010 again."** The engine hubs and these
11 agents are retained for different reasons, per the removal-criteria table
in `assets/claude/README.md`. Engine hubs exist to close a **knowledge gap**
(the base model does not reliably know current-version UE5/Unity APIs without
`docs/specialists/*.md`) — the same table's "Domain agents" row gives a
different reason for `_core`/`_gamedev`: **context isolation on large,
multi-domain work**, not missing knowledge. The Check-1 probe outputs support
this reading — `architect`'s leaderboard design and `cpp-reviewer`'s
memory-safety review were solid, but not qualitatively different from what
this session already produces inline (the earlier README-fix work in this
same conversation, or the leaderboard-scale reasoning above, were done by this
session directly, unaided).

Given that, a domain-signal-only trigger copied verbatim from ADR-0010 would
misfire structurally: `_core`/`_gamedev`'s domain surface is far broader than
"UE/Unity keyword present" — architecture, code review, C++ build errors,
TDD, gameplay, networking, performance, tooling, UI. Almost any substantial
request touches one of these. A blanket domain-signal mandate would force a
30–50k-token, tens-of-seconds subagent consult onto small single-file tasks
that this session already handles correctly and cheaply inline — the opposite
of the token-economy split (`Architect` lane stays low-volume) that the
Builder-first design deliberately optimizes for, and a direct contradiction of
the very "context isolation on **large** work" rationale that justifies these
agents' continued existence.

## Decision

Mandate `_core`/`_gamedev` consult before HANDOFF, but gate it on **scale**,
not on domain-keyword presence: when the Architect's own triage already
classifies a request as requiring the **architect route** (multi-file,
multi-gate, structural decision, or HIGH — the same threshold that already
separates it from the LOW single-purpose `/delegate` lane) **and** the domain
matches one of the 11 agents per `agent-routing.md`'s existing routing table,
consult that agent once before authoring the HANDOFF, and fold its judgment
into the HANDOFF's constraints, gates, and verification criteria — the same
mechanic ADR-0010 established for engine hubs, applied at a different gate.

Work that stays in the LOW/`/delegate` lane, or that this session would
handle as a 1–2 line / read-only / exploratory answer, is exempt by
construction: it never reaches the architect-route classification that is
this rule's trigger.

## Implementation Guidelines

- **`content/rules/agent-routing.md`** — add a new section, `_core`/`_gamedev
  consult (구조적 HANDOFF 전 필수)`, parallel to the existing "엔진 허브
  consult" section. State the trigger explicitly: architect-route
  classification (다파일·구조 결정·HIGH) **and** a domain match against the
  existing "라우팅 규칙" table (Unreal/Unity work is already covered by the
  ADR-0010 section and is not re-triggered here). Exemptions mirror ADR-0010:
  read-only/exploratory, genuinely 1–2 line changes, a re-dispatch whose
  design is already fixed, a session that already consulted for the same
  design — plus the structural exemption that anything classified into the
  LOW/`/delegate` lane never reaches this trigger at all.
- **`content/roles/ROLE_ARCHITECT.md`** — add a new **step 6.6** (do not
  renumber steps 7/8/9; `orchestrator/controller.py` references them by
  number). Text: when step 6's scoping already puts the work on the
  architect route and the domain matches the `_core`/`_gamedev` table,
  consult the matching agent once via the `Agent`/Task tool, and fold its
  design judgment, anti-patterns, and verification points into step 7's
  HANDOFF before authoring it.
- **`content/instructions/CLAUDE.md`** — one pointer sentence next to the
  existing ADR-0010 pointer line in §2, referencing this rule in
  `agent-routing.md`. No rule-body duplication (the existing CLAUDE.md
  convention for this kind of pointer, per the ADR-0010 commit).
- **`assets/claude/README.md`** — changelog entry (milestone-level, matching
  the existing 2026-08-11 ADR-0010 entry's format) documenting this decision,
  the audit numbers (19 total / 11 self-test / 8 mechanical / 0 organic), and
  the next-audit signal below. Also update the "Domain agents" row of the
  removal-criteria table to note the new consult condition without changing
  its stated retention rationale (context isolation on large work).
- **root `README.md`** — extend the sentence added for ADR-0010 (in "일상
  사용법 > 1) 기본 세션에서 실제로 일어나는 일") with one additional clause
  noting that architect-route domain work also requires a `_core`/`_gamedev`
  consult under this ADR. Keep it to one added clause/sentence — do not
  restructure the existing table or paragraph.

No hook change. A `route_nudge`-style keyword nudge does not fit this trigger:
"architect-route classification" cannot be determined from raw prompt text
before the Architect's own triage runs (step 6), unlike a UE/Unity keyword
match on the raw prompt. Encoding a scale-gated trigger in a
UserPromptSubmit hook would either underfire (miss scale signals that only
emerge after triage) or overfire (match domain keywords in small requests —
exactly the cost problem this ADR rejects). The rule therefore lives in the
Architect's own workflow instructions, not in `route_nudge.py`.

## Consequences

- **Positive:** large/structural domain work gets the specialist's judgment
  folded into the HANDOFF, at a cost paid only on the already-expensive
  architect-route path — never on the common LOW/`/delegate` case. This keeps
  the token-economy split (`Architect` lane low-volume) intact, unlike a
  blanket domain-signal mandate would.
- **Negative / trade-offs:** one additional subagent turn (similar cost
  profile to the ADR-0010 hub consult, ~30–50k tokens / tens of seconds) on
  every architect-route gate whose domain matches. Two implementations of
  design guidance (this session's own reasoning vs. the consulted agent's)
  can drift if the consult's output is not actually folded into the HANDOFF —
  the same failure mode ADR-0010 flagged for hubs ("read the doc but don't
  cite it").
- **Follow-ups:** the next conformance audit must measure invocation **rate
  among architect-route sessions whose domain matches the table**, not raw
  counts across all sessions — architect-route work is itself a minority of
  total sessions (most stay in the LOW/`/delegate` lane by design), so a raw
  count will always look small even if the rule is fully actuated. If that
  conditional rate stays at zero under this binding rule, the honest
  conclusion is to drop this ADR's mandate (not sunset the agents themselves,
  since Check 1 showed they work — the mandate specifically, reverting to
  discretionary use) rather than re-argue it.

## Alternatives considered

- **Copy ADR-0010 verbatim (domain-signal trigger, no scale gate)** — rejected.
  `_core`/`_gamedev`'s domain surface is far broader than "UE/Unity keyword,"
  so this would fire on nearly every substantial request and force a subagent
  consult onto small tasks this session already handles correctly and cheaply
  inline — contradicting both the Builder-first token-economy design and the
  agents' own stated retention rationale (context isolation on *large* work).
- **No rule / defer to next audit** — rejected. The audit already found a
  0-organic-invocation baseline under the current soft-prose-only regime
  across the full local history (19 matches, all explicit or mechanical).
  Repeating the same measurement under the same unenforced-prose condition
  would return the same zero — ADR-0010 rejected this same move ("repeating a
  measurement whose result is already determined by the design is not
  evidence") for the identical reason.
- **`route_nudge`-style hook nudge on domain keywords** — rejected. The
  trigger this ADR needs (architect-route scale classification) is not
  computable from raw prompt text before the Architect's own triage step
  runs; a hook keyed on domain keywords alone would reproduce the
  over-broad-firing problem the scale gate exists to avoid.
