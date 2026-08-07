# Cross-Vendor Two-CLI Orchestrator

**한국어** | [English](README.md)

`autonomous-loop` skill의 외부·cross-process 대응물입니다. `HANDOFF.md` /
`RESULT.md` 파일 버스로 **Architect** vendor와 **Builder** vendor(Codex / Claude,
양방향 가능)를 연결해 사람이 파일을 전달하던 역할을 대체합니다. risk-tiered
autonomy가 사람에게 남기는 경계는 세 곳뿐입니다.

1. **START** — 의도 전달과 선택적인 HANDOFF 1회 승인
2. **HIGH sign-off** — HIGH-tier gate가 있을 때만
3. **END** — 최종 수용

그 사이의 Architect 설계, Builder 구현, panel review, Architect review, cycle
반복은 자동화됩니다. 외부 의존성 없이 Python standard library만 사용하며,
`install.py` / `check.py` / `adapters/` toolchain과 같은 방식으로 구성됩니다.

## Cross-vendor Two-CLI를 복원하는 방식

Codex adapter는 session-pair 개념이 없으므로 Two-CLI 역할을 여전히 일부
degraded로 표시합니다(`CODEX-RECON.md`). orchestrator는 이 pairing을 외부에서
관리합니다. 여기서 각 "session"은 controller가 실행하는 headless invocation
하나(`codex exec` 또는 `claude -p`)입니다. 즉 Two-CLI는 인터랙티브 터미널 두 개가
아니라 **두 역할과 두 CLI engine**을 뜻합니다.

HANDOFF/RESULT가 self-contained여야 하므로 각 turn은 repo와 bus를 매번 새로
읽는 stateless 실행입니다. session resume은 필요 없습니다.

진입점은 두 가지입니다.

- **`run`** — 완전 headless 모드. controller가 Architect와 Builder 모두를 전체
  loop 동안 실행합니다.
- **`build`** — 기존 `HANDOFF.md`로 Builder만 한 번 실행합니다. interactive Claude
  Architect가 세션 안에서 HANDOFF를 승인받은 뒤 auto-dispatch하는 기본
  orchestrated single-pane 경로입니다. Codex Builder와 hard safety net이 실행되고,
  같은 Claude 세션이 `RESULT.md`를 검토합니다. 상세는
  `roles/ROLE_ARCHITECT.md`의 "Builder 자동 dispatch"를 참조하세요.

## 빠른 시작

```bash
# Offline smoke: CLI 인증 없이 mock vendor로 LOW cycle 전체를 실행한다.
py -3 orchestrate.py run --goal "add a feature flag reader" --backend mock --yes --repo /path/to/scratch

# 실제 cross-vendor 실행. 기본값은 Claude=Architect, Codex=Builder.
py -3 orchestrate.py run --goal "..." --architect claude --builder codex \
    --backend real --repo /path/to/work-repo

# 기존 HANDOFF.md로 Builder만 한 번 실행한다.
py -3 orchestrate.py build --repo /path/to/work-repo --backend real
```

주요 flag는 `--architect/--builder {codex,claude}`, `--architect-model`,
`--builder-model`, `--max-cycles N`, `--no-confirm-handoff`, `--yes`,
`--net-dryrun`, `--timeout-s N`입니다. `--timeout-s`의 기본값은 headless vendor
turn당 1800초입니다. vendor stdout/stderr는 실행 중 stream되고 parsing용으로
capture됩니다. timeout은 child를 종료하고 `BLOCKED`로 남습니다. 재시도나 수동
fallback 전에 남아 있는 Builder worktree를 먼저 확인하세요.

### Dispatch receipt와 audit

`build`는 기본으로 harness 측 `logs/build-audit.jsonl`에 content-free JSONL event
두 개를 기록합니다. Builder 실행 전의 `attempted`와 controller 판단 뒤의
`built`, `blocked`, `timeout`, `builder_bailed` 중 하나입니다. `--audit-dir <path>`로
runtime log 위치를 바꿀 수 있지만, safety net이 판단하는 worktree delta를 오염시키므로
`--repo` 아래에는 두지 마세요.

terminal event는 dispatch id, UTC timestamp, vendor/backend, attempt 수, duration,
고정 reason code, repo path·handoff name·handoff text의 SHA-256 hash만 기록합니다.
prompt, HANDOFF/RESULT 본문, 변경 파일 경로·내용은 기록하지 않습니다. CLI의
`[receipt]` 출력은 audit 증거일 뿐이며 Architect의 RESULT/diff review나 HIGH human
end sign-off를 대체하지 않습니다.

## linked worktree로 Builder 격리

