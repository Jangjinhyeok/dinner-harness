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
