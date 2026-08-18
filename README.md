# dinner-harness

**한국어** | [English](README.en.md)

커스텀 Claude Code **및** Codex 하네스의 single source of truth.

**목적: 구독료 절감.** 고가의 Claude Max 대신 Claude Pro + Codex로 가되, 역할을 vendor에 맞춰 나눈다 — 저volume 설계·검토는 Claude(Architect), 토큰 무거운 구현은 Codex(Builder). token sink인 구현을 quota 여유가 큰 plan에 얹어 비용을 낮추는 게 핵심이다.

이 repo의 canonical 트리를 손-편집한다. **`~/.claude`·`~/.codex`를 직접 편집하지 말 것** — 둘 다 생성된 출력이다. 타깃은 installer로 재생성한다.

## 처음 사용하는 사람: 설치부터 첫 작업까지

이 하네스는 **Claude를 평소 대화 창으로 유지하면서**, 실제 구현 변경의 토큰은
Codex Builder에 쓰게 하는 Windows용 workflow다. 별도 Codex 터미널을 매번 열거나
`/delegate`를 외울 필요가 없다.

### 0. 준비물

- Windows PowerShell, Git, Python Launcher (`py -3`)
- Claude Code와 Codex CLI가 설치되어 있고 각각 로그인되어 있음
- 작업 대상이 Git repository임 (`git status`가 동작해야 함)

먼저 이 repository를 clone한 뒤, 그 폴더에서 다음을 실행한다. `refresh.py`는 Claude와
Codex 설치본을 한 번에 갱신하는 권장 진입점이다.

```powershell
py -3 check.py --no-install       # canonical source 자체 검사
py -3 refresh.py                  # 실제 쓰기 전 설치 계획 확인
py -3 refresh.py --apply          # ~/.claude 와 ~/.codex 에 실제 설치
py -3 check.py                    # 설치본까지 포함해 최종 대조
```

`--apply`는 실제 라이브 설치본을 바꾸며 backup을 만들지 않는다. 출력에서 오류가 나면
그 상태로 사용하지 말고 해결한 뒤 다시 실행한다.

### 1. 작업할 프로젝트에서 Claude 시작

PowerShell에서 **작업할 프로젝트 폴더**로 이동한 뒤 아래 명령으로 시작한다.

```powershell
cd C:\path\to\your-project
claude
```

일반 `claude`가 기본 Builder-first 진입점이다. 설치 뒤에도 동작하지 않으면
dinner-harness repository에서 `py -3 refresh.py --apply`를 다시 실행한다.

### 2. 평소처럼 요청한다

새 Claude 세션에서 모드 선언이나 `/delegate` 없이 일반 대화로 요청한다.

```text
인벤토리 화면에서 선택된 아이템의 이름과 등급을 표시해줘. 기존 UMG 스타일을 따른다.
```

Claude가 코드·문서 읽기, 검색, MCP 조사, 설계, HANDOFF 작성과 결과 검토를 맡고,
구현 파일의 structured `Edit`/`Write`는 Codex Builder가 맡는다. 즉 **Claude를 메인으로
쓰되 구현 token sink를 Codex에 둔다**는 것이 기본 UX다.

### 3. 사용자가 직접 결정하는 지점

- **LOW 단일 목적 변경**: 원래 요청이 시작 intent다. Claude가 최소 HANDOFF를 만들고
  Codex Builder를 자동 dispatch한 뒤 결과를 검토한다.
- **다파일·구조 변경·HIGH 작업**: Claude가 HANDOFF(필요하면 ADR)를 보여 주고 시작 승인을
  요청한다. 완료 후에도 merge/apply 전에 사람의 종단 승인을 받는다.
- **Git integration**: Builder는 사용자가 session 시작 전에 checkout해 둔 현재 branch의
  repository에서 변경한다. `commit` 또는 `commit and push`를 현재 대화에서 명시 승인한
  경우에만 Claude가 그 branch에 반영한다. 새 delivery branch를 만들지 않는다.

## Layout

