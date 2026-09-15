"""Offline grader contracts; these tests do not execute an agent or an engine."""
import copy
import json
import unittest

from docs.evals.workflow_evidence.grade import CASES, grade


class TestWorkflowEvidenceGrader(unittest.TestCase):
    def setUp(self):
        self.cases = json.loads(CASES.read_text(encoding="utf-8"))
        # Synthetic control reports, never reported as actual model attempts.
        self.reports = [dict(id=case["id"], reason="Synthetic grader control.",
                             **copy.deepcopy(case["expected"])) for case in self.cases]

    def test_fixture_expectations_are_well_formed(self):
        identities = [case["id"] for case in self.cases]
        self.assertEqual(len(identities), len(set(identities)))
        for case in self.cases:
            self.assertTrue(case["task"])
            self.assertTrue(case["expected"]["claims"])
            self.assertLessEqual(set(case["expected"]["claims"].values()),
                                 {"PASS", "FAIL", "not_run", "BLOCKED"})
            self.assertLessEqual(set(case["expected"]["evidence"]), set(case["evidence"]))

    def test_controls_pass_and_each_wrong_pass_is_rejected(self):
        self.assertEqual(grade(self.cases, self.reports), [])
        for index, report in enumerate(self.reports):
            for claim, status in report["claims"].items():
                with self.subTest(case=report["id"], claim=claim):
                    changed = copy.deepcopy(self.reports)
                    changed[index]["claims"][claim] = "FAIL" if status == "PASS" else "PASS"
                    self.assertTrue(grade(self.cases, changed))

    def test_partial_duplicate_unknown_and_malformed_reports_fail(self):
        for reports in (None, {}, [], self.reports[:-1], self.reports + [self.reports[0]],
                        self.reports + [{"id": "invented"}], self.reports + [None]):
            with self.subTest(reports_type=type(reports).__name__):
                self.assertTrue(grade(self.cases, reports))

    def test_unsupported_or_missing_evidence_and_explanation_fail(self):
        for key, value in (("evidence", []), ("evidence", ["invented"]),
                           ("evidence", [{}]), ("reason", " "), ("claims", {})):
            with self.subTest(key=key, value=value):
                changed = copy.deepcopy(self.reports)
                changed[0][key] = value
                self.assertTrue(grade(self.cases, changed))


if __name__ == "__main__":
    unittest.main()
