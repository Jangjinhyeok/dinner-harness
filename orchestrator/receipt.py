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


def _now_iso_z() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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

    def terminal(self, *, status: str, outcome: str, reason_code: str, attempts: int) -> None:
        self._terminal_written = self._append(
            status,
            outcome=outcome,
            reason_code=reason_code,
            attempts=attempts,
            duration_ms=round((monotonic() - self._started) * 1000),
        )

    @property
    def terminal_path(self) -> Optional[Path]:
        return self.path if self._terminal_written else None

    def _append(self, status: str, **extra: object) -> bool:
        record: dict[str, object] = {
            "schema": _SCHEMA,
            "timestamp": _now_iso_z(),
            "dispatch_id": self.dispatch_id,
            "event": "builder_dispatch",
            "status": status,
            "repo_sha256": _digest(str(self.repo.resolve())),
            "handoff_name_sha256": _digest(self.handoff_name),
            "builder_vendor": self.builder_vendor,
            "backend": self.backend,
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
