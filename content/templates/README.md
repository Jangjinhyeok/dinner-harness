# templates/ — 프로젝트에 복사해 쓰는 템플릿

이 디렉토리는 `~/.claude/` 자체 동작엔 영향을 주지 않는다. **각 게임 프로젝트로 복사**해서, 이미 agent·skill이 참조하지만 비어 있던 컨벤션을 실제로 작동시키는 용도다. 복사 위치는 템플릿마다 다르다 — 대부분 `docs/`지만 `AGENTS.md`만 프로젝트 루트다(아래 표 참조).

## 무엇을 / 어디로

| 템플릿 | 복사 위치 (프로젝트) | 소비하는 agent/skill |
|---|---|---|
| `AGENTS.md` | `<프로젝트 루트>/AGENTS.md` (★ `docs/` 아님) | 외부 도구(Codex/Gemini CLI, Cursor 등) + Claude |
| `mcp.json` | `<프로젝트 루트>/.mcp.json` (★ 루트, dot-file) | 엔진 MCP 등록 — UE/Unity 에디터 제어 (Claude Code + 다른 CLI) |
| `engine-reference/unreal/VERSION.md` | `docs/engine-reference/unreal/VERSION.md` | `gameplay/ui/tools-programmer`의 "Engine Version Safety" |
| `engine-reference/unity/VERSION.md` | `docs/engine-reference/unity/VERSION.md` | (동일) |
| `architecture/ADR-template.md` | `docs/architecture/ADR-NNN-<slug>.md` | `architect`, `gameplay-programmer` ADR Compliance, `arch-review` |

> **`AGENTS.md`·`mcp.json`은 예외 — 프로젝트 루트에 둔다.** 나머지 템플릿은 `docs/`로 가지만, `AGENTS.md` 표준과 `.mcp.json`(project-scope MCP 설정)은 **작업 디렉터리 루트(및 상위)** 에서만 자동 발견되므로 루트에 둬야 한다.

## 왜 필요한가

`agents/_gamedev/{gameplay,ui,tools}-programmer.md`는 엔진 API를 제안하기 전 `docs/engine-reference/[engine]/VERSION.md`를 확인하도록 지시한다. 이 파일이 없으면 그 "Engine Version Safety" 단계가 조용히 no-op되고 낡은 training data로 fallback한다 (assistant 지식 컷오프 ~2026-01, 대략 UE 5.3 시점이라 그 이후 breaking change를 모른다). VERSION.md를 두면 핀된 버전·post-cutoff 위험 API를 agent가 ground truth로 삼는다 — "이 파일이 training data보다 우선".

ADR도 마찬가지다. `arch-review`·`architect`·`gameplay-programmer`가 `docs/architecture/` ADR을 참조하지만 컨벤션이 없으면 매번 "No ADR found"에 그친다. Two-CLI에서 Architect 세션이 ADR을 저작하고 Builder/specialist가 Implementation Guidelines를 그대로 따른다.

`AGENTS.md`는 다른 축이다. Codex/Gemini CLI 같은 **Claude 외 도구는 `CLAUDE.md`를 자동 로드하지 않고** project-root `AGENTS.md`만 읽는다. 이 템플릿은 그 도구들에게 `CLAUDE.md §1` 메타 원칙(가정 명시·최소 코드·외과적 수정·research-first·검증 목표)을 tool-neutral하게 inline 전달하고, 나머지는 `./CLAUDE.md`를 읽도록 지시한다 — 중복 없이 cross-tool 베이스라인만 깐다. Claude Code는 평소대로 `CLAUDE.md`를 쓰므로 영향이 없다(충돌 시 `CLAUDE.md` 우선).

`mcp.json`은 엔진 MCP(UE/Unity 에디터를 자연어로 제어) 등록을 프로젝트마다 copy-paste 수준으로 만드는 reference다. 아래 "엔진 MCP 등록" 절 참조.

## 엔진 MCP 등록 (UE / Unity)