- `content/` — tool-neutral 하네스 콘텐츠 (instructions, rules, skills, agents, roles,
  templates, ecc-reference, docs). codex adapter는 이를 transform하고, claude adapter는
  verbatim copy한다.
- `assets/claude/` — claude-native raw (Python hooks, launchers, settings template,
  손-작성 문서). verbatim copy되며 codex adapter는 무시한다.
- `assets/codex/` — codex-native raw (curated `AGENTS.md`).
- `adapters/` — 타깃별 renderer (`claude.py`, `codex.py`).
- `harness.toml` — manifest: targets, template 변수, copy / template(merge) / skip / exclude.
- `install.py` — CLI entry: `install --target claude|codex [--dest PATH] [--dry-run] [--allow-live]`.
- `refresh.py` — two-target refresh wrapper: preview by default; `--apply` is the explicit live-install signature.

## 설치/갱신 세부

```
py -3 install.py --target claude --dest C:/Users/<you>/.claude
py -3 install.py --target codex  --dest C:/Users/<you>/.codex
```

`--dest` 생략 시 `~/.<target>`이 기본값이며, 라이브 디렉터리에 쓰려면 `--allow-live`가 필요하다.
`--dry-run`으로 쓰기 없이 plan을 미리 본다.

두 target을 함께 갱신할 때는 아래 wrapper를 쓴다. 기본 실행은 source 정합 확인과 두 target의
dry-run만 수행하고, 실제 라이브 write는 사람이 명시적으로 `--apply`를 붙였을 때만 수행한다.

```
py -3 refresh.py
py -3 refresh.py --apply
```

> **`--apply`는 transaction이 아니며 backup도 만들지 않는다.** Claude 갱신 뒤 Codex 갱신이
> 실패하면 두 설치본 revision이 달라질 수 있다. 원하는 이전 commit을 checkout한 뒤 그 commit에서
> `refresh.py --apply`를 다시 실행해 복구한다.

- **claude** — inclusion set 전체의 verbatim copy. `settings.json`은
  `settings.json.template`에서 생성(`<USERNAME>` 치환, `_template` strip)되어 기존 파일과
  **merge**되므로 머신/runtime 키(예: `skipWorkflowUsageWarning`)가 보존된다.
  라이브 `HANDOFF.md` / `RESULT.md`는 절대 덮어쓰지 않는다(skip-if-exists).
- **codex** — portable subset을 Codex-native 경로로 transform: curated `AGENTS.md`,
  `skills/` 아래 18 portable skills, reference 디렉터리(`ecc-reference/`, `docs/`, `templates/`),
  그리고 adapter v2(Cycle 3, Codex 0.141)부터 **agents 13개 → `agents/*.toml` 변환 + hooks native 포팅**
   (`hooks/` 복사 + `hooks.json` 자동 생성 — 단 Codex에선 advisory: hard block은 sandbox/approval 레이어).
   Claude 전용 `route_nudge`는 standalone Codex가 자신을 Codex Builder로 dispatch할 수 없으므로 `hooks.json`에서 의도적으로 제외한다.
  여전히 드롭: `_mode`의 file-glob 자동 inject(Codex 대응 기제 없음 → 모드 명시 선언으로 진입)와
  Claude-machinery skills 8종(routing 별칭 5 + harness 전용 2 + 다중 judge 1). **Two-CLI 역할(roles)은
  AGENTS.md §8로 cross-vendor curate된다**(양방향 — 아래 "Two-CLI 협업" 참조). 상세 = `CODEX-RECON.md`·`CODEX-COVERAGE.md`.

## Targets

- **claude** — implemented & live: repo가 `~/.claude`의 source of truth다. inclusion set이
  byte-identical로 round-trip된다(diff-0 증명).
- **codex** — implemented & live: `~/.codex`에 비파괴 배포됨(runtime 보존).

codex feasibility 분석(build vs adopt)은 `CODEX-RECON.md`, 콘텐츠별 native/degraded/dropped
회계는 `CODEX-COVERAGE.md` 참조.

