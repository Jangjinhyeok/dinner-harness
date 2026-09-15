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

- Risk has two levels: LOW/HIGH; Compute has LOW/NORMAL/HIGH. MEDIUM is not a Risk level.
  For nontrivial work, including planning, read `rules/autonomy-policy.md` from the active
  harness install root (reuse an unchanged copy already read in this session). This applies
  to single-session Codex as well as optional Two-CLI work.
  HIGH includes replication/RPC/net serialization, save formats, live config, migration/schema,
  security, public API/ABI, build/packaging, large blast radius or irreversibility; ambiguity is HIGH.
  LOW is scoped, reversible local work.
- Start with `Risk / rationale / verification / acceptance conditions`; update after new findings.
  Report planning, implementation, actual verification, independent review and human acceptance
  separately, including unmet conditions. Planning-only work leaves implementation/runtime checks
  not_run; a design review does not replace implementation review. Do not force questions on trivial work.
- REQUEST CHANGES/FAIL fixes are not a re-review PASS. Preserve the prior verdict and pending
  re-review until an independent reviewer checks the changed artifact and evidence.
- Prompt instructions do not enforce semantic risk classification. Native hooks cover supported
  tool events; controller checks inspect post-turn deltas. Neither proves independent review or
  human acceptance, and inline work does not automatically receive the controller checks.
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
