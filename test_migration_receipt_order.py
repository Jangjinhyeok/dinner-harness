"""Challenge cap ordering with equal timestamps and required receipt sidecars."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from orchestrator.receipt import BuildAudit, count_consecutive_challenge_rounds, task_identity


class ReceiptOrderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.audit_dir = self.root / "audit"
        self.binding = dict(repo=self.repo, task_id=task_identity(self.repo, "HANDOFF.md"),
                            policy_hash="policy")
        clock = mock.patch("orchestrator.receipt._now_iso_z", return_value="2026-09-10T01:00:00.000000Z")
        clock.start()
        self.addCleanup(clock.stop)

    def record(self, event="challenge_dispatch", *, required=True, backend="real"):
        audit = BuildAudit(self.audit_dir, self.repo, "HANDOFF.md", "codex", backend,
                           event=event, task_id=self.binding["task_id"], policy_hash="policy")
        audit.set_handoff("draft")
        status = "challenged" if event == "challenge_dispatch" else "built"
        audit.terminal(status=status, outcome=status.upper(), reason_code="test", attempts=1,
                       required=required, challenge_result_hash="critique-digest")
        return audit

    def count(self):
        return count_consecutive_challenge_rounds(self.audit_dir, "HANDOFF.md", **self.binding)

    def test_equal_timestamps_follow_committed_jsonl_append_order(self):
        self.record()
        self.record("builder_dispatch", required=False)
        self.record()
        self.assertEqual(self.count(), 1)

    def test_mock_records_neither_reset_nor_consume_real_cap(self):
        self.record()
        self.record("builder_dispatch", backend="mock", required=False)
        self.record(backend="mock")
        self.assertEqual(self.count(), 1)

    def test_required_builder_receipt_does_not_duplicate_or_reorder_boundary(self):
        self.record()
        self.record("builder_dispatch")
        self.record()
        self.assertEqual(self.count(), 1)

    def test_unlogged_required_challenge_counts_conservatively_at_equal_timestamp(self):
        self.record("builder_dispatch", required=False)
        with mock.patch.object(Path, "open", side_effect=OSError("observational log unavailable")):
            self.record()
        self.assertEqual(self.count(), 1)

    def test_uncommitted_challenge_jsonl_cannot_create_a_round(self):
        self.record(required=False)
        self.assertEqual(self.count(), 0)

    def test_altered_jsonl_copy_cannot_move_committed_evidence_after_build(self):
        audit = self.record()
        self.record("builder_dispatch", required=False)
        forged = json.loads(audit.terminal_path.read_text(encoding="utf-8"))
        forged["extra"] = "not-the-committed-record"
        with audit.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(forged) + "\n")
        self.assertEqual(self.count(), 0)


if __name__ == "__main__":
    unittest.main()
