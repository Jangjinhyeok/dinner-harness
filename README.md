# dinner-harness

**한국어** | [English](README.en.md)

커스텀 Claude Code **및** Codex 하네스의 single source of truth.

이 repo의 canonical 트리를 손-편집한다. **`~/.claude`·`~/.codex`를 직접 편집하지 말 것** — 둘 다 생성된 출력이다. 타깃은 installer로 재생성한다.

## Layout

- `content/` — tool-neutral 하네스 콘텐츠 (instructions, rules, skills, agents, roles,
  templates, ecc-reference, docs). codex adapter는 이를 transform하고, claude adapter는
  verbatim copy한다.
- `assets/claude/` — claude-native raw (Python hooks, launchers, settings template,
  손-작성 문서). verbatim copy되며 codex adapter는 무시한다.
- `assets/codex/` — codex-native raw (curated `AGENTS.md`).
- `adapters/` — 타깃별 renderer (`claude.py`, `codex.py`).
- `harness.toml` — manifest: targets, template 변수, copy / template(merge) / skip / exclude.
- `install.py` — CLI entry: `install --target claude|codex [--dest PATH] [--dry-run] [--allow-live]`.

## Install

```
py -3 install.py --target claude --dest C:/Users/<you>/.claude
py -3 install.py --target codex  --dest C:/Users/<you>/.codex
```

`--dest` 생략 시 `~/.<target>`이 기본값이며, 라이브 디렉터리에 쓰려면 `--allow-live`가 필요하다.
`--dry-run`으로 쓰기 없이 plan을 미리 본다.

- **claude** — inclusion set(88 files)의 verbatim copy. `settings.json`은
  `settings.json.template`에서 생성(`<USERNAME>` 치환, `_template` strip)되어 기존 파일과
  **merge**되므로 머신/runtime 키(예: `skipWorkflowUsageWarning`)가 보존된다.
  라이브 `HANDOFF.md` / `RESULT.md`는 절대 덮어쓰지 않는다(skip-if-exists).
- **codex** — portable subset을 Codex-native 경로로 transform: curated `AGENTS.md`,
  `skills/` 아래 17 portable skills, reference 디렉터리(`ecc-reference/`, `docs/`, `templates/`).
  Claude-machinery(subagent routing, hooks, Two-CLI roles, 7 routing skills)는 현재 codex adapter가
  **드롭**한다 — Codex 신버전도 hooks·custom agents를 지원하나 orchestration·세션페어 시맨틱 한계로
  포팅 보류다(아키텍처 불가가 아닌 설계 결정). 상세 = `CODEX-RECON.md`·`CODEX-COVERAGE.md`.

## Targets

- **claude** — implemented & live: repo가 `~/.claude`의 source of truth다. inclusion set이
  byte-identical로 round-trip된다(diff-0 증명).
- **codex** — implemented & live: `~/.codex`에 비파괴 배포됨(runtime 보존).

codex feasibility 분석(build vs adopt)은 `CODEX-RECON.md`, 콘텐츠별 native/degraded/dropped
회계는 `CODEX-COVERAGE.md` 참조.
