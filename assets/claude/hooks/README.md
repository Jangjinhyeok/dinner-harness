# Claude Code hooks (~/.claude/hooks/)

이 디렉터리는 Claude Code의 **PreToolUse·PostToolUse hook 안전망** 인프라를 담는다. hook은 Claude가 도구를 실행하기 *직전(PreToolUse)·직후(PostToolUse)*에 자동으로 끼어들어 검사하고, 종료 코드로 통과(exit 0)/차단(exit 2)을 결정한다(advisory hook은 차단 없이 stderr 제안·로깅만 한다). 사용자가 직접 호출하지 않는다.

## 한눈에

|  | `secret_scan` | `scope_check` | `suggest_compact` | `learning_log` | `route_nudge` |
|---|---|---|---|---|---|
| 이벤트 | PreToolUse | PreToolUse | PreToolUse | PostToolUse | UserPromptSubmit |
| matcher | Edit · Write · Bash · PowerShell | Edit · Write | Edit · Write | Bash · PowerShell | 없음 (전체 프롬프트) |
| 역할 | 입력에서 시크릿·민감 파일경로 검출 | hook 인프라 보호 + Builder 스코프 규율 | 도구 호출 누적 시 `/compact` 제안 | Bash 실패 신호(컴파일/링크/빌드 에러 등) 포착 → `learning_log.log` | 프롬프트의 UE 도메인 신호 검출 → 라우팅 nudge를 stdout으로 출력 (2026-07-02 재조준: 단일 도메인→`/alias`+포커스 문서, 멀티→architect 모드+dispatch 제안) |
| 룰셋 | `rules/secret_patterns.json` | `rules/scope_protect.json` + `HANDOFF.md`의 scope 블록 | 없음 (`COMPACT_THRESHOLD` env, 기본 50) | 없음 (핸들러 내장 패턴) | 없음 (핸들러 내장 regex) |
| 모드 env var | `CLAUDE_SECRET_SCAN_MODE` | `CLAUDE_SCOPE_WHITELIST_MODE` | 없음 (항상 advisory) | 없음 (항상 advisory) | 없음 (항상 advisory) |
| 현재 모드 | enforce (2026-05-31 승격, ADR-0001 Gate 4) | dryrun (영구 — always-block layer만 실차단) | advisory only — **차단 불가**(항상 exit 0) | advisory only — **차단 불가**(항상 exit 0) | advisory only — **차단 불가**(항상 exit 0) |
| 출처 | ADR-0001 | ADR-0005 | strategic-compact skill (ECC), 2026-06-01 | ADR-0004 / gap #4, 2026-06-01 | 2026-06-16, commit 09aa4f9 |

> **2026-06-01: "추가 hook 없음" 결정 번복** — 사용자 승인 하에 advisory-only hook `suggest_compact`를 도입(2026-05-24 운영 확정 → 갱신). **핸들러·런처는 `hooks/`에 배치됐고 `settings.json.template`·로컬 `settings.json`(개인 PC) 양쪽에 등록 완료다(always-block이라 hand-edit 또는 off ceremony로 추가).** 이 hook은 secret_scan/scope_check와 달리 룰셋·모드·차단이 없고 stderr로 `/compact`를 제안만 한다. 핸들러는 `strategic-compact` skill의 stderr-only 로직을 `run_handler` fail-open 계약으로 포팅한 것. 상세는 맨 아래 "결정 이력" 참조.

> **2026-06-01: `learning_log` (PostToolUse, advisory) 도입 — 예약돼 있던 ADR-0004 활성화.** Bash 도구 호출 후 출력에서 강한 실패 신호(컴파일 `error C\d{4}`·`LNK`·`CS`·`undefined reference`·build failed·traceback 등)만 골라 `log_event`로 `logs/learning_log.log`에 한 줄씩 포착한다. 차단 불가(항상 exit 0), 룰셋 없음(핸들러 내장 패턴, 노이즈 최소화). 포착물은 `learnings-review` skill이 클러스터링해 반복 항목을 CLAUDE.md 규칙/메모리로 **승격**한다(포착≠학습, 승격해야 학습). **off-ceremony 설치 완료(2026-06-01)** — 핸들러는 `hooks/handlers/learning_log.py`, 런처는 `hooks/launchers/learning_log.cmd`, 로컬 `settings.json`·`settings.json.template`의 `PostToolUse`에 등록됨(스모크 + 라이브 배선 검증 완료).

