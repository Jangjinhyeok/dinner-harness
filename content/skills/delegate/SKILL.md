---
name: delegate
description: Lightweight delegation lane — hand a small, single-purpose LOW-risk coding task to the Codex Builder headless (orchestrate.py build) and review the result inline, skipping the full Architect ceremony (mode entry, gated HANDOFF, ADR). Use when the user wants a self-contained change built by Codex without the heavy ritual — "위임", "이거 codex/코덱스로 시켜", "delegate this", "quick build". HIGH-risk or multi-file/multi-gate/design work escalates to architect mode instead.
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
  anything broad/irreversible;
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
   result. Changes are STAGED, not committed — the user owns the commit.

## Guardrails

- **LOW-only** — HIGH or multi-gate escalates to architect mode; never dispatched here.
- **Scope fence is mandatory** — it is the safety boundary the controller-side net
  enforces (a Codex Builder fires no Claude hooks, so this net is the only
  automatic defense).
- **Never clobber `HANDOFF.md`** — always dispatch from `HANDOFF_DELEGATE.md`.
- **Default pairing only** — Claude=Architect dispatches Codex=Builder. If codex is
  unavailable/unauthenticated, fall back to manual.
- **No commit/merge** — LOW is report-only; the user commits.

## Example

User: "위임 — src/util/date.py에 KST 기준 오늘 날짜를 'YYYY-MM-DD'로 주는 today_kst() 추가해줘."

1. Triage: pure local util, no HIGH signal, single file → LOW, proceed.
2. Write `HANDOFF_DELEGATE.md`:
   - Goal: add `today_kst() -> str` returning KST today as `YYYY-MM-DD` in `src/util/date.py`.
   - ` ```scope `: `src/util/date.py`, `RESULT.md`
   - ` ```tiers `: `gate 1: LOW`
   - Verify: `python -c "import re, src.util.date as d; assert re.fullmatch(r'\d{4}-\d{2}-\d{2}', d.today_kst())"`
3. Dispatch `orchestrate.py build --handoff HANDOFF_DELEGATE.md`.
4. BUILT → read diff, run verify (PASS), accept.
5. Report: `src/util/date.py` +1 function, verify PASS, staged (not committed).
