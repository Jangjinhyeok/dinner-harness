# ADR-0023: Claude-only default and Codex as optional compatibility

- Date: 2026-10-11
- Status: accepted by user (direction and model basis); implemented in the working tree (2026-10-11), independent review APPROVE; awaiting user acceptance; live installation not performed
- Risk: HIGH (live `~/.claude/settings.json` hook set, install pipeline default)
- Supersedes: default-workflow portions of ADR-0008 (Builder-first), ADR-0012 (trivial fast path) and ADR-0022 (Codex inline default). Codex paths stay available as opt-in compatibility, mirroring how `claude_only` was kept after ADR-0022.

## Context

After ADR-0022 the canonical tree became Codex-first, but the Claude target was only partially migrated:

- `content/instructions/CLAUDE.md` still describes the Builder-first model (Claude = Architect only, Codex Builder dispatch, `builder_guard` blocks Edit > 2 lines and every Write, `route_nudge` pushes `/delegate`).
- `content/rules/*` and `content/roles/*`, installed into the same `~/.claude`, already describe a Codex inline default ("Codex 기본은 같은 세션의 설계·구현·검증").
- A Claude session therefore receives contradictory instructions: "do not implement" and "implement in the same session".
- `claude_only` preset model IDs (`claude-sonnet-5`, `claude-opus-5`) are a generation behind (current: Opus 5.5, Sonnet 5.5).

## Decision

1. The Claude main session designs, implements and verifies inline, matching the ADR-0022 policy with Claude as the vendor. Native subagents are optional for independent boundaries. HANDOFF/RESULT/challenge/build remain an opt-in path.
2. `[routing].preset = "claude_only"` in source. The Codex target renders `routing.toml` with `preset = "codex_only"` (`harness.toml [targets.codex] routing_preset`, `adapters/codex.py _write_routing`) so a Codex-only machine never resolves to a Claude backend; all profiles stay identical to the source. `codex_only` and `hybrid` remain selectable compatibility presets; the Codex target (`assets/codex`, `adapters/codex.py`, `CodexBackend`) is kept, not deleted.
3. `builder_guard` is removed entirely (handler, launcher, settings registration, tests, the `DINNER_EXECUTION_MODE=direct` escape). Its only purpose was forcing Claude implementation into Codex dispatch; the Codex target never registered it (`adapters/codex.py` hooks exclude it), so no compatibility path depends on it. A plain `claude` session becomes the direct-edit session. `route_nudge` no longer instructs Codex dispatch. Launchers that exist only to escape the guard (`claude-direct.cmd`, `dh*.cmd`) are retired. `secret_scan` and `scope_check` remain — they are safety nets, not workflow routing.
4. Default target in README/check/install guidance becomes `claude`.

## Model selection (claude_only)

Basis: VulcanBench Frontier v4, "Claude Sonnet 5.5 vs Claude Opus 5.5 vs GPT-6.1 Sol" (2026-10-08, 23 tasks × 5 efforts, Claude Code harness). https://vulcanbench.com/benchmarks/swe-v4-sonnet55-vs-frontier.html

| Role | Profile | Reason |
|---|---|---|
| architect | `claude-opus-5-5` / medium | 90.86 ±0.64, 23/23, $2.84, Opus 4.8 fallback 6.4% of replies — best quality/cost point |
| challenger_high | `claude-opus-5-5` / high | 91.11 ±0.57, code quality 77.99; rare HIGH-only call, accepts 20.9% fallback |
| builder_low | `claude-opus-5-5` / low | 86.36, $1.70, 13.7 min, no fallback; dominates Sonnet low (81.63, $2.88) and medium (84.10, $3.00) |
| builder_normal | `claude-opus-5-5` / medium | same as architect |
| builder_high | `claude-sonnet-5-5` / max | highest 92.02 ±0.35, 23/23, code quality 81.72, no fallback; cost $5.52 and 38 min accepted for HIGH compute |
| reviewer | `claude-opus-5-5` / medium | benchmark measures solving, not review; quality/cost point extrapolated |

Native agents: frontmatter `model: sonnet` → `model: opus` (alias), because Opus dominates Sonnet at the default/low-medium efforts the subagents run at.

Limits: 23 tasks, one attempt per cell, implementation-only (review/design roles are extrapolated), API list-price cost basis (subscription billing differs), Opus high efforts partly measure Opus 4.8. Fable 5.1 is not in the benchmark and is not selected. Not a proof of optimality; revisit when new data appears.

