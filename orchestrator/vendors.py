"""Vendor backends — one headless invocation per Architect/Builder turn.

A "session" in the Two-CLI sense is not a long-lived terminal here; it is a
single headless call. Because the harness mandates self-contained HANDOFF/RESULT,
turns are stateless: each reads the bus + repo fresh, so no session-resume is
needed (this is what makes cross-vendor clean).

- MockBackend  — deterministic canned turns; drives the full loop offline. The
  default backend, and the one the tests exercise.
- ClaudeBackend / CodexBackend — real `claude -p` / `codex exec` shell-outs.
  SCAFFOLD: the exact flags / output formats differ across CLI versions and
  must be verified on the machine that has both CLIs authenticated (see
  orchestrator/README.md "Build-time verification"). Not exercised by tests.

Stdlib only.
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .config import Config
from .safety import Change

ROLE_ARCHITECT = "architect"
ROLE_BUILDER = "builder"


@dataclass
class Turn:
    text: str = ""
    changeset: Optional[list[Change]] = None  # mock supplies this; real reads git
    error: str = ""


class Backend:
    """Vendor backend interface. ``invoke`` runs one headless turn."""

    name = "base"

    def invoke(self, role: str, prompt: str, cfg: Config) -> Turn:  # pragma: no cover
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# Mock                                                                        #
# --------------------------------------------------------------------------- #
@dataclass
class Scenario:
    """Canned turns for a deterministic offline run.

    ``handoffs`` / ``results`` / ``reviews`` are per-cycle lists; ``changesets``
    pairs with ``results``. The orchestrator pulls index = cycle-1.
    """
    handoffs: list[str] = field(default_factory=list)
    results: list[str] = field(default_factory=list)
    changesets: list[list[Change]] = field(default_factory=list)
    reviews: list[str] = field(default_factory=list)


def default_low_scenario(goal: str) -> Scenario:
    """A single-cycle, all-LOW scenario that completes cleanly."""
    handoff = (
        f"# HANDOFF: {goal}\n\n## 1. Goal\n{goal}\n\n## 5. 게이트\n"
        "### Gate 1 — implement\n- 작업: 구현\n- 검증: build\n\n"
        "```tiers\ngate 1: LOW\n```\n\n"
        "## Section A — operative scope codeblock\n```scope\nsrc/feature.py\nRESULT.md\n```\n"
    )
    result = (
        "# RESULT\n\n## Summary\n| Gate | Status |\n|---|---|\n| Gate 1 | ✅ |\n\n"
        "```verdicts\ngate 1: status=completed tier=LOW panel=PASS\n```\n"
    )
    changeset = [Change(path="src/feature.py", content="# implemented\nVALUE = 1\n")]
    review = "review: HANDOFF intent met.\n\n```control\nverdict: DONE\nreason: gate 1 verified\n```\n"
    return Scenario(handoffs=[handoff], results=[result], changesets=[changeset], reviews=[review])


class MockBackend(Backend):
    name = "mock"

    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self._cycle = {ROLE_ARCHITECT: 0, ROLE_BUILDER: 0}

    def invoke(self, role: str, prompt: str, cfg: Config) -> Turn:
        s = self.scenario
        if role == ROLE_BUILDER:
            i = self._cycle[ROLE_BUILDER]
            self._cycle[ROLE_BUILDER] += 1
            text = s.results[i] if i < len(s.results) else ""
            cs = s.changesets[i] if i < len(s.changesets) else []
            return Turn(text=text, changeset=cs)
        # architect: design on even calls, review on odd — but we route by
        # prompt marker for robustness.
        is_review = "REVIEW" in prompt.upper()
        i = self._cycle[ROLE_ARCHITECT]
        if is_review:
            text = s.reviews[i] if i < len(s.reviews) else ""
            self._cycle[ROLE_ARCHITECT] += 1
            return Turn(text=text)
        text = s.handoffs[i] if i < len(s.handoffs) else ""
        return Turn(text=text)


# --------------------------------------------------------------------------- #
# Real backends (scaffold — verify flags on your machine)                     #
# --------------------------------------------------------------------------- #
def _run(argv: list[str], cfg: Config) -> Turn:
    # shell=False with a list argv: the prompt (which carries the user goal and
    # prior LLM output) is ONE element, never re-tokenised by a shell. Flag
    # injection via prompt content is the residual surface and is CLI-specific —
    # part of the "verify on your machine" scaffold contract (see README).
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cfg.repo),
            capture_output=True,
            text=True,
            timeout=cfg.timeout_s,
        )
        if proc.returncode != 0:
            return Turn(text=proc.stdout or "", error=f"exit {proc.returncode}: {(proc.stderr or '').strip()}")
        return Turn(text=proc.stdout or "")
    except Exception as exc:  # noqa: BLE001
        return Turn(error=f"{type(exc).__name__}: {exc}")


class ClaudeBackend(Backend):
    """`claude -p` print mode. Hooks fire in this mode (scope/secret net)."""

    name = "claude"

    def invoke(self, role: str, prompt: str, cfg: Config) -> Turn:
        argv = ["claude", "-p", prompt, "--output-format", "text"]
        model = cfg.architect_model if role == ROLE_ARCHITECT else cfg.builder_model
        if model:
            argv += ["--model", model]
        # A Builder edits files autonomously; without a non-interactive
        # permission posture the headless turn would stall on approval.
        # VERIFY this flag name/behaviour on your CLI version.
        if role == ROLE_BUILDER:
            argv += ["--permission-mode", "acceptEdits"]
        return _run(argv, cfg)


class CodexBackend(Backend):
    """`codex exec` non-interactive mode."""

    name = "codex"

    def invoke(self, role: str, prompt: str, cfg: Config) -> Turn:
        argv = ["codex", "exec", prompt, "--cd", str(cfg.repo)]
        model = cfg.architect_model if role == ROLE_ARCHITECT else cfg.builder_model
        if model:
            argv += ["--model", model]
        # A Builder needs write access; an Architect is read-only. VERIFY the
        # sandbox/approval flag names for your Codex version (0.111 vs 0.140+).
        if role == ROLE_BUILDER:
            argv += ["--full-auto"]
        return _run(argv, cfg)


def make_backend(vendor: str) -> Backend:
    """Real backend for a vendor slot."""
    if vendor == "claude":
        return ClaudeBackend()
    if vendor == "codex":
        return CodexBackend()
    raise ValueError(f"unknown vendor: {vendor!r}")
