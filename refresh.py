"""Refresh selected live dinner-harness targets from this canonical repository.

Usage:
  py -3 refresh.py          # validate source and preview both target installs
  py -3 refresh.py --apply  # explicit live-install approval, then verify drift
  py -3 refresh.py --target codex  # Codex-only source validation and preview

This intentionally owns no rendering logic. ``install.py`` remains the only
writer for a target, and ``check.py`` remains the source/install conformance
checker. ``--apply`` is the human signature required before either live target
is changed. The two in-place installs are not transactional; a failed second
target is reported and must be repaired by re-running from the desired commit.
"""
from __future__ import annotations

import argparse
import sys

import check
import install


_TARGETS = ("claude", "codex")


def _run(callable_, argv: list[str]) -> int:
    """Normalize the root CLI convention and stop refresh at a failed boundary."""
    result = callable_(argv)
    return 0 if result is None else result


def _preflight(check_args: list[str]) -> int:
    print("[refresh] source preflight")
    return _run(check.main, ["--no-install", *check_args])


def _install_targets(targets: tuple[str, ...], *, dry_run: bool) -> int:
    for target in targets:
        print(f"[refresh] {'preview' if dry_run else 'install'} target={target}")
        argv = ["--target", target, "--allow-live"]
        if dry_run:
            argv.append("--dry-run")
        status = _run(install.main, argv)
        if status:
            return status
    return 0


def refresh(*, apply: bool, target: str = "all") -> int:
    """Validate source, preview selected targets, and apply only on explicit request."""
    selected = _TARGETS if target == "all" else (target,)
    check_args = [] if target == "all" else ["--target", target]
    status = _preflight(check_args)
    if status:
        return status

    status = _install_targets(selected, dry_run=True)
    if status:
        return status

    if not apply:
        print("[refresh] PREVIEW complete - rerun with --apply and the same --target to install.")
        return 0

    status = _install_targets(selected, dry_run=False)
    if status:
        return status

    print("[refresh] live conformance check")
    return _run(check.main, check_args)


def _parse_args(argv: list[str] | None):
    parser = argparse.ArgumentParser(
        description="Preview or explicitly apply selected harness targets."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="install selected live targets after preflight; omitted means dry-run only",
    )
    parser.add_argument("--target", choices=["codex", "claude", "all"], default="all")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    return refresh(apply=args.apply, target=args.target)


if __name__ == "__main__":
    raise SystemExit(main())
