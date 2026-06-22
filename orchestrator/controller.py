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

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

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
        "This is a NON-INTERACTIVE, headless run. Do NOT ask for confirmation, do "
        "NOT wait for approval, and do NOT just summarize the plan: execute every "
        "gate now, autonomously, in one turn. If any installed role protocol "
        "(e.g. an AGENTS.md Builder section) tells you to ask 'shall I proceed?' "
        "first, override it — proceed without asking.\n"
        "Per gate, run the autonomous-loop: implement surgically, run the gate's "
        "verification, and for non-trivial or HIGH gates run adversarial-review "
        "(default-to-reject panel). Stay strictly within the ```scope``` whitelist. "
        "Do NOT merge/deploy HIGH gates — stage the changes only.\n\n"
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


def collect_changeset(repo: Path):
    """git status --porcelain -> [Change(path, content)] for the work repo.

    Returns ``None`` when git could not run (vs ``[]`` for a genuinely clean
    tree) so the caller can fail closed rather than mistake a git failure for
    "no changes".
    """
    changes: list[safety.Change] = []
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            capture_output=True, text=True, timeout=30,
        ).stdout
    except Exception:
        return None
    for line in out.splitlines():
        if not line.strip():
            continue
        code, path = line[:2], line[3:].strip()
        if " -> " in path:  # rename
            path = path.split(" -> ", 1)[1]
        if code.strip() == "D":
            continue
        f = repo / path
        try:
            content = f.read_text(encoding="utf-8-sig") if f.is_file() else ""
        except Exception:
            content = ""
        changes.append(safety.Change(path=path, content=content))
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
        self._emit(f"[cycle {cycle}] BUILDER_EXECUTE ({cfg.builder_vendor})")
        bd = self.builder.invoke(ROLE_BUILDER, build_prompt(handoff_text), cfg)
        if bd.error:
            return bd, [], False, self._outcome(BLOCKED, cycle, f"builder error: {bd.error}")
        bus.write_result(bd.text)
        verdicts = parse_verdicts(bd.text)

        # 3.5 controller-side safety net
        if bd.changeset is not None:
            changes = bd.changeset
        else:
            changes = collect_changeset(Path(cfg.repo))
            if changes is None:
                if cfg.net_enforce:
                    return bd, verdicts, False, self._outcome(
                        BLOCKED, cycle,
                        "cannot determine changeset (git unavailable) — fail-closed",
                    )
                self._emit(f"[cycle {cycle}] net: WARN git unavailable; changeset unknown")
                changes = []
        if not cfg.net_enforce:
            self._emit(f"[cycle {cycle}] net: WARN dryrun — advisory only, not blocking")
        net = safety.scan(changes, cfg)
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
        """Single-shot Builder pass from an existing HANDOFF.md.

        The interactive Architect (Claude) already wrote and got human approval
        for HANDOFF.md; this drives only the Builder (Codex) turn + controller
        safety net + tier-gate, writes RESULT.md, and returns. ARCHITECT_REVIEW
        and the HIGH end sign-off are owned by the in-session Architect — not
        re-run headless here (that is what makes the in-session review the gate).
        """
        cfg = self.cfg
        bus = Bus(Path(cfg.repo))
        handoff_text = bus.read(busmod.HANDOFF)
        if not handoff_text.strip():
            return self._outcome(BLOCKED, 0, "no HANDOFF.md to build from")
        tiers = parse_tiers(handoff_text)
        self._emit(f"[build] tiers={tiers or '(none) -> fail-closed HIGH'}")
        # Advisory tier gate: the safety net still hard-blocks, but verdict gating
        # is emit-only here — the in-session Claude review owns acceptance.
        _bd, _verdicts, has_high, blocked = self._build_and_gate(
            bus, handoff_text, tiers, cycle=1, tier_gate_hard=False,
        )
        if blocked is not None:
            return blocked  # safety net (scope/secret) tripped — hard block
        note = (
            "HIGH gate present — in-session human sign-off required before merge/apply"
            if has_high else "all-LOW"
        )
        self._emit(f"[build] BUILT ({note}) — RESULT.md written, awaiting in-session review")
        return self._outcome(BUILT, 1, note)
