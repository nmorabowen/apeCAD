# ADR 0035 — Scratchpad state store, two-signature reconciler, and dirty-flagged render loop

**Status:** Accepted (2026-10-24)

## Context

The 3-D scratchpad client (`src/apeCAD/scratchpad/static/js/`) originally mutated `S` in `state.js` directly and called `rebuild()` on every selection click, filter switch, or scene change. That coupled three distinct update frequencies:

1. **Full 3-D geometry realization** (`revision`, `hiddenIds`, `theme`/viz changes): tearing down and recreating every `BufferGeometry` and `Material` in `draft`, rebuilding the workplane `grid`, and replacing the `#tree` DOM (`treeEl.innerHTML = ""`).
2. **Selection and hover highlights** (`selectedIds`, `hoverIds`, `selectFilter`): tinting already-built meshes/lines and toggling `.selected` / `.hovered` classes on outliner rows plus refreshing `#prop-body`.
3. **Viewport frame presentation**: an unconditional 60 fps `requestAnimationFrame(tick)` loop recomputed `sceneBounds3()` inside `updateClipPlanes()` and traversed `grid` in `syncGridLineResolution()` on every frame even when the scene and camera were completely idle.

In addition, several client modules imported each other in cycles (`commands.js ↔ input.js`, `outliner.js ↔ render.js ↔ selection.js`, `draw.js ↔ section.js`, `modify.js ↔ tools.js`), making module initialization order fragile.

## Decision

1. **Pure client store (`static/js/store.js`) synchronized with `S` (`static/js/state.js`).**
   - `reduce(state, action)` is a pure function over serializable/immutable client state slices (`revision`, `sceneState`, `tool`, `selectFilter`, `selectedIds`, `hoverIds`, `hiddenIds`, `cutterIds`, `projection`, `useOrtho`, `namedView`, `theme`).
   - `Store` exposes `get()`, `dispatch(action)`, and `subscribe(listener)` and mirrors state changes onto `S` so existing modules and tests continue to work without regressions.
2. **Two-signature coalesced reconciler (`createReconciler`).**
   - Coalesces synchronous bursts of dispatches into one realization pass ("one gesture, one realize").
   - Splits realization by two signatures:
     - `geometrySignature(state)` (`revision`, `hiddenIds`, `theme`, `vizKey`): triggers full `rebuild()` + `rebuildTree()` + `rebuildGrid()`.
     - `selectionSignature(state)` (`selectedIds`, `hoverIds`, `selectFilter`, `cutterIds`): updates 3-D entity/B-rep selection tints and `#tree` `.selected` / `.hovered` classes in place without wiping `draft` or `#tree`, refreshes `#prop-body`, and requests a render frame.
3. **Cross-surface hover.**
   - Hovering an outliner row (`#tree`) or the status warning chip (`#status`) dispatches `hoverIds` and highlights matching 3-D entities in `preselects`.
4. **Dirty-flagged render loop (`requestRender`) and cached bounds.**
   - Replace the unconditional 60 fps `tick()` loop with an on-demand `requestRender()` scheduler that renders only when dirty or while `viewAnim` is active.
   - Cache `sceneBounds3` per `sceneState` / `revision` instead of recomputing it every frame in `updateClipPlanes()`.
   - Run `syncGridLineResolution()` only on viewport resize and `rebuildGrid()`.
5. **Acyclic client module graph.**
   - Break all circular imports in `static/js/` and guard the directed acyclic import graph in `tests/test_client_modules.py`.

## Alternatives rejected

| Rejected | Why |
|---|---|
| Keep calling `rebuild()` on selection and hover | Destroys and recreates GPU buffers and `#tree` DOM nodes on every click, breaking double-click/rename stability and wasting frame time. |
| Pull in Redux / Zustand / React | Violates ADR 0003 and ADR 0023 (vanilla ES modules, no Node build step). |
| Keep an unconditional 60 fps render loop | Wastes CPU/GPU in background tabs and laptops when no camera, ghost, or scene state has changed. |

## Consequences

- `static/js/store.js` is a pure module tested under `node --test` (`tests/js/store.test.mjs`).
- `render.js` and `outliner.js` separate full geometry/tree rebuilds from in-place selection/hover updates.
- `tests/test_client_modules.py` enforces an acyclic import graph across `static/js/*.js`.
