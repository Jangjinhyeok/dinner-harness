# Cross-Vendor Two-CLI Orchestrator


> 2026-09-10 correction: Codex inline is the default. The historical/compatibility material below is superseded by source `content/rules/two-cli-reference.md` and ADR-0022 for current operation. `run` is experimental with explicit vendor/model options and refuses real HIGH implementation. `challenge/build` uses a numeric prefix, bound evidence, and JSON result contract. Builder panel=PASS is not independent review. Consult the dated CODEX-COVERAGE matrix for actual native hook measurements. 2026-10-11 (ADR-0023): the Claude install is 1-CLI inline and no longer installs the orchestrator; `challenge/build` run from a Codex-target install or a repo checkout.

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
`check.py` / `adapters/` toolchain. Design rationale: the ADRs under
`docs/architecture/` (notably ADR-0007 net, ADR-0019 baseline, ADR-0020 routing,
ADR-0021 challenge cap, ADR-0022/0023 current operation).

## Why this restores cross-vendor Two-CLI

The 2026-06 codex adapter recon marked Two-CLI roles **STILL-DEGRADED — 세션페어 없음**
(`CODEX-RECON.md`): Codex has no session-pair concept. (The Codex target now
installs `roles/` and the two-cli/routing references — `harness.toml [targets.codex]`.) The orchestrator manages
the pairing **externally** — each "session" is one headless invocation
(`codex exec` / `claude -p`) the controller makes — so "Two-CLI" here is **two
roles / two CLI engines, not two interactive terminals**. Because the harness
mandates self-contained HANDOFF/RESULT, turns are **stateless** (each reads the
bus + repo fresh), so no session-resume is needed.

`orchestrate.py --help` lists three subcommands, with different support tiers:
- **`build`** — Single-shot Builder pass from an existing handoff file
  (`--handoff`, default `HANDOFF.md`; no headless Architect). It is an **opt-in**
  dispatch run from the session that owns the HANDOFF, using a Codex-target
  install (`<HARNESS_HOME>/orchestrate.py`) or a repo checkout; the Claude install
  is 1-CLI (ADR-0023) and does not ship the orchestrator. The Builder
  vendor/model/effort come from the active routing preset (`routing.toml`, or
  `--routing-preset` for one dispatch) unless `--builder` / `--builder-model` /
  `--builder-effort` override them (model/effort overrides are refused on a HIGH
  gate, ADR-0020). It runs the hard safety net; the dispatching session then
  reviews `RESULT.md` and the diff, and a HIGH gate additionally needs independent
  review and human acceptance. **HIGH acceptance authority is that review + human
  acceptance, not the Builder's self-report** — `run_from_handoff()` treats the
  verdict-based tier gate as advisory (emit-only) for exactly this reason. See
  `content/roles/ROLE_ARCHITECT.md` and `content/rules/two-cli-reference.md`.
- **`challenge`** — Single-shot, read-only `challenger_high` dispatch against a
  draft HANDOFF/ADR (ADR-0020). It writes `CHALLENGE.md` plus a receipt that a
  HIGH `build` checks (see "HIGH pre-design challenge freshness" below), and is
  capped by `--max-challenge-rounds` (default 3, ADR-0021).
- **`run`** — **Experimental legacy loop.** Fully headless: the controller drives
  *both* Architect and Builder (`claude -p` / `codex exec`) through the whole loop
  with explicit `--architect/--builder` vendors and models only (no routing preset
  or effort). `run()` keeps the verdict-based tier gate **hard**, but with
  `--backend real` it **blocks** as soon as the Architect's `tiers` fence is
  missing or declares any HIGH gate ("use challenge/build"), so a real `run` only
  starts on all-LOW declared work. The effective tier still includes the Builder's
  self-report: if the Builder reports a LOW-declared gate as HIGH, the hard gate and
  the HIGH human end sign-off run in real mode too (a Codex JSON result carries no
  panel, so that case is BLOCKED).

For interactive use, launch ordinary `claude` from the work repository. It implements inline by
default (ADR-0023); the `build` path is an opt-in dispatch for bounded work that needs controller checks.

## Quick start

