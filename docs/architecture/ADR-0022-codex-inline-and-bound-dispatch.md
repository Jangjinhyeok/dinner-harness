# ADR-0022: Codex inline default and bound optional dispatch

- Date: 2026-09-10
- Status: implemented locally; HIGH changes await user acceptance; live installation not performed
- Supersedes: default-workflow portions of ADR-0011, ADR-0013, ADR-0015, ADR-0020 and ADR-0021. Historical measurements remain unchanged.

## Decision

Codex with Astra is the primary interactive implementation session. A request authorizing implementation permits normal inspection, editing, and proportional verification without per-file approval or compulsory HANDOFF. Independent native agents are selected for useful independent boundaries, with explicit ownership and isolation for parallel writers. An important implementation receives independent review; HIGH acceptance remains the user's decision.

The existing `challenge/build` path is optional for delegated implementation or work requiring the controller's pinned scope/secret net. Inline tools and native hooks do not provide an equivalent all-I/O boundary. `run` remains an experimental legacy loop with explicit CLI model options; it does not implement the routing preset pipeline and rejects unsupported routing/effort options.

Real HIGH execution is refused in legacy `run`; its self-reported panel field cannot establish the bound challenge/review contract.

```text
User request → Codex inline → implementation → relevant checks → optional independent review → report
                          ↘ selected headless dispatch:
  HANDOFF → validate numeric prefix through first HIGH → max risk/compute → bound challenge evidence
          → Builder → delta even on error → scope/secret net → versioned result → calling-session review
```

Concrete model choices stay in `content/routing.toml`. Interactive recommendations do not change an active session. Native custom-agent TOML resolves explicit logical roles and read-only review permissions; headless dispatch resolves its eligible gate set before execution. Partial model overrides inherit their remaining fields from the active preset or an explicit vendor compatibility map. No vendor or billing fallback occurs on errors.

The Codex result contract is JSON schema version 1 (`orchestrator.bus.RESULT_SCHEMA`), passed via `--output-schema`. JSONL execution events and `-o` final output remain distinct. Builder self-review and verification claims are not independent review or controller-run tests. The controller renders RESULT.md and reports completed, blocked, pending, and needs-review gates separately. A no-op is valid. Format recovery is a single read-only invocation preserving the original report; it never repeats implementation.

Challenge evidence binds normalized repo, hashed task identity, exact draft, policy digest, and a separate invocation. Required evidence is atomically published after fsync. Observational log failure cannot manufacture evidence. Mock evidence cannot authorize a real dispatch. Use a unique `--task-id` when reusing the same HANDOFF filename for a new task; without it the stable repo/filename identity intentionally shares the cap across draft edits. A challenge is not implementation review or human approval.

Codex installation renders and preflights in a temporary tree, then updates only owned files. Unknown conflicts fail unless explicitly adopted with backups. Exact legacy hook definitions can be adopted; user hook definitions remain. Config.toml/auth are never replaced. Target selection keeps Codex-only installation independent of Claude live state.

## Alternatives

- Mandatory Architect/Builder CLI splitting: rejected as the default because it adds context transfer and consent loops to ordinary work; retained when explicitly selected.
- All gates or first gate for dispatch policy: rejected because either differs from the permitted execution prefix. The numeric prefix through first HIGH is both enforced in the prompt and checked in the result contract.
- A new orchestrator or broad safety rewrite: rejected; existing controller, vendor backends, bus, adapters, and handler subprocess contracts remain.
- Automatic legacy hook deletion: rejected; exact reviewed adoption with backup preserves unrelated hooks.

## Validation and limits

Baseline on Windows / Python 3.12.8: 284 tests, no failures, one platform skip. Installed Codex 0.153.4 help supports JSONL, output schema, and sandbox flags. Offline process tests exercise real Python child processes; Windows Job Objects prevent orphan writes after CLI exit. Current official docs support native subagents and trusted PreToolUse deny, but temporary-home model/hook enforcement is not_run because it has no authentication or trusted hook hashes. CLI config parsing alone does not establish model access or model/effort acceptance.

Synthetic scope/secret checks measured 0.113/1.054/5.532 seconds for 1/10/50 clean files on this machine. Optional batching is deferred to keep timeout, UTF-8, fail-closed, and pinned-fence behavior intact. See the dated migration report for final test counts and item-by-item status.
