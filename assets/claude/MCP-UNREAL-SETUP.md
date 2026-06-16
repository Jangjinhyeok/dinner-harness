# mcp-unreal 셋업 가이드 (UE 5.7)

이 문서는 `~/.claude`의 MCP 인프라 중 **엔진 MCP(Unreal)** 의 구체 셋업 walkthrough다. 루트 `README.md`의 "MCP (외부 도구 연결)" 절과 `templates/README.md`의 "엔진 MCP 등록"이 개념·등록 레시피를 다루고, 이 문서는 **실제로 진행한 UE 5.7 + [remiphilippe/mcp-unreal](https://github.com/remiphilippe/mcp-unreal) 셋업 전 과정과 트러블슈팅**을 남긴다.

> 경로는 **placeholder**다 — 본인 환경에 맞게 치환한다:
> - `<USERNAME>` = Windows 사용자명 (`C:\Users\<USERNAME>\…`)
> - `<Project>` = 게임 프로젝트명 (`.uproject` 이름)
> - mcp-unreal 클론 위치(`C:\Users\<USERNAME>\mcp-unreal`)·UE 설치 경로(`…\UE_5.7\…`)도 본인 환경 기준으로 조정

---

## 0. 아키텍처 — 연결이 2개다

```
[1] Claude Code ──stdio──▶ mcp-unreal(Go 서버) ──HTTP──▶ [2] UE 에디터
                                                            ├─ Remote Control API : 30010 (+WS 30020)
                                                            └─ MCPUnreal 플러그인 : 8090
```

- **연결 [1] (Claude ↔ Go 서버)**: Claude Code가 세션 시작 시 stdio로 바이너리를 **직접 spawn**한다. **에디터 불필요** — 에디터가 꺼져 있어도 `/mcp`엔 Connected로 뜬다.
- **연결 [2] (서버 ↔ 에디터)**: 서버가 tool 호출 시 30010/8090으로 HTTP 요청. **에디터가 켜져 있어야** 동작. 닫혀 있으면 에디터 계열 tool만 실패(headless 빌드/테스트/문서 tool은 가능).

이 구분이 트러블슈팅의 핵심이다 (§6).

---

## 1. 선행 설치 (1회)

```powershell
winget install GoLang.Go      # Go 1.25+ (이 서버는 Go로 작성됨)
go version
```
- UE 5.7 + 대상 프로젝트(<Project>)는 이미 있다고 가정.

---

## 2. 에디터 측 준비 (프로젝트에서, 1회)

### 2-1. repo 클론 (plugin/ 폴더 확보용)
`go install`은 바이너리만 받고 플러그인 소스는 안 받는다. 클론이 필요하다.
```powershell
git clone https://github.com/remiphilippe/mcp-unreal.git C:\Users\<USERNAME>\mcp-unreal
```

### 2-2. 플러그인 복사
```powershell
New-Item -ItemType Directory -Force C:\Users\<USERNAME>\Documents\Github\<Project>\Plugins\MCPUnreal
Copy-Item -Recurse -Force C:\Users\<USERNAME>\mcp-unreal\plugin\* C:\Users\<USERNAME>\Documents\Github\<Project>\Plugins\MCPUnreal\
# .uplugin가 한 단계 안에 있는지 확인
Get-ChildItem -Recurse -Filter *.uplugin C:\Users\<USERNAME>\Documents\Github\<Project>\Plugins\MCPUnreal
```

### 2-3. 프로젝트 재빌드
C++ 모듈을 새로 인식해야 한다.
1. `<Project>.uproject` 우클릭 → **Generate Visual Studio project files**
2. `.uproject` 더블클릭 → "missing modules, rebuild?" → **Yes** (또는 VS에서 빌드)

### 2-4. Remote Control API 켜기 + web server 시작
1. 에디터 → `Edit > Plugins` → "Remote Control API" **Enabled** → **에디터 재시작**(모듈 로드).
2. RC API HTTP 서버는 자동으로 안 뜰 수 있다. 에디터 콘솔(`` ` `` 키) 에서:
   ```
   RemoteControl.StartWebServer
   ```
   매번 자동으로 켜려면 `Project Settings` → "Remote Control" 검색 → web server auto-start 옵션 활성화.

### 2-5. 검증
PowerShell의 `curl`은 `Invoke-WebRequest` 별칭이라 헷갈린다. 포트 직접 확인이 확실:
```powershell
Get-NetTCPConnection -LocalPort 30010,30020,8090 -State Listen
# RC API 응답 확인 (Invoke-RestMethod 권장)
Invoke-RestMethod "http://127.0.0.1:30010/remote/info"
```
30010(RC API)·30020(WS)·8090(플러그인) 셋 다 listen이면 에디터 측 완료.

---

## 3. 서버 바이너리 + 문서 인덱스 (1회)

```powershell
go install github.com/remiphilippe/mcp-unreal/cmd/mcp-unreal@latest
# 설치 위치: C:\Users\<USERNAME>\go\bin\mcp-unreal.exe
mcp-unreal --help          # 실행 확인(AV 격리 등 점검)

cd C:\Users\<USERNAME>\mcp-unreal
mcp-unreal --build-index   # UE 5.7 docs 인덱싱 → ./docs/index.bleve
```
- `--help`가 "명령 없음"이면 `C:\Users\<USERNAME>\go\bin`이 PATH에 없는 것(단, `.mcp.json`은 절대경로를 쓰므로 spawn엔 PATH 불필요).

---

## 4. Claude Code 등록 (project scope)

엔진 MCP는 특정 프로젝트·에디터에 묶이므로 **project scope** `.mcp.json`에 둔다(user scope면 다른 세션에서 죽은 tool이 뜬다). **프로젝트 루트**(`docs/` 아님)에 `.mcp.json`을 둔다.

`C:\Users\<USERNAME>\Documents\Github\<Project>\.mcp.json`:
```json
{
  "mcpServers": {
    "mcp-unreal": {
      "type": "stdio",
      "command": "C:\\Users\\<USERNAME>\\go\\bin\\mcp-unreal.exe",
      "env": {
        "MCP_UNREAL_PROJECT": "C:\\Users\\<USERNAME>\\Documents\\Github\\<Project>\\<Project>.uproject",
        "UE_EDITOR_PATH": "C:\\Program Files\\Epic Games\\UE_5.7\\Engine\\Binaries\\Win64\\UnrealEditor-Cmd.exe",
        "MCP_UNREAL_DOCS_INDEX": "C:\\Users\\<USERNAME>\\mcp-unreal\\docs\\index.bleve"
      }
    }
  }
}
```
- `MCP_UNREAL_DOCS_INDEX`는 **절대경로 권장**이다. 없으면 서버가 `./docs/index.bleve`(cwd 상대)를 찾는데, Claude가 프로젝트 루트를 cwd로 띄우면 인덱스를 못 찾아 서버가 실패할 수 있다(§6 참조). 절대경로로 박으면 cwd 무관.
- `.uproject` 파일명·`UE_5.7` 설치 경로는 본인 환경에 맞게. 30010/8090은 기본 포트라 생략 가능.
- ⚠️ 절대경로·`.uproject` 경로가 박혀 **머신 종속**이다. 게임 repo에 commit하려면 `.gitignore`에 `/.mcp.json` 추가(개인용이면 무관).

---

## 5. 연결 + 사용

1. **UE 에디터를 켠다**(RC web server + 플러그인 로드 상태).
2. **그 프로젝트 폴더에서 Claude Code 세션을 (재)시작** → Claude가 mcp-unreal을 자동 spawn.
   - `.mcp.json`은 **세션 시작 시점에 한 번** 읽힌다. 추가·수정 후엔 반드시 세션 재시작.
3. 처음이면 **승인 프롬프트** → **"Use this MCP server"**(1번)만 선택(모든 서버 자동신뢰는 비권장).
4. `/mcp` → `mcp-unreal` **Connected** 확인.
5. 자연어로 tool 호출:
   - "현재 레벨의 액터 나열해줘" (`get_level_actors`)
   - "BP_PlayerCharacter 변수·함수 보여줘" (`blueprint_query`)
   - "빌드하고 에러만 정리해줘" (`build_project`)
   - "`stat unit` 켜고 뷰포트 스크린샷" (`run_console_command` + `capture_viewport`)

tool은 49개(v0.2.0 기준): 빌드/테스트(headless), 액터·속성, Blueprint/AnimBP, GAS, UMG 조회(`ui_query`), Niagara/PCG/Material, 콘솔/Python/스크린샷, UE5.7 문서 lookup 등. 카테고리 상세는 세션에서 다룬 capability 목록 참조.

> **읽기 vs 쓰기**: 조회 tool(`get_level_actors`·`blueprint_query`·`ui_query`·`capture_viewport`)이 안전한 sweet spot. 쓰기 tool(`spawn_actor`·`blueprint_modify`·`set_property`·`execute_script`)은 §7 주의.

---

## 6. 트러블슈팅 (이 세션에서 실제로 겪은 것)

### RC API "원격 서버에 연결할 수 없다" / 30010 무응답
- 원인: 에디터는 떠 있어도 **RC web server가 자동 시작 안 됨**.
- 조치: 콘솔에서 `RemoteControl.StartWebServer` (§2-4). `Get-NetTCPConnection -LocalPort 30010`로 listen 확인. PowerShell `curl` 빈 결과는 `Invoke-WebRequest` 특성이니 `Invoke-RestMethod`로 재확인.

### `/mcp`엔 Connected인데 에디터 tool이 실패
- 원인: 연결 [2] 문제 — **에디터가 꺼져 있음**(또는 30010/8090 미기동).
- 조치: 에디터를 켜고 RC web server 시작. 서버는 매 호출 HTTP로 붙으므로 **Claude 세션 재시작 불필요** — 에디터만 켜고 tool 재호출.

### mcp-unreal이 `failed`로 뜸
- **에디터 닫힘이 원인이 아니다.** 서버(연결 [1])는 에디터 없이도 정상 기동한다(검증됨: 인덱스 로드 → tool 49개 등록 → connected). `failed`는 **서버 프로세스 spawn 문제**다.
- 점검 순서:
  1. 바이너리 존재·실행: `Test-Path C:\Users\<USERNAME>\go\bin\mcp-unreal.exe`, `mcp-unreal --help`
  2. 인덱스 존재: `Test-Path C:\Users\<USERNAME>\mcp-unreal\docs\index.bleve`
  3. `.mcp.json` 유효 JSON: `Get-Content …\.mcp.json -Raw | ConvertFrom-Json`
  4. **doc-index 경로**: `.mcp.json` env에 `MCP_UNREAL_DOCS_INDEX` 절대경로가 있는지(없으면 cwd 상대경로라 Claude가 띄울 때 못 찾을 수 있음) → §4처럼 박는다.
- 보통 위 하드닝 + **세션 재시작**으로 복구. 그래도 실패면 상세 로그로 진단:
  - `.mcp.json`의 `command`를 그대로 두고 args에 로그레벨을 주거나, 수동 실행으로 stderr 확인:
    ```powershell
    & "C:\Users\<USERNAME>\go\bin\mcp-unreal.exe" -log-level debug
    # 4초 살아있고 "server session connected" 나오면 서버 자체는 정상
    ```

### PowerShell `curl`이 이상함
- `curl` = `Invoke-WebRequest` 별칭이다. dead port면 "원격 서버에 연결할 수 없다", 정상이면 응답 객체. 깔끔히 보려면 `Invoke-RestMethod` 사용.

---

## 7. ⚠️ 보안 — hooks 안전망 밖

엔진 MCP의 쓰기 tool(`spawn_actor`·`blueprint_modify`·`set_property`·`execute_script` 등)은 **에디터에서 임의 작업을 실행**한다. 이는 `scope_check`·`secret_scan` hook이 가로채는 Claude의 Edit/Write/Bash가 **아니라** MCP 호출이라 **안전망 밖**이다(CLAUDE.md §5 라이브 서비스 원칙 직격).

- 메인 프로젝트엔 변경을 감독하며, **테스트 브랜치/사본에서 먼저** 검증.
- `execute_script`(임의 Python)·`blueprint_modify`는 특히 영향이 크다.
- **역할 분리**: `ue-*` specialist agent = 코드·설계 산출물(텍스트), MCP = 라이브 에디터 조작·빌드·검증(실행). 섞지 않는다.

---

## 8. 올바른 작업 순서 (요약)

1. `.mcp.json` 준비 + 승인 (1회)
2. UE 에디터 켜기 (RC web server + 플러그인 로드)
3. 프로젝트 폴더에서 Claude Code 세션 시작 → mcp-unreal 자동 spawn → `/mcp` Connected
4. tool 사용

엄밀히는 2번이 3번보다 반드시 먼저일 필요는 없지만(연결 [1]은 에디터 없이도 됨), 헷갈리지 않으려면 "에디터 먼저 → 세션 → 사용"을 습관화한다.

---

## 9. 문서 소스 분담 (참고)

UE5 엔진 API는 mcp-unreal의 `lookup_docs`/`lookup_class`, 일반 OSS 라이브러리는 context7(user scope)이 담당한다. 둘 다 research-first(CLAUDE.md §1.5)를 라이브 문서로 강화하는 보완재다.
