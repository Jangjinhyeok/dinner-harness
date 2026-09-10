# Unity — Version Reference

> Consumed by the `gameplay-programmer`, `ui-programmer`, and `tools-programmer`
> agents' "Engine Version Safety" check. Copy this file to your project at
> `docs/engine-reference/unity/VERSION.md` and fill in the `<FILL IN>` fields.
> **When this file and the model's training data conflict, this file wins.**

## Pinned version

- **Unity version:** `<FILL IN — e.g. 6000.0.23f1 (Unity 6 LTS)>`
- **Render pipeline:** `<URP | HDRP | Built-in — FILL IN + package version>`
- **Key packages:** `<Input System x.y, Addressables x.y, Entities/DOTS x.y, UI Toolkit x.y — FILL IN>`
- **Scripting backend:** `<Mono | IL2CPP — FILL IN>`
- **Verified on:** `<YYYY-MM-DD>`
- **API verification:** Verify uncertain/version-dependent APIs against the pinned engine/package
  version's official references. Do not assume the active model's knowledge cutoff.

## How the agent must use this file

1. Before suggesting any Unity API / package API / serialized-field pattern, check the tables below.
2. Check uncertain or changed APIs against the pinned version and record the verified source/date.
3. When this file and training data conflict, **this file wins**.
4. If something isn't covered here, say so rather than guessing.

## Version-sensitive / high-risk APIs & package versions (verify before use)

| API / package | Status in pinned version | Note | Verified source (URL) |
|---|---|---|---|
| <!-- example, replace --> Entities (DOTS) API | `<fill>` | API churn between versions | `<package changelog URL>` |
| <!-- example, replace --> Input System bindings | `<fill>` | | `<docs URL>` |
| <!-- example, replace --> | | | |

## Project-specific deviations from Unity defaults

- `<e.g. custom packages, asmdef layout, disabled modules, define symbols>`
- `<FILL IN or "None">`

## Trusted documentation sources

- Unity Scripting API: https://docs.unity3d.com/ScriptReference/
- Package docs & changelogs: `<FILL IN link>`
- Internal wiki / Confluence: `<FILL IN or "None">`
