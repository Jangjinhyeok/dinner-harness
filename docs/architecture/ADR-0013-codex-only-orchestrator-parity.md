# ADR-0013: Codex-only pairing gets orchestrator parity + a symmetric Architect-vendor switch

- **Status:** Accepted for canonical source; live installation remains a separate human end-sign-off gate
- **Date:** 2026-08-29
- **Deciders:** user + Architect session

## Context

Commit `3bb1538` gave the harness an explicit **Builder vendor switch**: CLAUDE.md,
ROLE_ARCHITECT.md, `rules/_mode/architect.md`, and `delegate/SKILL.md` all spell
`--builder codex` in their dispatch command, documented as the single flag to flip to
`--builder claude` when the user moves to Claude Max and no longer wants Codex in the
loop. That switch only covers **Claude-only** (Claude plays both Architect and Builder).

The mirror scenario — **Codex-only** (no Claude Code installed at all, an interactive
Codex CLI session is the sole driver) — has no equivalent switch, and turns out to be
blocked by more than a missing doc line. `harness.toml`'s `[targets.claude]` copies
`orchestrate.py` and `orchestrator/` into the live install; `[targets.codex]` does not.
A Codex-only user therefore has no `orchestrate.py` to invoke at all, even though
`assets/codex/AGENTS.md` §8 already describes the single-pane auto-dispatch workflow as
if it were available, and even carries a stale pre-fix dispatch command that predates
the `--builder codex` explicit-flag convention CLAUDE.md's docs now use.

The two switches are not symmetric because the underlying pairing isn't symmetric:
Claude-only only needs to flip **which vendor plays Builder** (Architect already
defaults to Claude — the interactive CLI does not change). Codex-only flips **which
vendor plays Architect** (the interactive CLI itself becomes Codex) while Builder stays
`codex` — already the default value of `orchestrate.py build --builder`, so nothing
there needs to change. What Codex-only actually needs is (a) `orchestrate.py` to exist
under `~/.codex`, and (b) AGENTS.md's dispatch prose to carry the same exact,
copy-pasteable command shape CLAUDE.md's docs already carry.

## Decision

Give the `codex` install target the same `orchestrate.py`/`orchestrator/` copy entries
the `claude` target already has (the orchestrator package is vendor-neutral stdlib —
`ClaudeBackend` and `CodexBackend` are already symmetric in `orchestrator/vendors.py`,
so no orchestrator code changes are needed), and re-curate `assets/codex/AGENTS.md` §8
to the same exact dispatch-command fidelity as the Claude-side docs, plus a symmetric
**Architect vendor switch** note explaining that Codex-only needs no `--builder` flag
change at all — only the interactive driver changes.

## Implementation Guidelines

- `harness.toml` `[targets.codex]` `copy`: add `["orchestrate.py", "orchestrate.py"]`
  and `["orchestrator", "orchestrator"]`, mirroring the `[targets.claude]` entries
  verbatim. The target's existing `exclude_dir_names` (`tests`, `__pycache__`, ...)
  already applies to directory copies, so `orchestrator/tests/` is excluded the same
  way it is for the claude target — no new exclude rule needed.
- `assets/codex/AGENTS.md` §8: replace the loose `orchestrate.py build --repo
  <absolute-repo-path>` line with the exact shape used in ROLE_ARCHITECT.md /
  `rules/_mode/architect.md`, using `<CODEX_HOME>` as the doc-prose placeholder
  (resolved by the reading session at dispatch time, the same convention `<CLAUDE_HOME>`
  already uses in prose — no install-time templating is needed for this placeholder).
  Add the "Architect vendor 스위치" paragraph immediately after the existing "Codex가
  기본 Builder다" sentence.
- `assets/codex/README.md`: one line noting `orchestrate.py`/`orchestrator/` are now
  part of the copied set (currently the file only mentions `AGENTS.md`).
- `CODEX-COVERAGE.md`: extend the D1/D6 row area (or add a short dated addendum, do not
  renumber D1–D8) to record that `orchestrate.py`/`orchestrator/` are now copied into
  `~/.codex`, not solely a `~/.claude` artifact referenced from AGENTS.md prose.
- `content/instructions/CLAUDE.md` §2: one cross-reference sentence near the existing
  "Builder vendor 스위치" paragraph, pointing to AGENTS.md's new "Architect vendor
  스위치" note, so a reader on the Claude side can discover the Codex-only path too.
  Any edit to this file's blessed content requires re-running `py -3 check.py --update`
  to re-bless `curation.toml`'s hash (same as `3bb1538`).
- `README.md` / `README.en.md`: a new subsection under "일상 사용법" / "Usage"
  documenting **both** single-vendor switches side by side (Claude-only via
  `--builder claude`; Codex-only via installing `--target codex`, which now ships its
  own `orchestrate.py`, plus declaring `architect 모드`/`builder 모드` inside an
  interactive Codex session since Codex has no path-glob auto-inject).

## Consequences

- **Positive:** a Codex-only user (no Claude Code installed) can now run the same
  single-pane auto-dispatch workflow entirely inside `~/.codex`, with a documented,
  copy-pasteable dispatch command instead of a stale/incomplete one.
- **Positive:** the two switches (Builder vendor, Architect vendor) are each one
  sentence pointing at the other, so neither doc silently goes stale when the other is
  updated next.
- **Negative / trade-offs:** `orchestrator/` now ships duplicated into two install
  targets (`~/.claude/orchestrator` and `~/.codex/orchestrator`); a future orchestrator
  bugfix must be re-installed to both live targets via `refresh.py --apply` to stay in
  sync — `refresh.py` already re-validates and re-installs both targets from the one
  canonical source, so this is existing tooling, not new maintenance surface.
- **Follow-ups:** `orchestrator/README.md` / `README.ko.md`'s advanced/manual
  `$claudeHome`-flavored examples are out of scope for this ADR (they predate and are
  independent of the `<CLAUDE_HOME>`/`<CODEX_HOME>` prose convention used in the
  canonical role/mode docs) — a future pass could add a `$codexHome` example there if
  needed.

## Alternatives considered

- **Document "run `orchestrate.py` from the dinner-harness source checkout" instead of
  copying it into `~/.codex`:** rejected — breaks the existing "each target is a
  portable, self-sufficient rendered tree" design the `claude` target already
  guarantees, and would require the user to keep the source repo around forever even
  after installing, unlike every other capability.
- **Give Codex-only its own `--builder`-style flag instead of "no flag change
  needed":** rejected — `orchestrate.py build --builder` already defaults to `codex`;
  inventing a new flag for a case that requires zero code change would be needless
  surface area.
