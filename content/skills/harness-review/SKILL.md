---
name: harness-review
description: "Review the dinner-harness repo — source-of-truth for the Claude Code / Codex harness (~/.claude and ~/.codex are generated outputs): content/ + assets/ (agents, skills, hooks, rules, roles, instructions, README) — through two lenses: (A) wiring integrity — overlap/duplication, dangling references, dormant parts, sunset candidates; (B) behavioral conformance — mine transcripts + hook logs to check whether the harness is actually used as designed (intent vs reality: routing actuation, mode usage, hook firing, dead weight). Proposes concrete fixes and applies the approved ones. Use when the user asks to review/audit the .claude config or harness — e.g. 'claude 구조 리뷰', 'harness 리뷰', '구조 점검', 'agent/skill 정합 확인', '실사용 정합 감사', 'conformance 감사', '의도대로 쓰이는지 확인', 'review my claude structure'."
argument-hint: "[mode: wiring|conformance|all] [area: agents|skills|hooks|rules|all]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash, Task, Edit, Write, AskUserQuestion
model: sonnet
origin: self
---

# Harness Review — Claude 구조 정합 점검

이 harness를 리뷰한다 — **source-of-truth는 dinner-harness repo**(`content/`·`assets/`)이고, `~/.claude`·`~/.codex`는 install로 생성된 output이다(거기 직접 적용한 수정은 다음 install에 덮인다). 코드가 아니라 harness 자신을 두 렌즈로 본다:

- **(A) 배선 (wiring)** — agent·skill·hook·rule·CLAUDE.md가 정적으로 제대로 연결됐는지: 중복·고아·휴면·dangling·일몰.
- **(B) 행동 정합 (conformance)** — transcript·hook log를 근거로 harness가 *설계 의도대로 실제 쓰이는지*: 라우팅 actuation, 모드 사용, hook 발화, 데드웨이트 (의도 vs 실사용).

진단에서 끝나지 않고 **수정 제안 → 승인 → 적용**까지 간다.

> `arch-review`(소스 코드 SOLID/품질)와 구분된다. 이건 harness 자신 전용이다.

## 대상 범위 · 모드

**렌즈 선택** (인자): `wiring`(배선 — default) | `conformance`(행동 정합) | `all`(둘 다). 인자에 모드가 없어도 '실사용/의도대로/conformance/감사' 뉘앙스면 conformance로 해석한다.

- **배선(wiring) 범위 (repo 기준)**: `content/agents/`, `content/skills/`, `assets/claude/hooks/`, `content/rules/`, `content/roles/`, `content/instructions/CLAUDE.md`, `assets/claude/README.md`, `assets/codex/AGENTS.md`, `content/templates/`. (`content/ecc-reference/`는 lookup-only.) `agents`|`skills`|`hooks`|`rules`로 좁힐 수 있다. *(비-repo flat install(`~/.claude`)을 직접 리뷰할 땐 같은 항목이 `~/.claude/agents/` 등 flat 경로에 있다 — 단 수정은 repo에서 하고 install로 전파.)*
- **행동 정합(conformance) 근거**: `projects/**/*.jsonl`(대화·tool_use 이력) + `hooks/logs/*`(hook 발화). 아래 '행동 정합 카탈로그' A~G 차원으로 본다.

## 작동 흐름 (5단계)

### Phase 1 — DIAGNOSE (heavy-read는 Explore에 위임)

대량 파일 읽기가 메인 컨텍스트를 오염시키지 않도록, **`Task`로 `Explore` subagent를 띄워** 아래 카탈로그를 실행시키고 **구조화된 findings 리포트만** 회수한다. (Explore는 read-only — 진단 전용.)

위임 프롬프트에 **해당 모드의 카탈로그**(`wiring`→배선 카탈로그, `conformance`→행동 정합 카탈로그, `all`→둘 다)와 대상 범위를 담는다. 인자로 범위가 좁혀졌으면 해당 항목만. conformance는 단순 사실 수집이 아니라 **의도 로드 → evidence 마이닝 → 판정**이라, 위임 프롬프트에 의도 소스와 판정 taxonomy도 함께 넘긴다.

