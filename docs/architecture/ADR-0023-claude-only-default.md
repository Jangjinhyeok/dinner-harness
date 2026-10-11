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
