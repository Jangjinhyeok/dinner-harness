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
from .receipt import BuildAudit
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
    receipt_path: Optional[Path] = None
    receipt_id: str = ""


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


def build_prompt(handoff_text: str, handoff_name: str) -> str:
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
        "NOT wait for approval, and do NOT just summarize the plan: execute each "
        "eligible gate now, autonomously, in one turn; after a completed HIGH gate, "
        "stop rather than progressing to the next gate. If any installed role protocol "
        "(e.g. an AGENTS.md Builder section) tells you to ask 'shall I proceed?' "
        "first, override it — proceed without asking.\n"
        "A `HIGH` tier gate does not mean stop and ask before implementing — "
        "implement it now and leave it unmerged; the human sign-off happens "
        "later in the dispatching session.\n"
        "Per gate, run the autonomous-loop: implement surgically, THEN run the "
        "gate's verification, and for non-trivial or HIGH gates run "
        "adversarial-review. Stay strictly within the ```scope``` whitelist. "
        "Do NOT merge/deploy HIGH gates. Leave your edits in the working tree: "
        "do NOT stage, commit, merge, or deploy — the Architect reviews them with "
        "plain `git diff`, which shows nothing once changes are staged.\n\n"
        "The following block is this turn's only specification; other `HANDOFF*` "
        "and `RESULT` files are stale artifacts from other turns, so do not read "
        "or act on them.\n\n"
        f"--- {handoff_name} ---\n{handoff_text}\n--- end ---\n\n"
        "After doing the work, write RESULT.md content as your final message.\n"
        "CRITICAL OUTPUT CONTRACT: regardless of any report format your role "
        "protocol normally uses, your final message MUST contain a fenced block "
        "with exactly this shape (one line per gate) — without it the run fails:\n"
        "```verdicts\n"
        "gate 1: status=completed tier=LOW panel=PASS\n"
        "```\n"
        "status=completed|blocked, tier=LOW|HIGH, panel=PASS|FAIL|BLOCK."
    )


def verdict_recovery_prompt(handoff_text: str, handoff_name: str) -> str:
    """Ask for the machine-readable artifact a completed turn omitted."""
    return (
        "VERDICT-ONLY RECOVERY. The implementation turn has already completed, "
        "and the controller has preserved its report in RESULT.md. Do NOT edit, "
        "create, delete, stage, commit, or otherwise change any file. Do NOT "
        "repeat the report. Return ONLY the fenced ```verdicts``` block, with one "
        "line for every gate declared in this HANDOFF. If you cannot honestly "
        "report a completed gate, use status=blocked and panel=BLOCK.\n\n"
        f"--- {handoff_name} ---\n{handoff_text}\n--- end ---\n\n"
        "Required shape:\n"
        "```verdicts\n"
        "gate 1: status=completed tier=LOW panel=PASS\n"
        "```\n"
        "status=completed|blocked, tier=LOW|HIGH, panel=PASS|FAIL|BLOCK."
    )


