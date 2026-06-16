"""Tests for the hook safety contract in ``lib/common.run_handler`` (ADR-0001).

The fail-open wrapper is the critical safety property: a handler bug must
never block a user's tool call. These tests pin the exit-code semantics.

The 200ms timeout path is intentionally NOT exercised here — it ends in
``os._exit(0)``, which would terminate the test runner. It is covered by
the manual stdin smoke documented in hooks/README.md instead.

Stdlib-only (no pytest), matching the hooks' zero-dependency contract.

Run:  py -3 -m unittest discover -s hooks/tests
  or: py -3 hooks/tests/test_common.py
"""
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


if __name__ == "__main__":
    unittest.main()
