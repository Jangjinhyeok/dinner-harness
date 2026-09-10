---
name: cli-update
description: Check or update only the requested Codex or Claude CLI through its actual installation channel.
---

# CLI Update

Select only the target named by the user (codex, claude or both). If unspecified use the current
harness target when known, otherwise report the ambiguity before a global update. Checking versions
does not authorize upgrades. Explicit update requests authorize the selected installed tool only.

Inspect executable path, version and installation channel without reading credentials.
Query the channel's official current release metadata; do not assume npm if the tool was installed
another way. Report unavailable commands or unknown channel rather than inventing an updater.
Do not install an absent second vendor merely to satisfy this workflow.

Before upgrading a harness-dependent CLI, inspect its known compatibility checks. Use temporary
verification when feasible; explain any actual unresolved incompatibility. Never relabel old
“verified against” comments to the new version without running the corresponding check.
Honor the user's existing update authorization and actual system approval limits; no silent
privilege escalation, vendor fallback or alternate billing route.

Run the selected channel's supported update, then verify the executable path and version.
Report attempted versus verified results. CLI version confirmation is not proof of model access,
hook enforcement or output-schema compatibility. Record later runtime verification as a new
dated observation, preserving historical records. Do not modify harness source, live homes or
authentication as an incidental part of an update.
