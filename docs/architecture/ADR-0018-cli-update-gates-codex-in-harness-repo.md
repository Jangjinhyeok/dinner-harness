# ADR-0018: `cli-update` gates a codex-cli promotion inside the harness repo instead of always applying it first

- **Status:** Accepted
- **Date:** 2026-08-31
- **Deciders:** user + Architect session

## Context

`content/skills/cli-update/SKILL.md`'s current lifecycle for `codex` inside the
dinner-harness repo is: Phase 4 unconditionally runs `npm install -g
@openai/codex@latest` for any tool marked UPDATE AVAILABLE; Phase 6 then checks
(only *after* the install already happened) whether the repo contains
`orchestrator/vendors.py` and, if so, prints a warning that several pieces of
version-pinned safety-net code (`parse_apply_patch`, `CodexBackend`'s `codex exec`
parsing, `adapters/codex.py`'s hooks.json/agents.toml generation) are not
auto-verified against the new release; Phase 7 then mechanically relabels five
version-sensitive comments as "NOT re-verified"; Phase 8 (the actual compatibility
re-verification procedure) is explicitly documented as "never run automatically."

Commit `a6f450e0` is a live instance of exactly this sequence: codex-cli 0.149.1 was
npm-installed to 0.151.0, five comments were relabeled "NOT re-verified," and no
functional re-check occurred in that commit. The user's re-verification (Finding
A5) named this "production changes first, compatibility confirmed later" ordering as
the most concrete live problem in the current harness, since this repo's Codex Builder
dispatch depends on `parse_apply_patch` correctly parsing whatever payload shape the
live `codex-cli` actually emits — a silent format drift there degrades the harness's
only automatic defense during a Codex Builder run without raising any error.

## Decision

Add a harness-compatibility gate to Phase 4, scoped narrowly to `codex` inside a
repo that contains `orchestrator/vendors.py` (the same detection Phase 6 already
uses, just moved earlier). When that specific condition holds and codex is marked
UPDATE AVAILABLE, `cli-update` stops before running the install command, explains
the risk, and waits for the user's explicit go-ahead in the same interactive
invocation — it does not build a separate isolated-candidate-install pipeline
(rejected as disproportionate complexity per the user's own framing: "isolated
candidate 설치가 지나치게 복잡하다면 자동 live update를 중지하고 ... 멈추는 구조가
더 낫다"). `claude` updates and `codex` updates outside the dinner-harness repo are
completely unaffected — they keep today's immediate-apply behavior, since the
version-pinned-code risk is specific to this repo's integration code, not to CLI
updates in general.

## Implementation Guidelines

- Insert the gate at the top of Phase 4, before the existing "For every tool marked
  UPDATE AVAILABLE" loop. The gate only fires for `codex` + harness-repo detected;
  everything else proceeds exactly as before, including codex updates in any other
  repo and all claude updates everywhere.
- On the gate firing, print a warning naming the specific version-pinned surfaces
  (safety-net payload parsing, `codex exec` output parsing, hooks/agents-schema
  generation) and pointing to Phase 8, then wait for explicit user confirmation
  before running `npm install -g @openai/codex@latest` for codex specifically. If
  the user does not confirm, skip the install for codex and report it as "update
  available, held pending compatibility check" in Phase 5 rather than silently
  dropping it.
- Do not modify Phase 5 (report format), Phase 6 (post-install warning — still
  fires correctly if the user did confirm and codex was in fact updated), Phase 7
  (mechanical relabeling), or Phase 8 (manual re-verification procedure) — none of
  their existing logic changes; Phase 6's detection condition is simply evaluated a
  second time naturally as part of its own unchanged flow.

## Consequences

- **Positive:** closes the exact "latest != trusted" gap Finding A5 identified and
  `a6f450e0` exhibited — a future codex-cli bump inside this repo now requires an
  explicit human decision before the live install happens, not just an
  after-the-fact warning.
- **Positive:** zero behavior change for the common case (claude updates, codex
  updates in any non-harness repo) — the gate is scoped as narrowly as the existing
  Phase 6 warning already was, just moved before the action instead of after it.
- **Negative / trade-off:** a user who previously ran `cli-update` inside
  dinner-harness expecting a silent codex bump now gets an interactive prompt
  instead. This is the explicit point of the fix, not an accidental regression.
- **Negative / trade-off:** the gate does not itself perform any compatibility
  verification — it only stops and asks. A user who confirms anyway gets exactly
  today's behavior (label swap, no functional check) unless they separately run
  Phase 8. Building automatic isolated-candidate verification was explicitly
  rejected as disproportionate for this cycle (see Alternatives).

## Alternatives considered

- **Isolated candidate install + automated Phase 8 compatibility suite run before
  promotion:** rejected for this cycle as disproportionate complexity — running a
  second `codex-cli` version side-by-side (separate npm prefix or container) and
  driving the full Phase 8 procedure (apply_patch payload check, `codex exec`
  output check, install pipeline check) automatically is a meaningfully larger
  undertaking than a stop-and-ask gate, and the user's own brief explicitly endorsed
  falling back to "stop and ask" when isolated verification is too complex to
  automate cheaply.
- **Leave Phase 4 unconditional and only strengthen the Phase 6 warning's wording:**
  rejected — this is the status quo (already warns, just after the fact); it does
  not change the "production first, compatibility later" ordering the finding
  specifically flagged as the actual problem.
