## Codex hook enforce retest

Date: 2026-06-19
Repo: `C:\Users\zero9\Documents\Github\dinner-harness`
Codex: `codex-cli 0.141.0`

### Scope and deviation

- Requested target was a normal trusted `~/.codex/hooks.json` path.
- That exact trust flow was not automatable from this shell: `codex --no-alt-screen "/hooks"` failed with `stdin is not a terminal`.
- To keep `dangerously-bypass-hook-trust` out of the path and still test normal runtime semantics, I used:
  - managed system hook source: `C:\ProgramData\OpenAI\Codex\hooks.json`
  - normal app-server thread/turn path: `codex debug app-server send-message-v2`
- In that path, `thread/start` reported:
  - `approvalPolicy = "on-request"`
  - `activePermissionProfile = ":workspace"`
  - `sandbox.type = "workspaceWrite"`
- Hook payloads recorded `permission_mode = "default"`.

### Previous contaminated conclusion

- The earlier preflight conclusion was contaminated by `codex exec --json --dangerously-bypass-hook-trust`.
- That path previously logged `permission_mode = "bypassPermissions"`, so it was not a valid enforce test.

### 1. PreToolUse exit-2 blocks `apply_patch`?

Result: **NO**

Evidence:

- Hook fired in a normal `on-request` session.
- Raw payload captured:

```json
{"session_id":"019eddbf-6161-7201-be46-eaafc11c677e","turn_id":"019eddbf-75f5-7631-9802-aa893e620148","transcript_path":"C:\\Users\\zero9\\.codex\\sessions\\2026\\06\\19\\rollout-2026-06-19T11-39-32-019eddbf-6161-7201-be46-eaafc11c677e.jsonl","cwd":"C:\\Users\\zero9\\Documents\\Github\\dinner-harness","hook_event_name":"PreToolUse","model":"gpt-5.4","permission_mode":"default","tool_name":"apply_patch","tool_input":{"command":"*** Begin Patch\n*** Update File: C:\\Users\\zero9\\Documents\\Github\\dinner-harness\\_codex_hook_retest_target.txt\n@@\n-alpha\n+beta\n*** End Patch\n"},"tool_use_id":"call_z7aLtnuVOeEfMGiXjnjCC2kB"}
```

- App-server stream showed:
  - `hook/started` for `preToolUse`
  - `hook/completed` with `status = "failed"`
  - entry text: `hook exited with code 1`
- Despite that, the `fileChange` item completed and the file changed from `alpha` to `beta`.

Notes:

- The probe handler itself was directly validated outside Codex and returned `EXIT=2`.
- So the observed behavior is: even when the handler is intended to exit 2, Codex 0.141 did not block `apply_patch` in this normal session path.

### 2. PermissionRequest deny blocks `apply_patch`?

Result: **NO** in this tested path

Observed payload:

```json
{"session_id":"019eddc0-4b47-7e61-ba5d-a853618aeee3","turn_id":"019eddc0-5fdc-73f3-8287-e44929539933","transcript_path":"C:\\Users\\zero9\\.codex\\sessions\\2026\\06\\19\\rollout-2026-06-19T11-40-32-019eddc0-4b47-7e61-ba5d-a853618aeee3.jsonl","cwd":"C:\\Users\\zero9\\Documents\\Github\\dinner-harness","hook_event_name":"PermissionRequest","model":"gpt-5.4","permission_mode":"default","tool_name":"apply_patch","tool_input":{"command":"*** Begin Patch\n*** Update File: C:\\Users\\zero9\\AppData\\Local\\Temp\\codex-hook-retest\\outside.txt\n@@\n-one\n+two\n*** End Patch"}}
```

Format findings:

- `{"decision":"decline"}` was rejected as invalid:
  - `hook returned invalid permission-request JSON output`
- Bare JSON string `"decline"` was accepted:
  - `hook/completed` with `status = "completed"`
  - no hook error entries

But blocking still did not happen:

- After the valid `"decline"` hook result, Codex still emitted `item/fileChange/requestApproval`.
- The `send-message-v2` debug client then auto-responded:

```json
{"decision":"accept"}
```

- The file edit completed and `outside.txt` changed from `one` to `two`.

### 3. Native block mechanism recommendation

Recommendation: **Do not rely on `PreToolUse` exit-2 for enforce.**

Observed runtime suggests the real block point for file edits is the approval layer after `item/fileChange/requestApproval`, not `PreToolUse`.

Concrete implications:

- `PreToolUse` failure did not stop `apply_patch`.
- `PermissionRequest` hook accepted a bare `"decline"` literal, but that still did not suppress the downstream file-change approval request in this client path.
- In `codex debug app-server send-message-v2`, the helper auto-accepts file-change approvals, so this surface is unsuitable for proving user-visible deny behavior.

Most defensible current reading:

- For `apply_patch`, the actual deny contract that matters is the approval response to `item/fileChange/requestApproval`.
- Version-matched app-server schema names that response `FileChangeRequestApprovalResponse`, with decision literals:
  - `accept`
  - `acceptForSession`
  - `decline`
  - `cancel`

Inference:

- If you need hard blocking in Codex 0.141, the reliable path is likely:
  - deny at the file-change approval response layer, or
  - deny by permissions/sandbox/profile policy
- Not `PreToolUse` exit-2.

### Summary

- Normal-session `permission_mode`: `default`
- `PreToolUse` exit-2 blocks `apply_patch`: **NO**
- `PermissionRequest` deny blocks `apply_patch`: **NO** in tested app-server helper path
- Corrective schema fact:
  - `PermissionRequest` did not accept object output `{"decision":"decline"}`
  - It accepted bare JSON string `"decline"`
