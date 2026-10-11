# Claude subagent Computer Use 검증 프롬프트

아래 지시를 Claude 데스크톱 앱(Code 탭)의 **새 세션**에서 수행하라. 이전 결과는 참고 정보이며 현재 실행의 성공 증거로 재사용하지 마라.

## 사전 조건 (사람이 수행)

- Claude 데스크톱 앱 Settings → This computer → **Computer use**를 켠다(기본값 off).
- 설정 변경 후 새 세션을 연다. 이미 열린 세션에는 도구가 추가되지 않을 수 있다.
- 테스트 앱은 Windows 메모장(Notepad)으로 한다. 시작 전에 열려 있는 메모장 창이 있으면 사람이 저장·종료해 둔다.

## 목적과 범위

Main 세션을 유지하면서 Agent 도구로 호출한 Claude subagent(Child)가 다음 과정을 **직접** 수행할 수 있는지 검증하라.

앱 접근 승인 요청 → 화면 확인 → UI 조작 → 변경된 화면 확인 → Main에 결과 인계

이번 작업은 기능 검증이다. 하네스 소스·routing·설치 설정·agent 정의를 변경하지 마라. commit·push도 하지 마라.

핵심 불확실성은 **Child의 `request_access` 승인 요청이 사람에게 정상적으로 표시되는가**이다. Codex에서는 이 단계가 "root thread 전용 elicitation" 제한으로 차단됐다(아래 참고 절).

## Main의 사전 확인

- Main이 먼저 ToolSearch `{ query: "computer", max_results: 40 }`로 `mcp__computer-use__*` 도구가 이 세션에 있는지 확인하라. 없으면 사전 조건 미충족으로 보고하고 중단하라. Main이 직접 computer use를 실행해 보지 마라.
- 적용되는 autonomy·agent-routing 정책에 따라 짧게 Risk·검증 기준·수용 조건을 알리라. 이 작업은 사람의 데스크톱을 조작하므로 범위를 아래 UI 작업으로 한정한다.

## Child 호출

- Agent 도구로 `subagent_type: "general-purpose"`를 호출하라. 이 타입은 `tools` 목록이 명시되지 않아 Main의 MCP 도구를 상속한다(2026-10-11 probe: 내장 브라우저 MCP 상속·호출 성공 확인).
- harness의 이름 있는 agent(`tools-programmer` 등)는 frontmatter에 `tools`가 명시돼 MCP 도구와 ToolSearch가 없다(2026-10-11 probe 확인). 이번 검증에 쓰지 마라. 이름 있는 역할에 위임하려면 agent 정의 변경이 필요하며 그것은 이 검증의 결과를 본 뒤 별도로 결정한다.
- **`run_in_background: false`(foreground)로 호출하라.** 승인 창·권한 프롬프트가 사람에게 표시될 수 있게 하기 위함이다. background 호출 결과와 섞지 마라.
- model을 override하지 마라. 실행 모델은 기록으로 확인한다.

## Child의 도구 접근 확인

Child가 직접 다음을 확인하도록 하라.

- `mcp__computer-use__*` 도구가 Child에게 보이는지(로드됨 / ToolSearch로 로드 가능 / 없음)
- `anthropic-skills:computer-use` 스킬 지침을 읽었는지
- `request_access`로 Notepad 접근을 요청했을 때의 결과(승인 창 표시 여부, 응답, 부여된 tier)

도구 목록에 이름이 있는 것과 호출 성공을 구분하라. 없는 도구를 추정하거나 Main의 연결을 복사하지 마라. 권한·승인 정책을 완화하지 마라. 승인 창이 뜨면 사람이 직접 승인한다. 사람이 승인 창을 처리한 것은 Main이 대신 조작한 것이 아니다.

## 작은 UI 작업

Child가 Notepad의 **새 빈 문서**에서 다음을 수행한다.