## Two-CLI 협업 (cross-vendor)

큰 작업은 **Architect**(설계·검토)와 **Builder**(구현) 두 역할로 나눈다. "Two-CLI"는 인터랙티브 터미널 둘이
아니라 **두 역할·두 CLI 엔진**(Claude·Codex)을 뜻한다. 두 역할은 vendor-neutral하며 Codex·Claude 어느 쪽이든
어느 역할이든 맡는다. **기본은 Claude=Architect / Codex=Builder** (역방향도 가능) — token sink인 Builder를
quota 여유 큰 plan(Codex)에, 저volume Architect를 Claude Pro에 두는 배치.

운용 모드 셋(통신은 어느 쪽이든 프로젝트 루트의 `HANDOFF.md`·`RESULT.md`·`INPUT.md` — IPC/MCP 불필요한 버스):
- **orchestrated single-pane (기본)** — 인터랙티브 Claude 한 세션이 HANDOFF 승인 후 `orchestrate.py build`로
  Codex Builder를 headless 자동 dispatch(**별도 Codex 터미널 안 엶**), RESULT를 같은 세션이 리뷰.
- **manual dual-session** — 사람이 양쪽 인터랙티브 세션을 열고 버스로 courier(역방향·동일 vendor·fallback).
- **fully headless** — `orchestrate.py run`이 양쪽을 headless 구동.

- **Claude**: `content/roles/ROLE_{ARCHITECT,BUILDER}.md` + `rules/_mode/`(통신 파일 paths 매칭 시 자동 inject).
- **Codex**: 동일 프로토콜을 `assets/codex/AGENTS.md` §8로 curate. Codex엔 paths 자동 inject가 없어 모드는
  **명시 선언**("architect/builder 모드")으로 진입한다.

파일 기반이라 Codex 0.111+에서 동작하며, Architect의 옵션 서브에이전트 위임만 0.140+를 쓴다. 상세 규약은
`content/instructions/CLAUDE.md` §2 참조.

## 일상 사용법

### 1) 기본 세션에서 실제로 일어나는 일

일반 `claude`로 시작한 Claude 세션은 다음 표처럼 동작한다. **읽기 비용까지 Codex에 넘기는
모드는 아직 의도적으로 넣지 않았다**. 먼저 이 흐름을 써 보고, 큰 코드 탐색의 Claude token
비용이 실제 문제인지 확인한 뒤 별도 read-only Scout lane을 검토한다.

| 요청 유형 | Claude의 역할 | Codex Builder 사용 | 사용자 행동 |
| --- | --- | --- | --- |
| 질문, 코드 Read, 검색, MCP 조사, 설계, 리뷰 | 직접 수행 | 아니오 | 평소처럼 질문 |
| 한 파일 한두 줄을 포함한 구현 파일 수정 | 범위 파악·HANDOFF·결과 리뷰 | 트리비얼 `Edit`(단일 파일·old/new 각 2줄 이하·비인프라 경로)은 아니오, 그 외는 예 | 평소처럼 요청 |
| 명확한 LOW 단일 목적 변경 | `HANDOFF_DELEGATE.md` 작성·리뷰 | 예, 같은 세션에서 자동 dispatch | 추가 명령 불필요 |
| 다파일, build/test iterate, 구조 변경, HIGH 신호 | 설계·HANDOFF/ADR·리뷰 | 예, 승인 뒤 자동 dispatch | 시작/종단 승인 |

엔진(Unreal/Unity) 신호가 있는 구현 요청은 위 표의 HANDOFF 작성 전에 해당 엔진 허브(`unreal-specialist`/`unity-specialist` 또는 `/ue`·`/umg`·`/gas`·`/repl`·`/bp`) consult가 필수다. read-only 질문과 실제 1~2줄 변경은 면제되며, 상세는 ADR-0010에 정리되어 있다.

architect 경로로 판정된 도메인 작업(코드 리뷰·설계·C++ 빌드·게임플레이/네트워크/UI/툴/성능 구현 등, 표의 세 번째·네 번째 행에 해당하는 규모)도 `_core`/`_gamedev` agent consult가 필요하며, 이 규칙은 ADR-0011에 정리되어 있다.