실제 Builder dispatch는 전용 linked worktree를 권장합니다. 이것은 process-level
boundary입니다. primary worktree의 Architect 수정은 Builder의 `git status` snapshot과
controller-side net에 섞이지 않습니다.

```powershell
# HANDOFF.md 승인 후 Architect primary worktree에서 실행한다.
$builderWorktree = "../repo-build"
git worktree add -b builder/my-task $builderWorktree HEAD
Copy-Item -LiteralPath .\HANDOFF.md -Destination "$builderWorktree\HANDOFF.md"

py -3 ~/.claude/orchestrate.py build --repo $builderWorktree --backend real

# primary가 아니라 Builder worktree에서 bus와 diff를 검토한다.
Get-Content -Raw "$builderWorktree\RESULT.md"
git -C $builderWorktree diff
```

`HANDOFF.md`와 `RESULT.md`는 local bus artifact이므로 linked worktree에 Architect의
uncommitted handoff가 자동으로 들어가지 않습니다. 승인된 handoff만 복사하고,
Builder가 수정한 handoff를 primary로 되돌려 복사하지 마세요. Builder output은 review와
일반적인 repository integration 절차를 위해 Builder worktree에 그대로 둡니다.

linked worktree는 Git common directory를 공유합니다. Builder가 실행 중일 때 primary
worktree에서 `git stash`, `core.excludesFile` 변경, `.git/info/exclude` 편집을 하지
마세요. 이 shared witness input의 변경은 net을 의도적으로 fail-closed 시킬 수 있습니다.
linked worktree의 per-worktree git dir에는 `info/exclude`가 없으므로 net은 의도적으로
`--git-dir` 대신 `rev-parse --git-common-dir`를 읽습니다.

## Machine-readable bus

사람이 읽는 HANDOFF/RESULT prose와 별도로, orchestrator는 vendor에게 prompt를 통해
작은 fenced block을 출력하게 하고 deterministic하게 parse합니다. harness 파일을 별도로
바꿀 필요는 없습니다.

| fence | 작성자 | 위치 | 내용 |
|---|---|---|---|
| ` ```tiers ` | Architect | HANDOFF | gate별 `gate N: LOW\|HIGH` |
| ` ```scope ` | Architect | HANDOFF | Builder가 수정 가능한 파일 목록 (`scope_check`도 사용) |
| ` ```verdicts ` | Builder | RESULT | `gate N: status=… tier=LOW\|HIGH panel=PASS\|FAIL\|BLOCK` |
| ` ```control ` | Architect review | stdout | `verdict: DONE\|NEXT_CYCLE\|BLOCKED` |

모호성은 모두 **fail-closed**입니다. 누락되거나 깨진 tier는 HIGH이고, `control` fence가
없으면 `BLOCKED`이며, HIGH gate에 `PASS` verdict가 없으면 block됩니다.

