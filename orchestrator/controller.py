"""The state machine. Drives Architect <-> Builder through the file bus,
invoking the human only at the boundaries risk-tiered autonomy keeps.

Cycle:
  1 ARCHITECT_DESIGN   -> HANDOFF.md (+ ```tiers``` + ```scope```)
  (start gate)         -> optional human confirm of the HANDOFF
  3 BUILDER_EXECUTE    -> RESULT.md (+ ```verdicts```), changeset
  3.5 SAFETY NET       -> rerun scope_check/secret_scan on the changeset
  tier-gate            -> every HIGH gate needs panel=PASS; any BLOCK fails
  2 HIGH SIGN-OFF      -> human, only if a HIGH gate is present
  4 ARCHITECT_REVIEW   -> ```control``` DONE | NEXT_CYCLE | BLOCKED
  5 loop / terminate

Stdlib only.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Protocol

from . import bus as busmod
from . import safety
from .bus import Bus, parse_tiers, parse_verdicts, parse_control, tier_for
from .config import Config
from .vendors import Backend, Turn, ROLE_ARCHITECT, ROLE_BUILDER


# --------------------------------------------------------------------------- #
# Human gate                                                                  #
# --------------------------------------------------------------------------- #
class HumanGate(Protocol):
    def confirm(self, prompt: str) -> bool: ...


class AutoApprove:
    """Opens every gate (mock / CI / --yes)."""

    def confirm(self, prompt: str) -> bool:
        return True


class TerminalGate:
    """Blocking y/n on the controlling terminal."""

    def confirm(self, prompt: str) -> bool:
        try:
            ans = input(f"{prompt} [y/N] ").strip().lower()
        except EOFError:
            return False
        return ans in ("y", "yes")


# --------------------------------------------------------------------------- #
# Outcome                                                                      #
# --------------------------------------------------------------------------- #
DONE = "DONE"
BLOCKED = "BLOCKED"
HELD = "HELD"            # a human declined a gate
BUILT = "BUILT"         # single-shot build done; net+tier-gate passed, review owned in-session
MAX_CYCLES = "MAX_CYCLES_EXCEEDED"

# A headless Codex Builder occasionally self-misjudges its sandbox as read-only
# and bails with no implementation (verified 2026-07-14: identical dispatch
# failed then succeeded). run_from_handoff re-dispatches once on such a bail.
_MAX_BUILD_ATTEMPTS = 2


@dataclass
class Outcome:
    status: str
    cycles: int = 0
    reason: str = ""
    log: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Prompt builders (self-contained per the harness "HANDOFF self-contained" rule)
# --------------------------------------------------------------------------- #
_TIER_RULE = (
    "Risk tier per autonomy-policy: HIGH = network replication / save or "
    "serialization format / live config or feature flags / data migration / "
    "security-sensitive / anything irreversible. Conservative OR; if ambiguous, HIGH."
)


def design_prompt(goal: str, prior_result: str, cycle: int) -> str:
    extra = f"\n\nPrevious RESULT.md (continue from here):\n{prior_result}" if prior_result else ""
    return (
        "You are the ARCHITECT in a Two-CLI workflow. Do not edit code; produce a "
        "self-contained HANDOFF.md.\n"
        f"GOAL: {goal}{extra}\n\n"
        "Break the work into independently verifiable gates (1-3 files each), each "
        "with an explicit verification command. " + _TIER_RULE + "\n"
        "Output ONLY the HANDOFF.md content. It MUST end with two fences:\n"
        "```tiers``` — one line per gate: `gate N: LOW|HIGH`\n"
        "```scope``` — the whitelist of files the Builder may edit (one per line)."
    )


def build_prompt(handoff_text: str) -> str:
    return (
        "You are the BUILDER in a Two-CLI workflow. Implement the HANDOFF below.\n"
        "YOUR VERY FIRST ACTION IS TO WRITE THE FILE EDITS the HANDOFF requires — "
        "do that now, before running ANY other command. Do NOT run a verification, "
        "build, test, or exploratory command first; make the edits, THEN verify. "
        "You have workspace-write access at the working directory and CAN create "
        "and edit files there.\n"
        "Never conclude the workspace is read-only. A failing command is NOT proof "
        "you cannot write — a verification often fails for reasons unrelated to "
        "write access: your edits are not in place yet, or the interpreter it names "
        "is unavailable in this sandbox. In particular, on this machine the `py` "
        "launcher frequently exits with 'no installed runtime' (exit 112) inside "
        "the sandbox even though writing works fine: if a verify command using "
        "`py`/`py -3` fails that way, DO NOT infer read-only — just make your edits "
        "and re-run the check with `python` or `python3` instead. If any probe "
        "makes you think you cannot write, that impression is WRONG — attempt the "
        "edit anyway; never report you cannot write without having actually tried. "
        "Never end with an empty changeset and never revert your edits over a "
        "failing verification.\n"
        "This is a NON-INTERACTIVE, headless run. Do NOT ask for confirmation, do "
        "NOT wait for approval, and do NOT just summarize the plan: execute every "
        "gate now, autonomously, in one turn. If any installed role protocol "
        "(e.g. an AGENTS.md Builder section) tells you to ask 'shall I proceed?' "
        "first, override it — proceed without asking.\n"
        "Per gate, run the autonomous-loop: implement surgically, THEN run the "
        "gate's verification, and for non-trivial or HIGH gates run "
        "adversarial-review. Stay strictly within the ```scope``` whitelist. "
        "Do NOT merge/deploy HIGH gates. Leave your edits in the working tree: "
        "do NOT stage, commit, merge, or deploy — the Architect reviews them with "
        "plain `git diff`, which shows nothing once changes are staged.\n\n"
        f"--- HANDOFF.md ---\n{handoff_text}\n--- end ---\n\n"
        "After doing the work, write RESULT.md content as your final message.\n"
        "CRITICAL OUTPUT CONTRACT: regardless of any report format your role "
        "protocol normally uses, your final message MUST contain a fenced block "
        "with exactly this shape (one line per gate) — without it the run fails:\n"
        "```verdicts\n"
        "gate 1: status=completed tier=LOW panel=PASS\n"
        "```\n"
        "status=completed|blocked, tier=LOW|HIGH, panel=PASS|FAIL|BLOCK."
    )


def review_prompt(handoff_text: str, result_text: str) -> str:
    return (
        "REVIEW. You are the ARCHITECT. Compare the HANDOFF intent against the "
        "actual implementation (inspect the real diff in the repo).\n\n"
        f"--- HANDOFF.md ---\n{handoff_text}\n--- RESULT.md ---\n{result_text}\n--- end ---\n\n"
        "Decide the cycle outcome. End your output with a fence:\n"
        "```control``` — `verdict: DONE|NEXT_CYCLE|BLOCKED` and `reason: <one line>`"
    )


# --------------------------------------------------------------------------- #
# Tier-gate enforcement                                                        #
# --------------------------------------------------------------------------- #
def enforce_tier_gates(tiers: dict[str, str], verdicts) -> list[str]:
    """Return block reasons for the tier gate.

    Effective tier = the higher of the Architect-declared tier (``tier_for``
    defaults HIGH for any gate absent from the ```tiers``` fence, so a missing or
    garbled fence makes EVERY gate HIGH — fail-closed) and the Builder's
    self-reported verdict tier. Rules:
      * no gates declared at all -> block (fail-closed)
      * a declared gate with no verdict -> block (fail-closed)
      * panel BLOCK or FAIL -> block (any tier)
      * a HIGH gate must carry an explicit panel=PASS
    """
    gate_keys = set(tiers) | {v.gate for v in verdicts}
    if not gate_keys:
        return ["no gates declared (fail-closed)"]
    by_gate = {v.gate: v for v in verdicts}
    reasons: list[str] = []
    for gate in sorted(gate_keys):
        v = by_gate.get(gate)
        eff_high = tier_for(tiers, gate) == busmod.TIER_HIGH or (
            v is not None and v.tier == busmod.TIER_HIGH
        )
        if v is None:
            reasons.append(f"gate {gate}: no verdict (fail-closed)")
            continue
        if v.panel == busmod.PANEL_BLOCK:
            reasons.append(f"gate {gate}: panel BLOCK")
        elif v.panel == busmod.PANEL_FAIL:
            reasons.append(f"gate {gate}: panel FAIL")
        elif eff_high and v.panel != busmod.PANEL_PASS:
            reasons.append(f"gate {gate}: HIGH requires panel=PASS, got {v.panel or 'NONE'}")
    return reasons


def _builder_bailed(verdicts) -> bool:
    """The observed flake signature: a headless Builder self-reports
    ``status=blocked`` (or emits no parseable verdict at all) after falsely
    deciding the workspace is read-only, having written no implementation.
    ``run_from_handoff`` re-dispatches once on this.

    A ``status=completed`` gate whose review panel FAILs/BLOCKs is NOT a bail — it
    is a legitimate advisory outcome the in-session review owns, so it passes
    through untouched (not retried, not clobbered)."""
    if not verdicts:
        return True
    return any((v.status or "").strip().lower() == "blocked" for v in verdicts)


def compute_has_high(tiers: dict[str, str], verdicts) -> bool:
    """True if any gate is HIGH. ``tier_for`` defaults HIGH, so a missing
    ```tiers``` fence yields HIGH for every declared gate (fail-closed); the
    Builder's self-reported tier is cross-checked too."""
    gate_keys = set(tiers) | {v.gate for v in verdicts}
    if not gate_keys:
        return True  # nothing declared -> fail-closed
    by_gate = {v.gate: v for v in verdicts}
    for gate in gate_keys:
        if tier_for(tiers, gate) == busmod.TIER_HIGH:
            return True
        v = by_gate.get(gate)
        if v is not None and v.tier == busmod.TIER_HIGH:
            return True
    return False


