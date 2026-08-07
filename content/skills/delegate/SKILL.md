---
name: delegate
description: Lightweight delegation lane — hand a small, single-purpose LOW-risk task (code OR file-based document) to the Codex Builder headless (orchestrate.py build) and review the result inline, skipping the full Architect ceremony (mode entry, gated HANDOFF, ADR). Use when the user wants a self-contained change built by Codex without the heavy ritual — "위임", "이거 codex/코덱스로 시켜", "delegate this", "quick build" — including document work such as 이력서/경력기술서 변형, JD 대조 갭 분석, 여러 버전 톤 통일, 문서 재구조화. HIGH-risk or multi-file/multi-gate/design work escalates to architect mode instead.
---

# /delegate — Lightweight Codex Delegation

The quick path for handing ONE small LOW-risk change to the Codex Builder without
the full Architect ceremony. Claude stays the Architect: it triages, writes a
minimal handoff, dispatches Codex headless, and reviews the diff inline — all in
one turn. Token-heavy implementation lands on Codex's quota; Claude's scarce
quota is spent only on triage + review.

This wraps the existing `orchestrate.py build` dispatch (retry-hardened against a
Builder's false read-only bail). It introduces no new engine or pairing — default
pairing only (Claude=Architect, Codex=Builder).

## Entry

`/delegate` is an explicit force-route, but it is not required. In a normal
Claude session, `CLAUDE.md` default-session routing enters this workflow
automatically for a clear, single-purpose LOW implementation request. Do not ask
the user to repeat the request with `/delegate`: their original request is the
LOW start intent. If repository inspection finds a HIGH signal, multiple gates,
or a design decision, stop this workflow and use the Architect route instead.

## Two lanes: code and document

The dispatch path carries **no domain assumption**. The scope fence is a plain
file whitelist; the controller-side net collects changes with
`git status --porcelain` and runs `secret_scan`/`scope_check` per file (file-level,
not language-level); `build_prompt` says "implement the HANDOFF", never "write
code". So the same lane carries **file-based document work** — 이력서/경력기술서
변형, JD 대조 갭 분석, 여러 버전 톤 통일, 문서 재구조화. These are token-heavy to
generate but cheap to specify and review: exactly the shape this lane exists for.

Only two things differ by lane:

| | code lane | document lane |
|---|---|---|
| HIGH signals | replication/RPC, save format, live config, migration, security, public API/ABI, build pipeline | 외부로 제출·발송·공개되는 최종본 확정 (비가역 outward-facing) |
| Verify | test / build / lint command | structural check — 섹션 존재, 분량 상한, 금지 표현, 날짜 형식 |

Everything else is identical: LOW-only, mandatory scope fence and `git diff` review.
The Builder delta remains uncommitted until Architect review. If the user explicitly
authorizes `commit` or `commit and push` in the current conversation, integrate only
the accepted delta into the user-selected current delivery branch; never create or
push a new delivery branch.

**Prerequisite (both lanes): the work directory must be a git repo.** The safety
net collects the changeset via `git status --porcelain` and **fails closed** when
git is unavailable, so a non-repo directory cannot be dispatched at all. Run the
CLI from the directory where the files already live, and commit a clean baseline
first — the inline review reads `git diff` against it.

## When to use vs escalate

Use `/delegate` when the task is **all** of:
- LOW risk (per `~/.claude/rules/autonomy-policy.md`), and
- single-purpose / roughly 1–3 files, and
- clear enough to specify without a design discussion.

STOP and escalate to `architect 모드` (full gated HANDOFF + ADR + human end
sign-off) when **any** of:
- a HIGH signal is present — replication/RPC/net-serialization, save/serialization
  format, live config/feature flag, data migration/schema, security
  (auth/crypto/trust/anti-cheat), public API/ABI, build/packaging pipeline, or
  anything broad/irreversible; in the document lane, finalizing anything that goes
  outward (제출본·발송본·공개 게시물) — drafting it is LOW, 확정·제출은 사람 몫;
- the change spans many files or multiple gates;
- the approach needs options/discussion first.

Tier is judged conservatively: ambiguous → HIGH → escalate. `/delegate` is
LOW-only by construction.

## Workflow (one turn)

1. **Triage** — classify risk tier + shape. HIGH, or multi-gate/design →
   do NOT dispatch; tell the user this needs architect mode and offer to switch.
   Otherwise continue.
2. **Draft minimal handoff** — write `HANDOFF_DELEGATE.md` in the work repo with
   exactly four parts (nothing else — no ADR, no options, no gate decomposition):
   - **Goal** — 1–3 lines.
   - **Operative scope** — a ` ```scope ` fence listing every file Codex may
     create/edit, plus `RESULT.md`. REQUIRED: the deterministic net
     (`scope_check`) hard-blocks any change outside this whitelist, so an omitted
     or wrong scope makes the build fail closed.
   - **Tier** — a ` ```tiers ` fence: `gate 1: LOW`.
   - **Verify** — the exact command(s) Codex must run to self-confirm the gate.
     A gate with no runnable check is not dispatchable. In the document lane
     substitute a structural check (sections present, length budget, banned
     phrasing, date format) — see the document example below.
3. **Dispatch (same turn)** — LOW is autonomous (autonomy-policy: the human sets
   intent at the start, which is the user's request itself), so dispatch right
   after showing the compact spec:
   ```
   py -3 ~/.claude/orchestrate.py build --repo . --backend real --handoff HANDOFF_DELEGATE.md
   ```
   `--handoff HANDOFF_DELEGATE.md` keeps a persistent `HANDOFF.md` (if any)
   untouched.
4. **Review inline** — on `[outcome] BUILT`: read `RESULT.md` + `git diff`, run
   the verify command, and judge accept / rework against the goal. On rework:
   rewrite `HANDOFF_DELEGATE.md` and re-dispatch once. On `[outcome] BLOCKED` or a
   command error (codex unauthenticated, flag drift): do NOT proceed — report and
   offer the manual fallback (open a Codex terminal, `builder 모드`, run the
   handoff).
5. **Report** — a §5 structure briefing: what changed, which files, verification
   result. Do not commit merely because the LOW build passed. An explicit current-turn
   `commit` or `commit and push` authorization targets only the user-selected current
   delivery branch after the accepted delta is integrated.

## Guardrails

- **LOW-only** — HIGH or multi-gate escalates to architect mode; never dispatched here.
- **Scope fence is mandatory** — it is the safety boundary the controller-side net
  enforces (a Codex Builder fires no Claude hooks, so this net is the only
  automatic defense). In `enforce` the net now **fails closed when the handoff
  carries no ```scope``` fence** (or an all-comment one): a dispatch without a
  fence is refused rather than admitted unbounded.
- **The fence must cover what VERIFICATION writes, not just what the work
  writes.** The gate's check runs inside the Builder's turn, so anything it
  creates is part of the delta the net judges — a Python verify writes
  `__pycache__/`, a test run writes `.pytest_cache/`, a build writes its output
  dir. Either name them in the fence or make sure the repo ignores them;
  otherwise a correct build is refused for its own side effects. Widening the
  fence to cover *source* paths to get past this is the anti-pattern — widen it
  for artifacts only.
- **Never clobber `HANDOFF.md`** — always dispatch from `HANDOFF_DELEGATE.md`.
- **Document lane: keep the source OUT of the scope fence.** Whitelist only the
  derived file(s), never the original. `scope_check` then blocks edits to the
  source — including **deleting or moving it away**, which the net sees even
  when the file is untracked — 원본 보호가 기존 안전망에서 공짜로 따라온다.
  Three honest limits: a block is a **refusal, not a rollback** (the net reports
  the violation, it does not restore the file); anything the repo **ignores** is
  invisible to the net; and the fence constrains a Builder that **over-reaches**,
  not one that **evades** — a headless agent with a shell in the same tree
  cannot be contained by a net living in that tree (see the threat model in
  `orchestrator/README.md`). Never delegate an in-place rewrite of a document
  that has no committed baseline — that baseline, not the fence, is what lets
  you undo a bad turn.
- **Default pairing only** — Claude=Architect dispatches Codex=Builder. If codex is
  unavailable/unauthenticated, fall back to manual.
- **Delivery discipline** — LOW is report-only unless the user explicitly authorizes
  `commit` or `commit and push` in the current conversation. Use the user-selected
  current branch only; do not create, switch, merge, or push a delivery branch.

## Example — code lane

User: "위임 — src/util/date.py에 KST 기준 오늘 날짜를 'YYYY-MM-DD'로 주는 today_kst() 추가해줘."

1. Triage: pure local util, no HIGH signal, single file → LOW, proceed.
2. Write `HANDOFF_DELEGATE.md`:
   - Goal: add `today_kst() -> str` returning KST today as `YYYY-MM-DD` in `src/util/date.py`.
   - ` ```scope `: `src/util/date.py`, `RESULT.md`, `**/__pycache__/` ← the
     verify below imports the module, and the bytecode it writes is part of the
     Builder's delta
   - ` ```tiers `: `gate 1: LOW`
   - Verify: `python -c "import re, src.util.date as d; assert re.fullmatch(r'\d{4}-\d{2}-\d{2}', d.today_kst())"`
3. Dispatch `orchestrate.py build --handoff HANDOFF_DELEGATE.md`.
4. BUILT → read diff, run verify (PASS), accept.
5. Report: `src/util/date.py` +1 function, verify PASS, awaiting optional explicit
   integration/commit authorization on the user's current branch.

## Example — document lane

User: "위임 — resume.md를 A사 JD(jd-a.md)에 맞춰 resume-a.md로 변형해줘."

1. Triage: local files, derived copy only, no outward finalization → LOW, proceed.
2. Write `HANDOFF_DELEGATE.md`:
   - Goal: `resume.md`를 `jd-a.md`의 요구 역량 순서로 재배열한 `resume-a.md` 생성.
     JD와 겹치는 경력을 상단에, 무관한 항목은 축약. 사실 추가·과장 금지 —
     원본에 없는 경력/수치를 만들어내지 말 것.
   - ` ```scope `: `resume-a.md`, `RESULT.md` — **`resume.md`·`jd-a.md`는 넣지
     않는다**(읽기만; scope 밖이라 수정 시도는 hard-block된다).
   - ` ```tiers `: `gate 1: LOW`
   - Verify:
     ```
     python -c "import pathlib; t=pathlib.Path('resume-a.md').read_text(encoding='utf-8'); assert all(h in t for h in ['## 경력','## 기술 스택','## 프로젝트']), 'missing section'; assert len(t)<6000, f'too long: {len(t)}'; assert not any(w in t for w in ['최고의','독보적','완벽한']), 'overclaim'; print('OK')"
     ```
3. Dispatch `orchestrate.py build --handoff HANDOFF_DELEGATE.md`.
4. BUILT → `git diff` 리뷰: 새 파일만 생겼는지, 원본이 그대로인지, **원본에 없는
   사실이 들어가지 않았는지**(문서 lane의 핵심 리뷰 축) 확인 + verify 실행.
5. Report: `resume-a.md` 신규, `resume.md` 무변경, verify PASS, working tree에 남김(커밋 안 함).
