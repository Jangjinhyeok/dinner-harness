"""Content-free audit receipts for headless Builder dispatches.

Receipts deliberately live in the harness runtime, never in the target work
repository: a target-side receipt would become part of the Builder delta the
safety net judges.  The JSONL records contain hashes and outcome metadata only;
they never store a handoff, RESULT, prompt, or changed file content.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Optional


_SCHEMA = "dinner-harness.build-audit.v1"
_AUDIT_FILENAME = "build-audit.jsonl"
_ORCHESTRATOR_SHA256: Optional[str] = None


class ReceiptError(RuntimeError):
    """Required policy evidence could not be read or durably recorded."""


def repo_identity(repo: Path) -> str:
    return _digest(os.path.normcase(str(repo.resolve())))


def task_identity(repo: Path, handoff_name: str, task_id: str = "") -> str:
    """Stable across draft edits; choose a new explicit ID when reusing a filename."""
    return _digest(task_id) if task_id else _digest(repo_identity(repo) + ":" + handoff_name)


def _now_iso_z() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


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

    Ordinary audit I/O is observational. Policy-bearing challenge evidence
    uses terminal(required=True), which fails closed if it cannot be persisted.
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
    task_id: str = ""
    policy_hash: str = ""
    _started: float = field(default_factory=monotonic, init=False)
    _handoff_digest: str = field(default="", init=False)
    _terminal_written: bool = field(default=False, init=False)
    _required_path: Optional[Path] = field(default=None, init=False)

    @property
    def path(self) -> Path:
        return self.audit_dir / _AUDIT_FILENAME

    def set_handoff(self, handoff_text: str) -> None:
        self._handoff_digest = _digest(handoff_text)

    def attempted(self) -> None:
        self._append("attempted")

    def terminal(
        self, *, status: str, outcome: str, reason_code: str, attempts: int,
        required: bool = False, **extra: object,
    ) -> bool:
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
            required=required,
            **extra,
        )
        return self._terminal_written

    @property
    def terminal_path(self) -> Optional[Path]:
        return (self._required_path or self.path) if self._terminal_written else None

    def _append(self, status: str, *, required: bool = False, **extra: object) -> bool:
        if required and (not self.task_id or not self.policy_hash or not self._handoff_digest):
            raise ReceiptError("required receipt is missing task, policy, or HANDOFF binding")
        record: dict[str, object] = {
            "schema": _SCHEMA,
            "timestamp": _now_iso_z(),
            "dispatch_id": self.dispatch_id,
            "event": self.event,
            "status": status,
            "repo_sha256": repo_identity(self.repo),
            "handoff_name_sha256": _digest(self.handoff_name),
            "builder_vendor": self.builder_vendor,
            "backend": self.backend,
            "orchestrator_sha256": _orchestrator_sha256(),
            "task_id": self.task_id,
            "policy_sha256": self.policy_hash,
        }
        if self._handoff_digest:
            record["handoff_sha256"] = self._handoff_digest
        record.update(extra)
        payload = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        if required:
            # Publish required evidence atomically only after its contents have
            # reached fsync. Failed required writes never publish evidence;
            # subsequent observational JSONL failures cannot erase it.
            temporary = None
            try:
                self.audit_dir.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="",
                                                 dir=self.audit_dir, prefix=".receipt-", delete=False) as f:
                    temporary = Path(f.name)
                    f.write(payload)
                    f.flush()
                    os.fsync(f.fileno())
                destination = self.audit_dir / f"receipt-{self.dispatch_id}.json"
                os.replace(temporary, destination)
                self._required_path = destination
            except (OSError, TypeError, ValueError) as exc:
                if temporary is not None:
                    try:
                        temporary.unlink(missing_ok=True)
                    except OSError:
                        pass
                raise ReceiptError("required policy receipt could not be recorded") from exc
        try:
            self.audit_dir.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="") as f:
                f.write(payload)
            return True
        except (OSError, TypeError, ValueError):
            return required


def _required_records(audit_dir: Path) -> list[dict]:
    """Read only atomically published policy evidence, never uncommitted JSONL."""
    try:
        paths = list(audit_dir.iterdir())
        records = [json.loads(path.read_text(encoding="utf-8"))
                   for path in paths if path.name.startswith("receipt-") and path.suffix == ".json"]
    except FileNotFoundError:
        if not audit_dir.exists():
            return []
        raise ReceiptError("required policy history disappeared while being read")
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReceiptError("required policy history is unreadable or malformed") from exc
    if any(not isinstance(record, dict) or not isinstance(record.get("timestamp"), str)
           for record in records):
        raise ReceiptError("required policy history contains a non-object record")
    return records


def content_hash(value: str) -> str:
    """Public alias of the internal digest helper — for a caller (e.g.
    controller.py's challenge dispatch) that needs to hash a challenge
    result's text the same way this module hashes a handoff, without
    duplicating hashing logic."""
    return _digest(value)


def find_challenge_evidence(
    audit_dir: Path, handoff_hash: str, *, repo: Path | None = None,
    task_id: str = "", policy_hash: str = "",
) -> bool:
    """Require exact repo/task/draft/policy challenge evidence, never human approval.

    Missing bindings and legacy unbound receipts cannot satisfy a HIGH gate.
    """
    if repo is None or not task_id or not policy_hash:
        return False
    try:
        records = _required_records(audit_dir)
    except ReceiptError:
        return False
    for record in records:
        if (
            record.get("event") == "challenge_dispatch"
            and record.get("backend") == "real"
            and record.get("status") == "challenged"
            and record.get("handoff_sha256") == handoff_hash
            and record.get("schema") == _SCHEMA
            and record.get("repo_sha256") == repo_identity(repo)
            and record.get("task_id") == task_id
            and record.get("policy_sha256") == policy_hash
            and bool(record.get("challenge_result_hash"))
            and bool(record.get("dispatch_id"))
        ):
            return True
    return False


def count_consecutive_challenge_rounds(
    audit_dir: Path, handoff_name: str, *, repo: Path | None = None,
    task_id: str = "", policy_hash: str = "",
) -> int:
    """Count this repo/task's rounds until its successful build, across revisions.

    A changed draft or policy does not reset the cap; unrelated builds and
    blocked attempts cannot reset it either. A fresh log means zero rounds;
    unreadable or malformed history fails closed.
    """
    if repo is None or not task_id or not policy_hash:
        raise ReceiptError("challenge cap requires repo, task, and policy binding")
    path = audit_dir / _AUDIT_FILENAME
    required_records = _required_records(audit_dir)
    try:
        lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    except (OSError, UnicodeError) as exc:
        raise ReceiptError("challenge history is unreadable") from exc
    def identity(record):
        values = (record.get("dispatch_id"), record.get("status"))
        if any(not isinstance(value, str) or not value for value in values):
            raise ReceiptError("challenge history has invalid dispatch/status fields")
        return values

    committed = {identity(record): record for record in required_records}
    represented = set()
    records = []
    for append_index, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ReceiptError("challenge history is malformed") from exc
        if not isinstance(record, dict) or not isinstance(record.get("timestamp"), str):
            raise ReceiptError("challenge history contains a non-object record")
        key = identity(record)
        matches_committed = committed.get(key) == record
        # The append order breaks equal-clock ties only for exact committed
        # challenges. JSONL alone can never manufacture challenge evidence.
        if record.get("event") == "challenge_dispatch" and not matches_committed:
            continue
        records.append((record, 0, append_index))
        if matches_committed:
            represented.add(key)
    for index, record in enumerate(required_records):
        if identity(record) not in represented:
            # A missing observational append must not undercount evidence at a
            # same-timestamp successful build boundary: conservatively count it.
            records.append((record, 1, index))
    target_hash = _digest(handoff_name)
    count = 0
    seen = set()
    for record, _, _ in sorted(
        records, key=lambda item: (item[0]["timestamp"], item[1], item[2]), reverse=True,
    ):
        if record.get("backend") != "real":
            continue
        if record.get("status") == "attempted":
            continue
        if record.get("handoff_name_sha256") != target_hash:
            continue
        if record.get("repo_sha256") != repo_identity(repo) or record.get("task_id") != task_id:
            continue
        key = identity(record)
        if key in seen:
            continue
        seen.add(key)
        if record.get("event") == "builder_dispatch" and record.get("status") == "built":
            break
        if record.get("event") == "challenge_dispatch" and record.get("status") == "challenged":
            count += 1
    return count
