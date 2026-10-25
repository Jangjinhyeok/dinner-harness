# ADR-0025: Official Claude Code plugins augment the harness; they do not replace it

- Date: 2026-10-25
- Status: decided by user (keep the harness, augment selectively); implemented in the working tree; plugins installed at user scope; independent review APPROVE after two fix rounds (`code-reviewer`, 2026-10-25); accepted by user 2026-10-25; live harness installation follows this commit
- Risk: HIGH (settings-template key that reaches live `~/.claude/settings.json` on install, as in ADR-0023/0024; reviewer verdict criteria used by every project's HIGH review)
- Source: anthropics/claude-plugins-official (Apache-2.0 repository; each plugin carries its own license), inspected 2026-10-25 at `main`; external plugins at the SHAs pinned in `.claude-plugin/marketplace.json`

## Context

- The user asked whether to delete this harness and use the official plugin marketplace instead, or keep the harness and borrow structure from it. The marketplace lists 315 plugins; 39 are maintained by Anthropic under `plugins/`, the rest are partner or community plugins. The README states that Anthropic does not control or verify what third-party plugins ship.
- No plugin covers what the harness exists for: LOW/HIGH risk policy and acceptance reporting, `secret_scan` (pre-write blocking, enforce), `shell_guard`, `scope_check`, `learning_log` + `learnings-review`, the game-dev agents and specialist docs, the Codex target, and the install/check/CI pipeline. hookify can approximate `shell_guard`/`scope_check` with regex rules but has no lexer.
- Several candidates do not run cleanly on this Windows (cp949) machine: hookify calls `python3` and opens files without an encoding on every tool call and prompt; ralph-loop and plugin-dev scripts need `jq`; skill-creator's eval runner uses `select.select()` on pipes.
- Others conflict with policy or duplicate built-ins: commit-commands `/commit-push-pr` creates a branch when on `main` (CLAUDE.md §6) and `/clean_gone` force-deletes branches and worktrees; feature-dev gates implementation on approval, against LOW autonomy; code-review (GitHub PR only), code-simplifier and skill-creator overlap the built-in `/code-review`, `/simplify` and `anthropic-skills:skill-creator`. security-guidance creates a venv from PyPI at SessionStart, runs `git stash create` on every prompt, and sends diffs to the API for Opus review at Stop and on commit/push, billed on top of session usage.
- `claude plugin marketplace add` declares the marketplace in `~/.claude/settings.json` under `extraKnownMarketplaces`. The Claude adapter merges the rendered template over the live file (`adapters/claude.py` `_merge_template_json`): the template owns its top-level keys, and it shipped `"extraKnownMarketplaces": {}`. A live install would therefore drop the marketplace declaration. Before it was added, `claude plugin marketplace list` showed only the built-in `anthropic-plugin-directory`, so installed plugins would likely lose their source (not tested). `enabledPlugins` is not a template key and survives the merge.

## Decision

1. **Keep the harness as the source of truth.** Plugins are an add-on layer managed by `claude plugin`, not by `install.py`.
2. **Install three plugins at user scope from `claude-plugins-official`:**
   - `unreal-engine-skills-for-claude-code` 3.1.1 (Epic, MIT, SHA `a6aa73a`): editor-control skills plus a SessionStart hook that only injects a note when a `*.uproject` is found walking up from the cwd. Installed files were compared with the reviewed copy. **Disabled 2026-10-25** (`claude plugin disable`, still installed): it needs UE 5.8 (see Boundary).
   - `clangd-lsp` 1.0.0: LSP config only. Requires `clangd` on PATH (LLVM 23.1.4 installed with winget; `C:\Program Files\LLVM\bin` appended to the user PATH).
   - `claude-md-management` 1.0.0: no hooks; edits CLAUDE.md only after approval. Overlaps `learnings-review` in part; kept as optional.
3. **The template declares the marketplace.** `assets/claude/settings.json.template` sets `extraKnownMarketplaces.claude-plugins-official` (GitHub `anthropics/claude-plugins-official`) so a live install keeps it.
4. **Port one pattern instead of installing the plugin.** From `code-review`: a 0-100 confidence rubric, report only at 80 or more, and an explicit false-positive list, added to `content/agents/_core/code-reviewer.md` and `content/skills/adversarial-review/SKILL.md`. Adaptations:
   - No separate scorer agent; the reviewer scores its own candidates (it has no Agent tool), and there is still no fixed judge count.
   - The score measures evidence only (refuted, untraced, partly traced, one link unconfirmed, confirmed). Severity, rarity, pre-existing status and instruction violations are handled by severity and the exclusions, not by the score.
   - Checks: errors a check already reported on the reviewed state are not restated line by line, but a required check that failed is itself a material finding and can produce FAIL. A check that did not run is `not_run`. UE projects have no guaranteed CI build.
   - Regressions the change causes on unmodified lines stay in scope, and requested behavior changes are excluded only when they break no contract the request did not waive.
   - Material candidates below 80 are verification gaps or BLOCKED, never silently dropped, matching the existing rule that uncertainty alone is not a defect.
   - The skill names the role instead of linking `agents/`, because the Codex adapter flattens agents into `agents/<name>.toml`.

## Boundary

- The harness does not install, pin or verify plugins. `check.py` does not report plugin state, and the template declares the marketplace only; another machine needs `claude plugin install` by hand.
- The template owns `extraKnownMarketplaces` as a whole. A marketplace added later with `claude plugin marketplace add` is removed by the next live install unless it is also added to the template.
- Plugin updates follow the marketplace. A third-party plugin can change hooks or MCP servers between versions; re-read its hooks and `.mcp.json` before accepting an update.
- The Epic plugin does not ship an MCP server config. The editor must enable the `ModelContextProtocol` and `AllToolsets` plugins and generate `.mcp.json`. The plugin's own docs state no minimum UE version.
- **UE 5.7 cannot use it (checked 2026-10-25).** The UE 5.7 install has no `ModelContextProtocol` plugin under `Engine/Plugins`, and Epic's page for the feature (dev.epicgames.com, "Unreal MCP in Unreal Editor") is in the UE 5.8 documentation and marks it Experimental. The page does not say which version first shipped it. The plugin's SessionStart hook does not check the engine version, so on a 5.7 project it points the agent at the `unreal-mcp` skill and at a console command that does not exist there; with a `remiphilippe/mcp-unreal` `.mcp.json` present it reports that config as ready. For this reason the plugin is disabled. On UE 5.7 the existing `remiphilippe/mcp-unreal` setup (`assets/claude/MCP-UNREAL-SETUP.md`) remains the editor MCP.

## Consequences

- **Positive:** C/C++ code intelligence without new harness code, and official UE editor skills ready to re-enable on UE 5.8; reviewer findings are filtered by an explicit confidence bar and exclusion list.
- **Negative / trade-offs:** when the Epic plugin is enabled, one more SessionStart hook (Git Bash, 5 s timeout) runs in every session; plugin content is outside the harness's tests and review; the confidence bar can hide a real defect that the reviewer could not verify, which is why material candidates below 80 must be reported as gaps or BLOCKED.
- **Follow-ups:**
  - Generate `compile_commands.json` for UE projects so clangd resolves includes.
  - When a project moves to UE 5.8, re-enable the Epic plugin (`claude plugin enable`), evaluate it against `remiphilippe/mcp-unreal`, and update `MCP-UNREAL-SETUP.md` with the result.
  - Optionally add the rubric to `cpp-reviewer` directly; today it receives it through the adversarial-review dispatch. Its verdict terms (Approve/Warning/Block, where Block means a defect) also differ from the skill's BLOCKED (missing evidence).

## Alternatives considered

- **Delete the harness and run on plugins** — rejected: loses the safety hooks, risk policy, game-dev roles and Codex target, and several replacements fail on this machine.
- **Install code-review, pr-review-toolkit or feature-dev** — rejected: duplicate the built-in skills and the existing `code-reviewer`/`planner`/`architect` roles, and feature-dev's approval gate contradicts LOW autonomy.
- **Install security-guidance** — rejected: network installs, per-prompt git commands and extra billed LLM review; `secret_scan` already blocks before writes.
- **Install hookify for user-defined rules** — rejected: `python3` and encoding issues on this machine, and it runs on every tool call alongside the existing hooks.
