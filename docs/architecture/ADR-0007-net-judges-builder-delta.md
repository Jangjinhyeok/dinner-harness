# ADR-0007: The controller net judges the Builder's delta, not the dirty tree

- **Status:** Accepted (2026-08-06) — merged to `main` in PR #12 the same day.
  Accepted by the user's decision, **not** by a round-10 panel: the round-9 fixes
  below were never juried, and that gap is recorded rather than closed. The
  install gate stands separately — see Follow-ups.
- **Date:** 2026-08-05 (accepted 2026-08-06)
- **Deciders:** Architect session (dinner-harness); accepted by the user

## Context

The controller-side safety net (`orchestrator/safety.py`) is the **only automatic
defense** in the default pairing: a headless Codex Builder fires no Claude hooks,
so `scope_check` + `secret_scan` run from the controller instead. Two defects
found on 2026-08-05 while exercising the `/delegate` document lane:

1. **The scope fence was inert in `/delegate`.** `scope_check.py` hardcoded
   `HANDOFF.md`; `/delegate` always dispatches from `HANDOFF_DELEGATE.md`. The
   handler found no file and, by design, **failed open**. Measured: identical
   out-of-scope changeset, `blocked=True` under `HANDOFF.md`, `blocked=False`
   under `HANDOFF_DELEGATE.md`. Every run of that lane had no scope enforcement.
   `secret_scan` was unaffected. `check.py` could not see this — it was repo-only
   and did not compare the repo against the installed `~/.claude`. (Closed on
   2026-08-06 by its install-drift axis; that hole is what let the fix sit
   uninstalled and unnoticed twice.)

2. **A successful build could be reported `BLOCKED`.** A codex CLI finished the
   work, wrote correct files, and never exited; `timeout_s=1800` fired and the
   changeset was discarded. (Deferred — see Follow-ups.)

Fixing (1) turned out to be the hard part, and not for the reason it looked like.
Five `adversarial-review` rounds (4 jurors: code-reviewer / architect / tdd-guide
/ tools-programmer, default-REJECT, HIGH tier ⇒ unanimity required) never
reached PASS. Each round the panel found that **turning the fence on broke
legitimate dispatches**, in a new place:

- R1: `collect_changeset` sweeps `git status`, which includes the untracked
  `HANDOFF_DELEGATE.md` Claude writes seconds before dispatch. The fence lists
  files to *edit*, never the spec — so every dispatch blocked on its own handoff.
- R3: guarding the resulting tamper check with `if on_disk.strip()` let a Builder
  **delete** the handoff; the handler then found no fence and failed open. PoC
  reproduced `BUILT` with an out-of-scope file surviving.
- R5: the same root cause, third face — the net judges **everything dirty**, not
  what the Builder did. `ROLE_ARCHITECT.md` step 8 tells the Architect to write
  an ADR *before* dispatching at step 9. That ADR is untracked and correctly
  absent from the fence, so the architect lane blocks on its own protocol.
  Reproduced: `BLOCKED — safety net blocked the changeset`.

Each round I patched the specific face (exempt the handoff; then exempt bus files
by name; then earn the exemption via a pre-turn snapshot of three filenames). All
three were the same mistake at increasing cost: **special-casing a general
problem.** The only operator workaround for the residual cases is to widen the
```scope``` fence to cover files the Builder must not write — which converts the
safety boundary into a "don't look here" list, i.e. weakens the net to keep it
usable. That is the failure mode worth designing away from.

Additional constraint discovered while testing: plain `git status --porcelain`
collapses an untracked directory to one entry (`src/`), so a Builder creating
`src/feature.py` was judged as having written `src/` — matching no fence entry.
Fixed with `-uall`, which makes per-file listing (and therefore changeset size) a
real concern on repos with a thin `.gitignore`.

## Decision

**The net judges the delta of the Builder's turn.** The controller snapshots
`collect_changeset(repo)` immediately before `builder.invoke(...)` and again
after, and submits only paths whose content changed. Pre-existing dirt is not the
Builder's work and is not charged to it.

## Implementation Guidelines