# Upper bound on paths the deterministic net will materialise in one snapshot.
# Two handler subprocesses per file, and every path's content is read into
# memory once per snapshot (twice per turn), so an unbounded tree is both a
# multi-minute stall and a memory hazard. Enforced BEFORE any content is read:
# a ceiling applied after the cost it exists to bound is not a ceiling.
_MAX_CHANGESET = 500


class _Oversized:
    """Sentinel: git answered, but with more paths than the net can vet."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "OVERSIZED"


OVERSIZED = _Oversized()

# Distinguishes "absent from this snapshot" from any real file content, so a
# path present on only one side of the turn always reads as changed.
_ABSENT = object()


def _changeset_index(changes) -> Optional[dict]:
    """{path: content} for a collected changeset, or None if it could not run."""
    return None if changes is None else {c.path: c.content for c in changes}


def _git_env() -> dict:
    """Environment for our git calls, with the repo-redirecting knobs removed.

    `GIT_DIR` / `GIT_WORK_TREE` / `GIT_INDEX_FILE` / `GIT_COMMON_DIR` override
    `-C` and point git at a different repository, so an inherited value makes
    the net vet the wrong tree — measured: with `GIT_DIR` and `GIT_WORK_TREE`
    set elsewhere, the work repo's out-of-fence file vanished from the
    changeset entirely. These are routinely set inside git hooks and
    `git rebase --exec`, so this is a misconfiguration hazard before it is a
    spoofing one. `safety.scan` already clears an inherited `CLAUDE_SCOPE_FENCE`
    for the same reason; this is the git-side half of that.
    """
    env = dict(os.environ)
    for k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
        env.pop(k, None)
    return env


def _git_why(repo: Path) -> str:
    """git's own words for why it will not answer, for the operator's message.

    "git unavailable" is the one thing that is *not* true in most of these
    cases — git ran fine and refused. `detected dubious ownership` (routine on
    Windows when the repo sits under another profile or drive) is one
    `git config --global --add safe.directory <path>` away; a corrupt .git and
    an index.lock conflict are each fixed differently. Collapsing them all into
    one string leaves the operator nothing to act on.
    """
    try:
        proc = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                              capture_output=True, timeout=30, env=_git_env())
    except Exception as exc:  # noqa: BLE001 - git not on PATH, etc.
        return f"{type(exc).__name__}: {exc}"
    lines = [ln.strip() for ln in
             (proc.stderr or b"").decode("utf-8", "replace").strip().splitlines()
             if ln.strip()]
    # Prefer git's `fatal:` line over whatever came first: an unreadable
    # excludesFile emits `warning: unable to access ...` and only then the
    # actionable `fatal: cannot use ... as an exclude file`, so taking line one
    # hands the operator the symptom and drops the cause. (`dubious ownership`
    # happens to lead with `fatal:`, which is why the common case read fine.)
    for ln in lines:
        if ln.startswith("fatal:"):
            return ln
    return lines[0] if lines else f"git exited {proc.returncode} with no message"


def _git_out(repo: Path, *args: str) -> Optional[str]:
    """stdout of a git command, or ``None`` when git did not succeed.

    Checking ``returncode`` is what makes this fail closed. `git status` in a
    non-repository exits 128 with EMPTY stdout and raises nothing, so a caller
    that only catches exceptions reads "clean tree" out of "there is no
    repository here" — and the net then vets nothing while the run reports
    BUILT. The same shape covers `detected dubious ownership` (routine on
    Windows when the repo sits under another profile or drive), a corrupt
    .git, and an index.lock conflict.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, timeout=30,
            env=_git_env(),
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    # git writes paths as UTF-8; anything undecodable becomes U+FFFD, which
    # resolves to no file — content "" and a fence mismatch, i.e. fail closed.
    return proc.stdout.decode("utf-8", "replace")


