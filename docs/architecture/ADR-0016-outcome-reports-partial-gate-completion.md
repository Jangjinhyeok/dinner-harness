# ADR-0016: `Outcome` reports completed/remaining gates instead of a single opaque `BUILT`

- **Status:** Accepted
- **Date:** 2026-08-31
- **Deciders:** user + Architect session

## Context

`build_prompt()` (see ADR-0015 area of `controller.py`) instructs the headless
Builder to stop after completing a HIGH gate rather than progressing to the next
declared gate, so that the HIGH gate gets human sign-off before further work lands.
`_run_from_handoff()` correctly implements the stop, but its return value does not:
`Outcome.status` is drawn from a small closed vocabulary (`DONE`/`BLOCKED`/`HELD`/
`BUILT`/`MAX_CYCLES`) with no gate-level granularity, so a Builder that completed
every eligible gate and a Builder that implemented gate 1 (HIGH) and then correctly
stopped before gates 2-3 both return the identical bare `BUILT`. A human or calling
script reading `orchestrate.py build`'s one-line `[outcome] BUILT after N cycle(s):
...` print cannot tell these apart without reading the full log or RESULT.md by
hand — exactly the ambiguity the user's re-verification (Finding A2) flagged.

## Decision

Add three optional, additive fields to `Outcome` — `completed_gates: list[str]`,
`remaining_gates: list[str]`, `review_required_gate: Optional[str]` — populated only
at the `BUILT` return site in `_run_from_handoff()`, computed from `tiers` (every
gate the HANDOFF declared) and `verdicts` (the gates the Builder actually reported
this run). `Outcome.status` keeps its existing string vocabulary unchanged, so every
existing `outcome.status == BUILT` / `in (DONE, HELD)` comparison in `orchestrate.py`
and the test suite continues to work without modification — this is why the 6-status
rename sketched in the original finding (`BUILT_COMPLETE`/`REVIEW_REQUIRED`/`PARTIAL`/
etc.) was not implemented: it would have required updating every existing status
comparison for a benefit fully achievable by adding fields instead.

## Implementation Guidelines

- `Outcome` dataclass: add `completed_gates: list[str] = field(default_factory=list)`,
  `remaining_gates: list[str] = field(default_factory=list)`,
  `review_required_gate: Optional[str] = None`.
- `Orchestrator._outcome()`: add matching optional keyword-only parameters
  (`completed_gates`, `remaining_gates`, `review_required_gate`, all defaulting to
  `None`/empty), threaded into the `Outcome(...)` it constructs. Every existing call
  site that does not pass these keeps getting the empty-list/`None` defaults — no
  existing call site needs to change.
- At the `BUILT` return in `_run_from_handoff()` (the `return self._outcome(BUILT,
  attempt, note)` line), compute: `completed = sorted({v.gate for v in verdicts})`,
  `remaining = sorted(set(tiers) - set(completed))`, and `review_required_gate =`
  the last completed gate if `remaining` is non-empty and that gate's tier
  (`tier_for(tiers, last_gate)`) is `TIER_HIGH`, else `None`. Pass these into the
  `_outcome(...)` call.
- `orchestrate.py`'s `_build()`: after the existing `[outcome] ...` print, add one
  conditional line — if `outcome.remaining_gates` is non-empty, print
  `[outcome] remaining gates: {", ".join(outcome.remaining_gates)}`. No other output
  or control-flow change.
- Do not touch `_receipt_status`/`_receipt_reason_code`'s existing return vocabulary
  (`built_high`/`built_low`/etc.) — those are a separate, already-stable audit
  contract; widening it is out of scope for this gate.
- Add one test exercising a HANDOFF with gate 1 (HIGH) + gate 2 (LOW) where only
  gate 1's verdict comes back, asserting `completed_gates == ["1"]`,
  `remaining_gates == ["2"]`, `review_required_gate == "1"`.

## Consequences

- **Positive:** a caller can now distinguish full completion from a correct
  stop-after-HIGH-gate without parsing free-text logs, closing the ambiguity
  Finding A2 identified.
- **Positive:** fully additive — zero risk to any existing `status`-based branching
  in `orchestrate.py` or the test suite.
- **Negative / trade-off:** the audit receipt's `reason_code` vocabulary
  (`built_high`/`built_low`) still does not distinguish complete-vs-partial; a
  future gate could extend it (e.g. `built_high_partial`) if that granularity turns
  out to matter for the audit trail specifically, but this gate does not do so.

## Alternatives considered

- **Six new top-level `Outcome.status` values** (as sketched in the original
  finding): rejected — breaks every existing `== BUILT` / `in (DONE, HELD)`
  comparison for a benefit the additive-fields approach achieves without doing so.
