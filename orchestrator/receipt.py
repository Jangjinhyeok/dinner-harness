"""Content-free audit receipts for headless Builder dispatches.

Receipts deliberately live in the harness runtime, never in the target work
repository: a target-side receipt would become part of the Builder delta the
safety net judges.  The JSONL records contain hashes and outcome metadata only;
they never store a handoff, RESULT, prompt, or changed file content.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Optional


_SCHEMA = "dinner-harness.build-audit.v1"
_AUDIT_FILENAME = "build-audit.jsonl"
_ORCHESTRATOR_SHA256: Optional[str] = None


def _now_iso_z() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _orchestrator_sha256() -> str:
    """Fingerprint the installed orchestrator code without affecting dispatches."""
    global _ORCHESTRATOR_SHA256
    if _ORCHESTRATOR_SHA256 is not None:
        return _ORCHESTRATOR_SHA256
    try:
        directory = Path(__file__).resolve().parent
        digest = hashlib.sha256()
        for path in sorted(directory.glob("*.py"), key=lambda item: item.name):
            digest.update(path.name.encode("utf-8"))
            digest.update(b"\n")
            digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii"))
            digest.update(b"\n")
        _ORCHESTRATOR_SHA256 = digest.hexdigest()
    except OSError:
        _ORCHESTRATOR_SHA256 = "unknown"
    return _ORCHESTRATOR_SHA256


@dataclass
class BuildAudit:
    """Append attempt and terminal metadata for one ``build`` invocation.

    Audit I/O is observational: an unavailable log directory must not turn a
    legitimate Builder result into a different execution result.
    """

    audit_dir: Path
    repo: Path
    handoff_name: str
    builder_vendor: str
    backend: str
    dispatch_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    # "builder_dispatch" (default, unchanged for every existing caller) or
    # "challenge_dispatch" for a challenger_high read-only dispatch.
    event: str = "builder_dispatch"
    _started: float = field(default_factory=monotonic, init=False)
    _handoff_digest: str = field(default="", init=False)
    _terminal_written: bool = field(default=False, init=False)

    @property
    def path(self) -> Path:
        return self.audit_dir / _AUDIT_FILENAME

    def set_handoff(self, handoff_text: str) -> None:
        self._handoff_digest = _digest(handoff_text)

    def attempted(self) -> None:
        self._append("attempted")

    def terminal(
        self, *, status: str, outcome: str, reason_code: str, attempts: int,
        **extra: object,
    ) -> None:
        """``extra`` carries additional content-free metadata (routing_preset,
        logical_profile, model, effort, and — for a challenge-audit use of this
        same class — challenged_hash/challenge_result_hash). Never pass prompt,
        HANDOFF/RESULT text, or any file content here — this file's own module
        docstring's content-free guarantee applies to every field, including
        these (ADR-0020 correction 5)."""
        self._terminal_written = self._append(
            status,
            outcome=outcome,
            reason_code=reason_code,
            attempts=attempts,
            duration_ms=round((monotonic() - self._started) * 1000),
            **extra,
        )

    @property
    def terminal_path(self) -> Optional[Path]:
        return self.path if self._terminal_written else None

    def _append(self, status: str, **extra: object) -> bool:
        record: dict[str, object] = {
            "schema": _SCHEMA,
            "timestamp": _now_iso_z(),
            "dispatch_id": self.dispatch_id,
            "event": self.event,
            "status": status,
            "repo_sha256": _digest(str(self.repo.resolve())),
            "handoff_name_sha256": _digest(self.handoff_name),
            "builder_vendor": self.builder_vendor,
            "backend": self.backend,
            "orchestrator_sha256": _orchestrator_sha256(),
        }
        if self._handoff_digest:
            record["handoff_sha256"] = self._handoff_digest
        record.update(extra)
        try:
            self.audit_dir.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="") as f:
                f.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            return True
        except OSError:
            return False


def content_hash(value: str) -> str:
    """Public alias of the internal digest helper — for a caller (e.g.
    controller.py's challenge dispatch) that needs to hash a challenge
    result's text the same way this module hashes a handoff, without
    duplicating hashing logic."""
    return _digest(value)


def find_challenge_evidence(audit_dir: Path, handoff_hash: str) -> bool:
    """True if audit_dir's JSONL log has a successful challenge_dispatch
    record whose handoff_sha256 matches handoff_hash. Used to fail-closed a
    HIGH-tier Builder dispatch that has no matching challenge evidence
    (ADR-0020 correction 5). Any read/parse failure is treated as "no
    evidence" — fail-closed, never fail-open on a corrupt or unreadable log.
    """
    path = audit_dir / _AUDIT_FILENAME
    if not path.is_file():
        return False
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return False
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        if (
            record.get("event") == "challenge_dispatch"
            and record.get("status") == "challenged"
            and record.get("handoff_sha256") == handoff_hash
        ):
            return True
    return False
