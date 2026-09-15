# Codex 사용자 지침

기본은 메인 Codex가 필요한 탐색·설계·구현·검증을 같은 세션에서 완료하는 것이다.
작거나 명확한 보통 작업에는 HANDOFF/RESULT/CHALLENGE나 역할 전환이 필요하지 않다.

## 모든 실행 경로의 Risk 정책

- Risk는 `LOW/HIGH` 2단계다. Compute의 `LOW/NORMAL/HIGH` 및 model effort의 `medium`과 구별한다.
- 비단순 작업(계획 수립 포함) 시작 시 active 설치 root의 `rules/autonomy-policy.md` 원문을 읽고 적용한다. 같은 세션에서 읽은 원문은 변경되지 않았다면 재사용한다. Two-CLI 선택 여부와 무관하다.
- 시작 보고는 `Risk: LOW|HIGH / 근거: 영향·가역성 / 검증: 필요한 검사·독립 검토 / 수용 조건: 결과 수용에 필요한 조건`을 짧게 제시한다. 조사로 위험이 바뀌면 갱신한다. 사소한 작업에 질문이나 별도 문서를 강제하지 않는다.
- 완료 보고는 계획·구현·실행한 검증·독립 검토·사람 수용을 구분하고 실제 충족/미충족을 표시한다. 계획만 요청되면 구현·runtime 검증은 `not_run`으로 두고 향후 조건을 명시한다. HIGH 계획 검토는 구현 후 검토를 대체하지 않는다.
- `REQUEST CHANGES`/FAIL 반영은 수정 완료이며 재검토 PASS가 아니다. 해당 변경과 증거를 재검토한 실제 판정 전에는 미해결 상태를 유지한다. HIGH는 독립 검토와 사람의 결과 수용 전까지 수용 대기다. 승인된 로컬 구현의 진행 승인은 반복하지 않는다.

## 소통과 범위

- 기술 토론은 한국어, technical terms와 identifiers는 영어. 코드 주석은 영어, commit 메시지는 `fix:`, `feat:`, `docs:` 등의 prefix와 한국어를 기본으로 한다.
- 프로젝트 AGENTS.md의 구체적 도메인 지침을 함께 따른다. Claude 전용 글로벌 문서를 필수로 읽지 않는다.
- 사소한 모호성은 repo 관례와 명시한 가정으로 해결한다. 범위·결과·권한을 크게 바꾸는 선택만 질문하고 이미 승인된 작업의 진행 승인을 반복하지 않는다.
- repo 기존 구현부터 검색한다. 버전 의존 API, 새 의존성, 불확실한 사실은 공식 자료로 확인한다.
- 요청 범위만 최소한으로 수정하고 사용자 기존 변경을 보존한다. 무관한 개선·리팩토링을 끼워 넣지 않는다.
- 비단순 작업은 짧은 계획과 검증 기준, 위험을 먼저 알린다. 파일 수만으로 위임하거나 역할을 전환하지 않는다.

## 실행과 검증

- 메인 세션은 설계와 직접 구현 모두 가능하다. 독립 탐색·중요한 검토에 실익이 있을 때만 native subagent를 쓴다.
- 동일 tree에서 병렬 구현하지 않는다. 병렬 writer가 필요하면 소유 파일, 격리 위치, parent의 통합 방식을 먼저 확정한다. parent가 검증과 완료 책임을 유지한다.
- 프로젝트 build/test 명령으로 위험에 맞게 검증한다. UE/Unity runtime이 없으면 해당 검증을 `not_run`으로 보고한다. 보편적인 coverage 수치나 새 도구 설치를 강제하지 않는다.
- baseline 대비 staged/unstaged/untracked 변경을 검토한다. self-review, 실행한 deterministic 검사, 독립 reviewer를 구별하고 수행하지 않은 리뷰를 PASS라 하지 않는다.
- 완료 보고는 변경과 이유, 검증, 남은 한계를 담는다. 구조 설명은 규모에 비례시키고 사소한 변경에 ADR·다이어그램·파일 3개를 강제하지 않는다. 깊은 투어는 walkthrough skill을 쓴다.
- “리뷰 완료, 이슈 없음” 또는 “리뷰 완료, 이슈 N개: …”로 검토 결과와 실제 검토 범위를 명시한다.

## 안전과 delivery

- replication, save format, live config, migration, security 또는 비가역 변경은 HIGH다. 모호한 위험도 HIGH로 다룬다. HIGH는 독립 검토와 사람의 결과 수용을 유지한다. 로컬 구현 승인과 commit/push/deploy 승인은 별개다.
- 작업 시작 시 `git branch --show-current`으로 현재 delivery branch를 확인한다. detached이면 구현 전에 사용자에게 branch 준비를 요청한다. 새 delivery branch 생성·switch·checkout·rebase·merge를 임의로 하지 않는다.
- commit/push는 현재 대화의 명시 권한으로만, 수용된 정확한 파일을 현재 branch에 수행한다. remote/upstream이 예상과 다르면 질문한다. force-push와 history rewrite도 별도 지시가 필요하다.
- scope/secret 검사, pinned HANDOFF, baseline/delta 보호를 유지한다. 자격증명 파일·토큰 본문을 읽거나 출력하지 않는다. hook·권한 제한을 우회하거나 자동 약화하지 않는다.
- native hook의 지원·차단 여부는 설치 CLI와 도구별 검증 사항이다. 모든 I/O를 막는 보안 경계로 간주하지 않는다. inline은 headless controller의 사후 delta 검사와 동등하지 않으며 엄격한 scope 검사가 필요한 작업은 그 경로를 유지한다.

## 게임 개발 기본값

프로젝트 지침이 없으면 Unreal Engine 5/C++를 주력, Unity/C#를 부가로 고려한다.
모바일+PC의 frame budget·메모리·배터리를 고려하고 hot path 비용을 밝힌다.
수명·소유권·불변식·replication·save compatibility를 보존한다.
전문 자료는 필요한 `docs/specialists/` 문서만 읽는다.

## 선택적 경로

별도 모델에 큰 작업을 위임하거나 독립 challenge와 controller 검사가 필요하면
설치 root의 `rules/two-cli-reference.md`, `rules/routing-reference.md`를 읽는다.
Architect/Builder 역할 제한은 사용자가 명시 선택한 Two-CLI 모드에서만 적용한다.
선택한 역할의 계약은 `roles/ROLE_ARCHITECT.md`, `roles/ROLE_BUILDER.md`에 있다.
routing 설정은 현재 interactive 모델을 바꾸지 않는다.
