"""Offline policy and bound-receipt regression contracts."""
import copy
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator import routing
from orchestrator.config import Config
import orchestrate
from orchestrator.receipt import (
    BuildAudit, ReceiptError, content_hash, count_consecutive_challenge_rounds,
    find_challenge_evidence, task_identity,
)


class RoutingMigrationTests(unittest.TestCase):
    def setUp(self):
        self.config = routing.load_routing_config(routing.default_routing_path())
        self.preset = routing.active_preset_name(self.config)

    def test_default_and_native_policy_resolve(self):
        self.assertEqual(self.preset, routing.DEFAULT_PRESET)
        self.assertEqual(Config().builder_vendor, "")
        for name, role in self.config["native_agents"].items():
            with self.subTest(agent=name):
                self.assertEqual(routing.resolve_profile(self.config, "codex_only", role).vendor, "codex")

    def test_profiles_reject_empty_invalid_fields_and_vendor_effort(self):
        for key, value in (("model", ""), ("model", " "), ("model", "bad name"),
                           ("effort", "nonsense"), ("effort", "max"),
                           ("vendor", "unknown"), ("model", None), ("modle", "typo")):
            with self.subTest(key=key, value=value):
                config = copy.deepcopy(self.config)
                config["presets"][self.preset]["builder_low"][key] = value
                with self.assertRaises(routing.RoutingConfigError):
                    routing.resolve_profile(config, self.preset, "builder_low")

    def test_codex_builder_cost_tiers_match_in_default_and_hybrid(self):
        # Policy acceptance contract; runtime selection still comes only from TOML.
        expected = {
            "builder_low": routing.ModelProfile("codex", "gpt-5.6-luna", "medium"),
            "builder_normal": routing.ModelProfile("codex", "gpt-5.6-terra", "medium"),
            "builder_high": routing.ModelProfile("codex", "gpt-6-astra", "high"),
        }
        self.assertEqual(self.preset, "codex_only")
        for preset in (self.preset, "hybrid"):
            for role, profile in expected.items():
                with self.subTest(preset=preset, role=role):
                    self.assertEqual(routing.resolve_profile(self.config, preset, role), profile)

    def test_codex_manual_efforts_and_vendor_mismatch_contract(self):
        for model in ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol", "gpt-6-astra"):
            for effort in ("low", "medium", "high", "xhigh"):
                with self.subTest(model=model, effort=effort):
                    profile = routing.ModelProfile("codex", model, effort)
                    self.assertEqual(routing.validate_profile(profile), profile)
        for profile in (routing.ModelProfile("codex", "gpt-6-astra", "max"),
                        routing.ModelProfile("codex", "gpt-6-astra", "extra-high"),
                        routing.ModelProfile("codex", "claude-opus-5", "high"),
                        routing.ModelProfile("claude", "gpt-6-astra", "high")):
            with self.subTest(profile=profile), self.assertRaises(routing.RoutingConfigError):
                routing.validate_profile(profile)

    def test_vendor_override_uses_explicit_active_mapping_for_every_tier(self):
        for role in ("builder_low", "builder_normal", "builder_high"):
            actual = routing.resolve_profile_for_vendor(self.config, self.preset, role, "claude")
            expected = routing.resolve_profile(self.config, "claude_only", role)
            self.assertEqual(actual, expected)

    def test_unrelated_preset_cannot_supply_override(self):
        self.config["presets"][self.preset].pop("vendor_fallbacks")
        with self.assertRaises(routing.RoutingConfigError):
            routing.resolve_builder_high_for_vendor(self.config, "claude")

    def test_ambiguous_explicit_fallback_is_rejected(self):
        self.config["presets"][self.preset]["vendor_fallbacks"]["claude"] = ["hybrid", "claude_only"]
        with self.assertRaises(routing.RoutingConfigError):
            routing.resolve_profile_for_vendor(self.config, self.preset, "builder_normal", "claude")

    def test_policy_digest_changes_with_relevant_profile(self):
        original = routing.policy_digest(self.config, self.preset)
        self.config["presets"][self.preset]["challenger_high"]["effort"] = "medium"
        self.assertNotEqual(original, routing.policy_digest(self.config, self.preset))

    def test_unknown_preset_and_legacy_run_routing_options_are_rejected(self):
        with self.assertRaises(routing.RoutingConfigError):
            routing.resolve_profile(self.config, "missing", "builder_low")
        for option in ("--routing-preset", "--builder-effort", "--architect-effort"):
            with self.subTest(option=option), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    orchestrate.main(["run", "--goal", "offline", option, "unsupported"])
                self.assertEqual(error.exception.code, 2)