### Phase 2 — PROPOSE

findings를 심각도(High/Med/Low)로 묶어 제시한다. **각 actionable 항목마다**:

- 파일/위치 (`path:line`)
- 현재 상태 (무엇이 문제인가)
- 제안 변경 (정확한 diff 또는 적용할 내용)
- 근거 (왜 — 어떤 정합 규칙·일몰 기준 위반인가)
- 위험도 / 영향 범위

그리고 **"자동 적용 가능" vs "수동 필요"**로 분리한다 (수동 = 아래 안전 규약의 always-block 파일).

### Phase 3 — APPROVE (게이트 — 승인 전 Edit/Write 금지)

`AskUserQuestion`(또는 명시 목록)으로 **어떤 항목을 적용할지** 사용자가 고르게 한다. 일괄 승인/부분 승인/전부 보류 모두 허용. **승인 전에는 어떤 파일도 수정하지 않는다.**

### Phase 4 — APPLY (repo에 적용 → install로 전파)

승인된 항목만 **repo의 canonical 트리**(`content/`·`assets/`)에 `Edit`/`Write`로 적용한다. **`~/.claude`·`~/.codex`를 직접 수정하지 않는다** — generated output이라 다음 install에 덮인다. repo 적용 후 `py -3 install.py --target claude|codex --allow-live`로 라이브에 전파한다(install은 copy-only). `surgical-changes` 원칙 — 승인 범위 밖 한 줄도 건드리지 않는다.

- **always-block 인프라 파일은 자동 수정 금지** (안전 규약 참조) → 적용하지 말고 "수동 적용용 정확한 내용/위치"를 출력.
- 적용 후 변경을 재확인 (해당 파일 re-read 대신 Edit 성공 여부로 판정).

### Phase 5 — REPORT

`리뷰 완료 — 적용 N건 / 수동 M건 / 보류 K건` 형식으로 보고. 마지막에 **sync 노트**(같은 내용이 여러 곳에 사는 항목은 앞으로 함께 고쳐야 함)와 다음 후보를 남긴다.

---

## 배선 카탈로그 (wiring mode)

Phase 1에서 Explore에 넘길 **정적 배선** 체크리스트. 각 항목에 탐지법을 명시했다.

1. **Skill-tool 배선** — `agents/**/*.md`의 `tools:`에 `Skill` 유무. 명시적 `tools:` 리스트에서 `Skill`이 빠지면 그 agent는 runtime skill 호출 불가.
   - 탐지: `tools:` 라인 grep → `Skill` 포함 여부.
   - ⚠️ **이건 "버그"가 아닐 수 있다.** 이 harness는 skill→agent(위에서 호출) 설계라 agent가 skill을 안 부르는 게 정상일 수 있다. **항상 "의도 확인 필요"로 분류**하고 자동 추가하지 말 것.

2. **`skills:` preload 정합** — agent frontmatter `skills:` 각 항목이 실존하는가 (`skills/<name>/SKILL.md`). 코드 작성 agent(_core 일부·_gamedev·_ue·_unity)에 메타 원칙(`simplicity-first`·`surgical-changes`)이 preload돼 있는가.
   - 탐지: `skills:` 항목 추출 → `skills/<name>/` 존재 확인. 누락 agent 목록화.

3. **`agent:` 바인딩 정합** — `skills/**/*.md`의 `agent:` 값이 실존 agent거나 빌트인(`Explore`/`Plan`/`general-purpose`)인가. 미설치 agent를 가리키면 dangling.
   - 탐지: skill `agent:` 추출 → `agents/**/<name>.md` 또는 빌트인 화이트리스트와 대조.

4. **skill↔agent 중복/미연결** — 주제가 특정 agent와 겹치는 skill이 그 agent에 preload돼 있지 않으면, 내용이 따로 자라며 어긋난다 (예: `ue-umg-review` ↔ `ue-umg-specialist`).
   - 탐지: skill 주제 ↔ agent 책임 범위 휴리스틱 매칭 → preload 누락 + 고유 항목 유출 표시.

