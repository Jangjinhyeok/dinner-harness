# UE Gameplay Ability System — specialist reference

Apply when the project uses GAS or the task evaluates adoption. Ability/effect complexity and
prediction may justify GAS; combat or numeric stats alone do not. This is domain knowledge, not
an invocation contract. Check pinned Unreal/GameplayAbilities versions and verify uncertain APIs,
effect components and prediction behavior against official docs or engine source.

## Ability ownership and activation

The ASC manages grants, activation and effects for its owner/avatar. Verify actor-info initialization
when possession, respawn or avatar changes occur. Keep ASC/AttributeSet objects reachable through
engine lifetime/GC mechanisms; preserve reflection, replicated properties and serialized contracts.

Direct inheritance from UGameplayAbility is valid. A project base class helps when abilities share
real behavior/invariants, not merely to satisfy a pattern. Choose instancing and net execution
policies for state, concurrency and authority. Mutable per-actor state must not live in a shared
non-instanced ability object.

Use supported ASC activation paths and respect CanActivateAbility checks. Overrides must preserve
applicable base checks, authority, tags and resource conditions. Do not replace activation with an
unchecked direct call. Activated abilities must finish/cancel through their lifecycle, including
EndAbility where required, so blocking state and owned work do not linger.

## Costs, cooldowns and effects

Gameplay Effects integrate with GAS costs, cooldowns, aggregation, stacking and supported prediction.
Prefer them when those semantics are needed. Initialization, authoritative base-value changes or a
project resource system may use other supported paths if notifications, aggregation, replication
and authority remain correct. Direct field writes bypassing required ASC behavior are unsafe;
absence of a GE alone is not a defect.

CommitAbility is the standard combined cost/cooldown commitment path. Check its result and place
commitment at the intended consumption point. It is not a transaction rolling back arbitrary
gameplay side effects. Custom/separate commitment needs failure, interruption and duplicate-execution
handling to avoid charging twice or granting benefits without the required cost.

Choose Instant/duration/infinite effects by persistence and removal semantics. Instant and periodic
executions can modify base values; non-periodic duration modifiers typically contribute to current
values while active. Do not assume every GE changes only current value. Verify the mutation path
before clamping or reacting.

Modifiers suit supported value operations; executions/custom calculations suit more involved
calculations. Compare capture timing, authority and prediction support. Shared GE definitions are
not per-application mutable state; use supported spec/runtime paths. Data-only assets aid tuning;
native configuration may fit existing authoring conventions.

For stackable effects, check effective defaults/configuration against limits, refresh, expiry,
source/target aggregation and removal requirements. Overriding every default or writing a document
per effect is unnecessary when behavior is already clear and correct.

## Attributes and tags

Group attributes by ownership and dependencies. Preserve base/current semantics and actual gameplay
ranges; do not impose artificial min/max on every attribute. PreAttributeChange/PreAttributeBaseChange
can enforce relevant value constraints. PostGameplayEffectExecute handles execution-related reactions,
not every possible attribute update. Cover other required mutation paths and avoid recursive reactions.
Use supported initialization and preserve registered AttributeSet lifetime.

Tags suit hierarchical matching, blocking/cancellation and shared contracts. Not every ability needs
the same tag set; enums/booleans can suit local state. Register tags with supported project native,
config or data sources. RequestGameplayTag retrieves registered tags and is not a forbidden pattern.
Keep shared meanings discoverable without mandating a new document or naming taxonomy.

## Ability Tasks and asynchronous work

Ability Tasks suit montage, targeting and event flow owned by an ability. Timers/delegates can also
fit with correct cancellation and cleanup. Handle the success, interruption, failure and cancellation
paths exposed by the chosen task; there is no universal OnCancelled delegate on every task.

Finish custom tasks through supported EndTask/lifecycle paths; clean external subscriptions in
teardown and preserve required Super calls. Prevent late callbacks using ended abilities or destroyed
avatars. Server execution does not automatically require replicated task state. Replicate what the
remote execution/target-data contract needs, validating consequential client input.

## Prediction and replication

LocalPredicted can improve responsiveness when reconciliation is supported. Other execution policies
can be appropriate. Preserve server validation regardless. Use GAS prediction-key/scoped mechanisms
on supported paths; arbitrary executions, side effects and GE configurations are not all safely
predictable. Test rejection, interruption and duplicated/missing cosmetic feedback.

ASC effect replication modes control effect information, not automatic replication of every ability
or attribute. Full sends full effect information, Mixed limits full information to owners/autonomous
proxies, and Minimal sends minimal effect information. Choose for client needs, ownership setup and
bandwidth; verify exact behavior in the project version.

Attributes still need replication/RepNotify configuration and GAS notification handling where
replicated. Applying a GE alone does not configure attribute replication. Keep cues/presentation
separate from authoritative gameplay state.

## Verification and references

Test activation failure, cancellation, cost timing, stacking/expiry, avatar replacement, late join,
prediction rejection and attribute notifications as relevant. Use project automation/multiplayer
checks; unavailable runtime validation is not_run. See [replication](ue-replication.md) and [UMG](ue-umg.md).

Official references (select the project's version):

- [Gameplay Effects](https://dev.epicgames.com/documentation/en-us/unreal-engine/gameplay-effects-for-the-gameplay-ability-system-in-unreal-engine)
- [Effect replication modes](https://dev.epicgames.com/documentation/unreal-engine/API/Plugins/GameplayAbilities/EGameplayEffectReplicationMode)
