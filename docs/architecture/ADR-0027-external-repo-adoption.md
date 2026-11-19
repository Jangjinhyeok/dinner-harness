# ADR-0027: External repositories — default no-op, classify by the surface they touch

- Date: 2026-11-20
- Status: **Proposed.** Recorded in the repo at the user's request on 2026-11-20 together with the Ponytail port below; acceptance of the open decisions is pending (see "Open decisions"). Nothing is installed or changed by this ADR itself.
- Source: draft from another session, based on the repo at `147ae35` (2026-11-18) and the READMEs of ten repositories the draft labels as the 2026-10-21 trending list; verified against this repo at `70abc0a`.
- Risk, stated per part:
  - This ADR text: LOW. `docs/architecture/` is not installed by any target (`harness.toml` copies only `content/docs`).
  - The Ponytail port recorded below: LOW. It changes the text of four installed skills in both targets, effective from the next live install; it changes no installer, template or hook and is reversible.
  - Any installer change chosen under "Install-contract options" is a separate HIGH change (live `settings.json` reaches every session; build/packaging pipeline).
- Generalizes: ADR-0025 (official plugins augment the harness). ADR-0025's Decisions 1, 3 and 4 and its Boundary stay valid. Its Decision 2 installs predate this rule and fit row 3 below only through that row's exception (see Open decision 5).

## Context

- Trending repositories come up repeatedly with no rule for whether to absorb them, install them beside the harness, or ignore them.
- The harness install contract decides what survives next to it. Verified 2026-11-20 at `70abc0a` by rendering into a scratch `--dest`, adding third-party entries, re-running `install.py --dest`, and running `check.check_install` (live home untouched):
  - `adapters/claude.py:37` merges `{**existing, **rendered}`; only `permissions.allow/ask/deny` are unioned (`:43-49`). The template owns `extraKnownMarketplaces`, `env`, `permissions`, `hooks`.
  - Third-party `hooks` entries (new events and extra entries on template events), `extraKnownMarketplaces` entries and `env` variables are **removed** by the next install. `enabledPlugins`, `statusLine` and other non-template keys survive, so a plugin can stay enabled while its marketplace declaration is gone.
  - Before reinstall, `check.py` reports the drift one line per key, e.g. ``settings.json: 키 내용 다름 — `hooks` ``, and likewise for `env` and `extraKnownMarketplaces` (`check.py:235-236`). After reinstall it reports nothing — the loss is silent.
  - A skill copied into `~/.claude/skills/<name>/` is kept by install but reported by `check.py` as a **blocking** leftover (exit 1): `skills` is a manifest-owned dir, `shared_dirs = []`, and `vendor_dirs` covers only `skills/synced`. The same applies to `agents/`.
  - Plugin-delivered hooks live in files inside the plugin under `~/.claude/plugins/` (by default `hooks/hooks.json`; a plugin may name other files in its `plugin.json`, as Ponytail does), not in `settings.json`, so the merge does not touch them; plugin skills live under `plugins/`, which is not an owned dir.
  - The Codex adapter already preserves user hooks (`adapters/codex.py:304` `_merge_hooks`, receipt-based ownership, test `test_owned_hooks_remove_exact_prior_entries_only`); the Claude adapter has no equivalent.
- Example: Orca (`stablyai/orca` at `c34c424`, main on 2026-11-19; `src/main/claude/hooks/hook-settings.ts:59`) writes its managed hooks into `~/.claude/settings.json` for many events (SessionStart, UserPromptSubmit, Stop, PreToolUse, PostToolUse and others, version-gated), with the managed script built with `decidesPreToolUse: this.options.agent === 'claude'`, true for Claude (`src/main/claude/hook-service.ts:105`; the script body was not read), plus `statusLine`. Whether Orca re-installs its hooks on its own after they are removed was not determined. A harness install removes the hooks and keeps the `statusLine`.

## Decision (proposed)

1. **Default is no-op.** Proceed only when a trigger is named: an observed failure (e.g. a `learnings-review` record) or a concrete recurring need the user states. Benchmarks in a project's README are not a trigger.
2. **Classify by the surface the tool touches, not by what it calls itself.**

