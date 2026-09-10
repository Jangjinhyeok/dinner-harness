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

import json
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


def scope_entries(handoff_text: str) -> list[str]:
    """Entries of the first ```scope``` fence: the Builder's edit whitelist.

    Blank and ``#`` comment lines are dropped, so an all-comment fence yields
    ``[]`` — it bounds nothing, which is the same hole as no fence at all.

    Callers use only the emptiness of this list; the authoritative per-path
    matching lives in the ``scope_check`` handler. Parsing the fence in one
    place keeps the controller's "is there a fence?" question from drifting
    away from the handler's "does this path match?" answer.
    """
    body = extract_fence(handoff_text, "scope")
    if body is None:
        return []
    return [
        line.strip()
        for line in body.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _gate_key(raw: str) -> str:
    """Normalize a gate label: 'Gate 2', 'gate2', '2' -> '2'."""
    m = re.search(r"(\d+)", raw)
    return m.group(1) if m else raw.strip().lower()


@dataclass
class GateTier:
    gate: str
    tier: str  # LOW | HIGH


def parse_tiers(handoff_text: str) -> dict[str, str]:
    """Parse the ```tiers``` fence -> {gate_key: LOW|HIGH} (risk tier only).

    Lines look like ``gate 1: LOW`` / ``2: HIGH`` (bare — unchanged since
    before this function supported anything else) or ``gate 1: risk=LOW
    compute=NORMAL`` (KV form — see :func:`parse_compute_tiers` for the
    compute half of the same line). Unknown/garbled risk -> HIGH
    (fail-closed). A missing fence yields {} (caller treats every gate as
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
        val = val.strip()
        if "=" in val:
            kv = {k.lower(): v for k, v in _KV_RE.findall(val)}
            tier = (kv.get("risk", "") or "").upper()
        else:
            tier = val.upper()
        out[_gate_key(label)] = TIER_HIGH if tier not in (TIER_LOW, TIER_HIGH) else tier
    return out


def tier_for(tiers: dict[str, str], gate: str) -> str:
    """Look up a gate's tier, defaulting to HIGH (fail-closed)."""
    return tiers.get(_gate_key(gate), TIER_HIGH)


COMPUTE_LOW = "LOW"
COMPUTE_NORMAL = "NORMAL"
COMPUTE_HIGH = "HIGH"
_VALID_COMPUTE = (COMPUTE_LOW, COMPUTE_NORMAL, COMPUTE_HIGH)


def parse_compute_tiers(handoff_text: str) -> dict[str, str]:
    """Parse the ``compute=`` value from the ```tiers``` fence's KV form ->
    {gate_key: LOW|NORMAL|HIGH}. A gate written in the old bare risk-only
    form, or carrying an unrecognized/garbled compute value, is simply absent
    from the returned dict — :func:`effective_compute` resolves the default
    (NORMAL, or HIGH when risk is HIGH), not this function. This keeps
    ``parse_tiers`` the single place risk is judged fail-closed, and this
    function purely observational for compute.
    """
    body = extract_fence(handoff_text, "tiers")
    out: dict[str, str] = {}
    if not body:
        return out
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        label, _, val = line.partition(":")
        val = val.strip()
        if "=" not in val:
            continue
        kv = {k.lower(): v for k, v in _KV_RE.findall(val)}
        compute = (kv.get("compute", "") or "").upper()
        if compute in _VALID_COMPUTE:
            out[_gate_key(label)] = compute
    return out


def effective_compute(tiers: dict[str, str], compute_tiers: dict[str, str], gate: str) -> str:
    """The compute tier that actually governs profile resolution for one gate:
    risk HIGH always forces effective compute HIGH (ADR-0020 — risk HIGH ->
    challenger_high -> builder_high regardless of what compute was declared);
    otherwise the declared compute tier, defaulting to NORMAL when missing or
    garbled (ADR-0020: "compute ambiguity/missing -> NORMAL", distinct from
    risk's own "ambiguity -> HIGH" fail-closed default).
    """
    if tier_for(tiers, gate) == TIER_HIGH:
        return COMPUTE_HIGH
    compute = compute_tiers.get(_gate_key(gate), COMPUTE_NORMAL)
    return compute if compute in _VALID_COMPUTE else COMPUTE_NORMAL


@dataclass
class GateVerdict:
    gate: str
    status: str = ""
    tier: str = TIER_HIGH
    panel: str = ""  # PASS | FAIL | BLOCK | "" (not run)
    self_review: str = "not_run"
    verification_claim: str = "not_run"


class ContractError(ValueError):
    """A handoff or result cannot safely identify the work performed."""


class GateBoundaryError(ContractError):
    """Reported execution crossed a HIGH boundary; format recovery cannot undo it."""


def effective_high_gates(verdicts: list[GateVerdict], selected: dict[str, str]) -> list[str]:
    reported_high = {v.gate for v in verdicts if v.tier == TIER_HIGH}
    return sorted((gate for gate in selected if tier_for(selected, gate) == TIER_HIGH
                   or gate in reported_high), key=gate_order)


def gate_order(gate: str) -> int:
    if not re.fullmatch(r"[1-9][0-9]*", gate):
        raise ContractError(f"invalid gate ID: {gate!r}")
    return int(gate)


def dispatch_gates(handoff_text: str) -> tuple[dict[str, str], dict[str, str]]:
    """Validate declarations and select the numeric prefix through the first HIGH.

    A new build starts from the declared gates; callers must supply a new handoff
    for remaining work. Stale RESULT files are never completion evidence.
    """
    bodies = _fence_re("tiers").findall(handoff_text)
    if len(bodies) != 1:
        raise ContractError("exactly one tiers fence is required")
    seen = set()
    for raw in bodies[0].splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        label, separator, value = line.partition(":")
        match = re.fullmatch(r"(?:gate\s*)?([1-9][0-9]*)", label.strip(), re.I)
        if not separator or not match:
            raise ContractError("invalid gate declaration")
        key = match[1]
        if key in seen:
            raise ContractError(f"duplicate gate {key}")
        seen.add(key)
        if "=" in value:
            pairs = _KV_RE.findall(value)
            keys = [k.lower() for k, _ in pairs]
            if len(keys) != len(set(keys)) or set(keys) - {"risk", "compute"}:
                raise ContractError(f"ambiguous fields for gate {key}")
            if _KV_RE.sub("", value).strip():
                raise ContractError(f"malformed fields for gate {key}")
    if not seen:
        raise ContractError("no gates declared")
    tiers = parse_tiers(handoff_text)
    compute = parse_compute_tiers(handoff_text)
    selected = {}
    for gate in sorted(tiers, key=gate_order):
        selected[gate] = tiers[gate]
        if tiers[gate] == TIER_HIGH:
            break
    return selected, {g: compute[g] for g in selected if g in compute}


RESULT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["schema_version", "summary", "gates"],
    "properties": {
        "schema_version": {"type": "integer", "enum": [1]},
        "summary": {"type": "string"},
        "gates": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["gate", "status", "tier", "self_review", "verification_claim"],
            "properties": {
                "gate": {"type": "string", "pattern": "^[1-9][0-9]*$"},
                "status": {"type": "string", "enum": ["completed", "blocked", "pending", "needs_review"]},
                "tier": {"type": "string", "enum": ["LOW", "HIGH"]},
                "self_review": {"type": "string", "enum": ["pass", "fail", "not_run"]},
                "verification_claim": {"type": "string", "enum": ["pass", "fail", "not_run"]},
            },
        }},
    },
}


