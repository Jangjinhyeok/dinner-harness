"""Vendor backends — one headless invocation per Architect/Builder turn.

A "session" in the Two-CLI sense is not a long-lived terminal here; it is a
single headless call. Because the harness mandates self-contained HANDOFF/RESULT,
turns are stateless: each reads the bus + repo fresh, so no session-resume is
needed (this is what makes cross-vendor clean).

- MockBackend  — deterministic canned turns; drives the full loop offline. The
  default backend, and the one the tests exercise.
- ClaudeBackend / CodexBackend — real `claude -p` / `codex exec` shell-outs.
  SCAFFOLD: the exact flags / output formats differ across CLI versions and
  must be verified on the machine that has both CLIs authenticated (see
  orchestrator/README.md "Build-time verification"). Not exercised by tests.

Stdlib only.
"""
from __future__ import annotations

import os
import json
import signal
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .config import Config
from .safety import Change

ROLE_ARCHITECT = "architect"
ROLE_BUILDER = "builder"
# Read-only challenger dispatch (ADR-0020 correction 5). Both backends default
# non-ROLE_BUILDER challenger turns to read-only behavior. ClaudeBackend also
# clears any inherited DINNER_EXECUTION_MODE=direct below so its builder_guard
# hook stays active even when the parent process is a direct-edit session.
ROLE_CHALLENGER = "challenger"
ROLE_RECOVERY = "recovery"
ROLE_REVIEWER = "reviewer"