- `_build_and_gate` takes `before` **before** the builder turn; after the turn it
  computes the delta over the **union** of both snapshots' paths, using a unique
  `_ABSENT` sentinel so a path present on only one side always reads as changed.
  The union is not a detail: a path can *leave* `git status` entirely — deleting
  an **untracked** file produces no `D` entry, it simply vanishes — so an
  `after`-only comparison never constructs a `Change` for it and the fence never
  sees the one edit git keeps no object for. That was the document lane's whole
  promise failing on its most destructive counter-example, reported `BUILT`.
  Either snapshot being `None` fails closed in `enforce`.
- **`None` means "git did not answer", and that includes a non-zero exit.**
  `git status` in a non-repository exits 128 with *empty stdout* and raises
  nothing, so catching only exceptions read "clean tree" out of "there is no
  repository here" — the net ran zero handlers and the run reported `BUILT`.
  Same shape for `detected dubious ownership` (routine on Windows), a corrupt
  `.git`, and an `index.lock` conflict. Every git call goes through `_git_out`,
  which checks `returncode`.
- **Resolve reported paths against the git root, not against `cfg.repo`.**
  `git status` reports repo-root-relative paths regardless of `-C`. When the
  work repo is a *subdirectory* of the git repo, resolving against it found
  nothing: every content read came back `""`, so `secret_scan` vetted an empty
  string and a key shipped, while `scope_check` was handed a doubled path
  (`docs/resume/docs/resume/x.md`) and false-blocked work that *was* in the
  fence. The controller asks `git rev-parse --show-toplevel` and re-expresses
  each path relative to `cfg.repo`; anything outside it keeps its absolute form
  and therefore matches no fence entry, which is the correct answer.
- `collect_changeset` uses `git status --porcelain -uall -z` — the net judges
  files, so it must be given files, not collapsed directories.
