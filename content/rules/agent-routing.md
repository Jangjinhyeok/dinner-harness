# Agent Routing

메인 세션은 요구사항 해석·작업 분해·설계 판단·결과 통합과 최종 책임을 유지한다.
같은 세션에서 완료해도 구현 단위는 native agent에 위임할 수 있다.
이 문서는 위임 판단 지침이며 자동 scheduler가 아니다. 파일 수에 따른 자동 dispatch,
항상 위임, 임의의 위임 비율, 모든 구조 결정의 mandatory consult는 적용하지 않는다.

## 언제 위임하는가

비단순 구현 전 설계 불확실성, 변경 영향, 검증 가능성, 작업 간 의존성,
문맥 전달·검토 비용을 비교하고 기존 계획에 선택 경로와 이유를 짧게 남긴다.
목표·소유 범위·완료 조건·검증을 독립적으로 전달할 수 있고 분리할 실익이 있는 구현은
아래의 적합한 구현 역할에 위임한다. main은 필요한 설계 결정을 먼저 확정한다.
작은 수정이나 강하게 결합된 작업은 전달·통합 비용이 더 크면 직접 수행한다.
코드 길이·파일 수·모델 비용만으로 위임하거나 risk를 낮추지 않는다.

| 경로 | 선택 기준 | 계약 |
|---|---|---|
| main 직접 수행 | 작은 작업의 위임 비용이 더 큼, 또는 아직 설계/의존성 분리가 어려움 | main이 구현·검증; 중요한 변경/HIGH의 독립 review 유지 |
| native 구현 agent | 범위·완료 조건이 명확하고 현재 세션에서 독립 구현할 실익이 있음 | 해당 구현 `agent_type` 명시, 소유 범위 전달, 결과 인계 후 main 검증 |
| headless `challenge/build` | self-contained 작업에 controller의 pinned scope·baseline/delta 검사가 필요하거나 명시적 compute profile 선택이 적합함 | [Two-CLI reference](two-cli-reference.md)의 HANDOFF·risk/compute·검증 계약 유지 |

native는 controller net과 동등하지 않다. 엄격한 scope 검사가 필요한 작업을 편의상
native/main으로 바꾸지 않는다. 이미 승인된 구현의 위임에 매번 새 승인을 요구하지 않지만,
실제 권한 제한과 commit/push/deploy 및 HIGH 사람 수용 경계는 그대로다.

## 역할과 모델 선택

구체적인 vendor/model/effort는 [routing 정책](routing-reference.md)과 설치 `routing.toml`에서
읽는다. main의 interactive 모델 선택은 별개이며 위임 때문에 변경하지 않는다.
Codex native 설정은 `[native_agents]`의 역할을 `codex_only` profile로 생성한다.
현재 native 구현 specialist는 모두 `builder_normal`이다. 작은 작업이라는 설명이나
작업 이름만으로 `builder_low`가 되지 않으며, HIGH risk라고 자동 승격되지도 않는다.
필요한 compute와 native profile이 맞지 않으면 적절한 main profile 또는 기존 headless
경로를 선택한다. 호출 도구가 명시 override를 지원할 때만 SSOT 값과 기존 risk 정책을
지켜 사용하고 이유를 기록한다. 모델 불가/권한 실패를 다른 모델로 조용히 우회하지 않는다.

일반 독립 리뷰는 `code-reviewer`, C++ 전문 검토는 `cpp-reviewer`로 명시해 호출한다.
`default`에 review라는 작업명/프롬프트를 주는 것은 reviewer routing이 아니다.
별도 model이나 `default`가 필요한 예외는 이유와 적용 profile을 남긴다. 중요한 변경에는
fresh-context reviewer 1회, 추가 specialist는 다른 미해결 위험 축이 있을 때만 배치한다.
검토의 독립성과 요청/실행 model 일치 여부는 서로 다른 검증 항목이다.

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
parent는 목표·소유 파일·현재 baseline·제약·완료 조건·검증 명령을 전달한다.
builder는 그 범위의 구현과 해당 검증을 소유하고, main은 같은 구현을 중복 수행하지 않는다.
builder는 변경 파일·실제 실행한 검사와 결과·미해결 의존성·한계를 반환한다.
범위 밖 변경이 필요하면 임의 확장하지 않고 parent에 인계한다. parent가 실제 diff와
검증 증거를 검사하고 필요한 추가 검증·독립 review를 거쳐 통합한다.
같은 tree의 동시 writer는 기본 금지다. 병렬 구현은 격리 위치와 통합 방법을 먼저 정하고
parent가 결과를 통합·검증한다. branch 전략을 임의로 바꾸지 않는다.
이미 승인된 로컬 수정은 매 파일마다 묻지 않는다. HIGH 수용 경계는
[autonomy policy](autonomy-policy.md)를 따른다.

관찰은 기존 native UI/tools 또는 headless receipt/실행 메타데이터를 사용한다.
기존 계획/결과 보고에 `경로(main/native/headless) / Risk / 선언 Compute와 유효 profile
(적용되는 경우) / 호출 역할 / 요청 model·effort / 선택 이유 / 확인된 실행 model`을 짧게 남긴다.
main 직접 수행과 review에는 builder Compute를 붙이지 않는다. 로컬 turn_context 관찰과
서버 과금 확인은 별개이며, 실제 실행 model을 확인할 수 없으면 요청 설정만 확인됐다고 쓴다.
설정 존재, 요청 profile, 실제 응답/변경/검증, 확인된 실행 model을 구분한다.
실행 model 메타데이터가 없으면 확인 불가로 보고하고 agent의 자기 진술로 대체하지 않는다.
합성 검증 작업은 과거 실무 분담의 증거가 아니며 지침 개선이 자동 위임을 보장하지 않는다.

Engine MCP는 별도의 실제 editor 조작 도구이며 모든 호출이 file hook에 잡히지 않는다.
허용된 scope 안에서 사용하고, live asset 변경은 사본 등 검증 가능한 환경으로 다룬다.
MCP availability를 추측하지 않으며 engine runtime이 없으면 검증은 not_run이다.
