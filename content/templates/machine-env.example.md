# Machine Environment

<!--
컴퓨터별 로컬 파일 템플릿이다. harness는 이 파일을 rules/에 설치하지 않는다.
사용: 이 파일을 ~/.claude/rules/machine-env.md로 복사한 뒤 그 컴퓨터에서 확인한 사실로 고친다.
~/.claude/rules/의 .md는 매 세션 자동 로드되므로 확인하지 않은 항목은 지운다.
install.py는 이 로컬 파일을 덮어쓰거나 지우지 않고, check.py도 leftover로 보고하지 않는다.
-->

이 컴퓨터(<사용자>, <OS>, <locale>)에서 확인된 환경 사실이다. 프로젝트와 무관하게 적용한다.
상태가 바뀌면 이 파일을 갱신한다.

- **CLI 도구**: <예: `jq` 유무 — `command -v jq`>. <예: `gh` 설치·인증 — `gh auth status`>.
  없는 도구는 대체 수단(예: JSON은 `py -3` json 모듈 또는 PowerShell `ConvertFrom-Json`)을 적는다.
- **셸 + Python**: <예: Git Bash에서 `py -3`의 콘솔 인코딩이 cp949면 non-ASCII 출력 시 `py -3 -X utf8`.
  Windows Python에는 MSYS `/c/...` 대신 `C:/...` 경로를 넘긴다.>
- **Computer use**: <예: `screenshot`이 전체 회색이면 hidden 목록의 overlay 프로세스
  (`tabtip.exe`, `nvidia overlay.exe` 등)를 `request_access`로 보이게만 한다.>
