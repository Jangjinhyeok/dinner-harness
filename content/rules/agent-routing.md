# Agent Routing

2026-09-10: 기본은 메인 세션이 완료 책임을 유지하는 inline 구현이다.
파일 수에 따른 자동 dispatch, 모든 구조 결정의 mandatory consult는 적용하지 않는다.

## 언제 위임하는가

독립 탐색·중요한 별도 검토·경계가 명확한 작업에서 비용/지연 이점이 있을 때 쓴다.
기본은 구현자 검증이며 중요한 변경에는 fresh-context reviewer 1회,
추가 specialist는 다른 미해결 위험 축이 있을 때만 배치한다.
메인 Astra 작업을 risk/파일 수만으로 저가 모델에 내려보내지 않는다.
native model/effort는 routing logical profile을 따른다; interactive 모델 선택은 별개다.

## 엔진과 전문 자료

프로젝트 AGENTS.md 등 명시된 engine 정보를 우선한다.
`*.uproject` 또는 `Source/*/*.Build.cs`는 Unreal,
`ProjectSettings/ProjectVersion.txt` 또는 `Assets/`+`Packages/manifest.json`은 Unity 신호다.
관련 전문 자료는 직접 읽어도 되며 항상 agent를 부를 필요는 없다.
경로는 active harness install root 기준이다.

| 영역 | 선택 agent | 필요한 참조 |
|---|---|---|
| Unreal | unreal-specialist | docs/specialists/ue-gas.md, ue-blueprint.md, ue-replication.md, ue-umg.md 중 관련 문서 |
| Unity | unity-specialist | docs/specialists/unity-dots.md, unity-shader.md, unity-addressables.md, unity-ui.md 중 관련 문서 |
| Gameplay / netcode | gameplay-programmer / network-programmer | 프로젝트 불변식·소유권·예측·성능 요구 |
| UI / tooling / profiling | ui-programmer / tools-programmer / performance-analyst | 실제 engine version과 검증 절차 |
| 설계 / 계획 | architect / planner | 관련 boundary·의존성·성공 기준 |
| 검토 / 테스트 설계 | code-reviewer / cpp-reviewer / tdd-guide | baseline delta와 실행한 검증 |
| C++ build 실패 | cpp-build-resolver | 원본 exit code와 필요한 redacted diagnostic |

## 위임 계약

읽기 전용 explorer/reviewer는 구현 쓰기 권한을 받지 않는다.
parent는 목표·관련 파일·제약·검증과 소유 범위를 전달한다.
같은 tree의 동시 writer는 기본 금지다. 병렬 구현은 격리 위치와 통합 방법을 먼저 정하고
parent가 결과를 통합·검증한다. branch 전략을 임의로 바꾸지 않는다.
이미 승인된 로컬 수정은 매 파일마다 묻지 않는다. HIGH 수용 경계는
[autonomy policy](autonomy-policy.md)를 따른다.

Engine MCP는 별도의 실제 editor 조작 도구이며 모든 호출이 file hook에 잡히지 않는다.
허용된 scope 안에서 사용하고, live asset 변경은 사본 등 검증 가능한 환경으로 다룬다.
MCP availability를 추측하지 않으며 engine runtime이 없으면 검증은 not_run이다.
