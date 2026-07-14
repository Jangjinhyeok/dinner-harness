"""Orchestrator tests — stdlib unittest, fully offline (mock backend + the real
hook handlers as the safety net). Run from the repo root:

    py -3 -m unittest discover -s orchestrator/tests
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from orchestrator import bus
from orchestrator.config import Config
from orchestrator.controller import (
    AutoApprove,
    Orchestrator,
    compute_has_high,
    enforce_tier_gates,
    BUILT,
    DONE,
    BLOCKED,
    HELD,
)
from orchestrator import safety
from orchestrator.vendors import MockBackend, Scenario, default_low_scenario
from orchestrator.safety import Change


class TestBusParsing(unittest.TestCase):
    def test_tiers_fail_closed(self):
        h = "x\n```tiers\ngate 1: LOW\ngate 2: bogus\n```\n"
        t = bus.parse_tiers(h)
        self.assertEqual(t["1"], bus.TIER_LOW)
        self.assertEqual(t["2"], bus.TIER_HIGH)  # garbled -> HIGH
        self.assertEqual(bus.tier_for(t, "Gate 9"), bus.TIER_HIGH)  # missing -> HIGH

    def test_verdicts(self):
        r = "```verdicts\ngate 1: status=completed tier=HIGH panel=PASS\n```\n"
        v = bus.parse_verdicts(r)
        self.assertEqual(len(v), 1)
        self.assertEqual(v[0].tier, bus.TIER_HIGH)
        self.assertEqual(v[0].panel, bus.PANEL_PASS)

    def test_control_fail_closed(self):
        self.assertEqual(bus.parse_control("no fence").verdict, bus.VERDICT_BLOCKED)
        self.assertEqual(
            bus.parse_control("```control\nverdict: DONE\n```").verdict, bus.VERDICT_DONE
        )


class TestTierGate(unittest.TestCase):
    def test_high_without_pass_blocks(self):
        tiers = {"1": bus.TIER_HIGH}
        v = [bus.GateVerdict(gate="1", tier=bus.TIER_HIGH, panel=bus.PANEL_FAIL)]
        self.assertTrue(enforce_tier_gates(tiers, v))

    def test_high_missing_verdict_fail_closed(self):
        self.assertTrue(enforce_tier_gates({"1": bus.TIER_HIGH}, []))

    def test_block_panel_fails_any_tier(self):
        v = [bus.GateVerdict(gate="1", tier=bus.TIER_LOW, panel=bus.PANEL_BLOCK)]
        self.assertTrue(enforce_tier_gates({"1": bus.TIER_LOW}, v))

    def test_low_pass_ok(self):
        v = [bus.GateVerdict(gate="1", tier=bus.TIER_LOW, panel=bus.PANEL_PASS)]
        self.assertEqual(enforce_tier_gates({"1": bus.TIER_LOW}, v), [])

    def test_low_panel_fail_blocks(self):
        v = [bus.GateVerdict(gate="1", tier=bus.TIER_LOW, panel=bus.PANEL_FAIL)]
        self.assertTrue(enforce_tier_gates({"1": bus.TIER_LOW}, v))

    def test_missing_tiers_fence_enforces_high(self):
        # No ```tiers``` fence -> every gate HIGH (fail-closed): a non-PASS panel blocks...
        self.assertTrue(enforce_tier_gates({}, [bus.GateVerdict(gate="1", tier=bus.TIER_LOW, panel="")]))
        # ...but an explicit PASS satisfies the enforced-HIGH gate.
        self.assertEqual(
            enforce_tier_gates({}, [bus.GateVerdict(gate="1", tier=bus.TIER_LOW, panel=bus.PANEL_PASS)]), []
        )

    def test_no_gates_fail_closed(self):
        self.assertTrue(enforce_tier_gates({}, []))

    def test_builder_downgrade_still_enforced(self):
        # Architect declared HIGH; Builder self-reports LOW -> effective HIGH wins.
        v = [bus.GateVerdict(gate="1", tier=bus.TIER_LOW, panel="")]
        self.assertTrue(enforce_tier_gates({"1": bus.TIER_HIGH}, v))

    def test_compute_has_high(self):
        # missing tiers -> fail-closed HIGH
        self.assertTrue(compute_has_high({}, [bus.GateVerdict(gate="1", tier=bus.TIER_LOW, panel=bus.PANEL_PASS)]))
        self.assertTrue(compute_has_high({}, []))
        self.assertFalse(
            compute_has_high({"1": bus.TIER_LOW}, [bus.GateVerdict(gate="1", tier=bus.TIER_LOW, panel=bus.PANEL_PASS)])
        )


def _cfg(repo: Path, **kw) -> Config:
    base = dict(repo=repo, goal="demo", backend="mock", auto_approve=True)
    base.update(kw)
    return Config(**base)


class TestSafetyNet(unittest.TestCase):
    def test_scope_check_blocks_out_of_scope(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            # HANDOFF with a scope whitelist that excludes forbidden.py.
            (repo / bus.HANDOFF).write_text(
                "# HANDOFF\n```scope\nallowed.py\n```\n", encoding="utf-8"
            )
            cfg = _cfg(repo, net_enforce=True)
            res = safety.scan([Change(path="forbidden.py", content="x = 1\n")], cfg)
            self.assertTrue(res.blocked, res.reasons)

    def test_in_scope_passes(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            (repo / bus.HANDOFF).write_text(
                "# HANDOFF\n```scope\nallowed.py\n```\n", encoding="utf-8"
            )
            cfg = _cfg(repo, net_enforce=True)
            res = safety.scan([Change(path="allowed.py", content="x = 1\n")], cfg)
            self.assertFalse(res.blocked, res.reasons)

    def test_secret_scan_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            (repo / bus.HANDOFF).write_text(
                "# HANDOFF\n```scope\nsrc/x.py\n```\n", encoding="utf-8"
            )
            cfg = _cfg(repo, net_enforce=True)
            key = "AKIA" + "IOSFODNN7EXAMPLE"  # matches the aws_access_key content pattern
            res = safety.scan([Change(path="src/x.py", content=f"KEY = '{key}'\n")], cfg)
            self.assertTrue(res.blocked, res.reasons)

    def test_missing_handler_fails_closed_in_enforce(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            (repo / bus.HANDOFF).write_text("# H\n```scope\nx.py\n```\n", encoding="utf-8")
            cfg = _cfg(repo, net_enforce=True, hooks_dir=repo / "no_such_hooks")
            res = safety.scan([Change(path="x.py", content="ok\n")], cfg)
            self.assertTrue(res.blocked, res.reasons)


class TestEndToEndMock(unittest.TestCase):
    def test_low_cycle_completes(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            cfg = _cfg(repo)
            mock = MockBackend(default_low_scenario("demo"))
            out = Orchestrator(cfg, mock, mock, AutoApprove(), log=lambda m: None).run()
            self.assertEqual(out.status, DONE, out.reason)
            self.assertEqual(out.cycles, 1)
            # bus files were written
            self.assertTrue((repo / bus.HANDOFF).is_file())
            self.assertTrue((repo / bus.RESULT).is_file())

    def test_high_panel_fail_blocks(self):
        # HIGH gate whose panel FAILs must block at the tier gate.
        handoff = (
            "# HANDOFF\n## 5. 게이트\n### Gate 1\n- 작업: x\n\n"
            "```tiers\ngate 1: HIGH\n```\n```scope\nsrc/net.py\n```\n"
        )
        result = "```verdicts\ngate 1: status=completed tier=HIGH panel=FAIL\n```\n"
        sc = Scenario(
            handoffs=[handoff],
            results=[result],
            changesets=[[Change(path="src/net.py", content="x = 1\n")]],
            reviews=["```control\nverdict: DONE\n```"],
        )
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            cfg = _cfg(repo)
            mock = MockBackend(sc)
            out = Orchestrator(cfg, mock, mock, AutoApprove(), log=lambda m: None).run()
            self.assertEqual(out.status, BLOCKED, out.reason)


class _RejectGate:
    """A human that declines every gate."""

    def confirm(self, prompt: str) -> bool:
        return False


def _high_scenario() -> Scenario:
    handoff = (
        "# HANDOFF\n## 5. 게이트\n### Gate 1\n- 작업: x\n\n"
        "```tiers\ngate 1: HIGH\n```\n```scope\nsrc/net.py\n```\n"
    )
    result = "```verdicts\ngate 1: status=completed tier=HIGH panel=PASS\n```\n"
    return Scenario(
        handoffs=[handoff],
        results=[result],
        changesets=[[Change(path="src/net.py", content="x = 1\n")]],
        reviews=["```control\nverdict: DONE\n```"],
    )


class TestHumanGates(unittest.TestCase):
    def test_high_pass_completes_with_signoff(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            mock = MockBackend(_high_scenario())
            out = Orchestrator(cfg, mock, mock, AutoApprove(), log=lambda m: None).run()
            self.assertEqual(out.status, DONE, out.reason)

    def test_high_decline_is_held(self):
        # confirm_handoff False isolates the HIGH end sign-off as the only gate.
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d), confirm_handoff=False)
            mock = MockBackend(_high_scenario())
            out = Orchestrator(cfg, mock, mock, _RejectGate(), log=lambda m: None).run()
            self.assertEqual(out.status, HELD, out.reason)


class TestBuildFromHandoff(unittest.TestCase):
    """run_from_handoff: single-shot Builder pass from an on-disk HANDOFF.md
    (the interactive Architect's auto-dispatch path). No headless architect."""

    def test_built_from_existing_handoff(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            # default_low_scenario's handoff carries a `gate 1: LOW` tiers fence.
            sc = default_low_scenario("demo")
            (repo / bus.HANDOFF).write_text(sc.handoffs[0], encoding="utf-8")
            cfg = _cfg(repo)
            mock = MockBackend(sc)
            out = Orchestrator(cfg, mock, mock, AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BUILT, out.reason)
            self.assertTrue((repo / bus.RESULT).is_file())

    def test_retries_once_on_builder_bail(self):
        # A headless Builder that bails (status=blocked, no changeset) after a
        # false read-only self-judgement is re-dispatched once; the clean second
        # attempt BUILDs. Verified against real Codex 2026-07-14.
        handoff = "# H\n```tiers\ngate 1: LOW\n```\n```scope\nfeat.py\n```\n"
        sc = Scenario(
            handoffs=[handoff],
            results=[
                "bailed\n```verdicts\ngate 1: status=blocked tier=LOW panel=BLOCK\n```\n",
                "```verdicts\ngate 1: status=completed tier=LOW panel=PASS\n```\n",
            ],
            changesets=[[], [Change(path="feat.py", content="x = 1\n")]],
            reviews=[],
        )
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            (repo / bus.HANDOFF).write_text(handoff, encoding="utf-8")
            cfg = _cfg(repo)
            mock = MockBackend(sc)
            out = Orchestrator(cfg, mock, mock, AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BUILT, out.reason)
            self.assertEqual(out.cycles, 2)  # retried exactly once

    def test_no_retry_on_completed_panel_fail(self):
        # A completed gate whose review panel FAILs is a legitimate advisory
        # outcome, not a bail: it must NOT be retried (which would clobber the
        # informative verdict the in-session review reads). One attempt only.
        handoff = "# H\n```tiers\ngate 1: LOW\n```\n```scope\nfeat.py\n```\n"
        sc = Scenario(
            handoffs=[handoff],
            results=[
                "```verdicts\ngate 1: status=completed tier=LOW panel=FAIL\n```\n",
                "SECOND ATTEMPT SHOULD NOT RUN\n",
            ],
            changesets=[[Change(path="feat.py", content="x = 1\n")], []],
            reviews=[],
        )
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            (repo / bus.HANDOFF).write_text(handoff, encoding="utf-8")
            cfg = _cfg(repo)
            mock = MockBackend(sc)
            out = Orchestrator(cfg, mock, mock, AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BUILT, out.reason)
            self.assertEqual(out.cycles, 1)  # no retry
            self.assertNotIn("SECOND ATTEMPT", (repo / bus.RESULT).read_text(encoding="utf-8"))

    def test_missing_handoff_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            mock = MockBackend(default_low_scenario("demo"))
            out = Orchestrator(cfg, mock, mock, AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)

    def test_custom_handoff_name(self):
        # build reads cfg.handoff_name so a repo that keeps HANDOFF.md as a
        # persistent doc can dispatch an alternate spec without clobbering it.
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            sc = default_low_scenario("demo")
            # HANDOFF.md occupied by an unrelated persistent doc; spec lives elsewhere.
            (repo / bus.HANDOFF).write_text("# P0 master doc — not a handoff\n", encoding="utf-8")
            (repo / "HANDOFF_WEBVIEW.md").write_text(sc.handoffs[0], encoding="utf-8")
            cfg = _cfg(repo, handoff_name="HANDOFF_WEBVIEW.md")
            mock = MockBackend(sc)
            out = Orchestrator(cfg, mock, mock, AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BUILT, out.reason)
            self.assertTrue((repo / bus.RESULT).is_file())

    def test_safety_net_blocks_out_of_scope(self):
        # The safety net (scope_check) is ALWAYS a hard block in the build path —
        # an out-of-scope change fails closed even though tier-gate is advisory.
        handoff = "# H\n```tiers\ngate 1: LOW\n```\n```scope\nallowed.py\n```\n"
        sc = Scenario(
            handoffs=[handoff],
            results=["```verdicts\ngate 1: status=completed tier=LOW panel=PASS\n```\n"],
            changesets=[[Change(path="forbidden.py", content="x = 1\n")]],
            reviews=[],
        )
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            (repo / bus.HANDOFF).write_text(handoff, encoding="utf-8")
            cfg = _cfg(repo)
            mock = MockBackend(sc)
            out = Orchestrator(cfg, mock, mock, AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)

    def test_tier_gate_advisory_does_not_block(self):
        # HIGH gate, panel FAIL, but in-scope: tier-gate is advisory in the build
        # path, so it still BUILDs — the in-session Claude review owns the verdict
        # and the HIGH human sign-off happens in-session, not here.
        sc = _high_scenario()
        sc.results[0] = "```verdicts\ngate 1: status=completed tier=HIGH panel=FAIL\n```\n"
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            (repo / bus.HANDOFF).write_text(sc.handoffs[0], encoding="utf-8")
            cfg = _cfg(repo)
            mock = MockBackend(sc)
            out = Orchestrator(cfg, mock, mock, AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BUILT, out.reason)


if __name__ == "__main__":
    unittest.main()