1. `request_access`로 Notepad 접근을 받는다. 필요하면 `open_application`으로 연다.
2. Child가 직접 screenshot으로 최초 화면을 확인한다.
3. 테스트 식별 문자열 `CU-VERIFY-20261011-alpha`를 입력한다.
4. `alpha`를 선택해 `beta`로 수정한다.
5. Child가 다시 screenshot으로 확인하고 최종 문자열 `CU-VERIFY-20261011-beta`와 대조한다.
6. 문서를 **저장하지 않고** 닫는다(저장 확인 창에서 "저장 안 함"). 자신이 연 창만 닫고 기존 사용자 창은 건드리지 않는다.

기존 문서·UE 에셋·프로젝트 설정 수정, 파일 저장, 외부 전송·게시·구매는 금지한다.

Main은 같은 화면을 동시에 조작하거나 클릭 좌표를 판단해 전달하지 마라. Main이 대신 UI 작업을 하고 Child가 설명만 하면 성공이 아니다. Bash·PowerShell·파일 쓰기·다른 UI 자동화로 결과를 만들어 Computer Use 성공처럼 보고하지 마라. Main이 최종 화면을 확인했다면 Child 수행과 따로 기록하라.

## 실행 주체·모델 증거

가능한 로컬 기록에서 다음을 대조하라. Claude Code transcript는 `~/.claude/projects/<프로젝트 slug>/` 아래 세션 JSONL과 subagent JSONL에 있다. 정확한 경로·필드는 현재 CLI 버전에서 확인하라.

- Main 세션 ID와 Child(subagent) transcript의 관계
- 호출한 `subagent_type`과 model override 여부
- Child transcript에 기록된 assistant 메시지의 `model` 값
- `request_access`·`screenshot`·입력·선택·수정 호출이 Child transcript에 있는지와 각 결과
- 정리(저장 안 함 종료)의 실제 결과

역할 이름이나 Child의 자기 보고만으로 실행 주체·모델을 확정하지 마라. 기록을 읽을 수 없다면 "요청 모델 확인 / 실제 실행 모델 확인 불가"라고 표시하라. 서버 내부 실행·과금까지 검증했다고 표현하지 마라.

## 실패 처리

다음 원인을 구분하라.

- Main 세션에 computer use 도구 없음(사전 조건 미충족)
- Child에 computer use 도구가 상속되지 않음
- Child의 `request_access`가 오류로 실패(승인 창이 Main/root에서만 가능한 제한 등)
- 승인 창은 떴으나 사람이 거부했거나 시간 초과
- tier 제한으로 조작 차단(Notepad가 "full"이 아닌 경우)
- 화면 조회만 가능하고 조작 불가
- Main이 대신 실행해야만 완료됨
- 기록 부족으로 실행 주체·모델 확인 불가

구체적인 일시 오류를 해결할 근거가 있을 때만 제한적으로 재시도하라. 승인이 차단되면 같은 요청을 반복하거나 다른 앱으로 우회하지 마라. Main이 `request_access`를 대신 받아 Child가 이어서 조작할 수 있는지는 **별도의 두 번째 시험**으로만 수행하고, 첫 시험 결과와 분리해 기록하라.

## 이전 실험 참고: Codex, 2026-09-23

이 내용은 Codex Desktop에서의 당시 결과이며 Claude의 현재 상태로 단정하지 마라.

- 기존 `tools-programmer`를 model override 없이 호출했다. Parent는 `gpt-6-astra / medium`, Child 고유 turn은 `gpt-6-sol / medium`으로 로컬 기록에서 확인됐다.
- Child는 `computer-use` 스킬과 guidance/api/confirmations 문서를 읽었고, `mcp__node_repl__js`에서 `@oai/sky` 초기화와 `sky.list_apps()` 호출에 성공했다.
- Word의 `sky.launch_app`와 Chrome의 `sky.get_window`/`sky.get_window_state` 호출은 아래 오류로 차단됐다(Chrome은 한 cell에서 실행돼 정확한 차단 단계는 미확정).

