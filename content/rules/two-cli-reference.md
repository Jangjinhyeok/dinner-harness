# Two-CLI Workflow — Reference Detail

이 문서는 `content/instructions/CLAUDE.md` §2(Two-CLI Workflow)에서 매 세션
필요하지 않은 상세 rationale·내부 동작·edge case를 분리해 둔 lookup-only
참고 문서다. **자동 inject되지 않는다** — CLAUDE.md의 포인터를 따라 필요할 때만
Read한다. 매 turn 필요한 핵심 라우팅 규칙(모드 진입, `/delegate` 판정, 기본
Builder-first entrypoint, dispatch 명령 자체)은 CLAUDE.md §2에 그대로 남아
있다 — 여기 있는 건 "왜 이렇게 설계했는가"와 "흔하지 않은 상황(cross-vendor,
내부 guard 동작 detail)"이다.

## Builder-first execution details

The normal `claude` command is the daily strict entrypoint. `builder_guard`
blocks Claude `Edit`/`Write` implementation edits by default; it permits only
root bus artifacts (`HANDOFF*.md`, `RESULT.md`, `INPUT.md`) and
`docs/architecture/*.md`, plus persistent-memory Markdown under
`<CLAUDE_CONFIG_DIR>/projects/*/memory/` (or `~/.claude/...` when the variable
is unset). The memory path is resolved before segment-based matching, so path
traversal is not allowed. Write the self-contained HANDOFF, create an ADR when
the decision is structural, then dispatch Codex with `orchestrate.py build`.

`~/.claude/dh.cmd` and `~/.claude/dh-architect.cmd` remain compatibility
launchers with the same Builder-first behavior. They are not required for the
daily workflow. `~/.claude/claude-direct.cmd` is the only direct-edit escape;
it sets `DINNER_EXECUTION_MODE=direct` for that one Claude process.

This is a workflow guard, not a sandbox. It deliberately does not parse or
block arbitrary Bash/PowerShell commands: the controller safety net remains the
deterministic decision boundary, and containment remains the sandbox's responsibility.

Each `build` appends content-free `attempted` then terminal (`built`, `blocked`,
`timeout`, or `builder_bailed`) JSONL events under the harness runtime `logs/`
directory and prints a `[receipt]` path only after the terminal event is
written. The record has hashes and outcome metadata, never HANDOFF/RESULT text,
prompts, or changed-file content.

## Cross-vendor 역할 분담 — rationale과 상세

Architect/Builder 역할은 **서로 다른 CLI(vendor)가 채울 수 있다 — 양방향**. 두 역할 모두 vendor-neutral한 협업 프로토콜이며 Claude·Codex 어느 쪽이든 어느 역할이든 맡을 수 있다.

**기본 페어링은 Claude = Architect, Codex = Builder다.** 근거는 token economy — 두 역할의 토큰 소비는 비대칭이다. **Builder가 token sink**다(여러 파일 Read, diff 생성, 빌드·에러 iterate 반복, 큰 컨텍스트, tool call 다발). 반면 **Architect는 low-volume·high-leverage**다(추론, 선별 Read, HANDOFF spec 작성, diff 검수). 따라서 토큰 무거운 Builder를 **quota 여유가 큰 plan(Codex)**에, 가벼운 Architect를 **quota가 빠듯한 plan(Claude Pro)**에 둔다 — Claude Max→Pro 다운그레이드로 Claude quota가 줄어든 상황의 합리적 배치다. 품질 축도 같은 방향이다: 설계 오류는 blast-radius가 크지만 Architect는 저volume이라, quota 빠듯하지만 추론 잘하는 모델에 정확히 들어맞는다.

예시 페어링:

- **Claude = Architect, Codex = Builder** (기본 — 설계·추론은 Claude, 토큰 무거운 구현·iterate는 Codex)
- **Codex = Architect, Claude = Builder** (역방향 — Claude quota가 충분하거나 특정 작업에서 Codex 설계가 더 나을 때)
- 동일 vendor 2세션(기존 Claude↔Claude)도 그대로 유효

**Builder vendor 스위치**: 기본값은 `codex` — Claude가 quota 빠듯한 plan(Pro 등)이라 token sink인 구현을 Codex에 맡기는 게 전제다(근거는 위 rationale). 이 값은 `harness.toml`의 `[vars].builder_vendor` 한 곳에서 중앙 관리된다(ADR-0014) — **Claude Max 등으로 옮겨 Codex 없이 Claude만 쓰고 싶어지면, 그 값을 `"claude"`로 바꾸고 `py -3 refresh.py --apply`로 재설치하는 것이 유일한 필수 변경이다.** `orchestrate.py`는 이미 `ClaudeBackend`/`CodexBackend` 양쪽을 동등하게 지원하므로(`orchestrator/vendors.py`) 코드 변경은 불필요하다. 아래 dispatch 명령을 비롯해 `~/.claude/roles/ROLE_ARCHITECT.md`·`~/.claude/rules/_mode/architect.md`·`~/.claude/skills/delegate/SKILL.md`·`~/.claude/README.md`·`~/.codex/AGENTS.md`의 동일 dispatch 명령도 같은 값으로 함께 렌더링되므로 개별 수정이 필요 없다. 이 문서·ROLE 파일의 나머지 Codex 관련 서술(quota 비대칭 근거, cross-vendor 주의사항 등)은 그 시점부터 더는 적용되지 않지만 동작을 막지는 않는다 — 정리는 그때 필요한 만큼만 한다. 반대로 Claude Code 없이 Codex만 쓰고 싶다면(Codex 단독), 바뀌는 축은 Builder vendor가 아니라 **Architect vendor**다 — 상세는 `~/.codex/AGENTS.md` §8 "Architect vendor 스위치" 참조(근거: ADR-0013).

**builder_vendor Scope 한계**: 위 `harness.toml` 값은 여기 나열된 문서들의 **렌더링된 예시**만 제어한다. `orchestrate.py build`/`run`을 `--builder` 플래그 없이 직접 실행하면 `orchestrator/config.py`의 `Config.builder_vendor` 코드 기본값(현재 `"codex"`)이 적용된다 — `harness.toml`은 런타임에 읽히지 않는다. 렌더된 문서가 이미 보여주는 `--builder <BUILDER_VENDOR>` 형태로 명시 지정하는 한 문제없다.

cross-vendor 시 주의:

- **HANDOFF.md는 self-contained여야 한다.** Builder가 다른 vendor면 상대에게 없는 도구(특정 skill·subagent·`/명령`)를 전제하지 않는다. 게이트의 빌드·검증은 표준 CLI 명령으로 기술한다.
- **Codex 세션은 path-매칭 auto-inject가 없다.** Claude는 `HANDOFF.md`/`RESULT.md`를 읽으면 `_mode` reminder가 자동으로 박히지만, Codex엔 그 기제가 없으므로 사용자가 모드를 **명시 선언**한다(`architect 모드`/`builder 모드`). Codex의 역할 프로토콜은 `~/.codex/AGENTS.md`의 Two-CLI 섹션(§8)에 있다.
