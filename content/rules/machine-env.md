# Machine Environment

이 PC(zero9, Windows 11, 한국어 locale)에서 반복 확인된 환경 사실이다. 프로젝트와 무관하게 적용한다.
상태가 바뀌면 이 파일을 갱신한다.

- **CLI 도구**: `jq`는 없다 — JSON은 `py -3`(json 모듈)이나 PowerShell `ConvertFrom-Json`으로 파싱한다.
  `gh`(GitHub CLI)는 설치돼 있으나 인증은 보장되지 않으니 쓰기 전에 `gh auth status`로 확인하고,
  미인증이면 WebSearch/레지스트리 채널로 fallback하며 못 쓴 채널을 명시한다. (2026-10-11 확인)
- **Git Bash + `py -3`**: 콘솔이 cp949라 non-ASCII(한글·em-dash) 출력 시 `UnicodeEncodeError`가 난다 —
  `py -3 -X utf8`로 실행한다. Windows Python은 MSYS 경로 `/c/Users/...`를 해석하지 못하므로 Python에
  넘기는 경로는 `C:/Users/...` 형식을 쓴다.
- **Computer use 화면 마스킹**: `screenshot`이 화면 전체 단색 회색으로 나오면 투명 full-screen overlay
  (`TabTip`, `NVIDIA Overlay`)가 마스킹된 것이다. `request_access(["tabtip.exe", "nvidia overlay.exe"])`로
  allowlist에 추가해 보이게만 한다(조작하지 않는다). hidden 목록의 `lockapp.exe`는 원인이 아니다.
