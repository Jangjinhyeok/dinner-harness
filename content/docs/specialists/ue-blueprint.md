# UE Blueprint Architecture — specialist reference

Use for Blueprint/C++ boundaries, graph design and runtime behavior. This is domain knowledge,
not a separate agent or delegation requirement. Follow the project's pinned Unreal version and
current conventions; verify uncertain/version-dependent APIs with official docs or engine source.

## Choosing the Blueprint/C++ boundary

Choose from iteration speed, designer ownership, debugging, testability, available APIs and
measured runtime cost. Blueprint can implement gameplay, replication and tests when its tools fit
the contract. C++ can help with native APIs, reusable infrastructure or measured Blueprint overhead;
a system label or instance count alone does not require a port.

A native framework with Blueprint content variations is useful when responsibilities divide that
way. Blueprint-only and native-only features can also fit. Reuse existing boundaries before adding
a base class, interface, plugin or module.

At mixed boundaries, use BlueprintCallable for intended calls, BlueprintNativeEvent for overridable
behavior with a native implementation, and BlueprintImplementableEvent for Blueprint implementation
hooks. Preserve reflection signatures and metadata. Expose intended editing surfaces rather than
defaulting every field to EditAnywhere/BlueprintReadWrite.

## Graph readability and reuse

- Judge execution/data flow, responsibility, debugging difficulty and actual reuse. A graph over
  20 nodes is not inherently defective; explicit state transitions may be clearer intact.
- Extract functions for meaningful contracts or reuse, not screen size or node count. Choose
  functions/macros/libraries from execution and latent-action constraints, context and debugging.
- Comments, reroute nodes and comment boxes help explain non-obvious flow. Their colors,
  placement and frequency are project conventions, not engine requirements.
- Follow existing asset/variable naming. BP_, BPI_ and BPFL_ can aid discovery but are not universal
  engine rules. Renaming assets has reference and packaging costs.
- Interfaces suit polymorphic behavior across types; a cast/direct typed reference is valid when
  the concrete dependency is intended. Do not introduce an interface merely to remove a cast.
- Data-only Blueprints suit authored variations. Data Assets/Tables may fit other schema,
  validation and loading needs; select by workflow rather than an entry-count threshold.

## Lifetime, state and events

Preserve UObject creation, GC reachability, reflection and serialized asset contracts. Retained
references must keep required objects reachable or tolerate destruction. Use engine creation paths,
not new/delete for UObjects. Validate targets across latent actions, travel and async load callbacks.

Bind/unbind delegates for the actual owner lifetime. BeginPlay/EndPlay can suit Actors; widget and
subsystem lifetimes differ. Prevent duplicate subscriptions and callbacks into expired owners.
Refresh or invalidate cached references when their targets change.

Tick/polling can suit per-frame or sampled state; events can suit change notifications. Compare
freshness, ordering, initial synchronization, lifetime and cost. An event alternative alone does
not make polling wrong. Gameplay Tags/events fit existing tag-based contracts, not every feature.

For multiplayer preserve authority, owning connection, RPC and replicated-state behavior across
the Blueprint/C++ boundary. A port must preserve wire/save compatibility and base lifecycle behavior.

## Loading, performance and verification

Hard references provide direct access and can load dependencies; soft references support deferred
loading but require completion/failure and lifetime handling. Inspect dependency and cooking behavior
instead of replacing every direct reference.

Profile the workload with supported Unreal/Blueprint tools. Investigate repeated casts, searches,
allocations or iteration in hot paths by measured cost and target lifetime. Caching, spatial queries,
update frequency changes and native code are options, not automatic fixes. Do not assume legacy
Blueprint nativization is available in the project's engine/toolchain.

Verify Blueprint compilation and relevant runtime/automation scenarios, including failure paths,
loading, destruction and multiplayer. Unavailable engine checks are not_run.
For widget addition/deletion, reparenting or reflected-binding changes, compile and save, then
reload the affected saved packages in a fresh process and run targeted validation. Same-session
success does not establish persisted-state correctness. Investigate relevant load ensures and
stale serialized metadata instead of dismissing them as noise. If loading repairs metadata,
save the repaired package and repeat the fresh-process check before PASS. Do not prescribe manual
metadata surgery without pinned engine evidence. Cosmetic text/color-only edits need only their
relevant checks; unavailable engine/reload verification remains not_run.
See [UMG](ue-umg.md) and [replication](ue-replication.md) for adjacent contracts.
