"""Orchestrator tests — stdlib unittest, fully offline (mock backend + the real
hook handlers as the safety net). Run from the repo root:

    py -3 -m unittest discover -s orchestrator/tests
"""
from __future__ import annotations

import json
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import orchestrate
from orchestrator import bus
from orchestrator.config import Config
from orchestrator.controller import (
    AutoApprove,
    Orchestrator,
    collect_changeset,
    compute_has_high,
    enforce_tier_gates,
    BUILT,
    DONE,
    BLOCKED,
    HELD,
)
from orchestrator import safety
from orchestrator import vendors
from orchestrator.vendors import (
    ROLE_BUILDER,
    Backend,
    MockBackend,
    Scenario,
    Turn,
    default_low_scenario,
)
from orchestrator.safety import Change

_HOOKS_ROOT = Path(__file__).resolve().parents[2] / "assets" / "claude" / "hooks"
if str(_HOOKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_HOOKS_ROOT))
from handlers import builder_guard  # noqa: E402


_GIT_ISOLATION = {
    # The controller shells out to git itself, so isolation has to live in the
    # PROCESS environment — passing -c to the test's own git calls would not
    # reach it. Without this the suite reads the developer's git config: a
    # global core.excludesFile hides the Builder's writes from `git status`
    # (2 FAIL + 4 ERROR, and the net silently stops seeing changes), and
    # commit.gpgsign turns every _git_commit_all into a CalledProcessError.
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}
_SAVED_ENV: dict = {}


def setUpModule():
    for k, v in _GIT_ISOLATION.items():
        _SAVED_ENV[k] = os.environ.get(k)
        os.environ[k] = v


def tearDownModule():
    for k, old in _SAVED_ENV.items():
        if old is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = old


class TestVendorRunner(unittest.TestCase):
    def test_child_output_is_streamed_and_captured(self):
        # The old subprocess.run(capture_output=True) held every progress line
        # until the CLI exited. Keep stdout for Claude RESULT parsing while also
        # showing both streams to the operator during a long Builder turn.
        script = (
            "import sys; "
            "print('builder progress', flush=True); "
            "print('builder warning', file=sys.stderr, flush=True)"
        )
        with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout, \
             mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            turn = vendors._run([sys.executable, "-c", script], Config())
        self.assertEqual(turn.error, "")
        self.assertEqual(turn.text, "builder progress\n")
        self.assertIn("builder progress", stdout.getvalue())
        self.assertIn("builder warning", stderr.getvalue())

    def test_timeout_kills_the_child_and_names_the_configured_budget(self):
        # A timeout must terminate the child (rather than leave Codex behind)
        # and the operator needs the actual CLI-configured budget to distinguish
        # it from a policy block. The current salvage is the surviving worktree,
        # not treating a still-running process as a successful Builder turn.
        cfg = Config(timeout_s=0.05)
        turn = vendors._run([sys.executable, "-c", "import time; time.sleep(5)"], cfg)
        self.assertIn("timed out after 0.05s", turn.error)

    def test_cli_passes_timeout_to_config_and_rejects_zero(self):
        # `--timeout-s` is the supported escape hatch for a productive CLI
        # process that has not exited. Without wiring it into Config, argparse
        # accepts the flag but the runner silently keeps the 1800-second budget.
        with mock.patch("sys.stdout", new_callable=io.StringIO), \
             mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            status = orchestrate.main([
                "run", "--goal", "demo", "--backend", "mock", "--yes",
                "--timeout-s", "0",
            ])
        self.assertEqual(status, 2)
        self.assertIn("timeout_s must be > 0", stderr.getvalue())


class TestBuilderFirstGuard(unittest.TestCase):
    def test_claude_template_wires_guard_for_structured_file_edits(self):
        # A correct handler that is absent from settings is indistinguishable
        # from no guard at all. Pin the installed Claude matcher and launcher.
        template = json.loads(
            (Path(__file__).resolve().parents[2] / "assets" / "claude" /
             "settings.json.template").read_text(encoding="utf-8")
        )
        commands = [
            hook["command"]
            for entry in template["hooks"]["PreToolUse"]
            if entry.get("matcher") == "Edit|Write"
            for hook in entry["hooks"]
        ]
        self.assertIn("<CLAUDE_HOME>/hooks/launchers/builder_guard.cmd", commands)

    def test_only_bus_and_architecture_artifacts_are_allowed(self):
        # The guard is deliberately narrow: it reserves implementation edits
        # for Codex without preventing an Architect from writing its spec/ADR.
        old = os.environ.get("DINNER_EXECUTION_MODE")
        os.environ["DINNER_EXECUTION_MODE"] = "builder-first"
        try:
            cwd = Path(tempfile.gettempdir()) / "builder-guard-test"
            code = {"tool_name": "Edit", "cwd": str(cwd),
                    "tool_input": {"file_path": "src/feature.py"}}
            handoff = {"tool_name": "Write", "cwd": str(cwd),
                       "tool_input": {"file_path": "HANDOFF_DELEGATE.md"}}
            adr = {"tool_name": "Write", "cwd": str(cwd),
                   "tool_input": {"file_path": "docs/architecture/ADR-0008.md"}}
            self.assertEqual(builder_guard.guarded_paths(code), ["src/feature.py"])
            self.assertEqual(builder_guard.guarded_paths(handoff), [])
            self.assertEqual(builder_guard.guarded_paths(adr), [])
        finally:
            if old is None:
                os.environ.pop("DINNER_EXECUTION_MODE", None)
            else:
                os.environ["DINNER_EXECUTION_MODE"] = old

    def test_apply_patch_cannot_hide_a_code_edit_behind_an_allowed_handoff(self):
        # A mixed patch is one structured file-edit call. Allowing it because
        # its first target is HANDOFF.md would reopen the inline-code path.
        old = os.environ.get("DINNER_EXECUTION_MODE")
        os.environ["DINNER_EXECUTION_MODE"] = "builder-first"
        try:
            payload = {
                "tool_name": "apply_patch",
                "cwd": tempfile.gettempdir(),
                "tool_input": {"command": """*** Begin Patch
*** Update File: HANDOFF.md
+spec
*** Update File: src/feature.py
+implementation
*** End Patch
"""},
            }
            self.assertEqual(builder_guard.guarded_paths(payload), ["src/feature.py"])
        finally:
            if old is None:
                os.environ.pop("DINNER_EXECUTION_MODE", None)
            else:
                os.environ["DINNER_EXECUTION_MODE"] = old

    def test_guard_audit_hashes_a_blocked_path_instead_of_retaining_it(self):
        old = os.environ.get("DINNER_EXECUTION_MODE")
        os.environ["DINNER_EXECUTION_MODE"] = "builder-first"
        nonce = "customer-project-path-must-not-be-logged.py"
        payload = {"tool_name": "Edit", "cwd": tempfile.gettempdir(),
                   "tool_input": {"file_path": nonce}}
        try:
            with mock.patch.object(builder_guard, "read_hook_input", return_value=payload), \
                 mock.patch.object(builder_guard, "log_event") as log_event, \
                 mock.patch.object(builder_guard, "exit_block", side_effect=SystemExit(2)):
                with self.assertRaises(SystemExit):
                    builder_guard.main()
            fields = log_event.call_args.kwargs
            self.assertNotIn(nonce, json.dumps(fields))
            self.assertEqual(fields["blocked_path_count"], 1)
            self.assertEqual(fields["blocked_path_sha256"], builder_guard._path_digest(nonce))
            self.assertNotIn("file_path", fields)
        finally:
            if old is None:
                os.environ.pop("DINNER_EXECUTION_MODE", None)
            else:
                os.environ["DINNER_EXECUTION_MODE"] = old


def _git_available() -> bool:
    return shutil.which("git") is not None


def _write_n_files(repo: Path, n: int) -> None:
    """n real untracked files, so `git status -uall` reports n real paths."""
    pad = repo / "pad"
    pad.mkdir(exist_ok=True)
    for i in range(n):
        (pad / f"f{i}.txt").write_text("x\n", encoding="utf-8")


def _git_init(repo: Path) -> None:
    """A real repo, so `git status --porcelain` returns real untracked entries."""
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True,
                   capture_output=True, text=True)


def _git_commit_all(repo: Path) -> None:
    """Commit the tree, so a later removal shows up as a real ' D' entry.

    Untracked files simply vanish from `git status` when deleted; only a
    tracked one leaves the deletion the net has to judge.
    """
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True,
                   capture_output=True, text=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@example.com",
                    "-c", "user.name=t", "commit", "-qm", "base"],
                   check=True, capture_output=True, text=True)


_CLEAN_VERDICT = "```verdicts\ngate 1: status=completed tier=LOW panel=PASS\n```\n"


class _TamperingBackend(Backend):
    """Builder that messes with the bus, then reports a clean pass.

    Real backends leave ``Turn.changeset`` at None, so the controller reads the
    tree via git — the shape every production dispatch takes.
    """

    name = "tampering"

    def __init__(self, repo: Path, target: str, new_text=None, also_write=None):
        self._path = repo / target
        self._new_text = new_text  # None -> delete the file
        self._also_write = also_write

    def invoke(self, role: str, prompt: str, cfg: Config) -> Turn:
        if self._new_text is None:
            self._path.unlink()
        else:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(self._new_text, encoding="utf-8")
        if self._also_write:
            (self._path.parent / self._also_write).write_text("pwned = True\n", encoding="utf-8")
        return Turn(text=_CLEAN_VERDICT)


