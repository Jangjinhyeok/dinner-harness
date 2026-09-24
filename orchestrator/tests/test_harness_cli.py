"""Behavioral contracts for the harness CLI orchestration boundaries."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

import check
import install
import refresh


class RefreshCliTests(unittest.TestCase):
    def test_preview_only_checks_source_and_previews_every_target(self):
        events = []
        with mock.patch.object(refresh.check, "main", side_effect=lambda argv: events.append(("check", argv)) or 0), \
             mock.patch.object(refresh.install, "main", side_effect=lambda argv: events.append(("install", argv)) or 0), \
             redirect_stdout(StringIO()):
            self.assertEqual(refresh.main([]), 0)
        self.assertEqual(events, [
            ("check", ["--no-install"]),
            ("install", ["--target", "claude", "--allow-live", "--dry-run"]),
            ("install", ["--target", "codex", "--allow-live", "--dry-run"]),
        ])

    def test_preflight_and_preview_failures_stop_before_writes(self):
        for check_status, install_statuses, expected_calls, expected_status in (
            (7, [], [], 7),
            (0, [5], [["--target", "claude", "--allow-live", "--dry-run"]], 5),
            (0, [0, 6], [
                ["--target", "claude", "--allow-live", "--dry-run"],
                ["--target", "codex", "--allow-live", "--dry-run"],
            ], 6),
        ):
            with self.subTest(expected_status=expected_status):
                with mock.patch.object(refresh.check, "main", return_value=check_status) as checks, \
                     mock.patch.object(refresh.install, "main", side_effect=install_statuses) as installs, \
                     redirect_stdout(StringIO()):
                    self.assertEqual(refresh.refresh(apply=True), expected_status)
                checks.assert_called_once_with(["--no-install"])
                self.assertEqual([call.args[0] for call in installs.call_args_list], expected_calls)

    def test_apply_previews_all_before_writes_and_stops_on_install_failure(self):
        calls = []
        statuses = iter((0, 0, 8))
        with mock.patch.object(refresh.check, "main", side_effect=lambda argv: calls.append(("check", argv)) or 0), \
             mock.patch.object(refresh.install, "main", side_effect=lambda argv: calls.append(("install", argv)) or next(statuses)), \
             redirect_stdout(StringIO()):
            self.assertEqual(refresh.refresh(apply=True), 8)
        self.assertEqual(calls, [
            ("check", ["--no-install"]),
            ("install", ["--target", "claude", "--allow-live", "--dry-run"]),
            ("install", ["--target", "codex", "--allow-live", "--dry-run"]),
            ("install", ["--target", "claude", "--allow-live"]),
        ])

    def test_installer_exceptions_propagate_without_later_stages(self):
        for failure in (SystemExit(4), RuntimeError("render failed")):
            with self.subTest(failure=type(failure).__name__):
                with mock.patch.object(refresh.check, "main", return_value=0) as checks, \
                     mock.patch.object(refresh.install, "main", side_effect=failure) as installs, \
                     redirect_stdout(StringIO()):
                    with self.assertRaises(type(failure)):
                        refresh.refresh(apply=True)
                checks.assert_called_once_with(["--no-install"])
                installs.assert_called_once_with(["--target", "claude", "--allow-live", "--dry-run"])

    def test_post_check_failure_is_returned_after_all_installs(self):
        with mock.patch.object(refresh.check, "main", side_effect=(0, 9)) as checks, \
             mock.patch.object(refresh.install, "main", return_value=0) as installs, \
             redirect_stdout(StringIO()):
            self.assertEqual(refresh.refresh(apply=True, target="codex"), 9)
        self.assertEqual(checks.call_args_list, [
            mock.call(["--no-install", "--target", "codex"]),
            mock.call(["--target", "codex"]),
        ])
        self.assertEqual(installs.call_args_list, [
            mock.call(["--target", "codex", "--allow-live", "--dry-run"]),
            mock.call(["--target", "codex", "--allow-live"]),
        ])


class InstallCliTests(unittest.TestCase):
    def test_live_guard_prevents_adapter_dispatch(self):
        with mock.patch.object(install, "default_dest", return_value=Path("live")), \
             mock.patch.object(install, "is_live_dest", return_value=True), \
             mock.patch.object(install, "load_adapter") as adapter:
            with self.assertRaisesRegex(SystemExit, "refusing to write"):
                install.main(["--target", "codex"])
        adapter.assert_not_called()

    def test_dry_run_dispatches_and_reports_plan(self):
        adapter = SimpleNamespace(install=mock.Mock(return_value=[
            ("copy", Path("copied")), ("template", Path("rendered")),
        ]))
        output = StringIO()
        with mock.patch.object(install, "default_dest", return_value=Path("live")), \
             mock.patch.object(install, "is_live_dest", return_value=True), \
             mock.patch.object(install, "load_adapter", return_value=adapter), \
             redirect_stdout(output):
            self.assertEqual(install.main(["--target", "codex", "--dry-run"]), 0)
        self.assertTrue(adapter.install.call_args.kwargs["dry_run"])
        self.assertIn("[DRY-RUN] target=codex", output.getvalue())
        self.assertIn("copy=1, template=1 (total 2)", output.getvalue())
        self.assertIn("template", output.getvalue())


class CheckCliTests(unittest.TestCase):
    def test_source_failure_sets_exit_one_without_install(self):
        output = StringIO()
        with mock.patch.object(check, "check_catalog", return_value=({"Skills": 0, "Agents": 0, "Hooks": 0}, ["catalog issue"])), \
             mock.patch.object(check, "check_codex_generated", return_value=["generated issue"]), \
             mock.patch.object(check, "check_install") as installs, \
             redirect_stdout(output):
            self.assertEqual(check.main(["--target", "codex", "--no-install"]), 1)
        installs.assert_not_called()
        self.assertIn("catalog issue", output.getvalue())
        self.assertIn("generated issue", output.getvalue())

    def test_install_failure_exits_one_but_advisory_only_exits_zero(self):
        for problems, leftovers, expected in (
            (["broken"], [("extra", True)], 1),
            ([], [("stale", False)], 1),
            ([], [("shared", True)], 0),
        ):
            with self.subTest(expected=expected, problems=problems, leftovers=leftovers):
                output = StringIO()
                with mock.patch.object(check, "check_catalog", return_value=({"Skills": 0, "Agents": 0, "Hooks": 0}, [])), \
                     mock.patch.object(check, "check_codex_generated", return_value=[]), \
                     mock.patch.object(check, "check_install", return_value=(True, problems, leftovers)), \
                     mock.patch.object(check, "skill_discovery_roots", return_value=[]), \
                     mock.patch.object(check, "report_skill_duplicates"), \
                     redirect_stdout(output):
                    self.assertEqual(check.main(["--target", "codex"]), expected)
                self.assertIn("[install:codex]", output.getvalue())


if __name__ == "__main__":
    unittest.main()
