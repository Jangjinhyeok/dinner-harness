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

- **claude** — inclusion set(87 files)의 verbatim copy. `settings.json`은
  `settings.json.template`에서 생성(`<USERNAME>` 치환, `_template` strip)되어 기존 파일과
  **merge**되므로 머신/runtime 키(예: `skipWorkflowUsageWarning`)가 보존된다.
  라이브 `HANDOFF.md` / `RESULT.md`는 절대 덮어쓰지 않는다(skip-if-exists).
- **codex** — portable subset을 Codex-native 경로로 transform: curated `AGENTS.md`,
  `skills/` 아래 17 portable skills, reference 디렉터리(`ecc-reference/`, `docs/`, `templates/`).
  Claude-machinery(subagent routing, hooks, `_mode` 조건부 inject, 7 Claude-machinery skills
  [routing 5 + harness 2])는 현재 codex adapter가 **드롭**하나, **Two-CLI 역할(roles)은 AGENTS.md §7로
  cross-vendor curate된다**(양방향 — 아래 "Two-CLI 협업" 참조). 드롭된 건 `_mode`의 file-glob 자동 inject
  (Codex 대응 기제 없음 → 모드 명시 선언으로 진입)와 hooks·subagent orchestration이며, 후자는 Codex
  신버전이 지원하나 adapter 포팅 보류다(아키텍처 불가가 아닌 설계 결정). 상세 = `CODEX-RECON.md`·`CODEX-COVERAGE.md`.

## Targets

- **claude** — implemented & live: repo가 `~/.claude`의 source of truth다. inclusion set이
  byte-identical로 round-trip된다(diff-0 증명).
- **codex** — implemented & live: `~/.codex`에 비파괴 배포됨(runtime 보존).

codex feasibility 분석(build vs adopt)은 `CODEX-RECON.md`, 콘텐츠별 native/degraded/dropped
회계는 `CODEX-COVERAGE.md` 참조.

## Two-CLI 협업 (cross-vendor)

큰 작업은 두 CLI 세션을 나눠 운용한다 — **Architect**(설계·검토)와 **Builder**(구현). 두 역할은
vendor-neutral하며 Codex·Claude 어느 쪽이든 어느 역할이든 맡는다(예: Codex=Architect / Claude=Builder,
또는 역방향). 통신은 프로젝트 루트의 `HANDOFF.md`(Architect→Builder)·`RESULT.md`(Builder→Architect)·
`INPUT.md`(선택) 파일 — 런타임 IPC/MCP 불필요한 vendor-neutral 버스다.

- **Claude**: `content/roles/ROLE_{ARCHITECT,BUILDER}.md` + `rules/_mode/`(통신 파일 paths 매칭 시 자동 inject).
- **Codex**: 동일 프로토콜을 `assets/codex/AGENTS.md` §7로 curate. Codex엔 paths 자동 inject가 없어 모드는
  **명시 선언**("architect/builder 모드")으로 진입한다.

파일 기반이라 Codex 0.111+에서 동작하며, Architect의 옵션 서브에이전트 위임만 0.140+를 쓴다. 상세 규약은
`content/instructions/CLAUDE.md` §2 참조.

## 하네스 구성 (capabilities)

이 하네스가 보유한 skills·agents·hooks. _frontmatter 파생 snapshot — skill/agent 변경 시 갱신 필요._ codex 타깃에서 어느 항목이 native/degraded/dropped인지는 `CODEX-COVERAGE.md` 참조.

### Skills (26)

**메타원칙 (5)**
- `simplicity-first` — 최소 코드만, 과설계·추측 기반 유연성 방지
- `surgical-changes` — 요청 범위 밖 수정·무관 리팩토링 차단 (라이브 서비스 핵심)
- `think-before-coding` — 코딩 전 가정 명시·옵션 제시·질문
- `goal-driven-execution` — 모호한 작업을 검증 가능한 목표로 변환
- `search-first` — 코드 작성 전 기존 구현·라이브러리 검색·채택

**컨텍스트·검증 (7)**
- `verification-loop` — 세션 변경 검증 시스템
- `eval-harness` — eval-driven development 평가 프레임워크
- `strategic-compact` — 논리적 구간에서 수동 context compaction 제안
- `iterative-retrieval` — 컨텍스트 점진 정제 (subagent context 문제)
- `scope-check` — 원 계획 대비 scope creep 감사·정량화
- `perf-profile` — 병목 분석·예산 대비 측정·최적화 우선순위
- `tech-debt` — 기술 부채 추적·분류·상환 스케줄