---

# 공통 인프라

네 hook은 발화 흐름·fail-open 계약·로그 구조를 공유한다 (차단형 `secret_scan`·`scope_check`은 `*_MODE` 모드 모델도 갖고, advisory형 `suggest_compact`·`learning_log`은 모드·차단이 없다). 새 hook을 추가하면 같은 인프라를 그대로 재사용한다.

## 디렉터리 구조

```
hooks/
├── launchers/   # 인자 없는 절대경로 BAT wrapper (settings.json이 부르는 진입점)
├── handlers/    # Python 핸들러 본체 (<name>.py)
├── lib/         # common.py — run_handler fail-open wrapper, log/exit 헬퍼
├── rules/       # 룰셋 JSON (secret_patterns / scope_protect)
├── tests/       # run_handler 안전 계약 unittest (stdlib only)
└── logs/        # JSON-lines 로그 (git·동기화 제외)
```

## 발화 흐름

`settings.json`의 `hooks.PreToolUse` 엔트리에 박힌 command를 Claude Code가 실행한다. 그 command는 **인자 없는 절대경로 BAT 한 줄**이다. 체인은 다음과 같다 (secret_scan 예시):

```
Claude가 Edit/Write/Bash 호출
  → settings.json: matcher 매칭 시 발화, 도구 호출 내용을 JSON으로 stdin에 전달
  → launchers/secret_scan.cmd          (인자 없는 절대경로 BAT)
  → py -3 handlers/secret_scan.py
  → run_handler(main, hook_name=...)   (fail-open wrapper)
  → main()  — stdin JSON 파싱 → tool_name 필터 → 룰셋 스캔 → 판정
```

`main()`은 `tool_name`이 대상 도구가 아니면 즉시 `exit_allow()`, 맞으면 룰셋을 읽어 스캔한다. 매치가 없으면 `exit_allow()`, 있으면 모드에 따라 `exit_warn()` 또는 `exit_block()`을 호출한다. BAT는 `exit /b %ERRORLEVEL%`로 Python 종료 코드를 그대로 Claude Code에 돌려준다.

**종료 코드가 전부다**: `exit 0` → 도구 호출 진행, `exit 2` → 차단. 중간 단계(BAT·Python·wrapper)는 이 코드를 위로 전달하는 파이프일 뿐이다.

## 운영 모드 모델

각 hook은 자기 env var로 `off` / `dryrun` / `enforce` 셋 중 하나를 갖는다 (변수 미설정 또는 알 수 없는 값 → `dryrun`).

| 모드 | 매치 시 동작 |
|---|---|
| `dryrun` | `decision=warn` 로그 + stderr에 `[WARN] ...` 한 줄 + **exit 0** (통과). `[WARN]` prefix는 `exit_warn`이 자동 부착. |
| `enforce` | `decision=block` 로그 + stderr 한 줄 + **exit 2** (차단). |
| `off` | 전건 즉시 통과 (일시 비활성화용). |

**모드 env var는 새 세션부터 적용된다** — hook은 Claude Code 프로세스의 환경을 상속받으므로, 현재 세션 도중 변수를 바꿔도 무효다. (env var 외 변경의 반영 시점은 아래 "hot-reload 반영 시점" 참조.)

## Fail-open 안전망

"핸들러 버그가 사용자 작업을 막아선 안 된다"는 계약을 `lib/common.py`의 `run_handler()` wrapper가 강제한다. wrapper는 `main()`을 200ms `threading.Timer` 안에서 돌리며 `Exception`, `KeyboardInterrupt`, `SystemExit(코드 ≠ 2)`, timeout을 전부 잡는다. 잡힌 예외는 `<name>.error.log`에 traceback과 함께 기록된 뒤 exit 0으로 빠진다. 즉 핸들러 안에서 무슨 일이 나도 도구 호출은 통과한다. **exit 2가 Claude Code까지 전달되는 경로는 단 하나 — `main()`이 명시적으로 `exit_block()`(= `SystemExit(2)`)을 호출한 경우뿐이다.**

