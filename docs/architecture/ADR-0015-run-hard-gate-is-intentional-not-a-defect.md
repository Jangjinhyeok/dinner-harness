# ADR-0015: `run()`'s hard tier-gate is intentional; document its Codex-headless gap instead of loosening it

- **Status:** Accepted
- **Date:** 2026-08-31
- **Deciders:** user + Architect session

## Context

The user's re-verification brief (Finding A1) observed that `orchestrator/controller.py`'s
`run()` (the fully-headless `orchestrate.py run` Architect+Builder loop) calls
`_build_and_gate(..., tier_gate_hard=True)`, which hard-blocks a HIGH gate unless the
Builder's own self-reported `panel` verdict is `PASS` — a string the Builder itself
writes into its RESULT.md. The brief's proposed fix (Option B) was to remove this
structure: "Builder가 자기 RESULT에 적은 panel=PASS만으로 HIGH를 통과시키는 구조는
제거한다," and the Architect's initial plan (before this ADR) was to align `run()`'s
`tier_gate_hard` to the same advisory (`False`) setting the primary
`run_from_handoff()` path already uses.

While gathering the exact current text to implement that change, `_build_and_gate`'s
own docstring (controller.py:1195-1201) surfaced a fact the initial finding did not
weigh: *"``tier_gate_hard`` controls only the verdict-based tier gate: run() keeps it
hard (the autonomous loop has no other reviewer); the auto-dispatch build path sets
it advisory (emit-only) because the in-session Claude review + HIGH human sign-off
own that judgment."* The primary path (`run_from_handoff`, dispatched by an
interactive Claude Architect) is correctly advisory precisely because a human-facing
Claude session reviews the diff and signs off afterward — the self-reported panel is
redundant with, not a substitute for, that review. `run()` has no such downstream
reviewer: both Architect and Builder are headless, and nothing pauses for a human
between gates. Making its tier-gate advisory would not close a trust gap — it would
remove the only check that topology has, since an advisory gate never blocks
anything on its own.

Separately, `assets/codex/AGENTS.md` (the Codex-side Builder protocol, §"degraded
주의") already explicitly discloses that Codex's self-review is a single reviewer,
not `adversarial-review`'s jury, and that HIGH-tier changes compensate for that
weakness via **explicit human gate review** for interactive Codex sessions
(AGENTS.md:114, :165). That compensating mechanism — a human reviewing each HIGH
gate — is exactly what `run()`'s fully-headless topology does not have. So the real,
narrower gap is: **`run()` combined with a Codex Builder** has neither jury (Codex
lacks `adversarial-review`, dropped in `harness.toml [targets.codex].skills_drop`)
nor a human mid-loop gate (the topology is fully headless) — its hard tier-gate is
the sole safety mechanism, and it trusts an unverified self-report. This combination
is Tier-2/Experimental per the topology-support-level framing in the same
re-verification brief (Phase D), not the primary Claude-Architect→Codex-Builder path.

## Decision

Do not change `run()`'s gating logic, and do not rename the `panel` verdict field.
Both would either regress the one safety mechanism `run()` has (loosening the gate)
or churn a large, low-judgment surface — every test fixture and doc that writes
`panel=PASS/FAIL/BLOCK` — for a labeling concern that the primary path's advisory
design and AGENTS.md's existing disclosure already substantially address. Instead,
add one clarifying paragraph to `_build_and_gate`'s docstring, spelling out that when
the Builder vendor lacks jury capability, `run()`'s hard gate is a materially weaker
guarantee than either the primary path (Claude diff review + human sign-off) or an
interactive Codex session (explicit per-gate human review per AGENTS.md §8) — and
that `run()` HIGH gates with a Codex Builder should be treated with that in mind.

## Implementation Guidelines

- Extend the existing docstring at controller.py's `_build_and_gate` (around line
  1195-1201) with one additional paragraph after the existing `tier_gate_hard`
  explanation, stating: when the Builder vendor has no jury skill available (e.g.
  Codex, since `adversarial-review` is in `harness.toml [targets.codex].skills_drop`),
  `run()`'s hard gate trusts an unverified self-report with no compensating human
  review (unlike an interactive Codex session, which gets explicit per-gate human
  review per AGENTS.md §8) — prefer a Claude-vendor Builder for `run()` HIGH gates, or
  treat a Codex-Builder `run()` HIGH result as needing additional human scrutiny
  before accepting it.
- No change to `tier_gate_hard`'s value in either call site, no change to
  `GateVerdict.panel`, `PANEL_PASS`/`PANEL_FAIL`/`PANEL_BLOCK`, `parse_verdicts`, or
  any test fixture.
- Do not touch `content/roles/ROLE_BUILDER.md` or `assets/codex/AGENTS.md` in this
  gate — AGENTS.md's existing degraded-mode disclosure already covers the
  interactive-Codex-session case correctly; only the fully-headless `run()` gap
  needed documenting, and that lives in the code that implements it.

## Consequences

- **Positive:** closes the actual documentation gap (a session choosing `run()` with
  a Codex Builder for HIGH work now has an explicit warning at the exact code site
  that implements the hard gate) without touching any working logic or any of the
  dozens of existing test fixtures that write `panel=`.
- **Positive:** avoids a regression that a less careful implementation of the
  original finding would have introduced (loosening `run()`'s only safety check).
- **Negative / trade-off:** the underlying weak spot (Codex Builder + `run()` + HIGH
  gate = self-report with no independent check) is not eliminated, only documented.
  Eliminating it would require either giving Codex a jury mechanism (Option A/C from
  the original brief, both explicitly rejected there as disproportionate to the
  primary path) or making `run()` refuse Codex-vendor HIGH gates outright (a new
  behavior change out of scope for this cycle, not requested and not clearly
  wanted — `run()` is already Tier-2/Experimental and a user choosing it accepts
  its documented limitations).

## Alternatives considered

- **Align `run()`'s `tier_gate_hard` to `False` (the originally planned fix):**
  rejected after reading the docstring — this removes `run()`'s only safety
  mechanism rather than fixing a flaw in it, since that topology has no downstream
  human/Claude reviewer to fall back on.
- **Rename `GateVerdict.panel` to `self_review` everywhere:** rejected as
  disproportionate churn (bus.py, controller.py, every test fixture using
  `panel=PASS/FAIL/BLOCK`, both role docs) for a labeling clarity concern that the
  primary path's advisory design and AGENTS.md's existing disclosure already
  substantially cover; the one real gap (`run()` + Codex + HIGH) is better closed by
  a docstring note than a global rename.
- **Make `run()` refuse a Codex-vendor Builder for HIGH gates outright:** rejected
  for this cycle — `run()` is Experimental/Tier-2 scope per the user's own topology
  framing (Phase D); adding vendor-conditional refusal logic to it is new behavior
  beyond what this re-verification cycle asked for. Left as a documented limitation,
  not implemented.
