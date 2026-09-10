"""Offline regressions for effective HIGH boundaries and local skill discovery."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import check
from orchestrator import bus, controller
from orchestrator.vendors import Backend, Turn, ROLE_BUILDER
from orchestrator.tests.test_orchestrator import (
    _cfg, _git_init, setUpModule, tearDownModule,
)


class TestEffectiveHighBoundary(unittest.TestCase):
    def run_build(self, declared, results, *, structured=False, corrupt=None):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        repo = root / "work"
        repo.mkdir()
        _git_init(repo)
        handoff = "```tiers\n" + "".join(f"gate {g}: {t}\n" for g, t in declared.items())
        handoff += "```\n```scope\nallowed.py\nRESULT.md\n```\n"
        (repo / bus.HANDOFF).write_text(handoff, encoding="utf-8")
        if structured:
            text = json.dumps({"schema_version": 1, "summary": "original evidence", "gates": [
                dict(gate=g, status=s, tier=t, self_review="pass", verification_claim="not_run")
                for g, s, t in results]})
        else:
            text = "original evidence\n```verdicts\n" + "".join(
                f"gate {g}: status={s} tier={t} panel=PASS\n" for g, s, t in results) + "```\n"
        if corrupt:
            text = corrupt(text)

        class Builder(Backend):
            name = "boundary-test"
            def __init__(self):
                self.roles = []
            def invoke(self, role, prompt, cfg):
                self.roles.append(role)
                if len(self.roles) > 1:
                    raise AssertionError("execution violations must never invoke recovery")
                (repo / "allowed.py").write_text("observed = True\n", encoding="utf-8")
                return Turn(text=text)

        backend = Builder()
        cfg = _cfg(repo, audit_dir=root / "audit", backend="real" if structured else "mock",
                   builder_vendor="codex")
        runner = controller.Orchestrator(cfg, backend, backend, controller.AutoApprove(), log=lambda _: None)
        with mock.patch.object(runner, "_resolve_builder_profile", return_value=None):
            outcome = runner.run_from_handoff()
        record = json.loads(outcome.receipt_path.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(backend.roles, [ROLE_BUILDER])
        self.assertEqual((repo / "allowed.py").read_text(), "observed = True\n")
        return outcome, record, (repo / bus.RESULT).read_text(encoding="utf-8"), text

    def test_promoted_high_crossing_blocks_without_recovery_and_preserves_evidence(self):
        for structured in (False, True):
            with self.subTest(structured=structured):
                out, receipt, report, original = self.run_build(
                    {"1": "LOW", "2": "LOW"},
                    [("1", "completed", "HIGH"), ("2", "completed", "LOW")], structured=structured)
                self.assertEqual(out.status, controller.BLOCKED)
                self.assertTrue(out.contract_violation)
                self.assertEqual(out.completed_gates, ["1"])
                self.assertEqual(out.remaining_gates, ["2"])
                self.assertEqual(out.reported_completed_gates, ["1", "2"])
                self.assertTrue(out.implementation_observed)
                self.assertIn(original, report)
                self.assertIn("Contract violation", report)
                self.assertEqual(receipt["status"], "blocked")
                self.assertNotIn(receipt["reason_code"], ("built_high", "built_low"))
                self.assertEqual(receipt["attempts"], 1)
                self.assertEqual(receipt["reported_completed_gates"], ["1", "2"])

    def test_promoted_high_then_pending_is_normal_review_stop(self):
        for structured in (False, True):
            with self.subTest(structured=structured):
                out, receipt, _, _ = self.run_build(
                    {"1": "LOW", "2": "LOW"},
                    [("1", "completed", "HIGH"), ("2", "pending", "LOW")], structured=structured)
                self.assertEqual(out.status, controller.BUILT, out.reason)
                self.assertFalse(out.contract_violation)
                self.assertEqual(out.completed_gates, ["1"])
                self.assertEqual(out.pending_gates, ["2"])
                self.assertEqual(out.needs_review_gates, ["1"])
                self.assertEqual(out.independent_review, "not_run")
                self.assertEqual(receipt["reason_code"], "built_high")

    def test_schema_errors_cannot_hide_reported_execution_violation(self):
        def extra_field(text):
            data = json.loads(text)
            data["extra"] = True
            data["gates"][0]["unexpected"] = "field"
            return json.dumps(data)
        def invalid_extra_gate(text):
            data = json.loads(text)
            data["gates"].append({"gate": "bad", "status": "completed", "tier": "LOW"})
            return json.dumps(data)
        for structured, corrupt in ((True, extra_field), (True, invalid_extra_gate),
                                    (False, lambda text: "```verdicts\ngate 1: status=pending tier=LOW\n```\n" + text)):
            with self.subTest(structured=structured, corrupt=corrupt):
                out, record, report, original = self.run_build(
                    {"1": "LOW", "2": "LOW"},
                    [("1", "completed", "HIGH"), ("2", "completed", "LOW")],
                    structured=structured, corrupt=corrupt)
                self.assertEqual(out.status, controller.BLOCKED)
                self.assertTrue(out.contract_violation)
                self.assertEqual(record["status"], "blocked")
                self.assertEqual(out.cycles, 1)
                self.assertIn(original, report)

    def test_receipt_uses_effective_risk_not_prose_or_review_list(self):
        cases = [
            ({"1": "LOW", "2": "LOW"}, [("1", "completed", "LOW"), ("2", "completed", "LOW")], "built_low"),
            ({"1": "HIGH", "2": "LOW"}, [("1", "completed", "LOW")], "built_high"),
            ({"1": "LOW"}, [("1", "completed", "HIGH")], "built_high"),
            ({"1": "LOW"}, [("1", "needs_review", "LOW")], "built_low"),
        ]
        for declared, results, expected in cases:
            with self.subTest(declared=declared, results=results):
                out, receipt, _, _ = self.run_build(declared, results)
                self.assertEqual(out.status, controller.BUILT, out.reason)
                self.assertEqual(receipt["reason_code"], expected)
                for reason in ("arbitrary new prose", "HIGH gate present", ""):
                    out.reason = reason
                    self.assertEqual(controller._receipt_reason_code(out), expected)

    def test_numeric_boundary_wins_over_missing_or_extra_verdict_shape(self):
        for selected, verdicts in [
            ({"2": "LOW", "10": "LOW"}, [bus.GateVerdict("10", "completed", "LOW"), bus.GateVerdict("2", "completed", "HIGH")]),
            ({"1": "HIGH"}, [bus.GateVerdict("1", "completed", "LOW"), bus.GateVerdict("2", "completed", "LOW")]),
            ({"1": "HIGH", "2": "LOW"}, [bus.GateVerdict("2", "completed", "LOW")]),
        ]:
            with self.subTest(selected=selected):
                with self.assertRaises(bus.GateBoundaryError):
                    bus.validate_results(verdicts, selected)


class TestSkillDiscovery(unittest.TestCase):
    def test_skill_resources_are_not_recursive_discovery_roots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "skill/resources/other/SKILL.md"
            nested.parent.mkdir(parents=True)
            nested.write_bytes(b"\xffinvalid-resource")
            (root / "skill/SKILL.md").write_text("---\nname: outer\n---\n", encoding="utf-8")
            duplicates, errors = check.check_skill_duplicates([root])
            self.assertEqual((duplicates, errors), ({}, []))

    def test_names_content_and_alias_roots_are_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [root / "codex/a/SKILL.md", root / "agents/b/SKILL.md", root / "agents/c/SKILL.md"]
            for path, text in zip(paths, ["---\nname: 'same'\n---\nold", '---\nname: "same"\n---\nnew', "---\nname: user\n---\ncustom"]):
                path.parent.mkdir(parents=True)
                path.write_text(text, encoding="utf-8")
            before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths}
            duplicates, errors = check.check_skill_duplicates([root / "codex", root / "agents", root / "codex"])
            self.assertEqual(errors, [])
            self.assertEqual(list(duplicates), ["same"])
            self.assertEqual(len(duplicates["same"]), 2)
            self.assertEqual(len({p["sha256"] for p in duplicates["same"]}), 2)
            self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths})

    def test_same_bytes_are_still_duplicates_and_invalid_metadata_is_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("one", "two", "invalid"):
                path = root / name / "SKILL.md"
                path.parent.mkdir()
                path.write_bytes(b"no metadata" if name == "invalid" else b"---\nname: same\n---\n")
            duplicates, errors = check.check_skill_duplicates([root])
            self.assertEqual(len(duplicates["same"]), 2)
            self.assertEqual(len(errors), 1)

    def test_custom_home_and_repository_ancestors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            repo = root / "repo"
            repo.mkdir()
            _git_init(repo)
            cwd = repo / "src"
            cwd.mkdir()
            roots = check.skill_discovery_roots(cwd=cwd, home=root / "user", codex_home=root / "custom")
            self.assertIn(root / "custom/skills", roots)
            self.assertIn(root / "user/.agents/skills", roots)
            self.assertIn(cwd / ".agents/skills", roots)
            self.assertIn(repo / ".agents/skills", roots)
            self.assertNotIn(root / ".agents/skills", roots)


if __name__ == "__main__":
    unittest.main()