```text
MCP elicitation request failed: Mcp error: -32603: MCP server elicitations can only be requested by the root thread. Ask the parent agent to handle this request. Do not retry the blocked action until the parent confirms the blocker is resolved.
```

- screenshot·텍스트 입력·수정·사후 확인은 미수행이었다. 생성한 임시 문서와 Main의 대리 UI 조작은 없었다.
- 결론은 "차단"이었다. 도구 미제공이나 모델 오류가 아니라 Child의 root 전용 MCP elicitation 처리 제한이었다. 정상 root 승인 인계 후 Child가 직접 계속할 수 있는지는 미검증이었다.
- 당시 증거 식별자: Parent `01a0cdb7-24d4-7db2-b6ae-27384bd83740`, Child `01a0cdb7-dce8-7e03-a52a-2a768fbe13cb`, Child 고유 turn `01a0cdb7-de04-7d91-a8f2-3a2415e785ac`, 기록 `C:\Users\zero9\.codex\sessions\2026\09\23\rollout-2026-09-23T19-02-54-01a0cdb7-dce8-7e03-a52a-2a768fbe13cb.jsonl`.

## 이전 확인 참고: Claude, 2026-10-11

- 당시 세션에는 `mcp__computer-use__*`와 `enable__` 도구가 없었다(Computer use 설정 off로 추정). 실제 화면 조작은 미검증.
- `general-purpose` subagent는 Main의 `mcp__Claude_Browser__*` 19개를 상속했고 `tabs_context` 호출에 성공했다.
- `tools-programmer` subagent는 Read·Glob·Grep·Write·Edit·Bash·Skill만 받았고 MCP 도구와 ToolSearch가 없었다.

## 검증 결과: Claude, 2026-10-11 (Computer use 설정 on)

결론: **현재 환경에서 Claude subagent의 직접 Computer Use 수행: 확인** (Notepad 1개 앱, 1회 성공 기준).

| 항목 | 결과 | 근거 |
| --- | --- | --- |
| Main 세션의 computer use 도구 | 있음 | ToolSearch `computer`로 `mcp__computer-use__*` 확인 |
| Child 도구 상속 | 확인 | 4회 모두 Child가 deferred 상태에서 ToolSearch로 직접 로드, `anthropic-skills:computer-use` 스킬 로드 |
| Child `request_access` 승인 표시·결과 | 확인 | 1차에서 승인 창이 사람에게 표시되어 직접 승인(호출 06:35:22Z → 결과 06:35:27Z). 2~4차는 같은 세션 grant(`grantedAt 1791700527596`)가 이어져 즉시 응답. Codex의 root 전용 elicitation 오류 없음 |
| 부여된 tier | `full` | `granted: 메모장 (Microsoft.WindowsNotepad_8wekyb3d8bbwe!App)`, `denied: []` |
| 요청·실행 모델 | override 없음 / `claude-opus-5-5` | subagent meta `agentType: general-purpose`, `requestShape: foreground`; Child assistant 메시지 `model` 전부 `claude-opus-5-5` |
| Child 직접 화면 조회 | 확인 (4차) | 1~3차는 주 모니터 전체 회색 마스크(아래 원인). 4차에서 Notepad 빈 탭 정상 표시 |
| Child 직접 UI 조작 | 확인 (4차) | click → `type` alpha 문자열 → `shift+left`×5 → `type "beta"`, 오류 없음 |
| Child 조작 후 화면 확인 | 확인 | screenshot·zoom에서 `CU-VERIFY-20261011-beta`, 상태 표시줄 "줄 1, 열 24 / 23자". Main이 이미지 파일로 별도 대조 |
| Main의 대리 조작 여부 | 없음 | Main은 진단용 `request_access` 1회(overlay 2개)와 screenshot 2회만 수행. 클릭·입력 없음 |
| 임시 작업 정리(저장 안 함) | 확인 | ctrl+w → 저장 확인 창에서 "저장하지 않음" 클릭, Notepad 닫힘. 사용자 폴더에 `CU-VERIFY*` 파일 없음 |