def parse_build_result(text: str, *, compatibility: bool = False) -> list[GateVerdict]:
    """JSON is the Codex contract; Markdown is an explicit legacy adapter."""
    if compatibility and not text.lstrip().startswith("{"):
        if len(_fence_re("verdicts").findall(text)) != 1:
            raise ContractError("exactly one compatibility verdicts fence is required")
        return parse_verdicts(text)
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise ContractError("invalid result JSON") from exc
    if not isinstance(data, dict) or set(data) != {"schema_version", "summary", "gates"}:
        raise ContractError("invalid result fields")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ContractError("unsupported result schema")
    if not isinstance(data["summary"], str) or not isinstance(data["gates"], list):
        raise ContractError("invalid summary or gates")
    verdicts = []
    fields = {"gate", "status", "tier", "self_review", "verification_claim"}
    for entry in data["gates"]:
        if not isinstance(entry, dict) or set(entry) != fields:
            raise ContractError("invalid gate result fields")
        if any(not isinstance(value, str) for value in entry.values()):
            raise ContractError("gate result fields must be strings")
        if entry["tier"] not in (TIER_LOW, TIER_HIGH):
            raise ContractError("invalid result tier")
        if any(entry[k] not in ("pass", "fail", "not_run") for k in ("self_review", "verification_claim")):
            raise ContractError("invalid review or verification claim")
        verdicts.append(GateVerdict(**entry))
    return verdicts