- **The collector reports every path the Builder touched, deletions and both
  ends of a rename included**, with `content=""` for anything not readable as a
  file. Skipping `D` entries put `rm original.md` outside the fence entirely,
  which is precisely the guarantee `delegate/SKILL.md` sells for the document
  lane ("keep the source out of the fence and `scope_check` hard-blocks any edit
  to it"). Taking only the target of a rename had the same shape: move an
  out-of-fence file away and nothing was judged. Delta symmetry makes this safe
  to enable — a deletion that predates the turn reads `""` in *both* snapshots
  and drops out, so the operator's own `rm` is not charged to the Builder.
- **`-z` is for the unquoting, not the separator.** By default git C-quotes any
  non-ASCII path (`"\352\262\275...md"`); that spelling resolves to no file, so
  the content read comes back empty — `secret_scan` scans nothing — while the
  fence is asked about the escaped name and rejects a path the operator *did*
  whitelist. The document lane's files are routinely Korean-named, so this was
  its ordinary case. Under `-z` the rename source is the next NUL field rather
  than an `" -> "` suffix, and git's UTF-8 bytes are decoded explicitly
  (`errors="replace"`; an undecodable name then matches no fence entry, i.e.
  fails closed).
- **Handler I/O is pinned to UTF-8 at BOTH ends** — `encoding="utf-8"` on the
  subprocess, and `PYTHONUTF8`/`PYTHONIOENCODING` in the child env — instead of
  `text=True`'s locale codec. Observed: a handler answering in UTF-8 while the
  parent decoded cp949 killed the reader thread, which discards the stderr
  naming the violated rule; the change still blocked, the operator just got a
  bare `exit 2`. One correction: the *stdin* half is not a real failure mode
  (`json.dumps` defaults to `ensure_ascii=True`, so the payload is ASCII). One
  retraction: an earlier revision of this ADR called the child-side pair
  unverifiable belt-and-braces. That was wrong, and wrong because the test
  asserted a substring (`scope_check:block`) that survives the corruption —
  removing the pair turns `금지🚀.md` into `����\U0001f680.md` in the block
  reason. Both halves are load-bearing and both are now pinned by assertions on
  the full reason text.
- **The scope fence is pinned by the controller**, passed to the handler in the
  environment rather than re-read from disk. The tamper stop is a single
  comparison, but the scan that follows is two subprocesses per changed file —
  seconds to minutes — and the handler re-read the fence on every one of them. A
  Builder that rewrote the handoff inside that window was rewriting the rule it
  was about to be judged by, and nothing looked again. Reproduced end-to-end.
  An inherited `CLAUDE_SCOPE_FENCE` is cleared rather than honoured.
- **Fence matching is path-aware.** Directory entries match on a **boundary**
  (`src/` no longer admits `src-evil.py`, `srcret.env`, `src.py` — `resolve()`
  drops the trailing separator, so a bare `startswith` compared spellings, not
  paths), and glob `*` no longer crosses `/` (`src/*.py` no longer admits
  `src/deep/nested/evil.py`); `**` keeps the recursive meaning. Both predate
  this change — but this change is what makes the fence load-bearing in
  `/delegate`, so they would have shipped as live holes rather than dormant ones.
  Third face, found while documenting the artifact guidance: the classifier
  checked the trailing separator *before* glob characters, so `**/__pycache__/`
  meant a literal directory named `**` and matched nothing — silently, which is
  what trains an operator to widen the fence until something works. Metacharacters
  now win, and a trailing slash on a glob expands to `/**`.
- **The always-block layer is anchored on the LIVE install** (`~/.claude`),
  which is what its own docstring always claimed. Both other candidates are
  wrong: `DINNER_HARNESS_HOME` is repointed at the *work repo* by the net, so a
  target repo containing a root `settings.json` or a `hooks/` tree became
  undispatchable; the handler's own directory follows `cfg.hooks_dir`, which
  resolves into the checkout, so the harness repo could not dispatch a Builder
  to edit its own hooks. Both are unconditional, dryrun-exempt and fence-proof,
  so the only escape was turning the hook off. **Consequence, stated because it
  was not obvious:** the net submits only paths inside the work repo, so under
  this anchor the always-block layer never fires in a controller dispatch — the
  fence is the whole of the scope enforcement there. A non-default install
  (`install.py --dest <scratch>`) likewise does not protect itself. The
  resolution is also lazy and guarded: `Path.home()` raises on Windows when
  `USERPROFILE`/`HOME` are absent, and an import-time raise exits the handler
  with code 1 — which the caller read as neither allow nor block.
- **The handler watchdog does not answer "allow" for the net.** The 200 ms
  budget belongs to an interactive Claude hook, where a stalled handler must not
  freeze a keystroke; the net passes whole file contents and already allows the
  subprocess 30 s. Measured under the interactive budget: an AWS key that blocks
  at 1 KiB shipped at 48 MiB, for `scope_check` and `secret_scan` alike, with no
  warning anywhere. `CLAUDE_HOOK_TIMEOUT_MS` and `CLAUDE_HOOK_FAILS_CLOSED` are
  set by the net only; unset, every interactive session behaves exactly as
  before. The same flag covers a handler that *crashes* inside `main`, and the
  net separately treats **any** exit code other than 0 or 2 as "no verdict
  reached" — an import-time failure (a half-copied `hooks_dir`, a missing
  `lib/`) dies outside `run_handler`'s `try`, where no flag can reach it, and
  was previously recorded as a clean pass with an empty reason list.
- **Two paths are scope-exempt, and only two**: `RESULT.md` and the dispatched
  handoff. Both are files the *controller* is answerable for rather than the
  Builder — it writes `RESULT.md` from the Builder's report after the snapshot,
  and the tamper stop has already proved the handoff unchanged. Judging either
  against the Builder's edit whitelist fails every dispatch on its own
  paperwork. Neither is *secret*-exempt: both are appended to the changeset
  every cycle so `secret_scan` sees them whether or not they are in the delta
  (an unchanged handoff is in both snapshots and drops out; `RESULT.md` is
  routinely `.gitignore`d — this repo ignores both).
- The `scope_exempt` and `fence` parameters on `safety.scan` are set by the
  **controller**, never inferred inside the net. The net does still resolve one
  bus name itself (`cfg.handoff_name or bus.HANDOFF`, to fill
  `CLAUDE_SCOPE_HANDOFF_NAME`); that is a known wart rather than a claim of
  purity, and it is inert in production because the fence is always pinned.
- **Handoff tamper stop:** after the turn, compare the on-disk handoff against
  the dispatched text unconditionally (`_same_text`, CRLF/outer-whitespace
  tolerant). Any drift — including **deletion**, which reads as `""`, and an
  unreadable file, which reads as `None` — fails the cycle before the fence is
  consulted. The handler re-reads the fence from disk, so an edited handoff would
  otherwise be rewriting the rule it is judged by.
