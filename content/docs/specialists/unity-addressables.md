# Unity Addressables — specialist reference

Use for a project using Addressables or explicitly evaluating asset delivery options. Direct
references, Resources and SceneManager can fit other scopes; do not mandate Addressables adoption.
Read pinned Editor/Addressables versions, build profile and platform. Verify uncertain API/handle
behavior with official docs/source. This is domain knowledge, not a loading-manager requirement.

## Grouping, packing and addresses

Group/pack according to co-residency, update cadence, dependency sharing, download overhead and
authoring workflow. Loading-context groups can help; asset-type groups are not inherently wrong.
Pack Together reduces bundle granularity; Pack Separately allows independent loading/updates but
adds bundle overhead. Label-based packing is useful when labels represent stable usage boundaries.

Inspect build layout/dependencies and actual download/residency costs before splitting shared assets.
Deduplication can reduce copies but increase dependency lifetimes or reload churn. There is no
universal MB target for groups, bundles or platform asset memory.

Addresses and labels should follow existing stable lookup contracts. Path-shaped addresses can be
valid; asset renames must not silently break persisted/external keys. Document shared meanings when
unclear, not every label by default.

## Loading and callback lifetime

LoadAssetAsync loads one asset; LoadAssetsAsync can load a set, with failure/partial-result behavior
depending on arguments/version. Choose individual or batch loads by independent lifetimes, filtering
and failure handling. Prefer asynchronous loading on interactive paths; synchronous waits have
platform/operation limitations and can stall or deadlock. Verify support before a justified blocking
path rather than introducing it as a convenience.

Preload when measured first-use latency would violate the experience, balancing memory against
startup time. Existing owner-scoped loading may suffice; do not add a global manager or duplicate
reference-counting layer without a current shared-ownership requirement.

Check completion status before consuming results. A screen/object may disappear or request different
content before completion: validate ownership/request identity, ignore stale results, and still release
owned resources. Ending a coroutine or abandoning a request does not prove the underlying operation
was canceled. Use Unity APIs on the supported thread and handle destroyed Unity objects correctly.

## Handle and instance ownership

- Match each owned load/acquisition with the documented release path when its results are no longer
  needed. Keep the owning handle alive while consumers depend on assets; copied handle structs are
  aliases, not automatically independent acquisitions.
- Handle failure paths too. Release an owned failed-operation handle unless the API/options already
  auto-released it; batch failure semantics differ. Avoid double release and use after release.
- InstantiateAsync creates an Addressables-managed instance. Pair it with the supported ReleaseInstance
  overload. With tracking disabled, retain the operation handle needed for release rather than assuming
  the GameObject-only overload can locate it.
- Loading a prefab then using Object.Instantiate is a different valid path: ordinary clones do not
  acquire Addressables references. Destroy clones through their owner and retain the prefab/dependency
  handle until no clone needs it.
- Release is reference-count/lifetime bookkeeping, not a guarantee of immediate physical memory
  reclamation. Bundles/dependencies may remain resident for other users. Measure memory and asset churn;
  do not release shared content indiscriminately at every scene transition.

## Scenes and remote content

When using LoadSceneAsync, pair unload with the documented Addressables scene/operation lifecycle.
Scene unload does not release all separately loaded assets or other owners' handles. Preserve
activation sequencing and moved/persistent object dependencies during additive loading and unload.
Other scene APIs can coexist when their ownership is explicit.

Choose compression and bundle layout from supported build/load paths, download size, CPU and cache
costs; do not prescribe LZMA/LZ4 solely by local versus remote location. Keep player, platform bundles
and catalog versions compatible. Content-update builds must preserve the required previous build-state
artifacts and respect the package's update restrictions. Do not strip or replace dependencies still
needed by deployed players.

Remote hosting/CDN, caching, retry/backoff, progress and offline fallback follow actual product needs.
Validate catalog/bundle deployment coherence and download failure behavior; retry needs bounds and
terminal error handling. Offline play and cached rollback are not automatically supported by merely
versioning a catalog. Keep trust validation and separately authorized publication boundaries intact.

## Verification

Use the version's build-layout/Analyze/profiling tools where useful. Compare Editor asset-database
iteration with built content and actual player behavior; they are not equivalent evidence. Test fresh
install, supported upgrades/skipped releases, cached/offline states, failure, scene transitions and
consumer destruction as applicable. Measure peak residency, dependency churn and first-use latency
on target hardware without imposing fixed memory or load-time limits. Unavailable runtime is not_run.
See [UI](unity-ui.md) for screen lifetime.

Official references (these versions illustrate contracts; follow the project's pinned package):

- [Memory management](https://docs.unity3d.com/Packages/com.unity.addressables@1.21/manual/MemoryManagement.html)
- [Operation handles](https://docs.unity3d.com/Packages/com.unity.addressables@1.21/manual/AddressableAssetsAsyncOperationHandle.html)