이 safety net은 Python 핸들러 영역에 한정된다. Python 도달 전 단계 — BAT 실행 실패, `py` launcher 부재, `settings.json` 파싱 오류, hook command argument escaping 결함 — 은 wrapper 사정거리 밖이다. 이쪽 문제는 hook이 아예 발화하지 않거나 Claude Code가 에러를 토하는 형태로 드러나며, 진단은 `claude --debug` 출력과 `settings.json`을 직접 확인하는 수밖에 없다.

## 로그

모든 로그는 `~/.claude/hooks/logs/`에 JSON-lines로 쌓인다 (git·동기화 제외).

| 파일 | 내용 |
|---|---|
| `<name>.log` | 정상 경로 — allow / warn / block 결정이 모두 여기. |
| `<name>.error.log` | fail-open이 잡은 예외만. traceback 포함. |
| `common.log` | wrapper 레벨 진단 (현재는 stdin JSON 파싱 실패 등 극히 일부). |
| `claude-debug.log` | `claude --debug` 실행 시 Claude Code가 떨궈주는 출력. hook 발화 자체가 의심될 때 1차로 본다. |

**진단 순서**: 먼저 `<name>.log` 최신 라인 → `error.log`에 신선한 traceback이 있으면 핸들러 버그 → `claude-debug.log`에 hook 자체가 안 보이면 Pre-Python 영역 문제.

---

# secret_scan (ADR-0001)

Edit/Write/Bash 입력을 regex로 훑어 AWS access key, GitHub PAT, Slack token, PEM block 같은 시크릿이나 `.env` / `.credentials` 류 파일 경로를 검출한다. 사용자가 무심코 시크릿이 박힌 파일을 만들거나 시크릿을 포함한 명령을 실행하기 전에 잡는 안전망이다.

## 잡는 패턴

검출 패턴의 단일 출처는 `rules/secret_patterns.json`이다. 최상위는 `version` 정수와 `content_patterns` / `path_patterns` 두 배열로 구성된다.

- `content_patterns` → Edit의 `new_string` / Write의 `content` / Bash의 `command` 전체 문자열에 매치.
- `path_patterns` → Edit·Write의 `file_path` 또는 Bash의 `command` 전체에 매치.

각 엔트리는 `name`·`regex`·`severity` 세 필드를 갖고, 첫 매치가 곧바로 반환된다. Bash command는 shell tokenize 없이 명령 전체 문자열에 naive하게 regex를 거는 것이 v1 정책이다 (heredoc/pipe/redirection 분해 없음).

**패턴 추가**는 해당 JSON에 한 줄을 더하는 일이다. regex는 Python `re` 문법을 따르고 JSON 내부 이중 이스케이프에 주의한다. `severity`는 메타데이터로 로그에만 남으며 분기 로직은 쓰지 않는다.

## 현재 상태

**enforce로 운영 중** (2026-05-31 승격, ADR-0001 Gate 4). 1주 관찰에서 실사용 false-positive 0건을 확인한 뒤 `CLAUDE_SECRET_SCAN_MODE=enforce`로 전환했다 — 코드 변경 없는 env var 전환.

---

# scope_check (ADR-0005)

secret_scan과 동일한 인프라를 재사용하는 두 번째 hook. matcher는 `Edit|Write`로 `Bash`는 포함하지 않는다 — 파일 경로 기준 판정이 핵심이라 Bash command 파싱은 대상 밖이다. 목적은 Builder가 한 cycle에서 의도된 스코프 밖 파일을 수정하거나, cycle과 무관하게 보호돼야 할 인프라 파일을 건드리는 것을 막는 것이다.

## 2-layer 판정

- **always-block** (`rules/scope_protect.json`): cycle과 무관하게 늘 보호하는 **hook-integrity 핵심 파일** 블랙리스트. `settings.json` / `settings.local.json`(hook 배선)과 `hooks/handlers/`·`hooks/lib/`·`hooks/launchers/`·`hooks/rules/`(hook 본체) **6 entries**. dryrun이어도 면제 없이 즉시 block(exit 2)이며 `~/.claude/` 경로 안에서만 적용된다.
  - *(36ab046 이전엔 `CLAUDE.md`·`HANDOFF.md`·`rules/_mode/`·`roles/ROLE_*.md`도 always-block이었으나 제외했다 — 자가-config·워크플로우 정의는 ceremony 없이 편집 가능하게 두고, 이들의 보호는 scope codeblock layer의 advisory 차원과 `builder.md` 구두 규약에만 의존한다.)*
