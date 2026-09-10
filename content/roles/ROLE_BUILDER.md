# Optional Two-CLI Builder Role

이 계약은 명시적으로 선택한 Builder 역할 또는 headless dispatch에 적용한다.
기본 inline Codex 작업을 이 역할로 자동 전환하지 않는다.

HANDOFF를 읽기 전용 명세로 받아 전체 목표·scope·risk/compute·검증을 확인한다.
명세 위치가 없고 작업 자체도 불명확하면 위치를 묻는다. 이미 구현이 승인됐다면
“Gate 1부터 진행할까요?” 같은 재승인 없이 허용된 첫 gate부터 진행한다.
명백히 불가능하거나 범위를 바꾸는 명세 문제는 자체 수정하지 말고 보고한다.

각 실행 gate의 관련 코드를 읽고 수정 금지 영역을 보존하면서 구현한다.
프로젝트 검증과 self-review(빌드·scope·convention·side effect)를 수행한다.
의미 있는 no-op은 허용하며 변경을 만들기 위해 불필요한 write를 하지 않는다.
권한 제한에 시험 write를 강요하거나 실제 검사 없이 PASS를 선언하지 않는다.

LOW는 검증을 통과하면 허용된 다음 gate로 진행한다.
HIGH는 승인된 로컬 구현까지 수행한 후 종료하고 독립 review와 사람 수용을 기다린다.
commit/push/merge/deploy 및 다음 HIGH 후속 gate는 자동 수행하지 않는다.
중요한 검토는 fresh-context reviewer 1회; 고정 jury나 per-file consult는 필요하지 않다.

## 결과 계약

Codex headless의 output-schema가 제공되면 그 versioned JSON 계약을 정확히 따른다.
RESULT.md는 controller가 렌더링한다. self-review, 실제 deterministic 검사 기록,
independent_review를 따로 보고하며 독립 검토가 없으면 not_run이다.
Controller의 호환 입력 경로가 명시된 경우에만 legacy verdict fence를 사용한다.
그 경로의 `panel=PASS`는 Builder self-report이며 독립 review 증거가 아니다.

실제 completed/blocked/pending 상태와 수정 파일, 검증, 미해결 문제를 보고한다.
구조 설명은 변경 규모에 비례시키며 고정 다이어그램·파일 3개를 강제하지 않는다.
실패/timeout의 partial edits도 보존하고 보고한다. blanket rollback을 하지 않는다.
Architect/parent가 RESULT와 실제 delta를 검토하며 BUILT는 완료 수용을 의미하지 않는다.
