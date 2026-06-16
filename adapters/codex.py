"""codex target adapter: render the portable subset of the canonical tree into a
`.codex` install dir.

stdlib only. Invoked by install.py. Same install() signature as claude.py, but a
pure transform-by-selection (no templating): Codex has no <USERNAME>-style machine
paths in its content. Driven by harness.toml's [targets.codex]:
  - copy        : verbatim byte-exact copy (file or recursive dir, honoring excludes)
  - skills      : copy skills_src -> skills_dest, dropping the Claude-machinery skills
                  listed in skills_drop (D8 — they route to Claude subagents/hooks)

Claude-only machinery (agents, hooks, roles, agent-routing, _mode) is NOT mapped here;
it is dropped and accounted for in CODEX-COVERAGE.md.

Copy primitives are intentionally duplicated from claude.py (a frozen Cycle-1 artifact)
to keep the two adapters decoupled.
"""
import shutil
from pathlib import Path


def _excluded(rel, exclude_dirs, exclude_suffixes):
    return any(part in exclude_dirs for part in rel.parts) or rel.name.endswith(exclude_suffixes)


def _copy_tree(src, dest, exclude_dirs, exclude_suffixes, plan, dry_run, drop_top=()):
    for f in sorted(src.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(src)
        if rel.parts and rel.parts[0] in drop_top:
            continue
        if _excluded(rel, exclude_dirs, exclude_suffixes):
            continue
        target = dest / rel
        plan.append(("copy", target))
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)


def _copy_one(src, dest, exclude_dirs, exclude_suffixes, plan, dry_run):
    if src.is_dir():
        _copy_tree(src, dest, exclude_dirs, exclude_suffixes, plan, dry_run)
    else:
        plan.append(("copy", dest))
        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)


def install(repo_root, target_cfg, vars_cfg, dest_root, username, dry_run):
    repo_root = Path(repo_root)
    dest_root = Path(dest_root)
    exclude_dirs = set(target_cfg.get("exclude_dir_names", []))
    exclude_suffixes = tuple(target_cfg.get("exclude_file_suffixes", []))
    plan = []

    # 1. verbatim copies (curated AGENTS.md + inert reference dirs)
    for src_rel, dest_rel in target_cfg.get("copy", []):
        _copy_one(repo_root / src_rel, dest_root / dest_rel, exclude_dirs, exclude_suffixes, plan, dry_run)

    # 2. skills: copy the portable subset, dropping Claude-machinery skills (D8)
    skills_src = target_cfg.get("skills_src")
    if skills_src:
        drop_top = set(target_cfg.get("skills_drop", []))
        _copy_tree(
            repo_root / skills_src,
            dest_root / target_cfg.get("skills_dest", "skills"),
            exclude_dirs, exclude_suffixes, plan, dry_run, drop_top=drop_top,
        )

    return plan
