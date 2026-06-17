"""dinner-harness drift-check — advisory, stdlib only, repo-only.

Two checks (manual; no CI/pre-commit — run after editing content):
  1. catalog completeness — the README capability catalog (`## 하네스 구성` / `## What's inside`)
     must list exactly the repo's skills (`content/skills/*/`) + agents (`content/agents`
     frontmatter `name`) + hooks (`assets/claude/hooks/handlers/*.py`), in BOTH READMEs with
     KO/EN parity. Description text is NOT checked — only the item set + group-header counts.
  2. curation drift — `content/instructions/CLAUDE.md` whole-file SHA-256 vs the blessed hash
     in `curation.toml`. `assets/codex/AGENTS.md` was curated from CLAUDE.md, so a change may
     need re-curation (advisory; §2 Two-CLI changes are irrelevant to the codex curation).

Usage:
  py -3 check.py            run both; exit 0 if clean, 1 if drift (human-readable report)
  py -3 check.py --update   re-bless: store the current CLAUDE.md hash in curation.toml
"""
import argparse
import hashlib
import re
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent
CURATION = REPO / "curation.toml"
CLAUDE_MD = REPO / "content/instructions/CLAUDE.md"
READMES = {"README.md": "## 하네스 구성", "README.en.md": "## What's inside"}


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


def main():
    try:  # report uses em-dash + Korean; force UTF-8 stdout regardless of console codepage
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="dinner-harness drift-check (advisory).")
    ap.add_argument("--update", action="store_true", help="re-bless the current CLAUDE.md hash")
    args = ap.parse_args()
    if args.update:
        do_update()
        return 0

    declared, cat_problems = check_catalog()
    cur_problems = check_curation()

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

    return 0 if not (cat_problems or cur_problems) else 1


if __name__ == "__main__":
    sys.exit(main())
