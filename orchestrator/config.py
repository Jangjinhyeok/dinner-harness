"""Orchestrator configuration.

Stdlib only. All knobs have defaults; the CLI overrides them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Repo root = parent of this package's parent (orchestrator/ lives at repo root).
_REPO_ROOT = Path(__file__).resolve().parent.parent

# The harness hook handlers reused as the controller-side deterministic net.
# Two layouts resolve the same _REPO_ROOT differently: in the dev source tree the
# hooks live at assets/claude/hooks; once installed to ~/.claude (orchestrator/
# copied alongside hooks/) they live at <root>/hooks. Prefer the dev path, fall
# back to the installed path so the quoted absolute-path `orchestrate.py build` still finds
# the net.
def _resolve_hooks_dir() -> Path:
    dev = _REPO_ROOT / "assets" / "claude" / "hooks"
    installed = _REPO_ROOT / "hooks"
    return dev if dev.is_dir() else installed


_DEFAULT_HOOKS_DIR = _resolve_hooks_dir()
_DEFAULT_AUDIT_DIR = _REPO_ROOT / "logs"


def _is_inside(child: Path, parent: Path) -> bool:
    """Whether ``child`` is ``parent`` or a descendant after symlink resolve."""
    try:
        child.resolve(strict=False).relative_to(parent.resolve(strict=False))
        return True
    except (OSError, ValueError):
        return False


@dataclass
class Config:
    # --- work target -------------------------------------------------------
    repo: Path = field(default_factory=Path.cwd)  # the project being worked on
    goal: str = ""
    # Input handoff filename (relative to repo) the build path reads. Default
    # HANDOFF.md; a project that repurposes HANDOFF.md as a persistent doc can
    # point `build` at an alternate spec (e.g. HANDOFF_WEBVIEW.md) so auto-dispatch
    # never has to clobber it. Only the run-from-handoff build path honours this;
    # the full `run` loop always authors HANDOFF.md — and says so explicitly by
    # passing that name down, rather than letting the gate re-read this field and
    # tamper-check a file the loop never wrote.
    handoff_name: str = "HANDOFF.md"

    # --- vendor <-> role mapping (bidirectional) ---------------------------
    # Default: Claude architects, Codex builds. Builder is the token sink
    # (many-file reads, diff generation, build/error iterate loops, large
    # context), so it goes on the higher-quota plan (Codex); the lower-volume,
    # higher-leverage Architect (reasoning, spec authoring, diff review) goes on
    # the quota-constrained plan (Claude Pro). Rational placement once Claude is
    # downgraded Max->Pro. Note: a Codex Builder does NOT fire the Claude
    # scope_check / secret_scan hooks, so the controller-side net (safety.py) is
    # load-bearing in this default, not just the reverse pairing.
    architect_vendor: str = "claude"  # codex | claude
    builder_vendor: str = "codex"     # codex | claude
    architect_model: str = ""         # "" = vendor default
    builder_model: str = ""
    architect_effort: str = ""        # "" = vendor/profile default; low|medium|high|xhigh|max
    builder_effort: str = ""
    # "" = use routing.toml's own declared [routing].preset; an explicit
    # --routing-preset CLI override (wired in a later gate) takes precedence.
    # See docs/architecture/ADR-0020-routing-preset-architecture.md.
    routing_preset: str = ""

    # --- backend -----------------------------------------------------------
    backend: str = "mock"             # mock | real
    timeout_s: float = 1800           # per headless vendor turn

    # --- loop control ------------------------------------------------------
    max_cycles: int = 5

    # --- human gates (the only places a human is invoked) ------------------
    confirm_handoff: bool = True      # start gate: confirm the proposed HANDOFF once
    # HIGH sign-off and final acceptance are always required for a human run;
    # auto_approve forces them open (mock / CI / explicit --yes).
    auto_approve: bool = False
    # auto_approve on a REAL run auto-signs HIGH-tier changes — refused unless
    # this explicit override is set (see validate()).
    allow_auto_approve_real: bool = False

    # --- safety net --------------------------------------------------------
    hooks_dir: Path = field(default_factory=lambda: _DEFAULT_HOOKS_DIR)
    # The net always runs in enforce so a real secret/scope hit blocks the
    # cycle regardless of the shipped hook default (dryrun).
    net_enforce: bool = True

    # Dispatch receipts stay beside the harness, not inside ``repo``: putting
    # audit artifacts in the worktree would add them to the Builder delta and
    # contaminate the safety-net decision they are meant to record.
    audit_dir: Path = field(default_factory=lambda: _DEFAULT_AUDIT_DIR)

    def role_of(self, vendor_slot: str) -> str:
        return self.architect_vendor if vendor_slot == "architect" else self.builder_vendor

    def validate(self) -> list[str]:
        problems: list[str] = []
        if self.architect_vendor not in ("", "codex", "claude"):
            problems.append(f"architect_vendor invalid: {self.architect_vendor!r}")
        if self.builder_vendor not in ("", "codex", "claude"):
            problems.append(f"builder_vendor invalid: {self.builder_vendor!r}")
        if self.backend not in ("mock", "real"):
            problems.append(f"backend invalid: {self.backend!r}")
        _valid_effort = ("", "low", "medium", "high", "xhigh", "max")
        if self.architect_effort not in _valid_effort:
            problems.append(f"architect_effort invalid: {self.architect_effort!r}")
        if self.builder_effort not in _valid_effort:
            problems.append(f"builder_effort invalid: {self.builder_effort!r}")
        # The scope_check handler resolves the fence as DINNER_HARNESS_HOME /
        # <basename>, so a handoff in a subdirectory would leave the controller
        # reading repo/specs/H.md while the handler looks for repo/H.md, finds
        # nothing, and fails OPEN — the scope layer silently disarmed by a CLI
        # flag. Refuse the input rather than let the two sides disagree.
        if self.handoff_name and (
            "/" in self.handoff_name or "\\" in self.handoff_name or self.handoff_name in (".", "..")
        ):
            problems.append(
                f"handoff_name must be a bare filename in the repo root: {self.handoff_name!r}"
            )
        if self.max_cycles < 1:
            problems.append("max_cycles must be >= 1")
        if self.timeout_s <= 0:
            problems.append("timeout_s must be > 0")
        if self.audit_dir.exists() and not self.audit_dir.is_dir():
            problems.append(f"audit_dir is not a directory: {self.audit_dir}")
        if _is_inside(Path(self.audit_dir), Path(self.repo)):
            problems.append(
                "audit_dir must be outside repo: receipts cannot enter the Builder worktree"
            )
        if self.backend == "real" and not Path(self.repo).is_dir():
            problems.append(f"repo not a directory: {self.repo}")
        if self.auto_approve and self.backend == "real" and not self.allow_auto_approve_real:
            problems.append(
                "--yes with --backend real auto-signs HIGH-tier changes on a real "
                "repo; drop --yes (use the gates) or pass --dangerously-auto-approve-real"
            )
        return problems
