# ADR-0020: logical-profile routing preset architecture (Multi-Model Routing)

- **Status:** Accepted
- **Date:** 2026-08-31
- **Deciders:** user + Architect session

## Context

The harness currently has exactly one vendor pair (`Config.architect_vendor`/
`builder_vendor`) and one model pair (`architect_model`/`builder_model`), with no
concept of compute tier, no challenger role, and no effort/reasoning parameter
anywhere (confirmed by grep across `orchestrator/*.py`, `orchestrate.py`,
`content/rules/*.md` — zero matches for "challenger"/"compute_tier"/"effort"/
"reasoning" before this ADR). The user's actual production policy assigns
different concrete models by role *and* by implementation-complexity tier
(Luna/Terra/Sol for Codex Builder at LOW/NORMAL/HIGH compute; Opus for a HIGH-risk
ADR challenger), and wants the ability to later switch to an all-Claude lineup
(Sonnet/Opus only) by editing configuration, not by rewriting `controller.py`,
HANDOFF format, or risk policy.

Real CLI evidence gathered before design (not guessed): `codex exec --help` has
`-m/--model` but no dedicated effort flag — effort is set via
`-c model_reasoning_effort=<value>` (confirmed key name from
`~/.codex/config.toml`). `claude --help` has both `--model` and a dedicated
`--effort <low|medium|high|xhigh|max>` flag. Real model IDs confirmed from actual
session logs on this machine: `gpt-5.6-luna`, `gpt-5.6-terra`, `gpt-5.6-sol`
(Codex); `claude-sonnet-5`, `claude-opus-5` (Claude).

## Decision

Add a **logical profile → routing preset → vendor/model/effort → backend**
abstraction layer, reusing the existing `Backend`/`ClaudeBackend`/`CodexBackend`
classes unchanged in shape. Six logical profiles: `architect`, `challenger_high`,
`builder_low`, `builder_normal`, `builder_high`, `reviewer`. Two initial presets:
`hybrid` (current production default) and `claude_only`. `controller.py` never
references a vendor or model literal — only profile name strings.

Five corrections from the user's review are binding on this design (superseding
the Architect's original proposal in each case):

1. **`content/routing.toml` is the sole SSOT for concrete model/vendor/effort
   literals.** No hardcoded fallback mapping in `orchestrator/routing.py`. A
   missing or invalid routing config is a hard `RoutingConfigError`, not a silent
   fallback to a duplicated hardcoded mapping. Only the *preset name string*
   `"hybrid"` (not any model mapping) may exist as a code default, and even then
   only as which preset name to look up in the *same* `routing.toml` — never as a
   substitute mapping. Path resolution mirrors `Config._resolve_hooks_dir()`'s
   existing dev/installed dual-path pattern exactly: dev = `<repo>/content/
   routing.toml`, installed = `<repo>/routing.toml`.
2. **No new dual-copy SSOT between `harness.toml`'s `builder_vendor` and
   `routing.toml`.** The originally proposed regression test tying the two
   together is rejected. Instead, the six canonical docs' rendered dispatch
   example is made vendor-neutral (drop `--builder <BUILDER_VENDOR>` from the
   *recommended* command — the active routing preset chooses the runtime vendor
   by default). `harness.toml`'s `builder_vendor`/`builder_vendor_token` vars and
   the corresponding adapter substitution code become dead once no doc needs the
   token — Phase F evaluates and, if safe, removes them outright (not just
   deprecates), since the removal set is small and well-contained (2 adapters + 6
   docs + one manifest var).
