<!--
  Project-root agent instructions. The AGENTS.md standard is read from the
  PROJECT ROOT (and ancestor dirs) by cross-tool agents — Codex CLI, Gemini CLI,
  Cursor, and others. Keep this file at the repository root, NOT under docs/.

  Purpose: give NON-Claude agents the same baseline discipline Claude Code gets
  from CLAUDE.md, without duplicating it. Claude Code reads CLAUDE.md directly;
  other tools read this file. This template points to CLAUDE.md as the
  authoritative source and carries only the tool-neutral essentials inline,
  because other tools do not auto-load CLAUDE.md.

  Copy to:  <project-root>/AGENTS.md   then fill every <FILL IN>.
-->

# AGENTS.md

## Authoritative instructions

The full, authoritative conventions for this project live in:

- `./CLAUDE.md` — project-level domain knowledge (architecture, modules, conventions).
- `~/.claude/CLAUDE.md` — user-level meta-principles and workflow.

If you are an agent that does not auto-load those files, **read `./CLAUDE.md` now
before making changes.** This file carries only the tool-neutral baseline below;
on any conflict, CLAUDE.md wins.

## Project overview

<FILL IN — one paragraph: what this project is, engine/stack (e.g. UE5 C++ /
Unity C#), target platforms (mobile + PC), live-service or not.>

## Repository structure

<FILL IN — short map of the meaningful folders. Example:
  Source/   game modules
  Content/  assets (do not hand-edit binary assets)
  docs/     ADRs, engine-reference/<engine>/VERSION.md >

## Working principles (tool-neutral baseline)

Apply these on every change. Full rationale in `~/.claude/CLAUDE.md` §1.

1. **State assumptions, don't guess.** Ambiguous request → state the assumption or
   ask before coding.
2. **Minimum viable code.** Build only what was asked. No speculative flexibility,
   configurability, or error handling for impossible cases.
3. **Surgical changes.** Touch only files in scope. No "while I'm here" refactors —
   critical on live-service code.
4. **Research before writing.** For non-trivial work, search existing libraries and
   patterns (package registries, official docs, code search) before writing
   net-new code.
5. **Verifiable goals.** Convert the task into checks; state the verification
   method before multi-step work.

## Conventions

- **Code style:** <FILL IN — formatter/linter, e.g. clang-format, .editorconfig.>
- **Naming:** identifiers, comments, and commit messages in English.
- **Testing:** <FILL IN — command to run tests + pass criteria.>
- **Commits:** <FILL IN — message format / branch strategy. Commit only when asked.>

## Tool permissions

- **Allowed without asking:** read files, run tests/builds, search.
- **Confirm first:** writing/editing source, deleting files, dependency changes,
  anything outward-facing or hard to reverse.
- **Prohibited unless explicitly instructed:** force-push, history rewrite,
  secret/credential handling, mass automated edits across many files.

## Known constraints

<FILL IN — non-obvious env/build assumptions, frame/memory budgets, platform
limits, backward-compat requirements. Engine API claims must match
docs/engine-reference/<engine>/VERSION.md, which overrides training data.>

## Verification gates

Before reporting work complete:

- [ ] Builds / compiles.
- [ ] Tests pass (command above), or state which were skipped and why.
- [ ] Changes stay within requested scope (no unrelated file edits).
- [ ] Self-review done; report "issues: N" or "no issues".

## Escalation

When a decision falls outside the scope above — architecture choices, dependency
additions, anything destructive or live-service-affecting — stop and ask the
human (or the Architect session) rather than assuming authority.
