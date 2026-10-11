---
name: asset-gen-tools
description: Select, connect and verify 3D and image generation MCP servers, plugins and skill packs (Blender, Krita, ComfyUI, Meshy, Tripo, Hyper3D/Hunyuan3D, image APIs) for game asset work. Use when choosing or setting up a generation or DCC tool; asset-authoring owns the authoring workflow itself.
---

# Asset Generation Tools

Tool catalog and connection procedure for [asset-authoring](../asset-authoring/SKILL.md).
Apply [autonomy policy](../../rules/autonomy-policy.md); this skill adds no permissions.
Installing a server, editing client MCP config, granting trust or spending credits keeps its own
authority, and live config/trust changes are HIGH. Do not install anything only because it is listed.

## Catalog snapshot (verified 2026-10-11)

Entries change quickly. Re-check the official page, version, license and pricing before
selecting one; treat this table as candidates, not as installed or connected tools.

### 3D / DCC

| Tool | Kind | Connect (Claude Code) | Notes |
|---|---|---|---|
| Blender Lab MCP (official, `projects.blender.org/lab/blender_mcp`) | Add-on + stdio relay (`python -m blmcp`) | See Blender Lab setup below | Blender 5.1+, GPL-3.0+. Scene analysis, Python API, screenshots/renders, `_for_cli` background tools. No generation or asset-library integration. Executes LLM code without guards. Previously verified locally (1.0.3) |
| MCP for Blender (`ahujasid/blender-mcp`, PyPI `mcp-for-blender`) | Own add-on + stdio relay | `claude mcp add --scope project blender -- uvx blender-mcp` (compat wrapper name) | Blender 3.0+, MIT. **Different protocol from the official add-on; not interchangeable.** Adds Poly Haven, Sketchfab, Poly Pizza, Hyper3D Rodin, Hunyuan3D, Tripo, `export_scene`. Python exec on by default (a safe-mode env is reported by third parties; confirm in README). `DISABLE_TELEMETRY=true`. GUI clients may need the absolute `uvx` path (`spawn uvx ENOENT`) |
| Meshy MCP (official, `meshy-dev/meshy-mcp-server`) | Cloud API, stdio | `npx add-mcp @meshy-ai/meshy-mcp-server` with `MESHY_API_KEY` in env; on Windows the command may need `cmd /c npx` | Text/image/multi-image to 3D, refine, remesh, retexture, rig, animate, text/image to image, `meshy_check_balance`. API needs a paid tier plus API credits; every call spends REST credits. Free-tier outputs carry CC BY 4.0 attribution. `model_type: lowpoly` announced to end 2026-10-30 |
| Meshy skill pack (`meshy-dev/meshy-3d-agent`) | Skill, REST direct | `npx skills add meshy-dev/meshy-3d-agent` | No MCP server; same credits. Prefer one of MCP or skill pack, not both |
| Tripo MCP (official, `VAST-AI-Research/tripo-mcp`) | Blender-coupled, alpha | `uvx tripo-mcp` plus Tripo Blender add-on | Text to 3D imported into Blender. Alpha; Tripo API key/credits (1 credit = US$0.01 when last checked) |
| Autodesk Fusion, SketchUp (claude.ai connectors) | Remote connector | Connector directory, account auth | CAD/architectural modeling; not game-mesh pipelines by default |
| Hunyuan3D | No official MCP found | Via MCP for Blender integration or a third-party wrapper | Check model weight license and regional terms separately |

### 2D / image

| Tool | Kind | Connect | Notes |
|---|---|---|---|
| Comfy MCP local (official, `Comfy-Org/comfy-mcp`, PyPI `comfy-mcp`) | stdio over comfy-cli | `claude mcp add --scope project comfy-mcp -e COMFY_BIN=<path> -- comfy-mcp` | Needs `comfy-cli>=1.14.0`, a ComfyUI workspace and running ComfyUI for execution. `validate_workflow`, `run_workflow`, `fetch_outputs`. Local GPU, model licenses per checkpoint |
| Comfy MCP cloud | Remote | Comfy Cloud early access | Cloud GPU credits |
| Krita AI Diffusion (`Acly/krita-ai-diffusion`) | Krita plugin | Not an MCP; uses a ComfyUI backend | Layered inpaint/refine inside `.kra` |
| krita-codex-mcp (PyPI) | Third-party stdio + Krita plugin | `uvx krita-codex-mcp` | Loopback + shared token; layer/selection/document tools. Tested on Krita 5.3.2.1 |
| Adobe for creativity (claude.ai connector) | Remote connector | Connector directory | Photoshop/Firefly/Illustrator; Adobe plan and generative credits |
| Google GenMedia MCP (`GoogleCloudPlatform/vertex-ai-creative-studio`, experiments) | stdio binaries | Repo install script, Vertex AI credentials | Nano Banana image, Veo, Lyria. Experimental; Google Cloud billing |
| OpenAI / Gemini image MCPs | Third-party stdio | Per README | No official OpenAI image MCP found. Review source before use; reject servers reusing a ChatGPT/Codex session token |

