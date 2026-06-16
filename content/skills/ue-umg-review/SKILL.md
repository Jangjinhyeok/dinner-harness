---
name: ue-umg-review
description: Use when reviewing or designing UMG widgets in Unreal Engine 5. Triggers on UMG widget code, UserWidget subclasses, widget tree changes, or performance discussions involving UI.
---

# UMG Widget Review Checklist

This developer has done significant UMG work and accumulated these review points. Apply when reviewing or designing UMG widgets.

## Widget hierarchy

- [ ] Avoid unnecessary nesting (each level costs render time)
- [ ] Use Overlay over Canvas Panel when absolute positioning isn't needed
- [ ] Retainer Box only when the content actually doesn't change frequently
- [ ] Invisible widgets: use `Collapsed` not `Hidden` (Hidden still ticks)

## Performance hot spots

- [ ] Tick events on widgets — remove if not strictly needed
- [ ] Bindings (especially function bindings) — these tick. Prefer event-driven updates
- [ ] Image widgets with frequent texture swaps — consider Material parameter changes instead
- [ ] Text widgets with frequent updates — check if Slate caching is invalidated

## Scrollable content

- [ ] Use Scroll Box only when needed; List View / Tile View for many items
- [ ] List View item recycling — verify EntryWidget pooling is working
- [ ] Scroll position preservation across rebuild

## Gradient / texture rendering

- [ ] Material-based gradients over baked textures when parameterization needed
- [ ] Texture compression: UI textures should be User Interface 2D compression
- [ ] Mipmaps off for UI textures

## Interaction patterns

- [ ] Input focus management explicit (especially for gamepad)
- [ ] Navigation rules defined for widget switcher / panels
- [ ] Drag-drop operations: clean up dragged widget on drop

## Localization readiness

- [ ] No hardcoded strings — use FText with namespace
- [ ] Layout flexible enough for longer translated strings
- [ ] RTL language considerations if applicable

---

This list grows. Add new patterns when you spot a UMG issue that wasn't caught here.