`builder_guard`는 Claude의 structured `Edit`/`Write` 구현 변경을 막고 Builder 경로를
안내한다. 단, ADR-0012의 trivial-edit fast path에 따라 `Edit`이면서 대상이 단일 파일이고
`old_string`과 `new_string`이 각각 2줄 이하이며 하네스 인프라(`assets/claude/hooks/`,
`settings*.json`, `harness.toml`, `orchestrator/`, `orchestrate.py`)나 live `~/.claude` install
경로(`projects/*/memory/*.md` 제외)가 아닌 경우에는 Claude가 직접 처리한다. `Write`·
`apply_patch`·여러 줄/여러 파일·인프라 경로 변경은 계속 Builder 전용이다. 이는 workflow
guard이지 보안 sandbox가 아니다. Bash/PowerShell을 해석해서
모든 쓰기를 막지는 않으므로, shell로 guard를 우회하는 사용은 이 UX의 범위 밖이다.

### 2) 작업 결과를 확인하고 반영하기

Builder는 원본 project tree에서 작업한다. dispatch 전 baseline commit으로 tree를 clean하게
두고, ADR-0007의 snapshot delta가 Builder turn의 변경만 판정한다. Claude는 다음 순서로
검토해야 한다.

1. `RESULT.md`에서 완료 gate, 변경 파일, 검증 결과와 미해결 이슈를 읽는다.
2. 원본 repository의 `git diff`와 실제 파일을 확인한다.
3. 요구사항·스코프·검증이 맞는지 판단한다.
4. 통과한 변경을 사용자가 선택한 primary branch로 integration한다. 사용자가 이 대화에서
   `commit` 또는 `commit and push`를 명시 승인한 경우에만 agent가 정확한 파일을 그 branch에
   stage·commit/push한다. task 완료만으로 push하지 않으며, 새 delivery branch·force-push·merge는
   별도 지시가 필요하다.

`BLOCKED`가 나오면 성공으로 취급하지 않는다. Claude가 제시한 reason, `RESULT.md`, Builder
repository의 diff를 보고 범위·HANDOFF·인증·검증 오류를 고친 뒤 새 dispatch를 결정한다.

### 3) 언제 Claude 직접 수정을 쓰는가

평소에는 일반 `claude`를 쓴다. 직접 수정이 정말 필요할 때만 아래 explicit escape를 쓴다.

```powershell
& "$env:USERPROFILE\.claude\claude-direct.cmd"
```

이 escape는 그 Claude process에만 `DINNER_EXECUTION_MODE=direct`를 설정한다. 따라서
`builder_guard`가 비활성화되고 strict token boundary는 보장되지 않는다. 기존 `dh.cmd`와
`dh-architect.cmd`는 호환용 Builder-first launcher로 남지만 더 이상 일상 진입점이 아니다.

### 4) orchestrator 직접 호출 (고급·선택)

일상 사용에서는 이 명령을 직접 실행하지 않는다. strict Claude 세션이 HANDOFF, baseline
commit, dispatch, 결과 검토를 순서대로 처리한다. 아래는 승인된 HANDOFF가 있는 원본
repository에서 쓰는 진단·수동 fallback용이다.

```powershell
# 원본 repository에서 Builder만 1회 실행
py -3 "$env:USERPROFILE\.claude\orchestrate.py" build --repo . --backend real

# Architect·Builder 양쪽 완전 headless (사람은 경계에만)
py -3 "$env:USERPROFILE\.claude\orchestrate.py" run --goal "..." --backend real --repo .

# CLI 없이 오프라인 스모크
py -3 "$env:USERPROFILE\.claude\orchestrate.py" build --repo . --backend mock
```

### 5) 수동 dual-session (fallback·역방향 페어링)

