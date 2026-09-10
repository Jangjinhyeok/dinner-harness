"""codex target adapter: render the canonical tree into a Codex install dir.

stdlib only. Invoked by install.py. Same install() signature as claude.py.

Current native rendering (historical runtime observations: CODEX-COVERAGE.md):
  - copy        : inert reference dirs
  - template    : curated AGENTS.md with plain-text variable substitution
  - skills      : portable subset under Codex skills
  - hooks       : native hooks.json + copied Python handlers/lib/rules
  - agents      : content/agents/*.md -> agents/*.toml

Claude _mode path-glob injection remains target-specific. Engine entry skills
use explicit reference reads; copied rules do not imply automatic injection.
"""
import json
import hashlib
import os
import shlex
import shutil
import sys
import tempfile
import tomllib
import uuid
from pathlib import Path

from orchestrator.routing import load_routing_config, resolve_profile

OWNERSHIP = ".dinner-harness-owned.json"


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


def _write_skills(src, dest, exclude_dirs, exclude_suffixes, plan, dry_run, drop_top):
    _copy_tree(src, dest, exclude_dirs, exclude_suffixes, plan, dry_run, drop_top)
    if dry_run:
        return
    for skill in dest.glob("*/SKILL.md"):
        meta, body = _frontmatter(skill.read_text(encoding="utf-8"))
        if not isinstance(meta.get("name"), str) or not isinstance(meta.get("description"), str):
            raise RuntimeError(f"skill requires string name/description: {skill}")
        # Only supported discovery fields; Claude tool/model directives are not copied.
        header = "---\n" + "\n".join(f"{key}: {_toml_string(meta[key])}" for key in ("name", "description"))
        skill.write_text(header + "\n---\n\n" + body, encoding="utf-8", newline="\n")
        for index, (action, path) in enumerate(plan):
            if path == skill:
                plan[index] = ("skill", path)


def _toml_string(value):
    return json.dumps(str(value), ensure_ascii=False)


def _toml_multiline(value):
    # A JSON basic string is valid TOML and preserves all backslashes/newlines.
    return _toml_string(value)


def _frontmatter(text):
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    raw = text[3:end].strip("\n")
    body = text[end + len("\n---"):].lstrip("\n")
    data = {}
    current_key = None
    for line in raw.splitlines():
        if not line.strip():
            continue
        if line.startswith("  - ") and current_key:
            data.setdefault(current_key, []).append(line[4:].strip())
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        current_key = key
        if not value:
            data[key] = []
        elif value.startswith("[") and value.endswith("]"):
            try:
                data[key] = json.loads(value)
            except json.JSONDecodeError:
                data[key] = value
        else:
            data[key] = value.strip('"')
    return data, body


def _agent_toml(src, rel_group, routing=None):
    text = src.read_text(encoding="utf-8")
    meta, body = _frontmatter(text)
    name = meta.get("name") or src.stem
    description = meta.get("description") or f"Ported dinner-harness agent: {name}"
    if routing is None:
        routing = load_routing_config(Path(__file__).resolve().parents[1] / "content/routing.toml")
    role = routing.get("native_agents", {}).get(name)
    if not isinstance(role, str):
        raise RuntimeError(f"native agent {name!r} has no logical role in routing.toml")
    profile = resolve_profile(routing, "codex_only", role)
    if profile.vendor != "codex":
        raise RuntimeError(f"native Codex agent {name!r} resolves to {profile.vendor!r}")
    sandbox = "read-only" if role in {"architect", "reviewer", "explorer"} else "workspace-write"
    preamble = (f"Source: dinner-harness content/agents/{rel_group}/{src.name}.\n"
                "Work only within the parent's assigned scope. Return findings and verification evidence to the parent.\n\n")
    return "\n".join([
        f"name = {_toml_string(name)}",
        f"description = {_toml_string(description)}",
        f"model = {_toml_string(profile.model)}",
        f"model_reasoning_effort = {_toml_string(profile.effort)}",
        f"sandbox_mode = {_toml_string(sandbox)}",
        f"developer_instructions = {_toml_multiline(preamble + body)}",
        "",
    ])


