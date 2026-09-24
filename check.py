"""dinner-harness drift-check — advisory, stdlib only.

Checks (CI runs source checks with --no-install; live checks are local):
  1. catalog completeness — the README capability catalog (`## 하네스 구성` / `## What's inside`)
     must list exactly the repo's skills (`content/skills/*/`) + agents (`content/agents`
     frontmatter `name`) + hooks (`assets/claude/hooks/handlers/*.py`), in BOTH READMEs with
     KO/EN parity. Description text is NOT checked — only the item set + group-header counts.
  2. legacy Claude curation — compare `content/instructions/CLAUDE.md` with the blessed hash
     in `curation.toml`. This is not a Codex validation check.
  3. Codex generated output — render into a temp dir and validate native routing, sandbox,
     JSON, and required references, including with `--no-install`.
  4. install drift — compare the repo with LIVE `~/.claude` / `~/.codex`. Render through
     install.py's adapters; normalize path substitutions. `skip_if_exists`
     workflow files (HANDOFF/RESULT) are runtime state and are excluded, a `merge` JSON dest is
     compared on template-owned keys only, and the manifest's own exclude lists apply. Live-only
     leftovers are reported separately for manifest-owned directories and require manual deletion:
     Codex retires only unchanged receipt-owned obsolete skill/agent entrypoints, with backups.
     Other leftovers require manual review. `shared_dirs` leftovers are advisory-only; other
     leftovers affect exit status. Machine-local by nature: `--no-install` skips it.
  5. Codex skill discovery — report duplicate local skill names as advisory; ownership and
     runtime loading are not inferred.

Usage:
  py -3 check.py            run all checks; exit 0 if clean, 1 if drift (human-readable report)
  py -3 check.py --target codex  check Codex generated output and live install
  py -3 check.py --no-install   skip install drift; keep source/generated checks
  py -3 check.py --update   re-bless the legacy Claude source hash
"""
import argparse
import hashlib
import importlib.util
import json
from datetime import datetime, timezone
import os
import re
import sys
import subprocess
import tempfile
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent
CURATION = REPO / "curation.toml"
CLAUDE_MD = REPO / "content/instructions/CLAUDE.md"
MANIFEST = REPO / "harness.toml"
READMES = {"README.md": "## 하네스 구성", "README.en.md": "## What's inside"}
INSTALL_TARGETS = ("claude", "codex")


def frontmatter_name(text):
    if text.startswith("---"):
        end = text.find("\n---", 3)
        fm = text[3:end] if end != -1 else text
    else:
        fm = text
    m = re.search(r"^name:\s*(.+?)\s*$", fm, re.M)
    return m.group(1).strip() if m else None


def actual_sets():
    skills = {d.name for d in (REPO / "content/skills").iterdir() if d.is_dir()}
    agents = set()
    for f in (REPO / "content/agents").rglob("*.md"):
        n = frontmatter_name(f.read_text(encoding="utf-8"))
        if n:
            agents.add(n)
    hooks = {f.stem for f in (REPO / "assets/claude/hooks/handlers").glob("*.py")
             if f.stem != "__init__"}
    return skills, agents, hooks


def catalog_section(text, header):
    i = text.find(header)
    if i == -1:
        return None
    rest = text[i + len(header):]
    j = rest.find("\n## ")
    return rest if j == -1 else rest[:j]


