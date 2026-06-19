"""codex target adapter: render the canonical tree into a Codex install dir.

stdlib only. Invoked by install.py. Same install() signature as claude.py.

Cycle 3 / adapter v2 targets current Codex (0.140+ / 0.141 observed):
  - copy        : curated AGENTS.md + inert reference dirs
  - skills      : portable subset under Codex skills
  - hooks       : native hooks.json + copied Python handlers/lib/rules
  - agents      : content/agents/*.md -> agents/*.toml

Still not mapped: Claude _mode path-glob injection and routing alias skills.
Those remain documented in CODEX-COVERAGE.md.
"""
import json
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


def _toml_string(value):
    return json.dumps(str(value), ensure_ascii=False)


def _toml_multiline(value):
    escaped = str(value).replace('"""', '\\"\\"\\"')
    return f'"""{escaped}"""'


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


def _agent_toml(src, rel_group):
    text = src.read_text(encoding="utf-8")
    meta, body = _frontmatter(text)
    name = meta.get("name") or src.stem
    description = meta.get("description") or f"Ported dinner-harness agent: {name}"
    preamble = f"""Ported from dinner-harness content/agents/{rel_group}/{src.name}.

Codex custom-agent notes:
- Follow the instructions below as developer instructions for this spawned agent.
- If the original text mentions Claude-specific Task/subagent mechanics, translate that to Codex subagent language.
- Codex subagents are explicitly spawned and inherit the parent sandbox/approval policy.
- Keep delegation shallow: do not rely on recursive grandchildren. If a deeper specialist is needed, return a concise recommendation to the parent session so the parent can spawn the right specialist directly.

"""
    return "\n".join([
        f"name = {_toml_string(name)}",
        f"description = {_toml_string(description)}",
        f"developer_instructions = {_toml_multiline(preamble + body)}",
        "",
    ])


def _write_agents(repo_root, dest_root, agents_src, agents_dest, plan, dry_run):
    src_root = repo_root / agents_src
    dest = dest_root / agents_dest
    for f in sorted(src_root.rglob("*.md")):
        rel = f.relative_to(src_root)
        target = dest / f"{f.stem}.toml"
        plan.append(("agent", target))
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(_agent_toml(f, rel.parent.as_posix()), encoding="utf-8", newline="\n")


def _write_hooks_json(dest_root, plan, dry_run):
    hooks_root = dest_root / "hooks" / "handlers"

    def command(name):
        script = (hooks_root / f"{name}.py").as_posix()
        return f'py -3 "{script}"'

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
                {
                    "matcher": "Edit|Write|apply_patch",
                    "hooks": [{"type": "command", "command": command("suggest_compact"), "timeout": 30}],
                },
            ],
            "PostToolUse": [
                {
                    "matcher": "Bash|PowerShell",
                    "hooks": [{"type": "command", "command": command("learning_log"), "timeout": 30}],
                }
            ],
            "UserPromptSubmit": [
                {"hooks": [{"type": "command", "command": command("route_nudge"), "timeout": 30}]}
            ],
        }
    }
    target = dest_root / "hooks.json"
    plan.append(("hooks_json", target))
    if not dry_run:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


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

    # 3. hooks: copy portable Python implementation, but do not copy Claude
    # launchers (they intentionally point at Claude home). Codex hooks.json calls
    # handlers directly with the actual dest_root.
    for src_rel, dest_rel in target_cfg.get("hooks_copy", []):
        _copy_one(repo_root / src_rel, dest_root / dest_rel, exclude_dirs, exclude_suffixes, plan, dry_run)
    if target_cfg.get("hooks_json", False):
        _write_hooks_json(dest_root, plan, dry_run)

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

    return plan

