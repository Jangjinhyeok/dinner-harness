# Cross-Vendor Two-CLI Orchestrator

[한국어](README.ko.md) | **English**

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
`--net-dryrun` (safety net warns instead of blocks), and `--timeout-s N` (per
headless vendor turn; default 1800). Vendor stdout/stderr is streamed while the
turn runs and captured for parsing. A timeout kills the child and remains
`BLOCKED`; inspect the Builder worktree for surviving output before retrying or
starting a manual fallback.

### Dispatch receipt and audit

`build` writes two content-free JSONL events to the harness-side
`logs/build-audit.jsonl` by default: `attempted` before the Builder work and a
terminal `built`, `blocked`, `timeout`, or `builder_bailed` event after the
controller decides the outcome. Pass `--audit-dir <path>` to move that runtime
log; do not place it inside `--repo`, because it would pollute the worktree
delta the safety net judges. A terminal event records dispatch id, UTC timestamp,
vendor/backend, attempt count, duration, a fixed reason code, and SHA-256 hashes of
the repo path, handoff name, and handoff text. It never records prompts,
HANDOFF/RESULT bodies, changed-file paths, or changed-file contents. The CLI prints `[receipt]` only when that terminal
event is written; its presence is audit evidence, not a substitute for the
Architect's RESULT + diff review or HIGH human end sign-off.

## Isolate the Builder in a linked worktree

For a real Builder dispatch, prefer a dedicated linked worktree. It is a
process-level boundary: Architect edits in the primary worktree cannot be
included in the Builder's `git status` snapshots or its controller-side net.

```powershell
# Run from the Architect's primary worktree after HANDOFF.md is approved.
$builderWorktree = "../repo-build"
git worktree add -b builder/my-task $builderWorktree HEAD
Copy-Item -LiteralPath .\HANDOFF.md -Destination "$builderWorktree\HANDOFF.md"

py -3 ~/.claude/orchestrate.py build --repo $builderWorktree --backend real

# Review the Builder's bus and diff in the Builder worktree, not the primary one.
Get-Content -Raw "$builderWorktree\RESULT.md"
git -C $builderWorktree diff
```

`HANDOFF.md` and `RESULT.md` are local bus artifacts, so a linked worktree does
not receive the Architect's uncommitted handoff automatically. Copy the approved
handoff before dispatch; do not copy a Builder-modified handoff back. Builder
output remains in the Builder worktree for review and subsequent acceptance by
the repository's normal change-integration workflow.

Linked worktrees share the Git common directory. While the Builder is running,
do not `git stash`, change `core.excludesFile`, or edit `.git/info/exclude` in
the primary worktree: those shared witness inputs can correctly make the Builder
net fail closed. The net deliberately reads `rev-parse --git-common-dir`, rather
than `--git-dir`, because a linked worktree's per-worktree git dir has no
`info/exclude`.

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