5. **Dangling 참조** — skill·agent·rule 본문이 **미설치** 명령(`/eval` 등)·agent(director/lead tier 등)·skill·MCP tool을 가리키는가.
   - 탐지: 본문에서 `/명령`·agent 이름·MCP tool 패턴 grep → 실존 카탈로그와 대조.

6. **휴면 skill** — 한 번도 호출된 적 없는 skill. transcript에서 `"skill":"<name>"` 집계로 식별 (있으면).
   - 탐지: `projects/**/*.jsonl`에서 `"name":"Skill"` + `"skill":"…"` 추출 → 전체 skill 수 대비 0회 목록. (로컬 세션만 보임 — 한계 명시.)

7. **중복/sync 부채** — 같은 내용이 `CLAUDE.md` + skill 본문 + agent preload 등 2곳 이상에 사는가 (예: simplicity-first/surgical-changes는 3곳).
   - 탐지: 원칙 키워드 cross-grep → 다중 거주 항목. "고칠 때 함께 고칠 곳" 명시.

8. **Hook 무결성** — `settings.json`(또는 `.template`)에 등록된 hook이 `hooks/launchers/`·`hooks/handlers/`에 실제 파일로 존재하는가. matcher(Edit|Write|Bash|PowerShell)와 핸들러가 짝맞는가.
   - 탐지: settings의 hook command 경로 ↔ launchers/handlers 파일 존재 대조.

9. **일몰 대조** — README "Removal Criteria Table"의 제거·축소 신호와 현황을 대조해 축소 후보 표시 (자동 삭제 아님, 점검용 lookup).

---

## 행동 정합 카탈로그 (conformance mode)

Phase 1에서 Explore에 넘길 **실사용 행동** 체크리스트. "설계가 실제로 발화하는가"를 본다.

**선행 — 의도 로드**: `CLAUDE.md`(§1 원칙·§2 Two-CLI·§5·§6), `rules/agent-routing.md`, `README.md`(작동방식·일몰표), `hooks/README.md`, `roles/ROLE_*.md`를 읽어 "무엇이 일어나야 하는가"를 먼저 추출한다.

**Evidence 소스**: (1) `projects/**/*.jsonl` — tool_use 이력. (2) `hooks/logs/*` — hook 발화(transcript보다 hook 행동을 잘 드러냄).

**탐지 주의 (추측 금지)**:
- CC 버전마다 위임 tool 이름이 다르다 — `Task`인지 `Agent`인지 **실제 라인을 먼저 열어** 확인.
- skill 호출 = `"name":"Skill"` + input `skill`; agent = `Task`/`Agent` + `subagent_type`; 사용자 슬래시는 user 메시지에 `<command-name>`.
- **meta-prompt FP 주의**: 이 감사 프롬프트 자신이 specialist 이름을 텍스트로 언급해 `route_nudge`를 오발화시킨다(이 스킬을 conformance로 돌릴 때마다 관측됨). 이건 결함 evidence이지 위임 신호가 아니다.

**차원별 측정** — 각 항목: 설계 의도 / 관측 행동(수치 + 예시 path·session) / 판정 / 괴리 원인 + 최소 개선안.

