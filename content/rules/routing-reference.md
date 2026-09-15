# Routing Reference

이 문서는 Compute/model routing을 다룬다. 모든 실행 경로의 Risk 정책은
[autonomy policy](autonomy-policy.md)이며 Risk는 LOW/HIGH, Compute는 LOW/NORMAL/HIGH다.
보고와 설명에는 Risk/Compute 축 이름을 명시한다. 모델명 뒤 소문자 값은 effort다.

모델 정책 SSOT는 source `content/routing.toml`, 설치본 `routing.toml`이다.
기본 preset은 codex_only이며 hybrid와 claude_only는 선택 가능한 호환 경로다.
구체적인 모델/effort 값은 TOML에서 읽고 문서나 프롬프트로 덮어쓰지 않는다.

2026-09-10 초기 운영 제안은 main/architect Astra medium, 작은 위임 Luna medium,
일반 위임 Terra medium, Compute HIGH 구현 Astra high, 중요한 독립 review Sol high,
Risk HIGH design challenge Astra high의 별도 호출이다. 벤치마크로 최적성을 입증한 조합이 아니다.

2026-09-11 builder 비용 계층 결정은 [ADR-0020 addendum](https://github.com/Jangjinhyeok/dinner-harness/blob/main/docs/architecture/ADR-0020-routing-preset-architecture.md#addendum-2026-09-11-codex-builder-cost-tiers)을 참고한다.
기본/hybrid builder는 같은 비용 계층을 사용하며,
일반 작업을 자동으로 frontier 모델에 올리지 않는다. 실제 값은 TOML이 결정한다.
LOW compute는 명확하고 국소적이며 기존 pattern을 복제하는 구현,
NORMAL compute는 기존 abstraction을 활용하는 일반 feature/moderate refactor,
HIGH compute는 architecture·ownership·invariant 판단과 큰 영향 범위의 구현에 사용한다.
검증 실패가 요구사항/추론 부족을 드러내면 같은 저가 profile로 무작정 반복하지 말고
compute를 재평가한다. 이 지침이 자동 retry/escalation 기능을 추가하지는 않는다.

명시 model/effort override는 non-HIGH risk에서 기존 CLI 경로로 적용한다.
HIGH risk에서는 설정된 profile과 정확히 일치해야 한다. 예외적 effort escalation이
필요하면 정책 변경과 그 정책에 결합된 challenge를 다시 수행해야 하며 Risk HIGH를 낮추지 않는다.
현재 harness의 Codex effort 허용값은 `low/medium/high/xhigh`이며
`max/ultra`는 허용하지 않는다.

## 적용 범위

Logical keys는 `architect`, `builder_low`, `builder_normal`, `builder_high`,
`challenger_high`, `reviewer`다. `builder_low/normal/high`는 위임 compute를 선택하며,
`challenger_high`는 Risk HIGH 설계 검토의 별도 호출이다.

- Interactive main/architect: 권장 profile이며 routing 파일이 열린 세션 모델을 바꾸지 않는다.
  모델은 앱 선택기 또는 지원되는 CLI model/effort 옵션에서 사용자가 선택한다.
- Headless challenge/build: 실제 실행할 gate 집합과 선택 preset/override에서 profile을 결정한다.
  risk와 compute는 다르며 mixed scope의 Risk HIGH를 첫 gate Risk LOW로 숨기지 않는다.
- Native custom agents: logical role에서 생성된 model/effort/permissions를 사용한다.
  읽기 전용 reviewer/planner/architect가 구현 권한을 받지 않도록 확인한다.

명시 preset/override가 없으면 설치 TOML active preset을 따른다.
부분 override는 나머지 필드를 active preset의 명시적 호환 관계로 결정해야 하며
다른 preset을 이름순 탐색하거나 vendor default로 조용히 새면 안 된다.
실제 선택값과 resolution 근거는 receipt에서 확인한다. 모호한 후보·빈 모델·지원하지 않는
effort는 오류로 보고하며 다른 vendor/API 과금으로 조용히 fallback하지 않는다.

정적 profile 형식 검증, CLI schema/capability 검증, 실제 계정 model access는 다른 증거다.
검증하지 못한 접근은 unknown으로 보고한다. Pro 구독이 API 요금을 포함한다고 가정하지 않는다.
effort 이름을 추측 변환하거나 max/ultra 같은 미확인 옵션을 기본 생성하지 않는다.
`run`은 legacy/experimental이며 이 기본 routing 경로와 동일하다고 설명하지 않는다.
Real headless Risk HIGH 작업은 bound challenge/review 경계가 있는 `challenge/build`로 수행한다.
단일 interactive 세션의 Risk HIGH 구현은 autonomy policy의 독립 검토·사람 수용을 유지하며
가능하다. 이 문장은 Two-CLI나 headless 전환을 강제하지 않는다.
Legacy `run --backend real`은 Risk HIGH 구현을 거부한다.
