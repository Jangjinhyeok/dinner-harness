# dinner-harness

[한국어](README.md) | **English**

Source of truth for a Codex-first personal harness. Main Astra owns requirements, decomposition,
design, integration and final responsibility. Delegate useful bounded implementation to named native
roles; do small work directly when context-transfer/review overhead is greater. Choose by uncertainty,
impact, verifiability and dependencies, not file count or a delegation quota. General independent review
uses `code-reviewer`; naming a `default` task "review" does not select the reviewer profile.
See [agent routing](content/rules/agent-routing.md) for route and handoff contracts.
Existing hybrid and claude_only presets remain optional
compatibility paths.

## Start with Codex

Python, Git and Codex CLI are required; a Codex-only install needs no Claude CLI or Claude home.
Edit repository source rather than generated homes. Windows examples (use your Python executable
instead of py -3 on other platforms):

```text
py -3 check.py --target codex --no-install
py -3 install.py --target codex --dest "C:/temp/dinner-harness-codex"
py -3 refresh.py --target codex
```

Inspect the temporary output before a separately authorized live install:

```text
py -3 install.py --target codex --allow-live
py -3 check.py --target codex
codex -m gpt-6-astra -c model_reasoning_effort="medium"
```

Respect custom CODEX_HOME and user-owned config/hooks/skills; do not replace the entire config.toml.
Use --target claude or --target all only when intended. App users select the interactive model in
the supported model picker. Routing updates do not change an already open session.

## Workflow and policy

Request → necessary exploration/short plan → main-session implementation → project verification →
useful independent review → report. Ordinary work needs no HANDOFF/RESULT/CHALLENGE or Builder mode.
Do not delegate based on file count or downgrade an Astra task solely because of risk.
Parallel writers require explicit ownership, isolation and parent integration; avoid concurrent
implementation in the same tree.

HIGH changes retain independent review and human acceptance. Existing local implementation
authority does not grant commit/push/deploy permission. Preserve the user's branch and baseline
dirty tree. Distinguish self-review, actual deterministic execution and independent review;
unperformed review is not_run. Add specialists only for distinct unresolved risks.

## Models

[content/routing.toml](content/routing.toml) is the profile SSOT; codex_only is the default.
The configuration selected on 2026-09-23 is a usage policy, not a benchmark-proven optimum.

| Role | Model / effort | Meaning |
|---|---|---|
| Main / architect | GPT-6 Astra / medium | Interactive recommendation, selected separately |
| Small clear delegation | GPT-6 Luna / medium | Selected headless LOW |
| General delegation | GPT-6 Sol / medium | NORMAL/native implementation |
| Complex/HIGH implementation | GPT-6 Astra / high | HIGH compute floor |
| Important independent review | GPT-6 Sol / high | Fresh-context reviewer |
| HIGH design challenge | GPT-6 Astra / high | Separate read-only invocation |

Native implementation specialists currently map to `builder_normal`; they do not automatically select
LOW/HIGH. Headless resolves the selected gates' risk/compute. These instructions are not an automatic scheduler.
Risk and compute differ. Static profile validity, CLI capability and actual account model access
are separate evidence; unknown access stays unknown. Never silently fallback across vendors or
billing methods. Pro does not imply included API usage or maximum reasoning for every call.

## Optional dispatch and safety

Use [headless challenge/build](content/rules/two-cli-reference.md) for substantial bounded delegation
or controller scope/secret and baseline/delta checks. Explicit
[Architect](content/roles/ROLE_ARCHITECT.md)/[Builder](content/roles/ROLE_BUILDER.md) contracts do not
restrict default inline Codex. run is legacy/experimental, not the default entrypoint.

JSONL events provide thread/error/usage observation; final schema JSON is the result contract.
Review RESULT plus actual delta. BUILT and Builder panel=PASS do not establish independent review
or acceptance. Recovery is read-only; no-op or output-format failures must not force new edits.
Partial edits after failure/timeout are inspected without blanket rollback.

Native hooks can deny supported tool calls but are not containment for all I/O.
Controller delta checks serve a different purpose; inline does not automatically have equivalent
scope enforcement. Keep strict-scope tasks on the required path.
See dated [coverage](CODEX-COVERAGE.md) and historical [recon](CODEX-RECON.md) evidence.

## Sources

[AGENTS](assets/codex/AGENTS.md) holds concise Codex defaults;
[rules](content/rules) and [roles](content/roles) hold on-demand contracts;
[skills](content/skills) provide portable procedures;
[agents](content/agents) and [specialist references](content/docs/specialists) preserve engine knowledge;
[templates](content/templates) provide self-contained project instructions;
[manifest](harness.toml) and [adapter](adapters/codex.py) generate selected targets.

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

### Skills (29)

- `adversarial-review`
- `arch-review`
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

### Hooks (6)

- `builder_guard`
- `learning_log`
- `route_nudge`
- `scope_check`
- `secret_scan`
- `suggest_compact`
