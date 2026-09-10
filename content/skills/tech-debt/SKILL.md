---
name: tech-debt
description: Inspect, record or prioritize concrete technical debt while preserving existing register entries.
---

# Technical Debt

Infer scan/add/prioritize/report from the request; default to inspection and reporting.
Read the existing `docs/tech-debt-register.md` if present. Inspect workarounds, duplication,
compatibility constraints, test gaps and measured performance costs. A long file or TODO alone
does not prove harmful debt.

Record affected files, concrete impact, why accepted (unknown if undocumented), estimated effort
and confidence. Prioritize by impact/frequency/effort without invented precision. Scans/reports are
read-only unless updates were requested. Add/update/prioritize requests authorize the register
edit without per-row consent. Preserve IDs and rationale; do not fix source because a scan found debt.

No mandatory sprint cadence, age cutoff or automatic follow-up workflow is imposed.
