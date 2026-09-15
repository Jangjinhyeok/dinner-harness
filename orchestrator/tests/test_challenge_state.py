"""Offline regression: real temporary Git repos, mocked model transport only.

Synthetic receipts stay in temporary audit dirs and never authorize live work.
"""
import json
import os
import stat
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from types import SimpleNamespace
from unittest import mock

from adapters import codex
from orchestrator import receipt
from orchestrator.bus import Bus
from orchestrator.config import Config
from orchestrator.controller import Orchestrator, AutoApprove, CHALLENGED, BLOCKED
from orchestrator.vendors import Backend, Turn


class ChallengeStateTests(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
        })
        env.start()
        self.addCleanup(env.stop)
        temporary = tempfile.TemporaryDirectory(prefix="challenge-state-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.audit = self.root / "audit"
        self.git("init", "-q")
        self.write("source.txt", "original")
        self.write(".gitignore", "cache/\nHANDOFF.md\n")
        self.commit()
        self.write("HANDOFF.md", "# draft\n```scope\nsource.txt\n```\n")
        self.binding = dict(repo=self.repo, task_id="fixture-task", policy_hash="fixture-policy")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=fixture",
                               "-c", "user.email=fixture@example.invalid", *args],
                              check=True, capture_output=True).stdout

    def write(self, name, content):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-qm", "fixture")

    def record(self, *, legacy=False):
        audit = receipt.BuildAudit(self.audit, self.repo, "HANDOFF.md", "codex", "real",
                                   event="challenge_dispatch", task_id="fixture-task",
                                   policy_hash="fixture-policy")
        audit.set_handoff("draft")
        extra = {} if legacy else {"code_state": receipt.code_state(self.repo)}
        audit.terminal(status="challenged", outcome=CHALLENGED, reason_code="offline-fixture",
                       attempts=1, required=True, challenge_result_hash=receipt.content_hash("critique"),
                       **extra)
        return audit

    def evidence(self):
        return receipt.find_challenge_evidence(self.audit, receipt.content_hash("draft"), **self.binding)

    def test_unchanged_state_is_deterministic_and_content_free(self):
        audit = self.record()
        self.assertTrue(self.evidence())
        self.assertEqual(receipt.code_state(self.repo), receipt.code_state(self.repo))
        data = json.loads(audit.terminal_path.read_text(encoding="utf-8"))
        self.assertEqual(set(data["code_state"]), {"schema", "sha256"})
        self.assertNotIn("original", json.dumps(data))

    def test_unstaged_change_invalidates(self):
        self.record()
        self.write("source.txt", "edited")
        self.assertFalse(self.evidence())

    def test_index_change_invalidates_even_with_original_worktree_bytes(self):
        self.record()
        self.write("source.txt", "staged")
        self.git("add", "source.txt")
        self.write("source.txt", "original")
        self.assertFalse(self.evidence())

    def test_committed_change_invalidates_even_with_original_worktree_bytes(self):
        self.record()
        original = self.git("rev-parse", "HEAD").decode().strip()
        self.write("source.txt", "committed")
        self.commit()
        # Isolate the committed layer: restore the original index and worktree.
        self.git("read-tree", original)
        self.write("source.txt", "original")
        self.assertFalse(self.evidence())

    def test_untracked_add_edit_delete_and_rename(self):
        self.record()
        self.write("new.txt", "one")
        self.assertFalse(self.evidence())
        self.record()
        self.write("new.txt", "two")
        self.assertFalse(self.evidence())
        self.record()
        (self.repo / "new.txt").rename(self.repo / "renamed.txt")
        self.assertFalse(self.evidence())
        # Keep this deletion case distinct from the original reusable state.
        self.write("source.txt", "new deletion baseline")
        self.record()
        (self.repo / "renamed.txt").unlink()
        self.assertFalse(self.evidence())

    def test_tracked_delete_and_staged_rename(self):
        self.record()
        (self.repo / "source.txt").unlink()
        self.assertFalse(self.evidence())
        self.git("restore", "source.txt")
        self.git("mv", "source.txt", "renamed.txt")
        self.assertFalse(self.evidence())

    def test_reports_and_external_execution_records_do_not_invalidate(self):
        self.record()
        self.write("RESULT.md", "report")
        self.write("CHALLENGE.md", "critique")
        (self.audit / "watch-builder-fixture.json").write_text("{}")
        self.assertTrue(self.evidence())
        self.git("add", "RESULT.md", "CHALLENGE.md")
        self.assertTrue(self.evidence())
        self.git("commit", "-qm", "reports only")
        self.assertTrue(self.evidence())
        self.write("docs/RESULT.md", "not a controller report")
        self.assertFalse(self.evidence())

    def test_scope_is_whole_git_visible_repo_and_ignored_files_are_outside(self):
        self.record()
        self.write("cache/local.bin", "ignored")
        self.assertTrue(self.evidence())
        self.write("read-dependency.txt", "outside HANDOFF write scope")
        self.assertFalse(self.evidence())

    def test_legacy_and_snapshot_failure_fail_closed(self):
        self.record(legacy=True)
        self.assertFalse(self.evidence())
        self.record()
        with mock.patch.object(Path, "open", side_effect=PermissionError("unreadable")):
            self.assertFalse(self.evidence())
        with mock.patch("orchestrator.receipt.subprocess.run", side_effect=subprocess.TimeoutExpired("git", 30)):
            self.assertFalse(self.evidence())

    def test_change_during_snapshot_fails_closed(self):
        original_open = Path.open
        reads = 0
        def changing_open(path, *args, **kwargs):
            nonlocal reads
            if path == (self.repo / "source.txt").resolve() and args == ("rb",):
                reads += 1
                if reads == 2:
                    with original_open(path, "w", encoding="utf-8") as stream:
                        stream.write("changed between snapshot passes")
            return original_open(path, *args, **kwargs)
        with mock.patch.object(Path, "open", changing_open):
            with self.assertRaisesRegex(receipt.ReceiptError, "changed during snapshot"):
                receipt.code_state(self.repo)

    def test_submodule_is_opaque_and_rejected(self):
        oid = self.git("rev-parse", "HEAD").decode().strip()
        self.git("update-index", "--add", "--cacheinfo", "160000," + oid + ",nested")
        with self.assertRaises(receipt.ReceiptError):
            receipt.code_state(self.repo)

    def test_parent_reparse_point_is_rejected_without_path_is_junction(self):
        self.write("nested/dependency.txt", "must not follow a junction")
        junction = (self.repo / "nested").resolve()
        original_lstat = Path.lstat
        def reparse_lstat(path, *args, **kwargs):
            info = original_lstat(path, *args, **kwargs)
            if path == junction:
                return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
            return info
        # Simulate the Python 3.11 API surface even on a newer interpreter.
        with mock.patch.object(Path, "is_junction", None, create=True), mock.patch.object(
                stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400, create=True), mock.patch.object(
                Path, "lstat", reparse_lstat):
            with self.assertRaisesRegex(receipt.ReceiptError, "filesystem link"):
                receipt.code_state(self.repo)

    def test_unborn_or_non_git_repo_fails_closed(self):
        other = self.root / "other"
        other.mkdir()
        with self.assertRaises(receipt.ReceiptError):
            receipt.code_state(other)
        subprocess.run(["git", "-C", str(other), "init", "-q"], check=True)
        with self.assertRaises(receipt.ReceiptError):
            receipt.code_state(other)

    def controller(self, backend):
        cfg = Config(repo=self.repo, audit_dir=self.audit, backend="real")
        return Orchestrator(cfg, backend, backend, AutoApprove(), log=lambda _: None)

    def test_controller_challenge_then_high_gate_rechecks_state(self):
        backend = mock.Mock(spec=Backend)
        backend.invoke.return_value = Turn(text="offline critique")
        with mock.patch("orchestrator.controller.make_backend", return_value=backend):
            self.assertEqual(self.controller(backend).run_challenge().status, CHALLENGED)
            draft = (self.repo / "HANDOFF.md").read_text(encoding="utf-8")
            self.assertIsNone(self.controller(backend)._resolve_builder_profile(draft, {"1": "HIGH"}, {}))
            self.write("source.txt", "changed after critique")
            blocked = self.controller(backend)._resolve_builder_profile(draft, {"1": "HIGH"}, {})
            self.assertEqual(blocked.status, BLOCKED)
        backend.invoke.assert_called_once()

    def test_preflight_change_blocks_builder_before_invoke(self):
        backend = mock.Mock(spec=Backend)
        backend.invoke.return_value = Turn(text="offline critique")
        with mock.patch("orchestrator.controller.make_backend", return_value=backend):
            self.assertEqual(self.controller(backend).run_challenge().status, CHALLENGED)
            builder = self.controller(backend)
            draft = (self.repo / "HANDOFF.md").read_text(encoding="utf-8")
            self.assertIsNone(builder._resolve_builder_profile(draft, {"1": "HIGH"}, {}))
            def preflight(*args):
                self.write("source.txt", "changed during preflight")
                return None, None
            with mock.patch.object(builder, "_pre_turn_checks", side_effect=preflight):
                outcome = builder._build_and_gate(Bus(self.repo), draft, {"1": "HIGH"}, 1,
                                                  handoff_name="HANDOFF.md")
            self.assertEqual(outcome[3].status, BLOCKED)
            self.assertIn("stale before Builder", outcome[3].reason)
        backend.invoke.assert_called_once()

    def test_snapshot_failure_before_challenge_never_invokes_model(self):
        backend = mock.Mock(spec=Backend)
        with mock.patch("orchestrator.controller.make_backend", return_value=backend), mock.patch(
                "orchestrator.controller.code_state", side_effect=receipt.ReceiptError("snapshot unavailable")):
            self.assertEqual(self.controller(backend).run_challenge().status, BLOCKED)
        backend.invoke.assert_not_called()
        self.assertEqual(list(self.audit.glob("receipt-*.json")), [])

    def test_change_during_challenge_blocks_receipt_including_ignored_handoff(self):
        for name in ("source.txt", "HANDOFF.md"):
            with self.subTest(name=name):
                backend = mock.Mock(spec=Backend)
                def invoke(*args):
                    self.write(name, "changed during challenge " + name)
                    return Turn(text="stale critique")
                backend.invoke.side_effect = invoke
                with mock.patch("orchestrator.controller.make_backend", return_value=backend):
                    result = self.controller(backend).run_challenge()
                self.assertEqual(result.status, BLOCKED)
                self.assertIn("changed during challenge", result.reason)
                self.assertEqual(list(self.audit.glob("receipt-*.json")), [])

    def test_adapter_generated_install_executes_same_snapshot_contract(self):
        source = Path(__file__).resolve().parents[2]
        manifest = tomllib.loads((source / "harness.toml").read_text(encoding="utf-8"))
        installed = self.root / "installed"
        codex.install(source, manifest["targets"]["codex"], manifest.get("vars", {}), installed, "", False)
        self.assertEqual((installed / "orchestrator/receipt.py").read_bytes(),
                         (source / "orchestrator/receipt.py").read_bytes())
        script = '''
import sys
from pathlib import Path
from unittest import mock
from orchestrator.controller import Orchestrator, AutoApprove, CHALLENGED, BLOCKED
from orchestrator.config import Config
from orchestrator.vendors import Backend, Turn
from orchestrator.receipt import code_state
repo, audit = map(Path, sys.argv[1:])
cfg = Config(repo=repo, audit_dir=audit, backend="real")
backend = mock.Mock(spec=Backend)
backend.invoke.return_value = Turn(text="offline installed critique")
def controller():
    return Orchestrator(cfg, backend, backend, AutoApprove(), log=lambda _: None)
with mock.patch("orchestrator.controller.make_backend", return_value=backend):
    outcome = controller().run_challenge()
    assert outcome.status == CHALLENGED, outcome.reason
    draft = (repo / "HANDOFF.md").read_text(encoding="utf-8")
    assert controller()._resolve_builder_profile(draft, {"1": "HIGH"}, {}) is None
    (repo / "source.txt").write_text("installed fixture edit", encoding="utf-8")
    assert controller()._resolve_builder_profile(draft, {"1": "HIGH"}, {}).status == BLOCKED
backend.invoke.assert_called_once()
print("PASS: generated install, real Git snapshot, mocked transport")
'''
        result = subprocess.run([sys.executable, "-c", script, str(self.repo), str(self.audit)],
                                cwd=installed, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS: generated install", result.stdout)


if __name__ == "__main__":
    unittest.main()