def _write_agents(repo_root, dest_root, agents_src, agents_dest, plan, dry_run):
    routing = None
    src_root = repo_root / agents_src
    dest = dest_root / agents_dest
    seen: dict[str, Path] = {}
    for f in sorted(src_root.rglob("*.md")):
        rel = f.relative_to(src_root)
        if f.stem in seen:
            raise RuntimeError(
                f"duplicate agent stem {f.stem!r}: {seen[f.stem]} and {f} both "
                f"flatten to {f.stem}.toml — rename one before installing"
            )
        seen[f.stem] = f
        target = dest / f"{f.stem}.toml"
        plan.append(("agent", target))
        if not dry_run:
            if routing is None:
                routing = load_routing_config(repo_root / "content/routing.toml")
            target.parent.mkdir(parents=True, exist_ok=True)
            rendered = _agent_toml(f, rel.parent.as_posix(), routing)
            tomllib.loads(rendered)
            target.write_text(rendered, encoding="utf-8", newline="\n")


def _write_hooks_json(dest_root, plan, dry_run, command_root=None):
    hooks_root = (command_root or dest_root) / "hooks" / "handlers"

    def command(name):
        script = (hooks_root / f"{name}.py").as_posix()
        argv = [Path(sys.executable).as_posix(), script]
        # Always quote Windows paths, including a path with '&' but no spaces.
        return " ".join(f'"{arg}"' for arg in argv) if os.name == "nt" else shlex.join(argv)

    data = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Edit|Write|Bash|PowerShell|apply_patch",
                    "hooks": [{"type": "command", "command": command("secret_scan"), "timeout": 30}],
                },
                {
                    "matcher": "Edit|Write|apply_patch",
                    "hooks": [{"type": "command", "command": command("scope_check"), "timeout": 30}],
                },
            ],
            # Native compaction is preferred. Learning-log capture is opt-in;
            # automatic command/error capture can retain sensitive content.
            # route_nudge is Claude-specific: a standalone Codex session cannot
            # dispatch itself to a Codex Builder. Codex gets its routing guidance
            # from AGENTS.md instead.
        }
    }
    target = dest_root / "hooks.json"
    plan.append(("hooks_json", target))
    if not dry_run:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def _render(repo_root, target_cfg, vars_cfg, dest_root, username, dry_run):
    repo_root = Path(repo_root)
    dest_root = Path(dest_root)
    exclude_dirs = set(target_cfg.get("exclude_dir_names", []))
    exclude_suffixes = tuple(target_cfg.get("exclude_file_suffixes", []))
    plan = []

    # 1. verbatim copies (inert reference dirs)
    for src_rel, dest_rel in target_cfg.get("copy", []):
        _copy_one(repo_root / src_rel, dest_root / dest_rel, exclude_dirs, exclude_suffixes, plan, dry_run)

    # 2. portable skill bodies with supported Codex discovery frontmatter.
    skills_src = target_cfg.get("skills_src")
    if skills_src:
        drop_top = set(target_cfg.get("skills_drop", []))
        _write_skills(
            repo_root / skills_src,
            dest_root / target_cfg.get("skills_dest", "skills"),
            exclude_dirs, exclude_suffixes, plan, dry_run, drop_top=drop_top,
        )

    # 3. hooks: copy portable Python implementation, but do not copy Claude
    # launchers (they intentionally point at Claude home). Codex hooks.json calls
    # handlers directly with the actual dest_root.
    for src_rel, dest_rel in target_cfg.get("hooks_copy", []):
        _copy_one(repo_root / src_rel, dest_root / dest_rel, exclude_dirs, exclude_suffixes, plan, dry_run)
    if target_cfg.get("hooks_json", False):
        _write_hooks_json(dest_root, plan, dry_run, target_cfg.get("_hooks_command_root"))

    # 4. agents: convert Claude markdown agents to Codex custom-agent TOML.
    if target_cfg.get("agents_src"):
        _write_agents(
            repo_root,
            dest_root,
            target_cfg.get("agents_src"),
            target_cfg.get("agents_dest", "agents"),
            plan,
            dry_run,
        )

    # 5. templated files (plain text substitution only — no JSON handling needed here).
    for entry in target_cfg.get("template", []):
        src = repo_root / entry["src"]
        dest = dest_root / entry["dest"]
        text = src.read_text(encoding="utf-8")
        plan.append(("template", dest))
        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(text.encode("utf-8"))

    return plan


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _merge_hooks(existing, desired, owned):
    """Replace only exact prior-owned entries; preserve unrelated user hooks."""
    if not isinstance(existing, dict) or not isinstance(existing.get("hooks", {}), dict):
        raise RuntimeError("hooks.json must contain an object with a hooks object")
    merged = json.loads(json.dumps(existing))
    events = merged.setdefault("hooks", {})
    for event in set(owned) | set(desired.get("hooks", {})):
        entries = events.get(event, [])
        if not isinstance(entries, list):
            raise RuntimeError(f"hooks.json hooks.{event} must be an array")
        remaining = list(entries)
        for old in owned.get(event, []):
            if old in remaining:
                remaining.remove(old)
        for new in desired.get("hooks", {}).get(event, []):
            if new not in remaining:
                remaining.append(new)
        events[event] = remaining
    return merged