single-shot `build` 경로에서만, Builder가 in-scope implementation delta를 만들고 net
scan을 통과했지만 ` ```verdicts `를 누락한 경우 한 번의 **verdict-only recovery turn**을
시도합니다. 이 turn은 파일을 바꾸면 안 됩니다. controller는 기존의 사람이 읽는
`RESULT.md`에 fence를 덧붙이고, recovery 자체도 safety scan합니다. recovery 중 source
delta, 최초 implementation delta 부재, safety-net hit, 두 번째 malformed recovery는 모두
`BLOCKED`입니다.

## Safety model (협상 불가)

relay 자동화는 사람의 우연한 확인을 제거하므로 tier gate는 controller에 연결되며, 모든
모호성은 fail-closed입니다.

- **Controller-side deterministic net** — Builder turn 뒤 controller가 harness의
  `scope_check`와 `secret_scan` handler를 변경 없이 subprocess로 다시 실행합니다.
  vendor와 무관하게 적용되며, native Claude hook이 없는 Codex Builder를 보완합니다.
  handler block(exit 2), handler 누락·실행 실패, changeset 판별 실패는 모두 cycle을
  block합니다. non-repository에서 `git status`가 128로 끝나 빈 output을 내는 경우도
  clean tree가 아니라 failure입니다. fence는 hardcoded `HANDOFF.md`가 아니라 실제
  dispatch한 handoff(`cfg.handoff_name`)에서 가져와 handler environment에 pin합니다.
  `scope` fence가 없거나 comment만 있으면 Builder 시작 전에 거부됩니다. verdict 없이
  끝난 handler watchdog/crash도 여기서는 interactive fail-open이 아니라 block입니다.
- **증거 자체를 검증합니다.** Builder는 tracked file을 바꾸지 않고도 net의 witness인
  `git status`를 바꿀 수 있습니다. `git commit`, `git stash`, `.git/info/exclude`,
  `core.excludesFile`, `assume-unchanged`/`skip-worktree` index bit는 snapshot 양쪽에서
  path를 감출 수 있으므로 turn 전후 fingerprint로 검증하며, 변화가 있으면 cycle을
  fail-closed 합니다.
- **snapshot 안의 directory는 거부합니다.** `-uall`은 untracked directory를 file별로
  펼치지만 nested git repo에서는 repository boundary에서 멈춥니다. 이 opaque entry의
  내용은 `secret_scan`에 빈 문자열로 도달하므로, 아무것도 검증하지 않는 대신 cycle을
  실패시킵니다. dispatch 시 이미 dirty였던 nested repo도 delta 비교에서 사라질 수 있어
  snapshot과 turn 전 모두에서 검사합니다. dirty nested repo 또는 submodule이 있으면
  clean, commit, ignore 전에는 dispatch할 수 없습니다.
- net의 git 호출은 상속된 `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`,
  `GIT_COMMON_DIR`를 무시합니다. 이 값들은 git hook이나 `git rebase --exec`에서 흔하며,
  다른 repository를 가리키면 work repo 변경이 changeset에서 사라집니다.
- **net은 Builder turn의 DELTA를 판단합니다.** `collect_changeset`이 전후 snapshot을
  만들고 내용이 다른 path만 제출합니다. untracked handoff, Architect가 쓴 ADR, 기존
  scratch file 같은 pre-existing dirt는 Builder 작업이 아니므로 책임지게 하지 않습니다.
  delta는 두 snapshot의 union을 key로 사용하므로 `git status`에서 사라진 path도
  판단합니다. untracked file 삭제는 `D` entry 없이 사라지므로 after-only 비교로는 볼 수
  없기 때문입니다. scope-exempt path는 controller가 책임지는 `RESULT.md`와 dispatch한
  handoff 정확히 두 개뿐입니다. 둘 다 secret-exempt는 아니며 매 cycle changeset에
  추가되어 `secret_scan`이 봅니다. 그 외 예외는 없습니다.
- **Handoff tamper stop** — controller가 dispatch한 text를 보관하고 turn 뒤 비교합니다.
  삭제나 decode 불가를 포함한 모든 drift는 cycle failure입니다. handler가 적용하는
  fence도 disk에서 매 file 다시 읽지 않고 controller가 environment로 pin합니다.
- **Changeset ceiling** — `-uall`은 untracked file을 개별 목록으로 만들므로 `.gitignore`가
  얇은 repo는 수천 path와 path당 두 handler subprocess를 만들 수 있습니다.
  `_MAX_CHANGESET`을 넘으면 수 분 동안 stall하는 대신 fail-closed 합니다. 한계를 넘는지는
  file content를 읽기 전에 git이 보고한 path 수로 판정합니다.
- **Handler budget** — interactive Claude hook의 200 ms watchdog은 timeout 시 allow가
  맞지만, net은 전체 file content를 전달하므로 맞지 않습니다. net에서는 budget을
  높이고 timeout을 block으로 해석합니다.

**Threat model — 이 net이 보장하는 것.** 이 net은 spec을 오해하거나, 범위를 넘어
refactor하거나, 수정 금지 파일을 고치거나, key를 붙여 넣는 **over-reaching Builder**를
hard gate로 막습니다. 이는 headless agent에서 실제로 자주 발생하는 failure mode입니다.

반대로 shell을 통해 같은 tree에 접근하는 **evading Builder**를 containment하지는 못합니다.
ignore rule과 index-bit fingerprint는 가장 싼 우회 둘을 막을 뿐 전체 class를 막지는
않습니다. `BUILT`는 "net이 볼 수 있는 범위에서 문제가 없었다"는 뜻이지 다른 일이 전혀
없었다는 증명은 아닙니다. containment가 필요하면 Builder가 벗어날 수 없는 worktree나
sandbox 같은 process-level boundary가 필요합니다.

정직한 Builder에게도 net이 보지 못하는 영역이 있습니다. global `core.excludesFile`을
포함해 `.gitignore`에 match된 file은 `git status`에 나타나지 않습니다. `--ignored`는
`node_modules`까지 보고해 dispatch를 매번 거부할 수 있어 채택하지 않았습니다. 따라서
target repo의 ignore rule도 safety boundary의 일부입니다. 또한 block은 rollback이 아니라
**거부**입니다. out-of-fence deletion은 보고되지만 되돌려지지 않습니다.

- **Tier-gate enforcement** — effective tier는 Architect 선언과 Builder self-report 중 더
  높은 값입니다. ` ```tiers ` fence가 누락되거나 깨지면 모든 gate가 HIGH입니다. 모든
  tier에서 panel `FAIL`/`BLOCK`은 fail이고, HIGH는 명시적 `panel=PASS`가 필요합니다.
  선언된 gate에 verdict가 없거나 gate가 전혀 없어도 fail-closed 합니다.
