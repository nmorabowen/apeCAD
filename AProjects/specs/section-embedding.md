# Spec — Section embedding kit (stage C9)

**Status:** Implemented (2026-10-23); results overlay, client API 2 (2026-11-01, stage C2-S2); draws v2 (2026-11-02, C5-S3, client API still 2); edits v2, client API 3 (2026-11-03, C5-S4); `sync()`, `chrome` and `setGlyphs`, client API 4 (2026-11-13, C8a)  
**ADRs:** 0023, 0024, 0025, 0026, 0038, 0041

## Goal

Provide an embeddable, zero-CDN 2-D HTML5 Canvas section and rebar client (`APECADSection`)
plus a stateless Python transport (`apeCAD.scratchpad.transport.handle`) so sibling web apps
(`ape-web-tools` HA-04, `apeWorkbench`) can host apeCAD section authoring inside their own
FastAPI / ASGI process without spawning a separate `ScratchpadServer`.

## Python embedding surface

| Symbol | Module | Contract |
|---|---|---|
| `CLIENT_API_VERSION = 4` | `apeCAD.scratchpad.section_assets` | Matches `API_VERSION = 4` exported by `apecad-section.js`. 4 adds `sync()`, the `create` option `chrome` and `setGlyphs` (C8a, below) and removes nothing of 3; 3 added `create(container, {version: 2})` editing (C5-S4, ADR 0026 Errata 1) and removed nothing of 2; 2 added the results overlay (ADR 0041 decision 2) and removed nothing of 1. Every move is additive, so a host asserts `CLIENT_API_VERSION >= 1`. |
| `SECTION_DIR` | `apeCAD.scratchpad.section_assets` | `Path` to `src/apeCAD/scratchpad/static/section/`. |
| `client_files()` | `apeCAD.scratchpad.section_assets` | Returns `dict[str, Path]` mapping relative asset names (`apecad-section.js`, `transport.js`, `mock-transport.js`, `input-parse.js`, `canvas2d.js`, `display2d.js`, `tools-v2.js`, `overlay.js`, `section.css`, `index.html`) to absolute `Path`s. |
| `TRANSPORT_VERSION = 1`, `MAX_OPS`, `handle(request)` | `apeCAD.scratchpad.transport` | Stateless single-endpoint transport (`scene`, `apply`, `undo`, `redo`, `draft`, `load`, `seed`). Importing `section_assets` or `transport` never loads `scratchpad.server`. |

## Client surface (`apecad-section.js`)

```js
import { API_VERSION, create, httpTransport, mockTransport } from "/section/apecad-section.js";

const editor = create(container, {
  transport: httpTransport("/api/section/transport"), // or mockTransport(initialDraft)
  readOnly: false,
  units: "mm",
  version: 1, // or 2: edit v2 sections (API 3); anything else throws
  chrome: { toolbar: true, sidebar: true }, // API 4: false hides that part; other keys throw
  onChange(draft) {
    // Fired on apply / undo / redo; NEVER fired on loadDraft or loadSeed.
  },
});
```

### Instance methods