def review_prompt(handoff_text: str, result_text: str) -> str:
    return (
        "REVIEW. You are the ARCHITECT. Compare the HANDOFF intent against the "
        "actual implementation (inspect the real diff in the repo).\n\n"
        f"--- {busmod.HANDOFF} ---\n{handoff_text}\n--- {busmod.RESULT} ---\n{result_text}\n--- end ---\n\n"
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
    return any(
        (v.status or "").strip().lower() == "blocked" and not (v.panel or "").strip()
        for v in verdicts
    )


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


@dataclass
class _Evidence:
    """What the net knows about the tree at the instant before the builder turn.

    The first two fields carry an explicit UNKNOWN state, and that is the point
    of the type: ``before=None`` means "git did not answer", which is not ``{}``
    ("the tree is clean"), and ``witness=None`` means "the fingerprint could
    not be read", which is not "nothing moved". ``snapshot=None`` separately
    means there is no safe rollback ref. Collapsing these distinctions is the
    exact shape of two round-10 findings — one of them a silent fail-open that
    survived nine review rounds because ``None != None`` is False.
    """

    before: Optional[dict]
    witness: Optional[str]
    snapshot: Optional[str] = None
    fence: Optional[list[str]] = None


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


def _git_why(repo: Path, *args: str) -> str:
    """git's own words for why the failed command will not answer.

    "git unavailable" is the one thing that is *not* true in most of these
    cases — git ran fine and refused. `detected dubious ownership` (routine on
    Windows when the repo sits under another profile or drive) is one
    `git config --global --add safe.directory <path>` away; a corrupt .git and
    an index.lock conflict are each fixed differently. Collapsing them all into
    one string leaves the operator nothing to act on.

    When ``args`` are supplied, rerun that exact command shape. This matters for
    the fence-limited ignored query: a pathspec failure must not be diagnosed by
    a fresh pathspec-free ``git status`` that succeeds.
    """
    command = ["git", "-C", str(repo), *(args or ("status", "--porcelain"))]
    try:
        proc = subprocess.run(command, capture_output=True, timeout=30, env=_git_env())
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
            # is_dir() FOLLOWS the link, and git does not: it stores a symlink
            # as a blob and `status -uall` lists it as one ordinary file entry.
            # So a `latest -> builds/2026-08-06` convenience link, or a workspace
            # link in a JS monorepo, was classified as an unvettable directory
            # and refused every dispatch whole-tree, pre-turn, regardless of the
            # fence — while the message sent the operator hunting for a submodule
            # that does not exist and no fence edit could clear it. A link is a
            # file to git, and is judged as one.
            if p.is_symlink():
                continue
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


def _fence_pathspecs(repo: Path, fence: list[str]) -> list[str]:
    """Return valid repo-relative Git pathspecs for fence entries.

    Git's default pathspec lets ``*`` and ``?`` cross ``/``; scope_check does
    not, because ``src/*.py`` must not admit ``src/deep/leak.py``. Its ``glob``
    magic supplies the same segment boundary, while ``literal`` keeps brackets
    literal unless the fence author explicitly opted into a glob with ``*`` or
    ``?``. Git already treats a trailing-slash pathspec recursively, so no
    synthetic ``**`` is needed.

    Fence entries are relative to ``repo`` even when ``repo`` is below the Git
    root. Absolute entries are accepted only when they resolve inside ``repo``;
    outside paths, drive-qualified paths, and ``..`` escapes are omitted before
    Git sees them. This keeps a formal absolute scope entry from producing a
    Git fatal while preserving the scope handler's own absolute-path support.
    """
    work_repo = repo.resolve()
    specs: list[str] = []
    for entry in fence:
        raw = entry.strip()
        if not raw:
            continue
        path = raw.replace("\\", "/")
        if len(path) >= 2 and path[1] == ":":
            if len(path) < 3 or path[2] != "/":
                continue
        is_drive_absolute = len(path) >= 3 and path[1] == ":" and path[2] == "/"
        is_absolute = Path(raw).is_absolute() or path.startswith("/") or is_drive_absolute
        candidate = Path(raw) if is_absolute else work_repo / raw
        try:
            relative = candidate.resolve(strict=False).relative_to(work_repo)
        except (OSError, ValueError):
            continue
        normalized = relative.as_posix()
        if path.endswith("/") and normalized != ".":
            normalized += "/"
        path = normalized
        if "*" in path or "?" in path:
            specs.append(f":(glob){path}")
        else:
            specs.append(f":(literal){path}")
    return list(dict.fromkeys(specs))


def collect_changeset(repo: Path, max_files: Optional[int] = None,
                      fence: Optional[list[str]] = None,
                      warnings: Optional[list[str]] = None):
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

    outputs = [(out, False)]
    if fence:
        # Do NOT add --ignored to the main status call. Measured in a UE-style
        # tree, its whole-tree expansion reported 303 paths (and made every
        # dispatch OVERSIZED); removing -uall instead folded untracked work into
        # directories that _opaque_dirs refuses. Keep -uall on this query: without
        # it an untracked fence directory folds to one entry, evades file-path
        # deduplication, pushes the ceiling (see the ceiling regression), and
        # makes _opaque_dirs reject dispatch. Restrict this second query to the
        # dispatched fence, so -uall does not enumerate the whole tree; a large
        # declared directory is still bounded by the existing max_files ceiling.
        #
        # This closes only the fence lane. An ignored write outside the fence is
        # still invisible, and ignored files are absent from `git stash create`,
        # so they can be detected and blocked but cannot be rolled back.
        specs = _fence_pathspecs(repo, fence)
        ignored_args = (
            "status", "--porcelain", "-z", "-uall", "--ignored=traditional", "--",
            *specs,
        )
        ignored = _git_out(repo, *ignored_args) if specs else ""
        if ignored is None:
            if warnings is not None:
                warnings.append(
                    "ignored fence query failed; ignored fence paths were not "
                    f"collected ({_git_why(repo, *ignored_args)})"
                )
        else:
            outputs.append((ignored, True))

    paths: list[str] = []
    ignored_paths: list[str] = []
    for status, is_ignored_query in outputs:
        entries = [e for e in status.split("\0") if e]
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
            normalized = [_repo_relative(root / p, repo) for p in raw]
            paths.extend(normalized)
            if is_ignored_query and code == "!!":
                ignored_paths.extend(normalized)

    # The fence-restricted query deliberately overlaps the ordinary status
    # result for non-ignored paths. One file must reach each handler once, not
    # twice, and the ceiling must bound that merged set before any content read.
    paths = list(dict.fromkeys(paths))
    ignored_paths = list(dict.fromkeys(ignored_paths))
    if warnings is not None and ignored_paths:
        warnings.append(
            "ignored fence paths collected and scanned: "
            + ", ".join(ignored_paths)
        )

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
            # Scanned BEFORE write_handoff, so the handoff itself is not in this
            # delta — _build_and_gate appends it to the Builder's scan by name,
            # every cycle, and scanning it twice would report it twice.
            ad, arch_blocked = self._architect_turn(
                design_prompt(cfg.goal, prior_result, cycle), cycle, "design")
            if ad.error:
                return self._outcome(BLOCKED, cycle, f"architect design error: {ad.error}")
            if arch_blocked is not None:
                return arch_blocked
            bus.write_handoff(ad.text)
            tiers = parse_tiers(ad.text)
            self._emit(f"[cycle {cycle}] tiers={tiers or '(none) -> fail-closed HIGH'}")

            # START gate
            if cfg.confirm_handoff and not self.human.confirm(f"[cycle {cycle}] approve HANDOFF?"):
                return self._outcome(HELD, cycle, "human declined HANDOFF")

            # bus.write_handoff above wrote busmod.HANDOFF, so that is the name
            # the tamper stop must compare — not cfg.handoff_name, which this
            # loop never honours.
            bd, verdicts, has_high, blocked, _implementation_observed = self._build_and_gate(
                bus, ad.text, tiers, cycle, handoff_name=busmod.HANDOFF)
            if blocked is not None:
                return blocked

            # ARCHITECT_REVIEW happens BEFORE any acceptance, so the human never
            # signs off on a cycle the Architect itself then rejects.
            self._emit(f"[cycle {cycle}] ARCHITECT_REVIEW")
            # This turn runs AFTER the net, so without its own scan its writes
            # reached neither layer in this cycle and became baseline dirt in the
            # next — the gap the net was least likely to notice.
            rv, rv_blocked = self._architect_turn(
                review_prompt(ad.text, bd.text), cycle, "review")
            if rv.error:
                return self._outcome(BLOCKED, cycle, f"architect review error: {rv.error}")
            if rv_blocked is not None:
                return rv_blocked
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

    def _architect_turn(self, prompt: str, cycle: int, label: str):
        """Invoke the Architect and secret-scan whatever the turn wrote.

        Returns ``(turn, blocked_or_None)``.

        The ```scope``` fence bounds the BUILDER. The Architect has none, and is
        *expected* to author files no fence names — ``ROLE_ARCHITECT.md`` step 8
        tells it to write an ADR before dispatching at step 9. So its output gets
        the secret layer only.

        Why it needs a layer at all: ``--architect codex`` is a documented
        configuration, and a headless Codex Architect fires no Claude hooks —
        the same asymmetry this whole module exists for. Before the delta rework
        a post-turn whole-tree sweep happened to cover the Architect's files;
        the delta dropped them, because ``_build_and_gate`` takes its baseline
        AFTER the Architect has already written. Everything it authored was
        pre-existing dirt by construction, and the ARCHITECT_REVIEW turn was
        worse still: it runs after the net entirely, so its writes landed in the
        next cycle's baseline and dropped out there too. A key pasted into an
        ADR shipped with the run reporting DONE. The handoff and ``RESULT.md``
        were already re-added by name for exactly this reason; this is the same
        argument applied to the rest of what the Architect touches. The
        protection still covers only paths visible to the unfenced collector:
        an ignored Architect output, including an ignored ADR, remains outside
        this layer because the fence-limited ignored query belongs to the
        Builder turn.
        """
        cfg = self.cfg
        repo = Path(cfg.repo)
        before_raw = collect_changeset(repo, max_files=_MAX_CHANGESET)
        turn = self.architect.invoke(ROLE_ARCHITECT, prompt, cfg)
        if turn.error:
            return turn, None  # the caller reports the vendor error itself
        after_raw = collect_changeset(repo, max_files=_MAX_CHANGESET)

        if before_raw is OVERSIZED or after_raw is OVERSIZED:
            msg = self._oversized_msg("working tree")
            if cfg.net_enforce:
                return turn, self._outcome(BLOCKED, cycle, msg)
            self._emit(f"[cycle {cycle}] net: WARN dryrun — {msg}; skipping the scan")
            return turn, None
        before = _changeset_index(before_raw)
        after = _changeset_index(after_raw)
        if before is None or after is None:
            msg = (f"cannot determine what the architect {label} turn wrote "
                   f"({_git_why(repo)}) — fail-closed")
            if cfg.net_enforce:
                return turn, self._outcome(BLOCKED, cycle, msg)
            self._emit(f"[cycle {cycle}] net: WARN dryrun — {msg}")
            return turn, None

        # Keyed on `after`, NOT on the union the Builder's delta uses. There the
        # union is load-bearing: a path that leaves `git status` was deleted, and
        # a deletion is a fence violation to judge. Here the scan is secret-only,
        # and a path that is gone has no content to scan — the union would add a
        # branch no test could ever kill.
        changes = [safety.Change(path=p, content=content)
                   for p, content in sorted(after.items())
                   if before.get(p, _ABSENT) != content]
        if not changes:
            return turn, None
        self._emit(f"[cycle {cycle}] net: scanning {len(changes)} architect file(s)")
        net = safety.scan(changes, cfg, secret_only=True)
        for r in net.reasons:
            self._emit(f"[cycle {cycle}] net: {r}")
        if net.blocked:
            return turn, self._outcome(
                BLOCKED, cycle, f"safety net blocked the architect {label} output")
        return turn, None

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

    def _gate(self, cycle: int, block_msg: str, warn_tail: Optional[str] = None) -> bool:
        """The single place the net decides enforce-vs-dryrun. True => stop the cycle.

        Nine hand-written copies of ``if cfg.net_enforce: return BLOCKED / else:
        _emit(WARN)`` is how two branches ended up with no copy at all — the
        witness baseline (silently fail-open in enforce) and the Architect's own
        delta — and neither a reviewer nor a test could see the omission, because
        there was nothing to see: the code that should have been there simply
        was not. Centralising the decision does not by itself prevent a missing
        call, but it makes every degrade site one line that looks like every
        other, so an absent one is visible in a way a nine-way copy was not.

        The caller still owns the state repair its own branch needs
        (``before_raw = None``, ``changes = []``, or nothing) — that part is
        genuinely case-specific, and returning a bool forces "and then what?"
        to be answered out loud at each site rather than trailing off.
        """
        if self.cfg.net_enforce:
            return True
        self._emit(f"[cycle {cycle}] net: {warn_tail or 'WARN dryrun — ' + block_msg}")
        return False

    def _pre_turn_checks(self, cycle: int, handoff_text: str, handoff_name: str,
                         fence: list[str]):
        """Everything knowable BEFORE the builder turn. Returns ``(evidence, stop)``.

        ``stop`` is a non-empty reason string when the cycle must be refused.
        Every check here exists because ``cfg.timeout_s`` is 1800s: answering a
        question we already hold the answer to, thirty minutes late, is the
        difference between a refusal and a refusal that also wasted the turn.
        A scope block can restore only paths proven to exist in the pre-turn
        snapshot; every other write remains in place for the operator to review.
        """
        cfg = self.cfg
        repo = Path(cfg.repo)

        # The prompt names the exact dispatch specification, but stale bus files
        # remain an easy way for a Builder to follow an older task by mistake.
        # They are legitimate project artifacts, so this is diagnostic only:
        # list names without reading them and never turn the warning into a gate.
        try:
            stale_handoffs = sorted(
                path.name
                for path in repo.iterdir()
                if (
                    path.is_file()
                    and path.name.startswith("HANDOFF")
                    and path.suffix == ".md"
                    and path.name != handoff_name
                )
            )
        except OSError:
            stale_handoffs = []
        if stale_handoffs:
            self._emit(
                f"[cycle {cycle}] warning: stale handoff file(s): "
                f"{', '.join(stale_handoffs)}"
            )

        # scope_check itself fails OPEN on an absent fence, deliberately, so an
        # interactive session predating ADR-0005 is not frozen. The controller
        # has no such excuse: here a changeset is admitted on the strength of the
        # fence, so no fence is a net that cannot run, not a pass.
        if not fence:
            msg = f"no ```scope``` fence in {handoff_name}: cannot bound the changeset"
            if self._gate(cycle, msg):
                return _Evidence(None, None), msg

        # The net judges the BUILDER'S work, and `git status` reports everything
        # merely dirty — the handoff Claude just wrote, an ADR the Architect
        # authored at step 8, a scratch file from yesterday. Judging all of it
        # against the Builder's whitelist blocks dispatches on files the Builder
        # never touched, and the only workaround is widening the fence, which
        # hands the Builder writes it should not have. The delta is the honest
        # changeset.
        collection_warnings: list[str] = []
        before_raw = collect_changeset(
            repo, max_files=_MAX_CHANGESET, fence=fence, warnings=collection_warnings
        )
        for warning in collection_warnings:
            self._emit(f"[cycle {cycle}] warning: {warning}")
        if before_raw is OVERSIZED:
            # The tree is already past what the net can vet, so a turn would only
            # add to it.
            msg = self._oversized_msg("working tree")
            if self._gate(cycle, msg):
                return _Evidence(None, None), msg
            before_raw = None
        elif before_raw is None:
            msg = (f"cannot determine changeset ({_git_why(repo)}) — "
                   "fail-closed before dispatching the builder")
            if self._gate(cycle, msg):
                return _Evidence(None, None), msg

        # A dirty nested repo is knowable in milliseconds too. The post-turn
        # check stays, for one created mid-turn.
        if before_raw:
            opaque = _opaque_dirs(before_raw, repo)
            if opaque:
                msg = self._opaque_msg(opaque)
                if self._gate(cycle, msg):
                    return _Evidence(None, None), msg

        # The fingerprint is the evidence baseline, and it can fail to compute
        # for reasons that have nothing to do with a Builder: an `ls-files`
        # timeout on a huge tree, an unreadable info/exclude. Those fail the
        # SAME way at both ends, and `None != None` is False — so the entire
        # witness layer (commit, stash, ignore rules, index bits) was skipped in
        # enforce with no warning and no reason, while `collect_changeset`, which
        # needs less from git, kept succeeding and the run looked normal. It was
        # the only "we could not see" case here that failed OPEN.
        witness = _witness_fingerprint(repo)
        if witness is None:
            msg = ("cannot read what git reports from — HEAD, the stash ref, "
                   ".git/info/exclude, core.excludesFile or the "
                   "assume-unchanged/skip-worktree index bits are unreadable, so "
                   "a mid-turn edit to any of them could not be detected; "
                   "fail-closed before dispatching the builder")
            if self._gate(cycle, msg):
                return _Evidence(None, None), msg

        snapshot = _git_out(repo, "stash", "create")
        if snapshot is None:
            self._emit(f"[cycle {cycle}] warning: rollback unavailable; could not snapshot pre-turn tree")
        else:
            snapshot = snapshot.strip() or "HEAD"

        return _Evidence(
            before=_changeset_index(before_raw), witness=witness, snapshot=snapshot,
            fence=list(fence),
        ), None

    def _restore_scope_blocked_paths(
        self, cycle: int, snapshot: Optional[str], paths: list[str]
    ) -> tuple[int, int]:
        """Restore scope-blocked tracked paths from the pre-turn snapshot only."""
        unique_paths = list(dict.fromkeys(paths))
        if not unique_paths:
            return 0, 0

        if snapshot is None:
            for path in unique_paths:
                self._emit(
                    f"[cycle {cycle}] net: rollback unavailable (no pre-turn snapshot): {path}"
                )
            return 0, len(unique_paths)

        repo = Path(self.cfg.repo)
        restored = 0
        left_in_place = 0
        for path in unique_paths:
            if _git_out(repo, "cat-file", "-e", f"{snapshot}:{path}") is None:
                left_in_place += 1
                self._emit(
                    f"[cycle {cycle}] net: rollback unavailable (snapshot has no path): {path}"
                )
                continue
            if _git_out(repo, "restore", f"--source={snapshot}", "--worktree", "--", path) is None:
                left_in_place += 1
                self._emit(f"[cycle {cycle}] net: rollback failed: {path}")
                continue
            restored += 1
            self._emit(f"[cycle {cycle}] net: rolled back: {path}")
        return restored, left_in_place

    def _builder_changes(self, cycle: int, bus: Bus, bd, ev: "_Evidence",
                         handoff_name: str, handoff_text: str, fence: list[str]):
        """What the Builder's turn changed, vetted for trustworthiness.

        Returns ``(changes, stop)``; ``stop`` is a non-empty reason when the
        cycle must be refused. Everything here answers one question — is the
        evidence good enough to judge? — and the answer is only as good as the
        witness, which is why the tamper stop and the fingerprint comparison
        come first.
        """
        cfg = self.cfg
        repo = Path(cfg.repo)

        # The handoff is the spec of record: the fence, the tiers, and what the
        # in-session review will later read this cycle against. A Builder that
        # rewrote it edited its own terms of reference. Compared unconditionally
        # — DELETING it counts, and so does a copy that no longer decodes. (The
        # fence the handler enforces is separately pinned from the dispatched
        # text, so this is not what stops a mid-scan rewrite; it is what stops us
        # accepting work whose spec no longer exists.) Degrades in dryrun like
        # every other check: continuing is safe precisely because the pinned
        # fence comes from the dispatched text, not from the changed file.
        if not _same_text(_read_bus(bus, handoff_name), handoff_text):
            msg = (f"builder altered or removed {handoff_name} — the scope fence is the "
                   "rule it is judged by; refusing to trust the changed copy")
            if self._gate(cycle, msg):
                return [], msg

        # Did the Builder change what `git status` will REPORT? Same reason as
        # the tamper stop. ev.witness is None only in dryrun (enforce already
        # stopped), and there is nothing to compare against then — the baseline
        # was already reported. "Could not look again" is a separate failure from
        # "it moved", and gets a separate message: an operator told the Builder
        # tampered would go hunting for a commit that is not there.
        if bd.changeset is None and ev.witness is not None:
            after_witness = _witness_fingerprint(repo)
            if after_witness is None:
                msg = ("cannot re-read what git reports from after the turn, so a "
                       "mid-turn commit/stash, ignore rule or index-bit change "
                       "cannot be ruled out; fail-closed")
            elif after_witness != ev.witness:
                msg = ("builder changed what git reports — a commit/stash, an ignore "
                       "rule (.git/info/exclude or core.excludesFile), or an "
                       "assume-unchanged/skip-worktree index bit moved during the turn; "
                       "the changeset can no longer be trusted. Leave changes in the "
                       "working tree: the Architect reviews them with `git diff`")
            else:
                msg = ""
            if msg and self._gate(cycle, msg):
                return [], msg

        snapshot_for_opaque = []
        if bd.changeset is not None:
            changes = bd.changeset
            snapshot_for_opaque = changes
            if len(changes) > _MAX_CHANGESET:
                msg = self._oversized_msg("changeset")
                if self._gate(cycle, msg, f"WARN dryrun — {self._oversized_msg('changeset')}; "
                                          "skipping the scan"):
                    return [], msg
                changes = []
        else:
            after_fence = ev.fence if ev.fence is not None else fence
            collection_warnings: list[str] = []
            after = collect_changeset(
                repo,
                max_files=_MAX_CHANGESET,
                fence=after_fence,
                warnings=collection_warnings,
            )
            for warning in collection_warnings:
                self._emit(f"[cycle {cycle}] warning: {warning}")
            if after is OVERSIZED:
                msg = self._oversized_msg("working tree")
                if self._gate(cycle, msg, f"WARN dryrun — {msg}; skipping the scan"):
                    return [], msg
                after = None
            after_index = _changeset_index(after)
            snapshot_for_opaque = after or []
            if after_index is None or ev.before is None:
                msg = f"cannot determine changeset ({_git_why(repo)}) — fail-closed"
                if self._gate(cycle, msg, "WARN git unavailable; changeset unknown"):
                    return [], msg
                changes = []
            else:
                # Key the delta on the UNION of both snapshots, not on `after`
                # alone. A path can leave `git status` entirely — deleting an
                # UNTRACKED file leaves no ' D' entry, it simply vanishes — so an
                # `after`-only comprehension never constructs a Change for it and
                # the fence never sees it. That is the document lane's promise
                # ("the source is out of the fence, so it cannot be touched")
                # failing on the most destructive edit there is, against a file
                # git has no object for and cannot restore.
                changes = [
                    safety.Change(path=p, content=after_index.get(p, ""))
                    for p in sorted(set(ev.before) | set(after_index))
                    if ev.before.get(p, _ABSENT) != after_index.get(p, _ABSENT)
                ]

        # The dispatched handoff is secret-scanned EVERY cycle, changed or not.
        # It normally sits in both snapshots — the Architect wrote it before the
        # turn — so the delta correctly drops it, and dropping it silently removed
        # the key check the old whole-tree sweep did provide: a key pasted into
        # the handoff shipped with the run reporting BUILT. Scope-exempt, never
        # secret-exempt.
        if all(c.path != handoff_name for c in changes):
            changes.append(safety.Change(path=handoff_name, content=handoff_text))
        # RESULT.md is the other file the controller writes, and its content is
        # verbatim Builder-authored text — strictly more exposed than the
        # Architect's handoff. It reaches the net only via the git delta, which
        # misses it whenever the target repo ignores it (this repo's own
        # .gitignore does exactly that). Same fix, same reason.
        if all(c.path != busmod.RESULT for c in changes):
            changes.append(safety.Change(path=busmod.RESULT, content=bd.text))

        # Judged over the SNAPSHOT, not the delta. A nested repo already dirty at
        # dispatch sits in both snapshots as the same directory entry with content
        # "", so it compares equal and drops out of the delta — and then the
        # Builder's writes inside it are neither refused nor scanned, with the run
        # reporting BUILT. A directory is unvettable whether or not it changed.
        opaque = _opaque_dirs(snapshot_for_opaque, repo)
        if opaque:
            msg = self._opaque_msg(opaque)
            if self._gate(cycle, msg):
                return changes, msg

        return changes, None

    def _build_and_gate(
        self, bus: Bus, handoff_text: str, tiers: dict[str, str], cycle: int,
        *, handoff_name: str, tier_gate_hard: bool = True,
        prompt: Optional[str] = None, result_prefix: str = "",
    ):
        """BUILDER_EXECUTE -> RESULT.md -> safety net (3.5) -> tier-gate.

        Shared by run() and run_from_handoff(). Returns
        ``(builder_turn, verdicts, has_high, blocked, implementation_observed)``
        where ``blocked`` is a terminal Outcome on any failure (the caller
        returns it) or ``None`` on success. ``implementation_observed`` means
        the net-scanned delta contained a non-bus file, so a missing verdict may
        be repaired without repeating the implementation.

        ``handoff_name`` is the file the CALLER actually wrote or read, not
        ``cfg.handoff_name``: ``run()`` authors ``bus.HANDOFF`` unconditionally
        while ``run_from_handoff()`` honours the config, and reading the config
        here made the tamper stop compare against a file the writer never wrote.
        The two coincided only because no CLI exposes ``--handoff`` on ``run``;
        adding one would have produced "builder altered or removed HANDOFF_X.md"
        on every cycle — the most alarming and least accurate message this
        system emits. The caller knows; it says.

        The safety net (scope_check / secret_scan) is ALWAYS a hard block — it
        is the deterministic compensation for a Codex Builder firing no Claude
        hooks. ``tier_gate_hard`` controls only the verdict-based tier gate:
        run() keeps it hard (the autonomous loop has no other reviewer); the
        auto-dispatch build path sets it advisory (emit-only) because the
        in-session Claude review + HIGH human sign-off own that judgment, and a
        headless Codex does not reliably emit the machine ```verdicts``` fence.
        """
        cfg = self.cfg

        # A normal Builder turn must not inherit a previous turn's report. Recovery
        # deliberately keeps it because its prompt directs the Builder to use it.
        if prompt is None:
            bus.write_result("")
        fence = busmod.scope_entries(handoff_text)
        ev, stop = self._pre_turn_checks(cycle, handoff_text, handoff_name, fence)
        if stop:
            return None, [], False, self._outcome(BLOCKED, cycle, stop), False

        self._emit(f"[cycle {cycle}] BUILDER_EXECUTE ({cfg.builder_vendor})")
        bd = self.builder.invoke(
            ROLE_BUILDER, prompt or build_prompt(handoff_text, handoff_name), cfg)
        if bd.error:
            return bd, [], False, self._outcome(BLOCKED, cycle, f"builder error: {bd.error}"), False
        if result_prefix:
            bd = Turn(
                text=f"{result_prefix.rstrip()}\n\n{bd.text.lstrip()}",
                changeset=bd.changeset,
            )
        bus.write_result(bd.text)
        verdicts = parse_verdicts(bd.text)

        changes, stop = self._builder_changes(
            cycle, bus, bd, ev, handoff_name, handoff_text, fence)
        if stop:
            return bd, verdicts, False, self._outcome(BLOCKED, cycle, stop), False

        # RESULT.md is ours: the controller wrote it from the Builder's report
        # after the snapshot, so it shows up in the delta but is never the
        # Builder editing an unlisted file. The handoff is the Architect's, and
        # the tamper stop has already proved the Builder did not touch it.
        scope_exempt = {busmod.RESULT, handoff_name}

        if not cfg.net_enforce:
            self._emit(f"[cycle {cycle}] net: WARN dryrun — advisory only, not blocking")
        # Two handler subprocesses per file at ~0.17s each, so a large delta is
        # a minute-plus of silence on a tool whose premise is that the operator
        # is watching a headless dispatch. Say what is about to happen.
        if changes:
            self._emit(f"[cycle {cycle}] net: scanning {len(changes)} file(s)")
        # Pin the fence we DISPATCHED, so the handler judges against that text
        # rather than re-reading a file the Builder can still be writing to.
        net = safety.scan(changes, cfg, scope_exempt=scope_exempt, fence=fence,
                          handoff_name=handoff_name)
        for r in net.reasons:
            self._emit(f"[cycle {cycle}] net: {r}")
        if net.blocked:
            secret_blocked = set(net.secret_blocked_paths)
            rollback_paths = [
                path for path in net.scope_blocked_paths if path not in secret_blocked
            ]
            skipped_secrets = list(dict.fromkeys(
                path for path in net.scope_blocked_paths if path in secret_blocked
            ))
            for path in skipped_secrets:
                self._emit(f"[cycle {cycle}] net: rollback skipped (secret blocked): {path}")
            restored, left_in_place = self._restore_scope_blocked_paths(
                cycle, ev.snapshot, rollback_paths
            )
            left_in_place += len(skipped_secrets)
            reason = "safety net blocked the changeset"
            if net.scope_blocked_paths:
                reason += (
                    f" (rolled back {restored} file(s), {left_in_place} left in place)"
                )
            return bd, verdicts, False, self._outcome(BLOCKED, cycle, reason), False

        # tier-gate enforcement
        gate_reasons = enforce_tier_gates(tiers, verdicts)
        if gate_reasons:
            label = "tier-gate" if tier_gate_hard else "tier-gate(advisory)"
            for r in gate_reasons:
                self._emit(f"[cycle {cycle}] {label}: {r}")
            if tier_gate_hard:
                return bd, verdicts, False, self._outcome(BLOCKED, cycle, "tier-gate enforcement failed"), False

        has_high = compute_has_high(tiers, verdicts)
        implementation_observed = any(
            change.path not in {busmod.RESULT, handoff_name} for change in changes
        )
        return bd, verdicts, has_high, None, implementation_observed

    def run_from_handoff(self) -> Outcome:
        """Run the single-shot build and append its attempt/terminal receipt."""
        cfg = self.cfg
        handoff_name = cfg.handoff_name or busmod.HANDOFF
        audit = BuildAudit(
            audit_dir=Path(cfg.audit_dir),
            repo=Path(cfg.repo),
            handoff_name=handoff_name,
            builder_vendor=cfg.builder_vendor,
            backend=cfg.backend,
        )
        audit.attempted()
        try:
            outcome = self._run_from_handoff(audit)
        except Exception:
            # Do not copy the exception string: a vendor exception may echo a
            # prompt or output. The caller still receives the original error,
            # while the audit keeps the attempted/terminal pairing intact.
            audit.terminal(
                status="blocked",
                outcome="ERROR",
                reason_code="controller_error",
                attempts=0,
            )
            raise
        audit.terminal(
            status=_receipt_status(outcome),
            outcome=outcome.status,
            reason_code=_receipt_reason_code(outcome),
            attempts=outcome.cycles,
        )
        outcome.receipt_path = audit.terminal_path
        outcome.receipt_id = audit.dispatch_id if outcome.receipt_path is not None else ""
        return outcome

    def _run_from_handoff(self, audit: BuildAudit) -> Outcome:
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
        audit.set_handoff(handoff_text)
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
            bd, verdicts, has_high, blocked, implementation_observed = self._build_and_gate(
                bus, handoff_text, tiers, cycle=attempt,
                handoff_name=handoff_name, tier_gate_hard=False,
            )
            if blocked is not None:
                return blocked  # safety net (scope/secret) tripped — hard block
            if not _builder_bailed(verdicts):
                break  # builder completed (advisory panel verdicts pass through)
            if not verdicts and implementation_observed:
                self._emit(
                    f"[build] attempt {attempt}: implementation passed the net but "
                    "the verdict fence is missing -- recovering verdict only"
                )
                recovery_attempt = attempt + 1
                _recovery, verdicts, has_high, blocked, recovery_implementation_observed = self._build_and_gate(
                    bus, handoff_text, tiers, cycle=recovery_attempt,
                    handoff_name=handoff_name, tier_gate_hard=False,
                    prompt=verdict_recovery_prompt(handoff_text, handoff_name), result_prefix=bd.text,
                )
                if blocked is not None:
                    return blocked
                if recovery_implementation_observed:
                    return self._outcome(
                        BLOCKED,
                        recovery_attempt,
                        "builder verdict recovery changed implementation",
                    )
                if _builder_bailed(verdicts):
                    return self._outcome(
                        BLOCKED,
                        recovery_attempt,
                        f"builder verdict recovery failed after {recovery_attempt} attempt(s)",
                    )
                attempt = recovery_attempt
                break
            if attempt < _MAX_BUILD_ATTEMPTS:
                self._emit(
                    f"[build] attempt {attempt}: builder bailed with no "
                    "implementation (likely a false read-only) — retrying once"
                )
        if _builder_bailed(verdicts):
            return self._outcome(
                BLOCKED,
                attempt,
                f"builder bailed with no implementation after {attempt} attempt(s)",
            )
        note = (
            "HIGH gate present — in-session human sign-off required before merge/apply"
            if has_high else "all-LOW"
        )
        self._emit(f"[build] BUILT ({note}) — RESULT.md written, awaiting in-session review")
        return self._outcome(BUILT, attempt, note)


def _receipt_status(outcome: Outcome) -> str:
    """Map controller outcomes to the small stable audit vocabulary."""
    if outcome.status == BUILT:
        return "built"
    if outcome.reason.startswith("builder error: vendor turn timed out after "):
        return "timeout"
    if outcome.reason.startswith("builder bailed with no implementation"):
        return "builder_bailed"
    return "blocked"


def _receipt_reason_code(outcome: Outcome) -> str:
    """Classify an outcome without copying vendor-controlled error text to audit."""
    if outcome.status == BUILT:
        return "built_high" if outcome.reason.startswith("HIGH gate present") else "built_low"
    if outcome.reason.startswith("builder error: vendor turn timed out after "):
        return "timeout"
    if outcome.reason.startswith("builder bailed with no implementation"):
        return "builder_bailed"
    if outcome.reason.startswith("safety net blocked the changeset"):
        return "safety_net"
    if outcome.reason.startswith("cannot read "):
        return "handoff_unreadable"
    if outcome.reason.startswith("no ") and outcome.reason.endswith(" to build from"):
        return "handoff_missing"
    if outcome.reason.startswith("builder error:"):
        return "builder_error"
    return "blocked_other"