class ReceiptMigrationTests(unittest.TestCase):
    def setUp(self):
        # Receipt serialization unit tests; real Git snapshots have a separate suite.
        snapshot = patch("orchestrator.receipt.code_state", return_value={"schema": "git-relevant-state.v1", "sha256": "fixture"})
        self.state = snapshot.start()
        self.addCleanup(snapshot.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.audit_dir = self.root / "audit"
        self.repo = self.root / "repo"
        self.task = task_identity(self.repo, "HANDOFF.md", "work-one")
        self.binding = dict(repo=self.repo, task_id=self.task, policy_hash="policy")

    def record(self, *, repo=None, task=None, event="challenge_dispatch", status="challenged", draft="draft", backend="real"):
        audit = BuildAudit(self.audit_dir, repo or self.repo, "HANDOFF.md", "codex", backend,
                           event=event, task_id=task or self.task, policy_hash="policy")
        audit.set_handoff(draft)
        audit.terminal(status=status, outcome=status.upper(), reason_code="test", attempts=1,
                       required=True, challenge_result_hash=content_hash("critique"), code_state=self.state())
        return audit

    def test_mock_challenge_cannot_authorize_real_dispatch(self):
        self.record(backend="mock")
        self.assertFalse(find_challenge_evidence(self.audit_dir, content_hash("draft"), **self.binding))

    def test_evidence_requires_repo_task_policy_and_exact_draft(self):
        self.record()
        digest = content_hash("draft")
        self.assertTrue(find_challenge_evidence(self.audit_dir, digest, **self.binding))
        self.assertFalse(find_challenge_evidence(self.audit_dir, digest))
        for field, value in (("repo", self.root / "other"), ("task_id", "other"), ("policy_hash", "other")):
            binding = {**self.binding, field: value}
            self.assertFalse(find_challenge_evidence(self.audit_dir, digest, **binding))
        self.assertFalse(find_challenge_evidence(self.audit_dir, content_hash("edited"), **self.binding))

    def test_cap_preserves_lineage_across_edits_and_unrelated_build(self):
        self.record(draft="first")
        self.record(draft="second")
        self.record(task="other-task", event="builder_dispatch", status="built")
        self.record(repo=self.root / "other", event="builder_dispatch", status="built")
        self.record(event="builder_dispatch", status="blocked")
        self.assertEqual(count_consecutive_challenge_rounds(self.audit_dir, "HANDOFF.md", **self.binding), 2)
        self.record(event="builder_dispatch", status="built")
        self.assertEqual(count_consecutive_challenge_rounds(self.audit_dir, "HANDOFF.md", **self.binding), 0)

    def test_required_write_failure_cannot_be_success_evidence(self):
        audit = BuildAudit(self.audit_dir, self.repo, "HANDOFF.md", "codex", "mock",
                           task_id=self.task, policy_hash="policy")
        audit.set_handoff("draft")
        with patch("orchestrator.receipt.os.fsync", side_effect=OSError("disk unavailable")):
            with self.assertRaises(ReceiptError):
                audit.terminal(status="challenged", outcome="CHALLENGED", reason_code="test", attempts=1,
                               required=True, challenge_result_hash=content_hash("critique"))
        self.assertIsNone(audit.terminal_path)
        self.assertFalse(find_challenge_evidence(self.audit_dir, content_hash("draft"), **self.binding))
        self.assertEqual(count_consecutive_challenge_rounds(self.audit_dir, "HANDOFF.md", **self.binding), 0)

    def test_observational_write_failure_does_not_lose_committed_evidence(self):
        with patch.object(Path, "open", side_effect=OSError("observational log unavailable")):
            audit = self.record()
        self.assertTrue(audit.terminal_path.is_file())
        self.assertTrue(find_challenge_evidence(self.audit_dir, content_hash("draft"), **self.binding))
        self.assertEqual(count_consecutive_challenge_rounds(self.audit_dir, "HANDOFF.md", **self.binding), 1)

    def test_missing_binding_and_unreadable_history_fail_closed(self):
        with self.assertRaises(ReceiptError):
            count_consecutive_challenge_rounds(self.audit_dir, "HANDOFF.md")
        audit = self.record()
        with patch.object(Path, "read_text", side_effect=OSError("unreadable")):
            self.assertFalse(find_challenge_evidence(self.audit_dir, content_hash("draft"), **self.binding))
            with self.assertRaises(ReceiptError):
                count_consecutive_challenge_rounds(self.audit_dir, "HANDOFF.md", **self.binding)
        self.assertTrue(audit.terminal_path)


if __name__ == "__main__":
    unittest.main()
