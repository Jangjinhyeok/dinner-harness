"""Offline subprocess contract regressions; no model or real home access."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from orchestrator.config import Config
from orchestrator import vendors


class VendorMigrationTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.cfg = Config(repo=self.root, audit_dir=self.root / "audit", timeout_s=5)

    def run_script(self, code, **kwargs):
        return vendors._run([sys.executable, "-c", code], self.cfg, **kwargs)

    def test_jsonl_metadata_and_separate_clean_final(self):
        final = self.root / "final.txt"
        final.write_text('{"version":1}', encoding="utf-8")
        events = [
            {"type": "thread.started", "thread_id": "thread-123"},
            {"type": "item.completed", "item": {"text": "not final"}},
            {"type": "turn.completed", "usage": {
                "input_tokens": 12, "cached_input_tokens": 2, "output_tokens": 3,
                "unrecognized_sensitive_field": "never retain"}},
        ]
        turn = self.run_script(
            "print(" + repr("\n".join(map(json.dumps, events))) + ")",
            json_events=True, last_message_file=final)
        self.assertEqual(turn.error, "")
        self.assertEqual(turn.thread_id, "thread-123")
        self.assertEqual(turn.text, '{"version":1}')
        self.assertEqual(turn.usage, {"input_tokens": 12, "cached_input_tokens": 2, "output_tokens": 3})

    def test_missing_final_never_falls_back_to_events(self):
        turn = self.run_script('print(\'{"type":"turn.completed"}\')',
                               json_events=True, last_message_file=self.root / "absent")
        self.assertIn("final response file missing", turn.error)
        self.assertEqual(turn.text, "")

    def test_failure_event_and_invalid_json_fail_closed(self):
        for line in ('{"type":"turn.failed","error":{"message":"secret"}}', "sandbox: workspace-write"):
            with self.subTest(line=line):
                turn = self.run_script("print(" + repr(line) + ")", json_events=True)
                self.assertTrue(turn.error)
                self.assertNotIn("secret", turn.error)

    def test_exit_error_preserves_clean_partial_report(self):
        final = self.root / "partial.txt"
        final.write_text("partial report", encoding="utf-8")
        turn = self.run_script("import sys; sys.exit(9)", last_message_file=final)
        self.assertIn("exit 9", turn.error)
        self.assertEqual(turn.text, "partial report")

    def test_prompt_stdin_unicode_and_long_payload(self):
        prompt = "한글; $(must-not-execute) " * 30000
        turn = self.run_script("import sys; sys.stdin.reconfigure(encoding='utf-8'); print(len(sys.stdin.read()))", stdin_text=prompt)
        self.assertEqual(turn.error, "")
        self.assertEqual(int(turn.text), len(prompt))

    def test_timeout_includes_blocked_stdin_writer(self):
        self.cfg.timeout_s = 0.2
        started = time.monotonic()
        turn = self.run_script("import time; time.sleep(30)", stdin_text="x" * 2000000)
        self.assertIn("timed out", turn.error)
        self.assertLess(time.monotonic() - started, 9)

    def test_timeout_terminates_child_before_delayed_write(self):
        self.cfg.timeout_s = 0.3
        escaped = self.root / "child-survived"
        child = "import time,pathlib;time.sleep(2);pathlib.Path(" + repr(str(escaped)) + ").touch()"
        code = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c'," + repr(child) + "]);time.sleep(30)"
        turn = self.run_script(code)
        self.assertIn("timed out", turn.error)
        time.sleep(2.1)
        self.assertFalse(escaped.exists())

    def test_exited_parent_cannot_leave_child_writing_after_return(self):
        escaped = self.root / "orphan-survived"
        child = "import time,pathlib;time.sleep(3);pathlib.Path(" + repr(str(escaped)) + ").touch()"
        # Parent exits normally while its child still owns inherited pipe handles.
        code = "import subprocess,sys; subprocess.Popen([sys.executable,'-c'," + repr(child) + "])"
        started = time.monotonic()
        turn = self.run_script(code)
        self.assertEqual(turn.error, "")
        self.assertLess(time.monotonic() - started, 2.5)
        time.sleep(3.1)
        self.assertFalse(escaped.exists())

    @unittest.skipUnless(os.name == "nt", "Windows job assignment")
    def test_containment_failure_never_executes_suspended_child(self):
        escaped = self.root / "must-not-run"
        with patch.object(vendors._WindowsJob, "assign_and_resume", side_effect=OSError("denied")):
            turn = self.run_script("import pathlib;pathlib.Path(" + repr(str(escaped)) + ").touch()")
        self.assertTrue(turn.error)
        self.assertFalse(escaped.exists())

    def test_codex_schema_permissions_and_dispatch_markers(self):
        self.cfg.output_schema = self.root / "schema.json"
        captured = []
        def fake_run(argv, cfg, **kwargs):
            captured.append((argv, kwargs))
            kwargs["on_event"]({"type": "thread.started", "thread_id": "thread-123", "usage": {}})
            return vendors.Turn(text="{}", thread_id="thread-123")
        with patch.object(vendors, "_run", side_effect=fake_run):
            turns = [vendors.CodexBackend().invoke(role, "prompt", self.cfg)
                     for role in (vendors.ROLE_BUILDER, vendors.ROLE_CHALLENGER,
                                  vendors.ROLE_REVIEWER, vendors.ROLE_RECOVERY)]
        for index, (argv, kwargs) in enumerate(captured):
            self.assertIn("--json", argv)
            self.assertEqual(argv[argv.index("--output-schema") + 1], str(self.cfg.output_schema))
            self.assertEqual(argv[argv.index("--sandbox") + 1], "workspace-write" if index == 0 else "read-only")
            self.assertNotIn("--enable", argv)
            self.assertEqual(kwargs["stdin_text"], "prompt")
        self.assertEqual(len({turn.dispatch_id for turn in turns}), 4)
        markers = list(self.cfg.audit_dir.glob("watch-builder-*.json"))
        self.assertEqual(len(markers), 4)
        self.assertFalse((self.cfg.audit_dir / "watch-builder-session.txt").exists())
        for marker in markers:
            metadata = json.loads(marker.read_text(encoding="utf-8"))
            self.assertEqual(metadata["sandbox_verified"], "not_run")
            self.assertNotIn("prompt", metadata)

    def test_claude_nonbuilder_drops_direct_mode(self):
        with patch.dict(os.environ, DINNER_EXECUTION_MODE="direct"), patch.object(vendors, "_run", return_value=vendors.Turn()) as run:
            for role in (vendors.ROLE_CHALLENGER, vendors.ROLE_REVIEWER, vendors.ROLE_RECOVERY):
                vendors.ClaudeBackend().invoke(role, "prompt", self.cfg)
                argv = run.call_args.args[0]
                self.assertEqual(argv[argv.index("--permission-mode") + 1], "plan")
                self.assertNotIn("DINNER_EXECUTION_MODE", run.call_args.kwargs["env"])


if __name__ == "__main__":
    unittest.main()
