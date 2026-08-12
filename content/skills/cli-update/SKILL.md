---
name: cli-update
description: "Check installed Claude Code CLI and Codex CLI versions against the latest available release, and apply the update automatically when one exists. Use when the user asks to check for Claude/Codex CLI updates, wants 'claude 버전 업데이트', 'codex 버전 확인', or wants CLI tools kept current."
argument-hint: "[claude|codex] (생략 시 둘 다 확인)"
user-invocable: true
allowed-tools: Bash, Read
model: haiku
---

# CLI Update Check

Checks whether the installed Claude Code CLI and/or Codex CLI have a newer version
available, and applies the update automatically when one exists. Read-only until an
update is confirmed available — the actual install/upgrade command only runs when a
newer version is detected.

**Argument:** `$ARGUMENTS[0]` — `claude`, `codex`, or omitted (checks both).

## Phase 1: Detect installed versions

For each target tool (`claude`, `codex`, or both per argument):

- Run `<tool> --version` (or `<tool> -v` if `--version` is unrecognized).
- If the command is not found, report "`<tool>` not installed — skipping" and move
  on. Do not attempt to install a tool that isn't present; this skill only updates
  existing installs.

## Phase 2: Determine install channel + latest version

Try each check in order, use the first that succeeds:

1. **npm global package** — `npm ls -g --depth=0` and look for
   `@anthropic-ai/claude-code` (Claude) or `@openai/codex` (Codex). If found, get
   the latest published version with `npm view <package> version`.
2. **Homebrew** (macOS/Linux only) — `brew list --versions <formula>` if the npm
   lookup found nothing and `brew` exists on PATH. Latest via `brew info <formula>`
   or `brew outdated`.
3. **Unknown channel** — if neither applies, report the detected local version,
   state the channel could not be determined, and point the user to the tool's
   official update method instead of guessing. Do not fabricate a subcommand.

## Phase 3: Compare + report

For each tool checked, report:

```
claude:  installed v<X> -> latest v<Y>   [UPDATE AVAILABLE | UP TO DATE]
codex:   installed v<X> -> latest v<Y>   [UPDATE AVAILABLE | UP TO DATE]
```

Compare as semver (major.minor.patch); treat a non-parseable local version string as
"unknown" and report it without a verdict rather than guessing.

## Phase 4: Apply updates

For every tool marked UPDATE AVAILABLE:

- npm channel: run `npm install -g <package>@latest`.
- Homebrew channel: run `brew upgrade <formula>`.
- Unknown channel: do not attempt an update — tell the user to update manually and
  how (point to the tool's official docs) and skip verification for it.

Run the update, then re-run `<tool> --version` to confirm the installed version now
matches the latest checked in Phase 2. If it doesn't match, report the mismatch
rather than declaring success — the update command may have silently no-op'd (e.g.
permission error, wrong global prefix).

## Phase 5: Report

One line per tool:
- Already up to date: `claude: already v<X>, no action taken`
- Updated: `claude: v<X> -> v<Y>, updated and verified`
- Update attempted but unverified: `claude: v<X> -> v<Y> attempted, verify failed —
  installed version is still v<X>. Check npm global prefix / permissions.`
- Not installed / unknown channel: report as-is, no action taken.

## Phase 6: Flag-drift warning (dinner-harness only)

If `codex` was updated in Phase 4, check whether the current working directory (or
the repo housing this skill install) contains `orchestrator/vendors.py`. If it
does, this is the `dinner-harness` harness repo, where several pieces of code
were hand-verified against a specific `codex-cli` release and are not guaranteed to
still match after an update:

1. **Safety net (highest priority — can fail silently)**: `assets/claude/hooks/lib/common.py`'s
   `parse_apply_patch`, used by `assets/claude/hooks/handlers/scope_check.py` and
   `secret_scan.py`, parses Codex's file-edit tool payload (`tool_name=apply_patch`)
   as observed on `codex-cli 0.141` (see `CODEX-COVERAGE.md` §6.2). If a newer
   `codex` changes this payload shape, `scope_check`/`secret_scan` can stop
   detecting edits correctly without raising any error — this is the harness's
   only automatic defense during a Codex Builder run (per
   `content/skills/delegate/SKILL.md`), so a silent miss here is worse than a
   loud dispatch failure.
