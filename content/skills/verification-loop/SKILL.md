---
name: verification-loop
description: Verify implementation with project-specific build, tests, safety and baseline-diff checks, including UE, Unity and Python workflows.
---

# Verification Loop

Record a pre-edit baseline including staged/unstaged/untracked state. Discover commands from
project instructions, CI and configuration. Use existing tooling; do not impose a universal
coverage threshold or install a generic stack.

- Unreal: identify target/platform/configuration and engine path. Run applicable build/automation
  tests; lifecycle, UI, assets and networking may need PIE, packaging or multiplayer scenarios.
- Unity: use the project's Editor version, build target and EditMode/PlayMode setup; validate
  runtime/asset/lifecycle effects with the corresponding project procedure.
- Python: use the configured interpreter and repository unittest/pytest command. Type/lint tools
  apply when configured or relevant.
- Other stacks: follow documented project build/test commands.

Before interactive Editor checks, state the final handoff state in the existing execution plan
(for example, PIE stopped with the requested map open, or Editor closed). Distinguish restarts
needed for verification from reopening for user handoff, and record the reason for each.
Preserve applicable fresh-process/save-reload, input/focus and exit checks. Follow the active
computer-use tool's action/observation contract; do not batch state-dependent inputs to cut calls.

Run useful targeted checks followed by required regressions. Preserve the process exit code,
timeout and error status; output head/tail must not hide failure. Separate actual command
execution from model claims and mock tests from live CLI/engine validation. Mark unavailable
environment checks not_run. Repeat only for relevant changes or unresolved failures.

## Evidence before PASS

Distinguish request delivery, process completion and target-operation success. An MCP `success`
flag or exit zero alone proves neither compilation nor requirement fulfillment. Confirm the
actual target, command, diagnostics and completed operation. For UE compile use compiler errors
and completion results; for Python inspect exceptions/tracebacks and a trustworthy completion
result; for builds verify the project's actual UBT/build command and result, not an unrelated
Editor command. Use the supported tool's diagnostics contract, not a universal text search for
"error" (fixtures, quoted history and unrelated logs are not current target failures).
Current relevant compiler errors, exceptions, failed checks or load ensures prevent PASS even
when the wrapper reports success. A known target failure is FAIL; a target never exercised is
not_run; incomplete or conflicting evidence stays unresolved, not PASS. Investigate the adapter
and the interpretation separately; do not infer an external MCP implementation bug without evidence.

Tie logs/images/reports to the tested artifact state with path, generation time and, when needed,
hash or revision. Mark supplied records separately from directly inspected evidence. A
revision alone does not identify uncommitted changes: record the relevant staged/unstaged/untracked
state too. Trace the actual caller or job/run to the changed path; an unused helper or an old run
cannot verify the current operation. Separate code changes, compile/build success, requirement
fulfillment, final artifact checks, deployment/publication and human acceptance in the existing report.
Check the final artifact when the requirement concerns its contents rather than just build success.
A created image or exit zero is not visual verification. Stale, blank or uninspected previews leave the
requested visual check not_run; if the actual target was observed violating a requirement, report
FAIL. After relevant code/asset edits, obtain applicable new evidence or retain the limitation.
Do not mandate a manifest tool or rerun unrelated checks for every small edit.

Verify the latest requested outcome as well as compilation. On feature removal, establish which
callers, bindings, widget hierarchy, references and serialized metadata must disappear; do not
restore obsolete placeholders solely to satisfy the old contract without a compatibility need.
For Blueprint structural/reflected-binding edits, follow the targeted save/reload checks in
[Blueprint guidance](../../docs/specialists/ue-blueprint.md); runtime absence remains not_run.

Review the task delta against the baseline, not `HEAD~1`; include staged, unstaged and new files.
Preserve unrelated user edits. Check scope, conventions, compatibility and side effects.
For generated/collected data, explain the input and generation rule, added/removed entries and
their relationship to the requested change. Check references and unexpected churn; generation
alone does not authorize a broad delta. Preserve baseline user edits instead of blanket rollback.
Use the existing secret scanner with redacted paths/rule IDs, never matched secret values;
do not read credentials or expose them with broad content searches.

Report PASS/FAIL/not_run with evidence and original failures. Distinguish self-review and an
independent reviewer. Verification grants no commit/push/deploy or HIGH acceptance authority.
No fixed edit count, function count or timer mandates another full-suite run.
Apply the unchanged session copy or original [autonomy policy](../../rules/autonomy-policy.md)
in single-session work too. Completion reports separate planning, implementation, actual checks,
independent review and HIGH human acceptance, retaining unmet conditions. Planning-only work
leaves implementation/runtime checks not_run. REQUEST CHANGES/FAIL fixes need independent
re-review before reporting PASS; an author's fix report is not review evidence.
Report local changes, commit and push separately with their actual outcomes and remote/ref when
attempted. A failed push after a successful commit leaves the commit intact and delivery incomplete.
Authentication failure is neither a code failure nor a user refusal; do not print credentials,
bypass permissions/hooks or retry without changed evidence. This reporting grants no delivery authority.
