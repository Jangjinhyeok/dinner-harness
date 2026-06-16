# Unreal Engine — Version Reference

> Consumed by the `gameplay-programmer`, `ui-programmer`, and `tools-programmer`
> agents' "Engine Version Safety" check. Copy this file to your project at
> `docs/engine-reference/unreal/VERSION.md` and fill in the `<FILL IN>` fields.
> **When this file and the model's training data conflict, this file wins.**

## Pinned version

- **Engine version:** `<FILL IN — e.g. 5.5.4>`
- **Source build / launcher:** `<launcher | source (custom engine mods?) — FILL IN>`
- **Verified on:** `<YYYY-MM-DD>`
- **Assistant knowledge cutoff:** Claude Opus 4.8 ≈ 2026-01 (confirm for the model
  in use). Treat any UE API, class, UFUNCTION, module, plugin, or workflow
  introduced or changed AFTER this date as UNVERIFIED — flag it and confirm
  against the official docs before using.

## How the agent must use this file

1. Before suggesting any UE-specific API / class / module / console var, check the tables below.
2. If an API was introduced or changed after the knowledge cutoff, flag it explicitly:
   "This API may have changed in <version> — verify against the reference below."
3. When this file and training data conflict, **this file wins**.
4. If something isn't covered here, say so rather than guessing.

## Post-cutoff / high-risk APIs (verify before use)

| API / system | Status in pinned version | Note | Verified source (URL) |
|---|---|---|---|
| <!-- example, replace --> `UE::Tasks` migration | `<fill>` | prefer over legacy TaskGraph? | `<official docs URL>` |
| <!-- example, replace --> Nanite/Lumen/PCG flags | `<fill>` | renamed/added cvars | `<release notes URL>` |
| <!-- example, replace --> | | | |

## Project-specific deviations from UE defaults

- `<e.g. custom build flags, disabled/added plugins, engine source modifications>`
- `<FILL IN or "None">`

## Trusted documentation sources

- Official UE docs: https://dev.epicgames.com/documentation/en-us/unreal-engine
- Release notes for the pinned version: `<FILL IN link>`
- Internal wiki / Confluence: `<FILL IN or "None">`