엔진 MCP는 context7 같은 원격 서버와 달리 **2-파트 브릿지**다: MCP 서버 프로세스 ↔ 에디터 플러그인/패키지(TCP). 따라서 **에디터가 실행 중**이어야 하고, 엔진 측 플러그인 설치가 선행한다.

**Scope는 `project`다 (user 아님).** 엔진 MCP는 특정 프로젝트·켜져 있는 에디터에 묶인다. user scope에 넣으면 다른 모든 세션에서 죽은 tool이 뜬다. 그래서 게임 프로젝트 루트 `.mcp.json`(project scope, 해당 프로젝트 repo에 commit 가능)에 둔다. (context7는 반대로 항상-on 원격이라 user scope가 맞아 `~/.claude.json`에 있고, 이건 루트 README 설치 6번 참조.)

### 등록 2경로

1. **자동** — 에디터 플러그인 설치 후, 선택한 repo README의 명령을 그대로:
   ```
   claude mcp add --scope project unreal -- <서버 launcher> <args...>
   ```
   이게 프로젝트 루트 `.mcp.json`을 대신 써준다. (Unity의 CoplayDev는 에디터 안 **Auto-Configure** 버튼으로 이 단계를 대신함.)
2. **수동** — `templates/mcp.json`을 프로젝트 루트 `.mcp.json`으로 복사하고 `<FILL IN>`을 채운다. 안 쓰는 엔진 엔트리는 삭제.

### 권장 기본 서버 (2026-06 기준, 자주 바뀌니 repo README가 ground truth)

- **UE 5.7** → [remiphilippe/mcp-unreal](https://github.com/remiphilippe/mcp-unreal) (CLI 지향, headless 빌드·테스트, Blueprint 편집). 대안: [flopperam/unreal-engine-mcp](https://github.com/flopperam/unreal-engine-mcp)(5.5+, 50+ tools), [chongdashu/unreal-mcp](https://github.com/chongdashu/unreal-mcp)(범용).
- **Unity** → [CoplayDev/unity-mcp](https://github.com/CoplayDev/unity-mcp) (mainstream, Auto-Configure). 멀티-CLI(Codex 포함)면 [CoderGamester/mcp-unity](https://github.com/CoderGamester/mcp-unity).

> UE 5.7 + remiphilippe/mcp-unreal **구체 셋업 walkthrough**(에디터 플러그인 빌드·RC API·포트·`.mcp.json`·트러블슈팅)는 repo 루트 `MCP-UNREAL-SETUP.md` 참조.

### ⚠️ 주의 — hook이 못 막는 경로

엔진 MCP tool은 **에디터에서 임의 작업을 실행**한다(Blueprint 편집, C# 실행, 씬/액터 조작, 에셋 변경). 이는 `scope_check`·`secret_scan` hook이 가로채는 Claude의 Edit/Write/Bash가 **아니라** MCP 호출이므로 **hook 안전망 밖**이다(CLAUDE.md §5 라이브 서비스 원칙 직격). 메인 프로젝트엔 변경을 감독하며 적용하고, **테스트 프로젝트나 별도 브랜치에서 먼저** 검증한다. engine specialist agent(`ue-*`/`unity-*`)는 코드·설계 산출물 담당이고 MCP는 라이브 에디터 조작 — 역할을 분리해 쓴다.

## 사용법

1. 새 프로젝트 시작 시 해당 엔진의 `engine-reference/<engine>/`를 프로젝트 `docs/`로 복사하고 `<FILL IN>` 필드를 채운다. 예시 행(`<!-- example -->`)은 실제 항목으로 교체한다.
2. 설계 결정이 생기면 `architecture/ADR-template.md`를 `docs/architecture/ADR-001-<slug>.md`로 복사해 기록한다. 번호는 순차.
3. VERSION.md는 엔진 업그레이드 때마다 갱신한다. `Verified on` 날짜를 남긴다.
4. 엔진 MCP를 쓰는 프로젝트면 `mcp.json`을 루트 `.mcp.json`으로 복사해 등록한다 (위 "엔진 MCP 등록" 절).
