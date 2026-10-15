# Project templates

Copy only the needed templates into a project and fill its actual facts. Preserve existing files;
do not blindly overwrite project instructions. AGENTS.md is self-contained and does not depend on
Claude global policy. For dual-vendor projects both entrypoints can refer to an explicit shared
project document.

| Template | Project destination |
|---|---|
| AGENTS.md | project-root AGENTS.md |
| engine-reference/unreal/VERSION.md | docs/engine-reference/unreal/VERSION.md |
| engine-reference/unity/VERSION.md | docs/engine-reference/unity/VERSION.md |
| architecture/ADR-template.md | docs/architecture/ADR-NNN-topic.md when a complex decision warrants it |
| mcp.json | Claude-compatible project .mcp.json reference; use the chosen CLI's supported MCP registration for other targets |
| machine-env.example.md | per-machine `~/.claude/rules/machine-env.md` (not a project file; local, never installed or reported as leftover) |

Pin the real engine version and actual build/test commands; do not guess the model's knowledge
cutoff or silently trust newer APIs. Record verification dates with sources. ADRs support meaningful
long-term boundary decisions, not every small edit. Reporting structure scales with the change.

Engine MCP requires its server and editor plugin/package plus a running editor. Inspect actual
capabilities and current official setup before registration. The template alone does not register
Codex MCP servers. MCP editor mutations may bypass file-edit hooks; use the authorized scope and
a suitable test copy. Do not create/switch branches merely to use a template or editor.
JSON has no comments, so mcp.json carries its rules inside the `<FILL IN>` placeholders: pin an
exact server package version (`pkg@1.2.3`); never use `@latest` or an unversioned `npx`/`uvx`
package, which can run a different release than the one you reviewed.