## Implementation gates (to run in a `claude-direct.cmd` session)

1. **Routing**: `content/routing.toml` preset + claude_only profiles above + header comments; `test_migration_routing.py` / `orchestrator/tests` fixtures referencing old Claude IDs; ADR-0020 addendum line pointing here. Keep the user's uncommitted Sol-xhigh codex_only edits intact.
2. **Instructions**: rewrite `content/instructions/CLAUDE.md` as a Claude counterpart of `assets/codex/AGENTS.md` (inline default, risk policy, delivery rules, game defaults, optional paths); de-Codex `content/rules/agent-routing.md`, `autonomy-policy.md`, `routing-reference.md`, `two-cli-reference.md`, `content/roles/*`, `content/rules/_mode/*` to vendor-neutral or Claude-first wording; agent frontmatter `sonnet` → `opus`.
3. **Hooks / target wiring**: delete `assets/claude/hooks/handlers/builder_guard.py`, `hooks/launchers/builder_guard.cmd`, `hooks/tests/test_builder_guard.py`; remove its `settings.json.template` registration and the builder_guard cases in `orchestrator/tests/test_orchestrator.py` (import at line 62, ~626-750; flip the line-626 assertion to `assertNotIn`); remove the `DINNER_EXECUTION_MODE` env handling in `orchestrator/vendors.py` (~line 40, ~485-498) while keeping `--permission-mode acceptEdits`/`plan`; fix references in `scope_check.py` docstring, `hooks/README.md`, `assets/claude/README.md`, `check.py` hook catalog (6 → 5 hooks, README parity); drop Codex-dispatch text from `route_nudge.py`; remove the `orchestrate.py build` allow rule only if no longer referenced; retire `claude-direct.cmd`, `dh.cmd`, `dh-architect.cmd`, `watch-builder.ps1` from `harness.toml [targets.claude]`. ADR-0008/0012 stay as history.
4. **Docs**: `README.md` / `README.en.md` / `assets/claude/README.md` to Claude-first; keep `check.py` catalog parity green.
5. **Cleanup** (user-approved): delete ignored test residue — repo-root `tmp????????/`, `gate-temp-20260831/`, `probe-temp-20260831/`, `assets/claude/tmp*`, `assets/claude/.builder-guard-test-local*`, `assets/claude/hooks/__pycache__/tmp*`.

## Verification

- Baseline before change (2026-10-11): `py -3 -m unittest discover -p "test_*.py"` 408 OK (4 skipped); `assets/claude/hooks/tests` 25 OK; `py -3 check.py --target claude --no-install` catalog parity OK.
- After change: same suites green; `py -3 install.py --target claude --dest <scratch>` and inspect rendered `settings.json` (no `builder_guard`) and `CLAUDE.md`; `py -3 check.py --target claude`.
- Independent review (code-reviewer) before acceptance. Live install (`--allow-live`) only after explicit user acceptance. The Claude adapter has no retire logic: stale live files (`claude-direct.cmd`, `dh*.cmd`, `hooks/handlers/builder_guard.py`, `hooks/launchers/builder_guard.cmd`, `HANDOFF_DELEGATE.md`, `AGENTS.md` in `~/.claude`; the guard files are inert once `settings.json` no longer registers them) must be listed for the user, not silently deleted.

## Addendum 2026-10-11: Claude install becomes 1-CLI

Decision (user-selected option B): the Claude target no longer installs Two-CLI/headless infrastructure — `orchestrate.py`, `orchestrator/`, `routing.toml`, `roles/`, `rules/_mode/`, HANDOFF/RESULT templates, `rules/two-cli-reference.md`, `rules/routing-reference.md`, the `delegate` skill (`drop_dests` in `adapters/claude.py`) and the settings `orchestrate.py build` allow rule. The orchestrator, `routing.toml`, roles and the two references stay installed by the Codex target; `content/routing.toml` stays the SSOT for headless profiles. The `delegate` skill (already in Codex `skills_drop`), `rules/_mode/` and the HANDOFF/RESULT templates are now source-only — no target installs them; deleting them is a separate decision.

Rationale: in a 1-CLI session these were never invoked but cost about 9.8KB of always-loaded context per session (`rules/routing-reference.md`, `rules/two-cli-reference.md`, the CLAUDE.md opt-in section), and opening a HANDOFF.md could still inject role reminders. Delegation uses native subagents.