- **Encoding:** every bus read the Builder could have touched goes through
  `_read_bus`, which returns `None` on any decode failure. `_same_text(None, x)`
  is `False`, so unreadable is treated as drift, never as "unchanged". This
  includes the *entry* read in `run_from_handoff` — a cp949 handoff must yield a
  clean `BLOCKED`, not a traceback out of the CLI.
- **Fence presence** is checked from the handoff text *before* the builder turn
  (`bus.scope_entries`), so a fenceless dispatch fails in seconds rather than
  after `timeout_s=1800`. Absent or comment-only ⇒ fail closed in `enforce`,
  warn in `dryrun`. One parser (`bus.scope_entries`) answers "is there a fence";
  the handler alone answers "does this path match".
- **Handoff filename** reaches the handler via `CLAUDE_SCOPE_HANDOFF_NAME`
  (unset ⇒ `HANDOFF.md`, preserving interactive behaviour exactly).
  `Config.validate()` rejects a `handoff_name` containing a path separator or
  `.`/`..`, so the controller and the handler can never resolve different files.
  When the variable **is** explicitly set and the named fence is missing, the
  handler blocks in `enforce` instead of falling back to the legacy fail-open.
- **Changeset ceiling** `_MAX_CHANGESET = 500`: past it, fail closed in
  `enforce`; in `dryrun` skip the scan entirely rather than spend minutes on 2×N
  subprocesses. It is applied to **the paths git reported, before any content is
  read** — the earlier cut checked the *resulting delta*, so the collector had
  already pulled every dirty file into memory twice per turn, i.e. the ceiling
  ran after the cost it exists to bound. It therefore also fires **before** the
  builder turn when the tree is already past the bound, rather than after 1800 s.
- **Testing rule (non-negotiable, this is what hid three of the defects):** never
  exercise **the net** with an injected `Turn.changeset`. Real backends leave it
  `None`, so production always takes the git path. Tests of the tier gate, the
  human gate and the retry logic may still inject — they are not testing the net
  — but any test whose name or docstring claims something about scope, secrets
  or the changeset must drive git. (An absolute rule with unstated exceptions is
  what let two net tests keep injecting; this is the rule as actually meant.) Use a real `git init` repo,
  and include **pre-existing dirt** and a **new subdirectory** — pristine temp
  repos hide exactly this class of bug. Do not dogfood in `dinner-harness`
  itself: its `.gitignore` hides `HANDOFF.md`/`RESULT.md`, so the bug is
  invisible here and appears only in target repos.

## Threat model (added after round 7)

Round 7 produced a working evasion: a Builder that appends to
`.git/info/exclude`, or sets an `assume-unchanged`/`skip-worktree` index bit,
removes a path from **both** snapshots — the delta is empty for it, and the
write (or the `rm`) is never judged. Neither knob lives in the working tree, so
neither appears in the listing it suppresses.

Round 8 then found the sharpest member of that family and one that is **not**
adversarial at all: a Builder that simply **commits its turn**. `build_prompt`
tells it not to, which is an admission that headless Codex sometimes does — and
a commit removes the paths from both snapshots exactly like an ignore rule does.
Reported `BUILT`, zero handlers run.

So the check is not "the two knobs" but **the witness**: everything that changes
what `git status` will report, other than the working tree itself — HEAD, the
stash ref, `.git/info/exclude`, `core.excludesFile` (setting *and* content), and
the `assume-unchanged`/`skip-worktree` index bits, the last read repo-wide
(`--full-name :/`, since `ls-files` is otherwise cwd-scoped) and the first read
from `--git-common-dir` (since a linked worktree's `--git-dir` has no `info/` —
which made the check inert in precisely the layout this document recommends for
containment). Any movement fails the cycle.

That closes the cheap evasions and the honest-mistake case; it does not close
the class, and pretending otherwise is how this ADR got into trouble before. So,
stated plainly:

**The net constrains an over-reaching Builder, not an evading one.** The failure
mode a headless agent actually produces is misreading the spec, refactoring past
its remit, touching a file it was told to leave alone, pasting a key — and
against that the net is a hard gate. An agent that is actively working around it
has a shell in the same tree the net lives in, and can reach anything the net
reaches, first. Containment is a process-level property (an isolated worktree, a
sandbox); it is not something a checker inside the tree can provide.

