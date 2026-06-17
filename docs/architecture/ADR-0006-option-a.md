# ADR-0006: dinner-harness — Option A (repo = single source-of-truth, install → target)

> Architecture Decision Record (dinner-harness repo-internal — **not** installed to any
> target). Consolidates the engine decision scattered across HANDOFF cycles, the adapters,
> `CODEX-RECON.md`, and `CODEX-COVERAGE.md` into one self-contained record.

- **Status:** Accepted (C1~C4 live — repo is source-of-truth for `~/.claude` and `~/.codex`)
- **Date:** 2026-06-16
- **Deciders:** user + Architect session

## Context

기존 `~/.claude` 하네스(CLAUDE.md·skills·agents·hooks·rules·roles)는 Claude Code에 lock-in돼 있었고, 백업은 dinner-claude repo + GitHub 웹UI 수동 동기화였다. 문제: ① Claude 외 도구(Codex 등) 병행 시 동일 메타원칙·skill을 재사용할 길이 없음, ② 손-편집 대상(`~/.claude`)과 백업(repo)이 갈려 drift 발생. tool-neutral 콘텐츠와 tool-native raw를 분리해 **단일 source에서 여러 타깃을 생성**할 구조가 필요했다.

## Decision

**Option A 채택**: 독립 repo `dinner-harness`가 **단일 source-of-truth**다. 손-편집은 repo의 canonical 트리에서만, `install --target claude|codex [--allow-live]`로 `~/.claude`·`~/.codex`를 **생성**한다(타깃 = generated output, hand-edit 금지). 타깃별 손-편집 + 양방향 동기화(topology-B) 대신 **source → generate 단방향**(purist)을 의도적으로 채택.

## Implementation Guidelines

- **canonical 레이아웃**: `content/`(tool-neutral: instructions·rules·skills·agents·roles·templates·ecc-reference·docs) + `assets/claude/`(claude-native raw: hooks·settings template·hand-written docs) + `assets/codex/`(codex-native: curated `AGENTS.md`) + `adapters/`(`claude.py`·`codex.py`) + `harness.toml`(manifest) + `install.py`(CLI entry).
- **비대칭 adapter**:
  - **claude = near-identity copy** (stdlib, zero external dep). inclusion 88파일 byte-exact copy. `settings.json`은 template `<USERNAME>` 치환 + `_template` strip + **기존과 merge**(machine/runtime 키 `skipWorkflowUsageWarning` 보존). 라이브 `HANDOFF.md`/`RESULT.md`는 skip-if-exists(작업본 비클로버). **성패 기준 = scratch 설치 ↔ `~/.claude` 무손실 DIFF-0**(C2에서 88파일 byte-identical 증명).
  - **codex = transform + degrade** (stdlib). portable subset만 Codex-native로: instructions → curated `AGENTS.md`(§2 Two-CLI 등 strip), skills 17(Claude-machinery 7 drop), reference(`ecc-reference`·`docs`·`templates`) copy. Claude-machinery(agents·hooks·agent-routing·roles·`_mode`)는 drop + log(`CODEX-COVERAGE.md`). 검증 = **coverage 기준**(diff-0 부적용 — transform이라).
- **byte-fidelity**: `.gitattributes` `* text=auto eol=lf`(+ `README.md eol=crlf`) — fresh checkout에서도 LF 보존해 DIFF-0 내구성 확보.
- **안전**: 라이브 write는 `install.py --allow-live` 가드 뒤. 라이브 배포는 비파괴(copy-only, prune 없음) + 백업 + 명시 승인 게이트(C3/C4 패턴).

## Consequences

- **Positive**: 단일 source에서 claude+codex 생성. claude DIFF-0(무손실) 증명. 손-편집 1곳(repo) → drift 제거. tool-neutral 콘텐츠 재사용. `harness-review` skill도 repo-aware(리뷰 대상 = `content/`·`assets/`).
- **Negative / trade-offs**: 타깃은 generated라 직접 편집 시 다음 install에 덮임(워크플로 전환 비용). codex 일부는 hand-maintained curated(`assets/codex/AGENTS.md`) → CLAUDE.md 변경 시 재-curate 필요(drift 위험). install copy-only(prune 없음) — 파일 삭제는 "재작성으로 덮기"로 전파.
- **Follow-ups**: codex 실 포팅(adapter v2, Codex ≥0.140 선결 — `CODEX-RECON.md` Porting Plan) · `assets/codex/AGENTS.md` drift-check 자동화 · 옛 `~/.claude/.git`(dinner-claude) 정리 · capability 카탈로그 자동생성.

## Build-vs-adopt

- **rulesync 기각** (`CODEX-RECON.md`): codexcli 타깃에서 skills/subagents를 *simulate*해 비-native 경로(`.agents/skills/`·`.codex/agents/`)로 출력 — 라이브 `~/.codex/skills/`와 불일치(native보다 lag). + Node/TS dep + 극심한 churn(249 releases, 타깃 주간 retire). 자작 stdlib adapter가 fidelity·툴체인 일관성·churn 절연 모두 우위.
- **slides-grab 등 기존 도구**: 하네스 콘텐츠 변환과 무관(범위 밖).

## Codex 재-recon status

Cycle 1 recon은 Codex 0.111.0 + rulesync 기준 "Codex가 hooks/subagent 아키텍처적으로 불가"로 판정했으나, 후속 0.140 재조사로 **version-stale 판명** — Codex가 hooks(~v0.117)·subagents(orchestration: spawn→wait→synthesise, `max_depth=1`, prompt-driven)를 추가했다. 따라서 codex 드롭은 **불가능이 아니라 시맨틱 한계에 의한 설계 결정**이며 **reversible**(hooks·hub-leaf agents 포팅 가능, depth-2 다중hop·세션페어만 잔존). 실행 = `CODEX-RECON.md` "Porting Plan"(adapter v2). **교훈: 외부 도구 capability는 현행 버전으로 재확인(버전 pin) + research-first — "도구가 못 한다"는 전제는 버전과 함께 stale해진다.**

## Status

**Accepted** — C1(claude DIFF-0 증명) → C2(codex BUILD scratch) → C3(codex 라이브 `~/.codex` 배포) → C4(claude go-live `~/.claude`). repo = `~/.claude`·`~/.codex` 양 타깃 single source-of-truth, live 운영 중.

## Alternatives considered

- **Option B (타깃별 손-편집 + 양방향 동기화)** — 기각: drift 원천이 그대로 남고 단일 source 이점 상실.
- **rulesync / ruler adopt** — 기각: 위 Build-vs-adopt(simulate 비-native 경로 · 외부 dep churn).
- **옛 dinner-claude 백업 모델(GitHub 웹UI 수동 업로드)** — 기각: 백업 ≠ source, drift·수동 마찰. C4 go-live로 폐기됨.
