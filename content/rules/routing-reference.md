# Routing Reference

모델 정책 SSOT는 source `content/routing.toml`, 설치본 `routing.toml`이다.
기본 preset은 codex_only이며 hybrid와 claude_only는 선택 가능한 호환 경로다.
구체적인 모델/effort 값은 TOML에서 읽고 문서나 프롬프트로 덮어쓰지 않는다.

2026-09-10 초기 운영 제안은 main/architect Astra medium, 작은 위임 Luna medium,
일반 위임 Terra medium, 복잡한/HIGH 구현 Astra high, 중요한 독립 review Sol high,
HIGH design challenge Astra high의 별도 호출이다. 벤치마크로 최적성을 입증한 조합이 아니다.

## 적용 범위

Logical keys는 `architect`, `builder_low`, `builder_normal`, `builder_high`,
`challenger_high`, `reviewer`다. `builder_low/normal/high`는 위임 compute를 선택하며,
`challenger_high`는 HIGH 설계 검토의 별도 호출이다.

- Interactive main/architect: 권장 profile이며 routing 파일이 열린 세션 모델을 바꾸지 않는다.
  모델은 앱 선택기 또는 지원되는 CLI model/effort 옵션에서 사용자가 선택한다.
- Headless challenge/build: 실제 실행할 gate 집합과 선택 preset/override에서 profile을 결정한다.
  risk와 compute는 다르며 mixed scope의 HIGH를 첫 gate LOW로 숨기지 않는다.
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
Real HIGH 작업은 bound challenge/review 경계가 있는 `challenge/build`로 수행한다.
Legacy `run --backend real`은 HIGH 구현을 거부한다.