- `await editor.loadDraft(payload)` / `await editor.load(payload)`: Load a `Document` dict, `apeCAD.section-draft` v1 dict, or `apeCAD.section-seed` v1 dict without firing `onChange`.
- `await editor.loadSeed(seedPayload)`: Load an `apeCAD.section-seed` v1 dict via `action: "seed"` without firing `onChange`.
- `editor.getDraft()`: Return the latest `apeCAD.section-draft` v1 dict, or `null` when v1 cannot say the document (a v2 face, a circular tie, a template, or a bar naming its steel: `transport.js::v1Unsayable`, the twin of `require_v1_expressible`). The client never writes a v1 draft that drops a v2 entity (C5 record invariant 8); while the draft is `null`, `onChange` is not fired. In v2 mode (`create(..., {version: 2})`, below) it is the transport's v2 draft.
- `editor.getScene()`: Return the normalized 2-D section scene payload.
- `await editor.applyOp(opOrOps)`: Apply one op or a list of ops and fire `onChange(draft)`.
- `await editor.undo()` / `await editor.redo()`: Undo or redo and fire `onChange(draft)`.
- `editor.setTool(toolId)`: Select active tool (`select`, `rect`, `polygon`, `opening`, `wall-chain`, `wall-leg`, `cover`, `bar`, `bar-row`, `bars-edge`, `hoop`, `crosstie`, `delete`; in v2 mode `select`, `rect`, `polygon`, `circle`, `hole`, `wall-chain`, `wall-leg`, `cover`, `bar`, `bar-row`, `hoop`, `crosstie`, `delete`).
- `editor.setParam(key, value)`: Set active tool parameter (`designation`, `hoop_designation`, `spacing_mm`, `count`, `thickness_mm`, `cover_mm`, `hooks`, `crosstie_hooks`, `gridStepMm`; `material`; in v2 mode `role`, `concrete`, `steel` or `void`).
- `editor.fitView()` / `editor.resize()`: Fit the viewport to section bounds or resize to container.
- `editor.dispose()`: Detach event listeners and remove the root element from `container`.
- `editor.setOverlay(overlay | null)`: Show an `apeCAD.section-overlay` v1 overlay (see below), or clear it with `null`.
- `editor.getOverlayState()`: The overlay as the client holds it (see below).
- `await editor.sync()`: Re-read the document after another writer changed it (API 4, below).
- `editor.setGlyphs(glyphs | null)`: Draw the glyphs a host supplies (API 4, below).

