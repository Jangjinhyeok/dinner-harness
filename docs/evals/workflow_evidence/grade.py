"""Grade structured evidence-interpretation reports, not live tools or prose truth."""
import json
from pathlib import Path
import sys


CASES = Path(__file__).with_name("cases.json")


def grade(cases, reports):
    """Return errors; missing/duplicate reports and unsupported evidence cannot pass."""
    if not isinstance(reports, list):
        return ["reports must be a list"]
    expected = {case["id"]: case for case in cases}
    seen = set()
    errors = []
    for report in reports:
        if not isinstance(report, dict) or not isinstance(report.get("id"), str):
            errors.append("invalid report")
            continue
        identity = report["id"]
        if identity not in expected or identity in seen:
            errors.append("unknown or duplicate case ID")
            continue
        seen.add(identity)
        case = expected[identity]
        if report.get("claims") != case["expected"]["claims"]:
            errors.append(f"{identity}: incorrect or missing claims")
        evidence = report.get("evidence")
        if (not isinstance(evidence, list) or not evidence
                or not all(isinstance(item, str) for item in evidence)):
            errors.append(f"{identity}: missing evidence IDs")
        elif (not set(case["expected"]["evidence"]) <= set(evidence)
              or not set(evidence) <= set(case["evidence"])):
            errors.append(f"{identity}: unsupported or incomplete evidence IDs")
        if not isinstance(report.get("reason"), str) or not report["reason"].strip():
            errors.append(f"{identity}: missing explanation")
    errors.extend(f"{identity}: missing report" for identity in sorted(set(expected) - seen))
    return errors


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python docs/evals/workflow_evidence/grade.py RESPONSES.json")
        return 2
    try:
        cases = json.loads(CASES.read_text(encoding="utf-8"))
        reports = json.loads(Path(args[0]).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        print("cannot read fixture or response JSON")
        return 2
    errors = grade(cases, reports)
    print(json.dumps({"cases": len(cases), "errors": errors}, ensure_ascii=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
