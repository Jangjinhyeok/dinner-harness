"""claude target adapter: render the canonical tree into a `.claude` install dir.

stdlib only. Invoked by install.py. Three operations, driven by harness.toml's
[targets.claude]:
  - copy          : verbatim byte-exact copy (file or recursive dir, honoring excludes)
  - template/merge: <USERNAME> + <CLAUDE_HOME> substitution; for JSON dests drop strip_keys; a `merge`
                    entry preserves existing dest keys the template does not own
  - skip_if_exists: write only when the dest does not already exist (never clobber)

Returns a plan: list of (action, dest_path) describing what was (or would be) done.
"""
import json
import shutil
from pathlib import Path


_PERMISSION_RULE_LISTS = ("allow", "ask", "deny")


def _stable_union(existing, rendered):
    """Return ordered, duplicate-free permission rules from both install states."""
    merged = []
    for rules in (existing, rendered):
        for rule in rules:
            if rule not in merged:
                merged.append(rule)
    return merged


def _merge_template_json(existing, rendered):
    """Merge a rendered template without clobbering user permission policy.

    The template owns its top-level keys, but Claude permission rule lists are an
    additive policy surface: preserving existing rules avoids changing a user's
    approval posture when harness adds one required dispatch rule.
    """
    merged = {**existing, **rendered}
    existing_permissions = existing.get("permissions")
    rendered_permissions = rendered.get("permissions")
    if not isinstance(existing_permissions, dict) or not isinstance(rendered_permissions, dict):
        return merged

    permissions = {**existing_permissions, **rendered_permissions}
    for key in _PERMISSION_RULE_LISTS:
        old_rules = existing_permissions.get(key)
        new_rules = rendered_permissions.get(key)
        if isinstance(old_rules, list) and isinstance(new_rules, list):
            permissions[key] = _stable_union(old_rules, new_rules)
    merged["permissions"] = permissions
    return merged


def _excluded(rel, exclude_dirs, exclude_suffixes):
    return any(part in exclude_dirs for part in rel.parts) or rel.name.endswith(exclude_suffixes)


def _copy_tree(src, dest, exclude_dirs, exclude_suffixes, plan, dry_run):
    for f in sorted(src.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(src)
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
    token = vars_cfg.get("username_token", "<USERNAME>")
    home_token = vars_cfg.get("claude_home_token", "<CLAUDE_HOME>")
    exclude_dirs = set(target_cfg.get("exclude_dir_names", []))
    exclude_suffixes = tuple(target_cfg.get("exclude_file_suffixes", []))
    templated_dests = {dest_root / entry["dest"] for entry in target_cfg.get("template", [])}
    plan = []

    # 1. verbatim copies
    for src_rel, dest_rel in target_cfg.get("copy", []):
        _copy_one(repo_root / src_rel, dest_root / dest_rel, exclude_dirs, exclude_suffixes, plan, dry_run)

    # A bulk copy may include a path that the template pass overwrites. Keep the
    # copy itself, but report only the final rendered action for that destination.
    plan = [
        (action, dest)
        for action, dest in plan
        if not (action == "copy" and dest in templated_dests)
    ]

    # 2. templated / merged files (variable substitution; JSON strip_keys). A `merge`
    #    entry preserves existing-dest keys the template does not own (e.g. runtime
    #    flags like skipWorkflowUsageWarning) so install does not clobber machine state.
    #    Written as bytes so line endings are not platform-translated.
    for entry in target_cfg.get("template", []):
        src = repo_root / entry["src"]
        dest = dest_root / entry["dest"]
        text = src.read_text(encoding="utf-8").replace(token, username).replace(home_token, dest_root.as_posix())
        strip_keys = entry.get("strip_keys", [])
        merge = entry.get("merge", False)
        if dest.name.endswith(".json") and (strip_keys or merge):
            data = json.loads(text)
            for k in strip_keys:
                data.pop(k, None)
            if merge and dest.is_file():
                existing = json.loads(dest.read_text(encoding="utf-8"))
                data = _merge_template_json(existing, data)
            text = json.dumps(data, indent=2) + "\n"
        plan.append(("merge" if merge else "template", dest))
        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(text.encode("utf-8"))

    # 3. skip-if-exists workflow files
    for src_rel, dest_rel in target_cfg.get("skip_if_exists", []):
        dest = dest_root / dest_rel
        if dest.exists():
            plan.append(("skip", dest))
            continue
        plan.append(("write", dest))
        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(repo_root / src_rel, dest)

    return plan
