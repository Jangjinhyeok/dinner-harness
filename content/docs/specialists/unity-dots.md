# Unity DOTS / ECS — specialist reference

Use when the project uses Entities/Jobs/Burst or evaluates them for a concrete workload. Entity
count alone does not justify migration from MonoBehaviour. Compare measured throughput/memory,
authoring, debugging, integration and platform requirements. This reference does not require delegation.
Read pinned Editor, Entities, Collections, Burst and Entities Graphics versions; verify uncertain
APIs and safety constraints with the matching official docs/source.

## Components and data layout

Unmanaged component data supports chunk-based processing and Burst-compatible paths. Managed
components are valid for appropriate integration but have GC/access restrictions and cannot be
accessed from jobs or Burst-compiled code. Component methods alone are not forbidden; preserve
supported field/layout/serialization constraints for the chosen component kind.

Choose component boundaries by access pattern, ownership, update frequency and chunk utilization.
Do not split because a struct exceeds a field count, or separate related state when doing so obscures
its invariants. Shared components can group entities but high value diversity can fragment chunks.
Tag components need no per-entity payload but still affect archetypes/querying; they are not cost-free.

Dynamic buffers suit variable-length entity data; choose capacity from measured distributions.
Enableable components can avoid structural changes for supported toggles, but affect query matching
and dependency behavior. Blob assets suit shared immutable data with explicit ownership/disposal.
Preserve baking, serialization and save/network compatibility when changing layouts or representations.

## Systems, queries and ordering

SystemBase and ISystem have different managed/unmanaged and Burst capabilities. Select for current
API needs and measured cost, not as a universal upgrade. Systems can own appropriate queries, caches
and resources; they need not be stateless. Keep persistent gameplay state where the project's
serialization, World lifetime and ownership contracts require it.

Use system groups and ordering attributes for logical phases, but ordering of system callbacks alone
does not establish every scheduled job dependency. Initialize/clean up system-owned resources through
the applicable lifecycle and account for World destruction or stopping/restarting updates.

Queries should match the required population; an all-entity query can be valid for a global task.
Use supported filters, enableable-state rules and read/write access declarations. Reuse queries where
it reduces setup cost without stale state; update lookups/handles as required by the package version.
Read-only declarations must match actual access, not just serve as optimization annotations.

## Jobs and structural changes

IJobEntity suits entity iteration, IJobChunk suits chunk-level access and IJob can suit independent
work. Small workloads may be clearer/cheaper on the main thread. When scheduling, propagate every
read/write dependency and use supported parallel access patterns. Never bypass safety restrictions
to hide an unresolved race.

Complete the relevant dependencies before main-thread access, disposal or other operations that
require ownership back. Immediate Complete can be correct when the result is needed immediately;
measure the lost overlap and scheduling overhead instead of banning synchronization.

Use ECB recording for structural changes requested by jobs. Its playback must occur at a valid
synchronized point, with producer dependencies registered and appropriate parallel-writer/order
semantics. Select the playback phase for when consumers need the changes; EndSimulation is not the
only valid phase. Direct main-thread EntityManager structural changes can be valid when synchronized,
but can introduce sync points and invalidate lookups/references.

## Burst and native allocation safety

Burst supports a restricted subset of C# and data types. Ordinary managed objects/collections are
not valid job/Burst data; use supported native collections, fixed strings and math operations where
appropriate. Confirm package/runtime support, not a blanket language-wide ban on managed code.

Dispose owned native allocations after dependent users finish, or through a supported deferred
disposal path. Allocator.Temp, TempJob and Persistent have different thread/lifetime constraints;
check their documented maximum lifetime rather than describing TempJob as generically frame-scoped.
For Collections versions with the four-frame TempJob rule, that is an allocator contract, not a
performance heuristic. Non-owning aliases must not double-dispose shared storage.

Use Burst Inspector and profiling to evaluate vectorization, access locality, capacity, copies and
branches. Branchless math.select can evaluate unwanted work and change numeric behavior; do not
replace branches without correctness and performance evidence.

## GameObject / rendering integration and verification

Use the installed Entities Graphics/baking/transform pipeline where it fits. GameObject companions
or a hybrid boundary may suit UI, audio, VFX or managed APIs; features differ by package/platform.
Follow supported transform components and system ownership rather than mutating competing transform
representations. Synchronize data crossing the boundary with clear entity/object lifetime.

Test job dependencies, ECB visibility/order, World teardown, allocator lifetime and baking/player
behavior. Profile representative target workloads against the current implementation. Unavailable
Editor/player checks are not_run. See [shaders](unity-shader.md) for render integration.

Official references (select matching package versions):

- [Managed components](https://docs.unity3d.com/Packages/com.unity.entities@1.0/manual/components-managed.html)
- [ISystem lifecycle](https://docs.unity3d.com/Packages/com.unity.entities@1.0/manual/systems-isystem.html)
- [Allocators](https://docs.unity3d.com/Packages/com.unity.collections@2.1/manual/allocator-overview.html)
