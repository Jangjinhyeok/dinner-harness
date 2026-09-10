---
name: ue-umg-review
description: Use when reviewing or designing UMG widgets in Unreal Engine 5. Triggers on UMG widget code, UserWidget subclasses, widget tree changes, or performance discussions involving UI.
---

# UMG Widget Review Checklist

> For deeper UMG architecture/performance guidance, read [the UMG reference](../../docs/specialists/ue-umg.md).

Apply relevant checks to the project engine version, layout behavior and measured workload.
A missing preferred pattern alone is not a finding; report concrete failures with evidence.

## Widget hierarchy

- [ ] Investigate hierarchy/layout cost where nesting affects measured performance or clarity
- [ ] Use Overlay over Canvas Panel when absolute positioning isn't needed
- [ ] Evaluate Retainer Box redraw frequency, render-target cost and latency for the content
- [ ] Choose `Hidden` when layout space must remain and `Collapsed` when it must not; verify update/tick behavior separately

## Performance hot spots

- [ ] Evaluate widget Tick against update frequency, ordering, lifecycle and measured cost; keep it when appropriate for per-frame work
- [ ] Check binding evaluation/invalidation cost; use event-driven updates when they fit state ownership
- [ ] Image widgets with frequent texture swaps — consider Material parameter changes instead
- [ ] Text widgets with frequent updates — check if Slate caching is invalidated

## Scrollable content

- [ ] Use Scroll Box only when needed; List View / Tile View for many items
- [ ] List View item recycling — verify EntryWidget pooling is working
- [ ] Scroll position preservation across rebuild

## Gradient / texture rendering

- [ ] Material-based gradients over baked textures when parameterization needed
- [ ] Choose texture compression for UI quality and target memory requirements
- [ ] Choose mipmaps for actual display scale/filtering, including world-space UI

## Interaction patterns

- [ ] Input focus management explicit (especially for gamepad)
- [ ] Navigation rules defined for widget switcher / panels
- [ ] Drag-drop operations: clean up dragged widget on drop

## Localization readiness

- [ ] Use the project FText/localization conventions for localizable player-facing text
- [ ] Layout flexible enough for longer translated strings
- [ ] RTL language considerations if applicable

---

Report demonstrated issues; optional suggestions need a task-specific benefit. An ordinary UMG review does
not authorize editing this skill or other harness policy.
