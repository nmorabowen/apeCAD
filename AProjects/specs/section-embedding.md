# Spec — Section embedding kit (stage C9)

**Status:** Implemented (2026-10-23)  
**ADRs:** 0023, 0024, 0025, 0026

## Goal

Provide an embeddable, zero-CDN 2-D HTML5 Canvas section and rebar client (`APECADSection`)
plus a stateless Python transport (`apeCAD.scratchpad.transport.handle`) so sibling web apps
(`ape-web-tools` HA-04, `apeWorkbench`) can host apeCAD section authoring inside their own
FastAPI / ASGI process without spawning a separate `ScratchpadServer`.

## Python embedding surface

| Symbol | Module | Contract |
|---|---|---|
| `CLIENT_API_VERSION = 1` | `apeCAD.scratchpad.section_assets` | Matches `API_VERSION = 1` exported by `apecad-section.js`. |
| `SECTION_DIR` | `apeCAD.scratchpad.section_assets` | `Path` to `src/apeCAD/scratchpad/static/section/`. |
| `client_files()` | `apeCAD.scratchpad.section_assets` | Returns `dict[str, Path]` mapping relative asset names (`apecad-section.js`, `transport.js`, `mock-transport.js`, `input-parse.js`, `canvas2d.js`, `section.css`, `index.html`) to absolute `Path`s. |
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

## Security, CSP, and isolation rules

1. **Zero external URLs:** No file in `static/section/` may contain `https://` or load external scripts, stylesheets, or fonts.
2. **No `innerHTML`:** DOM construction in `static/section/` uses `document.createElement` and `textContent` exclusively.
3. **Scoped events:** Keyboard listeners attach to `container` (`container.tabIndex = 0`), never `window`.
4. **No module-scope DOM access:** Importing `apecad-section.js`, `canvas2d.js`, `input-parse.js`, `transport.js`, or `mock-transport.js` in Node (`node --test`) succeeds without a global `window` or `document`.
