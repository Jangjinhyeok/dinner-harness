# dinner-harness

**한국어** | [English](README.en.md)

Claude Code 중심으로 설계·구현·검증을 이어가는 개인 harness의 source of truth다(ADR-0023).
기본은 Claude Opus 5.5 메인 세션이며, 독립 탐색·중요한 review 또는 경계가 명확한 위임에만
추가 agent를 쓴다. Codex target과 hybrid/codex_only preset은 선택 가능한 호환 경로로 유지한다.
설치된 `~/.claude`·`~/.codex`는 생성 결과다. canonical source를 수정하고 검증 후 설치한다.

## 기본 workflow

요청 → main의 탐색·설계와 직접 수행/위임 판단 → 직접 또는 지정 역할의 구현 → main의 통합·프로젝트 검증 →
필요한 독립 review → 결과 보고.

보통 작업은 HANDOFF/RESULT/CHALLENGE나 Builder 역할 전환 없이 진행한다.
main은 최종 책임을 유지하며, 분리할 실익이 있는 구현은 지정 역할에 위임한다.
작은 작업은 문맥 전달·검토 비용이 더 크면 직접 수행한다. 설계 불확실성·영향·검증 가능성·
의존성이 판단 기준이며 항상 위임하거나 비율을 맞추지 않는다.
[agent routing](content/rules/agent-routing.md)에 선택·소유권·인계 계약이 있다.
일반 review는 `code-reviewer`를 명시한다. `default`의 작업명만으로 reviewer 모델이 선택되지 않는다.
파일 수 자체는 위임 기준이 아니다. 독립 작업에 실익이 있을 때 native subagent를 쓰며,
동일 tree에서 병렬 구현하지 않는다. 병렬 writer는 소유 범위·격리·통합을 먼저 정한다.
parent가 통합과 완료 책임을 유지한다.

HIGH(replication/save/live config/migration/security 등)는 독립 검토와 사람 수용을 유지한다.
사용자가 승인한 로컬 구현은 매 파일마다 재승인받지 않는다.
commit/push/deploy, branch 변경은 별도 권한이다. self-review·실제 test 실행·독립 review를
구별하며 수행하지 않은 리뷰는 not_run이다.

## Claude 설치와 확인

Python, Git, Claude Code CLI가 필요하다. Codex CLI나 Codex home은 필요하지 않다.
Windows 예시이며 다른 OS는 `py -3` 대신 설치된 Python executable을 쓴다.

```powershell
py -3 check.py --target claude --no-install
py -3 install.py --target claude --dest "C:/temp/dinner-harness-claude"
py -3 refresh.py --target claude
```

임시 설치 결과(`settings.json`에 `builder_guard`가 없는지, 렌더링된 `CLAUDE.md`)를 확인한 후
**사용자가 live 설치를 요청한 경우에만**:

```powershell
py -3 install.py --target claude --allow-live
py -3 check.py --target claude
```

Claude 설치는 1-CLI 구성이다. orchestrator·`routing.toml`·roles·`rules/_mode`·HANDOFF/RESULT 템플릿·
two-cli/routing reference·`delegate` skill은 설치하지 않는다(orchestrator·routing·roles·reference는
Codex target용으로 유지, `delegate`·`_mode`·HANDOFF/RESULT 템플릿은 source-only).
Claude adapter에는 retire 로직이 없어 이전 설치의 해당 파일과 `claude-direct.cmd`, `dh*.cmd`,
`watch-builder.ps1`, `builder_guard` 파일, settings의 `orchestrate.py` allow 규칙이 `~/.claude`에 남을 수 있다.
`check.py --target claude`가 남은 파일을 leftover로 보고하지만 자동 삭제하지 않는다. 특히 `rules/`의 남은 파일은
매 세션 auto-load되므로 반드시 직접 삭제한다. settings의 allow 규칙은 check.py가 보고하지 않으니
`settings.json`에서 직접 제거한다.
Codex가 필요하면 `--target codex`, 양쪽을 의도한 경우만 `--target all`을 쓴다.
Codex 설치 절차와 기존 사용자 config 보존 규칙은 [전환 결과](docs/codex-migration-2026-09-10.md)에 있다.