`challenger_high` remains in every preset: the Claude install no longer reaches it, but the Codex headless path requires it (`routing.policy_digest`, HIGH build evidence gate).

Alternatives: A (only move the references out of auto-load) kept unused infrastructure in the Claude install; C (delete the orchestrator from the repo) would reverse the decision to keep Codex compatibility.

Live leftovers from earlier installs are not deleted automatically. `harness.toml [targets.claude] retired_dests` lists the paths earlier manifests placed outside owned dirs; `check.py` reports any that still exist as blocking leftovers. This matters most for `rules/*.md`: Claude Code auto-loads them, so stale references would keep consuming context and contradict CLAUDE.md until removed. `route_nudge` no longer mentions HANDOFF/Builder dispatch.

## Addendum 2026-10-14: Haiku 5.5 data reviewed, no routing change

New data: VulcanBench Frontier v4, "Claude Haiku 5.5 vs Claude Sonnet 5.5, GPT-6.1 Sol and GPT-6 Luna" (2026-10-12, same 23 tasks × 5 efforts, Claude Code harness). https://vulcanbench.com/benchmarks/swe-v4-haiku55-vs-frontier.html

| Effort | Haiku 5.5 combined | Judged n | Passed | $/task | Min/task |
|---|---|---|---|---|---|
| low | 84.42 ±1.97 | 23 | 13/23 | $1.04 | 22.9 |
| medium | 84.03 ±2.50 | 22 | 13/23 | $1.36 | 24.0 |
| high | 88.01 ±1.42 | 23 | 17/23 | $1.25 | 26.8 |
| xhigh | 91.83 ±0.39 | 22 | 22/23 | $0.84 | 19.0 |
| max | 92.16 ±0.37 | 21 | 22/23 | $1.54 | 27.7 |

Comparison with the current `claude_only` profiles:

| Role | Current | Haiku candidate | Verdict |
|---|---|---|---|
| builder_low | Opus low: 86.36, 17/23, $1.70, 13.7 min | xhigh: 91.83, 22/23, $0.84, 19.0 min | Haiku ahead on passes and cost even with its excluded failure scored 0 (≈87.8); kept as candidate, not applied |
| builder_normal / architect / reviewer | Opus medium: 90.86 ±0.64, 23/23, $2.84 | xhigh as above | keep; the score edge disappears with the excluded failure scored 0 (≈87.8) and it passes one task fewer |
| builder_high | Sonnet max: 92.02 ±0.35, 23/23, $5.52, 38 min | max: 92.16 ±0.37, 22/23, $1.54, 27.7 min | keep; score tie (0.14 points), one fewer pass, safety-stop risk on the role used for invariant/ownership work |
| low/medium efforts | Opus low 86.36 / medium 90.86 | 84.42 / 84.03, 13/23 each | Haiku clearly behind |

Decision: no change to `content/routing.toml` or native agent frontmatter.

Reasons:

1. Haiku's combined scores at medium/xhigh/max leave out paddockcore, where a safety classifier stopped the session with an empty patch (counted as failed in Passed, excluded from judged n). Scored as 0, xhigh drops to about 87.8 and falls below Opus medium. This is the same correction the report applies to GPT-6 Luna's timeouts.
2. Haiku's combined edge comes mainly from model-judged Code quality, not tasks solved; it passes fewer tasks than Sonnet from low to high. Correctness matters more for the game-client work this harness targets.
3. Haiku only wins at xhigh/max, but the Claude 1-CLI install has no effort control: `routing.toml` is not installed (Addendum 2026-10-11) and native agent frontmatter sets only `model: opus`. Changing the alias to `haiku` would likely run it at default effort, where it is weaker than Opus. Frontmatter effort support was not verified.
4. The candidate `builder_low` change would only affect the headless `claude_only` path, which the Claude install no longer ships, and would put builder_low above builder_normal in effort.

Limits: 23 tasks, one attempt per cell; judge protocols and Claude Code versions differ between columns (Haiku v3.24 on 2.1.293–2.1.296, Opus v3.15 on 2.1.280); Haiku has two price tiers by prompt length (sweep floor $31.10, ceiling $155.50, reported $138.31); API list-price basis, not subscription billing; not UE5/C++ specific.

Revisit when: Claude native agents can set effort, the headless `claude_only` path is used again, or a run with failures scored (or a larger task set) is published. A `builder_low` → `claude-haiku-5-5` / xhigh change would then need fixture updates in `test_migration_routing.py` and an entry here.
