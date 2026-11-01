# Spec — Section embedding kit (stage C9)

**Status:** Implemented (2026-10-23); results overlay, client API 2 (2026-11-01, stage C2-S2)  
**ADRs:** 0023, 0024, 0025, 0026, 0038, 0041

## Goal

Provide an embeddable, zero-CDN 2-D HTML5 Canvas section and rebar client (`APECADSection`)
plus a stateless Python transport (`apeCAD.scratchpad.transport.handle`) so sibling web apps
(`ape-web-tools` HA-04, `apeWorkbench`) can host apeCAD section authoring inside their own
FastAPI / ASGI process without spawning a separate `ScratchpadServer`.

## Python embedding surface

| Symbol | Module | Contract |
|---|---|---|
| `CLIENT_API_VERSION = 2` | `apeCAD.scratchpad.section_assets` | Matches `API_VERSION = 2` exported by `apecad-section.js`. 2 adds the results overlay (ADR 0041 decision 2) and removes nothing of 1; a host that checks for 1 must accept 2. |
| `SECTION_DIR` | `apeCAD.scratchpad.section_assets` | `Path` to `src/apeCAD/scratchpad/static/section/`. |
| `client_files()` | `apeCAD.scratchpad.section_assets` | Returns `dict[str, Path]` mapping relative asset names (`apecad-section.js`, `transport.js`, `mock-transport.js`, `input-parse.js`, `canvas2d.js`, `overlay.js`, `section.css`, `index.html`) to absolute `Path`s. |
| `TRANSPORT_VERSION = 1`, `MAX_OPS`, `handle(request)` | `apeCAD.scratchpad.transport` | Stateless single-endpoint transport (`scene`, `apply`, `undo`, `redo`, `draft`, `load`, `seed`). Importing `section_assets` or `transport` never loads `scratchpad.server`. |

## Client surface (`apecad-section.js`)

```js
import { API_VERSION, create, httpTransport, mockTransport } from "/section/apecad-section.js";

const editor = create(container, {
  transport: httpTransport("/api/section/transport"), // or mockTransport(initialDraft)
  readOnly: false,
  units: "mm",
  onChange(draft) {
    // Fired on apply / undo / redo; NEVER fired on loadDraft or loadSeed.
  },
});
```

### Instance methods

- `await editor.loadDraft(payload)` / `await editor.load(payload)`: Load a `Document` dict, `apeCAD.section-draft` v1 dict, or `apeCAD.section-seed` v1 dict without firing `onChange`.
- `await editor.loadSeed(seedPayload)`: Load an `apeCAD.section-seed` v1 dict via `action: "seed"` without firing `onChange`.
- `editor.getDraft()`: Return the latest `apeCAD.section-draft` v1 dict.
- `editor.getScene()`: Return the normalized 2-D section scene payload.
- `await editor.applyOp(opOrOps)`: Apply one op or a list of ops and fire `onChange(draft)`.
- `await editor.undo()` / `await editor.redo()`: Undo or redo and fire `onChange(draft)`.
- `editor.setTool(toolId)`: Select active tool (`select`, `rect`, `polygon`, `opening`, `wall-chain`, `wall-leg`, `cover`, `bar`, `bar-row`, `bars-edge`, `hoop`, `crosstie`, `delete`).
- `editor.setParam(key, value)`: Set active tool parameter (`designation`, `hoop_designation`, `spacing_mm`, `count`, `thickness_mm`, `cover_mm`, `hooks`, `crosstie_hooks`, `gridStepMm`).
- `editor.fitView()` / `editor.resize()`: Fit the viewport to section bounds or resize to container.
- `editor.dispose()`: Detach event listeners and remove the root element from `container`.
- `editor.setOverlay(overlay | null)`: Show an `apeCAD.section-overlay` v1 overlay (see below), or clear it with `null`.
- `editor.getOverlayState()`: The overlay as the client holds it (see below).

The module also exports `parseOverlay` (the client's reader) and `MAX_OVERLAY_PRIMITIVES`.

## Results overlay (API 2, ADR 0041 decision 2)

The overlay contract is [`section-overlay.md`](section-overlay.md); the client's reader is
`overlay.js::parseOverlay`, which refuses every case of `tests/fixtures/section_overlay/` with
the same `code` and `path` as `apeCAD.render.overlay.parse_overlay`.

- **Result.** `setOverlay` returns `{ok: true, status: 200, ...state}` or, for an overlay the
  contract refuses, `{ok: false, status: 422, error: {code, path, message}}` (`code` is
  `INVALID_ARGUMENT`, or `TOO_LARGE` above `MAX_OVERLAY_PRIMITIVES`). A refused overlay
  replaces the one shown: nothing is drawn and the sidebar says `Overlay refused: <message>`.
  An overlay is never truncated.
- **State.** `getOverlayState()` returns `{active, revision, overlay_revision, stale,
  primitive_count, layers: [{id, label, visible, primitives, scale}], refusal}`. `revision`
  is the live document revision; `scale` is the scale's kind or `null`.
- **Revision.** When a transport response carries an integer `revision` (the mock transport
  does), the client takes it. The stateless Python transport sends none, so the client counts
  its own edits: each successful `apply`, `undo`, `redo`, `load` and `seed` adds 1. A host
  stamps an overlay with `getOverlayState().revision` read when it took the draft.
- **Stale.** When `revision > overlay_revision`, the client paints the overlay at
  `STALE_ALPHA` (0.35) of its opacity, dims its legends and shows a `stale` badge. It never
  hides it and never recomputes it. An undo is an edit, so it does not make an overlay current.
- **Draw order.** Section, then the overlay, then the selection, stroked again on top. The
  ghost preview and the snap marker stay above all three. The overlay is display only: hit
  testing and snapping ignore it.
- **Panel.** The sidebar lists each layer's `label` (`(hidden)` after a hidden one) and one
  legend per visible layer with a scale: the title and unit, a gradient bar with the domain
  values (numeric scales) or a swatch per category.
- **Text and colour.** Every overlay string reaches the page through `textContent` and the
  canvas through `fillText`, never as markup. Colours are validated by the reader. A token
  resolves from the live theme (the host page's CSS custom property, when it is a hex colour)
  and otherwise to its light value, `canvas2d.js::OVERLAY_TOKENS`, which equals
  `apeCAD.render.overlay.COLOR_TOKENS`.
- **Example scales.** `canvas2d.js::OVERLAY_EXAMPLE_SCALES` (`stress` diverging, `strain`
  sequential, `bar_state` categorical) pass the ADR 0038 gates on the client canvas
  (`tests/js/section-overlay.test.mjs`): the marking colours (every category, and both ends
  of a numeric scale) reach 2.2:1 contrast on the canvas, and every pair of categories, and
  every pair of neighbouring stops, is at least 0.055 apart in OKLab under normal vision,
  protanopia and deuteranopia. Red against green fails the deuteranopia check.

## Security, CSP, and isolation rules

1. **Zero external URLs:** No file in `static/section/` may contain `https://` or load external scripts, stylesheets, or fonts.
2. **No `innerHTML`:** DOM construction in `static/section/` uses `document.createElement` and `textContent` exclusively.
3. **Scoped events:** Keyboard listeners attach to `container` (`container.tabIndex = 0`), never `window`.
4. **No module-scope DOM access:** Importing `apecad-section.js`, `canvas2d.js`, `input-parse.js`, `transport.js`, or `mock-transport.js` in Node (`node --test`) succeeds without a global `window` or `document`.
