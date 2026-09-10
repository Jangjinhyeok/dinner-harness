---
name: walkthrough
description: Explain the structure and data flow of requested code or recent changes through a guided read-only tour.
---

# 코드 투어

사용자가 지정한 파일·시스템·commit 범위 또는 현재 작업의 baseline delta를 범위로 삼는다.
staged/unstaged/untracked 상태를 함께 고려한다. 요청 범위가 없고 최근 작업도 불명확하면
대표 진입점을 제안하거나 필요한 범위만 질문한다.

진입점부터 데이터 생산→변환→소비 순서로 설명한다. 각 중요한 클래스/모듈의 책임,
호출 관계, 수명·소유권과 이후 수정 시 주의할 지점을 실제 파일 링크로 연결한다.
사용자의 기존 이해 수준과 변경 규모에 맞춰 깊이를 조절한다.

설계 이유와 대안은 의미 있는 선택일 때 설명하고, 작은 변경에는 다이어그램이나
직접 읽을 파일 3개를 강제하지 않는다. 복잡한 관계는 작은 구조 그림으로 정리한다.
확인 질문은 학습을 원할 때 선택적으로 사용하고 투어 완료의 필수 gate로 삼지 않는다.

읽기 전용이다. 발견한 결함은 근거와 함께 보고하며 별도 수정 요청 없이 고치지 않는다.
