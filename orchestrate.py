"""Cross-vendor Two-CLI orchestrator — CLI entry.

Drives an Architect vendor and a Builder vendor (Codex / Claude, either way)
through the HANDOFF/RESULT file bus, with the human invoked only at the
boundaries risk-tiered autonomy keeps. Stdlib only.

  py -3 orchestrate.py run --goal "..." --backend mock --yes
  py -3 orchestrate.py run --goal "..." --architect codex --builder claude \
      --backend real --repo C:/path/to/work-repo

See orchestrator/README.md. `--backend mock` runs fully offline (no CLIs needed)
and is the smoke path; `--backend real` shells out to `claude -p` / `codex exec`
(verify flags on your machine first).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from orchestrator.config import Config
from orchestrator.controller import (
    AutoApprove,
    Orchestrator,
    TerminalGate,
    DONE,
    HELD,
)
from orchestrator.vendors import MockBackend, default_low_scenario, make_backend


def _build_config(args: argparse.Namespace) -> Config:
    return Config(
        repo=Path(args.repo).resolve(),
        goal=args.goal,
        architect_vendor=args.architect,
        builder_vendor=args.builder,
        architect_model=args.architect_model or "",
        builder_model=args.builder_model or "",
        backend=args.backend,
        max_cycles=args.max_cycles,
        confirm_handoff=not args.no_confirm_handoff,
        auto_approve=args.yes,
        allow_auto_approve_real=args.dangerously_auto_approve_real,
        net_enforce=not args.net_dryrun,
    )


def _run(args: argparse.Namespace) -> int:
    cfg = _build_config(args)
    problems = cfg.validate()
    if problems:
        for p in problems:
            print(f"config error: {p}", file=sys.stderr)
        return 2

    if cfg.backend == "mock":
        mock = MockBackend(default_low_scenario(cfg.goal))
        architect = builder = mock
    else:
        architect = make_backend(cfg.architect_vendor)
        builder = make_backend(cfg.builder_vendor)

    human = AutoApprove() if cfg.auto_approve else TerminalGate()

    print(
        f"[orchestrator] backend={cfg.backend} "
        f"architect={cfg.architect_vendor} builder={cfg.builder_vendor} "
        f"repo={cfg.repo}"
    )
    outcome = Orchestrator(cfg, architect, builder, human).run()
    print(f"\n[outcome] {outcome.status} after {outcome.cycles} cycle(s): {outcome.reason}")
    return 0 if outcome.status in (DONE, HELD) else 1


def main(argv: list[str] | None = None) -> int:
    # Logs carry em-dashes / Korean; force UTF-8 stdout regardless of the console
    # codepage (mirrors check.py).
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="Cross-vendor Two-CLI orchestrator.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run the Architect<->Builder loop")
    r.add_argument("--goal", required=True, help="what to build (the intent)")
    r.add_argument("--repo", default=".", help="work repo (default: cwd)")
    r.add_argument("--architect", default="codex", choices=["codex", "claude"])
    r.add_argument("--builder", default="claude", choices=["codex", "claude"])
    r.add_argument("--architect-model", default="")
    r.add_argument("--builder-model", default="")
    r.add_argument("--backend", default="mock", choices=["mock", "real"])
    r.add_argument("--max-cycles", type=int, default=5)
    r.add_argument("--no-confirm-handoff", action="store_true",
                   help="skip the start-gate HANDOFF confirmation")
    r.add_argument("--yes", action="store_true",
                   help="auto-approve every human gate (mock / CI / unattended)")
    r.add_argument("--dangerously-auto-approve-real", action="store_true",
                   help="permit --yes together with --backend real (auto-signs HIGH changes)")
    r.add_argument("--net-dryrun", action="store_true",
                   help="run the safety net in dryrun (warn) instead of enforce")
    r.set_defaults(func=_run)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