class _ScanSpy:
    """Records (handler_name, repo_relative_path) for every handler launch.

    Asserting on an outcome alone cannot tell "the rule allowed it" from "the
    rule was never consulted" — several tests here were the latter while
    claiming the former. This makes the difference assertable.
    """

    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def patch(self):
        import contextlib

        real = safety._run_handler
        calls = self.calls

        def spy(handler: Path, payload: dict, env: dict):
            repo = Path(payload.get("cwd", "")).resolve()
            target = Path(payload["tool_input"]["file_path"])
            try:
                rel = target.resolve().relative_to(repo).as_posix()
            except Exception:
                rel = str(target)
            calls.append((handler.stem, rel))
            return real(handler, payload, env)

        @contextlib.contextmanager
        def _ctx():
            safety._run_handler = spy
            try:
                yield
            finally:
                safety._run_handler = real

        return _ctx()


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

    def _hooks_copy(self, dest: Path) -> Path:
        """A private copy of the real hooks tree, safe to corrupt."""
        shutil.copytree(Config().hooks_dir, dest,
                        ignore=shutil.ignore_patterns("logs", "__pycache__"))
        return dest

    def _scan_with_broken_ruleset(self, repo: Path, hooks: Path, *, delete: bool):
        """Scan a real AWS key through a hooks tree whose secret ruleset is unusable."""
        rules = hooks / "rules" / "secret_patterns.json"
        if delete:
            rules.unlink()
        else:
            rules.write_text("{ not valid json", encoding="utf-8")
        (repo / bus.HANDOFF).write_text("# H\n```scope\nsrc/x.py\n```\n", encoding="utf-8")
        cfg = _cfg(repo, net_enforce=True, hooks_dir=hooks)
        key = "AKIA" + "IOSFODNN7EXAMPLE"
        return safety.scan([Change(path="src/x.py", content=f"KEY = '{key}'\n")], cfg)

    def test_unloadable_secret_ruleset_fails_closed(self):
        # Round 10 (BLOCK): secret_scan caught its own ruleset-load failure,
        # logged it, and called exit_allow() -> exit 0, which the net records as
        # a clean pass with an EMPTY reason list. CLAUDE_HOOK_FAILS_CLOSED did
        # not reach it: run_handler consults that flag only when the handler
        # CRASHES, and this handler ran to completion and chose to allow. An AWS
        # key shipped as BUILT with nothing on screen.
        #
        # Asserting `blocked` alone is not enough — scope_check could block this
        # path for its own reasons — so the reason has to name the cause.
        for delete in (False, True):
            with self.subTest(deleted=delete), tempfile.TemporaryDirectory() as d:
                repo = Path(d) / "repo"
                repo.mkdir()
                res = self._scan_with_broken_ruleset(
                    repo, self._hooks_copy(Path(d) / "hooks"), delete=delete)
                self.assertTrue(res.blocked, res.reasons)
                self.assertTrue(
                    any("secret ruleset" in r for r in res.reasons),
                    f"blocked, but not for the ruleset: {res.reasons}")

    def test_intact_ruleset_still_scans_normally(self):
        # The other half: the fail-closed path must not be reached when the
        # ruleset loads. Without this, "block on a corrupt ruleset" would also
        # pass if the handler blocked unconditionally.
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "repo"
            repo.mkdir()
            hooks = self._hooks_copy(Path(d) / "hooks")
            (repo / bus.HANDOFF).write_text("# H\n```scope\nsrc/x.py\n```\n", encoding="utf-8")
            cfg = _cfg(repo, net_enforce=True, hooks_dir=hooks)
            clean = safety.scan([Change(path="src/x.py", content="x = 1\n")], cfg)
            self.assertFalse(clean.blocked, clean.reasons)
            key = "AKIA" + "IOSFODNN7EXAMPLE"
            leaked = safety.scan([Change(path="src/x.py", content=f"K = '{key}'\n")], cfg)
            self.assertTrue(leaked.blocked, leaked.reasons)
            self.assertFalse(any("secret ruleset" in r for r in leaked.reasons),
                             f"blocked for the wrong reason: {leaked.reasons}")

    def test_interactive_session_still_safe_passes_a_broken_ruleset(self):
        # exit_no_verdict must invert ONLY under the net. An interactive Claude
        # session has a human in the loop and the opposite bargain: a handler
        # that cannot load its ruleset must not stop the user editing their own
        # files. CLAUDE_HOOK_FAILS_CLOSED is read at import, so this drives the
        # handler directly rather than through safety.scan (which always sets it).
        with tempfile.TemporaryDirectory() as d:
            hooks = self._hooks_copy(Path(d) / "hooks")
            (hooks / "rules" / "secret_patterns.json").write_text("{ nope", encoding="utf-8")
            key = "AKIA" + "IOSFODNN7EXAMPLE"
            payload = {"tool_name": "Write",
                       "tool_input": {"file_path": str(Path(d) / "x.py"),
                                      "content": f"K = '{key}'\n"},
                       "cwd": d}
            env = {k: v for k, v in os.environ.items()
                   if k != "CLAUDE_HOOK_FAILS_CLOSED"}
            env["CLAUDE_SECRET_SCAN_MODE"] = "enforce"
            proc = subprocess.run(
                [sys.executable, str(hooks / "handlers" / "secret_scan.py")],
                input=json.dumps(payload), capture_output=True,
                encoding="utf-8", errors="replace", env=env, timeout=30)
            self.assertEqual(proc.returncode, 0,
                             f"interactive session was blocked: {proc.stderr}")

    def test_scope_check_survives_a_home_less_environment(self):
        # Round 10 (tdd-guide): _install_home_posix()'s try/except around
        # Path.home() was unprotected — no test cleared the home variables, so
        # removing the guard left the suite green. It matters because the call
        # is made at IMPORT: an unguarded RuntimeError there exits the handler
        # with code 1, outside run_handler's try, where CLAUDE_HOOK_FAILS_CLOSED
        # cannot reach it — and the net reads any code other than 0 or 2 as "no
        # verdict", i.e. a blocked cycle for a reason that is not a policy hit.
        with tempfile.TemporaryDirectory() as d:
            hooks = self._hooks_copy(Path(d) / "hooks")
            env = {k: v for k, v in os.environ.items()
                   if k not in ("USERPROFILE", "HOME", "HOMEDRIVE", "HOMEPATH")}
            env["CLAUDE_SCOPE_WHITELIST_MODE"] = "enforce"
            env["CLAUDE_SCOPE_FENCE"] = "allowed.py"
            env["CLAUDE_SCOPE_HANDOFF_NAME"] = bus.HANDOFF
            payload = {"tool_name": "Write",
                       "tool_input": {"file_path": str(Path(d) / "allowed.py"),
                                      "content": "ok = True\n"},
                       "cwd": d}
            proc = subprocess.run(
                [sys.executable, str(hooks / "handlers" / "scope_check.py")],
                input=json.dumps(payload), capture_output=True,
                encoding="utf-8", errors="replace", env=env, timeout=30)
            # 0 (allowed) or 2 (a policy block) are verdicts. 1 is the import
            # blowing up before any verdict exists.
            self.assertIn(proc.returncode, (0, 2),
                          f"handler died before reaching a verdict: {proc.stderr}")
            self.assertNotIn("Traceback", proc.stderr)
            # This path IS in the pinned fence, so the verdict must be allow.
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_missing_handler_fails_closed_in_enforce(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            (repo / bus.HANDOFF).write_text("# H\n```scope\nx.py\n```\n", encoding="utf-8")
            cfg = _cfg(repo, net_enforce=True, hooks_dir=repo / "no_such_hooks")
            res = safety.scan([Change(path="x.py", content="ok\n")], cfg)
            self.assertTrue(res.blocked, res.reasons)

    def test_scope_fence_honours_alternate_handoff_name(self):
        # Regression (2026-08-05): scope_check hardcoded HANDOFF.md, so a build
        # dispatched from an alternate spec — which /delegate ALWAYS does, via
        # HANDOFF_DELEGATE.md — found no file and failed OPEN. The fence, billed
        # as the only automatic defense against a hook-less Codex Builder, was
        # inert for every run of that lane.
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            (repo / "HANDOFF_DELEGATE.md").write_text(
                "# H\n```scope\nallowed.py\n```\n", encoding="utf-8"
            )
            cfg = _cfg(repo, net_enforce=True, handoff_name="HANDOFF_DELEGATE.md")
            res = safety.scan([Change(path="forbidden.py", content="x = 1\n")], cfg)
            self.assertTrue(res.blocked, res.reasons)
            # ...and the fence must still admit what it names.
            ok = safety.scan([Change(path="allowed.py", content="x = 1\n")], cfg)
            self.assertFalse(ok.blocked, ok.reasons)

    def _assert_handler_said(self, reasons, needle):
        """The HANDLER's own words must name `needle`, undamaged.

        Asserting on the whole reason string is not enough: `safety.scan`
        prefixes it with `ch.path`, which the parent already holds, so a
        mangled path from the child still leaves the needle present. Look only
        at the part the child wrote, and reject the replacement character —
        that substring blindness is exactly what let a real encoding defect
        through review.
        """
        marker = "[scope_check:block]"
        said = [r.split(marker, 1)[1] for r in reasons if marker in r]
        self.assertTrue(said, f"no handler block message in {reasons}")
        self.assertTrue(any(needle in s for s in said),
                        f"handler did not name {needle!r}: {said}")
        for s in said:
            self.assertNotIn("�", s, f"handler message was mangled: {s!r}")

    def test_block_reason_survives_a_non_ascii_path(self):
        # The handler answers in UTF-8; the parent read the pipe with the
        # locale codec (cp949 on this box), which killed the reader thread and
        # discarded the stderr saying WHICH rule rejected the path. The block
        # still landed, so tests asserting only `blocked` stayed green while the
        # operator got a bare "exit 2". Pin the handler's own words.
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            (repo / bus.HANDOFF).write_text(
                "# HANDOFF\n```scope\n허용.md\n```\n", encoding="utf-8")
            cfg = _cfg(repo, net_enforce=True)
            res = safety.scan([Change(path="금지.md", content="x\n")], cfg)
            self.assertTrue(res.blocked, res.reasons)
            self._assert_handler_said(res.reasons, "금지.md")

    def _scan_one(self, fence_lines, path, content="x\n", **kw):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            body = "\n".join(fence_lines)
            (repo / bus.HANDOFF).write_text(f"# H\n```scope\n{body}\n```\n",
                                            encoding="utf-8")
            cfg = _cfg(repo, net_enforce=True, **kw)
            return safety.scan([Change(path=path, content=content)], cfg).blocked

    def test_bracketed_file_entry_is_literal_not_a_character_class(self):
        # Round 10: the "brackets stay literal" rule was applied only to
        # DIRECTORY entries, because the bracket test sat after the trailing-
        # separator test. A FILE entry kept the glob promotion, so `[2026]x.md`
        # compiled to a character class — matching `2x.md` and NOT the literal
        # name the operator whitelisted. Both directions wrong at once, and the
        # block message named the very path that was in the fence, so the only
        # move it suggests is widening.
        self.assertFalse(self._scan_one(["[2026]resume.md"], "[2026]resume.md"))
        self.assertTrue(self._scan_one(["[2026]resume.md"], "2resume.md"))
        # The document lane's routine case.
        self.assertFalse(self._scan_one(["[2026]이력서.md"], "[2026]이력서.md"))
        # Directory entries were already correct — they must stay correct.
        self.assertFalse(self._scan_one(["docs/[draft]/"], "docs/[draft]/x.md"))
        self.assertTrue(self._scan_one(["docs/[draft]/"], "docs/d/x.md"))
        # And an entry that opts INTO globbing still globs.
        self.assertFalse(self._scan_one(["src/*.py"], "src/a.py"))
        self.assertTrue(self._scan_one(["src/*.py"], "src/deep/a.py"))

    def test_directory_fence_entry_matches_on_a_path_boundary(self):
        # `Path.resolve()` drops the trailing separator, so a bare `startswith`
        # let `src/` admit every sibling that merely shares the spelling.
        # Directory entries are the common case for a code-lane fence.
        self.assertFalse(self._scan_one(["src/"], "src/feature.py"))
        self.assertFalse(self._scan_one(["src/"], "src/deep/a.py"))
        for sneaky in ("src-evil.py", "srcret.env", "src.py"):
            self.assertTrue(self._scan_one(["src/"], sneaky), sneaky)
        self.assertTrue(self._scan_one(["docs/architecture/"],
                                       "docs/architecture-backup.md"))

    def test_glob_star_does_not_cross_a_separator(self):
        # fnmatch's `*` matches `/`, so `src/*.py` also admitted
        # `src/deep/nested/evil.py` — far wider than the entry says.
        self.assertFalse(self._scan_one(["src/*.py"], "src/a.py"))
        self.assertTrue(self._scan_one(["src/*.py"], "src/deep/nested/b.py"))
        # `**` keeps the recursive meaning, and `**/` also matches zero dirs.
        self.assertFalse(self._scan_one(["src/**/*.py"], "src/deep/nested/b.py"))
        self.assertFalse(self._scan_one(["src/**/*.py"], "src/b.py"))

    def test_directory_entry_that_globs_is_treated_as_a_glob(self):
        # Classifying on the trailing slash FIRST made `**/__pycache__/` a
        # prefix entry — a literal directory named `**`, matching nothing,
        # silently. That is the shape the delegate skill recommends for build
        # artifacts, and an entry that quietly matches nothing is what pushes an
        # operator to widen the fence until something works.
        fence = ["src/util/date.py", "**/__pycache__/"]
        for artifact in ("src/util/__pycache__/date.cpython-312.pyc",
                         "__pycache__/x.pyc"):
            self.assertFalse(self._scan_one(fence, artifact), artifact)
        self.assertFalse(self._scan_one(fence, "src/util/date.py"))
        # ...and it must not have become a blanket pass.
        self.assertTrue(self._scan_one(fence, "src/evil.py"))

    def test_bracket_in_a_directory_entry_stays_literal(self):
        # Promoting `[` alongside `*`/`?` turned `docs/[draft]/` into a
        # character class: it began admitting `docs/d/**` (widening) while
        # rejecting the very path it names (false block) — wrong in both
        # directions at once. Brackets are legal in directory names; `*` and `?`
        # are not even legal on NTFS, which is why only those two get promoted.
        self.assertFalse(self._scan_one(["docs/[draft]/"], "docs/[draft]/x.md"))
        self.assertTrue(self._scan_one(["docs/[draft]/"], "docs/d/x.md"))
        # ...and the wildcard promotion it was introduced for still works.
        self.assertFalse(self._scan_one(["**/__pycache__/"], "a/__pycache__/x.pyc"))

    def test_handler_that_dies_before_a_verdict_fails_closed(self):
        # lib/common emits only 0 (allow) and 2 (block), so any other code is
        # death before the verdict — an import-time exception from a
        # half-installed hooks_dir exits 1 OUTSIDE run_handler's try, where
        # CLAUDE_HOOK_FAILS_CLOSED cannot reach it. Interpreting only 0/2/-1
        # let that fall through to "allow" with an EMPTY reason list.
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            (repo / bus.HANDOFF).write_text("# H\n```scope\nallowed.py\n```\n",
                                            encoding="utf-8")
            real = safety._run_handler
            safety._run_handler = lambda h, p, e: (1, "ImportError: no module named lib")
            try:
                res = safety.scan([Change(path="allowed.py", content="x\n")],
                                  _cfg(repo, net_enforce=True))
            finally:
                safety._run_handler = real
            self.assertTrue(res.blocked, res.reasons)
            self.assertTrue(any("reached no verdict" in r for r in res.reasons),
                            res.reasons)

    def test_handler_rejects_a_traversing_handoff_name(self):
        # The handler's own defense, independent of Config.validate: anything
        # that reaches CLAUDE_SCOPE_HANDOFF_NAME must not be able to redirect
        # the fence at an arbitrary file, which would silently disarm the layer.
        import sys as _sys
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            outside = Path(d) / "outside.md"
            outside.write_text("# H\n```scope\n*\n```\n", encoding="utf-8")
            (repo / "inner").mkdir()
            handler = safety._handler(_cfg(repo), "scope_check")
            for name in ("../outside.md", "..\\outside.md", str(outside), "..", "."):
                env = dict(os.environ)
                env.pop("CLAUDE_SCOPE_FENCE", None)
                env["CLAUDE_SCOPE_WHITELIST_MODE"] = "enforce"
                env["DINNER_HARNESS_HOME"] = str(repo / "inner")
                env["CLAUDE_SCOPE_HANDOFF_NAME"] = name
                payload = json.dumps({
                    "tool_name": "Write",
                    "tool_input": {"file_path": str(repo / "inner" / "anything.py"),
                                   "content": "x\n"},
                    "cwd": str(repo / "inner")})
                p = subprocess.run([_sys.executable, str(handler)], input=payload,
                                   capture_output=True, encoding="utf-8",
                                   errors="replace", env=env, timeout=30)
                # The traversal must never resolve to the permissive fence
                # outside; with the name reduced to a basename nothing is found,
                # and an explicitly named handoff with no fence fails closed.
                self.assertEqual(p.returncode, 2, f"{name}: {p.stderr}")

    def test_handler_timeout_fails_closed_for_the_net(self):
        # The handlers' watchdog is sized for an interactive Claude hook and
        # answers "allow" when it fires. The net passes whole file contents, so
        # a large enough payload could not be read in time and the change was
        # admitted silently — measured, a key that blocks at 1 KiB shipped at
        # 48 MiB. The net now buys a budget it can meet AND makes running out
        # of time mean block.
        import json as _json
        import sys as _sys
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            (repo / bus.HANDOFF).write_text("# H\n```scope\nallowed.py\n```\n",
                                            encoding="utf-8")
            cfg = _cfg(repo, net_enforce=True)
            handler = safety._handler(cfg, "scope_check")
            # Big enough that stdin.read() + json.loads() cannot finish inside
            # the budget below — this IS the production shape, since the net
            # puts each changed file's whole content in the payload.
            payload = _json.dumps({
                "tool_name": "Write",
                "tool_input": {"file_path": str(repo / "allowed.py"),
                               "content": "x" * (8 * 1024 * 1024)},
                "cwd": str(repo),
            })

            def _run(extra_env):
                env = dict(os.environ)
                env["CLAUDE_HOOK_TIMEOUT_MS"] = "1"
                env["CLAUDE_SCOPE_WHITELIST_MODE"] = "enforce"
                env["DINNER_HARNESS_HOME"] = str(repo)
                env.pop("CLAUDE_HOOK_FAILS_CLOSED", None)
                env.update(extra_env)
                return subprocess.run([_sys.executable, str(handler)], input=payload,
                                      capture_output=True, encoding="utf-8",
                                      errors="replace", env=env, timeout=30)

            timed_out = _run({"CLAUDE_HOOK_FAILS_CLOSED": "1"})
            self.assertEqual(timed_out.returncode, 2, timed_out.stderr)
            self.assertIn("budget", timed_out.stderr)
            # The interactive contract is unchanged: a slow handler must never
            # freeze the user's edit, so without the flag a timeout still allows.
            interactive = _run({})
            self.assertEqual(interactive.returncode, 0, interactive.stderr)

    def test_net_buys_the_handler_a_budget_it_can_meet(self):
        # Pins the wiring the previous test isolates: the net must actually ask
        # for the larger budget and for fail-closed, or the watchdog silently
        # goes back to answering "allow" on a payload it could not read.
        seen: dict = {}
        real = safety._run_handler

        def spy(handler, payload, env):
            seen.update(env)
            return real(handler, payload, env)

        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            (repo / bus.HANDOFF).write_text("# H\n```scope\nallowed.py\n```\n",
                                            encoding="utf-8")
            safety._run_handler = spy
            try:
                safety.scan([Change(path="allowed.py", content="x\n")],
                            _cfg(repo, net_enforce=True))
            finally:
                safety._run_handler = real
        self.assertEqual(seen.get("CLAUDE_HOOK_FAILS_CLOSED"), "1")
        self.assertGreaterEqual(int(seen.get("CLAUDE_HOOK_TIMEOUT_MS", "0")), 1000)

    def test_glob_entry_is_anchored_at_the_end(self):
        # Without the trailing \Z the regex matches a PREFIX of the path, so
        # every glob entry silently widens: `src/*.py` would admit
        # `src/secrets.py.bak` and `src/a.python_creds`.
        self.assertFalse(self._scan_one(["src/*.py"], "src/a.py"))
        for sneaky in ("src/a.pyc", "src/secrets.py.bak", "src/a.python_creds"):
            self.assertTrue(self._scan_one(["src/*.py"], sneaky), sneaky)

    def test_interactive_session_without_a_handoff_still_fails_open(self):
        # The complement of the fail-closed rule, and the one with the wider
        # blast radius: with neither CLAUDE_SCOPE_HANDOFF_NAME nor
        # CLAUDE_SCOPE_FENCE set and no HANDOFF.md on disk, an ordinary
        # interactive Claude session must be ALLOWED to write. Dropping that
        # guard hard-blocks every Write in every session that has no handoff,
        # and nothing in the suite noticed.
        import sys as _sys
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)  # deliberately no HANDOFF.md
            handler = safety._handler(_cfg(repo), "scope_check")
            env = dict(os.environ)
            for k in ("CLAUDE_SCOPE_HANDOFF_NAME", "CLAUDE_SCOPE_FENCE"):
                env.pop(k, None)
            env["CLAUDE_SCOPE_WHITELIST_MODE"] = "enforce"
            env["DINNER_HARNESS_HOME"] = str(repo)
            payload = json.dumps({
                "tool_name": "Write",
                "tool_input": {"file_path": str(repo / "anything.py"), "content": "x\n"},
                "cwd": str(repo),
            })
            p = subprocess.run([_sys.executable, str(handler)], input=payload,
                               capture_output=True, encoding="utf-8",
                               errors="replace", env=env, timeout=30)
            self.assertEqual(p.returncode, 0, p.stderr)

    def test_handler_crash_fails_closed_for_the_net(self):
        # run_handler converts ANY unhandled exception to exit 0, which is right
        # for an interactive hook (a handler bug must not stop the user editing
        # their own files) and wrong here: the net records exit 0 as a clean
        # pass with NO reason at all, so a crash reads as an approval nobody
        # gave. scope_check gained a hand-written regex translator and two env
        # contracts this round, so "the handler crashed" is not hypothetical.
        import sys as _sys
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            crasher = repo / "crasher.py"
            crasher.write_text(
                "import sys\n"
                f"sys.path.insert(0, r'{safety._handler(_cfg(repo), 'x').parent.parent}')\n"
                "from lib.common import run_handler\n"
                "def main():\n"
                "    raise RuntimeError('boom')\n"
                "run_handler(main, hook_name='crasher')\n",
                encoding="utf-8")
            payload = json.dumps({"tool_name": "Write",
                                  "tool_input": {"file_path": str(repo / "a.py"),
                                                 "content": "x\n"},
                                  "cwd": str(repo)})

            def _run(fails_closed):
                env = dict(os.environ)
                env.pop("CLAUDE_HOOK_FAILS_CLOSED", None)
                if fails_closed:
                    env["CLAUDE_HOOK_FAILS_CLOSED"] = "1"
                return subprocess.run([_sys.executable, str(crasher)], input=payload,
                                      capture_output=True, encoding="utf-8",
                                      errors="replace", env=env, timeout=30)

            closed = _run(True)
            self.assertEqual(closed.returncode, 2, closed.stderr)
            self.assertIn("failing closed", closed.stderr)
            self.assertEqual(_run(False).returncode, 0)  # interactive unchanged

    def test_handler_that_cannot_launch_fails_closed(self):
        # README promises "missing OR cannot launch also fails the cycle"; only
        # the missing half was tested, because handler.is_file() catches it
        # first. This is the branch the 30s subprocess timeout lands on.
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            (repo / bus.HANDOFF).write_text("# H\n```scope\nallowed.py\n```\n",
                                            encoding="utf-8")
            real = safety._run_handler
            safety._run_handler = lambda h, p, e: (-1, "simulated launch failure")
            try:
                res = safety.scan([Change(path="allowed.py", content="x\n")],
                                  _cfg(repo, net_enforce=True))
            finally:
                safety._run_handler = real
            self.assertTrue(res.blocked, res.reasons)
            self.assertTrue(any("reached no verdict" in r for r in res.reasons),
                            res.reasons)

    def test_always_block_is_anchored_on_the_live_install(self):
        # The layer is unconditional, dryrun-exempt and fence-proof, so WHERE it
        # is anchored decides which tree becomes undispatchable. Anchoring it on
        # the handler's own directory pointed it at <repo>/assets/claude whenever
        # orchestrate.py runs from a checkout — which would hard-block a Builder
        # from editing the harness's own hooks, with no escape but disabling the
        # hook. Move HOME to prove the anchor follows the install, not the file.
        import sys as _sys
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            fake_home = repo / "home"
            live = fake_home / ".claude"
            (live / "hooks" / "handlers").mkdir(parents=True)
            handler = safety._handler(_cfg(repo), "scope_check")

            def _run(target: Path, fence: str):
                env = dict(os.environ)
                env["CLAUDE_SCOPE_WHITELIST_MODE"] = "enforce"
                env["DINNER_HARNESS_HOME"] = str(repo)
                env["CLAUDE_SCOPE_FENCE"] = fence
                env["USERPROFILE"] = str(fake_home)
                env["HOME"] = str(fake_home)
                payload = json.dumps({
                    "tool_name": "Write",
                    "tool_input": {"file_path": str(target), "content": "x\n"},
                    "cwd": str(repo)})
                return subprocess.run([_sys.executable, str(handler)], input=payload,
                                      capture_output=True, encoding="utf-8",
                                      errors="replace", env=env, timeout=30)

            # Inside the live install: blocked even though the fence names it.
            blocked = _run(live / "hooks" / "handlers" / "evil.py",
                           str(live / "hooks" / "handlers" / "evil.py").replace("\\", "/"))
            self.assertEqual(blocked.returncode, 2, blocked.stderr)
            self.assertIn("always-block", blocked.stderr)
            # The same shaped path in the WORK repo is the fence's business.
            ok = _run(repo / "hooks" / "handlers" / "x.py", "hooks/")
            self.assertEqual(ok.returncode, 0, ok.stderr)

    def test_named_handoff_with_no_fence_fails_closed(self):
        # Fail-open covers the UNCONFIGURED case (a session predating ADR-0005).
        # When a caller explicitly names the handoff, a fence it cannot find is
        # a broken policy source, and allowing everything is the worst answer.
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)  # no handoff on disk at all
            cfg = _cfg(repo, net_enforce=True, handoff_name="HANDOFF_DELEGATE.md")
            res = safety.scan([Change(path="anything.py", content="x\n")], cfg)
            self.assertTrue(res.blocked, res.reasons)

    def test_non_cp949_content_reaches_the_handler_intact(self):
        # The UTF-8 pinning, tested with a character the locale codec CANNOT
        # represent. Korean round-trips through cp949 unchanged, so a Hangul
        # fixture proved nothing about the pinning on this box.
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            (repo / bus.HANDOFF).write_text("# H\n```scope\n許可🚀.md\n```\n",
                                            encoding="utf-8")
            cfg = _cfg(repo, net_enforce=True)
            key = "AKIA" + "IOSFODNN7EXAMPLE"
            leaked = safety.scan(
                [Change(path="許可🚀.md", content=f"日本語 🚀 key={key}\n")], cfg)
            self.assertTrue(leaked.blocked, leaked.reasons)
            self.assertTrue(any("secret_scan" in r for r in leaked.reasons),
                            leaked.reasons)
            ok = safety.scan([Change(path="許可🚀.md", content="日本語 🚀\n")], cfg)
            self.assertFalse(ok.blocked, ok.reasons)
            # The reason the operator reads must name the real path. Without the
            # child-side UTF-8 env this comes back as `����\U0001f680.md` — the
            # message survives, the path in it does not.
            #
            # The ambient environment must be cleared for this to test the CODE:
            # a terminal that exports PYTHONIOENCODING (this one does) already
            # makes the child answer in UTF-8, which masks the question entirely.
            # `scan` sets both vars itself, so clearing them here leaves its own
            # assignment as the only source.
            saved = {k: os.environ.pop(k, None)
                     for k in ("PYTHONUTF8", "PYTHONIOENCODING")}
            try:
                blocked = safety.scan([Change(path="禁止🚀.md", content="x\n")], cfg)
            finally:
                for k, v in saved.items():
                    if v is not None:
                        os.environ[k] = v
            self.assertTrue(blocked.blocked, blocked.reasons)
            self._assert_handler_said(blocked.reasons, "禁止🚀.md")

    def test_scope_entries_ignores_blank_and_comment_lines(self):
        # The controller's "is there a fence?" question and the handler's "does
        # this path match?" answer must not drift apart, so both read the fence
        # through this one parser. A fence of nothing but comments bounds
        # nothing — the same hole as no fence.
        self.assertEqual(bus.scope_entries("```scope\na.py\n\n# note\nb/\n```\n"),
                         ["a.py", "b/"])
        self.assertEqual(bus.scope_entries("```scope\n# TODO fill in\n```\n"), [])
        self.assertEqual(bus.scope_entries("# H\nno fence at all\n"), [])