| Surface | Handling |
|---|---|
| Separate app or separate workflow that writes nothing under `~/.claude` | Use it independently. Not a harness concern. |
| Runs only when invoked (skill, LSP, or an MCP server whose tool definitions are its only per-session footprint), upstream-maintained, and installed as a **plugin or at project scope** | Install separately; the harness does not manage it. Do not copy it into `~/.claude/skills` or `~/.claude/agents` (blocking leftover). |
| Runs without being invoked (hooks — including a plugin's own hooks —, CLAUDE.md/rules text, per-session instructions or context beyond tool definitions), or overlaps an existing skill/agent | Do not install. Port the idea into the existing file and record it (in the ADR that classified it, or an addendum). Exception (ADR-0025 precedent): a plugin may be installed as a plugin, with the reading recorded, when each condition of this row that applies to it is excused — hooks read in full that only inject context under a stated condition, and an overlap that is partial with the plugin kept optional. A plugin with both hooks and an overlap needs both excuses. |
| Writes the template-owned keys of user-scope `settings.json` (`hooks`, `env`, `extraKnownMarketplaces`) | Not supported at user scope under the current contract: the next install removes it. Use project scope, or decide an install-contract change first. |
| Replaces routing, memory or hooks wholesale (another harness) | Reject. |

3. **Deferred ("보류") needs a re-entry condition.** A deferred entry names what would change the answer (e.g. "UE macro parsing verified in a PoC"). Without one it is a rejection.
4. **No new vendoring.** Executable code or always-loaded text is not copied in. Existing exception: `content/ecc-reference/` (ECC cherry-pick, lookup-only, not auto-injected, ADR-0006 / CLAUDE.md). A new lookup-only excerpt follows the same terms and records source and license.

## Ported pattern: Ponytail (first application of this rule)

Trigger: no `learnings-review` record points at it; the user asked for this review on 2026-11-20 as part of a stated recurring need (deciding on trending repositories). If Open decision 2 settles on observed failures only, this port would not have qualified and stays only because the user accepted it.

`DietrichGebert/ponytail` (MIT, `96608e0`, plugin v5.3.3) is a prompt plus a plugin that adds SessionStart, SubagentStart and UserPromptSubmit hooks (node) and, by default, a per-turn ledger under `~/.config/ponytail/band/`. Under Decision 2 it runs without being invoked and overlaps `simplicity-first`/`surgical-changes`/`tech-debt`. The row-3 exception does not apply: its SessionStart hook (`startup|resume|clear|compact`, `hooks/ponytail-activate.js`) emits the ruleset on every session start unless its mode is set to `off`, so the hook excuse fails, and both excuses would be needed. It is not installed. From `skills/ponytail/SKILL.md`, three rules were compared with the harness:

- **Find callers before a bug fix; fix the root cause once in shared code.** Partly present (`surgical-changes` covered callers only for signature changes; `hotfix` used callers only to size verification). Added to `content/skills/surgical-changes/SKILL.md`, adapted for live service: when the shared-code fix reaches beyond the request or callers remain unchecked, compare it with a local fix and ask before editing, and the file's live-service rules take precedence; callers invisible to text search (`.uasset` references such as Blueprint and DataTable, name-string bindings) are reported as not checked.
- **Leave a small test or assert for non-trivial logic.** Mostly present (`goal-driven-execution`, `tdd-guide`). Not made mandatory: that contradicts the proportional "when justified" rule, and a UE automation test needs an editor run. No assert advice (`check()` is compiled out of Shipping). Only examples of "justified" were added to `content/skills/goal-driven-execution/SKILL.md`.
- **`shortcut: <limit>, <when to upgrade>` comments.** Absent. Added to `content/skills/simplicity-first/SKILL.md` as `shortcut: <limit>, <when to replace>` (project convention first; comment text in English per CLAUDE.md §3), and `content/skills/tech-debt/SKILL.md` now scans for these comments or the project's equivalent marker.

The four skills are copied to the Codex target unchanged apart from frontmatter quoting (`skills_src = content/skills`); `AGENTS.md` and the curation hash are unaffected.

## Install-contract options

| Option | Change | Risk | Test impact |
|---|---|---|---|
| A. Hook union | Port Codex `_merge_hooks`; add a retired-hooks list (like `retired_permission_rules`) or a receipt; key-merge `env` and `extraKnownMarketplaces` | HIGH. A template hook change not listed as retired leaves the old entry running beside the new one (e.g. `secret_scan` twice, or a stale `<CLAUDE_HOME>` path); install no longer resets to a known hook set | New merge tests; `check.py` must compare these keys as subsets (as `_hooks_drift` does for Codex) or external entries become permanent drift |
| B. Announce drops | Install and `--dry-run` list the hook/env/marketplace entries they will remove; the resulting file is unchanged | HIGH by policy wording (install pipeline); small blast radius | One or two output tests |
| C. Keep and document | This ADR's Decision 2 row; user-scope writers are unsupported, use project scope | LOW | None |
| D. Per-skill `vendor_dirs` | Add `"skills/<name>"` for an external skill that must live in `~/.claude/skills`; existing prefix logic applies | LOW (check-only, not installed) | None |

Making `skills` a `shared_dirs` entry is not listed: it would also turn stale harness skills into advisory leftovers.

Recommended: C now, with plugin or project-scope installs for skills and D only when needed; A when a concrete user-scope tool (Orca, graphify) is actually adopted, ported from the Codex implementation.

## Open decisions

1. Keep the `ecc-reference` exception in Decision 4.
2. Whether the trigger in Decision 1 includes "a concrete recurring need the user states" or only observed failures.
3. Which install-contract option (A–D) to adopt.
4. Corrections to the draft's trending classification proposed in review: Orca stays deferred, but on the verified settings-hook loss and CLAUDE.md §6 rather than ADR-0009 (which retired the headless Builder's linked-worktree procedure, not worktrees in general); headroom moves from deferred to rejected (no trigger, no stateable re-entry condition); cloudflare/security-audit-skill installs at project scope or as a plugin, not into `~/.claude/skills`.
5. Keep the row-3 exception, or reclassify ADR-0025's installs under the rule without it: `unreal-engine-skills-for-claude-code` has a SessionStart hook (conditional, inject-only, currently disabled) and `claude-md-management` partly overlaps `learnings-review`.

## Consequences

- Positive: one rule for every trending repo; the silent loss of user-scope hooks/env/marketplaces is written down instead of rediscovered (it was found separately for marketplaces in ADR-0025 and for graphify on 2026-11-19).
- Negative: tools that only support user-scope `settings.json` hooks (Orca, graphify user scope) stay unsupported until the contract changes.