**워크플로 (5)**
- `changelog` — git 커밋에서 changelog 자동 생성 (내부 + 플레이어용)
- `hotfix` — 긴급 수정 워크플로 (심각도·롤백 플랜·감사 추적)
- `codebase-onboarding` — 낯선 코드베이스 분석·온보딩 가이드 (엔진 인식)
- `arch-review` — 아키텍처·품질 코드 리뷰 (SOLID·테스트 가능성·성능)
- `learnings-review` — `learning_log` 포착 반복 실패를 CLAUDE.md/메모리로 승격

**UE 라우팅 (6)**
- `ue` — 멀티 서브시스템 Unreal 작업을 `unreal-specialist` 허브로 라우팅
- `bp` — Blueprint 아키텍처를 `ue-blueprint-specialist`로 직접 라우팅
- `gas` — GAS를 `ue-gas-specialist`로 직접 라우팅
- `umg` — UMG/CommonUI를 `ue-umg-specialist`로 직접 라우팅
- `repl` — replication/netcode를 `ue-replication-specialist`로 직접 라우팅
- `ue-umg-review` — UMG 위젯 리뷰·설계 (UE5)

**자율 루프 (2)**
- `autonomous-loop` — risk-tier 자율 자기수정 루프 (사람은 시작·종단만, 중간은 agent)
- `adversarial-review` — default-to-reject 다중 judge 패널 (HIGH tier 필수)

**harness (1)**
- `harness-review` — dinner-harness repo 자체를 wiring·conformance 두 렌즈로 리뷰

### Agents (21)

**_core (6)**
- `architect` — 시스템 설계·확장성·기술 결정
- `code-reviewer` — 코드 품질·보안·유지보수성 리뷰
- `cpp-build-resolver` — C++ 빌드·CMake·링커·템플릿 에러 해결 (최소 변경)
- `cpp-reviewer` — C++ 메모리 안전·모던 idiom·동시성·성능 리뷰
- `planner` — 복잡 기능·리팩토링 계획
- `tdd-guide` — 테스트 우선 방법론 (80%+ 커버리지)

**_gamedev (5)**
- `gameplay-programmer` — 게임 메커닉·전투·플레이어 시스템 구현
- `network-programmer` — 멀티플레이어 netcode·lag 보상·매치메이킹
- `performance-analyst` — 성능 프로파일링·병목·최적화 전략
- `tools-programmer` — 에디터 확장·콘텐츠 도구·파이프라인 자동화
- `ui-programmer` — 메뉴·HUD·인벤토리·UI 위젯 구현

**_ue (5)**
- `unreal-specialist` — UE5 작업 허브 (GAS·BP·UMG·replication sub로 fan-out)
- `ue-blueprint-specialist` — Blueprint 아키텍처·BP/C++ 경계·최적화
- `ue-gas-specialist` — GAS: ability·effect·attribute·tag·prediction
- `ue-replication-specialist` — property replication·RPC·client prediction·relevancy
- `ue-umg-specialist` — UMG/CommonUI: widget hierarchy·data binding·input

**_unity (5)**
- `unity-specialist` — Unity 작업 허브 (DOTS·shader·addressables·UI sub로 fan-out)
- `unity-dots-specialist` — DOTS/ECS·Jobs·Burst
- `unity-shader-specialist` — Shader Graph·VFX Graph·render pipeline (URP/HDRP)
- `unity-addressables-specialist` — asset 로딩·번들·메모리·content catalog
- `unity-ui-specialist` — UI Toolkit·UGUI·data binding·런타임 UI 성능

### Hooks (5)

상세 발화 흐름·운영 모드는 `assets/claude/README.md` + `assets/claude/hooks/README.md` 참조.

- `secret_scan` (PreToolUse) — 입력에서 시크릿·민감 파일경로 regex 검출 (enforce, 차단형)
- `scope_check` (PreToolUse) — cycle 스코프 밖 수정 + hook 인프라 보호 (dryrun, always-block 즉시 차단)
- `suggest_compact` (PreToolUse) — 도구 호출 누적 시 `/compact` 제안 (advisory)
- `learning_log` (PostToolUse) — Bash 실패 신호 포착 → `learnings-review`로 승격 (advisory)
- `route_nudge` (UserPromptSubmit) — 프롬프트의 UE 도메인 신호 검출 → 위임 nudge 주입 (advisory)