def _witness_fingerprint(repo: Path) -> Optional[str]:
    """Everything that changes what `git status` will REPORT, other than the
    working tree itself — captured as one comparable blob.

    The delta rests on `git status` being an honest witness, and the Builder can
    edit the witness without touching a single tracked file. Each of these
    removes a path from **both** snapshots, so the delta is empty for it and the
    write is never judged:

    * ``git commit`` (or ``git stash``) — the sharpest one, and NOT an exotic
      attack: ``build_prompt`` explicitly tells the Builder not to commit, which
      is an admission that headless Codex sometimes does. A Builder that
      misreads that line is exactly the over-reaching case this net exists to
      gate, and it was silently reported ``BUILT``. Caught via HEAD and the
      stash ref.
    * ``.git/info/exclude`` and ``core.excludesFile`` — ignore rules authored
      mid-turn rather than inherited from the repo.
    * the ``assume-unchanged`` / ``skip-worktree`` index bits.

    None of them live in the working tree, so none show up in the very listing
    they suppress. This narrows the hole; it does not close the class — see the
    threat model in ADR-0007.
    """
    # --git-common-dir, NOT --git-dir: in a linked worktree the latter is
    # .git/worktrees/<name>, which has no info/ at all, so the exclude read
    # silently became "" on both sides and the check went inert — in precisely
    # the layout the README recommends for containment.
    common = _git_out(repo, "rev-parse", "--git-common-dir")
    # --full-name :/ makes this repo-wide: `git ls-files` is otherwise scoped to
    # its cwd, while `git status` is not, so a work repo below the git root left
    # index bits outside it unwatched — the evasion survived in that layout.
    marks = _git_out(repo, "ls-files", "-v", "--full-name", ":/")
    if common is None or marks is None:
        return None
    common_dir = Path(common.strip())
    if not common_dir.is_absolute():
        common_dir = repo / common_dir
    try:
        exclude_text = (common_dir / "info" / "exclude").read_text(
            encoding="utf-8", errors="replace")
    except FileNotFoundError:
        exclude_text = ""
    except Exception:
        return None
    # `ls-files -v` tags assume-unchanged LOWERCASE and skip-worktree `S`
    # (verified: `S a.md` / `h b.md`). Keep only those so an ordinary large repo
    # does not carry a huge fingerprint — the lowercase test alone misses
    # skip-worktree, which is the half that survives a `rm`.
    hidden = [ln for ln in marks.splitlines() if ln[:1].islower() or ln[:1] == "S"]
    # HEAD and the stash ref: absent in a fresh repo, which is a stable answer,
    # not a failure — `rev-parse` exits non-zero there and _git_out returns None.
    head = _git_out(repo, "rev-parse", "HEAD") or ""
    stash = _git_out(repo, "rev-parse", "refs/stash") or ""
    # core.excludesFile is a third ignore knob, settable mid-turn. Both the
    # setting AND the file it names matter — repointing it and editing it are
    # the same attack with different spellings.
    excludes_file = (_git_out(repo, "config", "--get", "core.excludesFile") or "").strip()
    excludes_text = ""
    if excludes_file:
        try:
            excludes_text = Path(excludes_file).expanduser().read_text(
                encoding="utf-8", errors="replace")
        except Exception:
            excludes_text = "<unreadable>"
    return "\0".join([exclude_text, "\n".join(hidden), head.strip(),
                      stash.strip(), excludes_file, excludes_text])