class TestEndToEndMock(unittest.TestCase):
    def test_low_cycle_completes(self):
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
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


class _WritingArchitect(Backend):
    """An Architect that authors a file on a chosen turn, as its own role tells it to.

    ROLE_ARCHITECT step 8 mandates an ADR before dispatching at step 9, so this
    is the ordinary shape of an Architect turn, not an adversarial one.
    """

    name = "writing-architect"

    def __init__(self, repo: Path, scenario: Scenario, on_turn: int,
                 path: str, content: str):
        self._repo = repo
        self._sc = scenario
        self._on_turn = on_turn  # 1 = design, 2 = review
        self._path = path
        self._content = content
        self.turns = 0

    def invoke(self, role: str, prompt: str, cfg: Config) -> Turn:
        self.turns += 1
        if self.turns == self._on_turn:
            p = self._repo / self._path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(self._content, encoding="utf-8")
        if "REVIEW" in prompt.upper():
            return Turn(text=self._sc.reviews[0])
        return Turn(text=self._sc.handoffs[0])


class TestArchitectTurnIsScanned(unittest.TestCase):
    """Round 10: the Architect's own output reached neither net layer.

    `_build_and_gate` takes its baseline AFTER architect.invoke, so everything
    the Architect wrote was pre-existing dirt by construction and dropped out of
    every delta; ARCHITECT_REVIEW runs after the net entirely. `--architect
    codex` is documented, and a headless Codex Architect fires no Claude hooks —
    the same asymmetry the net exists for. Before the delta rework the whole-tree
    sweep covered this.
    """

    _KEY = "AKIA" + "IOSFODNN7EXAMPLE"

    def _run_with(self, repo: Path, on_turn: int, content: str, builder):
        sc = default_low_scenario("demo")
        arch = _WritingArchitect(repo, sc, on_turn, "docs/architecture/ADR-9.md", content)
        cfg = _cfg(repo, net_enforce=True, max_cycles=1, confirm_handoff=False)
        out = Orchestrator(cfg, arch, builder, AutoApprove(),
                           log=lambda m: None).run()
        return out, arch

    def _repo(self, d):
        repo = Path(d)
        _git_init(repo)
        (repo / "seed.md").write_text("seed\n", encoding="utf-8")
        _git_commit_all(repo)
        return repo

    def test_key_in_the_design_turns_adr_blocks_before_the_builder_runs(self):
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = self._repo(d)
            builder = MockBackend(default_low_scenario("demo"))
            out, _ = self._run_with(repo, 1, f"# ADR\nkey = '{self._KEY}'\n", builder)
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertIn("architect design", out.reason)
            # Knowable before dispatch — it must not cost a builder turn.
            self.assertEqual(builder._cycle[ROLE_BUILDER], 0)

    def test_key_in_the_review_turn_blocks(self):
        # The review turn runs AFTER the net, so its writes previously reached
        # neither layer this cycle and became baseline dirt in the next.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = self._repo(d)
            builder = MockBackend(default_low_scenario("demo"))
            out, arch = self._run_with(repo, 2, f"# ADR\nkey = '{self._KEY}'\n", builder)
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertIn("architect review", out.reason)
            self.assertEqual(arch.turns, 2)  # it really did reach the review turn

    def test_pre_existing_dirt_is_not_charged_to_the_architect(self):
        # The delta's whole premise, applied to this turn too: a key that was
        # ALREADY sitting in the tree when the cycle started is not something
        # this Architect turn wrote. Charging it would resurrect the failure the
        # delta rework exists to fix — a dispatch blocked on somebody else's
        # file, whose only workaround is to stop using the tool.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = self._repo(d)
            (repo / "old_scratch.py").write_text(f"k = '{self._KEY}'\n", encoding="utf-8")
            builder = MockBackend(default_low_scenario("demo"))
            out, _ = self._run_with(repo, 1, "# ADR-9\nA design record.\n", builder)
            self.assertEqual(out.status, DONE, out.reason)

    def test_an_ordinary_adr_is_not_blocked_by_the_builders_fence(self):
        # The other half, and the reason this is secret-only: the ADR is out of
        # every ```scope``` fence by design (the fence bounds the BUILDER). If
        # the Architect's delta were judged against it, step 8 of its own
        # protocol would fail every cycle.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = self._repo(d)
            builder = MockBackend(default_low_scenario("demo"))
            out, _ = self._run_with(repo, 1, "# ADR-9\nA design record.\n", builder)
            self.assertEqual(out.status, DONE, out.reason)
            self.assertTrue((repo / "docs" / "architecture" / "ADR-9.md").is_file())


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
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            _git_init(Path(d))
            cfg = _cfg(Path(d))
            mock = MockBackend(_high_scenario())
            out = Orchestrator(cfg, mock, mock, AutoApprove(), log=lambda m: None).run()
            self.assertEqual(out.status, DONE, out.reason)

    def test_high_decline_is_held(self):
        # confirm_handoff False isolates the HIGH end sign-off as the only gate.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            _git_init(Path(d))
            cfg = _cfg(Path(d), confirm_handoff=False)
            mock = MockBackend(_high_scenario())
            out = Orchestrator(cfg, mock, mock, _RejectGate(), log=lambda m: None).run()
            self.assertEqual(out.status, HELD, out.reason)


