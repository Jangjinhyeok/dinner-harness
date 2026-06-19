# CODEX-PREFLIGHT

Date: 2026-06-19  
Repo: `C:\Users\zero9\Documents\Github\dinner-harness`  
Scope: runtime preflight for how Codex `0.141.0` consumes the `adapters/codex.py` v2 output.  
Constraint: no repo code changes, no commit, no push.

## 0. Environment

- `codex --version` -> `codex-cli 0.141.0`
- `codex features list`:
  - `hooks stable true`
  - `multi_agent stable true`

Reference docs fetched locally on 2026-06-19:

- Codex manual `/codex/hooks`
- Codex manual `/codex/subagents`
- Codex manual `/codex/skills`

## 1. Scratch install

Command:

```powershell
py -3 install.py --target codex --dest C:/Users/zero9/codex-preflight
```

Observed:

- install succeeded
- summary: `agent=21, copy=46, hooks_json=1`
- generated artifacts confirmed:
  - `C:\Users\zero9\codex-preflight\agents\*.toml` (21 files)
  - `C:\Users\zero9\codex-preflight\hooks.json`
  - `C:\Users\zero9\codex-preflight\hooks\handlers\*`
  - `C:\Users\zero9\codex-preflight\hooks\lib\*`
  - `C:\Users\zero9\codex-preflight\hooks\rules\*`

## 2. `hooks.json` schema vs native Codex schema

### 2.1 Native 0.141 hook config shape

Per the current Codex manual, native hook config supports:

- locations:
  - `~/.codex/hooks.json`
  - `~/.codex/config.toml` with inline `[hooks]`
- top-level shape:
  - `{ "hooks": { ... } }`
- documented event names:
  - `PreToolUse`
  - `PostToolUse`
  - `PermissionRequest`
  - `PreCompact`
  - `PostCompact`
  - `UserPromptSubmit`
  - `SessionStart`
  - `SubagentStart`
  - `SubagentStop`
  - `Stop`
- matcher group shape:
  - `matcher` plus `hooks[]`
- handler keys:
  - `type = "command"`
  - `command`
  - optional `commandWindows`
  - optional `timeout`
  - optional `statusMessage`

### 2.2 Scratch-generated v2 `hooks.json`

Observed generated shape:

- top-level `hooks` key: present
- event names used:
  - `PreToolUse`
  - `PostToolUse`
  - `UserPromptSubmit`
- matcher key name:
  - `matcher`
- handler keys:
  - `type`
  - `command`
  - `timeout`

Verdict:

- **Schema-level match: YES**
- **No native schema correction is required for the JSON shape**
- `commandWindows` is supported natively but is optional; v2 scratch output does not emit it.

Important distinction:

- The remaining mismatch is not the `hooks.json` schema.
- The remaining mismatch is the **handler payload contract**.
- On Windows Codex `0.141.0`, real file-edit hook payloads came through as `tool_name=apply_patch` with `tool_input.command=<patch string>`, not as Claude-style `Edit` or `Write` payloads with `tool_input.file_path`.

## 3. Edit tool payload capture

Temporary probe:

- added a one-off `PreToolUse` probe to live `~/.codex/hooks.json`
- probe handler:

```python
import sys, pathlib
pathlib.Path.home().joinpath('.codex','_probe.jsonl').open('a', encoding='utf-8').write(sys.stdin.read() + chr(10))
```

Test action:

- asked Codex to edit one temporary file

Observed:

- file-edit `tool_name`: **`apply_patch`**
- payload shape:
  - `tool_input.file_path`: absent
  - `tool_input.new_content`: absent
  - `tool_input.command`: present
  - value: full patch string

Raw payload sample, verbatim:

```json
{"session_id":"019edd8e-07cf-78f1-96a0-06dc86b447a7","turn_id":"019edd8e-0e1d-7a01-ba31-1908e9d33861","transcript_path":"C:\\Users\\zero9\\.codex\\sessions\\2026\\06\\19\\rollout-2026-06-19T10-45-33-019edd8e-07cf-78f1-96a0-06dc86b447a7.jsonl","cwd":"C:\\Users\\zero9\\Documents\\Github\\dinner-harness","hook_event_name":"PreToolUse","model":"gpt-5.4","permission_mode":"bypassPermissions","tool_name":"apply_patch","tool_input":{"command":"*** Begin Patch\n*** Update File: C:\\Users\\zero9\\AppData\\Local\\Temp\\codex-preflight-test\\target.txt\n@@\n-alpha\n+beta\n*** End Patch\n"},"tool_use_id":"call_ES9wPKy5HXLPoUxUHSasUqe1"}
```