def _write_session_marker(dispatch_id: str, metadata: dict, cfg: Config) -> None:
    """Best-effort observations, never policy evidence or a raw transcript."""
    try:
        cfg.audit_dir.mkdir(parents=True, exist_ok=True)
        (cfg.audit_dir / f"watch-builder-{dispatch_id}.json").write_text(
            json.dumps(metadata, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass


@dataclass
class Turn:
    text: str = ""
    changeset: Optional[list[Change]] = None  # mock supplies this; real reads git
    error: str = ""
    thread_id: str = ""
    usage: dict = field(default_factory=dict)
    elapsed_s: float = 0.0
    dispatch_id: str = ""


class Backend:
    """Vendor backend interface. ``invoke`` runs one headless turn."""

    name = "base"

    def invoke(self, role: str, prompt: str, cfg: Config) -> Turn:  # pragma: no cover
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# Mock                                                                        #
# --------------------------------------------------------------------------- #
@dataclass
class Scenario:
    """Canned turns for a deterministic offline run.

    ``handoffs`` / ``results`` / ``reviews`` are per-cycle lists; ``changesets``
    pairs with ``results``. The orchestrator pulls index = cycle-1.
    """
    handoffs: list[str] = field(default_factory=list)
    results: list[str] = field(default_factory=list)
    changesets: list[list[Change]] = field(default_factory=list)
    reviews: list[str] = field(default_factory=list)


def default_low_scenario(goal: str) -> Scenario:
    """A single-cycle, all-LOW scenario that completes cleanly."""
    handoff = (
        f"# HANDOFF: {goal}\n\n## 1. Goal\n{goal}\n\n## 5. 게이트\n"
        "### Gate 1 — implement\n- 작업: 구현\n- 검증: build\n\n"
        "```tiers\ngate 1: LOW\n```\n\n"
        "## Section A — operative scope codeblock\n```scope\nsrc/feature.py\nRESULT.md\n```\n"
    )
    result = (
        "# RESULT\n\n## Summary\n| Gate | Status |\n|---|---|\n| Gate 1 | ✅ |\n\n"
        "```verdicts\ngate 1: status=completed tier=LOW panel=PASS\n```\n"
    )
    changeset = [Change(path="src/feature.py", content="# implemented\nVALUE = 1\n")]
    review = "review: HANDOFF intent met.\n\n```control\nverdict: DONE\nreason: gate 1 verified\n```\n"
    return Scenario(handoffs=[handoff], results=[result], changesets=[changeset], reviews=[review])


class MockBackend(Backend):
    name = "mock"

    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self._cycle = {ROLE_ARCHITECT: 0, ROLE_BUILDER: 0}

    def invoke(self, role: str, prompt: str, cfg: Config) -> Turn:
        s = self.scenario
        if role == ROLE_BUILDER:
            i = self._cycle[ROLE_BUILDER]
            self._cycle[ROLE_BUILDER] += 1
            text = s.results[i] if i < len(s.results) else ""
            cs = s.changesets[i] if i < len(s.changesets) else []
            return Turn(text=text, changeset=cs)
        # architect: design on even calls, review on odd — but we route by
        # prompt marker for robustness.
        is_review = "REVIEW" in prompt.upper()
        i = self._cycle[ROLE_ARCHITECT]
        if is_review:
            text = s.reviews[i] if i < len(s.reviews) else ""
            self._cycle[ROLE_ARCHITECT] += 1
            return Turn(text=text)
        text = s.handoffs[i] if i < len(s.handoffs) else ""
        return Turn(text=text)


# --------------------------------------------------------------------------- #
# Real backends (scaffold — verify flags on your machine)                     #
# --------------------------------------------------------------------------- #
class _WindowsJob:
    """Contain the suspended CLI before its first instruction (Windows 8+).

    No breakaway is allowed. Descendants remain owned after the launcher exits.
    Win32 handles are private and non-inheritable; closing the job kills members.
    """

    def __init__(self):
        import ctypes as ct
        from ctypes import wintypes as wt

        self.ct = ct
        self.api = ct.WinDLL("kernel32", use_last_error=True)
        class BasicLimits(ct.Structure):
            _fields_ = [
                ("process_time", ct.c_longlong), ("job_time", ct.c_longlong),
                ("flags", wt.DWORD), ("min_working_set", ct.c_size_t),
                ("max_working_set", ct.c_size_t), ("active_limit", wt.DWORD),
                ("affinity", ct.c_size_t), ("priority", wt.DWORD),
                ("scheduling", wt.DWORD),
            ]
        class ExtendedLimits(ct.Structure):
            _fields_ = [
                ("basic", BasicLimits), ("io_counters", ct.c_ulonglong * 6),
                ("process_memory", ct.c_size_t), ("job_memory", ct.c_size_t),
                ("peak_process_memory", ct.c_size_t), ("peak_job_memory", ct.c_size_t),
            ]
        class ThreadEntry(ct.Structure):
            _fields_ = [
                ("size", wt.DWORD), ("usage", wt.DWORD), ("thread_id", wt.DWORD),
                ("process_id", wt.DWORD), ("base_priority", wt.LONG),
                ("delta_priority", wt.LONG), ("flags", wt.DWORD),
            ]
        class Accounting(ct.Structure):
            _fields_ = [
                ("times", ct.c_longlong * 4), ("page_faults", wt.DWORD),
                ("total_processes", wt.DWORD), ("active_processes", wt.DWORD),
                ("terminated_processes", wt.DWORD),
            ]
        self.ThreadEntry = ThreadEntry
        self.Accounting = Accounting
        signatures = {
            "CreateJobObjectW": ([ct.c_void_p, wt.LPCWSTR], wt.HANDLE),
            "SetInformationJobObject": ([wt.HANDLE, ct.c_int, ct.c_void_p, wt.DWORD], wt.BOOL),
            "AssignProcessToJobObject": ([wt.HANDLE, wt.HANDLE], wt.BOOL),
            "OpenProcess": ([wt.DWORD, wt.BOOL, wt.DWORD], wt.HANDLE),
            "CreateToolhelp32Snapshot": ([wt.DWORD, wt.DWORD], wt.HANDLE),
            "Thread32First": ([wt.HANDLE, ct.POINTER(ThreadEntry)], wt.BOOL),
            "Thread32Next": ([wt.HANDLE, ct.POINTER(ThreadEntry)], wt.BOOL),
            "OpenThread": ([wt.DWORD, wt.BOOL, wt.DWORD], wt.HANDLE),
            "ResumeThread": ([wt.HANDLE], wt.DWORD),
            "CloseHandle": ([wt.HANDLE], wt.BOOL),
            "TerminateJobObject": ([wt.HANDLE, wt.UINT], wt.BOOL),
            "QueryInformationJobObject": ([wt.HANDLE, ct.c_int, ct.c_void_p, wt.DWORD, ct.c_void_p], wt.BOOL),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.api, name)
            function.argtypes, function.restype = args, result
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ct.WinError(ct.get_last_error())
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle, 9, ct.byref(limits), ct.sizeof(limits)):
            error = ct.WinError(ct.get_last_error())
            self.close()
            raise error

    def assign_and_resume(self, pid):
        ct, api = self.ct, self.api
        process = api.OpenProcess(0x0101, False, pid)  # SET_QUOTA | TERMINATE
        if not process:
            raise ct.WinError(ct.get_last_error())
        try:
            if not api.AssignProcessToJobObject(self.handle, process):
                raise ct.WinError(ct.get_last_error())
        finally:
            api.CloseHandle(process)
        snapshot = api.CreateToolhelp32Snapshot(0x4, 0)  # TH32CS_SNAPTHREAD
        if snapshot == ct.c_void_p(-1).value:
            raise ct.WinError(ct.get_last_error())
        try:
            entry = self.ThreadEntry()
            entry.size = ct.sizeof(entry)
            found = api.Thread32First(snapshot, ct.byref(entry))
            thread_ids = []
            while found:
                if entry.process_id == pid:
                    thread_ids.append(entry.thread_id)
                found = api.Thread32Next(snapshot, ct.byref(entry))
            # The suspended process has not executed user code or spawned threads.
            if len(thread_ids) != 1:
                raise OSError("cannot identify suspended CLI primary thread")
            thread = api.OpenThread(0x2, False, thread_ids[0])  # SUSPEND_RESUME
            if not thread:
                raise ct.WinError(ct.get_last_error())
            try:
                if api.ResumeThread(thread) != 1:
                    raise OSError("CLI primary thread was not suspended once")
            finally:
                api.CloseHandle(thread)
        finally:
            api.CloseHandle(snapshot)

    def close(self):
        if self.handle:
            handle, self.handle = self.handle, None
            try:
                if not self.api.TerminateJobObject(handle, 1):
                    raise self.ct.WinError(self.ct.get_last_error())
                # Termination requests are asynchronous. Wait for zero members
                # before permitting the controller's after-snapshot.
                deadline = time.monotonic() + 2
                accounting = self.Accounting()
                while True:
                    if not self.api.QueryInformationJobObject(
                        handle, 1, self.ct.byref(accounting), self.ct.sizeof(accounting), None
                    ):
                        raise self.ct.WinError(self.ct.get_last_error())
                    if accounting.active_processes == 0:
                        break
                    if time.monotonic() >= deadline:
                        raise OSError("vendor job termination incomplete")
                    time.sleep(0.01)
            finally:
                self.api.CloseHandle(handle)


def _terminate_tree(proc) -> None:
    """Bounded cleanup, including descendants that inherited our pipe handles."""
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=5, check=False,
            )
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        proc.kill()
    except OSError:
        pass


