"""Controller-side deterministic safety net.

The cross-vendor asymmetry: Claude Builder hooks are directly mediated, but a
Codex 0.147.0 Builder's native hooks are advisory: PreToolUse exit 2 cannot
veto an edit or deliver its block reason to the agent. So the net lives in the
*controller* and runs regardless of which vendor built — by invoking the
existing harness hook handlers verbatim as subprocesses, fed a synthesized
PreToolUse payload per changed file. No handler code is modified or reimplemented.

A block (hook exit code 2) on any changed file fails the cycle.
Stdlib only.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import bus
from .config import Config


@dataclass
class Change:
    path: str          # repo-relative or absolute
    content: str       # the new file content (post-change)


@dataclass
class NetResult:
    blocked: bool = False
    reasons: list[str] = field(default_factory=list)
    scope_blocked_paths: list[str] = field(default_factory=list)
    secret_blocked_paths: list[str] = field(default_factory=list)

    def add_block(self, reason: str) -> None:
        self.blocked = True
        self.reasons.append(reason)


def _handler(cfg: Config, name: str) -> Path:
    return Path(cfg.hooks_dir) / "handlers" / f"{name}.py"


def _run_handler(handler: Path, payload: dict, env: dict) -> tuple[int, str]:
    """Run a hook handler with the payload on stdin. Returns (code, stderr).

    Exit 2 = block (per lib/common.exit_block); 0 = allow/warn. A launch
    failure returns the sentinel ``-1`` so the caller fails CLOSED in enforce —
    a net that cannot run must not silently allow a changeset.
    """
    try:
        proc = subprocess.run(
            [sys.executable, str(handler)],
            input=json.dumps(payload),
            capture_output=True,
            # Pinned to UTF-8, NOT the locale default `text=True`. On a Korean
            # Windows box that default is cp949: the payload carries the file's
            # path and full content, so any character outside cp949 made the
            # write raise (a launch error, i.e. a blocked changeset for an
            # encoding reason), and a handler answering in UTF-8 blew up the
            # reader thread — which loses the stderr explaining WHY a change was
            # blocked, leaving an empty reason on the operator's screen.
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=30,
        )
        return proc.returncode, (proc.stderr or "").strip()
    except Exception as exc:  # noqa: BLE001 - launch failure -> fail-closed sentinel
        return -1, f"launch error for {handler.name}: {type(exc).__name__}: {exc}"


def scan(changes: list[Change], cfg: Config, *,
         scope_exempt: Optional[set[str]] = None,
         fence: Optional[list[str]] = None,
         handoff_name: Optional[str] = None,
         secret_only: bool = False) -> NetResult:
    """Run secret_scan + scope_check over every change.

    Block on any handler exit 2. In ``enforce`` the net also fails CLOSED when a
    configured handler is missing or cannot launch (a net you cannot run is not a
    pass); in ``dryrun`` those degrade to warnings.

    ``fence`` pins the scope whitelist for the whole scan. Pass it and the
    handler stops re-reading the fence from disk on every file — which is what
    closes the window between the controller's one-shot handoff comparison and
    the 2*N subprocesses that follow. Like ``scope_exempt`` it is the CALLER's
    to supply: only the controller knows what it actually dispatched.

    ``scope_exempt`` names repo-relative paths to skip in the **scope** layer
    only — never in the secret layer. It exists for the two files the CONTROLLER
    is responsible for rather than the Builder: ``RESULT.md``, which the
    controller writes from the Builder's report, and the dispatched handoff,
    which the Architect wrote and the controller has already proved untampered.
    Judging either against the Builder's edit whitelist would fail every
    dispatch on its own paperwork. The caller decides membership, because only
    the controller knows that — an exemption handed to a file the Builder wrote
    is a hole, not a convenience. A key pasted into a handoff is exactly as
    leaked as one in source, so ``secret_scan`` always runs.

    ``handoff_name`` is likewise the CALLER's to supply — it names the file the
    controller actually dispatched from, which is not always ``cfg.handoff_name``
    (``run()`` always authors ``bus.HANDOFF``). Falling back to the config was
    the last place the net resolved a bus name for itself; with the fence pinned
    the name only reaches the operator's block message, but a message naming a
    file nobody wrote is how an operator loses trust in the tool.

    ``secret_only`` runs the secret layer alone. It exists for output the
    ARCHITECT authored: the ```scope``` fence bounds the BUILDER, and the
    Architect has none — its own protocol tells it to write an ADR before
    dispatching, so judging its files against the Builder's whitelist would fail
    every cycle on the Architect's own paperwork. A key is a key wherever it was
    pasted, so the secret layer still runs. Spelling this as a blanket
    ``scope_exempt`` would behave identically and say the wrong thing: nothing
    here is exempt, there is simply no fence that applies.
    """
    res = NetResult()
    repo = Path(cfg.repo).resolve()
    enforce = cfg.net_enforce
    mode = "enforce" if enforce else "dryrun"
    handoff_name = handoff_name or cfg.handoff_name or bus.HANDOFF

    base_env = dict(os.environ)
    # The other half of the UTF-8 pinning in _run_handler, and load-bearing:
    # the parent now decodes the pipe as UTF-8 unconditionally, so a child
    # writing the locale codec garbles the one message that says why a change
    # was refused. Measured without these two, on a path named 금지🚀.md:
    #   [scope_check:block] .../����\U0001f680.md not in HANDOFF.md scope
    # — a path the operator cannot act on, for the document lane's routine case.
    base_env["PYTHONUTF8"] = "1"
    base_env["PYTHONIOENCODING"] = "utf-8"
    # The handlers' 200ms watchdog is sized for an interactive Claude hook, and
    # it answers "allow" when it fires — as does an unhandled crash. Neither
    # fits here: we pass whole file contents, and this net is the only automatic
    # defense against a Builder whose own hooks cannot veto the edit. Give the
    # handler a budget it can actually meet (inside the 30s subprocess timeout
    # below), and make
    # reaching no verdict mean BLOCK — a change the net could not read is not a
    # change it approved, and exit 0 here is recorded with no reason at all.
    base_env["CLAUDE_HOOK_TIMEOUT_MS"] = "20000"
    base_env["CLAUDE_HOOK_FAILS_CLOSED"] = "1"
    base_env["CLAUDE_SECRET_SCAN_MODE"] = mode
    base_env["CLAUDE_SCOPE_WHITELIST_MODE"] = mode
    # scope_check reads the ```scope``` fence from DINNER_HARNESS_HOME. The
    # filename is NOT always HANDOFF.md: the build path honours cfg.handoff_name
    # (e.g. /delegate always dispatches from HANDOFF_DELEGATE.md), and without
    # this the handler looked for HANDOFF.md, missed it, and failed OPEN — the
    # fence was inert for every run of that lane.
    base_env["DINNER_HARNESS_HOME"] = str(repo)
    base_env["CLAUDE_SCOPE_HANDOFF_NAME"] = handoff_name
    if fence is None:
        # Assign unconditionally either way: an inherited CLAUDE_SCOPE_FENCE
        # from the operator's shell must never become the rule this scan
        # enforces. Popping is the "read the file" signal the handler expects.
        base_env.pop("CLAUDE_SCOPE_FENCE", None)
    else:
        base_env["CLAUDE_SCOPE_FENCE"] = "\n".join(fence)

    handlers = [("secret_scan", _handler(cfg, "secret_scan"))]
    if not secret_only:
        handlers.append(("scope_check", _handler(cfg, "scope_check")))

    def _degrade(msg: str) -> None:
        if enforce:
            res.add_block(msg)
        else:
            res.reasons.append("WARN: " + msg)

    for name, handler in handlers:
        if not handler.is_file():
            _degrade(f"{name} handler not found: {handler}")

    exempt = {p.replace("\\", "/") for p in (scope_exempt or set())}

    for ch in changes:
        abs_path = str((repo / ch.path).resolve()) if not os.path.isabs(ch.path) else ch.path
        is_exempt = ch.path.replace("\\", "/") in exempt
        payload = {
            "tool_name": "Write",
            "tool_input": {"file_path": abs_path, "content": ch.content},
            "cwd": str(repo),
        }
        for name, handler in handlers:
            if is_exempt and name == "scope_check":
                continue
            if not handler.is_file():
                continue
            code, err = _run_handler(handler, payload, base_env)
            if code == 2:
                res.add_block(f"{name} blocked {ch.path}: {err or 'exit 2'}")
                if name == "scope_check":
                    res.scope_blocked_paths.append(ch.path)
                elif name == "secret_scan":
                    res.secret_blocked_paths.append(ch.path)
            elif code == 0:
                pass  # the only "allow" there is
            else:
                # ANY other code is a handler that produced no verdict, and a
                # non-verdict is not an approval. lib/common emits only 0 and 2,
                # so everything else is death before the verdict: an import-time
                # exception (a half-copied hooks_dir, a missing lib/, a syntax
                # error) exits 1 OUTSIDE run_handler's try, where
                # CLAUDE_HOOK_FAILS_CLOSED cannot reach it. Measured: each of
                # those gave blocked=False with an EMPTY reason list — the net
                # fully disarmed, the run reporting BUILT, nothing on screen.
                # -1 is our own launch-failure sentinel and lands here too.
                _degrade(f"{name} reached no verdict on {ch.path} "
                         f"(exit {code}): {err or 'no output'}")
    return res
