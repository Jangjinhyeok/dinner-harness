# UE Replication / Networking — specialist reference

Start with the pinned engine version, configured replication system (including Iris/Replication
Graph where used), actor ownership and multiplayer requirements. APIs and conditions differ by
configuration; verify uncertain details against official docs or engine source. This is domain
guidance, not a requirement to delegate or redesign the network stack.

## Authority, trust and lifetime

The server must validate consequential client requests against authority, owning connection,
gameplay state, parameter ranges and allowed request rates. Client-reported position, damage or
inventory is not authoritative merely because it arrived through an RPC. Ownership controls routing;
it does not authorize arbitrary requested actions. Preserve anti-abuse checks and redact/rate-limit
diagnostic logs. A checksum does not authenticate untrusted client data.

Trace actor/component/subobject creation, registration, destruction and GC reachability. Replicated
references can be unresolved or disappear during travel/relevance changes. Async work must respect
target lifetime and thread affinity. Preserve RPC/property schemas, custom serializer compatibility
and relevant save contracts. Local implementation does not authorize wire-format changes or bypass
HIGH independent review and human acceptance.

## State and property replication

In the applicable native property path, use reflection replication metadata and registration such
as GetLifetimeReplicatedProps/DOREPLIFETIME, preserving inherited registration. Blueprint, push-model,
Iris and subobject paths need their configured contracts; one macro does not configure all replication.
Use ReplicatedUsing/RepNotify when receive-side reactions are needed and check invocation semantics.
OnRep naming style follows the project; required signatures do not.

Choose conditions from who needs state and when. OwnerOnly/SkipOwner affect visibility. InitialOnly
is initial-channel state, not a guarantee a value never changes after spawn. Custom active conditions
need the configured activation mechanism; a macro alone does not implement arbitrary per-connection
logic. Test late join, channel recreation and owner changes.

Replicate durable state when clients need its current value, including late joiners. Derivation can
save bandwidth when inputs/timing are sufficient; replicating computed values can suit authority,
precision or unavailable inputs. Intermediate transitions and cross-property callback ordering must
not be treated as a guaranteed event log.

For Characters, reuse CharacterMovementComponent's movement/prediction contract when it fits.
Generic replicated movement (FRepMovement) is not a replacement for that prediction protocol.
Custom movement needs explicit authority, reconciliation and cost analysis.

## RPCs and prediction

Server RPCs carry requests through appropriate owned replicated objects; Client RPCs route to the
owning client. Server-originated NetMulticast reaches applicable relevant clients, not every client
unconditionally, and is not persistent late-join state. Check execution rules and ownership.

Choose reliable/unreliable from loss tolerance and frequency. Frequent reliable traffic can queue
or saturate connections; unreliable cosmetic traffic can be lost. Reliability does not replace
persistent state or guarantee delivery after disconnect. Bound payloads/rates using actual limits
and load measurements; legitimate continuous input may require repeated messages.

Prediction helps latency-sensitive actions when effects/state can reconcile. Prefer existing
movement/GAS mechanisms where they fit; not every action needs prediction. Restore gameplay
correctness on rejection, choosing smoothing or snapping according to collision/state requirements.
For GAS prediction keys and supported effects see [GAS](ue-gas.md).

## Relevancy, dormancy and bandwidth

Select distance, ownership filters and priority from client observation requirements. Verify APIs
for the active replication system. For legacy Actors, NetCullDistanceSquared is a distance-squared
input, while NetUpdateFrequency controls replication scheduling, not gameplay Tick rate or guaranteed
delivery frequency.

Dormancy can reduce checks for infrequently changing Actors, but changes need appropriate wake/flush
handling before mutation so clients receive them. DORM_DormantPartial describes dormancy on some
connections, not automatic replication on property change; it is not supported/recommended in every
configuration. Check the project's engine support before use.

Quantization trades precision for payload size. Packing and delta/FastArray serialization add schema
and dirty-tracking obligations. Compression, derivation and update frequency need representative
measurements rather than fixed KB/s or Hz targets. Do not withhold state clients need for correctness
merely to hit a bandwidth target.

Use supported networking traces, Network Profiler/Insights or stat commands. Measure actor/property
costs, relevant-actor counts, packet loss and latency on representative workloads. Test travel,
disconnect/reconnect, late join, owner change, dormancy wake and prediction failure as relevant.
Unavailable multiplayer/runtime checks are not_run.

Official reference: [Actor network dormancy](https://dev.epicgames.com/documentation/unreal-engine/actor-network-dormancy-in-unreal-engine).