Claude Code has no built-in raster image tool. Codex's `imagegen` system skill (built-in
`image_gen`, CLI fallback with `OPENAI_API_KEY`) applies only inside Codex. For Claude, image
generation needs an MCP server above, a DCC route, or the user running Codex separately.

## Select

Start from the asset-authoring need, not the catalog. Choose the smallest route:

1. Editable prop and same-model icon: Blender (direct CLI/Python or a Blender MCP) plus Krita.
   An MCP is optional; `blender --background --python` scripts are reproducible and need no server.
2. Scene inspection/debugging/batch scripting on Blender 5.1+: Blender Lab MCP.
3. Generated base mesh or reference: Meshy, Tripo, Hyper3D or Hunyuan3D, then explicit cleanup
   in Blender. Generated topology/UV/materials are a source stage, not a finished asset.
4. 2D textures/concepts/inpainting: ComfyUI (local) or Krita AI Diffusion; hosted image APIs when
   no local GPU is available.

Run only one Blender relay against one Blender socket at a time. The official and community
servers each need their own add-on; do not point one relay at the other's add-on or port.
Compare tool code license, model weight license, generated-output terms, account tier and
per-call credits; record them as provenance.

## Connect

Prefer project scope (`claude mcp add --scope project ...`, which writes `.mcp.json`) or a
dedicated profile over user-global config. Put credentials in environment variables referenced
by name; never write key values into `.mcp.json`, skills or reports. Pin a version when the
server supports it. On Windows, quote absolute paths with spaces and launch helpers hidden.
Project-scope servers load only after the client trusts/approves them (Codex project trust,
Claude Code `.mcp.json` approval) and appear in a new session; do not promise hot reload.

### Blender Lab setup (verified pattern)

A prior Codex setup (Blender 5.2.2 portable, add-on 1.0.3, MCP SDK 1.30.0) worked as follows:

- Isolate the profile with `BLENDER_USER_RESOURCES=<lab>/runtime/blender-profile`.
- Install the add-on headless: `blender --online-mode --background --factory-startup --command
  extension install-file mcp-<ver>.zip --repo user_default --enable`.
- Install the relay into a dedicated Python venv and register `<venv>/python -m blmcp` as the MCP
  command, with `BLENDER_MCP_HOST`/`BLENDER_MCP_PORT` in env.
- Start Blender with `--online-mode --background <scratch.blend> --command blender_mcp --host
  127.0.0.1 --port <port>`. The add-on refuses to run without online access enabled.
- The default port 9876 (tests use 9876-9878) collides easily; pick a free port and check its owner first.
- Allowlist only the needed tools (e.g. object/blend-file summaries, `execute_blender_code`) and
  raise the tool timeout for long scripts.

Known issues: `render_viewport_to_path` ignored the requested folder and wrote to vendor temp,
so renders went through a path-checking project script instead. The handshake `serverInfo.version`
is the MCP SDK version, not the add-on version. Open `.blend` files lock against move; save a new
version instead. Repeatable checks without MCP: `blender --background --factory-startup
--offline-mode --python-exit-code 1 --python <script> -- <mode>`, judged by a report file and
PASS marker rather than the exit code alone.

### Verification order

Verify in order and report each separately; one step does not imply the next:

1. Config present (`claude mcp list` / `/mcp`) and server process starts.
2. Fresh session enumerates the actual tool names.
3. A read-only call succeeds (scene info, `server_info`, `meshy_check_balance`, node search).
4. One reversible scratch change or minimal job within the approved cost budget; keep the task id,
   download the output to an explicit path and inspect it.
5. Hand off to asset-authoring for source preservation, export and engine acceptance.

DCC Python execution runs with the DCC process's OS permissions; file hooks and tool allowlists
are not containment for it. Work on scratch copies, and stop on unexpected port owners, version
mismatch or a failed read-only call instead of weakening hooks, sandbox or scope checks.

## Report

List chosen tools with version/source, config scope and file, credential variable names,
verification steps 1-5 as PASS/FAIL/not_run, credits spent and task ids, license/terms notes,
and open issues. Installation or connection outcomes are not asset quality evidence.