A `BUILT` therefore means "nothing the net can see went wrong", not "nothing
else happened". `delegate/SKILL.md` and `orchestrator/README.md` say so in the
same words, because the previous phrasing ("hard-blocks **any** edit") is what
made the gap read as a lie rather than a limit.

## Consequences

- **Positive:** one mechanism replaces three special cases (handoff exemption,
  by-name bus exemption, snapshot-of-three-filenames). Pre-existing dirt no
  longer blocks a dispatch, so the **common** reason to widen the fence is gone.
  The fence can finally be enabled in `/delegate`. `_MAX_CHANGESET` becomes
  meaningful. Verified on real git repos: pre-existing ADR + in-fence work →
  `BUILT`; Builder writing out-of-fence → `BLOCKED`; handoff edited, deleted, or
  cp949-mangled → `BLOCKED`; delegate lane clean dispatch → `BUILT`; untracked
  out-of-fence deletion or move → `BLOCKED`; non-repo and corrupt-`.git`
  dispatch → `BLOCKED`; work repo below the git root → key caught, in-fence
  write not false-blocked. Every behaviour above is pinned by a test that fails
  when the behaviour is reverted (21/21 mutants killed).
- **Two earlier claims here were too strong and are corrected.** "The operator
  is never pushed to widen the fence" — not unconditional: a gate's own
  verification can create files (a Python verify writes `__pycache__/`), and
  those land in the delta against a fence that names only source. The fence must
  cover what verification writes, or the target repo must ignore it; see
  `delegate/SKILL.md`. And "one mechanism replaces three special cases" — true
  of the three exemptions, but the number of things that must agree went *up*:
  the fence-presence pre-check, the tamper stop, the `RESULT.md` exemption, the
  ceiling's two modes, a pinned-fence env contract, and `Config.validate()`
  encoding `scope_check`'s path resolution. The delta is more general; the
  component is not smaller.
- **Negative / trade-offs:** two `git status` invocations per turn instead of
  one, plus the witness fingerprint's handful of `rev-parse`/`ls-files`/`config`
  calls at each end — roughly a dozen extra git invocations per cycle, against a
  builder turn budgeted at 1800s. A file the Builder modifies **back to its pre-turn content** is invisible
  to the net (acceptable: no net change to judge). `content=""` is overloaded —
  deleted, empty, and unreadable-as-UTF-8 all collapse to it, so a Builder that
  modifies an already-dirty *binary* file out of fence is not seen; distinguishing
  them means a status marker on `safety.Change`, which was judged not worth the
  reach here. **Files the target repo ignores are invisible to the net** — they
  never appear in `git status`, so a Builder writing there is unseen by both
  layers; widening to `--ignored` was rejected because on the repos the ceiling
  exists for it would report `node_modules` and refuse every dispatch, so the
  ignore rules are part of the safety boundary and are documented as such.
  **A nested git repository is refused** rather than vetted blindly — `-uall`
  stops at the boundary, so its files would arrive as one directory entry with
  empty content. The check runs over the **snapshots**, not the delta, and once
  before the turn: a nested repo that is already dirty at dispatch sits in both
  snapshots as the same entry, compares equal, and would otherwise drop out of
  the delta entirely — which is how three jurors independently found writes
  inside a dirty submodule reaching neither layer. Cost of the refusal: a repo
  with a dirty nested repo or submodule cannot be dispatched at all until it is
  cleaned, committed, or ignored. **A block is a refusal, not a rollback**: an out-of-fence
  deletion is reported, not undone. **`install.py` keeps no backup**, so backing
  this out means re-installing from the previous commit (`orchestrator/README.md`
  spells it out) — which matters because this change touches
  `hooks/lib/common.py`, imported by every handler. The controller now owns the
  "what did the Builder do" question, which is a genuine new responsibility —
  but it is the only component that knows the turn boundary.
