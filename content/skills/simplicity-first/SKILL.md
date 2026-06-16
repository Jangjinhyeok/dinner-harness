---
name: simplicity-first
description: Use when writing new code or refactoring. Triggers when implementing features, adding utility functions, or designing abstractions. Enforces minimum-viable code, prevents over-engineering and speculative flexibility.
---

# Simplicity First

최소한의 코드만 작성하라.

- 요청된 것 이상은 만들지 않는다.
- 일회성 코드에 추상화를 도입하지 않는다.
- 요청하지 않은 "유연성", "구성 가능성", "확장성"을 추가하지 않는다.
- 발생할 수 없는 시나리오에 대한 에러 처리를 작성하지 않는다.
- 200줄을 50줄로 줄일 수 있다면 다시 쓴다.

## 판단 기준

코드를 작성하기 전 또는 작성 후 자문한다:

> "시니어 개발자가 이걸 과설계라고 할까?"

답이 "그렇다"이면 단순화한다.

## 흔한 함정

- **인터페이스 조기 추출**: 구현체가 하나뿐인데 인터페이스를 만드는 것. 두 번째 구현체가 실제로 나타날 때 추출하는 것이 맞다.
- **설정 가능성**: "나중에 바꿀 수 있게" 설정 파일이나 매개변수를 추가하는 것. 실제로 바꿀 일이 없으면 hardcode가 낫다.
- **방어적 코딩 과잉**: 호출자가 명백히 보낼 수 없는 null이나 잘못된 값에 대한 검사. 호출 컨텍스트가 보장하면 검사 불필요.
- **에러 처리 추측**: 발생 가능성을 정확히 모르는 예외에 대한 catch 블록. 실제 발생하는 예외만 처리.

## 예외

요청 자체가 "유연성"이나 "확장성"을 명시한 경우에는 그 요청을 따른다. 단, 이 경우에도 요청된 범위만 만든다.
