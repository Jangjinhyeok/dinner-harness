---
name: hotfix
description: Apply a narrow emergency fix with reproduction, verification and rollback notes when explicitly invoked.
---

# Hotfix

Use only on explicit hotfix invocation. Identify the incident, affected platforms/users and
smallest correction. Infer routine choices from evidence; ask only when missing information
changes the fix or authority. Preserve current user-selected branch and dirty tree.
Do not create a branch, commit or deploy without explicit authority.

Reproduce, implement the bounded correction and run project build/regression checks.
For UE/Unity include relevant lifecycle, replication/save and runtime scenarios.
Report unavailable checks. Important/HIGH changes require independent review and HIGH acceptance.
Use the changed code's callers to select verification breadth: an isolated fix may need a focused
smoke check, while shared core behavior needs the affected systems' regression checks.

When an audit record is requested, write `docs/hotfixes/hotfix-<date>-<name>.md` with incident,
behavior change, verification and concrete rollback approach, preserving existing records.
Do not repeatedly ask for already authorized edits. A rollback plan does not authorize
reverting user work. Deployment is separately authorized.
After an authorized deployment, verify the affected flow in the deployed build before marking
the incident verified. If it persists, keep or reopen the incident and report rollback options;
do not silently revert or close it on the strength of local tests.