- **Follow-ups:**
  - Round 6 (`adversarial-review`, 4 axes) returned **FAIL** — one BLOCK, three
    REJECT — against the first delta cut: the union delta, the git returncode
    check, the git-root resolution, the pinned fence, the path-aware matching,
    the always-block anchor, the watchdog budget, the ceiling placement, the doc
    rewrites, and the test work all come from it. Round 7 confirmed every one of
    those closed (each juror re-tested with its own PoCs) and returned **FAIL**
    again on new ground: the delta had silently dropped the handoff from
    `secret_scan` (a regression from the old whole-tree sweep — a key in the
    handoff shipped as `BUILT`); the child-side UTF-8 retraction above was wrong
    and was itself caused by a substring assertion; a non-repo burned a full
    1800 s turn before refusing; a crashing handler read as an approval; the
    always-block anchor followed the handler's own tree, so a checkout dispatch
    blocked the harness's own hooks; the rename test passed for the wrong reason;
    and the jury's own 64-mutant set left 14 alive. Round 8 returned **FAIL**
    with no BLOCK — every round-7 item verified closed by the jurors' own PoCs —
    and found: a Builder **committing its turn** blinded the net entirely (the
    honest-mistake case, not an evasion); `ls-files` was cwd-scoped so index-bit
    evasion survived below the git root; the fingerprint was inert in a linked
    worktree; a handler dying at *import* still read as allow, and the new
    `Path.home()` could cause exactly that; `RESULT.md` was left out of the
    secret append that the handoff got; promoting `[` in the classifier both
    widened and false-blocked bracketed directory entries; nested repos were
    vetted as empty; inherited `GIT_DIR` redirected the witness; and the handoff
    append was pinned by a count rather than by content. Round 9 produced the
    first **APPROVE** (architect: the exemptions are now justified by ownership
    rather than by filename, and the residual items are stated limits rather
    than false claims) against three REJECTs that converged on **one** code
    defect — the opaque-directory check ran over the delta, so a nested repo
    already dirty at dispatch dropped out and writes inside it reached neither
    layer — plus three test gaps on claims the code already honoured
    (`core.excludesFile` content, the stash ref, `_run_handler`'s own `-1`) and
    a handful of doc/comment overclaims. All addressed here.
    **The round-9 fixes above were never juried** — they are the jurors' own
    prescriptions, verified by test and by mutation, but a tenth panel has not
    seen them. The user accepted this ADR and merged it on 2026-08-06 with that
    gap open; it is a known, accepted debt, not a closed item. Re-running
    `adversarial-review` against the merged state remains the way to close it.
  - **The install gate is separate and still stands.** Merging changed nothing at
    runtime: until `install.py` runs, `~/.claude` keeps running the old handler
    and **the `/delegate` scope fence is live-inert** — that lane's protection
    depends on the Builder complying, not on enforcement. HIGH tier ⇒ human end
    sign-off before `py -3 install.py --target claude --allow-live` (and
    `--target codex`); `orchestrate.py`, `orchestrator/` and the hook handlers
    are all installed artifacts.
  - The "install freshness" axis proposed here **landed on 2026-08-06**:
    `py -3 check.py` now compares the repo against the live install and reports
    the staleness described above. It reports; it does not install.
  - Builder-timeout salvage (defect 2 above) deliberately dropped from this
    change after it produced three new holes in one round. Prefer exposing
    `timeout_s` as a CLI flag and streaming the child's output — the 30-minute
    silence is the worse half of that bug.

## Alternatives considered

- **Exempt the handoff file when unchanged** (R1 fix) — rejected: closed one face
  of the problem. The ADR/pre-existing-dirt case remained, and the exemption had
  to be re-derived for each new bus file.
- **Exempt bus artifacts by name** (R2 fix) — rejected: an exemption granted by
  filename is a hole a Builder can write through. `HANDOFF.md` is the fence a
  later interactive session reads, so a free write to it is a transitive
  compromise of the interactive lane.
- **Earn the exemption via a pre-turn snapshot of the three bus filenames**
  (R4 fix) — rejected: correct in kind, wrong in scope. The mechanism was already
  a delta; restricting it to three names left every other pre-existing file
  misattributed to the Builder.
- **Require operators to commit a clean baseline before dispatch** — rejected as
  the primary mechanism: it pushes an invariant the tool can enforce onto the
  human, and the architect lane's own protocol (ADR at step 8) violates it by
  design. Worth keeping as advice, not as the guarantee.
- **Leave the fence fail-open in `/delegate`** — rejected: it is the lane's only
  automatic defense, and the document lane's original-file protection is stated
  in `delegate/SKILL.md` as coming from the fence.