1~3차 실패 원인(Main·subagent 공통, subagent 제약 아님):

- 주 모니터(2560x1440) 전체를 덮는 투명 topmost overlay 창 `TabTip`(Shell Handwriting Canvas)과 `NVIDIA Overlay`가 allowlist 밖이라 마스크 사각형으로 칠해져 screenshot 전체가 단색 회색이 됐다. Chrome 최소화·Claude 앱 이동으로는 해결되지 않았고, Main screenshot도 동일했다.
- `request_access(["tabtip.exe", "nvidia overlay.exe"])`로 세션 allowlist에 추가하자 정상 표시됐다(두 앱은 조작하지 않음). 이 grant는 이후 subagent에도 이어졌다.
- hidden 목록에 매번 나온 `lockapp.exe`는 원인이 아니었다.

관찰된 부작용:

- clipboardWrite grant가 false인데도 `type`이 "Typed (via clipboard)"로 처리돼 사용자 clipboard가 테스트 문자열로 바뀌었을 수 있다.
- 작업 후 IME 표시가 "A"에서 "가"로 바뀌었다(설정 변경은 없음).
- Notepad 저장 확인 버튼의 실제 라벨은 "저장 안 함"이 아니라 "저장하지 않음"이다.

결론과 남은 결정:

- `general-purpose` subagent에 화면 조작 업무를 위임할 수 있다. 남았던 제약은 하네스가 아니라 이 PC의 overlay 창과 도구의 마스킹 방식이었다.
- 이름 있는 harness 역할에 맡기려면 agent 정의의 `tools`를 생략하거나 `mcp__computer-use__*`와 ToolSearch를 추가해야 한다(근거: `tools`가 없는 `general-purpose`만 MCP 도구를 상속). 이번 검증에서는 변경하지 않았고 별도 결정 사항이다.
- 상태: 하네스 변경 없음, 실제 실행 검증 완료, 독립 검토 not_run, 사람 수용 LOW 해당 없음. 한 앱 1회 성공이며 모든 앱 지원이나 비용 절감의 근거가 아니다.

## 최종 보고 형식

결론을 먼저 제시하라.

"현재 환경에서 Claude subagent의 직접 Computer Use 수행: 확인 / 부분 확인 / 차단 / 확인 불가"

| 항목 | 결과 | 근거 |
| --- | --- | --- |
| Main 세션의 computer use 도구 | | |
| Child 도구 상속 | | |
| Child `request_access` 승인 표시·결과 | | |
| 부여된 tier | | |
| 요청·실행 모델 | | |
| Child 직접 화면 조회 | | |
| Child 직접 UI 조작 | | |
| Child 조작 후 화면 확인 | | |
| Main의 대리 조작 여부 | | |
| 임시 작업 정리(저장 안 함) | | |

마지막으로 다음을 짧게 설명하라.

- subagent에 화면 조작 업무를 위임할 수 있는지
- 이름 있는 harness 역할에 맡기려면 필요한 최소 하네스 변경(agent 정의의 `tools`에 computer use 도구 추가 또는 `tools` 생략)과 그 근거
- 남은 제약이 하네스 문제인지 데스크톱 앱·도구 제공·승인 처리 문제인지
- 계획·구현 여부, 실제 실행 검증, 독립 검토 여부, 사람 수용 상태

한 번의 성공을 모든 앱 지원이나 비용 절감 입증으로 확대하지 마라. 사용량을 측정하지 않았다면 절감률을 제시하지 마라. 보고서를 저장한다면 UTF-8로 저장 후 다시 읽어 한글을 확인하고 핵심 결론을 채팅에도 적어라.