def _opaque_dirs(changes, repo: Path) -> list[str]:
    """Changeset entries that are DIRECTORIES, i.e. contents we cannot vet.

    `-uall` expands untracked directories per-file, but it stops at a repository
    boundary: a nested git repo or an unregistered submodule comes back as ONE
    entry — the directory. Every file under it would then reach `secret_scan` as
    an empty string, and the fence would be asked about the directory rather
    than the writes inside it. Measured: fence ``sub/``, Builder runs
    ``git init sub`` and writes ``sub/leak.py`` with a key -> the path matched
    the fence and the key was never scanned.
    """
    out = []
    for c in changes:
        p = Path(c.path) if Path(c.path).is_absolute() else repo / c.path
        try:
            if p.is_dir():
                out.append(c.path)
        except OSError:
            continue
    return out


def _repo_relative(abs_path: Path, repo: Path) -> str:
    """The path as the net names it: repo-relative, forward slashes.

    Anything outside the work repo — a sibling directory of the same git
    repository — keeps its absolute form. `safety.scan` passes those through
    unchanged, and they match no fence entry, which is the right answer: the
    Builder was told to work inside ``repo``.
    """
    try:
        return abs_path.resolve().relative_to(repo.resolve()).as_posix()
    except Exception:
        return str(abs_path)


def _read_bus(bus: Bus, name: str) -> Optional[str]:
    """Bus file content, or ``None`` when it cannot be read as text.

    These reads land on bytes the Builder may have just written, and ``Bus.read``
    decodes as UTF-8. On a Korean-locale Windows box a naive text write lands in
    cp949, which would raise straight through the controller and out of the CLI
    as a traceback. A file we cannot read is a file we cannot vouch for, so it
    becomes ``None`` — which compares unequal to everything, and therefore reads
    as drift, never as "unchanged".
    """
    try:
        return bus.read(name)
    except Exception:  # noqa: BLE001 - unreadable == unvouchable; the caller blocks
        return None


def _same_text(a: Optional[str], b: Optional[str]) -> bool:
    """Content equality tolerant of the round-trip through disk.

    The handoff is compared against what we dispatched, but it crossed a file
    write, a git read, and possibly a CRLF translation on the way. Normalise
    line endings and trailing whitespace so those artefacts do not read as the
    Builder having edited its own spec. ``None`` (unreadable) matches nothing.
    """
    if a is None or b is None:
        return False
    return a.replace("\r\n", "\n").strip() == b.replace("\r\n", "\n").strip()


