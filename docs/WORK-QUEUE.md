# Work queue — pick-up notes

State of in-flight harness work, written so another machine can `git pull` this
branch and continue without the originating session's context.

Last updated: 2026-08-06.

---

## 0. Where things stand

Branch: `harness/net-judges-builder-delta` — **merged to `main` in PR #12 on
2026-08-06** (merge commit `9b74805`; the branch tree and `main` are identical
apart from later commits on the branch).

The controller-side safety net has been reworked to judge the **delta of the
Builder's turn** rather than the whole dirty tree. Design record, including the
threat model and every accepted limitation:
[`docs/architecture/ADR-0007-net-judges-builder-delta.md`](architecture/ADR-0007-net-judges-builder-delta.md)
(**Accepted** 2026-08-06). **Read that first** — it also records what four
earlier attempts broke, which is the fastest way to avoid repeating them.

Verification as of the merge:

- `py -3 -m unittest orchestrator.tests.test_orchestrator` → **89 tests, OK**
  (pytest is not installed; use unittest)
- mutation check: **48/48 mutants killed** — every behaviour the ADR claims has
  a test that fails when the behaviour is reverted
- interactive-session A/B against the pre-change handler: **identical** except
  two deliberate narrowings (directory fence entries match on a path boundary;
  glob `*` no longer crosses `/`), both warn-only in interactive sessions
  because `scope_check` runs permanently in `dryrun` there

### Merged, not installed — the remaining gate

The change is **HIGH tier** per `~/.claude/rules/autonomy-policy.md`: it is the
only automatic defense against a headless Codex Builder, which fires no Claude
hooks. Where the two gates actually stand:

1. **Design gate: closed by decision, with one item open.** ADR-0007 is
   **Accepted** and merged. `adversarial-review` ran four times (rounds 6–9);
   round 9 produced the first APPROVE (architect) against three REJECTs that
   converged on a single code defect plus three test gaps. All were fixed — but
   **a tenth panel never saw those fixes**, so the unanimity HIGH tier asks for
   was not reached. The user accepted and merged on 2026-08-06 with that gap
   open. It is accepted debt, not a closed item; re-running `adversarial-review`
   against the merged state is how to close it.
2. **Install gate: still standing.** Merging changed nothing at runtime.
   `~/.claude` still runs the previous handler, so the `/delegate` scope fence is
   **live-inert** — that lane's protection depends on the Builder complying, not
   on enforcement. Human end sign-off, then
   `py -3 install.py --target claude --allow-live` (and `--target codex`).
3. `py -3 check.py` now reports the staleness (item A below, landed) — eleven
   claude-target and three codex-target files, from this work plus `7d1f874`.
   It is a report, not a gate: it does not install anything.

To back out an install: re-install from the previous commit — `install.py`
overwrites in place and keeps no backup. See the note in
`orchestrator/README.md`. This matters because the change touches
`assets/claude/hooks/lib/common.py`, which every handler imports.

---

## 1. Queued harness improvements (A/B/C/F) — NOT STARTED

Four items picked from the Claude Code 70-tips document on 2026-08-05. **A is
done** (2026-08-06); B/C/F are not started.

### A — add an install-drift axis to `check.py` — DONE

`check.py` was repo-only by its own docstring, so it never compared the repo
against the installed `~/.claude`. This bit twice on 2026-08-05: the `/delegate`
document-lane commit (`7d1f874`) sat uninstalled and unnoticed, and the scope
fence work has the same trap (see §0 above).

Implemented as the sketch described: render the manifest into a temp dir through
`install.py`'s own adapters, compare content against the live `~/.claude` /
`~/.codex`. `--no-install` skips the axis; an absent install root is reported,
not counted as drift. On its first run it reproduced **both** incidents above.

Four false-positive sources are suppressed, and each is load-bearing rather than
cosmetic — the axis is worthless if a stale tree hides in noise:

- `<CLAUDE_HOME>` / dest-root substitution is normalized scratch→live. Applied
  to every **generated** dest, not just `template`: codex `hooks.json` embeds
  absolute handler paths the same way. Verbatim `copy` dests stay byte-exact.
- `skip_if_exists` dests (`HANDOFF.md`, `RESULT.md`) are live workflow state.
- a `merge` JSON dest is compared **key-wise on template-owned keys** — keeping
  live-only keys is what `merge` means, so a whole-text compare would flag every
  machine.
- inside owned dirs, dot-prefixed paths are vendor state (Codex ships
  `skills/.system/**`, marked by its own `.codex-system-skills.marker`); the
  manifest installs no dot-named path there, so it can never be a stale render
  of ours.

Live-only leftovers **are** reported, but only under directories the manifest
fills outright (dir-copy dests, skills, agents) — a skill deleted from the repo
keeps running until `install.py` re-runs, and nothing else caught that.