새 프로젝트에서 평소처럼 `claude`를 열고 요청한다. 평범한 `claude` 세션이 직접 수정 세션이다.
초기 interactive 권장 실행 예시:

```text
claude --model claude-opus-5-5 --effort medium
```

사용 중인 앱에서는 지원되는 모델 선택기를 쓴다. routing.toml 수정이나 harness 설치는
이미 열린 세션의 모델을 바꾸지 않는다.

## 모델 정책과 적용 범위

구체적인 profile SSOT는 [content/routing.toml](content/routing.toml)이다(기본 preset `claude_only`).
근거는 [ADR-0023](docs/architecture/ADR-0023-claude-only-default.md)의 VulcanBench Frontier v4
(2026-10-08, 23 tasks × 5 efforts) 결과이며 구현 위주 벤치마크의 외삽이라 최적성을 입증한 값이 아니다.

| 역할 | 모델 / effort | 적용 |
|---|---|---|
| Main / architect | Claude Opus 5.5 / medium | interactive 권장값, 실제 선택은 앱/CLI |
| 작은 명확한 위임 | Claude Opus 5.5 / low | 선택된 headless LOW |
| 일반 구현 위임 | Claude Opus 5.5 / medium | headless NORMAL/native 구현 profile (agent frontmatter `model: opus`) |
| 복잡한/HIGH 구현 | Claude Sonnet 5.5 / max | HIGH compute (비용·시간 수용) |
| 중요한 독립 review | Claude Opus 5.5 / medium | fresh-context reviewer |
| HIGH design challenge | Claude Opus 5.5 / high | 구현과 별도 read-only 호출 |

현재 native 구현 specialist는 `builder_normal`이며 LOW/HIGH를 자동 선택하지 않는다.
headless는 선택 gate의 risk/compute를 해석한다. 이 지침은 자동 위임 scheduler가 아니다.
risk와 compute는 별개다. profile 형식 검증, 설치 CLI의 schema/capability,
계정의 실제 모델 접근성도 별개다. 확인하지 못한 접근은 unknown이다.
Opus의 높은 effort 구간은 일부 Opus 4.8 fallback을 포함할 수 있다.
effort 이름을 추측 변환하거나 인증/모델 실패를 다른 vendor·API 과금으로 조용히 fallback하지 않는다.
구독이 API 비용을 포함한다고 가정하지 않는다. `codex_only`(GPT-6.1 Sol xhigh)와 `hybrid`는 선택 가능한 호환 preset이다.

## 선택적 headless dispatch (Codex target 전용)

이 경로는 Claude 1-CLI 설치에 포함되지 않으며 Codex target에서만 설치된다. 위 표의 headless/challenge
profile은 이 경로에만 적용되고, Claude 설치의 위임은 native subagent(frontmatter `model: opus`)를 쓴다.
큰 작업을 다른 모델에 맡기거나 controller의 pinned scope/secret·baseline/delta 검사가 필요하면
[Two-CLI reference](content/rules/two-cli-reference.md)를 사용한다.
scope와 검증 기준이 있는 self-contained HANDOFF로 `orchestrate.py challenge/build`를 실행한다.
[Architect](content/roles/ROLE_ARCHITECT.md)와 [Builder](content/roles/ROLE_BUILDER.md) 역할 제한은
명시적으로 선택한 Two-CLI 모드에만 적용한다.
`run`은 legacy/experimental이며 기본 workflow가 아니다.

Codex JSONL events는 thread/error/usage 관찰용, 최종 schema JSON은 결과 계약용이다.
RESULT와 실제 delta를 함께 검토한다. BUILT와 Builder의 panel=PASS는 독립 review나 수용 증거가 아니다.
결과 복구는 read-only이며 format 오류나 no-op을 이유로 불필요하게 재구현하지 않는다.
실패/timeout partial edits도 검사하고 기존 사용자 변경을 blanket rollback하지 않는다.

