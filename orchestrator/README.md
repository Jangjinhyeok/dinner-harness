# Cross-Vendor Two-CLI Orchestrator

The external, cross-process sibling of the `autonomous-loop` skill. It drives an
**Architect** vendor and a **Builder** vendor (Codex / Claude, either direction)
through the `HANDOFF.md` / `RESULT.md` file bus, **replacing the human relay**.
The human is invoked only at the three boundaries risk-tiered autonomy keeps:

1. **START** — the intent (and an optional one-time HANDOFF confirmation).
2. **HIGH sign-off** — *only* when a gate is HIGH-tier.
3. **END** — final acceptance.

Everything between (Architect design, Builder implement, panel review, Architect
review, cycle looping) is automated. Stdlib only; mirrors the `install.py` /
`check.py` / `adapters/` toolchain. Design rationale: this conversation's design
section (a future `docs/architecture/` ADR).

## Why this restores cross-vendor Two-CLI

The codex adapter marks Two-CLI roles **STILL-DEGRADED — 세션페어 없음**
(`CODEX-RECON.md`): Codex has no session-pair concept. The orchestrator manages
the pairing **externally** — each "session" is one headless invocation
(`codex exec` / `claude -p`) the controller makes — so "Two-CLI" here is **two
roles / two CLI engines, not two interactive terminals**. Because the harness
mandates self-contained HANDOFF/RESULT, turns are **stateless** (each reads the
bus + repo fresh), so no session-resume is needed.

Two entry points:
- **`run`** — fully headless: the controller drives *both* Architect and Builder
  (`claude -p` / `codex exec`) through the whole loop.
- **`build`** — single-shot Builder pass from an existing `HANDOFF.md` (no headless
  Architect). This is what an **interactive Claude Architect auto-dispatches** after
  an in-session HANDOFF approval (orchestrated single-pane — the default pairing's
  flow); it runs the Codex Builder + the hard safety net, then the in-session Claude
  reviews `RESULT.md`. See `roles/ROLE_ARCHITECT.md` "Builder 자동 dispatch".

## Quick start

```bash
# Offline smoke — no CLIs needed. Drives a full LOW cycle against a mock vendor.
py -3 orchestrate.py run --goal "add a feature flag reader" --backend mock --yes --repo /path/to/scratch

# Real cross-vendor run (default: Claude=Architect, Codex=Builder).
py -3 orchestrate.py run --goal "..." --architect claude --builder codex \
    --backend real --repo /path/to/work-repo

# Single-shot Builder from an existing HANDOFF.md (what the interactive Claude
# Architect auto-dispatches — orchestrated single-pane). Codex builds headless;
# the in-session Claude then reviews RESULT.md.
py -3 orchestrate.py build --repo /path/to/work-repo --backend real
```

Flags: `--architect/--builder {codex,claude}`, `--architect-model/--builder-model`,
`--max-cycles N`, `--no-confirm-handoff`, `--yes` (auto-approve all human gates),
`--net-dryrun` (safety net warns instead of blocks).

## The machine-readable bus

On top of the human-readable HANDOFF/RESULT prose, the orchestrator asks each
vendor (via its prompt — no harness file changes required) to emit small fenced
blocks it parses deterministically:

| fence | written by | in | content |
|---|---|---|---|
| ` ```tiers ` | Architect | HANDOFF | `gate N: LOW\|HIGH` per gate |
| ` ```scope ` | Architect | HANDOFF | files the Builder may edit (already read by `scope_check`) |
| ` ```verdicts ` | Builder | RESULT | `gate N: status=… tier=LOW\|HIGH panel=PASS\|FAIL\|BLOCK` |
| ` ```control ` | Architect (review) | stdout | `verdict: DONE\|NEXT_CYCLE\|BLOCKED` |

**Fail-closed everywhere**: a missing/garbled tier → HIGH; a missing `control`
fence → BLOCKED; a HIGH gate with no `PASS` verdict → blocked.

## Safety model (the non-negotiable part)

Automating the relay removes the human's incidental glance, so the tier gates are
wired into the controller — and every ambiguity fails **closed**:

- **Controller-side deterministic net** — after the Builder turn, the controller
  reruns the harness `scope_check` + `secret_scan` handlers **verbatim** (as
  subprocesses, fed a synthesized payload per changed file) in `enforce`. This
  holds **regardless of which vendor built** — it compensates for a Codex 0.111
  Builder having no native hooks. A hook block (exit 2) fails the cycle; in
  `enforce` a handler that is **missing or cannot launch also fails the cycle**
  (a net you cannot run is not a pass), and a changeset that cannot be
  determined (git unavailable) fails closed too.
- **Tier-gate enforcement** — effective tier = the higher of the Architect's
  declared tier and the Builder's self-reported tier; a **missing/garbled
  ```tiers``` fence makes every gate HIGH**. Any `FAIL`/`BLOCK` panel fails any
  tier; a HIGH gate needs an explicit `panel=PASS`; a declared gate with no
  verdict — or no gates at all — fails closed.
- **END boundary, tier-driven** — the Architect review runs **first**; on `DONE`
  a **LOW** cycle auto-completes (result reported, no human gate, per
  autonomy-policy), while a **HIGH** cycle stops for a human end sign-off before
  the change is accepted. The human never signs off on a cycle the Architect then
  rejects.
- **`--yes` guard** — auto-approving all gates is refused on a `--backend real`
  run unless `--dangerously-auto-approve-real` is passed explicitly.

## Status & build-time verification

- **Mock core — done & tested.** `py -3 -m unittest discover -s orchestrator/tests`
  exercises the full loop, the tier gate, and the real safety-net handlers offline.
- **Real backends — scaffold.** `ClaudeBackend` (`claude -p`) / `CodexBackend`
  (`codex exec`) are implemented but the exact flags/output formats and the
  non-interactive permission posture differ across CLI versions. **Verify on the
  machine that has both CLIs authenticated** before trusting a `--backend real`
  run:
  - `claude -p` output format / `--permission-mode` for an autonomous Builder.
  - `codex exec` sandbox/approval flags (`--full-auto` etc.) and `--cd`.
  - **Precondition**: cross-vendor Codex work wants **Codex ≥0.140** (0.111 lacks
    hooks/subagents — `CODEX-RECON.md` §b). The controller net covers the Builder
    diff regardless, but Codex-side native safety only exists on 0.140+.

## Layout

```
orchestrate.py            CLI entry (repo root, like install.py / check.py)
orchestrator/
  controller.py           state machine + prompt builders + tier-gate + human gate
  bus.py                  HANDOFF/RESULT I/O + ```tiers```/```verdicts```/```control``` parsing
  vendors.py              Backend interface + Mock + Claude/Codex (real)
  safety.py               controller-side net (reuses harness hook handlers)
  config.py               config dataclass + defaults
  tests/                  offline unittest (mock + real handlers)
```

This tool is repo-level tooling — it is **not** installed into `~/.claude` /
`~/.codex` (like `install.py`), so it does not affect the harness capability
catalog or `check.py`.