def _legacy_hooks(root):
    """Exact adapter-v2 definitions, used only by explicit legacy adoption."""
    definitions = (
        ("PreToolUse", "secret_scan", "Edit|Write|Bash|PowerShell|apply_patch"),
        ("PreToolUse", "scope_check", "Edit|Write|apply_patch"),
        ("PreToolUse", "suggest_compact", "Edit|Write|apply_patch"),
        ("PostToolUse", "learning_log", "Bash|PowerShell"),
    )
    for event, name, matcher in definitions:
        script = (root / "hooks" / "handlers" / f"{name}.py").as_posix()
        yield event, name, {"matcher": matcher, "hooks": [
            {"type": "command", "command": f'py -3 "{script}"', "timeout": 30}
        ]}


def _preflight_path(root, path):
    """Reject leaf/ancestor conflicts before any install or backup write."""
    if path.is_symlink() or root not in path.resolve().parents:
        raise RuntimeError(f"install path escapes destination or is a symlink: {path}")
    if path.exists() and not path.is_file():
        raise RuntimeError(f"install target is not a file: {path}")
    for parent in path.parents:
        if parent.exists() and not parent.is_dir():
            raise RuntimeError(f"install parent is not a directory: {parent}")
        if parent == root:
            break


def install(repo_root, target_cfg, vars_cfg, dest_root, username, dry_run):
    """Render first, preflight ownership, then update only proven-owned files.

    A legacy installation without an ownership receipt is never assumed owned.
    Identical files can be adopted; conflicts need an explicit migration decision.
    Obsolete discovery files are backed up and retired only when still owned
    and unchanged. Other obsolete entries remain for manual review.
    """
    repo_root, dest_root = Path(repo_root), Path(dest_root).resolve()
    state_path = dest_root / OWNERSHIP
    _preflight_path(dest_root, state_path)
    if state_path.is_symlink():
        raise RuntimeError(f"ownership receipt must not be a symlink: {state_path}")
    if state_path.exists() and not state_path.is_file():
        raise RuntimeError(f"ownership receipt is not a file: {state_path}")
    old = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    if (not isinstance(old, dict) or not isinstance(old.get("files", {}), dict)
            or not isinstance(old.get("hooks", {}), dict)
            or (old and old.get("version") != 1)
            or any(not isinstance(entries, list) for entries in old.get("hooks", {}).values())):
        raise RuntimeError(f"invalid ownership receipt: {state_path}")
    writes, plan, backups, retirements = [], [], [], []
    backup_root = dest_root / ".dinner-harness-backups" / uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix="dh-render-") as temp:
        scratch = Path(temp)
        render_cfg = dict(target_cfg, _hooks_command_root=target_cfg.get("_hooks_command_root", dest_root))
        rendered = _render(repo_root, render_cfg, vars_cfg, scratch, username, False)
        files = dict(old.get("files", {}))
        desired_paths = {path.relative_to(scratch).as_posix() for _, path in rendered}
        # Only discovery entries can remain accidentally active after selection
        # changes. Never prune unknown files, user edits, or reference/log trees.
        for rel in sorted(set(files) - desired_paths):
            relative = Path(rel)
            if relative.is_absolute() or ".." in relative.parts:
                raise RuntimeError(f"invalid obsolete ownership path: {rel}")
            if not ((len(relative.parts) == 3 and relative.parts[0] == "skills"
                     and relative.name == "SKILL.md")
                    or (len(relative.parts) == 2 and relative.parts[0] == "agents"
                        and relative.suffix == ".toml")):
                continue
            target = dest_root / relative
            _preflight_path(dest_root, target)
            if any(parent.is_symlink() for parent in target.parents if parent != dest_root):
                raise RuntimeError(f"obsolete discovery path has a symlink ancestor: {target}")
            if not target.exists():
                files.pop(rel)
                continue
            current = target.read_bytes()
            if files[rel] != _digest(current):
                plan.append(("skip", target))
                continue
            backup = backup_root / relative
            _preflight_path(dest_root, backup)
            backups.append((backup, current))
            plan.extend([("backup", backup), ("retire_owned", target)])
            retirements.append(target)
            files.pop(rel)
        hooks_owned = old.get("hooks", {})
        for action, generated in rendered:
            rel = generated.relative_to(scratch).as_posix()
            target = dest_root / rel
            _preflight_path(dest_root, target)
            data = generated.read_bytes()
            if action == "hooks_json":
                desired = json.loads(data)
                existing = json.loads(target.read_text(encoding="utf-8")) if target.is_file() else {}
                adopted = {event: list(entries) for event, entries in hooks_owned.items()}
                hook_retirements = []
                if target_cfg.get("adopt_existing", False):
                    for event, name, legacy in _legacy_hooks(dest_root):
                        entries = existing.get("hooks", {}).get(event, [])
                        if legacy in entries:
                            adopted.setdefault(event, []).append(legacy)
                            hook_retirements.append((f"retire_hook:{name}", target))
                if hook_retirements:
                    backup = backup_root / rel
                    _preflight_path(dest_root, backup)
                    backups.append((backup, target.read_bytes()))
                    plan.append(("backup", backup))
                    plan.extend(hook_retirements)
                merged = _merge_hooks(existing, desired, adopted)
                hooks_owned = desired["hooks"]
                data = (json.dumps(merged, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
            elif target.exists():
                current = target.read_bytes()
                if current != data and files.get(rel) != _digest(current):
                    if not target_cfg.get("adopt_existing", False):
                        raise RuntimeError(f"unowned or user-modified file conflicts with install: {target}; review --adopt-existing --dry-run to back up and adopt")
                    backup = backup_root / rel
                    _preflight_path(dest_root, backup)
                    backups.append((backup, current))
                    plan.append(("backup", backup))
            files[rel] = _digest(data)
            writes.append((target, data))
            plan.append((action, target))
        state = {"version": 1, "files": files, "hooks": hooks_owned}
        writes.append((state_path, (json.dumps(state, indent=2, ensure_ascii=False) + "\n").encode("utf-8")))
        plan.append(("ownership", state_path))
        if not dry_run:
            for target, data in backups:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            for target in retirements:
                target.unlink()
            for target, data in writes:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
    return plan