Conclusion:

- **risk#1 closed**
- On Windows Codex `0.141.0`, file-edit hook handling must assume an `apply_patch` patch-string contract.

## 4. `PreToolUse` exit `2` block behavior

Test setup:

- added a temporary `PreToolUse` hook for matcher `apply_patch`
- hook handler logged the payload and exited with code `2`

Decisive handler body:

```python
import json, sys, pathlib
payload = json.loads(sys.stdin.read() or '{}')
pathlib.Path.home().joinpath('.codex','_block_probe.log').open('a', encoding='utf-8').write(json.dumps(payload, ensure_ascii=False) + '\n')
if payload.get('tool_name') == 'apply_patch':
    print('[preflight:block] unconditional apply_patch block')
    raise SystemExit(2)
```

Direct script verification:

- same script executed manually under writable `~/.codex`
- observed exit code: `2`

Observed runtime result:

- the hook definitely ran
  - `_block_probe.log` captured the `apply_patch` payload
- Codex still applied the edit
  - temporary file `newfile.txt` was created with contents `ZETA`

Verdict:

- **Hook block behavior for observed `apply_patch` runs: NO**
- In this observed setup (`codex exec --json --dangerously-bypass-hook-trust` on Windows, Codex `0.141.0`), a `PreToolUse` command hook returning exit code `2` did **not** block `apply_patch`.

This was the highest-severity runtime discrepancy in the preflight.

## 5. Subagent spawn

Temporary live setup:

- copied two scratch-generated custom agents into `~/.codex/agents/`
  - `ue-gas-specialist.toml`
  - `unreal-specialist.toml`

### 5.1 Depth-1

Test:

- root session asked Codex to spawn `ue-gas-specialist`
- child was instructed to reply with `DEPTH1_OK`

Observed:

- `spawn_agent` succeeded
- `wait` returned child message `DEPTH1_OK`

Verdict:

- **depth-1 custom-agent spawn works**

### 5.2 Depth-2

Test:

- root session spawned `unreal-specialist`
- child was instructed to attempt grandchild spawn `ue-gas-specialist`

Observed:

- child returned `grandchild spawn blocked`

Verdict:

- **depth-2 grandchild spawn is blocked**
- This matches the documented default `agents.max_depth = 1` behavior.

## 6. Skill path discovery

Question asked to Codex:

- "Do not use any tools. From the skills list already in your context, list every skill named `simplicity-first` and the exact path shown for it."

Observed response:

- `C:/Users/zero9/.agents/skills/simplicity-first/SKILL.md`
- `C:/Users/zero9/.codex/skills/simplicity-first/SKILL.md`

Verdict:

- **Runtime discovered both**
  - `$HOME/.agents/skills/...`
  - `~/.codex/skills/...`
- Therefore, on this observed Windows `0.141.0` runtime, skill discovery is **not** `$HOME/.agents/skills only`.

Note:

- This empirical runtime result is newer than the current manual text that documents `$HOME/.agents/skills` as the user-scope path.

## 7. Final runtime facts

- Version: `codex-cli 0.141.0`
- Features: `hooks` stable, `multi_agent` stable
- Scratch install: success; `agents/*.toml`, `hooks.json`, `hooks/{handlers,lib,rules}` generated
- `hooks.json` schema vs native: **match**
- Actual edit tool: **`apply_patch`**
- Actual edit payload shape: **`tool_input.command` patch string**, not `tool_input.file_path`
- `PreToolUse` exit `2` blocked edit: **No for the observed `apply_patch` runs**
- Subagent depth-1: **works**
- Subagent depth-2: **blocked**
- Skill path discovery: **both `~/.agents/skills` and `~/.codex/skills` were observed**

## 8. Cleanup

After capture:

- temporary probe hooks removed
- original `~/.codex/hooks.json` restored
- temporary `~/.codex/agents/*.toml` removed
- temporary live test files removed

