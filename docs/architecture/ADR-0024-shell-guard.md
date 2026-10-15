# ADR-0024: shell_guard — destructive-command and git-hook-bypass checks for shell tools

- Date: 2026-10-15
- Status: accepted by user (decisions 1–4 below); implemented in the working tree; independent review pending; awaiting user acceptance; live installation not performed
- Risk: HIGH (security hook, permission deny list, live `~/.claude/settings.json` on install)
- Source: rule taxonomy and test cases adapted from affaan-m/ECC (MIT, Copyright (c) 2026 Affaan Mustafa), commit `b92f181` — `scripts/lib/powershell-destructive-command.js`, `scripts/hooks/block-no-verify.js` and their tests

## Context

- Shell destructive commands were guarded only by two permission globs, `Bash(rm -rf *)` and `PowerShell(Remove-Item *-Recurse*)`. String globs miss reordered or abbreviated flags (`rm -r -fo`, `ri -Recurse`, `rmdir -r`), cmd syntax (`rd /s /q`), backtick escapes, .NET calls and nested interpreters (`pwsh -c`, `iex`, `Start-Process cmd`).
- The same globs block routine engine cleanup (`Remove-Item Intermediate -Recurse`, `rm -rf Library`); deny cannot be overridden by allow.
- Nothing checked git hook bypass (`--no-verify`, `commit -n`, `-c core.hooksPath=`, `git config core.hooksPath`, `include.path`).
- The hook README and `scope_check` say shell containment "belongs to the sandbox". The Claude Code docs (code.claude.com/docs/en/sandboxing) state the sandbox runs on macOS, Linux and WSL2 only; on native Windows commands run unsandboxed. On this harness's primary platform there is no sandbox, so that boundary was empty.

## Decision

1. **Placement (option b).** A new PreToolUse hook `shell_guard` (matcher `Bash|PowerShell`) with its own `CLAUDE_SHELL_GUARD_MODE` (`off`/`dryrun`/`enforce`), starting in `dryrun`. It reuses `run_handler` (fail-open, 200 ms watchdog) and the BAT launcher pattern. Sensitive-path rules go to `secret_scan` (`rules/secret_patterns.json`), which is already enforce. Cost: one extra Python process per shell call (~145 ms measured on this Windows PC); Claude Code runs matching hooks in parallel, so wall-clock overlaps `secret_scan`.
2. **Deny globs: removed now (revised 2026-10-15).** The original decision kept the two destructive deny globs through dryrun and removed them at enforce promotion. On 2026-10-15 the user chose to remove them from the template immediately, so `shell_guard`'s engine cleanup allowlist is the only gate. Until `shell_guard` is promoted to enforce, destructive shell commands are warned and logged but not blocked. The user accepted that gap in exchange for removing the friction on engine cleanup. The allowlist is exact top-level paths, active only at a marked project root: `*.uproject` → `Intermediate`, `Binaries`, `DerivedDataCache`, `Saved/Logs`; `ProjectSettings/ProjectVersion.txt` → `Library`, `Temp`, `obj`, `bin`. Settings merge keeps the union of permission lists (`adapters/claude.py` `_stable_union`), so existing installs must delete the two globs from `~/.claude/settings.json` by hand (a `scope_check` protected path; the user does this, not the agent).
3. **Promotion criterion.** ADR-0001 Gate 4 (one week of dryrun, zero real false positives) plus a human review of every `shell_guard` warn record in `hooks/logs/shell_guard.log`.
4. Record the decision here, including the sandbox finding.

## Boundary

`shell_guard` is a lexical best-effort check, not containment. It does not see values computed at run time (variables, string assembly, `python -c "shutil.rmtree(...)"`, scripts on disk), and it fails open on timeout or crash in interactive sessions. Bash/PowerShell writes to protected paths remain outside `scope_check`. On native Windows, permission rules plus these hooks are the only shell protection; real containment requires running Claude Code under WSL2 with the sandbox enabled.

Read deny rules for key material use the filesystem-wide `//**/` form. Per the permissions docs a bare `**/` rule is anchored at the session cwd and does not cover `~/.ssh`.

## Consequences

- During dryrun no destructive shell command is blocked (the two globs are gone); every finding is only warned and logged until promotion to enforce.
- `secret_scan` (enforce) now blocks key-material file paths for Edit/Write/NotebookEdit/apply_patch (`.ssh/`, `id_*`, `.pem/.key/.p12/.pfx/.p8/.keystore/.jks/.mobileprovision`, `.netrc`, `.pgpass`, `.aws/credentials`), and in shell commands only when a reader/copy verb (`Get-Content`, `cat`, `type`, `cp`, `base64`, …) takes such a path or a `.env*` file. Signing and packaging tools that are handed a key path (`signtool /f`, `keytool -keystore`, `-mobileprovision=`) are allowed on purpose. Search tools (`grep`, `rg`, `sed`, `awk`, `findstr`, `Select-String`) are excluded because their first argument is a pattern (`grep -rn id_rsa docs` would block), so reading a key through them is a known gap. Known false-positive candidate for Read/Write: UE ships `Engine/Content/Certificates/ThirdParty/cacert.pem` (public CA bundle).
- `Secrets.ini` and `service-account.json` are not detected: the names are too generic to block on, and key bodies are caught by `content_patterns` on write.
- The Codex target registers the same handler in `hooks.json` (portable; no launcher).

## Results (2026-10-15)

Before = HEAD `7c6f2f1` hooks + deny globs (globs approximated with `fnmatch`; bare `**/` Read rules assumed cwd `C:/proj`). After = this change.

| Set | Category | Before | After |
|---|---|---|---|
| tuning | destructive (block) | 4/20 | 20/20 |
| tuning | git bypass (block) | 0/7 | 7/7 |
| tuning | sensitive paths (block) | 1/8 | 8/8 |
| tuning | sensitive command args (block) | 1/4 | 4/4 |
| tuning | benign commands / reads (allow) | 13/13, 5/5 | 13/13, 5/5 |
| held-out | dangerous commands (block) | 1/13 | 13/13 |
| held-out | dangerous paths (block) | 0/5 | 3/5 (misses: `Secrets.ini`, `service-account.json`, by design) |
| held-out | benign (allow) | 8/8 | 8/8 |

The held-out set was run once after the rules were final (16/18, 0 false positives). It was visible to the rule author from the start, and several items resemble ECC cases ported into tuning (Start-Process cmd, pipeline recurse, Clear-Content), so it is not a blind set. Independent review then found false positives in the first `secret_scan` key-path regex (applied to whole commands) and several lexer gaps. Those fixes came from review inputs, now in the tuning file. The held-out result was unchanged after the fixes. Re-review: PASS with three minor items (more reader verbs, `timeout` options, nested-shell syntax). The last two were fixed; for the first, only `Format-Hex` and `certutil` were added, and search tools remain a documented gap.

Latency on this PC: `classify` median 22 µs, p99 71 µs in process; a 48 KB command 30 ms. The handler process (`py -3`) median 117 ms, through `cmd /c` median 136 ms (max of 40: 151 ms).

Replay of 2,913 unique historical Bash/PowerShell calls from local transcripts:
- `shell_guard` flags 45 (1.6%): `remove.recurse` 39, `find.delete` 8, `remove.wildcard` 5. The sampled ones are real recursive deletes, mostly scratchpad/temp cleanup. In enforce these would block, which is an input for the promotion review.
- The extended `secret_scan` newly blocks 7, all reads of real `.env` files.
