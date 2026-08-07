# assets/codex

Codex-native raw: curated `AGENTS.md` (installs to `~/.codex/AGENTS.md`). The codex
adapter (`../../adapters/codex.py`) consumes this. Per-content native/degraded/dropped
accounting is in `../../CODEX-COVERAGE.md`; see also `../../harness.toml` `[targets.codex]`.

In the default paired workflow, an ordinary Claude session dispatches this Codex
target as the Builder; `claude-direct.cmd` is the only Claude direct-edit escape.
