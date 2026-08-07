"""dinner-harness drift-check — advisory, stdlib only.

Three checks (manual; no CI/pre-commit — run after editing content):
  1. catalog completeness — the README capability catalog (`## 하네스 구성` / `## What's inside`)
     must list exactly the repo's skills (`content/skills/*/`) + agents (`content/agents`
     frontmatter `name`) + hooks (`assets/claude/hooks/handlers/*.py`), in BOTH READMEs with
     KO/EN parity. Description text is NOT checked — only the item set + group-header counts.
  2. curation drift — `content/instructions/CLAUDE.md` whole-file SHA-256 vs the blessed hash
     in `curation.toml`. `assets/codex/AGENTS.md` was curated from CLAUDE.md, so a change may
     need re-curation (advisory; §2 Two-CLI changes are irrelevant to the codex curation).
  3. install drift — repo vs the LIVE `~/.claude` / `~/.codex`. Checks 1-2 are repo-only, so an
     edited-but-uninstalled harness looked clean while the live copy ran the old behaviour;
     that hole bit twice on 2026-08-05. Renders the manifest into a temp dir through install.py's
     own adapters and compares content only — path substitutions are normalized, `skip_if_exists`
     workflow files (HANDOFF/RESULT) are runtime state and are excluded, a `merge` JSON dest is
     compared on template-owned keys only, and the manifest's own exclude lists apply. Live-only
     leftovers are reported for directories the manifest owns outright (a skill deleted from the
     repo keeps running until install.py is re-run), never for the rest of the install root.
     Machine-local by nature: `--no-install` skips it.

Usage:
  py -3 check.py            run all three; exit 0 if clean, 1 if drift (human-readable report)
  py -3 check.py --no-install   skip the install-drift axis (repo-only checks)
  py -3 check.py --update   re-bless: store the current CLAUDE.md hash in curation.toml
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
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
    blessed = tomllib.load(open(CURATION, "rb")).get("claude_md_blessed_hash", "")
    if blessed != current:
        return ["CLAUDE.md가 AGENTS.md 큐레이션(blessed) 이후 변경됨 — `assets/codex/AGENTS.md`의 "
                "§1/3/4/5/6/7 재-curate 검토(§2 Two-CLI만 바뀌었으면 무시).",
                "  `git diff content/instructions/CLAUDE.md` 확인 후 `py -3 check.py --update`로 re-bless.",
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


def check_install(target, live_root=None, username=None):
    """Compare the rendered manifest against a live install tree.

    Returns (present, problems). present=False means the install root does not exist —
    reported, but not counted as drift: a machine need not use every target.
    """
    with open(MANIFEST, "rb") as manifest_file:
        manifest = tomllib.load(manifest_file)
    target_cfg = manifest.get("targets", {}).get(target)
    if target_cfg is None:
        return True, [f"harness.toml에 target '{target}' 없음"]
    inst = _installer()
    live = Path(live_root) if live_root else inst.default_dest(target)
    if not live.is_dir():
        return False, []
    if username is None:
        username = os.environ.get("USERNAME") or os.environ.get("USER") or ""

    exclude_dirs = set(target_cfg.get("exclude_dir_names", []))
    exclude_suffixes = tuple(target_cfg.get("exclude_file_suffixes", []))
    runtime = {dest_rel for _, dest_rel in target_cfg.get("skip_if_exists", [])}
    problems = []

    with tempfile.TemporaryDirectory(prefix="dh-check-") as td:
        scratch = Path(td) / f".{target}"
        if scratch.resolve() == live.resolve():  # never render onto the tree we are judging
            return True, [f"scratch dest가 live와 동일 — 비교 불가 ({live})"]
        adapter = inst.load_adapter(target)
        plan = adapter.install(
            repo_root=REPO, target_cfg=target_cfg, vars_cfg=manifest.get("vars", {}),
            dest_root=scratch, username=username, dry_run=False,
        )
        expected = set()
        for action, dest in plan:
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
            if action == "merge" and rel.endswith(".json"):
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
            problems.append(f"{rel}: repo에 없는 설치본 잔존 — 삭제 후 재설치 필요")
    return True, problems


def do_update():
    blessed_at = "unknown"
    if CURATION.is_file():
        blessed_at = tomllib.load(open(CURATION, "rb")).get("blessed_at", "unknown")
    h = sha256(CLAUDE_MD)
    CURATION.write_text(
        "# curation drift manifest — read by check.py. Re-bless: `py -3 check.py --update`.\n"
        "# claude_md_blessed_hash = content/instructions/CLAUDE.md at the last AGENTS.md curation.\n"
        f'claude_md_blessed_hash = "{h}"\n'
        f'blessed_at = "{blessed_at}"\n',
        encoding="utf-8")
    print(f"re-blessed CLAUDE.md hash → curation.toml ({h[:16]}…)")


def main(argv=None):
    try:  # report uses em-dash + Korean; force UTF-8 stdout regardless of console codepage
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="dinner-harness drift-check (advisory).")
    ap.add_argument("--update", action="store_true", help="re-bless the current CLAUDE.md hash")
    ap.add_argument("--no-install", action="store_true",
                    help="skip the install-drift axis (repo-only checks)")
    args = ap.parse_args(argv)
    if args.update:
        do_update()
        return 0

    declared, cat_problems = check_catalog()
    cur_problems = check_curation()
    inst_problems = []

    if not cat_problems:
        print(f"[catalog] skills {declared['Skills']} / agents {declared['Agents']} / "
              f"hooks {declared['Hooks']} — 카탈로그 일치 (README.md + README.en.md, parity OK)")
    else:
        print("[catalog] DRIFT:")
        for p in cat_problems:
            print("  -", p)
    if not cur_problems:
        print("[curation] CLAUDE.md hash == blessed — drift 없음")
    else:
        print("[curation] DRIFT:")
        for p in cur_problems:
            print("  -", p)

    if args.no_install:
        print("[install] skipped (--no-install)")
    else:
        for target in INSTALL_TARGETS:
            present, problems = check_install(target)
            if not present:
                print(f"[install:{target}] {_installer().default_dest(target)} 없음 — skip")
            elif not problems:
                print(f"[install:{target}] repo == 설치본 — drift 없음")
            else:
                inst_problems += problems
                print(f"[install:{target}] DRIFT ({len(problems)}건) — "
                      f"`py -3 install.py --target {target} --allow-live` 필요:")
                for p in problems[:20]:
                    print("  -", p)
                if len(problems) > 20:
                    print(f"  … 외 {len(problems) - 20}건")

    return 0 if not (cat_problems or cur_problems or inst_problems) else 1


if __name__ == "__main__":
    sys.exit(main())
