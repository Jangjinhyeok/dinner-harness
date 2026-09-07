# ADR-0021: challenge round cap — bounded challenger_high retries with a repeating human checkpoint

- **Status:** Accepted
- **Date:** 2026-09-07
- **Deciders:** user + Architect session

## Context

Real incident (user-reported, 2026-09-07, a separate ASAN project using this
harness): one HIGH-tier HANDOFF (a quest-v2 network protocol change) drove six
consecutive `orchestrate.py challenge` dispatches over 46 minutes
(build-audit.jsonl `dispatch_id` sequence `9a1854d2` -> `e8cdc70c` ->
`1d789748` -> `bde7ecd9` -> `c18cb5f4` -> `04a10761`, 07:11-07:56 UTC, every
one `outcome=CHALLENGED`). Each round the Architect revised the HANDOFF in
response to the Opus challenger's critique and re-challenged, but the gate
never reached `builder_high` dispatch or human sign-off before the session's
tokens ran out. `CHALLENGE.md` itself accumulated a "5차까지 오면서..." remark,
yet nothing in the workflow ever counted the rounds or said "stop here."

`_run_challenge()` (`orchestrator/controller.py`) and `BuildAudit`
(`orchestrator/receipt.py`) are stateless per call: neither tracks how many
times a given HANDOFF lineage (same filename, evolving content) has already
been challenged. `challenger_high`'s independent-invocation design
(`content/rules/routing-reference.md` §7, ADR-0020 correction 5 — each
challenge call is a fresh invocation so the critique never anchors on a prior
one) was never meant to imply "call it as many times as you like." The two
concerns — independence *per call* vs. a bound on *total calls* — were simply
never distinguished, leaving a real gap: nothing was counting which round this
was.

## Decision

Add a round-cap checkpoint to `orchestrate.py challenge` only (`run` and
`build` are unaffected). Before invoking the `challenger_high` vendor,
`_run_challenge()` counts consecutive `challenge_dispatch` / `status=
"challenged"` terminal records in `build-audit.jsonl` for the current
handoff's *filename* hash (`handoff_name_sha256`), scanning backward from the
newest record until a `builder_dispatch` record (any status) breaks the
streak. A `builder_dispatch` record only exists once a HIGH gate actually left
the challenge loop for a real build attempt, so it is the correct natural
boundary between one "challenge saga" and the next re-use of the same
recurring filename (e.g. `HANDOFF.md` reused across unrelated features over
time). A non-`"challenged"` `challenge_dispatch` record (`blocked`/`timeout`,
including a prior round-cap block itself) is skipped — neither counted nor
streak-breaking — so a blocked checkpoint call can never be replayed to
silently reset the counter.

When the count reaches `max_challenge_rounds` (default 3, override via
`--max-challenge-rounds`), the dispatch is refused before any vendor call is
made — `BLOCKED`, zero tokens spent — with a message presenting three explicit
choices: split the HANDOFF into smaller HIGH gates, proceed accepting residual
risk via `--acknowledge-challenge-round-cap`, or revisit the design before
challenging again. The override does not reset the counter and does not
"spend once, then coast": because the streak only resets on a `builder_dispatch`
record, every round at or past the cap requires the flag again until the gate
actually resolves. This is deliberate friction, not an oversight — see
Alternatives.

Counting is scoped by handoff **filename** hash, not content hash, so revising
the HANDOFF's wording between rounds does not reset the counter. A stuck saga
that gets reworded each round is still the same saga; content-hash scoping
would let a superficial reword dodge the cap indefinitely, which is closer to
what actually happened in the incident than an unchanged resubmission would
have been.

This does not change what the challenger judges or how (ADR-0020's
independent-invocation guarantee is untouched), and does not remove the
Architect's discretion to revise a HANDOFF between rounds — it only adds a
deterministic, pre-vendor-call count of how many rounds have already happened,
closing the "nobody was counting" gap.

## Implementation Guidelines

- `orchestrator/receipt.py`: `count_consecutive_challenge_rounds(audit_dir,
  handoff_name) -> int`, reusing the same JSONL-scan shape as
  `find_challenge_evidence` (skip non-JSON/non-dict lines, skip `"attempted"`
  pre-records). Missing or unreadable `build-audit.jsonl` returns `0`
  (fail-open on observability failure — see Consequences), matching this
  module's existing "audit I/O is observational" posture rather than
  `find_challenge_evidence`'s fail-closed posture.
