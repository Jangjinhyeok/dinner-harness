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
  Re-check these against the new codex-cli release (see CODEX-COVERAGE.md) before
  trusting Codex Builder dispatch or a fresh `install.py --target codex` again.
```

Do not edit `orchestrator/vendors.py`, `assets/claude/hooks/lib/common.py`,
`assets/claude/hooks/handlers/scope_check.py`, `assets/claude/hooks/handlers/secret_scan.py`,
`adapters/codex.py`, or `CODEX-COVERAGE.md` automatically — this is a warning
only. Updating the verified-version record or the parsing logic is a human
decision, not something this skill does.

### Notes

- This only ever touches global CLI tool installs (`npm -g`, Homebrew formula) for
  `claude`/`codex` — it does not touch project dependencies or any other package.
- npm global installs may need elevated permission depending on the npm prefix; if
  `npm install -g` fails with an EACCES/permission error, report the exact error
  and stop — do not retry with `sudo` or elevated privileges without the user's
  explicit go-ahead.
- If the user only asks about one tool, only touch that tool.