한 세션에서 `architect 모드`로 `HANDOFF.md`를 쓰고, **다른 세션(예: Codex 터미널)**에서 `builder 모드`로
그 HANDOFF를 실행한 뒤 `RESULT.md`로 돌려준다. 통신은 프로젝트 루트의 버스 파일.

### 6) 하네스 자체를 수정하거나 다른 PC에서 갱신할 때

`~/.claude`·`~/.codex`를 직접 고치지 말고 — repo의 canonical 트리(`content/`·`assets/`)를 편집 →
`py -3 refresh.py`로 plan을 확인 → 사람이 `py -3 refresh.py --apply`로 Claude·Codex를 함께 재생성한다.

Git 변경을 받은 뒤에는 `py -3 refresh.py`로 plan을 확인하고 `py -3 refresh.py --apply`로
두 설치본을 함께 갱신한다. 끝난 뒤 `py -3 check.py`를 실행한다. 이 검사는 repo와 라이브
설치본의 drift까지 잡아 "고쳤는데 설치를 안 했다"를 알려 준다. 설치본을 안 보려면
`--no-install`을 붙인다.

> **되돌리기는 install 전에 준비해라.** `install.py`는 제자리에 덮어쓰고 **백업을 남기지 않는다** — 유일한
> undo는 이전 커밋에서 다시 설치하는 것이다:
> `git stash && py -3 install.py --target claude --allow-live && git stash pop`
> (또는 이전 커밋을 checkout해서 거기서 install). `hooks/lib/common.py`는 **모든** 핸들러가 import하므로
> 그 파일이 깨진 사본으로 덮이면 인터랙티브 hook 전체가 한 번에 죽는다. 상세는 `orchestrator/README.md`.

## 하네스 구성 (capabilities)

이 하네스가 보유한 skills·agents·hooks. _frontmatter 파생 snapshot — skill/agent 변경 시 갱신 필요._ codex 타깃에서 어느 항목이 native/degraded/dropped인지는 `CODEX-COVERAGE.md` 참조.

### Skills (29)

**메타원칙 (5)**
- `simplicity-first` — 최소 코드만, 과설계·추측 기반 유연성 방지
- `surgical-changes` — 요청 범위 밖 수정·무관 리팩토링 차단 (라이브 서비스 핵심)
- `think-before-coding` — 코딩 전 가정 명시·옵션 제시·질문
- `goal-driven-execution` — 모호한 작업을 검증 가능한 목표로 변환
- `search-first` — 코드 작성 전 기존 구현·라이브러리 검색·채택

**컨텍스트·검증 (7)**
- `verification-loop` — 세션 변경 검증 시스템
- `eval-harness` — eval-driven development 평가 프레임워크
- `strategic-compact` — 논리적 구간에서 수동 context compaction 제안
- `iterative-retrieval` — 컨텍스트 점진 정제 (subagent context 문제)
- `scope-check` — 원 계획 대비 scope creep 감사·정량화
- `perf-profile` — 병목 분석·예산 대비 측정·최적화 우선순위
- `tech-debt` — 기술 부채 추적·분류·상환 스케줄

**워크플로 (8)**
- `delegate` — LOW·단일목적 작업을 Codex Builder에 headless dispatch + 인라인 리뷰 (full ceremony 없이)
- `cli-update` — 설치된 Claude Code CLI/Codex CLI 버전을 최신 릴리스와 비교하고, 업데이트가 있으면 자동 적용
- `changelog` — git 커밋에서 changelog 자동 생성 (내부 + 플레이어용)
- `hotfix` — 긴급 수정 워크플로 (심각도·롤백 플랜·감사 추적)
- `codebase-onboarding` — 낯선 코드베이스 분석·온보딩 가이드 (엔진 인식)
- `arch-review` — 아키텍처·품질 코드 리뷰 (SOLID·테스트 가능성·성능)
- `learnings-review` — `learning_log` 포착 반복 실패를 CLAUDE.md/메모리로 승격
- `walkthrough` — 최근 변경/지정 범위를 코드 투어로 안내 (구조·흐름·설계 의도 + 인출 질문)

