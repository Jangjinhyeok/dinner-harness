---
name: codebase-onboarding
description: Map an unfamiliar repository's architecture, entry points, conventions and verification procedures; create project instructions when requested.
---

# Codebase Onboarding

Inspect applicable project instructions and manifests first, then targeted code searches.
Detect Unreal through uproject/Build.cs/Target.cs and Unity through ProjectVersion.txt,
Packages/manifest.json and asmdef files. Ignore generated engine/build directories.
For other stacks inspect actual project manifests rather than assume a web toolchain.

Identify entry points, module/assembly dependencies, pinned versions, tooling and tests.
Unreal entry paths can include GameInstance/GameMode/PlayerController/subsystems;
Unity paths can include bootstrap scenes, runtime initialization and MonoBehaviour/ECS systems.
Trace one meaningful input→state→presentation or request→storage path end to end.
Describe lifecycle/ownership, async patterns, Blueprint/C++ or MonoBehaviour/DOTS boundaries,
replication and compatibility constraints when present.

Read relevant specialist references under the active harness install root's `docs/specialists/`
for deeper engine questions. A bounded native explorer is optional; the main session can inspect
and summarize directly. Cite concrete files, distinguish inferred conventions from explicit rules,
and record unknown build/test commands rather than inventing them.

A request to understand the repository is read-only. Create a concise onboarding guide when
requested. Create or update project-root AGENTS.md only when project instructions are requested,
using [the template](../../templates/AGENTS.md). A guide-only request does not authorize executable
project policy changes. Preserve existing files; enhance only the requested scope.
No mandatory CLAUDE.md/global Claude dependency or per-file consent is needed.
For dual-vendor use, an explicitly chosen common project document can serve both entrypoints.

Use Korean technical discussion, English identifiers/comments and type-prefixed Korean commit
messages unless project policy is more specific. Include actual build/test commands, platform
budgets and where to change relevant behavior. Engine version references and brief ADRs are useful
when needed, not mandatory starter artifacts for every repository.
