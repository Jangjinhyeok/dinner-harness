---
name: surgical-changes
description: Use when modifying existing code. Critical for live-service projects. Triggers when editing files in established codebases, fixing bugs, or making targeted changes. Prevents scope creep, unintended refactoring, and "while I'm here" modifications.
---

# Surgical Changes

외과적으로 수정하라. 라이브 서비스 안전 직결.

- 요청된 범위 밖의 코드는 건드리지 않는다. 인접 코드의 "개선", 주석/포맷 정돈도 금지.
- 망가지지 않은 것은 리팩토링하지 않는다.
- 본인이라면 다르게 했더라도 기존 스타일을 따른다.
- 무관한 데드 코드를 발견하면 언급만 하고 삭제하지 않는다.
- 본인이 만든 변경으로 인해 고아가 된 import/변수/함수는 정리한다. 기존부터 있던 데드 코드는 명시 요청 없이 삭제하지 않는다.
- 기존 사용자 변경을 보존한다.
- 변경은 요청한 결과에 필요하거나 그 변경으로 직접 발생한 필수 파생 수정이어야 한다.
  signature 변경에 따른 caller, required include/import, regression test, 변경으로 생긴
  dead code 정리와 compilation/build 유지에 필요한 연쇄 수정은 포함한다.

## 검증 질문

변경 후 자문한다:

> "이 수정이 요청한 결과 또는 그 결과에 필요한 파생 변경인가?"

관련 없는 본인 수정만 되돌린다. 기존 사용자 변경을 함께 되돌리지 않는다.

## 라이브 서비스 추가 원칙

라이브 서비스 코드베이스에서는 다음을 더 엄격히 적용:

- 변경 영향 범위를 명시적으로 보고한다 (어떤 시스템에 영향, 어떤 사이드이펙트 가능성).
- 기존 동작을 유지하는 것이 새 기능 추가보다 우선한다.
- "이 정도는 괜찮겠지" 판단을 금지한다. 확실하지 않으면 보수적으로.

## 발견한 문제는 언급만 하기

작업 중 무관한 버그, 데드 코드, 컨벤션 위반 등을 발견했을 때:

❌ "이것도 같이 고쳤습니다."
✅ "작업 중 다음을 발견했지만 스코프 밖이라 변경하지 않았습니다: [목록]. 별도 작업으로 처리할지 결정 필요."

## 예외

요청이 명시적으로 리팩토링이거나 "주변 코드도 정리"라고 한 경우에는 그 요청 범위까지 작업한다.
