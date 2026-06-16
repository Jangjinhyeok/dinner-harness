# dinner-harness

[한국어](README.md) | **English**

Single source of truth for a custom Claude Code **and** Codex harness.

Hand-edit the canonical tree in this repo; **never hand-edit `~/.claude` or `~/.codex`
directly** — they are generated outputs. Regenerate a target with the installer.

## Layout

- `content/` — tool-neutral harness content (instructions, rules, skills, agents, roles,
  templates, ecc-reference, docs). The codex adapter transforms this; the claude adapter
  copies it verbatim.
- `assets/claude/` — claude-native raw (Python hooks, launchers, settings template,
  hand-written docs). Copied verbatim; the codex adapter ignores it.
- `assets/codex/` — codex-native raw (curated `AGENTS.md`).
- `adapters/` — per-target renderers (`claude.py`, `codex.py`).
- `harness.toml` — manifest: targets, template vars, copy / template(merge) / skip / exclude.
- `install.py` — CLI entry: `install --target claude|codex [--dest PATH] [--dry-run] [--allow-live]`.

## Install

```
py -3 install.py --target claude --dest C:/Users/<you>/.claude
py -3 install.py --target codex  --dest C:/Users/<you>/.codex
```

Defaults to `~/.<target>` when `--dest` is omitted; writing to the live dir requires
`--allow-live`. Use `--dry-run` to preview the plan without writing.

- **claude** — verbatim copy of the inclusion set (88 files); `settings.json` is generated
  from `settings.json.template` (substitute `<USERNAME>`, strip `_template`) and **merged**
  with the existing file so machine/runtime keys (e.g. `skipWorkflowUsageWarning`) survive.
  Live `HANDOFF.md` / `RESULT.md` are never clobbered (skip-if-exists).
- **codex** — transforms the portable subset to Codex-native paths: curated `AGENTS.md`,
  17 portable skills under `skills/`, reference dirs (`ecc-reference/`, `docs/`, `templates/`).
  Claude-machinery (subagent routing, hooks, Two-CLI roles, 7 routing skills) is currently
  **dropped** by the codex adapter — newer Codex does support hooks and custom agents, but porting
  is deferred due to orchestration / session-pair semantic limits (a design decision, not an
  architectural impossibility). See `CODEX-RECON.md` and `CODEX-COVERAGE.md`.

## Targets

- **claude** — implemented & live: repo is the source of truth for `~/.claude`. The inclusion
  set round-trips byte-identical (proven diff-0).
- **codex** — implemented & live: `~/.codex` deployed non-destructively (runtime preserved).

See `CODEX-RECON.md` for the codex feasibility analysis (build vs adopt) and
`CODEX-COVERAGE.md` for the per-content native/degraded/dropped accounting.
