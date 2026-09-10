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

Run useful targeted checks followed by required regressions. Preserve the process exit code,
timeout and error status; output head/tail must not hide failure. Separate actual command
execution from model claims and mock tests from live CLI/engine validation. Mark unavailable
environment checks not_run. Repeat only for relevant changes or unresolved failures.

Review the task delta against the baseline, not `HEAD~1`; include staged, unstaged and new files.
Preserve unrelated user edits. Check scope, conventions, compatibility and side effects.
Use the existing secret scanner with redacted paths/rule IDs, never matched secret values;
do not read credentials or expose them with broad content searches.

Report PASS/FAIL/not_run with evidence and original failures. Distinguish self-review and an
independent reviewer. Verification grants no commit/push/deploy or HIGH acceptance authority.
No fixed edit count, function count or timer mandates another full-suite run.
