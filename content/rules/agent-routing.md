# Agent Routing (Engine Orchestration)

이 규칙은 항상 주입된다. 설치된 agent로 작업을 위임하는 진입 규칙이다. **여기 적힌 agent만 실제로 존재한다** — 다른 이름(`technical-director`, `lead-programmer`, `game-designer` 등)은 미설치이며, 그 판단이 필요하면 위임하지 말고 사용자에게 에스컬레이션한다.

## 언제 위임하지 않는가 (먼저 판정)

CLAUDE.md §2의 단일 세션 원칙을 따른다. 다음은 **메인 세션에서 직접** 처리하고 위임하지 않는다:
- 한두 줄 수정, 단일 함수 추적/디버깅
- 코드 질문, 탐색, 학습 목적
- 단일 파일 안에서 끝나는 작업

위임은 **엔진 특화 구현·아키텍처·최적화가 실질적 분량**일 때만 한다.

**Two-CLI Builder 모드 예외**: Builder 세션(`builder 모드`/HANDOFF.md 실행 중)에서는 specialist 재위임을 생략한다 — Architect가 이미 분해·설계한 spec을 실행하는 단계라 엔진 specialist 재호출이 구조적으로 잉여다. 엔진 라우팅이 가치를 갖는 지점은 **Architect의 설계 단계**(HANDOFF 작성 전 triage)이지 Builder의 실행 단계가 아니다. (근거: 2026-06-16 conformance 감사 — 실 UE5.6 작업의 ~89%가 메인 인라인 처리, hub-fan-out 0회. 위임이 실패한 게 아니라 Two-CLI가 그 lane을 이미 덮고 있었다. roster는 Architect 설계 단계용으로 유지하되 Builder 실행 중 강제 진입점으로 쓰지 않는다.)

## 엔진 판별

- `*.uproject` 또는 `Source/*/*.Build.cs` 존재 → **Unreal**
- `ProjectSettings/ProjectVersion.txt` 또는 `Assets/` + `Packages/manifest.json` → **Unity**
- 프로젝트 `CLAUDE.md`가 엔진을 명시하면 그쪽이 우선

## 라우팅 규칙

### Unreal 작업 → `unreal-specialist` (허브)
엔진 특화 작업은 하위 specialist를 **직접 부르지 말고** 허브를 통한다. 허브가 Task로 하위에 fan-out한다:
- `ue-gas-specialist` — GAS: ability, gameplay effect, attribute set, gameplay tag
- `ue-blueprint-specialist` — Blueprint 아키텍처, BP/C++ 경계, 그래프 표준
- `ue-replication-specialist` — property replication, RPC, prediction, relevancy
- `ue-umg-specialist` — UMG/CommonUI, widget hierarchy, data binding

### Unity 작업 → `unity-specialist` (허브)
- `unity-dots-specialist` — ECS, Jobs, Burst
- `unity-shader-specialist` — Shader Graph, VFX Graph, render pipeline
- `unity-addressables-specialist` — asset 로딩/번들/메모리
- `unity-ui-specialist` — UI Toolkit, UGUI, data binding

### 엔진 무관 도메인 작업 → `_gamedev` agent
- `gameplay-programmer` — 게임 메커닉/전투/플레이어 시스템 구현 (엔진 특화 부분은 엔진 허브에 재위임)
- `network-programmer` — netcode/replication 전략, matchmaking
- `ui-programmer` — UI 시스템/HUD/메뉴 (UMG 구현 디테일은 ue-umg-specialist에 재위임)
- `tools-programmer` — 에디터 확장, 콘텐츠 도구, 파이프라인 자동화
- `performance-analyst` — 프로파일링, 병목 분석, 최적화 전략

### 공통(엔진 무관)
- `planner` — 복잡한 기능/리팩토링 계획
- `architect` — 시스템 설계 결정
- `tdd-guide` — 신규 기능/버그픽스의 테스트 우선
- `code-reviewer` — 코드 작성 후 리뷰
- `cpp-build-resolver` — C++ 빌드/링커/템플릿 에러
- `cpp-reviewer` — C++ 메모리 안정성/모던 idiom 리뷰

## 위임 시 규약

- 허브/하위 specialist는 승인 게이트("May I write this to [filepath]?")를 지킨다 — 사용자 승인 전 Write/Edit 금지.
- 독립적인 하위 작업은 병렬 Task로 띄운다.
- 위임 프롬프트에 관련 파일 경로·설계 제약·성능 요구를 모두 담는다.

## MCP-aware 라우팅 (tool layer)

엔진 MCP(`mcp-unreal` 등)는 위 위임 축과 **별개인 tool layer**다. 이 절은 **세션에 엔진 MCP tool(`mcp__unreal__*` / `mcp__mcp-unreal__*`)이 노출돼 있을 때만** 적용된다 — 없으면 무시한다(대부분의 세션이 그렇다).

- **탐지**: 세션 tool 목록에 엔진 MCP tool이 있는가. 있으면 라이브 에디터가 붙은 게임 프로젝트 세션이다.
- **text vs live 분리** (`MCP-UNREAL-SETUP.md` §7): `ue-*` specialist agent = 코드·설계 산출물(텍스트), 엔진 MCP = 라이브 에디터 조작·빌드·검증(실행). **섞지 않는다** — specialist의 `tools:`에 MCP를 넣지 않으며, MCP 호출은 **세션 레벨**이 담당한다(Two-CLI에서 Builder=실행 lane, Architect=read-only 검사).
- **read-only가 sweet spot**: `get_level_actors`·`blueprint_query`·`ui_query`·`capture_viewport`로 specialist advice를 실제 프로젝트 상태에 grounding하거나 변경을 검증한다.
- **write는 user-supervised**: `spawn_actor`·`blueprint_modify`·`set_property`·`execute_script`는 `scope_check`·`secret_scan` hook **밖**이다(안전망 없음). 테스트 브랜치/사본에서 먼저, 사용자 승인 하에.

상세 셋업·트러블슈팅은 `MCP-UNREAL-SETUP.md`.
