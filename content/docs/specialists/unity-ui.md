# Unity UI — specialist reference

Start with pinned Editor/package versions, existing UI stack, input setup and supported platforms.
Check version-dependent UI Toolkit, uGUI and binding features against official docs/source.
This is domain knowledge, not a requirement to adopt a UI framework or invoke a separate agent.

## Framework and screen architecture

Choose UI Toolkit, uGUI or an intentional integration from authoring, existing content, rendering,
world/screen-space needs, animation, input, accessibility and measured cost. Do not universally
prefer UI Toolkit for new screens or assume its world-space/animation limitations are unchanged
across versions. Mixing frameworks can be valid with explicit focus, sorting and lifetime boundaries.

Split UXML/screens by ownership and reuse, not one-file-per-screen rules. Templates and shared USS
help reusable controls/themes; local or runtime styles can suit specific state. Naming conventions,
selector organization and theme count are project choices, not engine invariants. Keep selectors,
layout dependencies and style precedence understandable before optimizing hierarchy depth.

A stack fits hierarchical menus; tabs, independent panels or a simpler controller may fit other
navigation. Back/Escape behavior follows modal/product semantics, not an unconditional pop.
Assign creation, activation and teardown ownership for screens and their pending work.

## State updates and lifetime

Bindings, ViewModels, commands/events, explicit refresh and per-frame polling are options. Select by
freshness, ownership, ordering, available APIs and measured cost. In supported UI Toolkit binding
versions, INotifyBindablePropertyChanged can provide change notifications; it is not required for
all UI data sources or versions. Preserve authoritative game-state contracts while allowing local
presentation state and intended commands.

Match subscriptions to actual document/element lifetime. OnEnable/OnDisable can suit MonoBehaviour
ownership, but visual trees may be rebuilt or detached independently. Unregister callbacks and
release bindings/resources when their owner or item changes. Cached visual-tree references must be
reacquired after rebuilds; caching every query is not automatically correct.

Handle destroyed Unity objects and stale asynchronous completions, including after screen closure,
scene unload or pooled-item rebinding. Use Unity's lifetime-aware object checks as appropriate and
keep Unity API calls on supported threads. Retain assets while consumers need them and release
owned Addressables handles correctly; see [Addressables](unity-addressables.md).

## Input and focus

Support the project's required devices through its chosen input system. Do not migrate legacy
input merely to satisfy this reference. Verify click, navigation, submit/cancel and pointer semantics;
a low-level pointer-down callback is not equivalent to a complete button interaction.

Automatic navigation may suffice; explicit routes can resolve ambiguity. Set sensible initial focus,
restore valid prior focus and prevent unintended navigation/input behind modal screens. Device
connection changes are different from active input usage; choose the configured system's suitable
signals for prompt switching rather than assuming onDeviceChange identifies the current input method.

## uGUI layout and rendering

Choose Canvas render mode, camera and sorting from the intended composition. Separate Canvases can
isolate rebuild work but add rendering/batching costs; do not mandate one Canvas per layer or split
every dynamic control. Determine whether a change dirties layout, geometry or batching before claiming
the entire UI rebuilds.

Anchors/RectTransform and Layout Groups serve different adaptive-layout needs. Prefer the simplest
correct layout and profile recalculation; do not disable layout updates that content changes require.
GetComponent/visual-tree lookups may be worth caching on hot paths, but do not assume every call
allocates or that the target survives indefinitely.

CanvasGroup can control group opacity/input without eliminating all update cost. Disable unnecessary
raycast participation only when hit-testing behavior remains correct. For UI Toolkit, distinguish
visibility from display/layout participation using APIs supported by the pinned version.

## Lists, styling and accessibility

Virtualization can reduce list element work for large/expensive collections. Use the supported
ListView make/bind/unbind/destroy lifecycle, cleaning callbacks and item state as entries recycle.
uGUI pooling or virtualization can help measured creation/layout cost; a small static list need
not introduce it. Choose atlases by batching, packing and residency needs rather than placing all
sprites into one shared atlas.

Use project localization for localizable player-facing strings. Verify expansion, fonts, RTL where
required, text scaling, contrast, non-color cues, motion preferences, subtitles and supported assistive
technology against actual product/platform requirements. Web ARIA attributes are not automatically
Unity accessibility APIs. Touch target dimensions and text-size options need applicable platform
guidance, not a universal hardcoded number.

## Verification

Profile UI layout/rebuilds, event handling, allocations, rendering and memory on representative target
hardware with supported Profiler/UI Toolkit Debugger/Frame Debugger tools. Compare against project
budgets, not a fixed UI millisecond allowance. Test player behavior, required devices, modal focus,
tree rebuild, item reuse, destroyed data sources, async failure and localization. Missing Editor/
player/hardware checks are not_run. See [shaders](unity-shader.md) for material/pipeline integration.
