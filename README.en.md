# dinner-harness

[한국어](README.md) | **English**

Source of truth for a Claude-first personal harness (ADR-0023). Main owns requirements, decomposition,
design, integration and final responsibility. Delegate useful bounded implementation to named native
roles; do small work directly when context-transfer/review overhead is greater. Choose by uncertainty,
impact, verifiability and dependencies, not file count or a delegation quota. General independent review
uses `code-reviewer`; naming a `default` task "review" does not select the reviewer profile.
See [agent routing](content/rules/agent-routing.md) for route and handoff contracts.
The Codex target and the codex_only/hybrid presets remain optional compatibility paths.

## Start with Claude

Python, Git and the Claude Code CLI are required; no Codex CLI or Codex home is needed.
Edit repository source rather than generated homes. Windows examples (use your Python executable
instead of py -3 on other platforms):

```text
py -3 check.py --target claude --no-install
py -3 install.py --target claude --dest "C:/temp/dinner-harness-claude"
py -3 refresh.py --target claude
```

Inspect the temporary output (no `builder_guard` in `settings.json`, rendered `CLAUDE.md`) before a
separately authorized live install:

```text
py -3 install.py --target claude --allow-live
py -3 check.py --target claude
claude --model claude-opus-5-5 --effort medium
```

The Claude install is 1-CLI: the orchestrator, `routing.toml`, roles, `rules/_mode`, HANDOFF/RESULT
templates, two-cli/routing references and the `delegate` skill are not installed (the orchestrator,
routing, roles and references stay for the Codex target; `delegate`, `_mode` and the HANDOFF/RESULT
templates are source-only). The Claude adapter has no retire logic, so those files from older installs,
plus `claude-direct.cmd`, `dh*.cmd`, `watch-builder.ps1`, the `builder_guard` files and the settings
`orchestrate.py` allow rule, may remain in `~/.claude`. `check.py --target claude` reports the leftover
files but never deletes them. Remove leftover `rules/` files by hand: Claude Code auto-loads them.
check.py does not report the settings allow rule; remove it from `settings.json` by hand.
Use --target codex or --target all only when intended. A plain `claude` session is the direct-edit
session. App users select the interactive model in the supported model picker. Routing updates do
not change an already open session.

## Workflow and policy

Request → necessary exploration/short plan → main-session implementation → project verification →
useful independent review → report. Ordinary work needs no HANDOFF/RESULT/CHALLENGE or Builder mode.
Do not delegate based on file count or downgrade a task solely because of risk.
Parallel writers require explicit ownership, isolation and parent integration; avoid concurrent
implementation in the same tree.

HIGH changes retain independent review and human acceptance. Existing local implementation
authority does not grant commit/push/deploy permission. Preserve the user's branch and baseline
dirty tree. Distinguish self-review, actual deterministic execution and independent review;
unperformed review is not_run. Add specialists only for distinct unresolved risks.

## Models

[content/routing.toml](content/routing.toml) is the profile SSOT; claude_only is the default.
The basis is the VulcanBench Frontier v4 result recorded in
[ADR-0023](docs/architecture/ADR-0023-claude-only-default.md) (23 tasks, one attempt per cell,
implementation-only, review roles extrapolated); it is a usage policy, not a proven optimum.

| Role | Model / effort | Meaning |
|---|---|---|
| Main / architect | Claude Opus 5.5 / medium | Interactive recommendation, selected separately |
| Small clear delegation | Claude Opus 5.5 / low | Selected headless LOW |
| General delegation | Claude Opus 5.5 / medium | NORMAL/native implementation (agent frontmatter `model: opus`) |
| Complex/HIGH implementation | Claude Sonnet 5.5 / max | HIGH compute, higher cost and time accepted |
| Important independent review | Claude Opus 5.5 / medium | Fresh-context reviewer |
| HIGH design challenge | Claude Opus 5.5 / high | Separate read-only invocation |