Verification: 15 cases against a scratch install tree (never the live one),
9 mutants, all killed — the axis has no test module in-repo because `check.py`
has none and adding one changes the repo's test topology (the documented entry
point is `orchestrator.tests.test_orchestrator`). **That is a real gap**: the
mutation evidence is in a session scratchpad, not in the repo. If this axis is
worth keeping, give it a test module.

Not taken: the `SessionStart`-hook alternative — note the harness still uses only
`PreToolUse` / `PostToolUse` / `UserPromptSubmit`, so `SessionStart`, `Stop`,
`SubagentStop` and `PreCompact` remain unused.

### B — isolate the Builder in a git worktree (tip §5.2)

Architect and Builder currently share one working tree, so anything the
Architect touches while the Builder runs is swept into the same `git status` the
safety net judges. `git worktree add ../repo-build <branch>`, then
`orchestrate.py build --repo <worktree>`.

This is the tip that fits the Two-CLI design best and it is absent from the
harness docs. **Caveat discovered during the ADR-0007 work:** a linked worktree's
`rev-parse --git-dir` has no `info/` directory — the net now uses
`--git-common-dir` for exactly this reason. Re-read the witness-fingerprint
section of the ADR before wiring this up, and note the threat model's remark
that a worktree is a *process-level* containment boundary, which is the thing
the in-tree net explicitly cannot provide.

### C — audit the approval allowlist (tip §5.4)

`secret_scan` and `scope_check` gate **writes**; nobody looks at the
auto-approved command list accumulating in `settings.local.json`. Scan with
`npx cc-safe ~/Documents`, then report and prune.

### F — document the `!` prefix in CLAUDE.md (tip §2.2)

`!git status` runs a shell command and puts only its output in context, with no
model turn. Directly serves the token-economy principle the harness is built
around, and it is undocumented.

**Commit plan (user's decision, 2026-08-05):** land the four tips and ADR-0007
together, but in **at least two commits** — the net rework is HIGH and touches a
trust boundary, the four tips are LOW and mutually unrelated, and a single
commit would make the net impossible to revert alone. That split is already
honoured on this branch: the net rework is its own commit.

Not selected from the same document: D (context budget), E (backoff),
G (plugin marketplace), H (thinking budget).

---

## 2. Deferred from ADR-0007

- **Builder-timeout salvage.** A codex CLI finished its work, wrote correct
  files, and never exited; `timeout_s=1800` fired and the changeset was
  discarded — a successful build reported `BLOCKED`. Deliberately dropped from
  the ADR-0007 change after an attempted fix produced three new holes in one
  round. Preferred direction: expose `timeout_s` as a CLI flag and stream the
  child's output — the thirty minutes of silence is the worse half of that bug.
  On a `BLOCKED`, check `git status` for surviving output before falling back to
  a manual run.
- **A heartbeat during long scans.** The net now emits
  `net: scanning N file(s)` before the loop, which lets an operator bound the
  wait. At the 500-path ceiling the scan is still ~85 s with no further output.
  A juror judged the current emit adequate; a heartbeat every ~50 files would be
  better.
- **`_MAX_CHANGESET` above the ceiling.** The union delta can in principle
  produce up to 2× the ceiling of `Change` objects (before ∪ after, each capped
  at 500). Cost only — no safety impact — and not asserted anywhere.

---

## 3. Gotchas for whoever picks this up

- **Never test the safety net with an injected `Turn.changeset`.** Real backends
  leave it `None`, so production always takes the git path; injection hid three
  separate defects. Tier-gate / human-gate / retry tests may still inject — they
  are not testing the net. This is stated in the ADR as a non-negotiable rule.
- **Do not dogfood the net in this repo.** `dinner-harness`'s own `.gitignore`
  hides `HANDOFF.md` and `RESULT.md`, so that whole class of bug is invisible
  here and shows up only in a target repo.
- **A green suite is not the bar; a killed mutant is.** Several defects survived
  review because a test asserted an outcome (`BLOCKED`) that the buggy path also
  produced, or a substring that survived the corruption. When adding a test,
  revert the behaviour and confirm the test dies.
- The suite neutralises git config (`GIT_CONFIG_GLOBAL`/`SYSTEM`) at module
  scope. Without it a global `core.excludesFile` hides the Builder's writes from
  `git status`, and `commit.gpgsign` breaks the commit helper.
- One test (`test_builder_writing_outside_the_fence_still_blocks`) can fail
  under heavy CPU contention: a `git status` timeout yields a fail-closed
  `BLOCKED` with a different reason string. The behaviour is safe; the
  assertion is strict on purpose. **Do not "fix" it by dropping the reason
  assertion** — that would let every such test pass on a block for the wrong
  reason.
- `orchestrate.py` may show as modified with an empty diff: line endings only.