2. **Dispatch parsing**: `orchestrator/vendors.py`'s `CodexBackend` class was
   hand-verified against a specific `codex-cli` release for its `codex exec`
   flags and output-parsing format (see the class docstring and
   `CODEX-COVERAGE.md`'s recorded verified version).
3. **Install pipeline**: `adapters/codex.py` generates `~/.codex/hooks.json` and
   `agents/*.toml` from `content/` assuming a Codex hooks.json / agents.toml
   schema observed on 0.140+/0.141 (see its module docstring). A schema change in
   a newer Codex could make `install.py --target codex` output stop matching what
   Codex actually expects.

In that case, after the Phase 5 summary, add:

```
⚠ codex was updated. This repo has version-sensitive code that was hand-verified
  against an older codex-cli release and is not auto-checked:
  - hooks/lib/common.py parse_apply_patch (+ scope_check.py / secret_scan.py) —
    the Codex Builder safety net; a payload-shape change here can fail silently.
  - orchestrator/vendors.py CodexBackend — `codex exec` flags / output parsing.
  - adapters/codex.py — ~/.codex hooks.json / agents.toml generation schema.
  Re-check these against the new codex-cli release before trusting Codex Builder
  dispatch or a fresh `install.py --target codex` again — see Phase 8 for the
  exact re-verification steps.
```

Phase 7 performs a narrow, mechanical version-label swap in five of these
locations (not `CODEX-COVERAGE.md` — its dated history log stays warning-only,
see Phase 7). Both this warning and Phase 7 only ever touch a version number and
an added caveat comment; the actual `apply_patch`/`codex exec` parsing logic is
never auto-edited — re-verifying and fixing that logic, if it actually changed,
remains a human decision.

## Phase 7: Mechanical version-label update (dinner-harness only)

After printing the Phase 6 warning, also perform a narrow, mechanical version-label
swap in the five code-comment locations below — replace ONLY the old codex-cli
version number with the new one just confirmed in Phase 3, and add an inline
caveat marking the label as auto-updated and NOT re-verified. Never touch the
surrounding logic, and never touch `CODEX-COVERAGE.md` (it is a dated historical
log — mixing multiple past version numbers on purpose; a blind replace there would
corrupt history, so leave it as a manual follow-up instead).

Exact edits (`<OLD>` = the previously installed codex version from Phase 1,
`<NEW>` = the version confirmed in Phase 3):

1. `orchestrator/vendors.py` — in the `CodexBackend` docstring:
   - old: `` """`codex exec` non-interactive mode. Verified against codex-cli <OLD>. ``
   - new: `` """`codex exec` non-interactive mode. Verified against codex-cli <NEW>. (version label auto-updated by cli-update — NOT re-verified; confirm codex exec flags/output format before trusting this.) ``
2. `assets/claude/hooks/lib/common.py` — the comment above `_APPLY_PATCH_PATH_RE`:
   - old: `# Codex <OLD> sends file edits as tool_name="apply_patch" with the patch body in`
   - new: two lines — `# Codex <NEW> sends file edits as tool_name="apply_patch" with the patch body in` followed by `# (version label auto-updated by cli-update — NOT re-verified against <NEW>)`
3. `assets/claude/hooks/handlers/secret_scan.py` — the comment above `_TARGET_TOOLS`:
   - old: `# "apply_patch" is Codex <OLD>'s file-edit tool (CODEX-COVERAGE.md §6.2); Claude`
   - new: `# "apply_patch" is Codex <NEW>'s file-edit tool (CODEX-COVERAGE.md §6.2, version label auto-updated by cli-update — NOT re-verified); Claude`
4. `assets/claude/hooks/handlers/scope_check.py` — the comment above `_TARGET_TOOLS`:
   - old: `# "apply_patch" is Codex <OLD>'s file-edit tool (CODEX-COVERAGE.md §6.2); it`
   - new: `# "apply_patch" is Codex <NEW>'s file-edit tool (CODEX-COVERAGE.md §6.2, version label auto-updated by cli-update — NOT re-verified); it`
5. `adapters/codex.py` — the module docstring line:
   - old: `Cycle 3 / adapter v2 targets current Codex (0.140+ / <OLD> observed):`
   - new: `Cycle 3 / adapter v2 targets current Codex (0.140+ / <NEW> observed, version label auto-updated by cli-update — NOT re-verified):`

Apply each edit only if the exact old string (with `<OLD>` substituted for the
actual previously-recorded version in that file) is still present — the file may
have drifted since this skill was last updated, in which case skip that file and
say so in the report rather than guessing at a different match. After editing,
report which files were changed, and remind the user these are label-only edits:
the underlying `apply_patch`/`codex exec` parsing logic still needs a human (or a
separate Codex Builder task) to actually re-verify against the new codex-cli
release before it can be trusted again.

## Phase 8: Manual re-verification procedure (dinner-harness only)

Phase 6/7 only warn and relabel — they never confirm behavior actually still
matches. When the user (or a future session) is ready to actually re-verify,
this is the exact procedure (mirrors the 2026-08-10 run recorded in
`CODEX-COVERAGE.md` §6.3):

1. **`apply_patch` payload check** (covers `hooks/lib/common.py` parse_apply_patch
   + `scope_check.py`/`secret_scan.py`): with `~/.codex/hooks.json` installed and
   `CLAUDE_SCOPE_WHITELIST_MODE=enforce` set, have a Codex Builder (or a direct
   `codex exec` call) attempt to edit a file outside a deliberately narrow scope
   fence in a scratch directory. Then check
   `~/.codex/hooks/logs/scope_check.log` for a fresh entry: `tool_name` should be
   `"apply_patch"`, `file_path` should be the exact path just edited (correctly
   extracted from the patch envelope), and `decision` should be `"block"`. If
   `tool_name` is missing, `file_path` is wrong/empty, or the handler errors
   instead of deciding, the payload shape has drifted and `parse_apply_patch`
   needs an actual code fix, not just a label swap.
2. **`codex exec` output check** (covers `orchestrator/vendors.py`
   `CodexBackend`): this one is nearly free — any normal
   `orchestrate.py build --backend real` run already exercises it. If the build
   reaches `BUILT`/`BLOCKED` with a parsed verdict instead of erroring out on
   unparseable output, the output-parsing format still matches. No separate step
   needed beyond doing one ordinary delegate/architect build after the update.
3. **Install pipeline check** (covers `adapters/codex.py`): run
   `py -3 install.py --target codex --dest <scratch-dir>` (a scratch `--dest`,
   never live `~/.codex`, unless `--allow-live` is intended) and confirm
   `hooks.json`/`agents/*.toml` are generated without error and match what the
   installed codex-cli actually loads (e.g. `codex features list` still reports
   `hooks`/`multi_agent` stable).
4. **Record the result** as a new dated `### 6.x <version> 재검증 (<date>)`
   section in `CODEX-COVERAGE.md`, following the exact shape of the existing
   `### 6.3 0.147.0 재검증 (2026-08-10)` section — new section, never edit
   older dated sections (they are frozen historical snapshots, not "current
   status").
5. **Only after that record exists**, update the five Phase 7 caveats from
   `(version label auto-updated by cli-update — NOT re-verified)` to
   `(re-verified <date> — see CODEX-COVERAGE.md §6.x)` — same shape as the
   existing citations, single-file mechanical edits like any other LOW change.

This phase is never run automatically by `cli-update` — it is what a human (or a
follow-up session the user explicitly starts) does after reading the Phase 6
warning. Do not skip straight to step 5 without doing steps 1-3 first; that
would fabricate a "re-verified" claim the way an unchecked label swap risks
doing.

### Notes

- This only ever touches global CLI tool installs (`npm -g`, Homebrew formula) for
  `claude`/`codex` — it does not touch project dependencies or any other package.
- npm global installs may need elevated permission depending on the npm prefix; if
  `npm install -g` fails with an EACCES/permission error, report the exact error
  and stop — do not retry with `sudo` or elevated privileges without the user's
  explicit go-ahead.
- If the user only asks about one tool, only touch that tool.