- **A. 엔진 라우팅 actuation** — `unreal/unity-specialist`·`ue-*`·`unity-*` Agent 호출 수 / 실질 엔진 세션 중 인라인 처리 비율(위임 누락률) / `route_nudge.log` 발화 vs 후속 위임(순응률) / 슬래시 `/umg…` 사용. ⚠️ Two-CLI Builder 실행 중 위임 생략은 **정상**(`agent-routing.md` 예외) — 누락률에서 Builder 세션은 제외.
- **B. Two-CLI 모드** — "architect/builder 모드" 선언 수, `HANDOFF/RESULT/INPUT` read·write 세션 수, **그리고 `orchestrate.py build`(orchestrated single-pane auto-dispatch) 호출 수**. ⚠️ 기본 모드는 single-pane이라 Codex Builder가 headless로 돌고 "builder 모드" 선언이 안 찍힌다 — 모드 선언 수만 보면 실사용을 휴면으로 오판한다. dispatch 호출·HANDOFF/RESULT write까지 합산해 판정. 셋 다 0이면 `roles/`·`rules/_mode/`·orchestrator 휴면 신호.
- **C. self-review §6** — 4파일+ 변경 세션 중 `code-reviewer`/`cpp-reviewer` 후속 비율 + 인라인 "리뷰 완료, 이슈 N" 멘트 빈도.
- **D. search-first §1.5** — 비단순 신규구현 턴의 선행 검색 비율. 전용 채널(`context7`·`gh search`) vs generic web(`WebSearch`/`WebFetch`) 분리 — 전용이 0이면 ROI 미실현.
- **E. 메타원칙 preload** — `simplicity-first`·`surgical-changes` 등이 코드 agent에 preload됐나 + 그 agent가 실제 spawn되나(A와 연동: agent가 안 뜨면 preload는 dependency-dormant). Skill 명시 호출 0은 정상(preload 설계).
- **F. hooks 행동** (`hooks/logs`별) — `secret_scan`(block/warn·FP), `scope_check`(warn·always-block hit — dryrun은 의도), `suggest_compact`(발화 후 `/compact` 비율·카운터 리셋), `learning_log`(포착 신호 품질·노이즈·승격 여부), `route_nudge`(발화 vs 위임·FP·인코딩 크래시).
- **G. MCP-aware 분리** — 엔진 MCP 세션에서 specialist(text)/MCP(live) 분리 준수, read-before-write, write-MCP의 사용자 승인 흐름(휴리스틱).

**판정 taxonomy**: `actuated`(설계대로 발화) / `partial`(일부만) / `dormant`(설치됐으나 0 actuation) / `misused`(발화하나 의도와 어긋남).

**Cross-machine 원칙**: **실사용이 가장 두꺼운 머신**에서 돌려야 의미 있다 — meta(`.claude` 자가작업)만 쌓인 얇은 표본은 actuation을 못 본다(엔진작업 표본이 얇으면 라우팅 휴면이 안 보임 → 실 프로젝트 머신이라야 분모가 실재). 여러 머신 결과가 수렴하면 강한 신호. 회사 PC는 git 미사용 규약이라 거기선 진단·제안까지만, 적용은 개인 PC repo에서.

**한계 (정직성)**: 로컬·미rotate 세션만 보임(횟수는 하한값). "실질 작업인지"는 휴리스틱(도메인 명사 + 작업동사) — **'위임 불필요' vs '기회 부재'를 혼동하지 말 것**. 갓 도입된 부품은 과거 transcript로 효과 평가 불가(관측 기간 필요).

---

## 안전 규약 (scope_check / hooks 인지)

- **always-block 파일은 자동 수정 금지** — repo에선 `assets/claude/settings.json.template`·`assets/claude/hooks/handlers/*`·`assets/claude/hooks/launchers/*`(설치 시 `~/.claude`의 `settings.json`·`hooks/`로 감) 및 README가 always-block으로 지정한 인프라 파일. 이들은 Phase 4에서 Edit/Write하지 말고 **수동 적용 안내**로만 출력 (off-ceremony 필요 시 `assets/claude/hooks/README.md` 참조).
- `secret_scan`(enforce)·`scope_check`(dryrun)이 Edit/Write/Bash를 가로챈다. 적용 중 hook이 막으면 우회하지 말고 사용자에게 보고.
- 새 파일 생성·일반 콘텐츠 파일(`agents/*`, `skills/*`, `rules/*`, `CLAUDE.md`, `README.md`) 수정은 정상 경로.

## 출력 원칙

- 진단은 **사실 + 근거**로. "겹친다"가 아니라 "X와 Y가 ~% 겹치고 Z는 미연결"처럼 정량/구체.
- 제안은 **최소 변경**(simplicity-first). 큰 리팩토링은 권하지 말고 배선 수정에 집중.
- 무엇을 못 봤는지 정직히 명시 (예: 로컬에 없는 세션, 미인증 채널).