def collect_changeset(repo: Path, max_files: Optional[int] = None):
    """git status --porcelain -> [Change(path, content)] for the work repo.

    Three return shapes, and the caller must tell them apart:
      * ``None``    — git could not answer; fail closed, do not read this as
                      "clean tree" (that is ``[]``).
      * ``OVERSIZED`` — git answered with more paths than ``max_files``. Raised
                      before any content is read, so the cost the ceiling
                      exists to bound is never paid.
      * ``list``    — one Change per reported path.

    Every path git reports is returned, deletions and both ends of a rename
    included, with ``content=""`` for anything not readable as a file. The
    fence judges *paths the Builder touched*, and making a file disappear is a
    touch — the strongest one. The delegate document lane states its core
    guarantee as "keep the original out of the fence and scope_check
    hard-blocks any edit to it"; skipping deletions left `rm original.md`
    outside that promise.
    """
    # `git status` reports paths relative to the REPOSITORY ROOT, not to the
    # -C directory. When the work repo is a SUBDIRECTORY of the git repo,
    # resolving those against it finds nothing: every content reads as "" — so
    # secret_scan vets an empty string and a leaked key ships — while
    # scope_check is handed a doubled path (docs/resume/docs/resume/x.md) and
    # false-blocks work that IS in the fence, pushing the operator to widen it.
    top = _git_out(repo, "rev-parse", "--show-toplevel")
    if top is None:
        return None
    root = Path(top.strip())
    out = _git_out(
        repo,
        "status", "--porcelain",
        # -uall: without it git collapses an untracked directory to a single
        # "src/" entry, so a Builder creating src/feature.py yields the path
        # "src/" — which matches no fence entry and blocks the very change the
        # fence permits. The net judges files, so it must be given files.
        "-uall",
        # -z: NUL-separated, and — the reason it is here — UNQUOTED. By default
        # git C-quotes any non-ASCII path ("\352\262\275...md"), which resolves
        # to nothing on disk: the file's content reads as empty, so secret_scan
        # finds nothing in it, while the fence is asked about the escaped
        # spelling and rejects a path the operator did whitelist. The document
        # lane's files are routinely Korean-named, so this is its common case.
        "-z",
    )
    if out is None:
        return None

    entries = [e for e in out.split("\0") if e]
    paths: list[str] = []
    i = 0
    while i < len(entries):
        code, path = entries[i][:2], entries[i][3:]
        i += 1
        raw = [path]
        if "R" in code or "C" in code:
            # Under -z the source path is the NEXT field rather than an " -> "
            # suffix. A rename is a delete of the source plus a write of the
            # target, so both ends are the Builder's work and both are judged;
            # taking only the target let a Builder move an out-of-fence file
            # away unseen.
            if i < len(entries):
                raw.append(entries[i])
                i += 1
        paths.extend(_repo_relative(root / p, repo) for p in raw)

    if max_files is not None and len(paths) > max_files:
        return OVERSIZED

    changes: list[safety.Change] = []
    for p in paths:
        f = Path(p) if Path(p).is_absolute() else repo / p
        try:
            content = f.read_text(encoding="utf-8-sig") if f.is_file() else ""
        except Exception:
            content = ""
        changes.append(safety.Change(path=p, content=content))
    return changes