def _run(
    argv: list[str],
    cfg: Config,
    last_message_file: Optional[Path] = None,
    *,
    stdin_text: Optional[str] = None,
    json_events: bool = False,
    on_event: Optional[Callable[[dict], None]] = None,
    env: Optional[dict] = None,
) -> Turn:
    """Drain stdout/stderr and feed stdin concurrently within a bounded turn.

    JSONL contains lifecycle metadata; only -o is a Codex final response.
    Requested sandbox flags are not proof of runtime enforcement.
    """
    started = time.monotonic()
    result = Turn()
    exe = shutil.which(argv[0])
    if exe is None:
        return Turn(error=f"executable not found on PATH: {argv[0]!r}")
    proc = None
    job = None
    workers = []
    try:
        if os.name == "nt":
            job = _WindowsJob()
        proc = subprocess.Popen(
            [exe, *argv[1:]], cwd=str(cfg.repo),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
            encoding="utf-8", errors="replace", bufsize=1, env=env,
            start_new_session=os.name != "nt",
            creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP | 0x4) if os.name == "nt" else 0,
        )
        if job is not None:
            job.assign_and_resume(proc.pid)
        stdout: list[str] = []
        stderr: list[str] = []
        event_error = ""
        reader_errors: list[str] = []

        def pump(stream, captured, destination, events=False):
            nonlocal event_error
            try:
                for line in iter(stream.readline, ""):
                    if not events:
                        captured.append(line)
                        print(line, end="", file=destination, flush=True)
                        continue
                    try:
                        event = json.loads(line)
                    except (ValueError, TypeError):
                        event_error = "invalid Codex JSONL event"
                        continue
                    if not isinstance(event, dict):
                        event_error = "invalid Codex JSONL event"
                        continue
                    kind = event.get("type")
                    if kind == "thread.started":
                        thread_id = event.get("thread_id")
                        if isinstance(thread_id, str):
                            result.thread_id = thread_id
                    elif kind == "turn.completed":
                        usage = event.get("usage")
                        if isinstance(usage, dict):
                            result.usage = {
                                key: value for key, value in usage.items()
                                if key in ("input_tokens", "cached_input_tokens", "output_tokens")
                                and isinstance(value, int) and not isinstance(value, bool) and value >= 0
                            }
                    elif kind in ("error", "turn.failed"):
                        # Raw error messages may contain source/prompt data.
                        event_error = f"Codex {kind} event; inspect CLI diagnostics"
                    if on_event and kind in ("thread.started", "turn.completed", "turn.failed", "error"):
                        on_event({"type": kind, "thread_id": result.thread_id, "usage": result.usage})
            except (OSError, ValueError) as exc:
                reader_errors.append(type(exc).__name__)
            finally:
                stream.close()

        def feed():
            try:
                proc.stdin.write(stdin_text)
            except (BrokenPipeError, OSError, ValueError):
                pass
            finally:
                try:
                    proc.stdin.close()
                except (BrokenPipeError, OSError, ValueError):
                    pass

        workers = [
            threading.Thread(target=pump, args=(proc.stdout, stdout, sys.stdout, json_events), daemon=True),
            threading.Thread(target=pump, args=(proc.stderr, stderr, sys.stderr), daemon=True),
        ]
        if stdin_text is not None:
            workers.append(threading.Thread(target=feed, daemon=True))
        for worker in workers:
            worker.start()
        remaining = max(0.001, cfg.timeout_s - (time.monotonic() - started))
        try:
            proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            result.error = f"vendor turn timed out after {cfg.timeout_s}s"
            if job is not None:
                job.close()
            else:
                _terminate_tree(proc)
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        # End ownership before collecting the final snapshot, even if the launcher
        # exited successfully while descendants retained pipes or kept editing.
        if job is not None:
            job.close()
        else:
            _terminate_tree(proc)
        deadline = time.monotonic() + 2
        for worker in workers:
            worker.join(timeout=max(0, deadline - time.monotonic()))
        if any(worker.is_alive() for worker in workers):
            _terminate_tree(proc)
            result.error = result.error or "vendor pipe cleanup incomplete"
        if not result.error and proc.returncode != 0:
            result.error = f"vendor exit {proc.returncode}; inspect CLI diagnostics"
        result.error = result.error or event_error
        if reader_errors:
            result.error = result.error or "vendor output reader failed"
        result.text = "".join(stdout)
        if last_message_file is not None:
            try:
                result.text = last_message_file.read_text(encoding="utf-8-sig")
                if not result.text.strip():
                    result.error = result.error or "vendor final response is empty"
            except OSError:
                result.text = ""
                result.error = result.error or "vendor final response file missing"
        return result
    except Exception as exc:  # noqa: BLE001
        if job is not None:
            try:
                job.close()
            except OSError:
                pass  # Preserve the invocation failure; close still releases the job.
        if proc is not None:
            _terminate_tree(proc)
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
            if not workers:
                for stream in (proc.stdin, proc.stdout, proc.stderr):
                    if stream is not None:
                        stream.close()
        result.error = f"vendor invocation failed: {type(exc).__name__}"
        return result
    finally:
        if job is not None:
            job.close()
        result.elapsed_s = round(time.monotonic() - started, 3)