```bash
# Offline smoke — no CLIs needed. Drives a full LOW cycle against a mock vendor.
py -3 orchestrate.py run --goal "add a feature flag reader" --backend mock --yes --repo /path/to/scratch

# Experimental real legacy loop (vendors are explicit; both default to codex).
# Blocks on any HIGH gate.
py -3 orchestrate.py run --goal "..." --architect claude --builder codex \
    --backend real --repo /path/to/work-repo

# Read-only HIGH pre-design challenge of a draft HANDOFF.md.
py -3 orchestrate.py challenge --repo /path/to/work-repo --backend real

# Single-shot Builder from an existing HANDOFF.md; vendor/model/effort come from
# the active routing preset. The dispatching session then reviews RESULT.md + diff.
py -3 orchestrate.py build --repo /path/to/work-repo --backend real
```

Flags (see `py -3 orchestrate.py <sub> --help`):
- `run`: `--goal`, `--architect/--builder {codex,claude}` (both default `codex`),
  `--architect-model/--builder-model`, `--max-cycles N` (default 5),
  `--no-confirm-handoff`, `--yes` (auto-approve all human gates),
  `--dangerously-auto-approve-real`, `--net-dryrun` (safety net warns instead of blocks).
- `build`: `--handoff NAME`, `--task-id`, `--builder {codex,claude}`,
  `--builder-model`, `--builder-effort`, `--routing-preset`, `--net-dryrun`.
- `challenge`: `--handoff NAME`, `--task-id`, `--routing-preset`,
  `--max-challenge-rounds N` (default 3), `--acknowledge-challenge-round-cap`.
- All three: `--repo` (default cwd), `--backend {mock,real}` (default `mock`),
  `--audit-dir`, and `--timeout-s N` (per headless vendor turn; default 1800).

Vendor stdout/stderr is streamed while the
turn runs and captured for parsing. A timeout kills the child and remains
`BLOCKED`; inspect the dispatch repository for surviving output before retrying or
starting a manual fallback.

### Dispatch receipt and audit

`build` writes two content-free JSONL events to the harness-side
`logs/build-audit.jsonl` by default: `attempted` before the Builder work and a
terminal `built`, `blocked`, or `timeout` event after the controller decides the
outcome (the audit vocabulary still maps a legacy `builder_bailed` code, but no
current path produces it). Pass `--audit-dir <path>` to move that runtime
log; do not place it inside `--repo`, because it would pollute the repository
delta the safety net judges. A terminal event records dispatch id, UTC timestamp,
vendor/backend, attempt count, duration, a fixed reason code, and SHA-256 hashes of
the repo path, handoff name, and handoff text. It never records prompts,
HANDOFF/RESULT bodies, changed-file paths, or changed-file contents. The CLI prints `[receipt]` only when that terminal
event is written; its presence is audit evidence, not a substitute for the
Architect's RESULT + diff review or HIGH human end sign-off.

Build and challenge terminal records include `turns`: one observation per backend invocation
(format recovery is a separate invocation). The outer `dispatch_id` identifies the controller
audit; each turn's `dispatch_id` identifies the backend invocation and its watch marker, when
available. Keep both levels. `usage_source` identifies the public event source; `usage_status`
is `reported`, `estimated` when explicitly flagged, or `unknown` when unavailable. Reported
values are backend observations, not verified billing/quota totals. No estimator is added.
Only provided token fields are kept; missing detail is unknown, not zero. Cached input is part
of input, and reasoning (not exposed by this collector) must not be added again to output.
The collector retains the latest completion snapshot without summing repeated events; it does
not establish whether a provider's snapshot is request-local or cumulative across resumed work.
Do not sum attempted/terminal events, required receipt copies and watch markers as separate usage.
For aggregation, deduplicate terminal observations by audit and backend invocation IDs and establish
snapshot scope first. These observations cover only the invoked headless path: interactive parent,
native children and automatic approval usage/inclusion are unknown, not whole-task totals.
Missing usage limits observation only; required challenge evidence still fails closed on persistence
or state-binding failure. No private rollout or transcript collection is used.

## Dispatch the Builder in place