# --------------------------------------------------------------------------- #
# Orchestrator                                                                 #
# --------------------------------------------------------------------------- #
class Orchestrator:
    def __init__(
        self,
        cfg: Config,
        architect: Backend,
        builder: Backend,
        human: HumanGate,
        log: Callable[[str], None] = print,
    ):
        self.cfg = cfg
        self.architect = architect
        self.builder = builder
        self.human = human
        self._log_fn = log
        self._log: list[str] = []

    def _emit(self, msg: str) -> None:
        self._log.append(msg)
        self._log_fn(msg)

    def _outcome(self, status: str, cycle: int, reason: str = "") -> Outcome:
        return Outcome(status=status, cycles=cycle, reason=reason, log=list(self._log))

    def run(self) -> Outcome:
        cfg = self.cfg
        bus = Bus(Path(cfg.repo))
        prior_result = ""

        for cycle in range(1, cfg.max_cycles + 1):
            self._emit(f"[cycle {cycle}] ARCHITECT_DESIGN ({cfg.architect_vendor})")
            ad = self.architect.invoke(ROLE_ARCHITECT, design_prompt(cfg.goal, prior_result, cycle), cfg)
            if ad.error:
                return self._outcome(BLOCKED, cycle, f"architect design error: {ad.error}")
            bus.write_handoff(ad.text)
            tiers = parse_tiers(ad.text)
            self._emit(f"[cycle {cycle}] tiers={tiers or '(none) -> fail-closed HIGH'}")

            # START gate
            if cfg.confirm_handoff and not self.human.confirm(f"[cycle {cycle}] approve HANDOFF?"):
                return self._outcome(HELD, cycle, "human declined HANDOFF")

            bd, verdicts, has_high, blocked = self._build_and_gate(bus, ad.text, tiers, cycle)
            if blocked is not None:
                return blocked

            # ARCHITECT_REVIEW happens BEFORE any acceptance, so the human never
            # signs off on a cycle the Architect itself then rejects.
            self._emit(f"[cycle {cycle}] ARCHITECT_REVIEW")
            rv = self.architect.invoke(ROLE_ARCHITECT, review_prompt(ad.text, bd.text), cfg)
            if rv.error:
                return self._outcome(BLOCKED, cycle, f"architect review error: {rv.error}")
            control = parse_control(rv.text)
            self._emit(f"[cycle {cycle}] control={control.verdict} ({control.reason})")

            if control.verdict == busmod.VERDICT_BLOCKED:
                return self._outcome(BLOCKED, cycle, f"architect review: {control.reason}")
            if control.verdict == busmod.VERDICT_NEXT:
                prior_result = bd.text
                continue

            # control == DONE -> END boundary. Per autonomy-policy: LOW
            # auto-completes (report only); HIGH requires the human end sign-off
            # before the change is accepted (merge/apply/deploy).
            if has_high:
                self._emit(f"[cycle {cycle}] HIGH cycle — human end sign-off required")
                if not self.human.confirm(
                    f"[cycle {cycle}] HIGH change — sign off to accept (merge/apply/deploy)?"
                ):
                    return self._outcome(HELD, cycle, "human withheld HIGH end sign-off")
                return self._outcome(DONE, cycle, control.reason)
            self._emit(f"[cycle {cycle}] LOW cycle — auto-complete (result reported)")
            return self._outcome(DONE, cycle, control.reason)

        return self._outcome(MAX_CYCLES, cfg.max_cycles, "max cycles exceeded without DONE")

    @staticmethod
    def _opaque_msg(opaque: list[str]) -> str:
        return ("changeset contains directories the net cannot look inside "
                f"({', '.join(sorted(opaque)[:3])}) — a nested git repo or an "
                "unregistered submodule stops `git status -uall` at its "
                "boundary, so its files would be admitted unscanned")

    @staticmethod
    def _oversized_msg(what: str) -> str:
        # -uall lists untracked files individually, so a target repo with a
        # thin .gitignore can hand us thousands of paths — each costing two
        # handler subprocesses, and each read into memory twice per turn. A net
        # that would take minutes is a net that will be turned off; refuse
        # instead, and say what to fix.
        return (f"{what} too large: over {_MAX_CHANGESET} paths — the net cannot "
                "bound this; check the target repo's .gitignore")

    def _build_and_gate(
        self, bus: Bus, handoff_text: str, tiers: dict[str, str], cycle: int,
        *, tier_gate_hard: bool = True,
    ):
        """BUILDER_EXECUTE -> RESULT.md -> safety net (3.5) -> tier-gate.

        Shared by run() and run_from_handoff(). Returns
        ``(builder_turn, verdicts, has_high, blocked)`` where ``blocked`` is a
        terminal Outcome on any failure (the caller returns it) or ``None`` on
        success. ``verdicts`` / ``has_high`` are meaningful only when ``blocked``
        is ``None``.

        The safety net (scope_check / secret_scan) is ALWAYS a hard block — it
        is the deterministic compensation for a Codex Builder firing no Claude
        hooks. ``tier_gate_hard`` controls only the verdict-based tier gate:
        run() keeps it hard (the autonomous loop has no other reviewer); the
        auto-dispatch build path sets it advisory (emit-only) because the
        in-session Claude review + HIGH human sign-off own that judgment, and a
        headless Codex does not reliably emit the machine ```verdicts``` fence.
        """
        cfg = self.cfg

        # Fence presence is knowable from the handoff alone, so check it BEFORE
        # burning a builder turn (cfg.timeout_s is 1800s — failing after that is
        # a 30-minute answer to a question we could answer now). scope_check
        # itself fails OPEN on an absent fence, deliberately, so an interactive
        # session predating ADR-0005 is not frozen; the controller has no such
        # excuse, because here a changeset is admitted on the strength of the
        # fence. No fence is a net that cannot run, not a pass.
        if not busmod.scope_entries(handoff_text):
            msg = f"no ```scope``` fence in {cfg.handoff_name or busmod.HANDOFF}: cannot bound the changeset"
            if cfg.net_enforce:
                return None, [], False, self._outcome(BLOCKED, cycle, msg)
            self._emit(f"[cycle {cycle}] net: WARN dryrun — {msg}")

        handoff_name = cfg.handoff_name or busmod.HANDOFF
        # Snapshot the whole working tree BEFORE the turn. The net judges the
        # BUILDER'S work, and `git status` reports everything that is merely
        # dirty — the handoff Claude just wrote, an ADR the Architect authored at
        # step 8, a scratch file from yesterday. Judging all of it against the
        # Builder's edit whitelist blocks dispatches on files the Builder never
        # touched, and the only workaround is widening the fence, which hands the
        # Builder writes it should not have. The delta is the honest changeset.
        before_raw = collect_changeset(Path(cfg.repo), max_files=_MAX_CHANGESET)
        if before_raw is OVERSIZED:
            # Refuse BEFORE the builder turn: the tree is already past what the
            # net can vet, so a turn would only add to it, and cfg.timeout_s is
            # 1800s. The operator gets the answer now, with the cause named.
            msg = self._oversized_msg("working tree")
            if cfg.net_enforce:
                return None, [], False, self._outcome(BLOCKED, cycle, msg)
            self._emit(f"[cycle {cycle}] net: WARN dryrun — {msg}")
            before_raw = None
        elif before_raw is None:
            # Knowable in milliseconds, so answer now. Letting this fall through
            # dispatched a headless Builder for up to cfg.timeout_s (1800s) into
            # a directory the net can never vet, and only refused afterwards —
            # by which point "a block is a refusal, not a rollback" means
            # whatever it wrote stays. Same reasoning as the fence-presence
            # check above; this one just had the answer already in hand.
            msg = (f"cannot determine changeset ({_git_why(Path(cfg.repo))}) — "
                   "fail-closed before dispatching the builder")
            if cfg.net_enforce:
                return None, [], False, self._outcome(BLOCKED, cycle, msg)
            self._emit(f"[cycle {cycle}] net: WARN dryrun — {msg}")
        # A dirty nested repo is knowable in milliseconds, so refuse before
        # burning the turn — same reasoning as the fence-presence and OVERSIZED
        # checks above. The post-turn check stays, for one created mid-turn.
        if before_raw:
            opaque = _opaque_dirs(before_raw, Path(cfg.repo))
            if opaque:
                msg = self._opaque_msg(opaque)
                if cfg.net_enforce:
                    return None, [], False, self._outcome(BLOCKED, cycle, msg)
                self._emit(f"[cycle {cycle}] net: WARN dryrun — {msg}")

        before = _changeset_index(before_raw)
        vis_before = _witness_fingerprint(Path(cfg.repo))

        self._emit(f"[cycle {cycle}] BUILDER_EXECUTE ({cfg.builder_vendor})")
        bd = self.builder.invoke(ROLE_BUILDER, build_prompt(handoff_text), cfg)
        if bd.error:
            return bd, [], False, self._outcome(BLOCKED, cycle, f"builder error: {bd.error}")
        bus.write_result(bd.text)
        verdicts = parse_verdicts(bd.text)

        # The handoff is the spec of record: the fence, the tiers, and what the
        # in-session review will later read this cycle against. A Builder that
        # rewrote it edited its own terms of reference, so the cycle is refused
        # whatever else it did. Compared unconditionally — DELETING the handoff
        # counts too, and so does a copy that no longer decodes. (The fence the
        # handler enforces is separately pinned from the dispatched text below,
        # so this check is not what stops a mid-scan rewrite; it is what stops
        # us accepting work whose spec no longer exists.)
        if not _same_text(_read_bus(bus, handoff_name), handoff_text):
            return bd, verdicts, False, self._outcome(
                BLOCKED, cycle,
                f"builder altered or removed {handoff_name} — the scope fence is the "
                "rule it is judged by; refusing to trust the changed copy",
            )

        # Did the Builder change what `git status` will report? Checked like the
        # handoff tamper stop, and for the same reason: the net's verdict is
        # only as good as the evidence it is given.
        if bd.changeset is None and _witness_fingerprint(Path(cfg.repo)) != vis_before:
            msg = ("builder changed what git reports — a commit/stash, an ignore "
                   "rule (.git/info/exclude or core.excludesFile), or an "
                   "assume-unchanged/skip-worktree index bit moved during the turn; "
                   "the changeset can no longer be trusted. Leave changes in the "
                   "working tree: the Architect reviews them with `git diff`")
            if cfg.net_enforce:
                return bd, verdicts, False, self._outcome(BLOCKED, cycle, msg)
            self._emit(f"[cycle {cycle}] net: WARN dryrun — {msg}")

        # RESULT.md is ours: the controller wrote it from the Builder's report
        # after the snapshot, so it shows up in the delta but is never the
        # Builder editing an unlisted file. The handoff is the Architect's, and
        # the tamper stop above has already proved the Builder did not touch it.
        scope_exempt = {busmod.RESULT, handoff_name}

        # 3.5 controller-side safety net, over the DELTA of the Builder's turn
        snapshot_for_opaque = []
        if bd.changeset is not None:
            changes = bd.changeset
            snapshot_for_opaque = changes
            if len(changes) > _MAX_CHANGESET:
                msg = self._oversized_msg("changeset")
                if cfg.net_enforce:
                    return bd, verdicts, False, self._outcome(BLOCKED, cycle, msg)
                self._emit(f"[cycle {cycle}] net: WARN dryrun — {msg}; skipping the scan")
                changes = []
        else:
            after = collect_changeset(Path(cfg.repo), max_files=_MAX_CHANGESET)
            if after is OVERSIZED:
                msg = self._oversized_msg("working tree")
                if cfg.net_enforce:
                    return bd, verdicts, False, self._outcome(BLOCKED, cycle, msg)
                self._emit(f"[cycle {cycle}] net: WARN dryrun — {msg}; skipping the scan")
                after = None
            after_index = _changeset_index(after)
            snapshot_for_opaque = after or []
            if after_index is None or before is None:
                if cfg.net_enforce:
                    return bd, verdicts, False, self._outcome(
                        BLOCKED, cycle,
                        f"cannot determine changeset ({_git_why(Path(cfg.repo))}) — fail-closed",
                    )
                self._emit(f"[cycle {cycle}] net: WARN git unavailable; changeset unknown")
                changes = []
            else:
                # Key the delta on the UNION of both snapshots, not on `after`
                # alone. A path can leave `git status` entirely — deleting an
                # UNTRACKED file leaves no ' D' entry, it simply vanishes — so
                # an `after`-only comprehension never constructs a Change for it
                # and the fence never sees it. That is exactly the document
                # lane's promise ("the source is out of the fence, so it cannot
                # be touched") failing on the most destructive edit there is,
                # against a file git has no object for and cannot restore.
                changes = [
                    safety.Change(path=p, content=after_index.get(p, ""))
                    for p in sorted(set(before) | set(after_index))
                    if before.get(p, _ABSENT) != after_index.get(p, _ABSENT)
                ]
        # The dispatched handoff is secret-scanned EVERY cycle, changed or not.
        # It normally sits in both snapshots — the Architect wrote it before the
        # turn — so the delta correctly drops it, and dropping it silently
        # removed the key check the old whole-tree sweep did provide: a key
        # pasted into the handoff shipped with the run reporting BUILT. It is
        # scope-exempt (see above), never secret-exempt.
        if all(c.path != handoff_name for c in changes):
            changes.append(safety.Change(path=handoff_name, content=handoff_text))
        # RESULT.md is the other file the controller writes, and its content is
        # verbatim Builder-authored text — strictly more exposed than the
        # Architect's handoff. It reaches the net only via the git delta, which
        # misses it whenever the target repo ignores it (this repo's own
        # .gitignore does exactly that). Same fix, same reason; missing it left
        # the identical hole open for the more dangerous of the two files.
        if all(c.path != busmod.RESULT for c in changes):
            changes.append(safety.Change(path=busmod.RESULT, content=bd.text))

        # Judged over the SNAPSHOT, not the delta. A nested repo that was
        # already dirty at dispatch sits in both snapshots as the same
        # directory entry with content "", so it compares equal and drops out
        # of the delta — and then the Builder's writes inside it are neither
        # refused nor scanned, with the run reporting BUILT. A directory is
        # unvettable whether or not it changed, so the refusal belongs where
        # the paths are collected. (Before the delta this failed closed: the
        # whole-tree sweep submitted `vendor/` every cycle and it matched no
        # fence entry. Keeping only the delta turned that into a silent pass.)
        opaque = _opaque_dirs(snapshot_for_opaque, Path(cfg.repo))
        if opaque:
            msg = self._opaque_msg(opaque)
            if cfg.net_enforce:
                return bd, verdicts, False, self._outcome(BLOCKED, cycle, msg)
            self._emit(f"[cycle {cycle}] net: WARN dryrun — {msg}")

        if not cfg.net_enforce:
            self._emit(f"[cycle {cycle}] net: WARN dryrun — advisory only, not blocking")
        # Two handler subprocesses per file at ~0.17s each, so a large delta is
        # a minute-plus of silence on a tool whose premise is that the operator
        # is watching a headless dispatch. Say what is about to happen.
        if changes:
            self._emit(f"[cycle {cycle}] net: scanning {len(changes)} file(s)")
        # Pin the fence we DISPATCHED, so the handler judges against that text
        # rather than re-reading a file the Builder can still be writing to.
        net = safety.scan(changes, cfg, scope_exempt=scope_exempt,
                          fence=busmod.scope_entries(handoff_text))
        for r in net.reasons:
            self._emit(f"[cycle {cycle}] net: {r}")
        if net.blocked:
            return bd, verdicts, False, self._outcome(BLOCKED, cycle, "safety net blocked the changeset")

        # tier-gate enforcement
        gate_reasons = enforce_tier_gates(tiers, verdicts)
        if gate_reasons:
            label = "tier-gate" if tier_gate_hard else "tier-gate(advisory)"
            for r in gate_reasons:
                self._emit(f"[cycle {cycle}] {label}: {r}")
            if tier_gate_hard:
                return bd, verdicts, False, self._outcome(BLOCKED, cycle, "tier-gate enforcement failed")

        has_high = compute_has_high(tiers, verdicts)
        return bd, verdicts, has_high, None

    def run_from_handoff(self) -> Outcome:
        """Single-shot Builder pass from an existing handoff file
        (``cfg.handoff_name``, default HANDOFF.md).

        The interactive Architect (Claude) already wrote and got human approval
        for the handoff; this drives only the Builder (Codex) turn + controller
        safety net + tier-gate, writes RESULT.md, and returns. ARCHITECT_REVIEW
        and the HIGH end sign-off are owned by the in-session Architect — not
        re-run headless here (that is what makes the in-session review the gate).
        """
        cfg = self.cfg
        bus = Bus(Path(cfg.repo))
        handoff_name = cfg.handoff_name or busmod.HANDOFF
        handoff_text = _read_bus(bus, handoff_name)
        if handoff_text is None:
            # A handoff we cannot decode is a spec we cannot dispatch. On a
            # Korean Windows box a Notepad "ANSI" save lands in cp949, and this
            # read is the one the orchestrator did not author.
            return self._outcome(BLOCKED, 0, f"cannot read {handoff_name} as UTF-8 text")
        if not handoff_text.strip():
            return self._outcome(BLOCKED, 0, f"no {handoff_name} to build from")
        tiers = parse_tiers(handoff_text)
        self._emit(f"[build] tiers={tiers or '(none) -> fail-closed HIGH'}")
        # Advisory tier gate: the safety net still hard-blocks, but verdict gating
        # is emit-only here — the in-session Claude review owns acceptance.
        #
        # Retry-once: a headless Codex Builder occasionally bails with no
        # implementation (status=blocked / no verdict) after falsely deciding the
        # workspace is read-only; a single re-dispatch clears it (_builder_bailed).
        # A completed gate whose review panel FAILs/BLOCKs is a real advisory
        # outcome, not a bail — it passes through. A safety-net block
        # (scope/secret) is deterministic and is NEVER retried.
        has_high = False
        attempt = 0
        for attempt in range(1, _MAX_BUILD_ATTEMPTS + 1):
            _bd, verdicts, has_high, blocked = self._build_and_gate(
                bus, handoff_text, tiers, cycle=attempt, tier_gate_hard=False,
            )
            if blocked is not None:
                return blocked  # safety net (scope/secret) tripped — hard block
            if not _builder_bailed(verdicts):
                break  # builder completed (advisory panel verdicts pass through)
            if attempt < _MAX_BUILD_ATTEMPTS:
                self._emit(
                    f"[build] attempt {attempt}: builder bailed with no "
                    "implementation (likely a false read-only) — retrying once"
                )
        note = (
            "HIGH gate present — in-session human sign-off required before merge/apply"
            if has_high else "all-LOW"
        )
        self._emit(f"[build] BUILT ({note}) — RESULT.md written, awaiting in-session review")
        return self._outcome(BUILT, attempt, note)