- **tier-driven END boundary** — Architect review가 먼저 실행됩니다. `DONE`이면 LOW cycle은
  autonomy-policy에 따라 report만 남기고 자동 완료되며, HIGH cycle은 변경 수용 전에
  human end sign-off에서 멈춥니다. Architect가 거부한 cycle에 사람이 sign-off하지 않습니다.
- **`--yes` guard** — `--backend real`에서는 `--dangerously-auto-approve-real`을 명시하지
  않으면 모든 gate를 auto-approve하는 `--yes`를 거부합니다.

handler의 `always_block` layer는 harness 설치본(`settings.json`, `hooks/`)을 보호하지만,
live install `~/.claude`에 anchor됩니다. controller는 보통 work repo 안 path만 제출하므로
일반 dispatch에서는 scope fence가 scope enforcement의 전부입니다. 단 git root가 work
repo보다 상위이면 repo 밖 path가 absolute form으로 제출되어 always-block layer도 match할 수
있습니다. 이는 block만 추가하므로 안전합니다. handler를 verbatim으로 재실행한다는 말은
mechanism 설명이지 두 layer가 항상 동시에 active라는 뜻은 아닙니다.

> **이 영역을 바꾸면 반드시 install합니다.** `assets/claude/hooks/`, `orchestrator/`,
> `orchestrate.py` 아래를 바꾼 뒤에는
> `py -3 install.py --target claude --allow-live`(필요하면 `--target codex`)를 다시
> 실행하세요. live dispatch는 `py -3 ~/.claude/orchestrate.py build`로 **설치본**을
> 실행하므로 repo에만 있는 수정은 runtime에 적용되지 않습니다. `py -3 check.py`의
> install-drift axis가 repo와 설치본의 차이를 보고합니다. 이것은 report일 뿐 install하지는
> 않습니다.
>
> **되돌리기:** `install.py`는 제자리 덮어쓰기만 하고 backup을 남기지 않습니다. 이전
> commit에서 다시 install하는 것이 유일한 undo입니다.
> `git stash && py -3 install.py --target claude --allow-live && git stash pop`
> 또는 이전 commit을 checkout해 거기서 install하세요. 모든 handler가 import하는
> `hooks/lib/common.py` 변경은 특히 위험합니다. live tree를 먼저 복사해 두는 것도 좋은
> 보험입니다.

## 상태와 build-time 검증

- **Mock core — 완료 및 테스트됨.** `py -3 -m unittest discover -s orchestrator/tests`는
  전체 loop, tier gate, 실제 safety-net handler를 offline에서 검증합니다.
- **Real backend — scaffold.** `ClaudeBackend`(`claude -p`)와 `CodexBackend`(`codex exec`)는
  구현되어 있지만, CLI version마다 정확한 flag/output format과 non-interactive permission
  posture가 다릅니다. `--backend real`을 신뢰하기 전에 두 CLI가 인증된 machine에서 다음을
  확인하세요.
  - autonomous Builder에서 `claude -p` output format과 `--permission-mode`
  - `codex exec` sandbox/approval flag(`--full-auto` 등)와 `--cd`
  - 전제 조건: cross-vendor Codex 작업에는 Codex 0.140 이상이 필요합니다. controller net은
    version과 무관하게 Builder diff를 보지만, Codex native safety는 0.140+에서만 있습니다.

## 구조

```
orchestrate.py            CLI 진입점 (repo root; install.py / check.py와 동일한 위치)
orchestrator/
  controller.py           state machine, prompt builder, tier gate, human gate
  bus.py                  HANDOFF/RESULT I/O 및 tiers/verdicts/control parsing
  vendors.py              Backend interface, Mock, Claude/Codex real backend
  safety.py               controller-side net (harness hook handler 재사용)
  config.py               config dataclass와 기본값
  tests/                  offline unittest (mock + real handler)
```

`orchestrate.py`와 이 package는 `install.py`가 `~/.claude`에 설치합니다
(`harness.toml` 참조). 기본 dispatch가 `py -3 ~/.claude/orchestrate.py build`를
실행하기 때문입니다. 이들은 skill/agent/hook이 아니므로 harness capability catalog에
나타나지 않으며, 설치본 대조가 없던 예전 `check.py`에서는 보지도 않았습니다. 따라서 이
영역의 수정이 repo에만 남고 live lane은 구버전을 계속 실행할 수 있습니다.
