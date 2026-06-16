# dinner-harness

Single source of truth for a custom Claude Code (and, later, Codex) harness.

Hand-edit the canonical tree in this repo; **never hand-edit `~/.claude` directly** — it
is a generated output. Regenerate a target with the installer.

## Layout

- `content/` — tool-neutral harness content (instructions, rules, skills, agents, roles,
  templates, ecc-reference, docs). A codex adapter will transform this (Cycle 2).
- `assets/claude/` — claude-native raw (Python hooks, launchers, settings template,
  hand-written docs). Copied verbatim; the codex adapter ignores it.
- `assets/codex/` — codex-native assets (Cycle 2 placeholder).
- `adapters/` — per-target renderers (`claude.py`; `codex.py` in Cycle 2).
- `harness.toml` — manifest: targets, template vars, copy/template/skip/exclude rules.
- `install.py` — CLI entry: `install --target claude|codex [--dest PATH] [--dry-run]`.

## Install (claude target)

```
py -3 install.py --target claude --dest C:/Users/<you>/.claude
```

Defaults to `~/.claude` when `--dest` is omitted. Use `--dry-run` to preview the plan
without writing. `settings.json` is generated from `settings.json.template` by
substituting `<USERNAME>`; live `HANDOFF.md` / `RESULT.md` are never clobbered.

## Targets

- **claude** — implemented (Cycle 1): verbatim copy + `<USERNAME>` templating.
- **codex** — Cycle 2.