- **scope codeblock** (`HANDOFF.md`의 첫 ` ```scope ` 블록): 그 cycle에서 Builder가 수정해도 되는 파일 화이트리스트. 블록이 없거나 비어 있으면 fail-open(allow)이라 ADR-0005 이전 cycle의 HANDOFF와도 호환된다.

두 layer가 충돌하면 **always-block이 우선**한다 — 화이트리스트에 있어도 always-block에 걸리면 막힌다. 유일한 escape는 `off` 모드(아래 ceremony).

## 모드별 동작과 off ceremony

공통 모드 모델(위)에 더해, scope_check만의 핵심은 **always-block은 dryrun에서도 차단**된다는 점이다.

- `dryrun` (현재, 영구): scope codeblock 위반 → warn + exit 0. **always-block 매치 → block + exit 2** (dryrun 면제). 그 외 allow.
- `enforce`: scope codeblock 위반도 block + exit 2 (always-block은 동일).
- `off`: always-block 포함 전건 allow — 보호 인프라를 의도적으로 수정할 때 쓰는 **escape hatch**.

scope_check은 ad-hoc 편집 마찰이 커서 **dryrun을 영구 유지**한다 (enforce 승격 안 함). always-block layer만으로 hook-integrity 핵심 보호가 dryrun에서도 작동하기 때문이다.

**off ceremony** — `scope_protect.json`(prefix `hooks/rules/`), `settings.json`, `hooks/` 본체 같은 always-block 파일을 직접 손봐야 하는 cycle:

1. 새 세션 띄우기 전 `$env:CLAUDE_SCOPE_WHITELIST_MODE = "off"` 설정
2. `claude`를 새로 실행 → 인프라 수정 작업
3. 마치면 `Remove-Item Env:CLAUDE_SCOPE_WHITELIST_MODE`로 dryrun 복귀

`off`는 `scope_check`만 끈다. `secret_scan`은 별도 변수를 쓰므로 ceremony 중에도 시크릿 안전망은 살아 있다. (`HANDOFF.md`·`CLAUDE.md`·ROLE·`rules/_mode/`는 36ab046 이후 always-block이 아니므로 ceremony 없이 편집된다.)

## HANDOFF.md scope codeblock convention

ADR-0005 이후 모든 cycle의 HANDOFF.md는 첫 ` ```scope ` 펜스에 그 cycle에서 Builder가 수정할 파일 화이트리스트를 둔다. 이 블록에는 **반드시 `RESULT.md`를 포함**한다 — `RESULT.md`는 always-block이 아니므로(ADR-0005-followup), 이 scope codeblock 매치가 Builder의 RESULT.md 작성 통로다. 누락하면 dryrun에선 warn에 그치지만 enforce에선 RESULT.md 작성 자체가 block된다.

형식은 **한 줄에 패턴 하나**. `#` 주석 줄과 빈 줄은 skip. 패턴은 자동 분류된다 — `/`로 끝나면 prefix, `*` `?` `[` 가 있으면 glob, 그 외 exact. 절대경로면 그대로, 상대경로면 cwd(`~/.claude/`) 기준 해석.

> **저자(Architect) 주의**: 핸들러는 HANDOFF.md의 **첫 번째** ` ```scope ` 펜스를 operative 블록으로 잡는다. 본문에서 scope 형식을 *설명*하려고 ` ```scope ` 펜스를 다시 쓰면 그 설명용 예시가 operative로 오인된다. 설명용 예시는 4-space indent code block으로 쓰고, 진짜 operative 블록은 문서 끝(관례상 Section A)에 펜스 하나만 둔다.

---

# hot-reload 반영 시점

"새 세션 필요"는 **모드 env var에 한해서만** 맞다. 변경 종류에 따라 반영 시점이 갈린다.

| 변경 | 반영 시점 |
|---|---|
| (a) `settings.json`의 hook 엔트리 추가/제거 | **즉시 hot-reload** (ADR-0005 Gate 3에서 등록 직후 같은 세션 발화 실측) |
| (b) rule 파일(`rules/*.json`) · HANDOFF.md scope codeblock | 핸들러가 **호출마다 재독** → 다음 도구 호출부터 반영 |
| (c) 모드 env var (`CLAUDE_*_MODE`) | 프로세스 환경 상속이라 **새 세션 필요** |

ADR-0001 시기의 "새 세션 필요" 가정은 (c)에만 유효하고, (a)·(b)는 즉시 반영이다.

---

# Windows 제약 — settings.json command는 BAT 절대경로만

`settings.json`의 hook command 필드에는 **인자 없는 절대경로 BAT 한 줄**만 들어가야 한다. 다음은 전부 금지:

- `cmd /c <something>`
- `powershell -Command ...` / `pwsh -c ...`
- `%USERPROFILE%`, `$env:USERPROFILE` 같은 변수 확장
- `&`, `|`, `<`, `>`, `^` 같은 shell metachar
- 인자가 붙은 호출 (예: `secret_scan.cmd arg1`)

복잡한 로직은 전부 BAT 내부에 격리한다. `launchers/secret_scan.cmd`가 표준 형태다.

이 제약의 이유는 **Claude Code 2.1.148 Windows 빌드의 hook command argument escaping 결함**이다 (Anthropic GitHub Issue #11544와 동일 패턴). 위 금지 형태들은 인자 escaping 단계에서 깨져 hook이 정상 발화하지 않거나 엉뚱한 명령으로 실행된다. ADR-0001의 8-cycle 디버깅 끝에 가설 15에서 확정됐다. 구체 증거는 `~/.claude/HANDOFF.md` Section A와 `~/.claude/bug-report-evidence/`에 있다.

---

# 운영 작업

**활성화 / 비활성화.** `settings.json`의 `hooks.PreToolUse`/`hooks.PostToolUse` 엔트리를 추가/제거한다. 일시적으로 끄려면 엔트리를 통째로 빼는 게 깔끔하다 (JSON은 주석 미지원 → 백업 후 삭제). 일시 비활성화만 원하면 env var `*_MODE=off`가 더 가볍다.

**모드 전환.** env var를 `enforce`로 잡고 새 `claude` 세션을 띄운다. 현재 세션엔 적용되지 않는다. 되돌리려면 변수를 지우거나 다른 값으로 바꾼다.

**새 hook 추가.** 패턴은 두 기존 hook과 동일하다 — `launchers/<name>.cmd`에 세 줄 BAT (`@echo off` / `py -3 "%USERPROFILE%\.claude\hooks\handlers\<name>.py"` / `exit /b %ERRORLEVEL%`), `handlers/<name>.py`의 `main()` 정의 후 `__main__`에서 반드시 `run_handler(main, hook_name="<name>")` 경유, 필요 시 `rules/<name>_patterns.json`, 마지막으로 `settings.json`에 BAT 절대경로 등록. (현재 추가 계획은 없다 — "결정 이력" 참조. 향후 추가하게 되면 이 패턴을 따른다.)

**다른 머신 동기화.** 동기화 대상은 `hooks/{launchers,handlers,rules,lib}`와 상위 `~/.claude/`의 `skills/`·`agents/`·`CLAUDE.md`·`HANDOFF.md`다. `settings.json`은 절대경로가 박혀 machine-specific이라 신규 머신에서 새로 작성한다. `hooks/logs/`는 동기화 안 한다. `~/.claude` 자체가 GitHub repo이므로 home 머신에서는 pull/push로 옮긴다. **회사 PC에서는 `git`을 쓰지 않는다** — commit author email로 개인 정보가 노출될 위험이 있어 zip 추출/수동 복사로만 옮긴다.

---

# 결정 이력

위 구조의 근거는 **ADR-0001**이다. 핵심 가설(가설 15)은 Windows 빌드의 hook command argument escaping 결함이 모든 비정상 발화의 공통 원인이라는 것. "인자 없는 절대경로 BAT wrapper" 패턴이 그 회피책이고, fail-open `run_handler` wrapper와 분리된 `.error.log` 구조도 같은 cycle의 산물이다. 8-cycle 가설 진행과 증거는 `~/.claude/HANDOFF.md`와 `~/.claude/bug-report-evidence/`에 있다.

**운영 확정 (2026-05-24) → 부분 번복 (2026-06-01).** 2026-05-24에는 현 2개 PreToolUse hook(`secret_scan`, `scope_check`)으로 운영하며 추가 hook 계획이 없다고 확정했다(YAGNI — 두 안전망이 시크릿 누출·스코프 규율을 이미 덮음). 2026-06-01 사용자 승인 하에 이를 부분 번복하고 advisory-only hook `suggest_compact`를 도입하기로 했다. 이는 차단 hook이 아니라 stderr 제안 hook이라 안전망의 본래 취지(시크릿/스코프 enforce)와 충돌하지 않는다. **핸들러·런처는 `hooks/handlers/`·`hooks/launchers/`로 이동 완료, `settings.json.template`·로컬 `settings.json`(개인 PC)에 등록 완료(2026-06-01). `settings.json`은 always-block이라 활성화는 직접 hand-edit하거나 off ceremony(`CLAUDE_SCOPE_WHITELIST_MODE=off` 새 세션)로 했다 — 추가 즉시 hot-reload.** 차단형 hook(secret_scan/scope_check 계열)을 더 추가할 계획은 여전히 없다. `ADR-0004`(예약돼 있던 transcript/learning 기반 hook)는 2026-06-01 **활성화**됐다 — gap 분석 #4(반복 교정이 세션 사이 증발)에서 실제 마찰이 확인돼, 그 정책("마찰이 생기면 정의")에 따라 advisory PostToolUse 포착 hook `learning_log` + `learnings-review` 승격 skill로 정의했다(Tier B — homunculus 없이 실패 신호만 로깅, 사람이 승격). `ADR-0002`("차기 hook")는 여전히 미정의 placeholder로 보류. (`ADR-0003`은 번호 미사용.) 남은 단일 액션은 secret_scan enforce 승격 *결정*(~2026-05-31)뿐이며 이는 새 hook이 아니라 env var 전환이다.

**route_nudge 도입 (2026-06-16, commit 09aa4f9).** 첫 **UserPromptSubmit** hook이자 세 번째 advisory hook이다. 사용자 프롬프트에서 UE 도메인 신호(UMG/GAS/Replication/Blueprint 키워드 또는 generic UE 신호)를 regex로 검출해 stdout으로 routing nudge를 출력한다. 차단 불가(항상 exit 0), 룰셋 없음(핸들러 내장 regex). `rules/agent-routing.md`의 위임 의도를 결정 시점에 deterministic하게 reinforcement하되, trivial 작업에선 skip 지시를 함께 출력해 과잉 위임을 막는다(auto-delegation이 한 번도 발화 안 한 gap 대응). 핸들러 `hooks/handlers/route_nudge.py`, 런처 `hooks/launchers/route_nudge.cmd`, `settings.json.template`·로컬 `settings.json`(개인 PC)의 `UserPromptSubmit`에 등록 완료 — 회사 PC 등록도 이후 완료(2026-07-02 conformance 감사에서 회사 머신 발화 확인). 2026-07-02 재조준: leaf agent 강등에 맞춰 nudge 목표를 leaf 위임 → `/alias`(허브+`docs/specialists/` 포커스 문서)·heavy-work 시 architect 모드+Codex dispatch 제안으로 변경(배경은 `~/.claude/README.md` 변경 이력).

**scope_check 영구 dryrun 재확인 (2026-06-16, conformance 감사).** 회사·개인 PC 양쪽 실사용 감사가 scope_check를 "거의 전부 dryrun/자가테스트 → enforce 승격 or 일몰" 후보로 봤으나, 이는 always-block layer의 실차단 가치를 누락한 판단이다. always-block(`settings.json`·`hooks/` 본체)은 dryrun에서도 즉시 block(exit 2)이라 hook-integrity 보호는 이미 작동 중이고, scope codeblock enforce는 ad-hoc 편집 마찰만 키운다. 따라서 **영구 dryrun 유지**를 재확인한다(§"모드별 동작" 근거 불변).
