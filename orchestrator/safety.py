"""Controller-side deterministic safety net.

The cross-vendor asymmetry: a Claude Builder fires the scope_check / secret_scan
hooks; a Codex 0.111 Builder does not. So the net lives in the *controller* and
runs regardless of which vendor built — by invoking the existing harness hook
handlers verbatim as subprocesses, fed a synthesized PreToolUse payload per
changed file. No handler code is modified or reimplemented.

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

from .config import Config


@dataclass
class Change:
    path: str          # repo-relative or absolute
    content: str       # the new file content (post-change)


@dataclass
class NetResult:
    blocked: bool = False
    reasons: list[str] = field(default_factory=list)

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
            text=True,
            env=env,
            timeout=30,
        )
        return proc.returncode, (proc.stderr or "").strip()
    except Exception as exc:  # noqa: BLE001 - launch failure -> fail-closed sentinel
        return -1, f"launch error for {handler.name}: {type(exc).__name__}: {exc}"


def scan(changes: list[Change], cfg: Config) -> NetResult:
    """Run secret_scan + scope_check over every change.

    Block on any handler exit 2. In ``enforce`` the net also fails CLOSED when a
    configured handler is missing or cannot launch (a net you cannot run is not a
    pass); in ``dryrun`` those degrade to warnings.
    """
    res = NetResult()
    repo = Path(cfg.repo).resolve()
    enforce = cfg.net_enforce
    mode = "enforce" if enforce else "dryrun"

    base_env = dict(os.environ)
    base_env["CLAUDE_SECRET_SCAN_MODE"] = mode
    base_env["CLAUDE_SCOPE_WHITELIST_MODE"] = mode
    # scope_check reads HANDOFF.md ```scope``` from DINNER_HARNESS_HOME.
    base_env["DINNER_HARNESS_HOME"] = str(repo)

    handlers = [("secret_scan", _handler(cfg, "secret_scan")),
                ("scope_check", _handler(cfg, "scope_check"))]

    def _degrade(msg: str) -> None:
        if enforce:
            res.add_block(msg)
        else:
            res.reasons.append("WARN: " + msg)

    for name, handler in handlers:
        if not handler.is_file():
            _degrade(f"{name} handler not found: {handler}")

    for ch in changes:
        abs_path = str((repo / ch.path).resolve()) if not os.path.isabs(ch.path) else ch.path
        payload = {
            "tool_name": "Write",
            "tool_input": {"file_path": abs_path, "content": ch.content},
            "cwd": str(repo),
        }
        for name, handler in handlers:
            if not handler.is_file():
                continue
            code, err = _run_handler(handler, payload, base_env)
            if code == 2:
                res.add_block(f"{name} blocked {ch.path}: {err or 'exit 2'}")
            elif code == -1:
                _degrade(f"{name} could not run on {ch.path}: {err}")
    return res
