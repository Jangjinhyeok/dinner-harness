"""dinner-harness installer — renders the canonical tree into a target tree.

Usage:
  py -3 install.py --target claude [--dest PATH] [--username NAME] [--dry-run]

stdlib only (tomllib, argparse, importlib). The per-target rendering lives in
adapters/<target>.py; this entry point just loads harness.toml and dispatches.
"""
import argparse
import importlib.util
import os
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent


def load_adapter(name):
    path = REPO_ROOT / "adapters" / f"{name}.py"
    if not path.is_file():
        sys.exit(f"error: no adapter for target '{name}' ({path} missing)")
    spec = importlib.util.spec_from_file_location(f"_adapter_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def default_dest(target):
    return Path.home() / f".{target}"


def main():
    ap = argparse.ArgumentParser(description="Install the dinner-harness into a target.")
    ap.add_argument("--target", required=True, choices=["claude", "codex"])
    ap.add_argument("--dest", default=None, help="install root (default: ~/.<target>)")
    ap.add_argument("--username", default=os.environ.get("USERNAME") or os.environ.get("USER") or "")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-live", action="store_true",
                    help="permit installing onto the live ~/.<target> (guarded off by default)")
    args = ap.parse_args()

    with open(REPO_ROOT / "harness.toml", "rb") as f:
        manifest = tomllib.load(f)

    target_cfg = manifest.get("targets", {}).get(args.target)
    if target_cfg is None:
        sys.exit(f"error: target '{args.target}' not defined in harness.toml")

    dest = Path(args.dest) if args.dest else default_dest(args.target)
    if dest.resolve() == default_dest(args.target).resolve() and not args.allow_live:
        sys.exit(f"refusing to write to the live {dest} — pass --dest <scratch> or --allow-live")

    adapter = load_adapter(args.target)
    plan = adapter.install(
        repo_root=REPO_ROOT,
        target_cfg=target_cfg,
        vars_cfg=manifest.get("vars", {}),
        dest_root=dest,
        username=args.username,
        dry_run=args.dry_run,
    )

    mode = "DRY-RUN" if args.dry_run else "INSTALL"
    print(f"[{mode}] target={args.target} dest={dest} username={args.username!r}")
    counts = {}
    for action, _ in plan:
        counts[action] = counts.get(action, 0) + 1
    print("plan:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())), f"(total {len(plan)})")
    for action, p in plan:
        if action in ("template", "skip", "write"):
            print(f"  {action:8} {p}")


if __name__ == "__main__":
    main()