Dispatch from the original repository. A baseline commit is optional
(ADR-0019): the controller takes a pre-turn snapshot (`git stash create`, or
`HEAD` on a clean tree) and ADR-0007's before/after snapshots judge only the
Builder turn's delta, so existing dirt is preserved and not charged to the
Builder. `HANDOFF.md` is already available as the local bus artifact and does not
need copying. Do not edit that repository while the Builder runs.

`<HARNESS_HOME>` is the Codex-target install (`~/.codex`, or `CODEX_HOME`) or this
repository checkout, as in `content/rules/two-cli-reference.md`.

```powershell
# Run from the original repository after HANDOFF.md is approved.
$harnessHome = ($env:USERPROFILE -replace '\\', '/') + '/.codex'   # or CODEX_HOME / repo checkout
$repoPath = (Get-Location).Path -replace '\\', '/'
py -3 "$harnessHome/orchestrate.py" build --repo "$repoPath" --backend real

# Review the Builder's bus and diff in the original repository.
Get-Content -Raw .\RESULT.md
git diff
```

Committing a baseline first still makes an unsuccessful run cheap to discard,
but it is not required. The snapshot delta is not a concurrency boundary, so
the Architect must leave the repository untouched until the Builder finishes.

## The machine-readable bus

On top of the human-readable HANDOFF/RESULT prose, the orchestrator asks each
vendor (via its prompt — no harness file changes required) to emit small fenced
blocks it parses deterministically:

| fence | written by | in | content |
|---|---|---|---|
| ` ```tiers ` | Architect | HANDOFF | `gate N: risk=LOW\|HIGH compute=LOW\|NORMAL\|HIGH` per gate (bare `gate N: LOW\|HIGH` still accepted) |
| ` ```scope ` | Architect | HANDOFF | files the Builder may edit (already read by `scope_check`) |
| result JSON | Builder (Codex, `--backend real`) | final message | output-schema JSON: `schema_version`, `summary`, `gates[]` of `gate`, `status=completed\|blocked\|pending\|needs_review`, `tier`, `self_review`, `verification_claim` |
| ` ```verdicts ` | Builder (compatibility only) | final message | exactly one fence, `gate N: status=completed\|blocked\|pending\|needs_review tier=LOW\|HIGH panel=PASS\|FAIL\|BLOCK` |
| ` ```control ` | Architect (`run` review) | stdout | `verdict: DONE\|NEXT_CYCLE\|BLOCKED` |

The controller renders `RESULT.md` from the parsed Builder result; it is a
human-readable report, not acceptance evidence.

**Fail-closed everywhere**: in `run`, a missing/garbled tier → HIGH; in `build`, a
missing or duplicate `tiers` fence, a duplicate gate or malformed fields is a
handoff contract error → BLOCKED; a missing `control` fence → BLOCKED. A HIGH gate
with no `PASS` verdict blocks only in `run` (hard tier gate); in `build` the tier gate is
advisory and only logs `tier-gate(advisory)`, since review and acceptance belong to the
calling session.

For the single-shot `build` path only, any output-contract error (invalid result
JSON, or a missing/duplicate compatibility `verdicts` fence) gets exactly one
**read-only result-format recovery turn**. It may not edit files or rerun
implementation; its report is appended after the preserved `RESULT.md`, and the
turn is net-scanned like any other. Any implementation delta during recovery, a
safety-net hit, or a second contract error returns `BLOCKED`.

## Safety model (the non-negotiable part)

Automating the relay removes the human's incidental glance, so the tier gates are
wired into the controller — and every ambiguity fails **closed**:

- **Controller-side deterministic net** — after the Builder turn, the controller
  reruns the harness `scope_check` + `secret_scan` handlers **verbatim** (as
  subprocesses, fed a synthesized payload per changed file) in `enforce`. This
  holds **regardless of which vendor built** — Codex native hooks were measured
  advisory on 0.147–0.151 (`CODEX-COVERAGE.md` §6: PreToolUse exit 2 did not veto
  `apply_patch`), and the net does not depend on native-hook enforcement either
  way. A hook block (exit
  2) fails the cycle; in
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
level (a sandbox), not here.

