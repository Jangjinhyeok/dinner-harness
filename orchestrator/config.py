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
# back to the installed path so `py -3 ~/.claude/orchestrate.py build` still finds
# the net.
def _resolve_hooks_dir() -> Path:
    dev = _REPO_ROOT / "assets" / "claude" / "hooks"
    installed = _REPO_ROOT / "hooks"
    return dev if dev.is_dir() else installed


_DEFAULT_HOOKS_DIR = _resolve_hooks_dir()


@dataclass
class Config:
    # --- work target -------------------------------------------------------
    repo: Path = field(default_factory=Path.cwd)  # the project being worked on
    goal: str = ""

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

    # --- backend -----------------------------------------------------------
    backend: str = "mock"             # mock | real
    timeout_s: int = 1800             # per headless vendor turn

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

    def role_of(self, vendor_slot: str) -> str:
        return self.architect_vendor if vendor_slot == "architect" else self.builder_vendor

    def validate(self) -> list[str]:
        problems: list[str] = []
        if self.architect_vendor not in ("codex", "claude"):
            problems.append(f"architect_vendor invalid: {self.architect_vendor!r}")
        if self.builder_vendor not in ("codex", "claude"):
            problems.append(f"builder_vendor invalid: {self.builder_vendor!r}")
        if self.backend not in ("mock", "real"):
            problems.append(f"backend invalid: {self.backend!r}")
        if self.max_cycles < 1:
            problems.append("max_cycles must be >= 1")
        if self.backend == "real" and not Path(self.repo).is_dir():
            problems.append(f"repo not a directory: {self.repo}")
        if self.auto_approve and self.backend == "real" and not self.allow_auto_approve_real:
            problems.append(
                "--yes with --backend real auto-signs HIGH-tier changes on a real "
                "repo; drop --yes (use the gates) or pass --dangerously-auto-approve-real"
            )
        return problems