class TestBuildFromHandoff(unittest.TestCase):
    """run_from_handoff: single-shot Builder pass from an on-disk HANDOFF.md
    (the interactive Architect's auto-dispatch path). No headless architect."""

    def test_built_from_existing_handoff(self):
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            # default_low_scenario's handoff carries a `gate 1: LOW` tiers fence.
            sc = default_low_scenario("demo")
            (repo / bus.HANDOFF).write_text(sc.handoffs[0], encoding="utf-8")
            cfg = _cfg(repo)
            mock = MockBackend(sc)
            out = Orchestrator(cfg, mock, mock, AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BUILT, out.reason)
            self.assertTrue((repo / bus.RESULT).is_file())

    def test_receipt_records_only_metadata_after_a_real_git_build(self):
        # Receipt output must live outside the target repo and must not copy the
        # handoff's text. The Builder uses the real git delta path, not an
        # injected Turn.changeset, so the same safety boundary production uses
        # passes before a BUILT receipt is emitted.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            repo = root / "work"
            audit_dir = root / "audit"
            repo.mkdir()
            _git_init(repo)
            nonce = "receipt-must-not-store-this-handoff-content"
            handoff = (
                f"# {nonce}\n```tiers\ngate 1: LOW\n```\n"
                "```scope\nallowed.py\nRESULT.md\n```\n"
            )
            (repo / bus.HANDOFF).write_text(handoff, encoding="utf-8")
            backend = _TamperingBackend(repo, "allowed.py", "VALUE = 1\n")
            out = Orchestrator(
                _cfg(repo, audit_dir=audit_dir), backend, backend, AutoApprove(),
                log=lambda m: None,
            ).run_from_handoff()
            self.assertEqual(out.status, BUILT, out.reason)
            self.assertEqual(out.receipt_path, audit_dir / "build-audit.jsonl")
            records = [json.loads(line) for line in out.receipt_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([record["status"] for record in records], ["attempted", "built"])
            self.assertEqual(records[-1]["outcome"], BUILT)
            self.assertEqual(records[-1]["reason_code"], "built_low")
            serialized = out.receipt_path.read_text(encoding="utf-8")
            self.assertNotIn(nonce, serialized)
            self.assertNotIn(str(repo), serialized)
            self.assertIn("handoff_sha256", serialized)

    def test_vendor_error_text_never_enters_the_receipt(self):
        # Backend stderr is vendor-controlled and can echo task content. The
        # audit may classify the failure, but must not retain that raw string.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            repo = root / "work"
            audit_dir = root / "audit"
            repo.mkdir()
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n"
                "```scope\nallowed.py\nRESULT.md\n```\n",
                encoding="utf-8",
            )
            leaked = "vendor-stderr-must-not-enter-audit"

            class _Errors(Backend):
                name = "error"

                def invoke(self, role, prompt, cfg):
                    return Turn(error=leaked)

            backend = _Errors()
            out = Orchestrator(
                _cfg(repo, audit_dir=audit_dir), backend, backend, AutoApprove(),
                log=lambda m: None,
            ).run_from_handoff()
            self.assertEqual(out.reason, f"builder error: {leaked}")
            serialized = out.receipt_path.read_text(encoding="utf-8")
            self.assertNotIn(leaked, serialized)
            self.assertIn('"reason_code":"builder_error"', serialized)

    def test_controller_exception_still_closes_the_audit_pair_without_text(self):
        # Backend exceptions may include a prompt or vendor output. The caller
        # keeps the original exception, but audit needs a fixed terminal record
        # rather than an orphaned `attempted` event or leaked exception text.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            repo = root / "work"
            audit_dir = root / "audit"
            repo.mkdir()
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n"
                "```scope\nallowed.py\nRESULT.md\n```\n",
                encoding="utf-8",
            )
            leaked = "backend-exception-must-not-enter-audit"

            class _Explodes(Backend):
                name = "explodes"

                def invoke(self, role, prompt, cfg):
                    raise RuntimeError(leaked)

            backend = _Explodes()
            with self.assertRaisesRegex(RuntimeError, leaked):
                Orchestrator(
                    _cfg(repo, audit_dir=audit_dir), backend, backend, AutoApprove(),
                    log=lambda m: None,
                ).run_from_handoff()
            serialized = (audit_dir / "build-audit.jsonl").read_text(encoding="utf-8")
            records = [json.loads(line) for line in serialized.splitlines()]
            self.assertEqual([record["status"] for record in records], ["attempted", "blocked"])
            self.assertEqual(records[-1]["outcome"], "ERROR")
            self.assertEqual(records[-1]["reason_code"], "controller_error")
            self.assertNotIn(leaked, serialized)

    def test_cli_refuses_an_audit_directory_inside_the_real_git_worktree(self):
        # A terminal receipt written under --repo lands after the net snapshot,
        # so it would be target dirt that this dispatch never judged.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "work"
            repo.mkdir()
            _git_init(repo)
            (repo / bus.HANDOFF).write_text("# H\n", encoding="utf-8")
            with mock.patch("sys.stdout", new_callable=io.StringIO), \
                 mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
                status = orchestrate.main([
                    "build", "--repo", str(repo), "--backend", "mock",
                    "--audit-dir", str(repo / "audit"),
                ])
            self.assertEqual(status, 2)
            self.assertIn("audit_dir must be outside repo", stderr.getvalue())

    def test_safety_block_never_receives_a_built_receipt(self):
        # Outcome-only assertions are insufficient: a receipt mutation could
        # still falsely claim success while the controller correctly BLOCKs.
        # Drive the safety net through an actual git worktree delta.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            repo = root / "work"
            audit_dir = root / "audit"
            repo.mkdir()
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n"
                "```scope\nallowed.py\nRESULT.md\n```\n",
                encoding="utf-8",
            )
            backend = _TamperingBackend(repo, "forbidden.py", "VALUE = 1\n")
            out = Orchestrator(
                _cfg(repo, audit_dir=audit_dir), backend, backend, AutoApprove(),
                log=lambda m: None,
            ).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertEqual(out.reason, "safety net blocked the changeset")
            records = [json.loads(line) for line in out.receipt_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(records[-1]["status"], "blocked")
            self.assertNotEqual(records[-1]["status"], "built")

    def test_timeout_receipt_is_not_a_generic_block(self):
        # Timeout has a distinct operational remedy (inspect the preserved
        # worktree), so collapsing it to an undifferentiated block loses the
        # evidence the CLI just gained from --timeout-s.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            repo = root / "work"
            audit_dir = root / "audit"
            repo.mkdir()
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n"
                "```scope\nallowed.py\nRESULT.md\n```\n",
                encoding="utf-8",
            )

            class _TimesOut(Backend):
                name = "timeout"

                def invoke(self, role, prompt, cfg):
                    return Turn(error="vendor turn timed out after 0.01s")

            backend = _TimesOut()
            out = Orchestrator(
                _cfg(repo, audit_dir=audit_dir), backend, backend, AutoApprove(),
                log=lambda m: None,
            ).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertEqual(out.reason, "builder error: vendor turn timed out after 0.01s")
            records = [json.loads(line) for line in out.receipt_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(records[-1]["status"], "timeout")

    def test_second_builder_bail_blocks_and_is_audited(self):
        # The old loop retried once but then called the final outcome BUILT even
        # when the second Builder also produced no implementation. That makes a
        # receipt only as trustworthy as the failure it is supposed to expose.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            repo = root / "work"
            audit_dir = root / "audit"
            repo.mkdir()
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n"
                "```scope\nallowed.py\nRESULT.md\n```\n",
                encoding="utf-8",
            )

            class _Bails(Backend):
                name = "bails"

                def invoke(self, role, prompt, cfg):
                    return Turn(text="```verdicts\ngate 1: status=blocked tier=LOW panel=BLOCK\n```\n")

            backend = _Bails()
            out = Orchestrator(
                _cfg(repo, audit_dir=audit_dir), backend, backend, AutoApprove(),
                log=lambda m: None,
            ).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertEqual(out.reason, "builder bailed with no implementation after 2 attempt(s)")
            records = [json.loads(line) for line in out.receipt_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(records[-1]["status"], "builder_bailed")

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
            _git_init(repo)
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
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(handoff, encoding="utf-8")
            cfg = _cfg(repo)
            mock = MockBackend(sc)
            out = Orchestrator(cfg, mock, mock, AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BUILT, out.reason)
            self.assertEqual(out.cycles, 1)  # no retry
            self.assertNotIn("SECOND ATTEMPT", (repo / bus.RESULT).read_text(encoding="utf-8"))

    def test_real_git_dispatch_does_not_block_on_its_own_handoff(self):
        # THE regression, driven the way production drives it. Real backends
        # leave Turn.changeset None (vendors.py), so the controller reads the
        # tree via git — and the handoff Claude writes right before dispatch is
        # untracked, so git reports it. The fence recipe lists files to EDIT,
        # never the spec itself, so judging bus artifacts against the fence made
        # every dispatch block on its own handoff. Injected-changeset tests hide
        # this completely; only a real repo shows it.
        #
        # The work lands in a NEW directory on purpose: plain `git status
        # --porcelain` collapses that to "src/", which matches no fence entry.
        # This test pins both the bus exemption and the -uall listing.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            handoff = ("# H\n```tiers\ngate 1: LOW\n```\n"
                       "```scope\nsrc/feature.py\nRESULT.md\n```\n")
            (repo / "HANDOFF_DELEGATE.md").write_text(handoff, encoding="utf-8")
            cfg = _cfg(repo, net_enforce=True, handoff_name="HANDOFF_DELEGATE.md",
                       backend="mock")
            # The Builder must do the work DURING its turn. Creating src/ before
            # dispatch makes it pre-existing dirt, present in both snapshots and
            # therefore absent from the delta — the earlier cut of this test did
            # exactly that, so scope_check was never invoked on anything and
            # removing -uall broke nothing the suite could see.
            backend = _TamperingBackend(repo, "src/feature.py", "VALUE = 1\n")
            seen = _ScanSpy()
            with seen.patch():
                out = Orchestrator(cfg, backend, backend, AutoApprove(),
                                   log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BUILT, out.reason)
            self.assertIn(("scope_check", "src/feature.py"), seen.calls,
                          f"scope_check never judged the new file: {seen.calls}")

    def test_secret_in_an_exempt_bus_file_is_still_caught(self):
        # Bus artifacts are exempt from SCOPE, never from SECRETS. A key pasted
        # into one is as leaked as one pasted into source.
        #
        # An earlier cut of this test asserted only `res.blocked` on a path that
        # was NOT scope-exempt, so scope_check blocked it and the assertion held
        # even with secret_scan removed from the handler list entirely. Grant
        # the exemption the test is about, and name the layer in the assertion.
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            key = "AKIA" + "IOSFODNN7EXAMPLE"
            (repo / bus.HANDOFF).write_text(
                "# H\n```scope\nfeat.py\n```\n", encoding="utf-8")
            cfg = _cfg(repo, net_enforce=True)
            leaked = f"# RESULT\nused {key}\n"
            res = safety.scan([Change(path=bus.RESULT, content=leaked)], cfg,
                              scope_exempt={bus.RESULT})
            self.assertTrue(res.blocked, res.reasons)
            self.assertTrue(any("secret_scan" in r for r in res.reasons), res.reasons)
            # ...and the exemption really is in force: clean content passes even
            # though RESULT.md is nowhere in the fence.
            ok = safety.scan([Change(path=bus.RESULT, content="# RESULT\nfine\n")], cfg,
                             scope_exempt={bus.RESULT})
            self.assertFalse(ok.blocked, ok.reasons)

    def test_builder_editing_the_handoff_blocks(self):
        # scope_check re-reads the fence from disk at handler time, so a Builder
        # that edits the fence would be rewriting the rule it is judged by. The
        # controller still holds what it dispatched, and refuses the drift.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            handoff = ("# H\n```tiers\ngate 1: LOW\n```\n"
                       "```scope\nfeat.py\nRESULT.md\n```\n")
            (repo / bus.HANDOFF).write_text(handoff, encoding="utf-8")
            widened = handoff.replace("feat.py", "feat.py\n*")
            backend = _TamperingBackend(repo, bus.HANDOFF, widened)
            out = Orchestrator(_cfg(repo, net_enforce=True), backend, backend,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertIn("altered or removed", out.reason)

    def test_builder_deleting_the_handoff_blocks(self):
        # Erasing the fence is the strongest edit of all: with the file gone the
        # handler finds nothing and fails OPEN, so the whole scope layer lifts.
        # An earlier cut guarded the drift check with `if on_disk.strip()`, which
        # skipped exactly this case — a Builder could delete the handoff and then
        # write anywhere, and the run still came back BUILT.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nallowed.py\nRESULT.md\n```\n",
                encoding="utf-8",
            )
            backend = _TamperingBackend(repo, bus.HANDOFF, None, also_write="forbidden.py")
            out = Orchestrator(_cfg(repo, net_enforce=True), backend, backend,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertIn("altered or removed", out.reason)

    def test_builder_writing_an_unrelated_bus_file_is_not_exempt(self):
        # Bus files earn the scope exemption by being untouched. In the delegate
        # lane HANDOFF.md is not the dispatched spec — but it IS the fence an
        # interactive Claude session later reads, so a Builder must not get a
        # free write to it just because the name is on the bus list.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / "HANDOFF_DELEGATE.md").write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nallowed.py\nRESULT.md\n```\n",
                encoding="utf-8",
            )
            backend = _TamperingBackend(repo, bus.HANDOFF, "```scope\n*\n```\n")
            cfg = _cfg(repo, net_enforce=True, handoff_name="HANDOFF_DELEGATE.md")
            out = Orchestrator(cfg, backend, backend, AutoApprove(),
                               log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)

    def test_undecodable_handoff_blocks_instead_of_crashing(self):
        # The tamper read lands on bytes the Builder just wrote. On a Korean
        # Windows box a naive text write is cp949, and Bus.read decodes UTF-8 —
        # that raised straight out of the CLI as a traceback. A file we cannot
        # read is a file we cannot vouch for: block, cleanly.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nallowed.py\nRESULT.md\n```\n",
                encoding="utf-8",
            )

            class _Cp949Backend(Backend):
                name = "cp949"

                def invoke(self, role, prompt, cfg):
                    (repo / bus.HANDOFF).write_bytes("한글 스코프\n".encode("cp949"))
                    return Turn(text=_CLEAN_VERDICT)

            backend = _Cp949Backend()
            out = Orchestrator(_cfg(repo, net_enforce=True), backend, backend,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertIn("altered or removed", out.reason)

    def test_undecodable_handoff_on_entry_blocks(self):
        # The ENTRY read, not the tamper read. run_from_handoff opens the
        # handoff before anything else runs, and the existing cp949 test writes
        # its bad bytes from inside the backend — i.e. it only ever covered the
        # post-turn comparison, so the entry guard could be reverted with the
        # suite still green. A Notepad "ANSI" save is how this arrives.
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            (repo / bus.HANDOFF).write_bytes(
                "# 한글 핸드오프\n```scope\n허용.md\n```\n".encode("cp949"))
            mock = MockBackend(default_low_scenario("demo"))
            out = Orchestrator(_cfg(repo, net_enforce=True), mock, mock,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertIn("cannot read", out.reason)
            self.assertEqual(mock._cycle[ROLE_BUILDER], 0)  # never dispatched

    def test_oversized_changeset_skips_the_scan_in_dryrun(self):
        # dryrun promises not to BLOCK. It does not promise to spend minutes on
        # 2*N handler subprocesses — that is the stall the ceiling exists to
        # prevent, and the ceiling only short-circuited in enforce.
        #
        # Asserting BUILT here proves NOTHING: in dryrun the handlers only warn,
        # so the run ends BUILT whether the scan was skipped or ground through
        # every file. (An earlier cut of this test did exactly that and passed
        # with the fix reverted — 86s instead of instant.) Spy on the call.
        # Driven on the GIT path, per the ADR's testing rule: injecting
        # Turn.changeset is the one shape production never takes, and -uall is
        # precisely what makes the ceiling necessary, so the injected version
        # exercised none of the mechanism it claimed to cover.
        if not _git_available():
            self.skipTest("git not on PATH")
        from orchestrator import controller as ctl
        from orchestrator.controller import _MAX_CHANGESET
        handoff = "# H\n```tiers\ngate 1: LOW\n```\n```scope\nsrc/feature.py\n```\n"
        seen = []
        real_scan = ctl.safety.scan

        def _spy(changes, cfg, **kw):
            seen.append(sorted(c.path for c in changes))
            return real_scan(changes, cfg, **kw)

        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(handoff, encoding="utf-8")
            _write_n_files(repo, _MAX_CHANGESET + 1)
            mock = MockBackend(default_low_scenario("demo"))
            mock.scenario.changesets = [None]
            ctl.safety.scan = _spy
            try:
                out = Orchestrator(_cfg(repo, net_enforce=False), mock, mock,
                                   AutoApprove(), log=lambda m: None).run_from_handoff()
            finally:
                ctl.safety.scan = real_scan
            self.assertEqual(out.status, BUILT, out.reason)
            # Only the two files the CONTROLLER writes, which are secret-scanned
            # every cycle regardless — the oversized tree must not reach the net.
            # Asserting the paths rather than the count: a length check cannot
            # tell which files arrived, and that blindness is what let a
            # content-free handoff append pass for the real thing.
            self.assertEqual(seen, [[bus.HANDOFF, bus.RESULT]],
                             "the oversized changeset must not reach the net")

    def test_preexisting_dirt_is_not_charged_to_the_builder(self):
        # The net judges the BUILDER'S delta, not the whole dirty tree. The
        # Architect's own protocol writes an ADR (step 8) before dispatching
        # (step 9): untracked, and rightly absent from the Builder's fence.
        # Judging the full `git status` blocked that dispatch after a full
        # builder turn, and the only workaround was widening the fence — i.e.
        # handing the Builder writes it should not have.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nsrc/feature.py\nRESULT.md\n```\n",
                encoding="utf-8")
            adr = repo / "docs" / "architecture"
            adr.mkdir(parents=True)
            (adr / "ADR-0007.md").write_text("# ADR\n", encoding="utf-8")  # pre-existing dirt
            (repo / "src").mkdir()
            (repo / "src" / "feature.py").write_text("VALUE = 1\n", encoding="utf-8")
            sc = default_low_scenario("demo")
            sc.changesets = [None]  # force the git path
            mock = MockBackend(sc)
            out = Orchestrator(_cfg(repo, net_enforce=True), mock, mock,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BUILT, out.reason)

    def test_builder_writing_outside_the_fence_still_blocks(self):
        # The delta must not become a blanket pass: a file the Builder actually
        # creates outside the fence is exactly what the net is for.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nallowed.py\nRESULT.md\n```\n",
                encoding="utf-8")
            (repo / "stale.txt").write_text("was already here\n", encoding="utf-8")

            class _WritesOutside(Backend):
                name = "outside"

                def invoke(self, role, prompt, cfg):
                    (repo / "forbidden.py").write_text("pwned = True\n", encoding="utf-8")
                    return Turn(text=_CLEAN_VERDICT)

            backend = _WritesOutside()
            out = Orchestrator(_cfg(repo, net_enforce=True), backend, backend,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertIn("safety net", out.reason)

    def test_builder_deleting_an_out_of_fence_file_blocks(self):
        # The delegate DOCUMENT lane states its core guarantee as "keep the
        # source out of the fence and scope_check hard-blocks any edit to it".
        # collect_changeset skipped deletions outright, so `rm original.md` was
        # not an edit the net could see — the most destructive counter-example
        # to that guarantee walked straight through and the run reported BUILT.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nderived.md\nRESULT.md\n```\n",
                encoding="utf-8")
            (repo / "original.md").write_text("the source document\n", encoding="utf-8")
            _git_commit_all(repo)
            backend = _TamperingBackend(repo, "original.md", None)  # deletes it
            out = Orchestrator(_cfg(repo, net_enforce=True), backend, backend,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertIn("safety net", out.reason)

    def test_builder_deleting_an_in_fence_file_is_allowed(self):
        # Judging deletions must not degrade into "no Builder may ever delete".
        # A path the operator whitelisted is a path the Builder may remove.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nscratch.md\nRESULT.md\n```\n",
                encoding="utf-8")
            (repo / "scratch.md").write_text("delete me\n", encoding="utf-8")
            _git_commit_all(repo)
            backend = _TamperingBackend(repo, "scratch.md", None)
            out = Orchestrator(_cfg(repo, net_enforce=True), backend, backend,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BUILT, out.reason)

    def test_preexisting_deletion_is_not_charged_to_the_builder(self):
        # Symmetry with pre-existing dirt: a file the operator removed before
        # dispatch sits in `git status` for the whole turn and is not the
        # Builder's work. Both snapshots see it, so the delta drops it — the
        # same mechanism, no second special case.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nallowed.py\nRESULT.md\n```\n",
                encoding="utf-8")
            (repo / "obsolete.md").write_text("removed before dispatch\n", encoding="utf-8")
            _git_commit_all(repo)
            (repo / "obsolete.md").unlink()
            sc = default_low_scenario("demo")
            sc.changesets = [None]  # force the git path
            mock = MockBackend(sc)
            out = Orchestrator(_cfg(repo, net_enforce=True), mock, mock,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BUILT, out.reason)

    def test_non_ascii_paths_reach_the_net_unmangled(self):
        # git C-quotes non-ASCII paths by default ("\352\262\275...md"). That
        # spelling resolves to no file, so the content read comes back EMPTY —
        # secret_scan gets nothing to scan — while the fence is asked about the
        # escaped name and rejects a path the operator did whitelist. The
        # document lane's files are routinely Korean-named, so this is its
        # ordinary case, not an edge.
        if not _git_available():
            self.skipTest("git not on PATH")
        handoff = ("# H\n```tiers\ngate 1: LOW\n```\n"
                   "```scope\n경력기술서.md\nRESULT.md\n```\n")

        def _run(body: str):
            with tempfile.TemporaryDirectory() as d:
                repo = Path(d)
                _git_init(repo)
                (repo / bus.HANDOFF).write_text(handoff, encoding="utf-8")
                backend = _TamperingBackend(repo, "경력기술서.md", body)
                return Orchestrator(_cfg(repo, net_enforce=True), backend, backend,
                                    AutoApprove(), log=lambda m: None).run_from_handoff()

        # Whitelisted and clean: the fence must recognise the real path.
        ok = _run("# 경력기술서\n2020-2026 게임 클라이언트 프로그래머\n")
        self.assertEqual(ok.status, BUILT, ok.reason)
        # Same path, secret inside: only reachable if the content was READ, so
        # this is what pins the quoting fix rather than a lucky fence miss.
        key = "AKIA" + "IOSFODNN7EXAMPLE"
        leaked = _run(f"# 경력기술서\naws_key = {key}\n")
        self.assertEqual(leaked.status, BLOCKED, leaked.reason)
        self.assertIn("safety net", leaked.reason)

    def test_oversized_changeset_fails_closed(self):
        # -uall lists untracked files one by one, so a target repo with a thin
        # .gitignore can hand the net thousands of paths at two subprocesses
        # each. A net that takes minutes gets switched off; refuse instead.
        if not _git_available():
            self.skipTest("git not on PATH")
        from orchestrator.controller import _MAX_CHANGESET
        handoff = "# H\n```tiers\ngate 1: LOW\n```\n```scope\nsrc/feature.py\n```\n"
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(handoff, encoding="utf-8")
            _write_n_files(repo, _MAX_CHANGESET + 1)
            mock = MockBackend(default_low_scenario("demo"))
            mock.scenario.changesets = [None]
            out = Orchestrator(_cfg(repo, net_enforce=True), mock, mock,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertIn("too large", out.reason)
            # Refused BEFORE the turn: the tree is already past what the net can
            # vet, and cfg.timeout_s is 1800s.
            self.assertEqual(mock._cycle[ROLE_BUILDER], 0)

    def test_untracked_out_of_fence_deletion_blocks(self):
        # An UNTRACKED file leaves no ' D' entry when deleted — it vanishes from
        # `git status` entirely. A delta built from the `after` snapshot alone
        # therefore never constructs a Change for it, and the fence never sees
        # it. That made the document lane's whole promise ("the source is out of
        # the fence, so it cannot be touched") false for exactly the case with
        # no git object behind it: unrecoverable, and reported BUILT.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nderived.md\nRESULT.md\n```\n",
                encoding="utf-8")
            (repo / "original.md").write_text("source doc\n", encoding="utf-8")  # untracked
            backend = _TamperingBackend(repo, "original.md", None)
            out = Orchestrator(_cfg(repo, net_enforce=True), backend, backend,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertIn("safety net", out.reason)

    def test_untracked_out_of_fence_move_blocks(self):
        # Same hole, worn as a rename: move the source onto an IN-fence name and
        # the target looks legitimate while the source silently disappears.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nderived.md\nRESULT.md\n```\n",
                encoding="utf-8")
            (repo / "original.md").write_text("source doc\n", encoding="utf-8")

            class _Moves(Backend):
                name = "moves"

                def invoke(self, role, prompt, cfg):
                    (repo / "original.md").rename(repo / "derived.md")
                    return Turn(text=_CLEAN_VERDICT)

            backend = _Moves()
            out = Orchestrator(_cfg(repo, net_enforce=True), backend, backend,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)

    def test_staged_rename_judges_the_source_too(self):
        # Under -z the rename SOURCE is the next NUL field, not an " -> " suffix.
        # Taking only the target let a Builder move an out-of-fence file away
        # with the run reporting BUILT. No test in the suite performed a rename.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nderived.md\nRESULT.md\n```\n",
                encoding="utf-8")
            (repo / "original.md").write_text("source doc\n", encoding="utf-8")
            _git_commit_all(repo)

            class _GitMv(Backend):
                name = "gitmv"

                def invoke(self, role, prompt, cfg):
                    subprocess.run(["git", "-C", str(repo), "mv",
                                    "original.md", "derived.md"],
                                   check=True, capture_output=True, text=True)
                    return Turn(text=_CLEAN_VERDICT)

            backend = _GitMv()
            seen = _ScanSpy()
            with seen.patch():
                out = Orchestrator(_cfg(repo, net_enforce=True), backend, backend,
                                   AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertIn("safety net", out.reason)
            # Asserting BLOCKED alone cannot tell "the source was judged" from
            # "the -z reader desynced": with the look-ahead disabled the source
            # field is re-parsed as an entry and yields the truncated path
            # `ginal.md`, which is ALSO out of fence, so the run still blocks and
            # the test still passes while the real path went unexamined.
            self.assertIn(("scope_check", "original.md"), seen.calls,
                          f"the rename source was never judged: {seen.calls}")

    def test_builder_modifying_preexisting_dirty_file_blocks(self):
        # The delta's central discriminator, and it had no test: a file that is
        # ALREADY dirty before the turn, that the Builder then edits. It must be
        # charged (the content changed) even though its mere presence in
        # `git status` is not the Builder's doing.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nallowed.py\nRESULT.md\n```\n",
                encoding="utf-8")
            (repo / "notes.md").write_text("dirty before the turn\n", encoding="utf-8")
            backend = _TamperingBackend(repo, "notes.md", "edited by the builder\n")
            out = Orchestrator(_cfg(repo, net_enforce=True), backend, backend,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertIn("safety net", out.reason)

    def test_non_git_directory_fails_closed(self):
        # `git status` in a non-repository exits 128 with EMPTY stdout and
        # raises nothing, so a collector that only catches exceptions read
        # "clean tree" out of "there is no repository here" — the net ran zero
        # handlers and the run reported BUILT. delegate/SKILL.md sells the
        # opposite, and a resume folder is the case most likely not to be a repo.
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)  # deliberately NOT a git repo
            self.assertIsNone(collect_changeset(repo))
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nallowed.py\nRESULT.md\n```\n",
                encoding="utf-8")
            mock = MockBackend(default_low_scenario("demo"))
            out = Orchestrator(_cfg(repo, net_enforce=True), mock, mock,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)
            # Refused BEFORE the turn, and with git's own words. Letting this
            # fall through dispatched a headless Builder for up to 1800s into a
            # directory the net can never vet, then refused — and a block is a
            # refusal, not a rollback, so whatever it wrote would have stayed.
            self.assertEqual(mock._cycle[ROLE_BUILDER], 0)
            self.assertIn("not a git repository", out.reason)

    def test_git_failure_reports_the_fatal_line_not_the_warning(self):
        # An unreadable excludesFile makes git print
        #   warning: unable to access '<path>'
        #   fatal: cannot use <path> as an exclude file
        # Taking stderr's FIRST line hands the operator the symptom and drops
        # the cause. (`dubious ownership` leads with `fatal:`, which is why the
        # common case read fine and this went unnoticed.)
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            # A directory cannot be read as an exclude file.
            (repo / "not-a-file").mkdir()
            subprocess.run(["git", "-C", str(repo), "config", "core.excludesFile",
                            str(repo / "not-a-file")],
                           check=True, capture_output=True, text=True)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nallowed.py\nRESULT.md\n```\n",
                encoding="utf-8")
            mock = MockBackend(default_low_scenario("demo"))
            out = Orchestrator(_cfg(repo, net_enforce=True), mock, mock,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertIn("fatal:", out.reason)
            self.assertNotIn("warning:", out.reason)
            self.assertEqual(mock._cycle[ROLE_BUILDER], 0)

    def test_work_repo_below_the_git_root_still_vets_content(self):
        # `git status` reports paths relative to the REPOSITORY ROOT, not to the
        # -C directory. Resolving those against a work repo that sits in a
        # subdirectory found nothing: every content read came back "" so
        # secret_scan vetted an empty string and a key shipped, while
        # scope_check got a doubled path and false-blocked work that WAS in the
        # fence — pushing the operator to widen it.
        if not _git_available():
            self.skipTest("git not on PATH")
        fence = ("# H\n```tiers\ngate 1: LOW\n```\n"
                 "```scope\nderived.md\nRESULT.md\n```\n")
        key = "AKIA" + "IOSFODNN7EXAMPLE"

        def _run(body: str):
            with tempfile.TemporaryDirectory() as d:
                root = Path(d)
                _git_init(root)
                work = root / "docs" / "resume"
                work.mkdir(parents=True)
                (work / bus.HANDOFF).write_text(fence, encoding="utf-8")
                backend = _TamperingBackend(work, "derived.md", body)
                return Orchestrator(_cfg(work, net_enforce=True), backend, backend,
                                    AutoApprove(), log=lambda m: None).run_from_handoff()

        ok = _run("a clean derived document\n")
        self.assertEqual(ok.status, BUILT, ok.reason)          # no false block
        leaked = _run(f"key = {key}\n")
        self.assertEqual(leaked.status, BLOCKED, leaked.reason)  # content was read

    def test_result_is_scope_exempt_without_being_in_the_fence(self):
        # RESULT.md is the CONTROLLER's write, made after the snapshot, so it is
        # always in the delta. Every other git-path test lists it in its own
        # fence, which meant the fence — not the exemption — was admitting it,
        # and deleting the exemption broke nothing.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nallowed.py\n```\n",
                encoding="utf-8")
            backend = _TamperingBackend(repo, "allowed.py", "VALUE = 1\n")
            out = Orchestrator(_cfg(repo, net_enforce=True), backend, backend,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BUILT, out.reason)

    def test_builder_hiding_a_path_from_git_status_blocks(self):
        # The delta trusts `git status`, and the Builder can edit the witness:
        # .git/info/exclude and the assume-unchanged/skip-worktree index bits
        # each remove a path from BOTH snapshots, so the delta is empty for it
        # and the write is never judged. Neither lives in the working tree, so
        # neither appears in the listing it suppresses.
        if not _git_available():
            self.skipTest("git not on PATH")
        fence = ("# H\n```tiers\ngate 1: LOW\n```\n"
                 "```scope\nderived.md\nRESULT.md\n```\n")

        def _run(hide):
            with tempfile.TemporaryDirectory() as d:
                repo = Path(d)
                _git_init(repo)
                (repo / bus.HANDOFF).write_text(fence, encoding="utf-8")
                (repo / "original.md").write_text("source doc\n", encoding="utf-8")
                _git_commit_all(repo)

                class _Hides(Backend):
                    name = "hides"

                    def invoke(self, role, prompt, cfg):
                        hide(repo)
                        return Turn(text=_CLEAN_VERDICT)

                b = _Hides()
                return Orchestrator(_cfg(repo, net_enforce=True), b, b,
                                    AutoApprove(), log=lambda m: None).run_from_handoff()

        def _exclude(repo):
            (repo / ".git" / "info").mkdir(parents=True, exist_ok=True)
            with (repo / ".git" / "info" / "exclude").open("a", encoding="utf-8") as f:
                f.write("\nevil.py\n")
            (repo / "evil.py").write_text("aws_key = 'x'\n", encoding="utf-8")

        def _skip_worktree(repo):
            subprocess.run(["git", "-C", str(repo), "update-index",
                            "--skip-worktree", "original.md"],
                           check=True, capture_output=True, text=True)
            (repo / "original.md").unlink()

        for label, hide in (("info/exclude", _exclude),
                            ("skip-worktree", _skip_worktree)):
            out = _run(hide)
            self.assertEqual(out.status, BLOCKED, f"{label}: {out.reason}")
            self.assertIn("what git reports", out.reason, label)

    def test_secret_in_the_dispatched_handoff_is_caught(self):
        # Pins the CONTENT of the appended handoff, not the count. The delta
        # drops an unchanged handoff (it is in both snapshots), so without the
        # append a key pasted into the spec ships as BUILT — and a test that
        # only counts the Changes reaching the net passes with the content
        # blanked, which is exactly how this stayed broken.
        if not _git_available():
            self.skipTest("git not on PATH")
        key = "AKIA" + "IOSFODNN7EXAMPLE"
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n"
                f"```scope\nallowed.py\nRESULT.md\n```\naws_key = {key}\n",
                encoding="utf-8")
            backend = _TamperingBackend(repo, "allowed.py", "VALUE = 1\n")
            out = Orchestrator(_cfg(repo, net_enforce=True), backend, backend,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)

    def test_secret_in_the_result_is_caught_even_when_ignored(self):
        # RESULT.md carries verbatim Builder-authored text, so it is the more
        # exposed of the two controller-written files — and it reaches the net
        # only via the git delta, which misses it whenever the repo ignores it.
        # This repo's own .gitignore does exactly that.
        if not _git_available():
            self.skipTest("git not on PATH")
        key = "AKIA" + "IOSFODNN7EXAMPLE"
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / ".gitignore").write_text("RESULT.md\nHANDOFF.md\n", encoding="utf-8")
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nallowed.py\n.gitignore\n```\n",
                encoding="utf-8")

            class _LeaksInResult(Backend):
                name = "leaks"

                def invoke(self, role, prompt, cfg):
                    (repo / "allowed.py").write_text("VALUE = 1\n", encoding="utf-8")
                    return Turn(text=f"# RESULT\nused {key}\n" + _CLEAN_VERDICT)

            backend = _LeaksInResult()
            out = Orchestrator(_cfg(repo, net_enforce=True), backend, backend,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertIn("safety net", out.reason)

    def test_dryrun_warns_on_handoff_tamper_instead_of_blocking(self):
        # Round 10: the tamper stop returned BLOCKED unconditionally while every
        # other check in _build_and_gate degrades, so --net-dryrun ("run the
        # safety net in dryrun (warn) instead of blocks", per orchestrate.py)
        # still hard-stopped here. Continuing is safe because the fence the
        # handlers enforce is pinned from the DISPATCHED text, not re-read from
        # the file the Builder just rewrote.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nallowed.py\nRESULT.md\n```\n",
                encoding="utf-8")
            _git_commit_all(repo)
            logs: list[str] = []
            backend = _TamperingBackend(
                repo, bus.HANDOFF,
                new_text="# rewritten\n```scope\n**\n```\n", also_write="allowed.py")
            out = Orchestrator(_cfg(repo, net_enforce=False), backend, backend,
                               AutoApprove(), log=logs.append).run_from_handoff()
            self.assertEqual(out.status, BUILT, out.reason)
            self.assertTrue(any("altered or removed" in m for m in logs),
                            f"dryrun did not warn about the tamper: {logs}")

    def test_run_loop_tamper_check_follows_the_file_it_wrote(self):
        # Round 10: _build_and_gate read cfg.handoff_name while run() writes
        # bus.HANDOFF unconditionally. They coincided only because no CLI
        # exposes --handoff on `run`; with one set, every cycle died on
        # "builder altered or removed HANDOFF_X.md" — a Builder integrity
        # accusation caused entirely by the controller reading the wrong field.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / "seed.md").write_text("seed\n", encoding="utf-8")
            _git_commit_all(repo)
            # cfg names a handoff the run loop will never write.
            cfg = _cfg(repo, net_enforce=True, handoff_name="HANDOFF_OTHER.md",
                       max_cycles=1, confirm_handoff=False)
            mock = MockBackend(default_low_scenario("demo"))
            out = Orchestrator(cfg, mock, mock, AutoApprove(),
                               log=lambda m: None).run()
            self.assertNotIn("altered or removed", out.reason)
            self.assertEqual(out.status, DONE, out.reason)

    def test_a_directory_symlink_does_not_refuse_the_dispatch(self):
        # Round 10: _opaque_dirs used Path.is_dir(), which FOLLOWS the link,
        # while git does not — it stores a symlink as a blob and lists it as one
        # ordinary entry. So an untracked `latest -> builds/` convenience link
        # was read as a nested repository and refused every dispatch, whole-tree
        # and pre-turn, regardless of the fence. The operator was told to look
        # for a submodule that does not exist, and no fence edit clears it.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nallowed.py\nRESULT.md\n```\n",
                encoding="utf-8")
            (repo / "builds").mkdir()
            (repo / "builds" / "out.txt").write_text("artifact\n", encoding="utf-8")
            try:
                (repo / "latest").symlink_to(repo / "builds", target_is_directory=True)
            except (OSError, NotImplementedError):
                # Windows needs Developer Mode or admin for this.
                self.skipTest("symlink creation not permitted on this machine")
            self.assertTrue((repo / "latest").is_symlink())

            class _WritesInFence(Backend):
                name = "in-fence"

                def invoke(self, role, prompt, cfg):
                    (repo / "allowed.py").write_text("ok = True\n", encoding="utf-8")
                    return Turn(text=_CLEAN_VERDICT)

            backend = _WritesInFence()
            out = Orchestrator(_cfg(repo, net_enforce=True), backend, backend,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BUILT, out.reason)

    def test_a_real_nested_repo_is_still_refused(self):
        # The other half of the symlink fix: skipping links must not skip the
        # thing the check exists for. Without this, "links are fine" would also
        # pass if _opaque_dirs had been deleted outright.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nallowed.py\nRESULT.md\nsub/\n```\n",
                encoding="utf-8")
            sub = repo / "sub"
            sub.mkdir()
            _git_init(sub)
            (sub / "inside.txt").write_text("unvettable\n", encoding="utf-8")

            mock = MockBackend(default_low_scenario("demo"))
            out = Orchestrator(_cfg(repo, net_enforce=True), mock, mock,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertIn("cannot look inside", out.reason)

    @staticmethod
    def _break_the_witness(repo: Path) -> None:
        """Make .git/info/exclude unreadable, so _witness_fingerprint returns None.

        A directory in the file's place raises IsADirectoryError on POSIX and
        PermissionError on Windows — either way the read fails for a reason that
        is not FileNotFoundError, which is the shape a huge-repo `ls-files`
        timeout or a permission problem takes in production.
        """
        info = repo / ".git" / "info"
        info.mkdir(parents=True, exist_ok=True)
        target = info / "exclude"
        if target.is_file():
            target.unlink()
        target.mkdir(exist_ok=True)

    def test_unreadable_witness_fails_closed_before_the_turn(self):
        # Round 10: vis_before was stored without being inspected, and the
        # post-turn comparison is `_witness_fingerprint(...) != vis_before`.
        # `None != None` is False, so when the fingerprint failed at BOTH ends —
        # which is what a persistent cause does — the entire witness layer went
        # silent in enforce: no block, no warning, no reason. Every other "we
        # could not see" case here fails closed.
        #
        # PATCHED, deliberately, and this is the one place in these tests that
        # is: the failure has to hit the fingerprint while `git status` still
        # answers, and the constructible causes do not separate. Making
        # .git/info/exclude unreadable takes git's own status call down with it
        # (verified — collect_changeset returns None too), so the pre-turn
        # changeset check fires first and this branch is never reached. The
        # production shape that DOES separate is a 30s `ls-files -v --full-name
        # :/` timeout on a large index, which `git status` survives via its
        # cache — not constructible in a unit test. The defect is in the
        # caller's handling of None, so None is what the test supplies.
        if not _git_available():
            self.skipTest("git not on PATH")
        from orchestrator import controller as ctrl
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nallowed.py\nRESULT.md\n```\n",
                encoding="utf-8")
            (repo / "seed.md").write_text("seed\n", encoding="utf-8")
            _git_commit_all(repo)
            # Precondition: git itself is healthy, so nothing else can block.
            self.assertIsNotNone(collect_changeset(repo))

            mock = MockBackend(default_low_scenario("demo"))
            real = ctrl._witness_fingerprint
            ctrl._witness_fingerprint = lambda repo: None
            try:
                out = Orchestrator(_cfg(repo, net_enforce=True), mock, mock,
                                   AutoApprove(), log=lambda m: None).run_from_handoff()
            finally:
                ctrl._witness_fingerprint = real
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertIn("cannot read what git reports", out.reason)
            # Knowable before dispatch, so it must not cost a 1800s builder turn.
            self.assertEqual(mock._cycle[ROLE_BUILDER], 0)

    def test_witness_broken_during_the_turn_fails_closed(self):
        # The other end of the same hole: the baseline read fine, the Builder
        # then made it unreadable. "Could not look again" is not "was unchanged",
        # and it gets its own message rather than the tamper one — an operator
        # told "builder changed what git reports" would go hunting for a commit
        # that is not there.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nallowed.py\nRESULT.md\n```\n",
                encoding="utf-8")
            (repo / "seed.md").write_text("seed\n", encoding="utf-8")
            _git_commit_all(repo)

            breaker = self._break_the_witness

            class _BreaksWitness(Backend):
                name = "breaks-witness"

                def invoke(self, role, prompt, cfg):
                    (repo / "allowed.py").write_text("ok = True\n", encoding="utf-8")
                    breaker(repo)
                    return Turn(text=_CLEAN_VERDICT)

            backend = _BreaksWitness()
            out = Orchestrator(_cfg(repo, net_enforce=True), backend, backend,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertIn("cannot re-read what git reports", out.reason)

    def test_repointing_excludes_file_is_watched_even_with_identical_content(self):
        # Round 10 (tdd-guide): dropping the excludesFile SETTING from the
        # fingerprint left the suite green. Every existing scenario changed the
        # setting and the content in lockstep, so the content term alone covered
        # them and the setting term was dead weight as far as the tests could
        # see. The ADR claims both halves matter — "repointing it and editing it
        # are the same attack with different spellings" — so here the two files
        # are byte-identical and only the pointer moves.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nallowed.py\nRESULT.md\n```\n",
                encoding="utf-8")
            (repo / "seed.md").write_text("seed\n", encoding="utf-8")
            _git_commit_all(repo)
            same = "# nothing ignored\n"
            a, b = Path(d) / "ex_a", Path(d) / "ex_b"
            a.write_text(same, encoding="utf-8")
            b.write_text(same, encoding="utf-8")
            self.assertEqual(a.read_text(encoding="utf-8"), b.read_text(encoding="utf-8"))
            subprocess.run(["git", "-C", str(repo), "config", "core.excludesFile", str(a)],
                           check=True, capture_output=True, text=True)

            class _Repoints(Backend):
                name = "repoints"

                def invoke(self, role, prompt, cfg):
                    (repo / "allowed.py").write_text("ok = True\n", encoding="utf-8")
                    subprocess.run(
                        ["git", "-C", str(repo), "config", "core.excludesFile", str(b)],
                        check=True, capture_output=True, text=True)
                    return Turn(text=_CLEAN_VERDICT)

            backend = _Repoints()
            out = Orchestrator(_cfg(repo, net_enforce=True), backend, backend,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertIn("builder changed what git reports", out.reason)

    def test_post_turn_opaque_check_reads_the_snapshot_not_the_delta(self):
        # Round 10 (tdd-guide): the round-9 fix — the post-turn opaque check
        # judges the SNAPSHOT, so a nested repo already dirty at dispatch (equal
        # in both snapshots, therefore absent from the delta) is still refused —
        # was masked. The pre-turn check at the top of _build_and_gate fires
        # first for every scenario the suite can build, so reverting the
        # post-turn line to the delta left 89/89 green.
        #
        # White-box on purpose: the pre-turn check is neutralised for ONE call so
        # the post-turn one is the thing under test. There is no black-box way
        # to separate them — that is exactly why the fix was unprotected.
        if not _git_available():
            self.skipTest("git not on PATH")
        from orchestrator import controller as ctrl
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nallowed.py\nRESULT.md\nsub/\n```\n",
                encoding="utf-8")
            sub = repo / "sub"
            sub.mkdir()
            _git_init(sub)
            (sub / "dirty.txt").write_text("already dirty at dispatch\n", encoding="utf-8")

            real = ctrl._opaque_dirs
            calls = {"n": 0}

            def once_blind(changes, repo_path):
                calls["n"] += 1
                return [] if calls["n"] == 1 else real(changes, repo_path)

            class _WritesInside(Backend):
                name = "writes-inside"

                def invoke(self, role, prompt, cfg):
                    (sub / "leak.py").write_text("k = 1\n", encoding="utf-8")
                    return Turn(text=_CLEAN_VERDICT)

            backend = _WritesInside()
            ctrl._opaque_dirs = once_blind
            try:
                out = Orchestrator(_cfg(repo, net_enforce=True), backend, backend,
                                   AutoApprove(), log=lambda m: None).run_from_handoff()
            finally:
                ctrl._opaque_dirs = real
            self.assertGreaterEqual(calls["n"], 2, "the post-turn check never ran")
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertIn("cannot look inside", out.reason)

    def test_builder_committing_its_turn_blocks(self):
        # The sharpest witness edit, and NOT an exotic one: build_prompt tells
        # the Builder not to commit, which is an admission that headless Codex
        # sometimes does. A commit removes the paths from BOTH snapshots, so the
        # union is empty for them and the net ran zero handlers on a
        # fence-violating write — reported BUILT.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nallowed.py\nRESULT.md\n```\n",
                encoding="utf-8")
            (repo / "seed.md").write_text("seed\n", encoding="utf-8")
            _git_commit_all(repo)

            class _Commits(Backend):
                name = "commits"

                def invoke(self, role, prompt, cfg):
                    (repo / "forbidden.py").write_text("pwned = True\n", encoding="utf-8")
                    subprocess.run(["git", "-C", str(repo), "add", "-A"],
                                   check=True, capture_output=True, text=True)
                    subprocess.run(["git", "-C", str(repo), "-c", "user.email=b@e.com",
                                    "-c", "user.name=b", "commit", "-qm", "builder"],
                                   check=True, capture_output=True, text=True)
                    return Turn(text=_CLEAN_VERDICT)

            backend = _Commits()
            out = Orchestrator(_cfg(repo, net_enforce=True), backend, backend,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertIn("what git reports", out.reason)

    def test_nested_git_repo_is_refused_rather_than_vetted_blindly(self):
        # `-uall` expands untracked directories per file, but it stops at a
        # repository boundary: a nested repo arrives as ONE entry, the
        # directory. Its files would then reach secret_scan as an empty string
        # while the fence was asked about the directory — measured, a key inside
        # a fence-listed `sub/` shipped as BUILT.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nsub/\nRESULT.md\n```\n",
                encoding="utf-8")

            class _NestsRepo(Backend):
                name = "nests"

                def invoke(self, role, prompt, cfg):
                    sub = repo / "sub"
                    sub.mkdir()
                    subprocess.run(["git", "-C", str(sub), "init", "-q"],
                                   check=True, capture_output=True, text=True)
                    (sub / "leak.py").write_text(
                        "key = 'AKIA" + "IOSFODNN7EXAMPLE'\n", encoding="utf-8")
                    return Turn(text=_CLEAN_VERDICT)

            backend = _NestsRepo()
            out = Orchestrator(_cfg(repo, net_enforce=True), backend, backend,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertIn("cannot look inside", out.reason)

    def test_witness_check_works_in_a_linked_worktree(self):
        # `rev-parse --git-dir` in a linked worktree is .git/worktrees/<name>,
        # which has no info/ at all, so the exclude read silently became "" on
        # both sides and the whole check went inert — in precisely the layout
        # the README recommends as a containment boundary.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            main = Path(d) / "main"
            main.mkdir()
            _git_init(main)
            (main / "seed.md").write_text("seed\n", encoding="utf-8")
            _git_commit_all(main)
            wt = Path(d) / "wt"
            subprocess.run(["git", "-C", str(main), "worktree", "add", "-q",
                            str(wt), "-b", "wt"],
                           check=True, capture_output=True, text=True)
            (wt / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nallowed.py\nRESULT.md\n```\n",
                encoding="utf-8")

            class _ExcludesItself(Backend):
                name = "excl"

                def invoke(self, role, prompt, cfg):
                    common = subprocess.run(
                        ["git", "-C", str(wt), "rev-parse", "--git-common-dir"],
                        check=True, capture_output=True, text=True).stdout.strip()
                    info = Path(common)
                    if not info.is_absolute():
                        info = wt / info
                    info = info / "info"
                    info.mkdir(parents=True, exist_ok=True)
                    with (info / "exclude").open("a", encoding="utf-8") as f:
                        f.write("\nevil.py\n")
                    (wt / "evil.py").write_text("pwned = True\n", encoding="utf-8")
                    return Turn(text=_CLEAN_VERDICT)

            backend = _ExcludesItself()
            out = Orchestrator(_cfg(wt, net_enforce=True), backend, backend,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertIn("what git reports", out.reason)

    def test_index_bits_outside_the_work_repo_are_watched(self):
        # `git ls-files` is scoped to its cwd; `git status` is not. A work repo
        # below the git root therefore left index bits outside it unwatched, and
        # the skip-worktree evasion survived in exactly that layout.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _git_init(root)
            (root / "secrets").mkdir()
            (root / "secrets" / "keys.md").write_text("token\n", encoding="utf-8")
            work = root / "work"
            work.mkdir()
            (work / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nsrc/feature.py\nRESULT.md\n```\n",
                encoding="utf-8")
            _git_commit_all(root)

            class _HidesOutside(Backend):
                name = "outside"

                def invoke(self, role, prompt, cfg):
                    subprocess.run(["git", "-C", str(root), "update-index",
                                    "--skip-worktree", "secrets/keys.md"],
                                   check=True, capture_output=True, text=True)
                    (root / "secrets" / "keys.md").unlink()
                    (work / "src").mkdir(exist_ok=True)
                    (work / "src" / "feature.py").write_text("v = 1\n", encoding="utf-8")
                    return Turn(text=_CLEAN_VERDICT)

            backend = _HidesOutside()
            out = Orchestrator(_cfg(work, net_enforce=True), backend, backend,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertIn("what git reports", out.reason)

    def test_excludes_file_authored_mid_turn_is_watched(self):
        # The third ignore knob. `.git/info/exclude` had a case and
        # core.excludesFile did not, so dropping it from the fingerprint broke
        # nothing the suite saw — while it hides a path from `git status`
        # exactly as effectively, and can be both repointed and edited mid-turn.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nallowed.py\nRESULT.md\n```\n",
                encoding="utf-8")

            class _SetsExcludesFile(Backend):
                name = "excludes"

                def invoke(self, role, prompt, cfg):
                    ignore = repo / "my-ignores"
                    ignore.write_text("evil.py\n", encoding="utf-8")
                    subprocess.run(["git", "-C", str(repo), "config",
                                    "core.excludesFile", str(ignore)],
                                   check=True, capture_output=True, text=True)
                    (repo / "evil.py").write_text("pwned = True\n", encoding="utf-8")
                    return Turn(text=_CLEAN_VERDICT)

            backend = _SetsExcludesFile()
            out = Orchestrator(_cfg(repo, net_enforce=True), backend, backend,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertIn("what git reports", out.reason)

    def test_appending_to_a_configured_excludes_file_is_watched(self):
        # The other half of the excludesFile pair, and the likelier one in
        # production: repointing needs a `git config` call, appending to an
        # ALREADY-configured ignore file (a global ~/.gitignore_global, say) is
        # a one-line write. Pinning only the setting left the content read
        # revertible with the suite still green.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            ignore = repo / "preconfigured-ignores"
            ignore.write_text("# nothing yet\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "config",
                            "core.excludesFile", str(ignore)],
                           check=True, capture_output=True, text=True)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nallowed.py\nRESULT.md\n```\n",
                encoding="utf-8")

            class _AppendsToExcludes(Backend):
                name = "appends"

                def invoke(self, role, prompt, cfg):
                    with ignore.open("a", encoding="utf-8") as f:
                        f.write("evil.py\n")
                    (repo / "evil.py").write_text("pwned = True\n", encoding="utf-8")
                    return Turn(text=_CLEAN_VERDICT)

            backend = _AppendsToExcludes()
            out = Orchestrator(_cfg(repo, net_enforce=True), backend, backend,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertIn("what git reports", out.reason)

    def test_builder_stashing_its_turn_blocks(self):
        # The stash is HEAD's sibling in the same claim, and it is NOT covered
        # by the HEAD half: `git stash push` leaves HEAD where it was while
        # removing the change from the working tree. build_prompt forbids
        # stage/commit/merge/deploy but says nothing about stash, so this is
        # squarely the honest-mistake class — and it leaves the reviewing
        # Architect's `git diff` showing nothing at all.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nallowed.py\nRESULT.md\n```\n",
                encoding="utf-8")
            (repo / "tracked.md").write_text("original\n", encoding="utf-8")
            _git_commit_all(repo)

            class _Stashes(Backend):
                name = "stashes"

                def invoke(self, role, prompt, cfg):
                    (repo / "tracked.md").write_text("rewritten\n", encoding="utf-8")
                    subprocess.run(["git", "-C", str(repo), "stash", "push", "-q",
                                    "-m", "builder"],
                                   check=True, capture_output=True, text=True)
                    return Turn(text=_CLEAN_VERDICT)

            backend = _Stashes()
            out = Orchestrator(_cfg(repo, net_enforce=True), backend, backend,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertIn("what git reports", out.reason)

    def test_preexisting_nested_repo_is_refused(self):
        # A nested repo that is already dirty at dispatch sits in BOTH snapshots
        # as the same directory entry, so it compares equal and drops out of the
        # delta — and the Builder's writes inside it were then neither refused
        # nor scanned. The opaque-directory check therefore has to run over the
        # snapshot, not the delta.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nallowed.py\nRESULT.md\n```\n",
                encoding="utf-8")
            vendor = repo / "vendor"
            vendor.mkdir()
            subprocess.run(["git", "-C", str(vendor), "init", "-q"],
                           check=True, capture_output=True, text=True)
            (vendor / "readme.md").write_text("vendored\n", encoding="utf-8")

            class _WritesInsideNested(Backend):
                name = "nested"

                def __init__(self):
                    self.ran = False

                def invoke(self, role, prompt, cfg):
                    self.ran = True
                    (vendor / "leak.py").write_text(
                        "key = 'AKIA" + "IOSFODNN7EXAMPLE'\n", encoding="utf-8")
                    return Turn(text=_CLEAN_VERDICT)

            backend = _WritesInsideNested()
            out = Orchestrator(_cfg(repo, net_enforce=True), backend, backend,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertIn("cannot look inside", out.reason)
            # Refused BEFORE the turn. Asserting only BLOCKED cannot tell the
            # pre-turn check from the post-turn one — both produce it — so
            # deleting the pre-turn check left the suite green while the
            # operator paid up to 1800s to learn something knowable at once.
            self.assertFalse(backend.ran, "the builder should never have run")

    def test_assume_unchanged_is_watched_too(self):
        # The lowercase half of the index-bit check. Only skip-worktree had a
        # case, so dropping the `islower()` test broke nothing the suite saw.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nallowed.py\nRESULT.md\n```\n",
                encoding="utf-8")
            (repo / "tracked.md").write_text("original\n", encoding="utf-8")
            _git_commit_all(repo)

            class _AssumeUnchanged(Backend):
                name = "assume"

                def invoke(self, role, prompt, cfg):
                    subprocess.run(["git", "-C", str(repo), "update-index",
                                    "--assume-unchanged", "tracked.md"],
                                   check=True, capture_output=True, text=True)
                    (repo / "tracked.md").write_text("rewritten\n", encoding="utf-8")
                    return Turn(text=_CLEAN_VERDICT)

            backend = _AssumeUnchanged()
            out = Orchestrator(_cfg(repo, net_enforce=True), backend, backend,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertIn("what git reports", out.reason)

    def test_builder_rewriting_the_fence_mid_scan_does_not_widen_it(self):
        # TOCTOU: the controller compares the handoff against what it dispatched
        # ONCE, but the scan that follows is two subprocesses per changed file,
        # and the handler re-read the fence from disk on each one. A Builder
        # that rewrote the handoff inside that window was rewriting the rule it
        # was about to be judged by. The window widens with changeset size, so
        # it got easier on exactly the large dispatches that matter.
        # The writer fires from inside the scan rather than from a sleeping
        # thread: a wall-clock race would mostly be caught by the tamper stop
        # (which runs BEFORE the scan) and so would pass with the pinning
        # reverted — it would be testing the wrong guard. Rewriting on the first
        # handler launch puts the change exactly in the window the pinning is
        # for: after the one-shot comparison, before the path that matters is
        # judged.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\nallowed.py\nRESULT.md\n```\n",
                encoding="utf-8")
            backend = _TamperingBackend(repo, "zz_forbidden.py", "pwned = True\n")

            real = safety._run_handler
            fired = []

            def rewrite_then_run(handler, payload, env):
                if not fired:
                    fired.append(True)
                    (repo / bus.HANDOFF).write_text(
                        "# H\n```tiers\ngate 1: LOW\n```\n```scope\n*\n```\n",
                        encoding="utf-8")
                return real(handler, payload, env)

            safety._run_handler = rewrite_then_run
            try:
                out = Orchestrator(_cfg(repo, net_enforce=True), backend, backend,
                                   AutoApprove(), log=lambda m: None).run_from_handoff()
            finally:
                safety._run_handler = real
            self.assertTrue(fired, "the scan never ran, so nothing was tested")
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertIn("safety net", out.reason)

    def test_inherited_scope_fence_env_cannot_widen_the_scan(self):
        # The pinned fence travels in an environment variable, so an inherited
        # CLAUDE_SCOPE_FENCE from the operator's shell must be cleared rather
        # than silently become the rule the scan enforces.
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            (repo / bus.HANDOFF).write_text("# H\n```scope\nallowed.py\n```\n",
                                            encoding="utf-8")
            os.environ["CLAUDE_SCOPE_FENCE"] = "*"
            try:
                res = safety.scan([Change(path="forbidden.py", content="x\n")],
                                  _cfg(repo, net_enforce=True))
            finally:
                os.environ.pop("CLAUDE_SCOPE_FENCE", None)
            self.assertTrue(res.blocked, res.reasons)

    def test_changeset_exactly_at_the_ceiling_is_scanned(self):
        # `>` vs `>=`: the boundary was never pinned, so an off-by-one either
        # refuses a legal dispatch or admits one file past the bound.
        if not _git_available():
            self.skipTest("git not on PATH")
        from orchestrator.controller import _MAX_CHANGESET
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            # The snapshot that must land exactly ON the ceiling is the one
            # taken AFTER the turn, and by then the controller has written
            # RESULT.md: handoff + RESULT.md + N-2 pad files == N paths.
            (repo / bus.HANDOFF).write_text(
                "# H\n```tiers\ngate 1: LOW\n```\n```scope\npad/\nRESULT.md\n```\n",
                encoding="utf-8")
            _write_n_files(repo, _MAX_CHANGESET - 2)
            mock = MockBackend(default_low_scenario("demo"))
            mock.scenario.changesets = [None]
            out = Orchestrator(_cfg(repo, net_enforce=True), mock, mock,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BUILT, out.reason)

    def test_fence_absence_blocks_before_the_builder_runs(self):
        # Failing after a 1800s builder turn is a 30-minute answer to a question
        # the handoff already answers. The builder must never be invoked.
        handoff = "# H\n```tiers\ngate 1: LOW\n```\nno scope fence here\n"
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            (repo / bus.HANDOFF).write_text(handoff, encoding="utf-8")
            mock = MockBackend(default_low_scenario("demo"))
            out = Orchestrator(_cfg(repo, net_enforce=True), mock, mock,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertIn("scope", out.reason)
            self.assertEqual(mock._cycle[ROLE_BUILDER], 0)  # builder never invoked

    def test_comment_only_fence_blocks_like_no_fence(self):
        handoff = "# H\n```tiers\ngate 1: LOW\n```\n```scope\n# TODO fill in\n```\n"
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            (repo / bus.HANDOFF).write_text(handoff, encoding="utf-8")
            mock = MockBackend(default_low_scenario("demo"))
            out = Orchestrator(_cfg(repo, net_enforce=True), mock, mock,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)

    def test_fence_absence_only_warns_in_dryrun(self):
        # dryrun is advisory by contract; it must not acquire a new hard block.
        # On the git path: the injected version passed only because injection
        # bypasses git, in a temp dir that was not even a repo.
        if not _git_available():
            self.skipTest("git not on PATH")
        handoff = "# H\n```tiers\ngate 1: LOW\n```\nno scope fence\n"
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(handoff, encoding="utf-8")
            backend = _TamperingBackend(repo, "forbidden.py", "x = 1\n")
            out = Orchestrator(_cfg(repo, net_enforce=False), backend, backend,
                               AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BUILT, out.reason)

    def test_ceiling_boundary_is_exact_on_both_sides(self):
        # `>` vs `>=` was pinned from below only, leaving a one-path permissive
        # gap above. Bound it from both directions against the real collector.
        if not _git_available():
            self.skipTest("git not on PATH")
        from orchestrator.controller import _MAX_CHANGESET, OVERSIZED
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            _write_n_files(repo, _MAX_CHANGESET)
            self.assertIsNot(collect_changeset(repo, max_files=_MAX_CHANGESET),
                             OVERSIZED)
            (repo / "pad" / "one_more.txt").write_text("x\n", encoding="utf-8")
            self.assertIs(collect_changeset(repo, max_files=_MAX_CHANGESET),
                          OVERSIZED)

    def test_inherited_git_dir_cannot_redirect_the_witness(self):
        # GIT_DIR / GIT_WORK_TREE override -C and point git at a different
        # repository, so an inherited value makes the net vet the wrong tree —
        # measured, the work repo's out-of-fence file vanished from the
        # changeset entirely. Routinely set inside git hooks and
        # `git rebase --exec`, so this is a misconfiguration hazard first.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            work = Path(d) / "work"
            other = Path(d) / "other"
            for r in (work, other):
                r.mkdir()
                _git_init(r)
            (work / "leak.md").write_text("secret-ish\n", encoding="utf-8")
            (other / "decoy.md").write_text("decoy\n", encoding="utf-8")
            saved = {k: os.environ.get(k) for k in ("GIT_DIR", "GIT_WORK_TREE")}
            os.environ["GIT_DIR"] = str(other / ".git")
            os.environ["GIT_WORK_TREE"] = str(other)
            try:
                paths = [c.path for c in collect_changeset(work)]
            finally:
                for k, v in saved.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
            self.assertIn("leak.md", paths)
            self.assertNotIn("decoy.md", paths)

    def test_subdirectory_handoff_is_refused(self):
        # The handler resolves the fence as HOME/<basename>, so a sub-directory
        # handoff would leave the controller reading repo/specs/H.md while the
        # handler looks for repo/H.md, finds nothing, and fails OPEN. Refuse the
        # input rather than let the two sides disagree.
        with tempfile.TemporaryDirectory() as d:
            problems = _cfg(Path(d), handoff_name="specs/H.md").validate()
            self.assertTrue(any("handoff_name" in p for p in problems), problems)
            self.assertEqual(_cfg(Path(d), handoff_name="HANDOFF_DELEGATE.md").validate(), [])

    def test_missing_handoff_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            mock = MockBackend(default_low_scenario("demo"))
            out = Orchestrator(cfg, mock, mock, AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)

    def test_custom_handoff_name(self):
        # build reads cfg.handoff_name so a repo that keeps HANDOFF.md as a
        # persistent doc can dispatch an alternate spec without clobbering it.
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
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
        #
        # Driven on the GIT path. The injected-changeset version of this test
        # exercised the one shape production never takes, while its name sold
        # the core guarantee — the shape that hid three defects before.
        if not _git_available():
            self.skipTest("git not on PATH")
        handoff = "# H\n```tiers\ngate 1: LOW\n```\n```scope\nallowed.py\nRESULT.md\n```\n"
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(handoff, encoding="utf-8")
            backend = _TamperingBackend(repo, "forbidden.py", "x = 1\n")
            out = Orchestrator(_cfg(repo), backend, backend, AutoApprove(),
                               log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BLOCKED, out.reason)
            self.assertIn("safety net", out.reason)

    def test_tier_gate_advisory_does_not_block(self):
        # HIGH gate, panel FAIL, but in-scope: tier-gate is advisory in the build
        # path, so it still BUILDs — the in-session Claude review owns the verdict
        # and the HIGH human sign-off happens in-session, not here.
        sc = _high_scenario()
        sc.results[0] = "```verdicts\ngate 1: status=completed tier=HIGH panel=FAIL\n```\n"
        if not _git_available():
            self.skipTest("git not on PATH")
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_init(repo)
            (repo / bus.HANDOFF).write_text(sc.handoffs[0], encoding="utf-8")
            cfg = _cfg(repo)
            mock = MockBackend(sc)
            out = Orchestrator(cfg, mock, mock, AutoApprove(), log=lambda m: None).run_from_handoff()
            self.assertEqual(out.status, BUILT, out.reason)


if __name__ == "__main__":
    unittest.main()
