# Optional Headless Dispatch / Two-CLI

2026-09-10 운영 정책: Codex는 기본적으로 한 세션에서 탐색·설계·구현·검증한다.
다른 모델로 큰 경계 작업을 넘기거나 독립 challenge 및 controller 검사가 필요할 때만
이 절차를 선택한다. Claude 전용 Builder-first entrypoint는 호환 경로다.

## 실행

active harness home(사용자 지정 home 포함)의 orchestrate.py와 실제 repository 절대경로를 쓴다.
Windows 예시(placeholder를 실제 경로로 치환):

```text
py -3 "<HARNESS_HOME>/orchestrate.py" challenge --repo "<REPO>" --backend real
py -3 "<HARNESS_HOME>/orchestrate.py" build --repo "<REPO>" --backend real
```

다른 OS는 설치된 Python executable을 쓴다. shell pipe/redirection이나 인증 내용을 명령에
끼워 넣지 않는다. HANDOFF는 self-contained scope/tiers/verify를 포함하고 build 동안
같은 tree를 parent가 편집하지 않는다. 현재 user-selected branch와 기존 dirt를 보존한다.

HIGH challenge 증거는 repo/task/HANDOFF/policy에 묶여야 하며 challenge가 실행된 사실과
사람의 수용은 별개다. HIGH는 구현 후 독립 review 및 사람 수용 경계를 유지한다.
Controller pinned scope/secret net은 위반 시 BLOCK하며 rollback을 대신하지 않는다.
Ignored files나 우회 shell I/O 전체를 봉쇄하는 containment라고 설명하지 않는다.

## 결과와 관찰

Codex JSONL events는 thread/error/usage 관찰용, 최종 output-schema JSON은 결과 계약용이다.
RESULT는 사람이 읽는 보고서이며 BUILT는 review PASS나 수용을 의미하지 않는다.
실제 independent review가 없으면 not_run이다. 손상 결과 복구는 read-only여야 하며
format 실패만으로 재구현하지 않는다. 실패/timeout partial edits도 검사·보고한다.

지원된 native agent UI/tools 또는 dispatch별 식별자로 관찰한다. private rollout 파일 형식과
단일 전역 session marker를 작업 identity로 쓰지 않는다. resume는 repo/task에 연결된
명시적 thread ID를 쓰고 concurrent 작업에서 --last를 쓰지 않는다.

`run`은 legacy/experimental 경로다. 기본 workflow로 권장하지 않으며 지원 옵션은 설치 CLI help를
확인한다. 명시적 역할 제한은 [Architect](../roles/ROLE_ARCHITECT.md)와
[Builder](../roles/ROLE_BUILDER.md), 모델 정책은 [routing](routing-reference.md)를 읽는다.
