# assets/codex

Codex-native raw: curated `AGENTS.md` (installs to `~/.codex/AGENTS.md`). The codex
adapter (`../../adapters/codex.py`) consumes this. Per-content native/degraded/dropped
accounting is in `../../CODEX-COVERAGE.md`; see also `../../harness.toml` `[targets.codex]`.

`orchestrate.py`/`orchestrator/`도 이 target에 복사된다(ADR-0013) — Codex 단독으로도
single-pane auto-dispatch를 자체 실행할 수 있게 하기 위함이다.

In the default paired workflow, an ordinary Claude session dispatches this Codex
target as the Builder; `claude-direct.cmd` is the only Claude direct-edit escape.
