# UE UMG / CommonUI — specialist reference

Read for layout, state updates, input and widget lifetime. Check pinned engine/plugins and UI
conventions; verify uncertain/version-dependent APIs with official docs/source. CommonUI and MVVM
are choices, not prerequisites for UMG. This document does not create a specialist role.
The ue-umg-review skill provides a compact companion checklist.

## Hierarchy and screen ownership

Organize screens by actual modal/input/z-order and lifetime requirements. HUD/menu/popup/overlay
layers can help complex products; simple screens need not introduce every layer. Make parent,
controller and data dependencies explicit. A widget may depend on a parent-owned model. Preserve
authoritative gameplay ownership while allowing UI-owned presentation/selection state.

Widget Blueprints suit authored layout; C++ can support shared logic/native APIs. Use the existing
boundary instead of requiring a native base for every widget. Choose Canvas, Overlay, box or grid
layouts by positioning/responsiveness. Depth alone is not a defect; examine readability and layout cost.

## CommonUI when adopted

UCommonActivatableWidget fits screens participating in CommonUI activation/input routing. Stack and
queue containers can manage last-in-first-out navigation or first-in-first-out presentation.
UCommonButtonBase supplies CommonUI button behavior when needed. Ordinary UUserWidget and other
buttons remain valid outside those contracts; do not require a plugin migration.

Configure supported input integration/action data for the pinned version. Activation, focus, routing
and consumption are related but distinct; focus alone does not define routing. Verify back handling,
modal boundaries, desired focus and restoration on deactivation. CommonInput can support device
prompts; configured devices and input policies determine the actual requirements.

## State updates and lifecycle

Choose direct model access, ViewModel/WidgetController, bindings, events, explicit refresh or NativeTick
from freshness, ownership, ordering and measured workload. NativeTick suits per-frame presentation;
events require initial synchronization and teardown. Gameplay Tag events fit tag-based state, not
every UI. Avoid duplicate update paths overwriting each other or producing repeated effects.

Widgets can outlive Pawns, players, requests and assets. Retain required UObjects through GC-aware
ownership, validate weak/expired targets and respect game-thread APIs. Match subscriptions to actual
activation/construction/destruction lifetime; repeated construction/reuse must not duplicate listeners.
Preserve base lifecycle behavior and cancel/ignore stale async completions, including after item rebinding.

For UListView/UTileView's UObject item API, supply compatible item objects; do not confuse it with
Slate's differently typed APIs. Virtualized entries can be reassigned: refresh item state on assignment
and clean subscriptions on release. Pooling transient widgets can reduce creation costs but adds
reset/residency complexity. Choose prewarming from measured latency/memory needs, not as a default.

## Input, styling and accessibility

Support required mouse/touch/keyboard/gamepad paths through the chosen input system. Non-CommonUI
projects need not use CommonUI input classes. Verify focusable controls, modal capture, device switching
and navigation across transitions.

Style assets/shared tokens support consistent themes; intentionally local styling is valid.
Use FText and project localization for localizable player-facing text. Check expansion, scaling,
contrast, non-color cues, subtitles, motion preferences and required screen-reader support against
product/platform requirements. Do not invent a fixed number of sizes or unrequested themes.

## Layout, performance and verification

Hidden keeps layout space; Collapsed removes it. Choose by intended layout behavior and evaluate
hit testing/update behavior separately. Invalidation and Retainer widgets have redraw, render-target
and latency trade-offs; compare with the existing invalidation system and dynamic content.

Compare targeted item refresh with full-list rebuilds; a fixed item count does not determine the
cheaper choice. Material changes, texture swapping, layout simplification and pooling need workload
measurements and visual checks. Use Widget Reflector and supported Slate/UI profiling against actual
platform budgets; there is no universal UI millisecond allowance.

Test focus/input, state changes, destruction, rebinding, loading failure and localization on configured
targets. Unavailable runtime checks are not_run. See [Blueprint](ue-blueprint.md) and [GAS](ue-gas.md).
When a feature is removed, reconcile its C++ bindings, widget hierarchy, references and metadata
with the requested removal boundary; Hidden/Collapsed placeholders are not full removal without
a compatibility requirement. Structural/binding changes need the Blueprint save/reload checks.
Visual verification must inspect a usable preview of the current target state. A blank/stale image
or successful capture command alone leaves layout verification not_run, not PASS; an observed
target layout defect is FAIL. Keep code inspection, visual checks and PIE validation separate.

Official reference: [ESlateVisibility](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/UMG/ESlateVisibility).
