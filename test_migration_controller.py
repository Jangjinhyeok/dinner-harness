"""Regression tests for dispatch boundaries and honest result accounting."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from orchestrator import bus, routing, safety
from orchestrator.config import Config
from orchestrator.controller import Orchestrator, AutoApprove, BLOCKED, BUILT
from orchestrator.receipt import BuildAudit
from orchestrator.vendors import Turn


def handoff(lines):
    return "```tiers\n" + lines + "\n```\n```scope\nx.py\n```\n"


class TestDispatchContract(unittest.TestCase):
    def test_numeric_prefix_stops_after_high(self):
        tiers, compute = bus.dispatch_gates(handoff(
            "gate 10: LOW\ngate 2: risk=HIGH compute=LOW\ngate 1: risk=LOW compute=LOW"))
        self.assertEqual(list(tiers), ["1", "2"])
        self.assertEqual(bus.effective_compute(tiers, compute, "2"), "HIGH")

    def test_duplicate_or_malformed_declarations_refused(self):
        for lines in ("gate 1: LOW\n1: HIGH", "gate 01: LOW", "gate 1: risk=LOW risk=HIGH",
                      "gate 1: risk=LOW ignored", "nonsense"):
            with self.subTest(lines=lines), self.assertRaises(bus.ContractError):
                bus.dispatch_gates(handoff(lines))

    def test_ambiguous_risk_remains_high(self):
        tiers, _ = bus.dispatch_gates(handoff("gate 1: risk=unknown compute=LOW"))
        self.assertEqual(tiers, {"1": "HIGH"})

    def test_json_and_legacy_never_certify_independent_review(self):
        text = json.dumps({"schema_version": 1, "summary": "Already satisfied", "gates": [
            {"gate": "1", "status": "completed", "tier": "LOW",
             "self_review": "pass", "verification_claim": "not_run"}]})
        verdicts = bus.parse_build_result(text)
        bus.validate_results(verdicts, {"1": "LOW"})
        self.assertEqual(verdicts[0].panel, "")
        self.assertIn("Independent implementation review: not_run", bus.render_result(text, verdicts, net_status="pass"))
        with self.assertRaises(bus.ContractError):
            bus.parse_build_result("```verdicts\ngate 1: status=completed tier=LOW panel=PASS\n```")

    def test_missing_duplicate_undeclared_and_invalid_status_refused(self):
        for verdicts in ([], [bus.GateVerdict("1", "completed"), bus.GateVerdict("1", "completed")],
                         [bus.GateVerdict("2", "completed")], [bus.GateVerdict("1", "success")]):
            with self.subTest(verdicts=verdicts), self.assertRaises(bus.ContractError):
                bus.validate_results(verdicts, {"1": "LOW"})

    def test_mixed_risk_requires_challenge_before_any_builder(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = Config(repo=Path(directory), audit_dir=Path(directory) / "audit", backend="real", builder_vendor="")
            runner = Orchestrator(cfg, object(), object(), AutoApprove(), log=lambda _: None)
            with mock.patch("orchestrator.controller.make_backend") as factory:
                outcome = runner._resolve_builder_profile("draft", {"1": "LOW", "2": "HIGH"}, {"1": "LOW"})
            self.assertEqual(outcome.status, BLOCKED)
            self.assertIn("challenger_high evidence", outcome.reason)
            factory.assert_not_called()

    def test_blocked_is_not_completed_or_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "HANDOFF.md").write_text(handoff("gate 1: LOW\ngate 2: LOW"), encoding="utf-8")
            runner = Orchestrator(Config(repo=root), object(), object(), AutoApprove(), log=lambda _: None)
            runner._last_contract_error = ""
            audit = BuildAudit(root / "audit", root, "HANDOFF.md", "codex", "mock")
            verdicts = [bus.GateVerdict("1", "completed", "LOW"), bus.GateVerdict("2", "blocked", "LOW")]
            with mock.patch.object(runner, "_build_and_gate", return_value=(Turn(), verdicts, False, None, True)) as build:
                outcome = runner._run_from_handoff(audit)
            self.assertEqual(outcome.status, BLOCKED)
            self.assertEqual(outcome.completed_gates, ["1"])
            self.assertEqual(outcome.blocked_gates, ["2"])
            build.assert_called_once()

    def test_error_turn_still_runs_delta_and_net(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backend = mock.Mock()
            backend.invoke.return_value = Turn(text='{"summary": null}', error="timeout")
            runner = Orchestrator(Config(repo=root), backend, backend, AutoApprove(), log=lambda _: None)
            with mock.patch.object(runner, "_pre_turn_checks", return_value=(object(), None)), \
                 mock.patch.object(runner, "_builder_changes", return_value=([safety.Change("x.py", "partial")], None)) as delta, \
                 mock.patch("orchestrator.controller.safety.scan", return_value=safety.NetResult()) as scan:
                _, _, _, outcome, observed = runner._build_and_gate(
                    bus.Bus(root), handoff("gate 1: LOW"), {"1": "LOW"}, 1,
                    handoff_name="HANDOFF.md", tier_gate_hard=False)
            delta.assert_called_once()
            scan.assert_called_once()
            self.assertTrue(observed)
            self.assertEqual(outcome.status, BLOCKED)
            self.assertIn("partial edits=True", outcome.reason)

    def test_noop_completes_and_format_recovery_is_read_only(self):
        good = json.dumps({"schema_version": 1, "summary": "Already satisfied", "gates": [
            {"gate": "1", "status": "completed", "tier": "LOW",
             "self_review": "pass", "verification_claim": "pass"}]})
        for recover in (False, True):
            with self.subTest(recover=recover), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "HANDOFF.md").write_text(handoff("gate 1: LOW"), encoding="utf-8")
                backend = mock.Mock()
                backend.invoke.side_effect = ([Turn(text="report without contract"), Turn(text=good)]
                                              if recover else [Turn(text=good)])
                runner = Orchestrator(Config(repo=root, audit_dir=root / "audit"), backend, backend,
                                      AutoApprove(), log=lambda _: None)
                with mock.patch.object(runner, "_pre_turn_checks", return_value=(object(), None)), \
                     mock.patch.object(runner, "_builder_changes", return_value=([], None)), \
                     mock.patch("orchestrator.controller.safety.scan", return_value=safety.NetResult()):
                    outcome = runner.run_from_handoff()
                self.assertEqual(outcome.status, BUILT)
                self.assertEqual(outcome.completed_gates, ["1"])
                self.assertEqual(backend.invoke.call_count, 2 if recover else 1)
                if recover:
                    self.assertEqual(backend.invoke.call_args.args[0], "recovery")
                    self.assertIn("report without contract", (root / "RESULT.md").read_text(encoding="utf-8"))

    def test_unencodable_result_still_scans_partial_edits(self):
        text = json.dumps({"schema_version": 1, "summary": chr(0xd800), "gates": [
            {"gate": "1", "status": "completed", "tier": "LOW",
             "self_review": "pass", "verification_claim": "pass"}]})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backend = mock.Mock()
            backend.invoke.return_value = Turn(text=text, error="timeout")
            runner = Orchestrator(Config(repo=root), backend, backend, AutoApprove(), log=lambda _: None)
            with mock.patch.object(runner, "_pre_turn_checks", return_value=(object(), None)), \
                 mock.patch.object(runner, "_builder_changes", return_value=([safety.Change("x.py", "partial")], None)), \
                 mock.patch("orchestrator.controller.safety.scan", return_value=safety.NetResult()) as scan:
                _, _, _, outcome, observed = runner._build_and_gate(
                    bus.Bus(root), handoff("gate 1: LOW"), {"1": "LOW"}, 1,
                    handoff_name="HANDOFF.md", tier_gate_hard=False)
            scan.assert_called_once()
            self.assertTrue(observed)
            self.assertEqual(outcome.status, BLOCKED)
            self.assertIn("delta checks completed", outcome.reason)

    def test_mock_challenge_never_constructs_real_backend(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "HANDOFF.md").write_text("draft", encoding="utf-8")
            backend = mock.Mock()
            backend.invoke.return_value = Turn(text="independent fake critique")
            runner = Orchestrator(Config(repo=root, audit_dir=root / "audit"), backend, backend,
                                  AutoApprove(), log=lambda _: None)
            with mock.patch("orchestrator.controller.make_backend") as factory:
                runner.run_challenge()
            factory.assert_not_called()

    def test_legacy_real_high_does_not_invoke_builder(self):
        for declarations in ("gate 1: HIGH", "gate 1: HIGH\ngate 1: LOW"):
            with self.subTest(declarations=declarations), tempfile.TemporaryDirectory() as directory:
                backend = mock.Mock()
                runner = Orchestrator(Config(repo=Path(directory), backend="real"), backend, backend,
                                      AutoApprove(), log=lambda _: None)
                with mock.patch.object(runner, "_architect_turn", return_value=(Turn(text=handoff(declarations)), None)):
                    outcome = runner.run()
                self.assertEqual(outcome.status, BLOCKED)
                backend.invoke.assert_not_called()


if __name__ == "__main__":
    unittest.main()
