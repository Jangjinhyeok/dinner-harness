"""File bus + machine-readable fence parsing.

The Two-CLI bus is three project-root files: HANDOFF.md (Architect->Builder),
RESULT.md (Builder->Architect), INPUT.md (human->Builder, optional). On top of
the human-readable prose, the orchestrator asks each vendor to emit small
fenced blocks it can parse deterministically (no NLP):

  ```tiers      in HANDOFF, by Architect  -> gate -> LOW|HIGH
  ```verdicts   in RESULT,  by Builder     -> gate -> status/tier/panel
  ```control    in Architect review stdout -> DONE|NEXT_CYCLE|BLOCKED

Fail-closed: a gate with a missing/garbled tier is treated as HIGH.
Stdlib only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

HANDOFF = "HANDOFF.md"
RESULT = "RESULT.md"
INPUT = "INPUT.md"

TIER_HIGH = "HIGH"
TIER_LOW = "LOW"

PANEL_PASS = "PASS"
PANEL_FAIL = "FAIL"
PANEL_BLOCK = "BLOCK"

VERDICT_DONE = "DONE"
VERDICT_NEXT = "NEXT_CYCLE"
VERDICT_BLOCKED = "BLOCKED"


def _fence_re(name: str) -> "re.Pattern[str]":
    # First ```<name> ... ``` block. DOTALL body, MULTILINE fences.
    return re.compile(rf"^```{name}\s*$(.*?)^```\s*$", re.DOTALL | re.MULTILINE)


def extract_fence(text: str, name: str) -> Optional[str]:
    """Return the inner body of the first ```<name>``` fence, or None."""
    m = _fence_re(name).search(text or "")
    return m.group(1) if m else None


def _gate_key(raw: str) -> str:
    """Normalize a gate label: 'Gate 2', 'gate2', '2' -> '2'."""
    m = re.search(r"(\d+)", raw)
    return m.group(1) if m else raw.strip().lower()


@dataclass
class GateTier:
    gate: str
    tier: str  # LOW | HIGH


def parse_tiers(handoff_text: str) -> dict[str, str]:
    """Parse the ```tiers``` fence -> {gate_key: LOW|HIGH}.

    Lines look like ``gate 1: LOW`` / ``2: HIGH``. Unknown/garbled tier ->
    HIGH (fail-closed). A missing fence yields {} (caller treats every gate as
    HIGH via :func:`tier_for`).
    """
    body = extract_fence(handoff_text, "tiers")
    out: dict[str, str] = {}
    if not body:
        return out
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        label, _, val = line.partition(":")
        tier = val.strip().upper()
        out[_gate_key(label)] = TIER_HIGH if tier not in (TIER_LOW, TIER_HIGH) else tier
    return out


def tier_for(tiers: dict[str, str], gate: str) -> str:
    """Look up a gate's tier, defaulting to HIGH (fail-closed)."""
    return tiers.get(_gate_key(gate), TIER_HIGH)


@dataclass
class GateVerdict:
    gate: str
    status: str = ""
    tier: str = TIER_HIGH
    panel: str = ""  # PASS | FAIL | BLOCK | "" (not run)


_KV_RE = re.compile(r"(\w+)\s*=\s*([^\s]+)")


def parse_verdicts(result_text: str) -> list[GateVerdict]:
    """Parse the ```verdicts``` fence in RESULT.md.

    Lines: ``gate 1: status=completed tier=LOW panel=PASS``. Unknown tier ->
    HIGH (fail-closed). Missing fence -> [].
    """
    body = extract_fence(result_text, "verdicts")
    out: list[GateVerdict] = []
    if not body:
        return out
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        label, _, rest = line.partition(":")
        kv = {k.lower(): v for k, v in _KV_RE.findall(rest)}
        tier = (kv.get("tier", "") or "").upper()
        out.append(
            GateVerdict(
                gate=_gate_key(label),
                status=kv.get("status", ""),
                tier=TIER_HIGH if tier not in (TIER_LOW, TIER_HIGH) else tier,
                panel=(kv.get("panel", "") or "").upper(),
            )
        )
    return out


@dataclass
class Control:
    verdict: str = VERDICT_BLOCKED  # fail-closed default
    reason: str = ""


def parse_control(review_text: str) -> Control:
    """Parse the ```control``` fence from an Architect review turn.

    ``verdict: DONE|NEXT_CYCLE|BLOCKED`` + optional ``reason:``. A missing or
    unrecognised verdict yields BLOCKED (fail-closed) so the loop never
    silently auto-completes on a malformed review.
    """
    body = extract_fence(review_text, "control")
    if not body:
        return Control(reason="no ```control``` fence in review output")
    verdict = VERDICT_BLOCKED
    reason = ""
    for raw in body.splitlines():
        line = raw.strip()
        if line.lower().startswith("verdict:"):
            v = line.split(":", 1)[1].strip().upper()
            if v in (VERDICT_DONE, VERDICT_NEXT, VERDICT_BLOCKED):
                verdict = v
        elif line.lower().startswith("reason:"):
            reason = line.split(":", 1)[1].strip()
    return Control(verdict=verdict, reason=reason)


@dataclass
class Bus:
    """Reads/writes the three bus files at ``root``."""

    root: Path

    def path(self, name: str) -> Path:
        return self.root / name

    def write(self, name: str, text: str) -> Path:
        p = self.path(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def read(self, name: str) -> str:
        p = self.path(name)
        return p.read_text(encoding="utf-8-sig") if p.is_file() else ""

    def write_handoff(self, text: str) -> Path:
        return self.write(HANDOFF, text)

    def write_result(self, text: str) -> Path:
        return self.write(RESULT, text)