The module also exports `parseOverlay` (the client's reader) and `MAX_OVERLAY_PRIMITIVES`.

## Drawing v2 (C5-S3; ADR 0039, 0040)

The scene carries three v2 lists beside the v1 ones (`scratchpad/payload.py`): `section_faces`
(every `SectionFace`), `circular_ties` and `templates`. Each item is the v2 draft's item from
`section/draft_v2.py`'s projectors with `entity_id` in place of `id`, so a `section_faces` or
`circular_ties` item equals the draft's, less `id` and `template_id`; a template adds
`child_ids` and `label`. `concrete_faces` keeps the v1 faces only, and `bars[]` items carry
`material` (null for the default steel). `warnings` is the v1 lint while v1 can say the document,
else the v2 lint. The 3-D client ignores the new keys.

- **Display list.** `display2d.js::displayList(scene)` lists every section kind
  (`SECTION_KINDS`) on its layer, back to front in `render`'s order (`SECTION_LAYERS`):
  concrete, steel, void, cover, leg, hoop, crosstie, circular-tie, bar; by id within a layer.
  A face takes the layer of its role, so overlaps paint concrete, steel, void whatever the
  ids. A template draws nothing of its own: its children are drawn from their own lists, never
  re-expanded. An item the reader does not know (a role, a boundary kind, a bad circle) draws
  nothing and is named in the warnings box as `[not-drawn] <message>`.
- **Painting.** `canvas2d.js` paints the list with the C5-S1 styles from `PALETTE`: steel
  on Grey128 (`steelFill`), a void in the paper colour (`voidFill`, so it takes away what it
  cuts), a circular tie's centreline at `centerline_radius_mm` in the hoop's ink. A face's
  boundary and holes are one path filled `evenodd`, so a hole stays open whatever its ring's
  winding; circles are drawn exactly with `arc`.
- **Hit-testing.** The nearest bar, else the first line (circular tie, crosstie, hoop, cover,
  leg, as in v1), else the face on top by role: void, steel, concrete. A point inside a hole
  misses that face (and may hit the face beneath it, such as a filled tube's core). A v2 face
  hit is `{kind: "SectionFace", id, item, role}`. v1 mode edits no v2 entity; v2 mode does
  (below).
- **Huge input.** A scene of 10^5 bars is listed, painted and hit-tested in bounded time. A
  request too deep to write as JSON is refused by `httpTransport` as `{ok: false, status:
  422, error: {code: "INVALID_ARGUMENT"}}`, never thrown; one too deep for the server to parse
  is the server's named 422, and the next request is served.

## Editing v2 (API 3, C5-S4; ADR 0039, 0040)

`create(container, {version})` takes `version` 1 (the default, also when absent or null) or 2.
Any other value, `3`, `"2"`, `1.5` or `true` among them, throws at `create`, naming it.
`{version: 2}` needs a `transport`: `mockTransport` writes v1 drafts only and refuses
`{action: "draft", version: 2}` by name. v1 mode is the client of API 2, unchanged: its tools
and its requests are those of apeCAD b4b6e63 (`tests/test_section_client_v2.py` pins the log).
The code is `tools-v2.js`.

- **Tools.** Rectangle, Polygon and Circle (centre, then a point on the rim) post
  `AddSectionFace` with `role` (`setParam("role", ...)`, default `concrete`) and `material`
  (null for a void). Hole replaces Opening and posts `AddFaceHole` on the face on top at its
  first point (void over steel over concrete, holes excluded). Edge bars are hidden:
  `AddBarsAlongEdge` is v1-only. The other v1 tools stay; Cover takes the face it is clicked
  in. Points snap to v2 faces as to v1 ones: ring vertices, midpoints and edges, and a
  circle's centre, quadrants and rim. A polygon or hole takes at most `MAX_GESTURE_POINTS`
  (10 000) points; the next is refused by name in the prompt.
- **Templates.** A click on a template's child selects the template: the panel shows its
  name, version and params and says `locked`, and its children are highlighted. Delete (the
  key or the tool) posts `Delete{entity_ids: [template_id]}`, which removes the subtree; the
  toolbar's Explode posts `ExplodeSectionTemplate`, which keeps the child ids. The client never
  expands a template, posts no `EditSectionTemplate` of its own (a host posts template ops
  through `applyOp`), and never checks the lock: an edit of a child is refused by the server
  (`TEMPLATE_LOCKED`).
- **Refusals.** Every refusal shows `Refused: <message>` in the prompt.
- **The v2 draft.** Each change (apply, undo, redo) and each load, seed or opening scene is
  followed by a transport request `{action: "draft", version: 2}`. `getDraft()` and `onChange`
  carry that draft, which equals `section_draft(document, version=2)`. A refused `draft`
  leaves `getDraft()` null (never a stale draft) and fires no `onChange`; a thrown `draft`
  counts as a refused one (no `onChange`; `Refused: <message>`), and so does a reply that is
  not an `apeCAD.section-draft` version 2. The change itself still shows. A draft reply that
  arrives late is dropped iff a newer change has landed since its own change landed (an ok
  apply, undo, redo, load or seed; a refused or thrown attempt is no landing), and kept
  otherwise. `onChange` fires at most once per landed change. v1 mode sends no
  `draft`.
- **Huge input.** A v2 scene of 10^4 faces and 10^5 bars edits, selects and deletes in
  bounded time (`tests/js/section-v2-edit.test.mjs`).

## A host that owns the document (API 4, C8a)

For a host that holds the document behind its own transport and has other writers (apeSection's
Geometry tab: its `docs/contracts/host-api-v1.md` §9, `verbTransport`; owner ruling
apeSection#113 c2383). The transport and overlay versions are unchanged.

- **`sync()`.** Sends `{action: "scene"}`, then in v2 mode `{action: "draft", version: 2}`,
  and shows what they return. It takes the scene reply's `revision` when it is an integer
  and otherwise leaves the revision as it was: it never counts an edit. It never refits or
  moves the view, never fires `onChange`, and keeps the selection, the tool, the overlay and
  the glyphs. A local edit wins: if an apply, undo, redo, load or seed lands while `sync()`
  waits (in either mode), its reply is dropped and the promise resolves to it with `stale:
  true`; an edit still in flight when the reply arrives repaints when it lands, and a refused
  one does not stop the sync. A refused `scene` shows
  the refusal in the prompt (`Refused: <message>` in v2 mode) and changes nothing; a refused
  `draft` leaves `getDraft()` null, as after any change. It works in read-only editors too.
- **`chrome`.** `create(container, {chrome: {toolbar, sidebar}})`: `false` leaves that part
  out of the DOM (the toolbar with its tool, Undo, Redo, Explode and Fit buttons; the sidebar
  with the properties, warnings and overlay panel), so the host draws its own. Both default to
  `true`; `null` or absent is the default. A key other than `toolbar` or `sidebar`, a value
  that is not a boolean, or a `chrome` that is not an object throws at `create`, naming it.
  The canvas, the prompt and the command line always show, and keys still work.
- **`setGlyphs({centroid_mm})`.** Draws the centroid symbol, a circle quartered by a cross at
  a fixed size on screen, at the world point `[x, y]` (mm) the host supplies. The client
  never computes a centroid: apeSection supplies the net solid-area centroid that apeConcrete
  reports (its PR #121 c2410). The glyph sits with the overlay, above the section and below
  the selection; it moves with pan and zoom, survives `sync()`, and is display only (no hit
  testing, no snapping, not an edit). `setGlyphs(null)`, `{}` or `{centroid_mm: null}`
  clears it. The result is `{ok: true, status: 200, centroid_mm}`, or `{ok: false, status:
  422, error: {code: "INVALID_ARGUMENT", path, message}}` for a value that is not an object,
  an unknown key (the axes glyph is C8b's), or a `centroid_mm` that is not two finite
  numbers. A refusal clears the glyph, as a refused overlay does: never a stale point.

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
  is the live document revision; `scale` is the scale's kind or `null`. Planned for slice 3
  of apeSection#46 (`section-overlay-v2.md`, "Echo"): an additive key
  `overlay_section_sha256`, the overlay's `section_sha256` (`null` for a v1 overlay or no
  overlay), with `overlay_revision` `null` for a v2 overlay's null revision. Neither is a
  client API change: `API_VERSION` stays 3 (ADR 0041 Errata E1).
- **Revision.** When a transport response carries an integer `revision` (the mock transport
  does), the client takes it. The stateless Python transport sends none, so the client counts
  its own edits: each successful `apply`, `undo`, `redo`, `load` and `seed` adds 1. An op
  list refused partway first shows the ops applied before the refusal, and counts them. A
  host stamps an overlay with `getOverlayState().revision` read when it took the draft.
  The counter restarts at 0 with each editor, so it identifies a revision only within one
  editor session. The identity that survives sessions is the overlay's `section_sha256`
  (section-overlay v2, ADR 0041 Errata E1): the hash of the **stored** draft's `section`
  block, computed by the host in Python, never by the client and never over a re-expansion.
  A saved overlay carries `revision: null`. On reload the host hashes the stored draft it
  loads and stamps the overlay with this revision, read right after the load, only when the
  hashes match.
- **Stale.** When `revision !== overlay_revision` (behind or ahead), the client paints the overlay at
  `STALE_ALPHA` (0.35) of its opacity, dims its legends and shows a `stale` badge. It never
  hides it and never recomputes it. An undo is an edit, so it does not make an overlay current.
  Planned for slice 2 (`section-overlay-v2.md`): a v2 overlay whose `revision` is `null` is
  stale at every live revision, 0 included, and the client never compares hashes. The host
  sends an overlay only to the editor whose stored draft hashes to its `section_sha256`, so
  two editors at equal revisions never show each other's results as current.
- **Draw order.** Section, then the overlay, then the selection, stroked again on top. The
  ghost preview and the snap marker stay above all three. The overlay is display only: hit
  testing and snapping ignore it.
- **Panel.** The sidebar lists each layer's `label` (`(hidden)` after a hidden one) and one
  legend per visible layer with a scale: the title and unit, a gradient bar with the domain
  values (numeric scales) or a swatch per category.
- **Text and colour.** Every overlay string reaches the page through `textContent` and the
  canvas through `fillText`, never as markup. Colours are validated by the reader. A token
  resolves to its light value, `canvas2d.js::OVERLAY_TOKENS` (equal to
  `apeCAD.render.overlay.COLOR_TOKENS`), whatever the host theme: the client canvas is
  light-only (`PALETTE.bg`), so a dark host's `--text` would not show on it.
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
4. **No module-scope DOM access:** Importing `apecad-section.js`, `canvas2d.js`, `display2d.js`, `input-parse.js`, `tools-v2.js`, `transport.js`, or `mock-transport.js` in Node (`node --test`) succeeds without a global `window` or `document`.