class ClaudeBackend(Backend):
    """`claude -p` print mode. Hooks fire in this mode (scope/secret net).

    Prompts use stdin because the `.CMD` shim passes through cmd.exe's 8191-char limit.
    """

    name = "claude"

    def invoke(self, role: str, prompt: str, cfg: Config) -> Turn:
        argv = ["claude", "-p", "--output-format", "text"]
        model = cfg.architect_model if role == ROLE_ARCHITECT else cfg.builder_model
        if model:
            argv += ["--model", model]
        effort = cfg.architect_effort if role == ROLE_ARCHITECT else cfg.builder_effort
        if effort:
            argv += ["--effort", effort]
        env = None
        # A Builder edits files autonomously; without a non-interactive
        # permission posture the headless turn would stall on approval.
        # VERIFY this flag name/behaviour on your CLI version.
        if role == ROLE_BUILDER:
            argv += ["--permission-mode", "acceptEdits"]
            # This subprocess inherits the machine's installed ~/.claude hooks.json
            # (it is a real `claude -p` session), including builder_guard -- which
            # has no concept of "this Claude process IS the Builder" and blocks any
            # non-bus-artifact Edit/Write outright. DINNER_EXECUTION_MODE=direct is
            # the same escape claude-direct.cmd sets for a human direct-edit
            # session; without it a Claude Builder turn can never write its
            # implementation. The controller-side net (safety.py) remains the
            # deterministic gate regardless of vendor.
            env = {**os.environ, "DINNER_EXECUTION_MODE": "direct"}
        else:
            env = {**os.environ}
            env.pop("DINNER_EXECUTION_MODE", None)
            argv += ["--permission-mode", "plan"]
        return _run(argv, cfg, stdin_text=prompt, env=env)