def reported_gate_evidence(text: str, *, compatibility: bool = False) -> list[GateVerdict]:
    """Extract only identifiable execution claims, never acceptance evidence.

    Extra schema fields must not hide a boundary violation behind format repair.
    Strict parsing/validation is still required before accepting any completion.
    """
    if compatibility and not text.lstrip().startswith("{"):
        verdicts = [v for body in _fence_re("verdicts").findall(text)
                    for v in parse_verdicts("```verdicts\n" + body + "\n```\n")]
    else:
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            return []
        if not isinstance(data, dict) or not isinstance(data.get("gates"), list):
            return []
        verdicts = [GateVerdict(entry["gate"], entry["status"], entry.get("tier", TIER_HIGH))
                    for entry in data["gates"] if isinstance(entry, dict)
                    and isinstance(entry.get("gate"), str) and isinstance(entry.get("status"), str)]
    return [v for v in verdicts if re.fullmatch(r"[1-9][0-9]*", v.gate)]


def validate_high_boundary(verdicts: list[GateVerdict], selected: dict[str, str]) -> None:
    high = effective_high_gates(verdicts, selected)
    if high:
        crossed = sorted({v.gate for v in verdicts if v.status == "completed"
                          and re.fullmatch(r"[1-9][0-9]*", v.gate)
                          and gate_order(v.gate) > gate_order(high[0])}, key=gate_order)
        if crossed:
            raise GateBoundaryError(
                f"completed gate(s) {', '.join(crossed)} after effective HIGH gate {high[0]}")


def validate_results(verdicts: list[GateVerdict], selected: dict[str, str]) -> None:
    # Execution violations take precedence over recoverable shape errors.
    validate_high_boundary(verdicts, selected)
    seen = set()
    for verdict in verdicts:
        gate_order(verdict.gate)
        if verdict.gate in seen or verdict.gate not in selected:
            raise ContractError(f"duplicate or undeclared gate {verdict.gate}")
        seen.add(verdict.gate)
        if verdict.status not in ("completed", "blocked", "pending", "needs_review"):
            raise ContractError(f"invalid gate status: {verdict.status!r}")
    if seen != set(selected):
        raise ContractError("missing verdict for dispatched gate(s)")
    stopped = False
    for verdict in sorted(verdicts, key=lambda v: gate_order(v.gate)):
        if stopped and verdict.status == "completed":
            raise ContractError("completed gate after an incomplete dependency")
        stopped |= verdict.status != "completed"


def render_result(text: str, verdicts: list[GateVerdict], *, net_status: str) -> str:
    try:
        data = json.loads(text)
        summary = data.get("summary", "") if isinstance(data, dict) else text
        if not isinstance(summary, str):
            summary = text
    except ValueError:
        summary = text
    lines = ["# Build result", "", summary, "", f"Controller scope/secret checks: {net_status}",
             "Independent implementation review: not_run", "Human acceptance: pending", "",
             "Builder verification values below are self-reports, not executed-check evidence.", ""]
    for v in sorted(verdicts, key=lambda v: gate_order(v.gate)):
        lines.append(f"- Gate {v.gate}: {v.status}; risk={v.tier}; self_review={v.self_review}; verification_claim={v.verification_claim}")
    return "\n".join(lines) + "\n"


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