For the single-shot `build` path only, a Builder that made an in-scope,
net-scanned implementation change but omitted ` ```verdicts ` receives one
**verdict-only recovery turn**. It may not change files; its fence is appended
to the already-written human-readable `RESULT.md` and is itself safety-scanned.
Any recovery implementation delta, no initial implementation delta, a safety-net
hit, or a second malformed recovery still
returns `BLOCKED`.

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
  determined fails closed too — which means **git answering non-zero**, not only
  git being absent: `git status` in a non-repository exits 128 with empty
  output, and reading that as "clean tree" would run the net over nothing. The
  fence comes from the handoff the build was actually dispatched from
  (`cfg.handoff_name`, not a hardcoded `HANDOFF.md`) and is **pinned into the
  handler's environment** rather than re-read from disk per file; a handoff
  carrying **no ```scope``` fence** — or one holding only comments — is refused
  in `enforce` **before the Builder turn starts**, since an unbounded changeset
  is a net that cannot run. A handler that reaches no verdict — watchdog or
  crash — is a block here, not the interactive fail-open.
- **The evidence itself is checked.** `git status` is the net's only witness and
  the Builder can edit the witness without touching a tracked file: a
  `git commit` or `stash`, an ignore rule (`.git/info/exclude`,
  `core.excludesFile`), or an `assume-unchanged`/`skip-worktree` index bit each
  removes a path from *both* snapshots. All of them are fingerprinted across the
  turn and any movement fails the cycle. The commit case is the one that is not
  even adversarial — the Builder is told not to commit, which is why it needs
  catching. This narrows the hole; see the threat model below.
- **Directories in the snapshot are refused.** `-uall` expands untracked
  directories per file but stops at a repository boundary, so a nested git repo
  arrives as one opaque entry whose contents would reach `secret_scan` as an
  empty string. The cycle fails rather than vet nothing — checked against the
  snapshots (and once before the turn), not the delta, because a nested repo
  that was already dirty at dispatch compares equal on both sides and would
  otherwise never be seen. A repo with a dirty nested repo or submodule cannot
  be dispatched until it is cleaned, committed, or ignored.
- **The net's git calls ignore `GIT_DIR`/`GIT_WORK_TREE`/`GIT_INDEX_FILE`/
  `GIT_COMMON_DIR`** — inherited, they point git at a different repository and
  the work repo's own changes disappear from the changeset. These are routinely
  set inside git hooks and `git rebase --exec`.
- **The net judges the DELTA of the Builder's turn** — `collect_changeset` is
  snapshotted before and after, and only paths whose content differs are
  submitted. Pre-existing dirt (the untracked handoff, an ADR the Architect
  wrote at step 8, yesterday's scratch file) is not the Builder's work and is
  not charged to it. The delta is keyed on the **union** of both snapshots, so a
  path that *leaves* `git status` is judged too: deleting an **untracked** file
  produces no `D` entry, it simply vanishes, and an after-only comparison would
  never see the one edit git cannot undo. Exactly two paths are **scope**-exempt
  — `RESULT.md` and the dispatched handoff, the two files the controller is
  answerable for rather than the Builder. Neither is **secret**-exempt: both are
  appended to the changeset every cycle, so `secret_scan` sees them even when
  the delta drops them (an unchanged handoff sits in both snapshots;
  `RESULT.md` is routinely `.gitignore`d). Nothing else is exempt from either.
- **Handoff tamper stop** — the controller holds the text it dispatched and
  compares after the turn: any drift fails the cycle. **Deletion counts as
  drift**, and so does a file that no longer decodes. Separately, the fence the
  handler enforces is **pinned by the controller** (passed in the environment)
  rather than re-read from disk per file, which closes the window between that
  one-shot comparison and the 2×N handler launches that follow.
- **Changeset ceiling** — `-uall` lists untracked files individually, so a
  target repo with a thin `.gitignore` can produce thousands of paths at two
  handler subprocesses each. Past `_MAX_CHANGESET` the cycle fails closed rather
  than stall for minutes. The ceiling is applied to the **paths git reported,
  before any file content is read**, so the cost it exists to bound is never
  paid first.
- **Handler budget** — the hook handlers carry a 200 ms watchdog that answers
  *allow* when it fires, which is right for an interactive Claude hook and wrong
  here: the net passes whole file contents. For the net the budget is raised and
  a timeout is made to mean **block**, so a change the handlers could not read
  is never one they approved.

**Threat model — what this net is for.** It constrains an **over-reaching**
Builder: one that misreads the spec, refactors past its remit, edits a file it
was told to leave alone, or pastes a key. That is the failure mode a headless
agent actually produces, and against it the net is a hard gate.

It does **not** contain an **evading** Builder, and cannot. The Builder runs a
shell in the same tree the net lives in; anything it can reach, it can reach
first. The `.git/info/exclude` and index-bit fingerprints above close the two
cheapest evasions, not the class. Do not read a `BUILT` as proof that nothing
else happened — read it as "nothing the net can see went wrong". If you need a
containment boundary rather than a review aid, that belongs at the process
level (a worktree the Builder cannot escape, a sandbox), not here.

**What the net does not see**, even from an honest Builder: files matched by
`.gitignore` (including a global `core.excludesFile`) never appear in
`git status`. Widening to `--ignored` was rejected — on the repos the ceiling
exists for it would report `node_modules` and refuse every dispatch — so treat
the target repo's ignore rules as part of the safety boundary. And a block is a
**refusal, not a rollback**: an out-of-fence deletion is reported, not undone.

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

**One of the two layers, not both.** The handlers carry an `always_block` layer
protecting the harness install itself (`settings.json`, `hooks/`). It is
anchored on the **live install** (`~/.claude`), while the net normally submits
only paths inside the work repo — so in a typical controller dispatch that layer
never fires and the fence is the whole of the scope enforcement. **Not
universal:** `git status` reports the whole git repo, so when the git root sits
ABOVE the work repo, paths outside it are submitted in absolute form (that is
`_repo_relative`'s deliberate behaviour) and the always-block layer can match
after all. The direction is safe — it only ever adds a block — but "exactly one
layer is live here" is a rule of thumb, not an invariant. That is deliberate: the
alternatives anchor it on the work repo (making any target repo with a root
`settings.json` undispatchable) or on the handler's own directory (making the
harness repo unable to edit its own hooks). It does mean "reruns the handlers
verbatim" above describes the *mechanism*, not two live layers.

> **Install after every change here.** After touching anything under
> `assets/claude/hooks/`, `orchestrator/`, or `orchestrate.py`, re-run
> `py -3 install.py --target claude --allow-live` (and `--target codex`). All
> three are installed, and the live dispatch
> (`py -3 ~/.claude/orchestrate.py build`) runs the **installed** copy — so a fix
> that stays in the repo is a fix that is not in force. `py -3 check.py` will
> tell you: its install-drift axis lists every file whose live copy differs from
> the repo. It reports, it does not install.
>
> **To back out**, re-install from the previous commit — `install.py` overwrites
> in place and keeps no backup, so there is no other undo:
> `git stash && py -3 install.py --target claude --allow-live && git stash pop`
> (or check out the previous commit and install from there). This matters more
> than usual for changes touching `hooks/lib/common.py`, which **every** handler
> imports: a bad copy there breaks every interactive hook at once. Copying the
> live tree aside first (`cp -r ~/.claude ~/.claude.bak`) is the cheap
> insurance.

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

`orchestrate.py` and this package **are** installed into `~/.claude` by
`install.py` (see `harness.toml`), because the default dispatch documented in
`ROLE_ARCHITECT.md` runs `py -3 ~/.claude/orchestrate.py build`. They are not
skills/agents/hooks, so they do not appear in the harness capability catalog and
`check.py` does not look at them — which is exactly why a change here can sit in
the repo, unnoticed, while the live lane keeps running the old copy.