3. **Interactive vs. dispatch-controlled roles are conceptually distinct.**
   `architect`/`reviewer` profiles in `routing.toml` describe recommended
   *interactive session* policy for the primary path (where the Architect/
   Reviewer *is* the user's own running Claude Code session — the orchestrator
   cannot and does not change that session's model) and are *actually dispatched*
   only by the secondary/experimental headless paths (`orchestrate.py run`, and
   the Phase D `challenge` subcommand uses `challenger_high`, a dispatch-
   controlled profile, not `architect`). No separate Architect-launcher framework
   is built to enforce this — it's a documentation and receipt-labeling
   discipline ("configured profile" vs. "actually dispatched runtime profile"),
   not new code surface.
4. **HIGH cannot be silently downgraded via explicit CLI override.** At profile-
   resolution time, if the gate being dispatched is effective-HIGH and
   `cfg.builder_model` is explicitly set, dispatch is refused with a clear error
   (fail-closed, not a silent ignore) — mirroring the harness's existing
   `CLAUDE_HOOK_FAILS_CLOSED` posture elsewhere. An explicit `--builder <vendor>`
   (vendor only, no model) at HIGH is allowed but resolves to *that vendor's own*
   `builder_high` profile (searched across all presets defined in `routing.toml`
   for one whose `builder_high.vendor` matches), never to an arbitrary model
   string — logical `builder_high` always outranks a concrete override at HIGH.
5. **`challenger_high` is a genuinely read-only invocation.** The challenger
   subprocess never gets write access (Codex: `sandbox=read-only`; Claude: no
   `DINNER_EXECUTION_MODE=direct`, so its own `builder_guard` blocks any
   accidental Edit/Write — defense in depth beyond the sandbox flag alone). The
   **parent** orchestrator process captures the subprocess's final message and
   writes the critique artifact (`CHALLENGE.md`) itself — the challenger process
   never touches the filesystem, unlike the Builder path where the subprocess
   writes `RESULT.md` itself as one of its own edits. Challenge evidence
   (content-free, reusing `receipt.py`'s existing `BuildAudit` shape rather than
   a new framework) records: challenged HANDOFF/ADR hash, `logical_profile=
   challenger_high`, `routing_preset`, resolved vendor, resolved model, effort,
   challenge-result hash, timestamp. A HIGH gate's `builder_high` dispatch is
   refused (fail-closed) if no challenge-evidence record exists whose challenged-
   HANDOFF hash matches the HANDOFF currently being dispatched.

## Implementation Guidelines

**Compute tier is a new axis, orthogonal to risk, added to the `tiers` fence
backward-compatibly.** Today: `gate 1: LOW`. New optional form: `gate 1:
risk=LOW compute=NORMAL` (matching the KV style the `verdicts` fence already
uses). The bare old form still parses (bare value = risk tier; compute absent →
NORMAL, or HIGH if risk is HIGH). Rules, all enforced in code:
- risk ambiguous/missing → HIGH (existing, unchanged).
- compute ambiguous/missing → NORMAL.
- risk HIGH → effective compute is HIGH regardless of what was declared.
- LOW risk + compute HIGH → `builder_high`, but **no** challenger/human
  mandatory — only *risk* HIGH triggers the challenge+human-signoff chain.
- risk HIGH → `challenger_high` → Architect adjudication (interactive, human) →
  `builder_high` → `reviewer` → human. This chain is vendor-invariant.

**One dispatch, one profile — resolved from the next undispatched gate.** A
single `orchestrate.py build` subprocess call cannot switch models mid-turn, and
today's `build_prompt()` already instructs the Builder to process consecutive
eligible gates in one turn and stop only at a HIGH gate (a prompt-level
instruction, not code-enforced — the existing pattern this ADR extends, not a
new kind of trust). Profile resolution happens once, from the tier/compute of
the first gate without a verdict yet; `build_prompt()` gains one more sentence
instructing the Builder to also stop at a compute-tier boundary, using the same
non-enforced-but-instructed mechanism HIGH-stop already relies on. This is a
known, documented limitation (heterogeneous compute tiers within one dispatch
turn are not deterministically split by the controller), not a silent gap.

**Phases** (each its own small, independently-verified gate, same discipline as
the prior Phase 0-D cycle):
- **A** — `orchestrator/routing.py`: `ModelProfile`, `RoutingConfigError`,
  `load_routing_config()`, `resolve_profile()`. Strict-SSOT, no fallback mapping.
- **B** — `content/routing.toml` itself (the real data) + `harness.toml` copy
  entries for both targets.
- **C** — `orchestrator/bus.py` compute-tier extension to the `tiers` fence,
  backward-compatible.
- **D1** — `orchestrator/vendors.py` effort pass-through (`--effort` / `-c
  model_reasoning_effort=`) + `Config` gains `routing_preset` (and effort
  override fields, mirroring the existing `*_model` pattern).
- **D2** — `controller.py` profile resolution wiring into `run_from_handoff()`'s
  Builder dispatch (compute routing + HIGH override-bypass guard). No
  architect/reviewer dispatch changes in the primary path — those stay
  interactive, per correction 3.
- **D3** — `orchestrate.py challenge` subcommand (read-only `challenger_high`
  dispatch, parent-owned `CHALLENGE.md`, challenge evidence) + HIGH
  fail-closed-without-evidence gate in `run_from_handoff()`.
- **E** — `receipt.py` extension: `routing_preset`/`logical_profile`/`model`/
  `effort` fields, reused for both Builder and Challenge audit records.
- **F** — docs (vendor-neutral dispatch examples, interactive-vs-dispatch role
  distinction documented), `builder_vendor` token removal evaluation/execution,
  final full verification (unittest, `check.py`, hybrid cases, claude_only
  cases, HIGH-downgrade rejection, challenge-evidence fail-closed).

## Consequences

- **Positive:** a future new model release is a `routing.toml` edit + compat
  verification — no `controller.py`, HANDOFF format, or risk-policy change, which
  was the explicit acceptance criterion.
- **Positive:** the same HANDOFF dispatches correctly under either preset, since
  it only ever encodes risk/compute/logical-profile-name, never a concrete model.
- **Negative / trade-off:** heterogeneous compute tiers within one Builder
  dispatch turn are only prompt-instructed to split correctly, not code-enforced
  (see above) — accepted as consistent with the existing HIGH-stop precedent,
  not a new category of risk.
- **Negative / trade-off:** the HIGH vendor-override-resolves-to-that-vendor's-
  own-builder_high search only works for vendors that actually have a
  `builder_high` entry somewhere in `routing.toml` — with only two presets
  defined initially (covering codex and claude), this is satisfied by
  construction; a third vendor with no defined `builder_high` anywhere would
  correctly fail closed rather than silently pick something.

## Addendum: 2026-09-11 Codex builder cost tiers

This addendum supersedes the historical builder lineup above. The current
default is `codex_only`; `hybrid` remains an opt-in compatibility preset.
Builder routing is intentionally cost-tiered within Codex models. The decision
applies only to their implementation builders, not architect, reviewer,
specialist, or challenger policy. `claude_only` remains unchanged. No non-Codex
provider or benchmark result is a candidate or input to this builder decision.

### Capability audit

The existing `content/routing.toml` already contains the canonical IDs
`gpt-5.6-luna`, `gpt-5.6-terra`, `gpt-5.6-sol`, and `gpt-6-astra`. All four also
appear in this host's Codex model catalog (`models_cache.json`, inspected
2026-09-11) and the [official OpenAI model catalog](https://developers.openai.com/api/docs/models).
Installed `codex-cli 0.154.0` exposes `--model` and `-c`; `CodexBackend` forwards
the resolved model and `model_reasoning_effort` through those options.

`ModelProfile`/`validate_profile` is a static shape/vendor/effort contract, not a
canonical known-model registry or account-access probe. The harness accepts
`low`, `medium`, `high`, and `xhigh` for Codex. Those efforts are present for all
four models in the host catalog. The catalog also advertises `max` (and `ultra`
for some models), but this harness rejects both. No profile, model ID, effort
alias, provider, or backend is added here. In particular, benchmark
"extra-high" corresponds to the catalog's `xhigh`; it is not an accepted literal
`extra-high` setting. Live inference/access tests were not run; per-account
access remains `unknown` until actual dispatch.

### Evidence and interpretation

The following VulcanBench SWE-v3/v4 figures are the user-supplied reference
snapshot for this decision, not measurements from dinner-harness or an
independently reproduced benchmark. SWE-v3 and SWE-v4 scores are not compared
directly across suites: task suites and scoring differ. Use v3 only to explore
Luna/Terra/Sol cost-performance, and v4 only to compare Astra efforts.

| SWE-v3 model | Effort | Score | Cost/task | Time/task |
| --- | --- | ---: | ---: | ---: |
| Luna | low | 77% | $0.03 | 1.2 min |
| Luna | medium | 80% | $0.06 | 2.1 min |
| Luna | high | 86% | $0.17 | 3.8 min |
| Terra | medium | 87% | $0.19 | 2.3 min |
| Sol | high | 87% | $0.69 | 4.2 min |

| SWE-v4 Astra effort | Combined | Code Quality | Cost/task | Time/task |
| --- | ---: | ---: | ---: | ---: |
| low | 87.43 | 70.31 | $1.72 | 4.2 min |
| medium | 87.73 | 71.19 | $1.48 | 3.8 min |
| high | 88.16 | 73.48 | $1.71 | 4.9 min |
| extra-high | 89.16 | 75.47 | $2.30 | 8.1 min |
| max | 89.30 | 76.26 | $2.57 | 10.3 min |

### Decision

Both `codex_only` and `hybrid` resolve the following automatic builder tiers
from TOML; the table documents that decision, not a runtime fallback:

| Compute | Model | Effort | Sufficient workload |
| --- | --- | --- | --- |
| LOW | `gpt-5.6-luna` | `medium` | Bounded mechanical edits, existing-pattern replication, small localized fixes/tests, docs/code synchronization; clear requirements and easy rollback |
| NORMAL | `gpt-5.6-terra` | `medium` | General features, moderate refactors, some repo exploration and subsystem integration using existing abstractions |
| HIGH | `gpt-6-astra` | `high` | Architecture-sensitive changes, ownership/lifetime or public API/invariant reasoning, ambiguity, large blast radius or difficult reversal |

- **Luna remains the cheap executor.** LOW includes small fixes and tests, not
  just text substitution. Medium offers a modest sufficiency margin over low
  in v3 while retaining low cost/latency. This is a conservative starting
  policy, not proof of a measured retry reduction. Low remains an explicit
  choice for purely mechanical work. Luna high costs more and takes longer
  than medium; tasks requiring that much reasoning are better candidates for
  NORMAL/Terra evaluation than inflating every LOW dispatch.
- **Terra medium is the cost-efficient general builder.** Within v3 it is
  1 point above Luna high for $0.02 more and 1.5 minutes less, and matches Sol
  high's aggregate score at substantially lower cost and latency. There is no
  repository-specific evidence requiring Sol as an intermediate builder.
- **Sol leaves automatic builder routing only.** Its independent
  `codex_only.reviewer` role is retained, and explicit model selection remains
  available. No unrelated profile is removed or reassigned.
- **Astra high is reserved for frontier reasoning.** The harness forces HIGH
  compute for HIGH risk, including ownership/invariant and difficult-to-reverse
  work. Within v4, high adds 0.43 Combined and 2.29 Code Quality over medium for
  about 16% more cost and 29% more time. That selective quality trade-off fits
  this tier; it does not justify sending routine NORMAL work to Astra.
- **Astra low is excluded from automatic routing.** In the supplied v4 sample,
  medium has higher scores, lower cost, and lower latency. Astra medium is an
  explicit escalation candidate when Luna/Terra reasoning is insufficient on
  non-HIGH-risk work. It does not become the general builder default.

Optimize sufficiency, expected cost to successful completion, and interactive
latency before buying more reasoning. Do not infer retry probabilities from
aggregate scores. If failures or review rejection expose missing repo reasoning,
reassess compute instead of repeatedly retrying an insufficient cheap model.
This is selection guidance; no automatic retry ladder or new scheduler is added.

### Explicit escalation and preserved boundaries

For non-HIGH risk, existing `build --builder-model gpt-6-astra
--builder-effort medium` selects Astra explicitly; `high` or `xhigh` can be
chosen when warranted. `xhigh` is exceptional debugging/one-off work only,
never an automatic LOW/NORMAL/HIGH default. `max` is outside the current harness
contract even as an override; it is only a possible manual choice in a Codex
surface that independently supports it. Do not claim that path provides harness
HIGH challenge/review enforcement.

For HIGH risk, the controller requires explicit model/effort values to match
the configured profile exactly; even `xhigh` cannot bypass that guard. A deliberate
HIGH policy escalation requires a reviewed configuration change and fresh bound
challenge evidence. This change does not relax that restriction. Within v4,
medium to max adds about 1.57 Combined for 74% more cost and 171% more time,
supporting exceptional rather than automatic use.

Risk remains distinct from compute. HIGH risk still forces HIGH compute and its
independent challenge/review/human acceptance chain; HIGH compute alone does not
invent HIGH-risk approval requirements. Preserve preset-driven `ModelProfile`
resolution, explicit overrides within those existing bounds, explicit vendor
compatibility maps, missing/invalid-config failure, and reference/orchestration
separation. Legacy install-time `builder_vendor` policy is not reintroduced;
the existing runtime override/receipt field of that name remains valid.

Changing TOML changes the policy digest: prior bound HIGH challenge evidence
must be regenerated before dispatch under the new policy. This intentionally
prevents stale authorization of a different builder lineup.

### Expected cost relative to the latest main baseline

The baseline default `codex_only` already uses the chosen three profiles: its
LOW, NORMAL and HIGH model costs/latencies are unchanged. In `hybrid`, LOW moves
from Luna high to medium (lower sampled cost and latency with less reasoning),
NORMAL remains Terra medium, and HIGH moves from Sol high to Astra high for the
frontier role. Do not calculate a HIGH cost ratio from different SWE suites.
HIGH spend may increase; overall hybrid spend depends on workload mix and
retries, which have not been measured. The default direction is **similar**,
while hybrid savings are expected only for LOW-heavy workloads, not guaranteed
overall. The benefit is consistent cost-tier intent and preventing unnecessary
Astra use in routine work, not a claimed across-the-board cost reduction.

## Alternatives considered

- **`routing.py` hardcoded hybrid fallback when `routing.toml` is missing**
  (Architect's original proposal): rejected by the user — creates a second
  location for concrete model literals, defeating the SSOT goal.
- **Regression test pinning `harness.toml.builder_vendor ==
  routing.toml.hybrid.builder_normal.vendor`**: rejected by the user — couples
  an install-time doc-rendering variable to the runtime routing SSOT, which
  would require updating `harness.toml` every time the routing strategy changes.
- **A separate Architect-launcher/framework to make `routing.toml`'s `architect`
  profile actually retarget the user's own interactive session**: rejected —
  out of scope, and the primary path's whole value proposition (single-pane,
  the user's own terminal) would need product-level changes (invoking a
  different CLI *for the user's own session*) this harness does not control.
