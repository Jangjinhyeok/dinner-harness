# Autonomy and Risk Policy

2026-09-10: Codex 기본은 같은 세션의 설계·구현·검증이다. 기존 ADR의 강제 consult/jury와
Codex 영구 degraded 설명은 당시 기록으로 보존하되 현재 운영 정책은 이 문서를 따른다.

## Risk와 compute

Risk는 변경의 영향과 비가역성, compute는 필요한 추론 자원이다. 서로 대체하지 않는다.
Risk는 `LOW/HIGH` 2단계이며 MEDIUM은 없다. Compute는 `LOW/NORMAL/HIGH` 3단계다.
model effort의 `medium`도 Risk 값이 아니다. 보고 시 `Risk: LOW / Compute: HIGH`처럼
축 이름을 붙인다. Headless routing은 Risk HIGH를 effective Compute HIGH로 올리지만
Compute HIGH가 Risk HIGH를 뜻하지는 않는다. Controller의 legacy `tier` 필드는 Risk다.
LOW는 범위가 명확하고 되돌릴 수 있는 로컬 변경이다.
HIGH는 replication/RPC/net serialization, save/serialization format, live config/feature flag,
migration/schema, security(auth/crypto/trust/anti-cheat), public API/ABI, build/packaging pipeline,
또는 큰 blast radius/비가역성을 가진 변경이다. 모호하면 HIGH로 다룬다.

## 기본 경로의 시작·완료 보고

이 정책은 단일 Codex 세션의 탐색·계획·구현·검증에도 적용한다. Two-CLI는 선택적 실행
방식이며 정책 적용 조건이 아니다. 비단순 작업은 계획 수립부터 이 원문을 읽는다.
같은 세션에서 읽은 원문은 변경되지 않았다면 재사용한다.

시작 시 짧게 `Risk: LOW|HIGH / 근거: 영향·가역성 / 검증: 필수 검사·독립 검토 /
수용 조건: 검증·검토·HIGH 사람 결과 수용`을 제시한다. 조사 중 위험이 바뀌면 근거와
남은 조건을 갱신한다. 사소한 작업에 질문, HANDOFF 또는 Two-CLI를 강제하지 않는다.

완료 보고는 다음 상태를 실제 증거와 함께 구분한다: 계획, 구현, deterministic 검증
(PASS/FAIL/not_run), self-review, 독립 검토(PASS/FAIL/BLOCKED/not_run), 사람 수용
(수용/대기/LOW 해당 없음). 계획 완료가 구현·검증·수용 완료를 뜻하지 않는다.
계획만 요청되면 계획 검토 범위를 밝히고 구현·runtime 검증은 not_run 및 향후 필수
조건으로 남긴다. HIGH 계획 결과도 독립 검토와 사람 수용이 필요하며 설계 검토는
구현 후 독립 검토를 대체하지 않는다. 미충족 조건을 최종 보고에서 숨기지 않는다.

## 실행과 수용

사용자가 요청한 로컬 구현·검증은 재승인 없이 진행한다. 구현자는 프로젝트 기준의
deterministic 검증과 self-review를 수행한다. 중요한 변경은 별도 context의 reviewer 1회를
활용하고, HIGH에는 독립 검토와 사람의 결과 수용을 유지한다. 추가 specialist는
실제로 다른 미해결 위험 축이 있을 때만 사용한다. 사전 challenge와 사후 review는 목적이 다르다.
파일 수나 비단순 여부만으로 consult→challenge→jury를 강제하지 않는다.

LOW는 검증과 결과 보고로 완료한다. HIGH 로컬 구현은 승인 범위 안에서 가능하나 독립 검토와
사람 수용 전에는 완료 수용을 선언하지 않는다. headless HIGH는 구현 후 종료하며 다음 gate로
자동 진행하지 않는다. commit/push/merge/deploy는 별도의 권한이며 LOW도 자동 허용되지 않는다.
Builder self-report, 실제 deterministic 실행 기록, independent review를 구별한다.
수행하지 않은 검토는 not_run이다. 구체적 결함이 없으면 PASS를 허용한다.
REQUEST CHANGES/FAIL → 수정 반영 → 해당 변경과 검증 증거의 독립 재검토를 구분한다.
수정자의 반영 보고만으로 PASS로 바꾸지 않는다. 재검토 전에는 원래 판정과
`수정 반영, 재검토 대기`를 함께 기록한다. PASS도 사람 수용을 대신하지 않는다.

## 안전 경계

AGENTS/skill/prompt는 모델의 행동 지침이다. 원문 읽기·risk 분류·보고·사람 수용을
prompt만으로 강제 집행했다고 주장하지 않는다. Controller는 선언된 Risk를 파싱하고
누락/알 수 없는 값은 HIGH로 처리하지만 코드 의미를 분석해 잘못 선언된 LOW를
자동 판별하지 않는다. Native hook과 delta 검사도 의미적 risk 분류나 독립 검토의 증거가 아니다.
scope/secret 검사, baseline/delta 사용자 변경 보호, pinned HANDOFF 변조 검사를 유지한다.
Native PreToolUse 지원·차단은 CLI 버전/도구/설정별로 검증하며 모든 I/O 보안 경계로 간주하지 않는다.
headless controller net은 turn 이후 delta 검사다. hook 차단과 같은 기능이 아니며 하나로
다른 하나를 제거하지 않는다. inline에서 동등한 강제 검사가 없으면 그 차이를 알리고
엄격한 scope 검사가 필요한 작업을 자동 inline 전환하지 않는다.
권한 또는 검사 실패를 우회하거나 blanket rollback으로 기존 dirt를 지우지 않는다.