**What the net does not see**, even from an honest Builder: the main whole-tree
`git status` query omits files matched by `.gitignore` (including a global
`core.excludesFile`). For the declared fence only, the controller adds a second
`--ignored=traditional -uall` query, merges and deduplicates its paths, and
then applies the changeset ceiling. This closes the **secret and observation
axes** for ignored writes inside the fence; it does not close the **scope axis**,
because ignored writes outside the fence remain invisible. Whole-tree
`--ignored` is still rejected — on repos where the ceiling exists it would
report `node_modules` and refuse every dispatch — so ignore rules remain part
of the safety boundary. Ignored files are not included by `git stash create`:
they can be detected and blocked, but cannot be rolled back by that snapshot.
A fence that names a large ignored directory can also hit the existing
`max_files` ceiling. And a block is only a **partial rollback**: on a scope
block the controller restores the scope-blocked **tracked** paths from the
pre-turn snapshot; paths the snapshot lacks (untracked, ignored) and
secret-blocked paths are left in place and reported.

- **Tier-gate enforcement (`run()` only — hard)** — effective tier = the higher of
  the Architect's declared tier and the Builder's self-reported tier; a
  **missing/garbled ```tiers``` fence makes every gate HIGH**. Any `FAIL`/`BLOCK`
  panel fails any tier; a HIGH gate needs an explicit `panel=PASS`; a declared gate
  with no verdict — or no gates at all — fails closed. With `--backend real`,
  `run()` blocks before the Builder on any declared HIGH gate; this HIGH branch still
  runs in real mode when the Builder self-reports HIGH on a LOW-declared gate. **In `build`/`run_from_handoff()` this
  same gate is advisory (emit-only)** — a HIGH gate's real acceptance authority is
  the dispatching session's review, independent review and human acceptance, not
  this panel value. See the subcommand list above.
- **END boundary, tier-driven (`run`)** — the Architect review runs **first**; on `DONE`
  a **LOW** cycle auto-completes (result reported, no human gate, per
  autonomy-policy), while a **HIGH** cycle stops for a human end sign-off before
  the change is accepted. The human never signs off on a cycle the Architect then
  rejects.
- **`--yes` guard** — auto-approving all gates is refused on a `--backend real`
  run unless `--dangerously-auto-approve-real` is passed explicitly.

