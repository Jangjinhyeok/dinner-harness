"""Tests for the hook safety contract in ``lib/common.run_handler`` (ADR-0001).

The fail-open wrapper is the critical safety property: a handler bug must
never block a user's tool call. These tests pin the exit-code semantics.

The 200ms timeout path ends in ``os._exit``, which would terminate the test
runner, so it is exercised only in a child interpreter (``TimeoutWarning``).

Stdlib-only (no pytest), matching the hooks' zero-dependency contract.

Run:  py -3 -m unittest discover -s hooks/tests
  or: py -3 hooks/tests/test_common.py
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Make ``lib.common`` importable the same way the BAT-launched handlers do.
_HOOKS_ROOT = Path(__file__).resolve().parent.parent
if str(_HOOKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_HOOKS_ROOT))

import lib.common as common  # noqa: E402
from lib.common import run_handler  # noqa: E402


def _exit_code(main_callable, hook_name="__unittest_probe__"):
    """Invoke run_handler and return the integer exit code it raised."""
    try:
        run_handler(main_callable, hook_name=hook_name)
    except SystemExit as exc:
        return 0 if exc.code is None else exc.code
    raise AssertionError("run_handler did not call sys.exit")


class RunHandlerContract(unittest.TestCase):
    def test_normal_return_allows(self):
        self.assertEqual(_exit_code(lambda: None), 0)

    def test_explicit_block_propagates(self):
        def main():
            raise SystemExit(2)

        self.assertEqual(_exit_code(main), 2)

    def test_non_block_systemexit_collapses_to_allow(self):
        # exit_warn() raises SystemExit(0); any non-2 code must become allow.
        def warn():
            raise SystemExit(0)

        def odd():
            raise SystemExit(1)

        self.assertEqual(_exit_code(warn), 0)
        self.assertEqual(_exit_code(odd), 0)

    def test_arbitrary_exception_fails_open(self):
        def main():
            raise ValueError("boom")

        original = common._LOGS_DIR
        with tempfile.TemporaryDirectory() as tmp:
            common._LOGS_DIR = Path(tmp)
            try:
                self.assertEqual(_exit_code(main), 0)  # fail-open
                err_log = Path(tmp) / "__unittest_probe__.error.log"
                self.assertTrue(err_log.is_file())
                self.assertIn("ValueError", err_log.read_text(encoding="utf-8"))
            finally:
                common._LOGS_DIR = original


class TimeoutWarning(unittest.TestCase):
    """The watchdog fires in a child process — ``os._exit`` would end this runner."""

    _CHILD = (
        "import sys, time\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "import lib.common as common\n"
        "common._LOGS_DIR = Path(sys.argv[2])\n"
        "common.run_handler(lambda: time.sleep(5), hook_name='secret_scan')\n"
    )

    def _run(self, fails_closed):
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_HOOK_FAILS_CLOSED"}
        env["CLAUDE_HOOK_TIMEOUT_MS"] = "50"
        if fails_closed:
            env["CLAUDE_HOOK_FAILS_CLOSED"] = "1"
        with tempfile.TemporaryDirectory() as tmp:
            return subprocess.run(
                [sys.executable, "-c", self._CHILD, str(_HOOKS_ROOT), tmp],
                capture_output=True, encoding="utf-8", errors="replace", env=env, timeout=30)

    def test_interactive_timeout_allows_with_one_warn_line(self):
        p = self._run(fails_closed=False)
        self.assertEqual(p.returncode, 0, p.stderr)
        lines = p.stderr.splitlines()
        self.assertEqual(len(lines), 1, p.stderr)
        self.assertTrue(lines[0].startswith("[WARN] secret_scan: "), p.stderr)
        self.assertIn("50ms budget", lines[0])

    def test_net_timeout_blocks_without_warn(self):
        p = self._run(fails_closed=True)
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertIn("[secret_scan:block]", p.stderr)
        self.assertNotIn("[WARN]", p.stderr)


if __name__ == "__main__":
    unittest.main()