**UE 라우팅 (6)**
- `ue` — 멀티 서브시스템 Unreal 작업을 `unreal-specialist` 허브로 라우팅
- `bp` — Blueprint 작업을 허브 + `docs/specialists/ue-blueprint.md` 포커스로 라우팅
- `gas` — GAS 작업을 허브 + `docs/specialists/ue-gas.md` 포커스로 라우팅
- `umg` — UMG/CommonUI 작업을 허브 + `docs/specialists/ue-umg.md` 포커스로 라우팅
- `repl` — replication/netcode 작업을 허브 + `docs/specialists/ue-replication.md` 포커스로 라우팅
- `ue-umg-review` — UMG 위젯 리뷰·설계 (UE5)

**자율 루프 (2)**
- `autonomous-loop` — risk-tier 자율 자기수정 루프 (사람은 시작·종단만, 중간은 agent)
- `adversarial-review` — default-to-reject 다중 judge 패널 (HIGH tier 필수)

**harness (1)**
- `harness-review` — dinner-harness repo 자체를 wiring·conformance 두 렌즈로 리뷰

### Agents (13)

**_core (6)**
- `architect` — 시스템 설계·확장성·기술 결정
- `code-reviewer` — 코드 품질·보안·유지보수성 리뷰
- `cpp-build-resolver` — C++ 빌드·CMake·링커·템플릿 에러 해결 (최소 변경)
- `cpp-reviewer` — C++ 메모리 안전·모던 idiom·동시성·성능 리뷰
- `planner` — 복잡 기능·리팩토링 계획
- `tdd-guide` — 테스트 우선 방법론 (80%+ 커버리지)

**_gamedev (5)**
- `gameplay-programmer` — 게임 메커닉·전투·플레이어 시스템 구현
- `network-programmer` — 멀티플레이어 netcode·lag 보상·매치메이킹
- `performance-analyst` — 성능 프로파일링·병목·최적화 전략
- `tools-programmer` — 에디터 확장·콘텐츠 도구·파이프라인 자동화
- `ui-programmer` — 메뉴·HUD·인벤토리·UI 위젯 구현

**_ue (1)**
- `unreal-specialist` — UE5 단일 엔진 agent (GAS·BP·UMG·replication 심화는 `docs/specialists/ue-*.md` 참조 문서를 Read해 소비 — 2026-07-02 leaf agent 축소)

**_unity (1)**
- `unity-specialist` — Unity 단일 엔진 agent (DOTS·shader·addressables·UI 심화는 `docs/specialists/unity-*.md` 참조 문서를 Read해 소비 — 2026-07-02 leaf agent 축소)

### Hooks (6)

상세 발화 흐름·운영 모드는 `assets/claude/README.md` + `assets/claude/hooks/README.md` 참조.

- `secret_scan` (PreToolUse) — 입력에서 시크릿·민감 파일경로 regex 검출 (enforce, 차단형)
- `scope_check` (PreToolUse) — cycle 스코프 밖 수정 + hook 인프라 보호 (dryrun, always-block 즉시 차단)
- `suggest_compact` (PreToolUse) — 도구 호출 누적 시 `/compact` 제안 (advisory)
- `learning_log` (PostToolUse) — Bash/PowerShell 실패 신호 포착 → `learnings-review`로 승격 (advisory)
- `route_nudge` (Claude UserPromptSubmit 전용) — 구현 작업은 HANDOFF 작성 전 허브 consult가 필수임을 안내(read-only 질문과 실제 1~2줄 변경은 면제). 프롬프트의 UE 도메인 신호를 검출해 라우팅 nudge를 주입한다: 단일 도메인은 `/alias`(허브+포커스 문서), 멀티 도메인은 architect 모드+dispatch 제안 (advisory). standalone Codex가 self-dispatch할 수 없으므로 Codex `hooks.json`에서는 의도적으로 제외한다.
- `builder_guard` (PreToolUse) — 일반 `claude`에서 직접 structured code edit을 막고 Codex Builder dispatch로 유도; `claude-direct.cmd` escape에서만 inert