**One of the two layers, not both.** The handlers carry an `always_block` layer
protecting the harness install itself (`settings.json`, `hooks/`). It is
anchored on the **live installs** (`~/.claude`, `CODEX_HOME` or `~/.codex`, and the
working directory's `.codex`), while the net normally submits
only paths inside the work repo — so in a typical controller dispatch that layer
never fires and the fence is the whole of the scope enforcement. **Not
universal:** the working directory's `.codex` sits inside the work repo, so a Builder
edit to protected `<repo>/.codex/` paths (`hooks.json`, `config.toml`, `rules/`) is
blocked by always-block even when the fence lists it. Also, `git status` reports the
whole git repo, so when the git root sits ABOVE the work repo, paths outside it are
submitted in absolute form (that is `_repo_relative`'s deliberate behaviour) and the
always-block layer can match there as well. The direction is safe — it only ever adds a block — but "exactly one
layer is live here" is a rule of thumb, not an invariant. That is deliberate: the
alternatives anchor it on the work repo (making any target repo with a root
`settings.json` undispatchable) or on the handler's own directory (making the
harness repo unable to edit its own hooks). It does mean "reruns the handlers
verbatim" above describes the *mechanism*, not two live layers.

> **Install after every change here.** After touching anything under
> `assets/claude/hooks/`, `orchestrator/`, or `orchestrate.py`, refresh the live
> installs: `py -3 refresh.py --apply`, or `py -3 install.py --target codex --allow-live`
> (plus `--target claude --allow-live` for hook changes). The orchestrator is
> installed only by the Codex target (`harness.toml [targets.codex].copy`); the
> Claude target retires it (`retired_dests`). A live dispatch
> (`py -3 "<HARNESS_HOME>/orchestrate.py" build --repo "<ABSOLUTE_REPO_PATH>"`) runs the copy
> under `<HARNESS_HOME>` — so a fix that stays in the repo is not in force there
> unless `<HARNESS_HOME>` is the repo checkout. `py -3 check.py` will
> tell you: its install-drift axis lists every file whose live copy differs from
> the repo. It reports, it does not install.
>
> **To back out**, re-install from the previous commit — `install.py` overwrites
> in place and keeps no backup, so there is no other undo:
> `git stash && py -3 install.py --target <claude|codex> --allow-live && git stash pop`
> (or check out the previous commit and install from there). This matters more
> than usual for changes touching `hooks/lib/common.py`, which **every** handler
> imports: a bad copy there breaks every interactive hook at once. Copying the
> live tree aside first (`cp -r ~/.claude ~/.claude.bak`, likewise `~/.codex`) is
> the cheap insurance.

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
    diff regardless; Codex-side native hooks need 0.140+ and were measured
    advisory on 0.147–0.151 (`CODEX-COVERAGE.md` §6).

## HIGH pre-design challenge freshness

`CHALLENGED` means receipt of a design critique, not review PASS, post-implementation
independent review, or human acceptance. Those HIGH boundaries remain unchanged.

Receipts bind repo/task/HANDOFF/routing policy plus a `git-relevant-state.v1`
snapshot. The scope is the **entire tracked and non-ignored untracked Git tree**,
including read dependencies outside an incomplete HANDOFF write scope. HEAD tree
entries, index mode/object/stage/path entries, and working paths/bytes/executable
bits are separate digest inputs. Additions, deletions, renames and index-only
changes invalidate evidence. Commit identity alone is not an input: identical
source trees, empty commits and report-only commits can reuse evidence.

Only root `RESULT.md` and `CHALLENGE.md` are reserved output exclusions in every
layer; nested names are included. Audit/execution records and temporary response
schemas remain outside the target repo. No arbitrary logs directory is exempted.
Receipts contain only the snapshot schema and SHA-256, never source bytes or a
path list. Ignored untracked files, Git internals and external dependencies are
outside the contract. Tasks relying on those inputs must bring required non-secret
inputs into Git-visible source and re-challenge; this evidence cannot attest to
their freshness. Tracked files remain included regardless of ignore rules.
Symlinks/junctions, submodules, opaque directories, unreadable files, Git failures,
and repositories without HEAD fail closed.

Two consecutive snapshots must agree. The controller compares state and HANDOFF
before/after the challenge, and refuses successful evidence on changes. HIGH builds
check evidence during profile resolution and again after preflight just before
Builder dispatch. This is not a filesystem lock: transient changes restored between
observations or concurrent writes after the final check are not prevented. Quiesce
other writers while using this workflow.

Legacy receipts without `code_state`, or with another snapshot schema, cannot
satisfy HIGH evidence. History is retained and still counts toward the existing
round cap; re-challenge and existing cap acknowledgement rules apply.

Run `python -m unittest orchestrator.tests.test_challenge_state` for temporary Git
and actual-adapter-generated install regressions. Model transport is mocked; these
tests make no live model or live installation claim.

## Layout

```
orchestrate.py            CLI entry (repo root, like install.py / check.py)
orchestrator/
  controller.py           state machine + prompt builders + tier-gate + human gate
  bus.py                  HANDOFF/RESULT I/O + ```tiers```/```verdicts```/```control``` parsing
  vendors.py              Backend interface + Mock + Claude/Codex (real)
  safety.py               controller-side net (reuses harness hook handlers)
  config.py               config dataclass + defaults
  routing.py              routing.toml preset → builder/challenger profile resolution
  receipt.py              content-free dispatch audit receipts
  tests/                  offline unittest (mock + real handlers)
```

`orchestrate.py` and this package are installed only by the Codex target
(`harness.toml [targets.codex].copy`, into `<HARNESS_HOME>` = `~/.codex` or
`CODEX_HOME`); the Claude target is 1-CLI (ADR-0023) and lists them in
`retired_dests`, so `check.py` reports any leftover copy under `~/.claude`.
Dispatch runs the quoted absolute-path `<HARNESS_HOME>/orchestrate.py build` form
(or a repo checkout; see `content/rules/two-cli-reference.md`). They are not
skills/agents/hooks, so they do not appear in the harness capability catalog, but
`check.py`'s install-drift axis does compare them for the Codex target — so a
change that sits in the repo uninstalled shows up there as drift.
