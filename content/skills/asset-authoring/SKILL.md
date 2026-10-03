---
name: asset-authoring
description: Create or edit reusable game assets, including 3D props, textures, sprites and UI icons, with Blender, Krita, DCC MCP tools or AI assistance. Use for editable source preservation, model-derived icon rendering, export and engine import validation.
---

# Asset Authoring

Use the project's art and asset conventions, installed tools and actual engine version.
Apply [autonomy policy](../../rules/autonomy-policy.md) and
[verification guidance](../verification-loop/SKILL.md); this skill adds no permissions.

## Scope and responsibilities

Search existing assets, authoring scripts and import settings first. State the asset, intended
view/use, style, dimensions or pixel sizes, editable source, exports and destination. If style
is undecided, make a stated prototype assumption. For a new pipeline, start with one representative
asset and verify the full path before batching; a Medkit and its icon are examples, not a fixed scope.
Keep inventory Model, MVVM/CommonUI wiring and gameplay changes within the requested integration scope.

| Component | Responsibility |
|---|---|
| Main / skill | Define scope, source/output ownership, tool choice and acceptance evidence |
| tools-programmer | Implement bounded authoring, export, render and validation automation when useful |
| Engine specialist | Check importer settings, materials, collision and runtime integration |
| MCP server | Expose the tools actually available to this client; relay calls and results |
| DCC Add-on / backend | Execute inside Blender/Krita or the configured generation backend |

A skill or agent does not install or connect an MCP server. An Add-on alone does not establish
client access. Krita layer editing does not imply that a Krita MCP or AI backend is installed.
The main session can perform small tasks directly; delegation follows
[agent routing](../../rules/agent-routing.md), without mandatory specialist dispatch.

## Choose and connect tools

When starting a small editable prop workflow without an established pipeline, consider Blender
for modeling and same-model icon renders, with Krita for layered 2D edits. Use existing CLI/Python
automation or an available DCC MCP according to the task; MCP is not required for asset creation.
Add Meshy/Tripo, Krita AI Diffusion/Comfy or another generator only for an identified need.
Verify current official compatibility, maintenance, costs and licenses when selecting a new dependency.
Check tool code, model weights, generated-output terms and reference-image rights separately;
record provenance relevant to portfolio redistribution and attribution. Do not assume every
local workflow is free or that a paid account includes API generation credits.

Use the supported client setup for the actual environment. Prefer project-local configuration
and a dedicated DCC profile/server environment when introducing a new integration. Inspect only
necessary non-secret settings. Report command/argument paths and credential variable names,
never API Key/token contents. A new installation, live config/trust change or paid generation
needs authority covering that action; reuse existing authorization without asking again.
Live config/security changes retain HIGH review and human result acceptance. Do not weaken
hooks, sandbox, scope/secret checks or baseline protections to make a tool connect.

For a new DCC connection, verify these boundaries in order:

1. Identify the client, DCC/server versions, executable, target source file and transport.
   For a local socket, use loopback, check port ownership before launch and verify the responding
   process/scene. Do not attach to or stop an unrelated DCC process. On Windows, launch background
   helpers hidden and quote absolute paths with spaces using the actual shell's rules.
2. In a fresh client session where necessary, enumerate the actual MCP tools and query the scene
   read-only. Configuration presence, process start and tool listing are separate from a successful call.
3. In the agreed scratch source, make one reversible object change, save to an explicit output
   path and reopen/query the saved result. Confirm the operation's actual destination and diagnostics.

For a generation/workflow service, enumerate its capabilities and validate the selected workflow
or task settings first. Run a minimal job within the approved cost/retry budget, retain its task
identifier and fetch/inspect the saved result. A queued/completed job alone does not verify asset quality.

Python/code execution through a DCC MCP may use the DCC process's OS permissions. Tool allowlists,
path-checking helpers and file hooks are not containment for every MCP/Add-on write or DCC cache.
Keep the assigned write scope and required controller path; do not claim inline MCP equals
headless baseline/delta enforcement. Use actual tool availability rather than promising hot reload.

## Preserve source and iterate

Follow project naming and storage conventions; identify editable sources, derived exports and
temporary outputs. Keep meshes/materials/modifiers in the `.blend` and paint layers in `.kra`
or the chosen native format. Save a source version before export or destructive processing.
Work on copies or evaluated export geometry when applying modifiers, joining, triangulating,
baking or remeshing would remove useful editing structure. Preserve imported AI output as a
source stage and make topology/UV/material cleanup explicit.

Before replacing existing source or outputs, preserve user edits with a versioned copy or verified
snapshot and define the affected files. A procedural rebuild can replace hand edits: update the
existing scene, or export/render the edited source, unless regeneration is explicitly intended.
Save and reopen the native source; demonstrate that a targeted edit can be retained and re-exported.
Keep any reusable script and relevant tool/recipe information with the project's source conventions.

For an icon required to match the model, render the final model with a recorded camera, lighting
and render settings. Use transparent RGBA when requested. Keep the render as a preserved base
layer and retouch separately; identify substantive 2D changes. An independently AI-generated
lookalike is not evidence of a same-model render. Inspect alpha edges, framing and silhouette
at the actual UI sizes and on light/dark backgrounds; 32/48/64 px are useful small-icon examples.

## Export and engine acceptance

Export only intended geometry/materials and collision objects; exclude authoring lights/cameras
unless requested. Record units, axes, transforms, pivot, evaluated geometry, material slots and
the importer settings actually used. Blender shader graphs do not establish engine material
equivalence: verify transferred/baked textures and engine material reconstruction where needed.

For Unreal, use the pinned engine version and project importer/naming conventions. Validate a
new pipeline in a disposable import destination before replacing production assets. Check:

- Mesh bounds in centimeters at intended actor scale, orientation, pivot, normals/UVs and materials.
- Appropriate simple/convex collision data and actual hit/miss behavior for the intended query or
  physics use. A hull/primitive count alone does not prove collision behavior; inspect convex and
  primitive data with the APIs supported by this engine version.
- Texture dimensions after loading/compilation finishes, alpha, color space and relevant UI
  compression/mip settings. Inspect the rendered material and icon in the intended view.
- Save/reload in a fresh engine process and reimport into the **same asset** after a small source
  edit. Check size, slots, collision, references and visible change. A second fresh import does not
  verify reimport; preserve production assets while an importer discrepancy remains unresolved.

Use the project's actual engine runtime and targeted checks; build/Automation or commandlet
success does not prove visual acceptance. For UE interactive PIE, reuse the user's choice for
the current scope or follow the choice gate in verification-loop before starting. Provide direct
test steps and expected results when the user tests. Mark missing engine/DCC/visual checks
`not_run`, distinguish observed results from user reports, and retain known FAILs.

## Handoff

Return the native source, exports/icons, relevant recipe/settings and evidence for the latest
artifact state. Separate connection, authoring/editability, export, import/reimport, collision,
visual/UI and runtime results using PASS/FAIL/not_run as applicable. Identify file version/hash
when needed to tie evidence to the result. State unresolved issues, independent review and human
acceptance separately. Commit/push, publication and further live installation keep their own authority.
