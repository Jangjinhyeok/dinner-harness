---
name: simplicity-first
description: Use when writing new code or refactoring. Triggers when implementing features, adding utility functions, or designing abstractions. Enforces minimum-viable code, prevents over-engineering and speculative flexibility.
---

# Simplicity First

요청한 결과를 충족하는 가장 단순한 구현을 선택하고 기존 project convention을 우선한다.
줄 수보다 요구사항과 control/data flow를 기준으로 판단한다.

- 실제 두 번째 use case 없이 범용 layer를 만들거나 필요 없는 abstraction을 추가하지 않는다.
  단, 기존 interface 계약, engine boundary 또는 test seam 등 현재의 이유가 있으면 유지한다.
- 요청에 필요하지 않은 configuration surface, 유연성, 확장성을 미리 만들지 않는다.
- 호출 계약과 불변식이 보장하는 경로에 중복 방어를 더하지 않는다. 외부 입력, 수명 또는
  실패 가능성이 불명확하면 먼저 확인하고 필요한 검증·복구를 보존한다.
- 기존 관례보다 control/data flow가 이해하기 어려워졌는지 검토한다.
- 명시적 switch/state table, serialization/schema, engine boilerplate는 길어도 읽기 쉬울 수
  있다. line count를 줄이기 위해 압축하거나 분할하지 않는다.

불필요한 계층과 선택지를 덜어내되 correctness, ownership, compatibility를 희생하지 않는다.
요청이 확장성을 포함하면 그 요구에 필요한 범위까지 구현한다.