def sha256(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def check_catalog():
    skills, agents, hooks = actual_sets()
    actual = skills | agents | hooks
    declared = {"Skills": len(skills), "Agents": len(agents), "Hooks": len(hooks)}
    problems = []
    per_readme = {}
    for fname, header in READMES.items():
        sec = catalog_section((REPO / fname).read_text(encoding="utf-8"), header)
        if sec is None:
            problems.append(f"{fname}: '{header}' 섹션 없음")
            per_readme[fname] = set()
            continue
        items = set(re.findall(r"^- `([^`]+)`", sec, re.M))
        per_readme[fname] = items
        for name in sorted(actual - items):
            problems.append(f"{fname}: 카탈로그 누락 — `{name}` (repo엔 존재)")
        for name in sorted(items - actual):
            problems.append(f"{fname}: 카탈로그 잉여 — `{name}` (repo엔 부재)")
        for cat, n in declared.items():
            m = re.search(rf"### {cat} \((\d+)\)", sec)
            if m and int(m.group(1)) != n:
                problems.append(f"{fname}: '### {cat} ({m.group(1)})' 헤더 ≠ 실제 {n}")
    if per_readme.get("README.md") != per_readme.get("README.en.md"):
        d = sorted(per_readme.get("README.md", set()) ^ per_readme.get("README.en.md", set()))
        problems.append(f"KO/EN parity 불일치 — {d}")
    return declared, problems


def check_curation():
    if not CLAUDE_MD.is_file():
        return [f"{CLAUDE_MD} 없음"]
    current = sha256(CLAUDE_MD)
    if not CURATION.is_file():
        return ["curation.toml 없음 — `py -3 check.py --update`로 seed"]
    with open(CURATION, "rb") as source:
        blessed = tomllib.load(source).get("claude_md_blessed_hash", "")
    if blessed != current:
        return ["Legacy Claude source hash changed; review Claude compatibility before --update. "
                "This hash is not evidence of Codex policy or generated-artifact validity.",
                "  Review `git diff content/instructions/CLAUDE.md`; Codex uses --target codex generated validation.",
                f"  blessed={blessed[:16]}… current={current[:16]}…"]
    return []


def _installer():
    """Load install.py as a module — its adapter loading and dest defaults stay one source."""
    spec = importlib.util.spec_from_file_location("_dh_install", REPO / "install.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _owned_dirs(target_cfg):
    """Install-root-relative dirs the manifest fills entirely — the only place a live-only
    file is judged stale. Everything else under the install root (settings.local.json,
    projects/, history.jsonl, plugin state) is the runtime's, not ours."""
    dirs = []
    for src_rel, dest_rel in list(target_cfg.get("copy", [])) + list(target_cfg.get("hooks_copy", [])):
        if (REPO / src_rel).is_dir():
            dirs.append(dest_rel)
    if target_cfg.get("skills_src"):
        dirs.append(target_cfg.get("skills_dest", "skills"))
    if target_cfg.get("agents_src"):
        dirs.append(target_cfg.get("agents_dest", "agents"))
    return dirs


def _shared_dir(dir_rel, shared_dirs):
    """Whether an owned directory is explicitly shared with an external tool."""
    normalized = Path(dir_rel).as_posix().rstrip("/")
    return normalized in shared_dirs


def _json_key_drift(rel, want_text, got_text):
    """A `merge` dest keeps existing-dest keys the template does not own, so only the
    rendered keys are ours to check — extra live keys are the point of merging."""
    try:
        want, got = json.loads(want_text), json.loads(got_text)
    except json.JSONDecodeError as e:
        return [f"{rel}: JSON 파싱 실패 — {e}"]
    problems = []
    for k in want:
        if k not in got:
            problems.append(f"{rel}: 설치본에 키 없음 — `{k}`")
        elif k == "permissions" and isinstance(want[k], dict) and isinstance(got[k], dict):
            for permission_key, required in want[k].items():
                if permission_key not in got[k]:
                    problems.append(
                        f"{rel}: permissions에 키 없음 — `{permission_key}`"
                    )
                elif permission_key in {"allow", "ask", "deny"} and isinstance(required, list):
                    actual = got[k][permission_key]
                    if not isinstance(actual, list):
                        problems.append(
                            f"{rel}: permissions.{permission_key} 내용 다름"
                        )
                    else:
                        for rule in required:
                            if rule not in actual:
                                problems.append(
                                    f"{rel}: permissions.{permission_key}에 canonical rule 없음 — `{rule}`"
                                )
                elif got[k][permission_key] != required:
                    problems.append(
                        f"{rel}: permissions.{permission_key} 내용 다름"
                    )
        elif got[k] != want[k]:
            problems.append(f"{rel}: 키 내용 다름 — `{k}`")
    return problems


def _hooks_drift(want_text, got_text):
    try:
        want, got = json.loads(want_text), json.loads(got_text)
        return [f"hooks.json: missing canonical {event} handler"
                for event, entries in want["hooks"].items()
                for entry in entries if entry not in got.get("hooks", {}).get(event, [])]
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        return [f"hooks.json: invalid hook structure ({exc})"]


def check_codex_generated():
    """Validate rendered native config, not a blessed Claude document hash."""
    problems = []
    try:
        with open(MANIFEST, "rb") as source:
            manifest = tomllib.load(source)
        inst = _installer()
        with tempfile.TemporaryDirectory(prefix="dh-codex-source-") as temp:
            dest = Path(temp)
            adapter = inst.load_adapter("codex")
            adapter.install(REPO, manifest["targets"]["codex"], manifest.get("vars", {}), dest, "", False)
            from orchestrator.routing import load_routing_config, resolve_profile
            routing = load_routing_config(dest / "routing.toml")
            for agent in (dest / "agents").glob("*.toml"):
                data = tomllib.loads(agent.read_text(encoding="utf-8"))
                role = routing.get("native_agents", {}).get(data.get("name"))
                profile = resolve_profile(routing, "codex_only", role)
                if (data.get("model"), data.get("model_reasoning_effort")) != (profile.model, profile.effort):
                    problems.append(f"{agent.name}: native routing does not match policy")
                expected_sandbox = "read-only" if role in {"architect", "reviewer", "explorer"} else "workspace-write"
                if data.get("sandbox_mode") != expected_sandbox:
                    problems.append(f"{agent.name}: unexpected sandbox")
            json.loads((dest / "hooks.json").read_text(encoding="utf-8"))
            for relative in manifest["targets"]["codex"].get("required_references", []):
                if not (dest / relative).is_file():
                    problems.append(f"Codex required reference missing: {relative}")
            for skill in (dest / "skills").glob("*/SKILL.md"):
                meta, body = adapter._frontmatter(skill.read_text(encoding="utf-8"))
                if set(meta) != {"name", "description"}:
                    problems.append(f"{skill.parent.name}: unsupported skill frontmatter")
                # Validate explicit relative Markdown links. External/optional home
                # paths are intentionally not guessed from arbitrary prose.
                for link in re.findall(r"\]\((\.\.?/[^)#]+)(?:#[^)]*)?\)", body):
                    if not (skill.parent / link).exists():
                        problems.append(f"{skill.parent.name}: missing relative reference {link}")
    except Exception as exc:
        problems.append(f"Codex generated validation failed: {exc}")
    return problems


def check_install(target, live_root=None, username=None):
    """Compare the rendered manifest against a live install tree.

    Returns (present, drift_problems, leftovers). ``leftovers`` contains
    ``(install-relative path, advisory)`` pairs. present=False means the install root does
    not exist — reported, but not counted as drift: a machine need not use every target.
    """
    with open(MANIFEST, "rb") as manifest_file:
        manifest = tomllib.load(manifest_file)
    target_cfg = manifest.get("targets", {}).get(target)
    if target_cfg is None:
        return True, [f"harness.toml에 target '{target}' 없음"], []
    inst = _installer()
    live = Path(live_root) if live_root else inst.default_dest(target)
    if target == "codex":
        live = inst.normalize_dest(live)
    if not live.is_dir():
        return False, [], []
    if username is None:
        username = os.environ.get("USERNAME") or os.environ.get("USER") or ""

    exclude_dirs = set(target_cfg.get("exclude_dir_names", []))
    exclude_suffixes = tuple(target_cfg.get("exclude_file_suffixes", []))
    runtime = {dest_rel for _, dest_rel in target_cfg.get("skip_if_exists", [])}
    problems = []
    leftovers = []
    codex_owned = set()
    if target == "codex":
        receipt = live / ".dinner-harness-owned.json"
        if receipt.is_file():
            try:
                codex_owned = set(json.loads(receipt.read_text(encoding="utf-8"))["files"])
            except (OSError, ValueError, KeyError, TypeError):
                problems.append("Codex ownership receipt is invalid; ownership cannot be established")
    shared_dirs = {
        Path(dir_rel).as_posix().rstrip("/")
        for dir_rel in target_cfg.get("shared_dirs", [])
    }

    with tempfile.TemporaryDirectory(prefix="dh-check-") as td:
        scratch = (Path(td) / f".{target}").resolve()
        if scratch.resolve() == live.resolve():  # never render onto the tree we are judging
            return True, [f"scratch dest가 live와 동일 — 비교 불가 ({live})"], []
        adapter = inst.load_adapter(target)
        if target == "codex":
            target_cfg = dict(target_cfg, _hooks_command_root=live.resolve())
        plan = adapter.install(
            repo_root=REPO, target_cfg=target_cfg, vars_cfg=manifest.get("vars", {}),
            dest_root=scratch, username=username, dry_run=False,
        )
        expected = set()
        for action, dest in plan:
            if action == "ownership":
                continue
            rel = Path(dest).relative_to(scratch).as_posix()
            if rel in runtime:  # HANDOFF.md / RESULT.md are live workflow state, never drift
                continue
            expected.add(rel)
            live_p = live / rel
            if not live_p.is_file():
                problems.append(f"{rel}: 설치본에 없음 — install.py 미실행")
                continue
            if action == "copy":  # verbatim, byte-exact by construction
                if Path(dest).read_bytes() != live_p.read_bytes():
                    problems.append(f"{rel}: 설치본 내용 다름")
                continue
            # Everything else is generated and may embed the dest root — the templated
            # <CLAUDE_HOME>, and codex hooks.json's absolute handler paths. Re-point the
            # scratch root at the live one so this compares content, not where we rendered.
            want = Path(dest).read_text(encoding="utf-8").replace(
                scratch.as_posix(), live.as_posix())
            try:
                got = live_p.read_text(encoding="utf-8")
            except UnicodeDecodeError:  # a mangled live file is drift, not a traceback
                problems.append(f"{rel}: 설치본이 UTF-8로 안 읽힘 — 손상")
                continue
            if action == "hooks_json":
                problems += _hooks_drift(want, got)
            elif action == "merge" and rel.endswith(".json"):
                problems += _json_key_drift(rel, want, got)
            elif want != got:
                problems.append(f"{rel}: 설치본 내용 다름 ({action})")

    for dir_rel in _owned_dirs(target_cfg):
        root = live / dir_rel
        if not root.is_dir():
            continue
        for f in sorted(root.rglob("*")):
            if not f.is_file():
                continue
            sub = f.relative_to(root)
            if any(p in exclude_dirs for p in sub.parts) or f.name.endswith(exclude_suffixes):
                continue
            rel = f.relative_to(live).as_posix()
            if rel in expected:
                continue
            # Vendors drop their own state into these dirs under a dot prefix (Codex ships
            # `skills/.system/**`, marked by its own `.codex-system-skills.marker`). The
            # manifest installs no dot-named path inside an owned dir, so a dot entry here
            # can never be a stale render of ours.
            if any(part.startswith(".") for part in sub.parts):
                continue
            advisory = _shared_dir(dir_rel, shared_dirs)
            if target == "codex" and rel not in codex_owned:
                advisory = True  # Unknown user files are not proven stale harness output.
            leftovers.append((rel, advisory))
    return True, problems, leftovers


def do_update():
    blessed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    h = sha256(CLAUDE_MD)
    CURATION.write_text(
        "# curation drift manifest — read by check.py. Re-bless: `py -3 check.py --update`.\n"
        "# claude_md_blessed_hash = content/instructions/CLAUDE.md at the last AGENTS.md curation.\n"
        f'claude_md_blessed_hash = "{h}"\n'
        f'blessed_at = "{blessed_at}"\n',
        encoding="utf-8")
    print(f"re-blessed CLAUDE.md hash → curation.toml ({h[:16]}…, blessed_at={blessed_at})")


def skill_discovery_roots(cwd=None, home=None, codex_home=None):
    """Known local roots, not proof of runtime loading or a plugin inventory."""
    cwd = Path(cwd or Path.cwd()).resolve()
    home = Path(home or Path.home()).expanduser().resolve()
    codex_home = Path(codex_home or os.environ.get("CODEX_HOME") or home / ".codex").expanduser()
    roots = [codex_home / "skills", home / ".agents/skills"]
    try:
        result = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
                                capture_output=True, text=True, timeout=10)
        top = Path(result.stdout.strip()).resolve() if result.returncode == 0 else cwd
    except (OSError, subprocess.TimeoutExpired):
        top = cwd
    for directory in (cwd, *cwd.parents):
        roots.append(directory / ".agents/skills")
        if directory == top:
            break
    if os.name != "nt":
        roots.append(Path("/etc/codex/skills"))
    return list(dict.fromkeys(roots))


def check_skill_duplicates(roots):
    """Read SKILL.md metadata only; names/content never establish ownership.

    Follow linked skill folders with cycle protection. Collapse aliases of the
    same physical entrypoint, but report distinct files even when bytes match.
    """
    entries = {}
    errors = []
    visited = set()
    entrypoints = set()
    for root in roots:
        root = Path(root).expanduser()
        try:
            root.stat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            errors.append(f"{root}: {type(exc).__name__}")
            continue
        if not root.is_dir():
            errors.append(f"{root}: not a skill directory")
            continue
        def onerror(exc):
            errors.append(f"{exc.filename}: {type(exc).__name__}")
        for directory, dirs, files in os.walk(root, followlinks=True, onerror=onerror):
            try:
                physical = Path(directory).resolve(strict=True)
                if physical in visited:
                    dirs[:] = []
                    continue
                visited.add(physical)
                dirs[:] = [d for d in dirs if not d.startswith(".") or d == ".system"]
                if "SKILL.md" not in files:
                    continue
                # Resources inside a skill are not additional discovery roots.
                # In particular, do not walk arbitrary linked resource trees.
                dirs[:] = []
                path = Path(directory) / "SKILL.md"
                resolved_path = path.resolve(strict=True)
                if resolved_path in entrypoints:
                    continue
                entrypoints.add(resolved_path)
                raw = path.read_bytes()
                name = frontmatter_name(raw.decode("utf-8-sig"))
                if not name:
                    errors.append(f"{path}: missing skill name")
                    continue
                name = name.strip("\"'")
                entries.setdefault(name, []).append({
                    "path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
                })
            except (OSError, UnicodeError, RuntimeError) as exc:
                errors.append(f"{directory}: {type(exc).__name__}")
                dirs[:] = []
    return {name: paths for name, paths in sorted(entries.items()) if len(paths) > 1}, errors


def report_skill_duplicates(roots):
    duplicates, errors = check_skill_duplicates(roots)
    print("[discovery:codex] read-only local candidates; ownership/loading not asserted; "
          "plugin/runtime-only roots require --skill-root")
    for root in roots:
        print(f"  root: {root}")
    for name, paths in duplicates.items():
        comparison = "identical bytes" if len({p['sha256'] for p in paths}) == 1 else "different content"
        print(f"  DUPLICATE {name}: {comparison}; ownership unknown, preserved")
        for entry in paths:
            print(f"    {entry['path']} sha256={entry['sha256']}")
    for error in errors:
        print(f"  UNKNOWN: {error}")
    print(f"[discovery:codex] {len(duplicates)} duplicate name(s), {len(errors)} unreadable/invalid entry(s); "
          "advisory only, separate from install drift; activation not verified")


def _parse_args(argv):
    ap = argparse.ArgumentParser(description="dinner-harness drift-check (advisory).")
    ap.add_argument("--update", action="store_true", help="re-bless the current CLAUDE.md hash")
    ap.add_argument("--target", choices=["codex", "claude", "all"], default="all")
    ap.add_argument("--no-install", action="store_true",
                    help="skip the install-drift axis (repo-only checks)")
    ap.add_argument("--skill-root", action="append", default=[],
                    help="additional local skill discovery root; also enables discovery with --no-install")
    args = ap.parse_args(argv)
    if args.update:
        if args.target == "codex":
            ap.error("--update is only a legacy Claude curation check; Codex validates generated artifacts")
    return args


def _collect_source_checks(targets):
    declared, cat_problems = check_catalog()
    cur_problems = check_curation() if "claude" in targets else []
    generated_problems = check_codex_generated() if "codex" in targets else []
    return declared, cat_problems, cur_problems, generated_problems


def _report_source_checks(targets, declared, cat_problems, cur_problems, generated_problems):
    if not cat_problems:
        print(f"[catalog] skills {declared['Skills']} / agents {declared['Agents']} / "
              f"hooks {declared['Hooks']} — 카탈로그 일치 (README.md + README.en.md, parity OK)")
    else:
        print("[catalog] DRIFT:")
        for p in cat_problems:
            print("  -", p)
    if "claude" not in targets:
        print("[curation] skipped: legacy Claude source hash does not validate Codex")
    elif not cur_problems:
        print("[curation:legacy-claude] source hash unchanged; semantic parity not asserted")
    else:
        print("[curation] DRIFT:")
        for p in cur_problems:
            print("  -", p)
    if "codex" in targets:
        print("[codex-generated] " + ("FAIL" if generated_problems else "TOML/JSON, routing, references OK"))
        for problem in generated_problems:
            print("  -", problem)


def _collect_install_target(target):
    present, problems, leftovers = check_install(target)
    missing_dest = _installer().default_dest(target) if not present else None
    blocking = [rel for rel, advisory in leftovers if not advisory]
    advisory = [rel for rel, advisory in leftovers if advisory]
    return present, problems, blocking, advisory, missing_dest


def _report_install_target(target, present, problems, blocking, advisory, missing_dest):
    if not present:
        print(f"[install:{target}] {missing_dest} 없음 — skip")
        return
    if not problems and not blocking and not advisory:
        print(f"[install:{target}] repo == 설치본 — drift 없음")
    if problems:
        print(f"[install:{target}] DRIFT ({len(problems)}건) — "
              f"`py -3 install.py --target {target} --allow-live` 필요:")
        for p in problems[:20]:
            print("  -", p)
        if len(problems) > 20:
            print(f"  … 외 {len(problems) - 20}건")
    if blocking:
        print(f"[install:{target}] LEFTOVERS ({len(blocking)}건, exit 1) — 수동 삭제 필요:")
        for rel in blocking[:20]:
            print(f"  - {rel}: repo에 없는 설치본 잔존")
        if len(blocking) > 20:
            print(f"  … 외 {len(blocking) - 20}건")
    if advisory:
        print(f"[install:{target}] ADVISORY LEFTOVERS ({len(advisory)}건, exit 0) — "
              "공유 디렉터리이므로 수동 정리 여부만 확인:")
        for rel in advisory[:20]:
            print(f"  - {rel}: repo에 없는 설치본 잔존")
        if len(advisory) > 20:
            print(f"  … 외 {len(advisory) - 20}건")


def _run_discovery(targets, args):
    if "codex" in targets and (not args.no_install or args.skill_root):
        report_skill_duplicates([*skill_discovery_roots(), *map(Path, args.skill_root)])
    elif "codex" in targets:
        print("[discovery:codex] skipped (--no-install; use --skill-root to include local diagnostics)")


def main(argv=None):
    try:  # report uses em-dash + Korean; force UTF-8 stdout regardless of console codepage
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    args = _parse_args(argv)
    if args.update:
        do_update()
        return 0
    targets = INSTALL_TARGETS if args.target == "all" else (args.target,)
    declared, cat_problems, cur_problems, generated_problems = _collect_source_checks(targets)
    _report_source_checks(targets, declared, cat_problems, cur_problems, generated_problems)
    inst_problems = []
    if args.no_install:
        print("[install] skipped (--no-install)")
    else:
        for target in targets:
            present, problems, blocking, advisory, missing_dest = _collect_install_target(target)
            _report_install_target(target, present, problems, blocking, advisory, missing_dest)
            if present:
                inst_problems += problems + blocking
    _run_discovery(targets, args)
    return 0 if not (cat_problems or cur_problems or generated_problems or inst_problems) else 1


if __name__ == "__main__":
    sys.exit(main())
