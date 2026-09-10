# Autonomy and Risk Policy

2026-09-10: Codex 기본은 같은 세션의 설계·구현·검증이다. 기존 ADR의 강제 consult/jury와
Codex 영구 degraded 설명은 당시 기록으로 보존하되 현재 운영 정책은 이 문서를 따른다.

## Risk와 compute

Risk는 변경의 영향과 비가역성, compute는 필요한 추론 자원이다. 서로 대체하지 않는다.
LOW는 범위가 명확하고 되돌릴 수 있는 로컬 변경이다.
HIGH는 replication/RPC/net serialization, save/serialization format, live config/feature flag,
migration/schema, security(auth/crypto/trust/anti-cheat), public API/ABI, build/packaging pipeline,
또는 큰 blast radius/비가역성을 가진 변경이다. 모호하면 HIGH로 다룬다.

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

## 안전 경계

scope/secret 검사, baseline/delta 사용자 변경 보호, pinned HANDOFF 변조 검사를 유지한다.
Native PreToolUse 지원·차단은 CLI 버전/도구/설정별로 검증하며 모든 I/O 보안 경계로 간주하지 않는다.
headless controller net은 turn 이후 delta 검사다. hook 차단과 같은 기능이 아니며 하나로
다른 하나를 제거하지 않는다. inline에서 동등한 강제 검사가 없으면 그 차이를 알리고
엄격한 scope 검사가 필요한 작업을 자동 inline 전환하지 않는다.
권한 또는 검사 실패를 우회하거나 blanket rollback으로 기존 dirt를 지우지 않는다.
