<!-- Copy to project-root AGENTS.md and replace project placeholders. Preserve any existing file. -->
# Project Instructions

This file is self-contained project policy for Codex and other agents that load AGENTS.md.
No vendor-specific global instruction file is required. If both CLI vendors are used,
CLAUDE.md may refer to an explicitly chosen shared project document without replacing this file.

## Project

<Describe the project, engine/version, language, platforms and live-service status.>

## Structure and constraints

<List meaningful module boundaries, entry points, ownership/lifetime invariants,
replication/save compatibility and frame/memory budgets. Avoid generated directories.>

## Build and verification

<Record exact project build/test commands and needed engine/editor target/configuration.
For Unreal note automation/PIE/multiplayer checks; for Unity note EditMode/PlayMode/build checks.
Mark unavailable runtime validation not_run. Do not impose a universal coverage threshold.>

## Working conventions

- Technical discussion: Korean with English technical terms. Identifiers/comments: English.
  Commit messages: type prefix plus Korean, unless a more specific project rule applies.
- Reuse repository patterns first; verify uncertain/version-dependent APIs against official sources.
- Infer routine details from repo conventions, state material assumptions, ask only when
  the missing choice changes scope, outcome or authority.
- Implement authorized local changes and relevant verification without per-file consent.
  Main Codex can design and implement in the same session. Ordinary tasks need no HANDOFF.
- Preserve current user-selected branch and existing staged/unstaged/untracked edits.
  No branch changes, commit, push, merge or deployment without the user's explicit authority.
- Keep changes scoped; review the task delta against its baseline. Report actual checks,
  self-review and independent review separately, with not_run when absent.
- HIGH changes require independent review and human result acceptance. Local implementation
  permission is separate from outward-facing or irreversible action authority.
- Respect actual sandbox/hooks/protected paths; never weaken them to complete a task.
  Do not read or print credential/token contents.

## References

<List only actual project docs, relevant ADRs and pinned engine reference paths.>
