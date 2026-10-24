# Spec — scratchpad client

**Status:** Implemented (2026-08-14)  
**ADRs:** 0002, 0003, 0005, 0006, 0013, 0014, 0015, 0016, 0017, 0018, 0019, 0023, 0024, 0025, 0030, 0031, 0034, 0035, 0036, 0037, 0038

## Goal

A localhost web canvas that **emits ops at the Python document**. Humans
sketch on the XY plane (z = 0) so a spatial draft can be explained
without prose. The browser does not own geometry, undo, or labels.

## Shape

```
python -m apeCAD
        → stdlib HTTP on 127.0.0.1:8765 (preferred; next free port if busy)
        → Three.js canvas (vendored in static/vendor/three/)
        → POST /api/op  (same JSON as Document.to_json ops)
        → GET  /api/identity  ({name, pid, host, port, root})
```

No Node build, no Qt, no TypeScript. Vanilla JS: a bootstrap `app.js` plus native ES
modules in `static/js/`, with a pure reducer + two-signature microtask reconciler in
`js/store.js` synchronized with the shared `S` facade in `js/state.js`
([ADR 0023](../adrs/0023-module-boundaries.md), [ADR 0035](../adrs/0035-scratchpad-store-and-reconciler.md)).
Edges, curves, hoops, and crossties render as screen-space `LineSegments2` (`1.5 px` wire,
`2.25 px` section outline, `3.0 px` rebar/selected) with a depth-exempt `SelectionHalo` and
ear-clipping polygon triangulation ([ADR 0036](../adrs/0036-screen-space-lines-and-triangulation.md)).
Camera navigation uses pure turntable math in `js/nav-math.js` + `js/navigation.js` and a zero-WebGL 26-zone SVG
ViewCube with compass ring and 90° roll buttons in `js/viewcube.js`
([ADR 0037](../adrs/0037-cad-turntable-and-svg-viewcube.md)). WCAG contrast and Viénot
protanopia/deuteranopia CVD separation are enforced by automated gates
([ADR 0038](../adrs/0038-visual-and-contrast-gates.md)).

Chrome follows the APE design system ([ADR 0031](../adrs/0031-ape-design-system.md),
values in [`ape-design.md`](ape-design.md) §1). Every colour is a role in `static/css/app.css`:
chrome roles per theme (light paper, dark carbon) and canvas roles on `#stage` per canvas
preset (paper, mist, carbon). `js/theme.js` sets `data-theme` / `data-canvas` and reads the
canvas roles into `INK` for three.js; no other module writes a colour. The section table in
`js/section.js` reads `--fill-concrete`, `--ink-concrete`, `--ink-section-guide` and
`--ink-rebar`: APE drawing ink on light canvases (ADR 0031 §3, ADR 0033), lifted on carbon. The UI face is Archivo Narrow, served from
`static/fonts/` with its OFL licence. The server serves `/css/<name>.css` and
`/fonts/<name>.woff2` beside `/js/<name>.js`.

Every string the client writes at run time lives in `js/strings.js` (`t(id, params)`), in
the ADR 0031 §2 register: imperative hints, results with counts and units, and refusals as
`Refused: <reason>.` in the attention colour (`refuse()` in `js/cmdline.js`, which wraps a
`DocumentError` message or a client check). Static labels and tooltips stay in
`index.html` under the same rules; `tests/test_ui_strings.py` and
`tests/js/strings.test.mjs` lint both.

## Tools

Line (chains until Esc or Enter, posted as one `AddLineChain`), polyline (Enter to finish, click start to close), rectangle (face), circle, arc, ellipse, polygon, Bézier, box
(one `Extrude` with a ring). Each draw gesture posts one op whose vertices are snapped point ids or coordinates, so one undo removes the whole shape ([ADR 0030](../adrs/0030-one-gesture-one-op.md)). Select (click, window, crossing; filter Point / Line / Face / Solid / Element / Section; hover preselects the B-rep hit). Section-mode entities draw flat on their own z (`js/section.js`, one `SECTION_STYLE` table): the concrete face filled, bars as discs at their diameter, hoops as a ring offset by bar radius plus half the tie, crossties, the dash-dot leg axis and the dashed cover ring; the Section filter (6) picks each as itself, and the outliner nests a bar's point under the bar. Nested Vertex rows (corners, a bar's point) show in the outliner only under the Point filter, as bar dots do on the canvas; loose points always show. Move, rotate,
mirror, array, polar, trim (T), extend (E), break, insert-node,
face-from-lines, join (J), chamfer, fillet, sew, simplify, delete (Del).
Section & rebar authoring (`js/section-tools.js`, `js/section-ghosts.js`, `js/section-props.js`): Section outline, Wall chain (`t <mm>` sets thickness), Wall leg, Cover guide, Bar, Bar row, Bars on edge, Hoop, and Crosstie in the Section menu and left rail; `#section-bar` context bar sets bar designation, hoop size, spacing, count, cover, wall thickness, and hook angles; `#props` edits selected section entities in place (`SetBarSize`, `SetMaterial`, `SetCover`, `SetTransverse`, `SetLegReinforcement`); snapping (`js/snap.js`) snaps to bar centres, cover-guide corners/edges, and concrete face edges; `File` exports `apeCAD.section-draft` JSON, SVG, and DXF; `section_lint()` warnings appear in `#status` (`WARN {n}`) and the command history.
Undo / redo / clear. Save JSON.
SNAP / GRIDSNAP / ORTHO / GRID. Live millimetre readout (X Y Z, Δ, length, angle).
Layout R4 ([ADR 0014](../adrs/0014-menubar-side-rail-prefs.md)):
thin File / Edit / View / Section / Grid / Help menubar; left dock is a nested B-rep
outliner with properties below it, then a vertical icon rail;
viewport; bottom command line. Docks collapse and drag-resize.
File New/Open/Save talks to the JSON document. Visualization (theme: system, light or
dark; canvas: theme, paper, mist or carbon; clay, curve colour, lights, AO) lives in
Preferences as client state, not in the
ops log. Grid spacing, units, minor style, and hidden-line scale live in Grid → Preferences (also client state). Count/`n` is not a chrome field. Right-click the outliner to
select, rename, duplicate, hide, fit, or delete.
View cube (upper right): Z-up named faces; click face / edge / corner.
ISO is always Front–Right–Top (+X −Y +Z), not the nearest octant. Fit, ISO,
Open, and New frame the camera from the model bounds (or the grid, if empty)
so millimetre parts and hundred-metre sites both fill the view. Clip planes
and orbit limits follow that radius. Camera is not in the ops log.

## Out of scope

Constraints, workplanes other than z = 0, Studio integration,
`to_gmsh`, a Node toolchain, image export.