Native implementation specialists currently map to `builder_normal`; they do not automatically select
LOW/HIGH. Headless resolves the selected gates' risk/compute. These instructions are not an automatic scheduler.
Risk and compute differ. Static profile validity, CLI capability and actual account model access
are separate evidence; unknown access stays unknown. Opus high-effort results partly measure an
Opus 4.8 fallback. Never silently fallback across vendors or billing methods. A subscription does
not imply included API usage. codex_only (GPT-6.1 Sol xhigh) and hybrid stay selectable.

## Optional dispatch and safety (Codex target only)

This path is not part of the Claude 1-CLI install; only the Codex target installs it. The headless and
challenge profiles above apply here only; Claude delegation uses native subagents (`model: opus`).
Use [headless challenge/build](content/rules/two-cli-reference.md) for substantial bounded delegation
or controller scope/secret and baseline/delta checks. Explicit
[Architect](content/roles/ROLE_ARCHITECT.md)/[Builder](content/roles/ROLE_BUILDER.md) contracts do not
restrict the default inline session. run is legacy/experimental, not the default entrypoint.

JSONL events provide thread/error/usage observation; final schema JSON is the result contract.
Review RESULT plus actual delta. BUILT and Builder panel=PASS do not establish independent review
or acceptance. Recovery is read-only; no-op or output-format failures must not force new edits.
Partial edits after failure/timeout are inspected without blanket rollback.

Native hooks can deny supported tool calls but are not containment for all I/O.
Controller delta checks serve a different purpose; inline does not automatically have equivalent
scope enforcement. Keep strict-scope tasks on the required path.
See dated [coverage](CODEX-COVERAGE.md) and historical [recon](CODEX-RECON.md) evidence.

## Sources

[CLAUDE.md](content/instructions/CLAUDE.md) and [AGENTS](assets/codex/AGENTS.md) hold concise Claude and Codex defaults;
[rules](content/rules) and [roles](content/roles) hold on-demand contracts;
[skills](content/skills) provide portable procedures;
[agents](content/agents) and [specialist references](content/docs/specialists) preserve engine knowledge;
[templates](content/templates) provide self-contained project instructions;
[manifest](harness.toml) and the [Claude](adapters/claude.py)/[Codex](adapters/codex.py) adapters generate selected targets.

Domain skills read relevant UE references without forcing delegation. Important review uses
concrete evidence rather than fixed judge counts. Learning logs are opt-in and redacted;
Codex installs neither learning-log collection nor edit-count compact reminders by default.
Prefer native compaction; experimental context management is optional.

Use actual UE/Unity/Python/project build and test procedures. No universal 80% coverage, fixed
timer, mandatory diagram or three-file briefing applies to every edit.
Legacy CLAUDE.md hash curation proves provenance, not Codex behavioral or generated-output validity.
Historical ADR/capability observations remain dated records.


## What's inside

Source catalog. The manifest and generated checks determine Codex installation coverage.

### Skills (30)

- `adversarial-review`
- `arch-review`
- `asset-authoring`
- `autonomous-loop`
- `bp`
- `changelog`
- `cli-update`
- `codebase-onboarding`
- `delegate`
- `eval-harness`
- `gas`
- `goal-driven-execution`
- `harness-review`
- `hotfix`
- `iterative-retrieval`
- `learnings-review`
- `perf-profile`
- `repl`
- `scope-check`
- `search-first`
- `simplicity-first`
- `strategic-compact`
- `surgical-changes`
- `tech-debt`
- `think-before-coding`
- `ue`
- `ue-umg-review`
- `umg`
- `verification-loop`
- `walkthrough`

### Agents (13)

- `architect`
- `code-reviewer`
- `cpp-build-resolver`
- `cpp-reviewer`
- `gameplay-programmer`
- `network-programmer`
- `performance-analyst`
- `planner`
- `tdd-guide`
- `tools-programmer`
- `ui-programmer`
- `unity-specialist`
- `unreal-specialist`

### Hooks (5)

- `learning_log`
- `route_nudge`
- `scope_check`
- `secret_scan`
- `suggest_compact`