class CodexBackend(Backend):
    """Codex exec: stdin prompt, JSONL observations, separate final response.

    Requires --json/-o/--output-schema support. Windows sandbox configuration
    belongs to the installed CLI; no experimental feature is silently enabled.
    Runtime sandbox enforcement requires a separate environment smoke test.
    """

    name = "codex"

    def invoke(self, role: str, prompt: str, cfg: Config) -> Turn:
        sandbox = "workspace-write" if role == ROLE_BUILDER else "read-only"
        dispatch_id = uuid.uuid4().hex
        scratch = tempfile.TemporaryDirectory(prefix="dinner-codex-")
        last_msg = Path(scratch.name) / "last-message.txt"
        argv = [
            "codex", "exec",
            "--cd", str(cfg.repo),
            "--sandbox", sandbox,
            "--skip-git-repo-check",
            "--json",
            "-o", str(last_msg),
        ]
        output_schema = getattr(cfg, "output_schema", None)
        if output_schema is not None:
            argv += ["--output-schema", str(output_schema)]
        model = cfg.architect_model if role == ROLE_ARCHITECT else cfg.builder_model
        if model:
            argv += ["--model", model]
        effort = cfg.architect_effort if role == ROLE_ARCHITECT else cfg.builder_effort
        if effort:
            argv += ["-c", f"model_reasoning_effort={effort}"]
        metadata = {
            "dispatch_id": dispatch_id, "role": role, "model": model,
            "effort": effort, "execution_path": "headless", "status": "starting",
            "sandbox_requested": sandbox, "sandbox_verified": "not_run",
        }

        def observe(event):
            metadata.update(event)
            metadata["status"] = event["type"]
            _write_session_marker(dispatch_id, metadata, cfg)

        _write_session_marker(dispatch_id, metadata, cfg)
        try:
            turn = _run(
                argv,
                cfg,
                last_message_file=last_msg,
                stdin_text=prompt,
                json_events=True,
                on_event=observe,
            )
            turn.dispatch_id = dispatch_id
            metadata.update(status="failed" if turn.error else "completed",
                            elapsed_s=turn.elapsed_s, thread_id=turn.thread_id,
                            usage=turn.usage)
            _write_session_marker(dispatch_id, metadata, cfg)
            return turn
        finally:
            scratch.cleanup()


def make_backend(vendor: str) -> Backend:
    """Real backend for a vendor slot."""
    if vendor == "claude":
        return ClaudeBackend()
    if vendor == "codex":
        return CodexBackend()
    raise ValueError(f"unknown vendor: {vendor!r}")