Native hooks는 지원 도구에서 사전 검사를 수행할 수 있지만 모든 I/O의 보안 경계는 아니다.
Controller net은 사후 delta 검사로 역할이 다르다. 엄격한 scope 검사가 필요한 작업을
동등한 검사가 없는 inline 경로로 자동 이동시키지 않는다.
[현재/과거 검증 기록](CODEX-COVERAGE.md)을 확인한다.

## 구성과 변경 위치

| 경로 | 책임 |
|---|---|
| [content/instructions/CLAUDE.md](content/instructions/CLAUDE.md) · [assets/codex/AGENTS.md](assets/codex/AGENTS.md) | Claude(기본)·Codex 전역 지침 |
| [content/rules](content/rules) · [content/roles](content/roles) | 필요할 때 읽는 risk/routing/headless 계약 |
| [content/skills](content/skills) | 공통 portable skill 본문; native frontmatter는 adapter가 생성 |
| [content/agents](content/agents) | 전문 agent 책임과 domain guidance |
| [content/docs/specialists](content/docs/specialists) | UE/Unity 전문 참조 문서 |
| [content/templates](content/templates) | self-contained 프로젝트 AGENTS와 engine/ADR 템플릿 |
| [adapters/claude.py](adapters/claude.py) · [adapters/codex.py](adapters/codex.py) · [harness.toml](harness.toml) | 선택 target 생성·배선 |
| [orchestrator](orchestrator) | 선택적 headless 실행과 증거·안전 검사 |

bp/gas/repl/umg/ue는 전문 문서를 읽는 작은 진입점이며 별도 agent를 강제하지 않는다.
autonomous-loop/adversarial-review는 고정 judge 수 대신 실제 evidence와 독립 검토를 사용한다.
learnings-review는 opt-in redacted 로그를 읽으며 logging이 없으면 no-data다.
Claude 설치는 `suggest_compact`(advisory)와 `learning_log` hook을 등록하며, Codex 기본 설치는 둘 다 등록하지 않는다.
native compaction을 우선하고 experimental context management는 자동 활성화하지 않는다.

검증은 프로젝트 build/test와 baseline delta 중심이다. coverage 80%, 고정 시간/함수 수 검증,
사소한 수정의 ADR·다이어그램·파일 3개를 강제하지 않는다.
기존 CLAUDE.md hash curation은 legacy provenance 검사이며 Codex 행동/생성 결과 검증의 대체물이 아니다.
역사적 [recon](CODEX-RECON.md)과 [ADRs](docs/architecture)는 당시 관찰로 보존한다.


## 하네스 구성

Source catalog입니다. Codex 설치 대상과 설정은 `harness.toml`과 생성 검증으로 확인합니다.

### Skills (31)

- `adversarial-review`
- `arch-review`
- `asset-authoring`
- `asset-gen-tools`
- `autonomous-loop`
- `bp`
- `changelog`
- `cli-update`
- `codebase-onboarding`
- `delegate`
- `eval-harness`
- `gas`
- `goal-driven-execution`
- `harness-review`
- `hotfix`
- `iterative-retrieval`
- `learnings-review`
- `perf-profile`
- `repl`
- `scope-check`
- `search-first`
- `simplicity-first`
- `strategic-compact`
- `surgical-changes`
- `tech-debt`
- `think-before-coding`
- `ue`
- `ue-umg-review`
- `umg`
- `verification-loop`
- `walkthrough`

### Agents (13)

- `architect`
- `code-reviewer`
- `cpp-build-resolver`
- `cpp-reviewer`
- `gameplay-programmer`
- `network-programmer`
- `performance-analyst`
- `planner`
- `tdd-guide`
- `tools-programmer`
- `ui-programmer`
- `unity-specialist`
- `unreal-specialist`

### Hooks (5)

- `learning_log`
- `route_nudge`
- `scope_check`
- `secret_scan`
- `suggest_compact`