- `orchestrator/config.py`: `Config.max_challenge_rounds: int = 3` and
  `Config.acknowledge_challenge_round_cap: bool = False`; `validate()` rejects
  a negative `max_challenge_rounds`.
- `orchestrator/controller.py`: `_run_challenge()` calls the counter before
  routing/profile resolution (so a capped call never resolves a vendor profile
  or spends a turn); a new branch in `_challenge_receipt_reason_code()` maps
  the cap-block reason string to `"challenge_round_cap"`; an acknowledged
  override marks `round_cap_acknowledged=True` in the terminal receipt's
  content-free `extra` metadata (same shape `routing_preset`/`logical_profile`
  already use).
- `orchestrate.py`: `challenge` subparser gains `--max-challenge-rounds`
  (`int`, default `3`) and `--acknowledge-challenge-round-cap`
  (`store_true`).
- `content/rules/routing-reference.md` §7's Challenge flow diagram gains the
  round-cap checkpoint between the read-only challenger step and the
  interactive Architect adjudication step.
- Regression tests in `orchestrator/tests/test_orchestrator.py`: the counting
  function (streak breaks on `builder_dispatch`, skips non-`"challenged"`
  `challenge_dispatch` records, scopes by filename hash), cap enforcement
  (blocks at the threshold *without* invoking the vendor backend — assert the
  mocked backend's `invoke` is never called), the override bypass, and
  presence of the new receipt field.

## Consequences

- **Positive:** bounds worst-case token burn from a stuck HIGH-tier design
  disagreement to `max_challenge_rounds` vendor calls before a conscious human
  decision is required, closing exactly the gap the incident exposed.
- **Positive:** preserves the challenger's per-call independence (ADR-0020
  correction 5) — the cap governs *how many times* the independent judge is
  called, never *what* it is told or *how* it judges.
- **Negative / trade-off:** fail-open on audit-log unavailability (an
  unreadable or missing log counts as 0 rounds, never blocking) is a
  deliberate asymmetry from `find_challenge_evidence`'s fail-closed posture.
  Accepted because this is a token-economy guardrail, not a security gate —
  the worst case of fail-open here is one extra automatic round, not a bypass
  of a HIGH gate's actual safety net (`scope_check`/`secret_scan` in
  `orchestrator/safety.py`, which remain fail-closed and untouched by this
  ADR).
- **Negative / trade-off:** filename-hash scoping means a project that
  recycles the same handoff filename across genuinely unrelated HIGH features
  back-to-back, with no intervening `builder_dispatch`, would inherit the
  prior feature's streak. Judged rare (a HIGH gate normally does reach a build
  attempt or an explicit human stop before a new unrelated feature starts) and
  arguably still worth a checkpoint if it does happen.
- **Negative / trade-off:** the override does not decay — every round at or
  past the cap needs `--acknowledge-challenge-round-cap` again, not just the
  first breach. A long but genuinely legitimate design back-and-forth pays a
  small repeated cost. Accepted as the point of the feature (see Alternatives).

## Alternatives considered

- **Modulo checkpoint** (re-prompt only every Nth round — 3, 6, 9 — letting an
  acknowledged override coast through the rounds in between): rejected. The
  entire point is to interrupt a loop the human has stopped noticing; a
  coasting window between checkpoints is exactly what let the real incident
  run six rounds unnoticed in the first place.
- **Reset the counter on override** (pay the friction once, then unlimited
  further rounds): rejected — indistinguishable from removing the cap after
  the first checkpoint, which defeats the purpose just as thoroughly as no cap
  at all.
- **Count by content hash instead of filename hash** (only count a round as
  "the same stuck saga" if the HANDOFF text is byte-identical to the prior
  round): rejected — would let a superficial reword of the same design each
  round dodge the cap indefinitely, which is a more likely real failure mode
  than an unchanged resubmission.
- **Enforce the stop as a prompt-level instruction to the interactive
  Architect session** (rather than a deterministic check in the orchestrator):
  rejected — the incident is itself evidence that a prompt-level "should I
  stop and ask" judgment silently degrades under a long, engaged design
  disagreement. A deterministic, pre-vendor-call check living beside the
  file's own independently-verified risk-tier logic (`_TIER_RULE`, ADR-0017)
  is the more reliable place for this, consistent with how this harness
  already treats deterministic checks as the load-bearing layer and prompts
  as advisory (`~/.claude/rules/autonomy-policy.md`).
