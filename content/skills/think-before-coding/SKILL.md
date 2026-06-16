---
name: think-before-coding
description: Use when starting any non-trivial coding task. Triggers when the user makes ambiguous requests, asks for code changes, or starts a new feature. Encourages explicit assumptions, option enumeration, and clarifying questions before implementation.
---

# Think Before Coding

가정을 명시하라 — 추측 금지.

코드 작성 또는 변경 전에 다음을 수행한다:

- 모호한 요청은 추측하지 말고 가정을 먼저 밝힌 후 진행한다.
- 여러 해석이 가능하면 옵션을 제시하고 사용자가 선택하게 한다. 임의로 한쪽을 고르지 않는다.
- 더 간단한 접근법이 있다고 판단되면 먼저 제안한다. 필요하면 반대 의견을 낸다.
- 불분명한 것이 있으면 멈추고, 무엇이 불분명한지 명시하고, 묻는다.

## 적용 예시

요청: "이 함수에 검증 추가해줘"

❌ 추측 후 진행:
"네, null 체크와 범위 체크를 추가했습니다."

✅ 가정 명시 후 진행:
"검증 종류를 명확히 하기 위해 확인하겠다:
1. null/undefined 검사만
2. 값의 유효 범위까지 (예: 음수 차단)
3. 타입 검사 (예: 정수만 허용)
어느 수준의 검증이 필요한가? 또는 전부?"

## 언제 이 skill을 건너뛰는가

trivial한 작업(변수 이름 변경, 오타 수정 등)에서는 이 원칙을 적용하지 않아도 된다. 판단 기준: "이 작업에 다른 해석이 있을 수 있는가?" 없으면 그냥 진행.
