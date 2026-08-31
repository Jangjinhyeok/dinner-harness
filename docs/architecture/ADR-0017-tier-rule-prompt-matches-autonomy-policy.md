# ADR-0017: widen `controller.py`'s `_TIER_RULE` to match `autonomy-policy.md`, and test the match

- **Status:** Accepted
- **Date:** 2026-08-31
- **Deciders:** user + Architect session

## Context

`content/rules/autonomy-policy.md` declares itself the single source of truth for
risk-tier classification and lists HIGH signals across explicit bullets: network
replication / RPC / net serialization / relevancy / bandwidth; save or serialization
format / persistent data back-compat; live config / feature flag / remote toggle;
data migration / schema change; security-sensitive (auth, permission, crypto, trust
boundary, anti-cheat); and public API/ABI, build/packaging pipeline, one-way
migration under a "광범위·비가역" bullet.

`orchestrator/controller.py`'s `_TIER_RULE` is the actual string sent to every
headless Architect (`design_prompt()`, used by the `orchestrate.py run` fully-headless
path) as its risk-classification instruction. As of `a6f450e0` it read: "HIGH =
network replication / save or serialization format / live config or feature flags /
data migration / security-sensitive / anything irreversible." This omits RPC, net
serialization (named separately from replication in the policy doc), relevancy,
bandwidth, persistent back-compat, schema change, the specific security-sensitive
examples, and — most notably — public API/ABI and build/packaging pipeline, folding
all of them into an unexplained "anything irreversible" catch-all with no worked
examples for a model to pattern-match against.

Two independently-maintained copies of the same taxonomy, one of which is missing
categories the other calls out explicitly, is exactly the drift `autonomy-policy.md`
itself warns against ("tier 정의를 다른 곳에서 재정의하지 않는다").

## Decision

Widen `_TIER_RULE` to name every category `autonomy-policy.md` lists, in the same
grouping, and add a unit test in `orchestrator/tests/test_orchestrator.py` that
asserts each required keyword substring is present in `_TIER_RULE`. This does not
introduce a code-generation pipeline or a shared Python/Markdown module — the
Markdown doc stays hand-authored prose (it carries Korean explanation and structure
worth keeping human-authored), and the Python string stays a literal. The test is
the mechanism that turns future drift into a build failure instead of a silent gap:
if a future edit to either side removes a keyword, the test catches it.

## Implementation Guidelines

- Rewrite `_TIER_RULE` (controller.py:85-89) to enumerate: network replication, RPC,
  net serialization, relevancy, bandwidth, save/serialization format, persistent
  back-compat, live config/feature flags, data migration/schema change,
  security-sensitive (auth/permission/crypto/trust boundary/anti-cheat), public
  API/ABI, build/packaging pipeline, and the "anything irreversible" catch-all —
  keep the "Conservative OR; if ambiguous, HIGH" closing sentence unchanged.
- Add one test (e.g. `test_tier_rule_names_every_policy_high_signal`) that imports
  `_TIER_RULE` and asserts each of the following substrings (case-insensitive) is
  present: `rpc`, `replication`, `net serialization`, `bandwidth`, `save`,
  `back-compat` (or `back compat`), `migration`, `schema`, `security`, `public
  api`, `abi`, `build`, `packaging`, `irreversible`. This is the "반드시 테스트할
  HIGH" list from the user's own task brief, minus items already covered by the
  existing wording (`live config`, `feature flag`).
- Do not touch `content/rules/autonomy-policy.md` itself in this gate — it already
  states the full list correctly; only the code-side copy needed to catch up.

## Consequences

- **Positive:** a headless Architect's risk classification now has the same worked
  examples a human reading `autonomy-policy.md` sees, closing the specific gap the
  user's own re-verification (Finding A3) identified.
- **Positive:** the new test makes future drift a CI-visible failure rather than a
  silent divergence, without building a doc-generation pipeline.
- **Negative / trade-off:** the two copies (Markdown prose, Python literal) are
  still hand-synced, not mechanically generated from one source — a future change to
  `autonomy-policy.md`'s HIGH list still requires a human to remember to update
  `_TIER_RULE` and the test's keyword list too. Accepted as proportionate: the
  taxonomy changes rarely, and a keyword-presence test is cheap insurance against
  the realistic failure mode (someone edits one side and forgets the other), not a
  proof of full semantic equivalence.

## Alternatives considered

- **Shared Python module (`orchestrator/risk_policy.py`) imported by both the
  prompt-builder and a Markdown-generation step:** rejected as disproportionate for
  a list that changes rarely and needs Korean prose context in the doc; would also
  require a doc-render step in `check.py`/CI that doesn't exist today for any other
  policy file.
- **No test, just widen the string:** rejected — this is exactly how the drift this
  ADR fixes was introduced in the first place (nothing caught it silently
  diverging from `autonomy-policy.md`).
