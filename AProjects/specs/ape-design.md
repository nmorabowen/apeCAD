# Spec — APE design system for apeCAD

**Status:** Accepted (2026-10-14). **ADRs:** [0031](../adrs/0031-ape-design-system.md), [0033](../adrs/0033-ape-drawing-style-errata.md) (drawing-style errata).
**Mockup:** [`design/ape-design-mockup.html`](../design/ape-design-mockup.html), published at
<https://claude.ai/artifact/8o96Ef5efK79HYXGuWBDbj> (private to the owner until shared).

Three tables an implementer can work from without re-arguing the ADR: tokens (§1),
UI strings (§2), drawing styles (§3). §4 is the slice plan.

Sources are cited by path once here and by name below:

- APE web: `ape WebPage/src/styles/global.css`
- apeGraphStyle: `ape-workflow/ape-libraries/apeGraphStyle/src/apeGraphStyle/__init__.py`
- apeCAD mark: `logo/README.md`, `logo/wordmark.svg`, `docs/styles.css`
- Drawing standards: `ape-workflow/drawing-standards/` ADR-004, ADR-005, ADR-007, ADR-009,
  ADR-010, `token-card.md`
- Rebar ink and tag grammar: `apeRevit/library/graphics-tokens.json`; skill
  `ape-drawing-standards`, `references/planillas-and-marks.md`
- Voice: skill `ape-tono`, `references/tone-standard.md`

## 1. UI tokens

### 1.1 Colour roles

Contrast is WCAG 2 against the surface the role sits on most (`surface-1` unless noted).
Text roles meet 4.5 : 1; stroke-only roles meet 3 : 1.

| Role | Light | Dark | Source | Used for | Contrast L / D |
|---|---|---|---|---|---|
| `--surface-0` | `#f7f6f3` | `#0c1016` | APE web `--paper` / `--carbon-2` | App background, command line | — |
| `--surface-1` | `#efede8` | `#14181d` | `--paper-2` / `--carbon` | Menubar, panels, menus, dialogs | — |
| `--surface-2` | `#ffffff` | `#1c2127` | white / `--ink` | Inputs, hover rows, dim labels | — |
| `--line` | `#d8d5cd` | `#232a33` | `--line` / band-dark rule | Borders, separators, tree guides | — |
| `--text` | `#1c2127` | `#e8ecf1` | `--ink` / band-dark text | Body text | 13.9 / 15.0 |
| `--muted` | `#4a525c` | `#97a1ad` | `--ink-soft` / `.band-dark .muted` | Labels, kbd, kickers, off chips | 6.8 / 6.8 |
| `--accent` | `#2f74ad` | `#3d8fce` | `--steel` / `--steel-bright` | Selection, active tool, focus, on chips (stroke, fill, border) | 4.3 / 5.1 |
| `--accent-text` | `#28679c` | `#3d8fce` | steel, darkened 10 % | Accent used as small text on `surface-1` | 5.1 / 5.1 |
| `--signal` | `#c64a1a` | `#e2703a` | apeCAD vest (lifted on dark) | Snap marker, crossing window, trim discard, refusals | 4.1 / 5.6 |
| `--signal-text` | `#b0441a` | `#e2703a` | vest, darkened | Refusal text on `surface-0/1` | 4.9 / 5.6 |
| `--canvas` | `#ffffff` | `#1c2127` | white, like the SVG render (owner, 2026-10-14) / ink | 3-D view background (the theme's default preset; the chrome keeps paper) | — |
| `--grid-major` | `#cfcfcf` | `#2c333c` | neutral grey for white / current dark line | Major grid | 1.6 / — |
| `--grid-minor` | `#e2e2e2` | `#232a33` | neutral grey for white | Minor grid dots or lines | 1.3 / — |
| `--ink-edge` | `#14181d` | `#c9d1da` | carbon / light slate | Sketch curves and solid edges on the canvas | — |
| `--ink-rebar` | `#000077` | `#8c9cf0` | ADR-004 annotation blue / lifted | Section bars, hoops, crossties, tags on the canvas | 15.3 / 6.9 |
| `--fill-concrete` | `#b4b4b4` | `#3a4048` | drawn at 60 % so the grid shows through: renders ADR-010 Grey210 on white / dark equivalent | Concrete face fill on the canvas | — |
| `--ghost` | `#2f74ad` | `#6cb3ff` | steel / current ghost | Rubber-band previews, keep half of trim | — / 8.1 |
| `--pick` | `= --accent` | `= --accent` | | Selected entity colour in 3-D | |
| `--hover` | `#3d8fce` | `#6aa8e8` | steel-bright / current hover | Preselection | |
| `--backdrop` | `#14181d66` | `#000000aa` | | Dialog backdrop | |

Retired raw values and their role:

| Now (file) | Becomes |
|---|---|
| `--bg/--panel #1d2229`, `#252b33`, `--chrome #10141a`, `#0d1014` (`index.html`) | `--surface-0/1/2` |
| `--accent/--pick #4a90d9` (`index.html`), `CURVE_PICK 0x4a90d9` (`draw.js`) | `--accent` / `--pick` |
| `CURVE_HOVER 0x6aa8e8` (`draw.js`) | `--hover` |
| `SNAP_COLOR 0xd55e00` (`draw.js`), crossing `#d55e00` (`index.html`) | `--signal` |
| `0x6cb3ff` ×7 (`ghosts.js`), cube edges (`viewcube.js`) | `--ghost` |
| trim keep `0x7dce7d`, discard `0xff6b6b` (`ghosts.js`) | keep `--ghost` solid, discard `--signal` dashed |
| `EDGE_COLOR 0x111111` (`draw.js`), pref `curve #111111` (`prefs.js`) | `--ink-edge` (pref stays, default from theme) |
| cube face `#1d2229`, `#2c333c`, `#e8edf2` (`viewcube.js`) | `--surface-1`, `--line`, `--text` |
| `scene.background 0xe4e9ee` (`viewport.js`), presets `g2/g5/g6` (`prefs.js`) | `--canvas` (theme default: white in light, ink in dark); presets `paper` (`#f7f6f3`), `mist` (`#e4e9ee`, kept), `carbon` |

### 1.2 Type

| Token | Value | Use |
|---|---|---|
| `--font-ui` | `"Archivo Narrow", "Arial Narrow", "Segoe UI", system-ui, sans-serif` | All chrome |
| `--font-mono` | `"Cascadia Mono", Consolas, ui-monospace, monospace` | Command line, coordinates, `kbd` |
| `--fs-kicker` | 11 px, weight 600, uppercase, `letter-spacing: 0.12em` | Panel heads, dialog section heads |
| `--fs-small` | 12 px | Tree kind column, notes, mono |
| `--fs-body` | 13 px, line-height 1.4 | Default |
| `--fs-title` | 15 px, weight 600 | Dialog titles |
| numerals | `font-variant-numeric: tabular-nums` | Status, coords, dims, properties |

Fonts shipped: `static/fonts/ArchivoNarrow-Regular.woff2`, `ArchivoNarrow-SemiBold.woff2`,
`OFL.txt`, converted from the TTFs apeGraphStyle bundles (`src/apeGraphStyle/fonts/`).

### 1.3 Spacing, size, shape

| Token | Value |
|---|---|
| `--space-1 … --space-7` | 2, 4, 6, 8, 12, 16, 24 px |
| `--h-menubar` | 28 px |
| `--h-row` | 22 px (tree, menu items) |
| `--h-input` | 24 px |
| `--size-rail-btn` | 32 px (icon 18 px) |
| `--w-rail` | 40 px |
| `--w-outliner` | 260 px default |
| `--radius` | 2 px (buttons, inputs); 0 (menus, panels, dialogs, chips) |
| `--focus` | `outline: 2px solid var(--accent); outline-offset: 1px` |
| `--border` | `1px solid var(--line)` |

### 1.4 Icons

| Property | Value |
|---|---|
| Grid | 24-unit viewBox, drawn at 18 px (rail), 14 px (dock), 10 px (tree) |
| Stroke | 1.5, `currentColor`, `stroke-linecap: square`, `stroke-linejoin: miter` |
| Vertex | Filled 3 × 3 square (`<rect>`), not a circle |
| Dash | `stroke-dasharray: 2 2` |
| Tint | `fill: currentColor; fill-opacity: 0.2` |
| Exception | Section bars are filled circles; hoops are rounded rectangles through bar dots |

### 1.5 Chrome rules

- Menubar: `surface-1`, 1 px `line` underneath, wordmark (`logo/wordmark-transparent.svg`,
  inline, `stroke=currentColor`, 14 px tall) at the left, mode chips at the right.
- Mode chips: `SNAP`, `GRID SNAP 100 / 1000 mm`, `ORTHO`, `GRID`, `FILTER Element`. On: `accent-text`
  with a 1 px accent underline. Off: `muted`. Always shown, so a mode that is off is
  visible.
- Panel heads: kicker style in `muted`; the active panel's head is `text`.
- Selected tree row: `surface-2` with a 2 px `accent` bar on the left, text in `text`.
- Dims overlay: `surface-2` at 92 % opacity, 1 px `accent` border, `accent-text`; committed
  dims `line` border, `muted` text.
- Command line: `surface-0`, mono; prompt in `accent-text`; history in `muted`; the latest
  line in `text`; refusals in `signal-text` prefixed `Refused:`; lint lines prefixed
  `Warning:` in `text`.
- Marquee: window = 1 px solid `accent` on `accent` at 10 %; crossing = 1 px dashed
  `signal` on `signal` at 10 %.

## 2. UI strings

### 2.1 Rules (from ADR 0031 §2)

| # | Rule | Example |
|---|---|---|
| S1 | Hint = `Tool: verb the object. Next step.` | "Rotate: click the pivot. Type degrees or click an angle." |
| S2 | No shortcut inside a hint; shortcuts live in tooltips and menus | "Trim (T): …" → "Trim: …" |
| S3 | No dash as a pause, no ellipsis in a message, no `!`, no `?` | "View cube — click…" → "View cube. Click…" |
| S4 | Result = past participle, count, noun, unit | "Moved 3 entities." |
| S5 | Refusal = `Refused: <reason>.`, reason capitalised unless it opens with an identifier (`keep_id`, `Ø21`) | "Refused: Lines do not cross." |
| S6 | No verdict words (*OK*, *pass*, *fail*, *fine*) | "implied intersection is OK" → "implied intersections count" |
| S7 | Sentence case; ALL CAPS only for CAD mode names (SNAP, GRID, ORTHO, ISO) | "Save As…" → "Save as…" |
| S8 | One noun per concept: entity, element (filter only), Rectangle, Bézier, centre, colour | "Rect placed." → "Rectangle placed." |
| S9 | Never *you*, *we*, *please* | |
| S10 | Op names (`AddLine`, `TrimLine`, …) are identifiers and never shown | |

Strings that already pass all rules are listed as "keep" so the table is a complete
inventory. Op kind literals (`"AddFace"`, `"Extrude"`, …), entity kind literals
(`"Polyline"`, `"Circle"`, …) and DOM ids are not UI strings and are omitted.

### 2.2 `index.html`

| Where | Current | Proposed |
|---|---|---|
| `<title>` | apeCAD scratchpad | keep |
| `#brand` | apeCAD (text + favicon) | wordmark SVG, `aria-label="apeCAD"` |
| Menus | File · Edit · View · Grid · Help | keep |
| File | New · Open… · Save · Save As… · Import JSON… · Export JSON… · Preferences… · Quit | New · Open… · Save · **Save as…** · Import JSON… · Export JSON… · Preferences… · Quit |
| Edit | Undo · Redo · Select all · Delete | keep |
| View | Perspective · Parallel · Top · Front · Right · Left · Back · Bottom · ISO · Fit · View cube | keep |
| View | Snap to nodes · Snap to grid · ORTHO · Show grid | keep |
| View | Model · Tool rail · Command line | keep |
| Grid | Show grid · Show minor · Snap to grid · Preferences… | Show grid · Show minor grid · Snap to grid · Preferences… |
| Help | Shortcuts… | keep |
| `#status` | SNAP · GRIDSNAP 100/1000 · GRID | chips: `SNAP` `GRID SNAP 100 / 1000 mm` `ORTHO` `GRID` `FILTER Element` (on/off states, §1.5) |
| Dock head | Model | keep |
| Dock button title | Collapse outliner | Collapse the model panel |
| `#tree` empty | No entities. | keep |
| Split titles | Resize properties · Resize outliner · Resize command line | Resize the properties panel · Resize the model panel · Resize the command line |
| Expand strip | Show outliner · Show tools | Show the model panel · Show the tool rail |
| `#props` head | Properties | keep |
| `#prop-body` empty | Nothing selected. | keep |
| Rail separators | Sketch · Solid · Transform · Modify · View | keep |
| Rail: select | Select (Esc) | keep |
| Rail: line | Line (chains until Esc) | Line (Esc ends the chain) |
| Rail: polyline | Polyline (Enter to finish, click start to close) | Polyline (Enter finishes; click the start to close) |
| Rail: rect | Rectangle | keep |
| Rail: circle, arc, ellipse, polygon, bezier | Circle · Arc · Ellipse · Polygon · Bézier | keep |
| Rail: box | Box (rect then height) | Box (rectangle, then height) |
| Rail: extrude | Extrude selected profile | Extrude the selected profile |
| Rail: move | Move (M) | keep |
| Rail: rotate, mirror | Rotate selection · Mirror selection | Rotate the selection · Mirror the selection |
| Rail: array, polar | Linear array · Polar array | keep |
| Rail: trim | Trim a free end to a cutter (T) | keep |
| Rail: extend | Extend a short end to a boundary (E) | keep |
| Rail: break | Break two crossing lines | keep |
| Rail: node | Insert a node on a line or face | keep |
| Rail: face-lines | Face from selected lines | Face from the selected lines |
| Rail: join | Join connected lines into a polyline (J) | keep |
| Rail: chamfer | Chamfer a corner (type distance) | Chamfer a corner (type the distance) |
| Rail: fillet | Fillet a corner (type radius) | Fillet a corner (type the radius) |
| Rail: sew | Sew coincident points in the selection | keep |
| Rail: simplify | Drop collinear vertices | keep |
| Rail: delete | Delete selection (Del) | Delete the selection (Del) |
| Rail: proj | Parallel (O) | keep (camera.js toggles it) |
| Rail: snap, grid-snap, ortho, grid | Snap to nodes (F3) · Snap to grid (F7) · ORTHO (F8) · Show grid (F9) | keep |
| Rail toggle | Collapse tool rail | Collapse the tool rail |
| View cube title | View cube — click a face, edge, or corner | View cube. Click a face, edge or corner. |
| ISO button | ISO · title "Isometric from the Right–Front–Top corner" | ISO · "Isometric from the right, front, top corner" |
| Fit button | Fit · title "Fit the draft in the view" | keep |
| Filter toolbar | Points (1) · Lines (2) · Faces (3) · Solids (4) · Whole element (5) | keep |
| Prompt | Command: | keep |
| Input placeholder | length mm · angle ° · Enter | keep (`grid-ui.js` rebuilds it with the unit) |
| Label field | label · placeholder "optional" | Label · placeholder "optional" |
| Coords | X 0  Y 0  Z 0 | keep |
| Prefs dialog | Preferences · Close | keep |
| Prefs | Background · G2 charcoal · G5 cool mist · G6 mid-gray | Theme · System · Light · Dark; Canvas · Paper · Mist · Carbon |
| Prefs | Clay fill (0–255) | Clay fill (80 to 230) |
| Prefs | Curve colour · Key light · Ambient / AO · Show edges · Show curves · Show faces | Curve colour · Key light · Ambient occlusion · Show edges · Show curves · Show faces |
| Grid dialog | Grid · Close · Show grid · Show minor · Snap to grid · Auto spacing from model | Grid · Close · Show grid · Show minor grid · Snap to grid · Auto spacing from the model |
| Grid dialog | Units · Minor style · Dots · Lines · Minor · Major | Units · Minor style · Dots · Lines · Minor spacing · Major spacing |
| Grid note | Auto picks a 1–2–5 step from the model (~10 major cells across). Manual values and presets turn auto off. | Auto picks a 1, 2, 5 step from the model, about 10 major cells across. A manual value or a preset turns auto off. |
| Grid dialog | Line thickness · Dot size · Hidden scale | Line width · Dot size · Dash scale |
| Grid notes | Screen pixels. Independent of zoom. · Dash period = minor spacing × scale. 1 = one dash per minor cell. | Screen pixels, independent of zoom. · Dash period = minor spacing × scale; 1 is one dash per minor cell. |
| Grid presets | 50 / 500 … 500 / 5000 | keep |
| Help dialog | Shortcuts · Close | keep |
| Help line 1–2 | Ctrl+N new · Ctrl+O open · Ctrl+S save / Ctrl+Z undo · Ctrl+Y redo · Ctrl+A select all · Del delete | keep (render as a two-column `kbd` table) |
| Help line 3 | Esc cancel / select · 1 point · 2 line · 3 face · 4 solid · 5 element | Esc cancels, then selects · 1 points · 2 lines · 3 faces · 4 solids · 5 whole elements · 6 section entities |
| Help line 4 | M move · T trim · E extend · J join · O perspective/parallel | M move · T trim · E extend · J join · O perspective or parallel |
| Help line 5 | Line chains until Esc · Polyline: Enter finishes, C or click start closes | Line chains until Esc · Polyline: Enter finishes; C or a click on the start closes |
| Help line 6 | F3 node snap · F7 grid snap · F8 ORTHO · F9 show grid · MMB orbit · RMB pan | F3 node snap · F7 grid snap · F8 ORTHO · F9 grid · middle drag orbits · right drag pans |
| Help line 7 | View menu: Perspective, Parallel, Top / Front / Right… · O toggles 3D lens | View menu: perspective, parallel and the six named views · O switches the lens |
| Help line 8 | Grid → Preferences: units, dots/lines, spacing, dot size · mm cm m in · grid 50 500 | Grid, Preferences: units, dots or lines, spacing, dot size · type mm, cm, m, in or `grid 50 500` |
| Help line 9 | F2 rename · right-click the model tree for duplicate / hide / delete | F2 renames · right-click the model tree to duplicate, hide or delete |

### 2.3 Hints and results in `static/js/`

| File:line | Current | Proposed |
|---|---|---|
| `camera.js:158` | Parallel (O) · Perspective (O) | keep |
| `camera.js:174` | Perspective. · Parallel. | Perspective view. · Parallel view. |
| `cmdline.js:23,25` | Command: | keep |
| `cmdline.js:72` | GRIDSNAP {minor}/{major} | `GRID SNAP {minor} / {major} {unit}` chip; `GRID` stays its own chip (visibility) |
| `cmdline.js:120,126` | X {x}   Y {y}   Z {z}   {unit} | keep |
| `commands.js:176` | Line chain placed. | keep |
| `commands.js:217`, `tools.js:371` | Box: move for height, type a length, then click or Enter. | Box: move for the height, or type it. Click or Enter places the box. |
| `commands.js:224,237,256,257,259`, `docfile.js:98` | {error.message} | Refused: {error.message} |
| `commands.js:253` | Close the browser tab to quit. | keep |
| `create.js:48` | face needs a non-zero width and height | Refused: The rectangle needs a width and a height. |
| `create.js:56` | Line: click a different point, or Esc to end the chain. | Line: click a different point. Esc ends the chain. |
| `create.js:65` | Line: click the next point. Esc ends the chain. | keep |
| `create.js:87` | Polyline: click the next point. | keep |
| `create.js:90` | Polyline: click the next point, or Enter to finish. | Polyline: click the next point. Enter finishes. |
| `create.js:92` | Polyline: click the next point, Enter to finish, click start or type C to close. | Polyline: click the next point. Enter finishes; C or a click on the start closes. |
| `create.js:102` | Polyline: click a different point, Enter to finish, or Esc to cancel. | Polyline: click a different point. Enter finishes; Esc cancels. |
| `create.js:114` | Polyline: need three points to close. | Refused: A closed polyline needs three points. |
| `create.js:114` | Polyline: click at least two points, then Enter. | Polyline: click two points or more, then Enter. |
| `create.js:128` | Closed polyline placed. | keep |
| `create.js:128` | Polyline placed. LMB starts another. | Polyline placed. Click to start another. |
| `create.js:140` | Rect placed. | Rectangle placed. |
| `create.js:158,175` | Box placed. · Solid placed. | keep |
| `create.js:180` | circle radius must be positive | Refused: The radius must be positive. |
| `create.js:189` | Circle placed. Select it, then Extrude. | Circle placed. Select it and extrude for a solid. |
| `create.js:195` | ellipse needs two positive radii | Refused: An ellipse needs two positive radii. |
| `create.js:208,221,238` | Ellipse placed. · Polygon placed. · Arc placed. | keep |
| `create.js:250` | Bézier placed. | keep |
| `docfile.js:28` | Save as | File name |
| `docfile.js:33` | Saved {name}. Preferences are not in this file. | Saved {name}. Preferences stay in the browser. |
| `docfile.js:43` | not an apeCAD document JSON | Refused: Not an apeCAD document. |
| `docfile.js:56,69` | Opened {name}. · New document. | keep |
| `docfile.js:78` | Line: last vertex removed. | keep |
| `grid-ui.js:35` | Grid auto {minor} / {major}. | Grid auto, {minor} / {major}. |
| `grid-ui.js:36` | Grid spacing is manual. | Grid spacing manual. |
| `grid-ui.js:45` | Minor grid on. · Minor grid off. | keep |
| `grid-ui.js:53` | Hidden line scale {s}. | Dash scale {s}. |
| `grid-ui.js:61` | Minor grid: dots. · Minor grid: lines. | Minor grid as dots. · Minor grid as lines. |
| `grid-ui.js:79,97` | Dot size {n} px. · Line thickness {n} px. | Dot size {n} px. · Line width {n} px. |
| `grid-ui.js:155` | length {unit} · angle ° · Enter | keep |
| `grid-ui.js:182,190` | Grid {minor} / {major}. · Units {unit}. | keep |
| `input.js:151` | Select one entity to rename. | keep |
| `input.js:204` | Line chain placed. Click to start another, or Esc for Select. | Line chain placed. Click to start another; Esc returns to Select. |
| `input.js:215,223`, `tools.js:98` | Cancelled. · Selection cleared. | keep |
| `modify.js:128` | Extended. Click another end, or Esc. | Extended. Click another end; Esc ends. |
| `modify.js:129` | Trimmed. Click another part, or Esc. | Trimmed. Click another part; Esc ends. |
| `modify.js:142` | Broke at the crossing. Click two more lines, or Esc. | Broken at the crossing. Click two more lines; Esc ends. |
| `modify.js:155` | Node inserted. | keep |
| `modify.js:164` | Select at least three lines that form a closed loop, then Face. | Face: select three lines or more that close a loop. |
| `modify.js:174` | Face from lines. | Face placed from {n} lines. |
| `modify.js:183` | Select two or more connected lines (or polylines), then Join. Sew first if ends only coincide. | Join: select two connected lines or polylines. Sew first where ends only coincide. |
| `modify.js:193` | Joined into a polyline. | Joined {n} lines into a polyline. |
| `modify.js:198` | Select entities, then Sew to merge coincident points. | Sew: select the entities whose coincident points to merge. |
| `modify.js:206` | Sewed coincident points. | Merged coincident points in {n} entities. (the op returns no merge count) |
| `modify.js:215` | Select a face or polyline, then Simplify. | Simplify: select a face or polyline. |
| `modify.js:222` | Simplified collinear vertices. | Dropped collinear vertices from {n} entities. (the op returns no vertex count) |
| `modify.js:227` | Finish or Esc the current command before deleting. | Finish or cancel the current command before deleting. |
| `modify.js:231` | Select entities, then Delete. | Delete: select the entities first. |
| `modify.js:239` | Deleted 1 entity. · Deleted {n} entities. | keep |
| `modify.js:282` | Chamfer: type a distance (mm), then click a corner. | Chamfer: type the distance in {unit}, then click a corner. |
| `modify.js:283` | Fillet: type a radius (mm), then click a corner. | Fillet: type the radius in {unit}, then click a corner. |
| `modify.js:288` | Click a face or polyline corner. | Chamfer: click a corner of a face or polyline. (Fillet alike) |
| `modify.js:307` | Corner chamfered. · Corner filleted. | keep |
| `outliner.js:103–111` | Select · Rename · Duplicate · Show · Hide · Fit · Expand · Collapse · Delete | keep |
| `outliner.js:164` | Renamed to {name}. · Label cleared. | keep |
| `outliner.js:210` | Select something to duplicate. | Duplicate: select the entities first. |
| `outliner.js:221` | Duplicated. | Duplicated {n} entities. |
| `outliner.js:232,237,246` | No entities. · Nothing selected. | keep |
| `outliner.js:241` | {n} entities selected. | keep |
| `outliner.js:257–297` | Label · Point · Length · Vertices · Width · Depth · Elevation · Radius · Height | keep (values with unit) |
| `outliner.js:321` | Hidden in the view. Right-click → Show to restore. | Hidden in the view. Right-click and Show restores it. |
| `render.js:185` | draw error: {message} | Refused to draw: {message}. |
| `selection.js:230` | Select {filter} (1–5). Click, window, or crossing. | Select {filter}: click, or drag a window or a crossing. |
| `selection.js:242` | Crossing · Window | keep |
| `selection.js:243` | Nothing in the window. | keep |
| `selection.js:253` | Nothing to select. | keep |
| `tools.js:81` | Trim (T): click the part to remove. {n} cutter(s) pinned. Shift pins more. | Trim: click the part to remove. {n} cutters pinned; Shift pins more. |
| `tools.js:82` | Trim (T): click the part to remove. Shift pins a cutter. All lines cut if none pinned. | Trim: click the part to remove. Shift pins a cutter; with none pinned, every line cuts. |
| `tools.js:85` | Extend (E): click the end to grow. {n} boundary line(s) pinned. | Extend: click the end to grow. {n} boundaries pinned. |
| `tools.js:86` | Extend (E): click the end to grow. Shift pins a boundary. All lines if none pinned. | Extend: click the end to grow. Shift pins a boundary; with none pinned, every line bounds. |
| `tools.js:103,120,141` | Select entities first, then Move. (Rotate, Mirror) | Move: select the entities first. (Rotate, Mirror alike) |
| `tools.js:110` | Move: click the destination, or type a length and Enter. | keep |
| `tools.js:127` | Rotate: type degrees and Enter, or click a second point for the angle. | keep |
| `tools.js:148` | Mirror: click the second point of the axis. | keep |
| `tools.js:158,175` | Select entities first, then Array. n is the count. (Polar) | Array: select the entities first. n is the total count. (Polar alike) |
| `tools.js:165` | Array: click the spacing to the next copy. n is the total count. | keep |
| `tools.js:206` | Extend: click the end to grow, or Shift-click a boundary. | keep |
| `tools.js:207` | Trim: click the part to remove, or Shift-click a cutter. | keep |
| `tools.js:214` | Extend: click the short end toward a boundary (implied intersection is OK). | Extend: click the short end toward a boundary. Implied intersections count. |
| `tools.js:215` | Trim: click a free end — the stub past the nearest cutter. | Trim: click a free end. The stub past the nearest cutter goes. |
| `tools.js:225,230` | Break: click the first line. · Break: click the crossing line. | keep |
| `tools.js:235` | Break: those lines do not cross. Click another line. | Refused: Those lines do not cross. Click another line. |
| `tools.js:245` | Node: click a line, face, or polyline. | Node: click a line, face or polyline. |
| `tools.js:256` | Select a face, circle, or ellipse first. | Extrude: select a face, circle or ellipse first. |
| `tools.js:263` | Extrude: move for height, then click or Enter. | Extrude: move for the height. Click or Enter places it. |
| `tools.js:274` | Line: click the next point, or type a length and Enter. | keep |
| `tools.js:287` | Polyline: click the next point. | keep |
| `tools.js:300` | Rect: click the opposite corner. | Rectangle: click the opposite corner. |
| `tools.js:314` | Circle: click the radius, or type it and Enter. | keep |
| `tools.js:316,317` | Polygon: click the radius. · Ellipse: click a corner of the bounding box. | keep |
| `tools.js:332,337` | Arc: click a second point on the arc. · Arc: click the end point. | keep |
| `tools.js:348,353` | Bézier: click control point {n}. | keep |
| `tools.js:364` | Box: click the opposite corner of the face. | keep |
| `tools.js:385` | Select: click, or drag L→R window / R→L crossing. Filter 1–5. Shift adds. Delete removes. | Select: click, or drag right for a window and left for a crossing. 1 to 6 filter; Shift adds; Del deletes. |
| `tools.js:386` | Line: click to chain segments, or type a length and Enter. Enter or Esc places the chain. | keep |
| `tools.js:387` | Polyline: click vertices. Enter finishes. Click start or type C to close. | Polyline: click the vertices. Enter finishes; C or a click on the start closes. |
| `tools.js:388` | Rect: two clicks for a rectangle on XY. | Rectangle: click two corners on XY. |
| `tools.js:389` | Circle: centre, then radius. Then Select + Extrude. | Circle: click the centre, then the radius. |
| `tools.js:390` | Arc: three clicks (start, on-arc, end). | Arc: click the start, a point on the arc, then the end. |
| `tools.js:391` | Ellipse: centre, then a corner of the bounding box. | Ellipse: click the centre, then a corner of the bounding box. |
| `tools.js:392` | Polygon: centre, then radius. The library places a hexagon. | Polygon: click the centre, then the radius. Six sides. |
| `tools.js:393` | Bézier: four control points. | Bézier: click four control points. |
| `tools.js:394` | Box: rectangle, then pull height. Type height and Enter. | Box: click two corners, then pull or type the height. |
| `tools.js:395` | Extrude: select a face/circle/ellipse, then pull height. | Extrude: select a face, circle or ellipse, then pull the height. |
| `tools.js:396` | Move (M): select entities, click a base point, then the destination. | Move: click a base point, then the destination. |
| `tools.js:397` | Rotate: select, click the pivot, type degrees or click an angle. | Rotate: click the pivot. Type degrees or click an angle. |
| `tools.js:398` | Mirror: select, then two clicks for the mirror axis. | Mirror: click two points on the axis. |
| `tools.js:399` | Array: select, click spacing to the next copy. | Array: click the spacing to the next copy. |
| `tools.js:400` | Polar: select, click the centre. Length = sweep ° (default 360). | Polar: click the centre. A typed length is the sweep in degrees, 360 by default. |
| `tools.js:401` | Trim (T): click the part to remove. Shift pins a cutter. Implied intersection is OK. | Trim: click the part to remove. Shift pins a cutter. Implied intersections count. |
| `tools.js:402` | Extend (E): click the short end to grow to a boundary. Shift pins a boundary. | Extend: click the short end to grow to a boundary. Shift pins a boundary. |
| `tools.js:403` | Break: click two crossing lines to insert a shared node. | keep |
| `tools.js:404` | Node: click a line, face, or polyline to insert a shared point. | Node: click a line, face or polyline to insert a shared point. |
| `tools.js:405,406` | Chamfer: type a distance, then click a face or polyline corner. (Fillet: radius) | keep |
| `transform.js:15` | Move cancelled (zero displacement). | Move cancelled: zero displacement. |
| `transform.js:29,44,60` | Moved {n} entities. · Rotated {n} entities. · Mirrored {n} entities. | keep |
| `transform.js:65` | n must be at least 2 for an array | Refused: An array needs n of 2 or more. |
| `transform.js:78,95` | Linear array: {n} items. · Polar array: {n} items. | Linear array of {n} copies. · Polar array of {n} copies. |
| `viewcube.js:169` | ISO (Front–Right). | ISO view, front right. |

Rows that read `Select entities first, then <Verb>.` (eight in all) collapse to one
template, `<Verb>: select the entities first.`, in `strings.js`.

### 2.4 Server and document messages

| Source | Current | Proposed |
|---|---|---|
| `server.py` 404 | unknown path {path} · missing static file {name} | keep (agent-facing, English) |
| `server.py` CLI | port {n} already in use | keep |
| `DocumentError` (163 raises) | lower-case clause, no values: "fillet radius is too large for the edges" | Reword on touch: capitalised by the client, values stated: "fillet radius 120 mm exceeds the shorter edge, 80 mm". `code` unchanged |
| `DocumentError` internal | internal error: second line vanished | keep; the client shows `Refused: Internal error: …` and the log keeps it |

## 3. Drawing output style

### 3.1 Pens, ink, fills, type (the `render/style.py` data, ADR 0033)

| Token | Value | Source |
|---|---|---|
| Black | `#000000` (DXF ACI 7) | ADR-005 D1 |
| Dark Grey | `#808080` (ACI 8) | ADR-005 D1, ADR-010 Grey128 |
| Grey | `#c0c0c0` (ACI 9) | ADR-005 D1, ADR-010 Grey192 |
| Grey210 | `#d2d2d2` (true colour 210,210,210) | ADR-010 D2 |
| Blue | `#000077` (true colour 0,0,119) | ADR-004 D2, token card |
| Pens (mm) | 0.10 · 0.20 · 0.30 · 0.40 · 0.50 | ADR-005 D1 |
| Screen px | `max(0.75, 5 × mm)`: 0.75 · 1.0 · 1.5 · 2.0 · 2.5 | ADR 0031 §3.3 |
| DXF lineweight | 9 · 20 · 30 · 40 · 50 (1/100 mm) | DXF enum has no 10 |
| Hidden pattern `H-` | dash 2.0 mm, gap 1.0 mm at paper scale; 6 px / 3 px on screen | ADR-005 D1 pattern letter |
| Working font | `"Arial Narrow", "Archivo Narrow", sans-serif` | ADR-007 D4, ADR-009 D1 |
| Display font | `"Bahnschrift SemiBold Condensed", "Bahnschrift", "Saira SemiCondensed", sans-serif` | ADR-009 D2 |
| Text sizes (mm) | 1.75 dense · 2.0 body · 2.5 emphasis · 3.5 view title · 5.0 header | ADR-007 D2 |
| Text on screen | 1 mm = 5 px (2.0 mm → 10 px; 3.5 mm → 17.5 px), floor 9 px | ADR 0031 §3.3 |
| Background | `#ffffff`, Transparent text (no mask) unless over a fill | ADR-007 D3 |
| Review highlight | `#c64a1a` stroke, 35 % fill; never exported | ADR 0031 §3.6 |

### 3.2 Entity → drawing style

`Role` is what `scene.py` attaches to a drawable (`Drawable.layer`); `render/style.py` resolves it: `SECTION_STYLE` for the section roles, `SKETCH_STYLE` for the rest ([ADR 0033](../adrs/0033-ape-drawing-style-errata.md)). The canvas twin is `static/js/section.js` `SECTION_STYLE`, reading the canvas roles of §1.1.

| Entity (kind) | Role | Line style | Fill | Layer (DXF) | Notes |
|---|---|---|---|---|---|
| `Point` | `point` | — | disc 0.5 mm, Black | `POINT` | Bar points are drawn by the bar, not as points |
| `Line`, `Polyline` (sketch, frame axis) | `sketch` | `0.30mm S-Black` | — | `SKETCH` | Frame axes are intent, not structure edges |
| `Circle`, `Arc`, `Ellipse`, `Bezier` | `sketch` | `0.30mm S-Black` | — | `SKETCH` | |
| `Face` (3-D, not section) | `face` | `0.20mm S-Black` outline | none | `FACE` | The 15 % blue tint goes; projection weight (ADR 0033) |
| `Box`, `Solid` edges | `solid` | `0.20mm S-Black` | — | `SOLID-EDGE` | Projection; no hidden-line removal |
| `ConcreteFace` | `concrete-cut` | `0.40mm S-Black` | `Solid - Grey210 - Transparent` | `CONCRETE-CUT`, fill on `CONCRETE-FILL` | Section is a cut (ADR-005 D2) |
| `WallLeg` axis | `wall-axis` | `0.10mm H-Dark Grey` | — | `WALL-AXIS` | Intent line; thickness is shown by the face |
| `WallLeg.horizontal` | `tag` | — | — | `TAG` | `Φd @ s mm, {curtains} curtains` beside the leg |
| `Bar` | `bar` | edge `0.10mm S-Blue` | disc at `diameter_mm`, Blue | `BAR` | True scale; never below 0.6 mm on paper |
| `Hoop` | `hoop` | `0.30mm S-Blue` | — | `HOOP` | Path = hull of bar centres offset by (d<sub>b</sub> + d<sub>h</sub>) / 2; 135° hook ticks of 6 d<sub>h</sub> at the closing corner (planned, not built in D4) |
| `Crosstie` | `crosstie` | `0.20mm S-Blue` | — | `HOOP` | Bar to bar, 135° or 90° hook tick per `hooks` (planned, not built in D4) |
| `CoverGuide` | `cover` | `0.10mm H-Dark Grey`, short dash (ADR 0033; Grey 192 vanishes on Grey210) | — | `COVER-GUIDE` | Face ring inset by `cover_mm` |
| entity `label` | `label` | — | — | `LABEL` | Working font 2.0 mm, Blue |
| `#id` (show_ids) | `label` | — | — | not exported | Debug only |
| Bar group tag | `tag` | leader `0.10mm S-Blue` | — | `TAG` | `n Φd`, one per designation (D4) |
| Hoop / crosstie tag | `tag` | leader `0.10mm S-Blue` | — | `TAG` | `Tie Φd @ s mm`, `Crosstie Φd @ s mm`, `×n` for several |
| Cover note | `tag` | — | — | `TAG` | `Cover c mm`, with a leader |
| Overall dimensions | `dimension` | `0.10mm S-Blue`, filled 30° arrows | — | `DIMENSION` | Arial Narrow 2.5 mm, Transparent (ADR-006 default linear) |
| View title | `view-title` | underline `0.30mm S-Blue` | — | `VIEW-TITLE` | Display font 3.5 mm: `SECTION {label}`, `PLAN`, `FRONT ELEVATION` … |
| Scale line | `view-title` | — | — | `VIEW-TITLE` | Working font 2.0 mm: `SCALE 1:{n}` on an annotated plan of a section; n is the scale the 5 px per paper mm mapping implies |
| Scale bar | `scale-bar` | `0.10mm S-Blue` | — | `SCALE-BAR` | Text `{n} mm` |
| Empty draft | `label` | — | — | — | `Empty drawing`, centred, 50 % |
| Highlight | `highlight` | `#c64a1a`, 2.5 px | 35 % | never | Agent review aid |

### 3.3 View-title vocabulary

The views `render_svg` offers (`render/api.py` `VIEW_NAMES`); a new view adds its row here and in `render/style.py` `VIEW_TITLES`.

| `view.name` (identifier, unchanged) | Title on the drawing |
|---|---|
| `top` | PLAN |
| `front` | FRONT ELEVATION |
| `right` | RIGHT ELEVATION |
| `iso` | ISOMETRIC |
| section (z = 0 with section entities) | SECTION {face label, or none} |

### 3.4 Designation glyph

The document stores `Ø16` (ADR 0024 P12). The drawing prints `Φ16`, the office tag
grammar (`references/planillas-and-marks.md`). The mapping is one function in
`render/annotate.py`; nothing else converts.

## 4. Implementation plan

Each stage is one PR, docs-free except for its own spec row. Order and dependencies are in
ADR 0031 "Implementation stages".

### D1 — UI tokens and themes (implemented)

- Move `index.html` `<style>` to `static/css/app.css`; write both themes as custom
  properties under `:root[data-theme=light|dark]` and `@media (prefers-color-scheme)`.
- `static/js/theme.js` (pure apart from reading computed style once per theme change):
  exports `colors()` as numbers for three.js; `draw.js`, `ghosts.js`, `viewport.js`,
  `viewcube.js`, `prefs-ui.js` read it. `prefs.js` gains `theme: "system"|"light"|"dark"`
  and the `paper`/`mist`/`carbon` canvas presets; old `g2`/`g5`/`g6` values map on load.
- Vendor `ArchivoNarrow-{Regular,SemiBold}.woff2` + `OFL.txt` under `static/fonts/`.
- `server.py`: routes for `/css/<name>.css` and `/fonts/<name>.woff2`, same whitelist
  regex style as `/js/`.
- Inline the wordmark SVG in the menubar; mode chips in `cmdline.js` `refreshToggles`.
- Trim preview: keep in `--ghost`, discard dashed in `--signal`.
- Tests: `tests/js/theme.test.mjs` (token table parses, both themes complete),
  `tests/test_scratchpad.py` (css and font routes 200, unknown font 404).
- Bump `app.js?v=N`. Update `logo/README.md` (light variant) and `specs/scratchpad.md`.

### D2 — UI strings (implemented)

- `static/js/strings.js`: `export const T = { "hint.line.next": "Line: click the next point. Esc ends the chain.", … }`
  plus `t(id, params)`. Every row of §2.2 and §2.3 becomes an entry; modules import `t`.
- `index.html` keeps literal English for the static markup (it is the same pack); a later
  `es` pack would need `data-t` attributes, out of scope here.
- Refusal prefix in one place: the `catch` sites in `commands.js` and `docfile.js` call
  `refuse(error)` from `cmdline.js`, which colours the line with `--signal-text`.
- Tests: `tests/js/strings.test.mjs` asserts no entry matches `/—|–|\.\.\.|…|!|\?|\bOK\b|\byou\b|\bwe\b|\bplease\b/i`
  (menu labels ending in `…` are exempt by key prefix `menu.`).

### D3 — Render style (implemented)

- `render/style.py` (#32's table, extended; ADR 0033): `pen_px(mm)`, the ink and font
  constants, `LayerStyle` with its ADR-005 `line_style`, ADR-010 `fill_name` and DXF
  `layer_name`, `SECTION_STYLE` (concrete, cover, leg, hoop, crosstie, bar),
  `SKETCH_STYLE` (face, solid, edge, point), `VIEW_TITLES`.
- `drawable.py` / `scene.py`: boxes and solids move from `edge` to a `solid` layer.
- `svg.py`: one group per layer in a fixed paint order (faces, section layers, solids,
  sketch edges, points, highlight, text, legend); widths from `pen_px`; labels in the
  working font, blue; the view title in the display font with a 0.30 mm rule; the empty
  placeholder `Empty drawing`; `data-*` attributes unchanged.
- Canvas: the light values of `--fill-concrete`, `--ink-concrete`, `--ink-section-guide`
  and `--ink-rebar` in `css/app.css` become `#b4b4b4` (Grey210 once drawn at 60 % on white),
  `#000000`, `#808080`, `#000077`; carbon keeps the D1 lifted values. The light theme's
  default canvas is white like the SVG render, with a `#cfcfcf` / `#e2e2e2` grid (owner,
  2026-10-14); the chrome stays APE paper.
- Tests: the 19 goldens in `tests/fixtures/render/` regenerated; `tests/test_render_style.py`
  checks every style name is an ADR-005 / ADR-010 name and every layer has a style.

### D4 — Section annotation (implemented)

- `render/annotate.py`, derived at render time from the document and the drawables: no
  op, no log entry, no change to the section-draft export. Only a `top` view with a
  concrete face drawn is annotated.
- **Standard scale.** An annotated plan is drawn at exactly the largest drafting scale
  at which the section, its dimensions and every tag stack fit the frame without
  overlapping. Candidates are, in order, the office ladder (`apeRevit`
  `library/graphics-tokens.json` `scale_ladder`: 1:5, 10, 15, 20, 25, 50, 75, 100) and
  then ISO 5455 (1:200, 250, 500, 1000, 2000, 5000). The legend's `SCALE 1:n` and its
  scale bar both use that n.
- **Fixed paper sizes.** At 5 px per paper mm, text is 2.0 mm (ADR-007), dimension text
  2.5 mm, arrowheads 1.6 mm, and the leader and dimension pen 0.10 mm, whatever the
  scale.
- **Tags by group,** each group a stack beside what it labels, with leaders (0.10 mm pen,
  a 1 px dot on the target nearest the stack):
  - each hoop: the bars inside its ring, one tag per designation (`6 Φ16`), then
    `Tie Φd @ s mm`, then the crossties inside it (`Crosstie Φd @ s mm`, `×n` for several);
  - the bars and crossties in no hoop (the web);
  - the whole section: wall-leg web steel `Φd @ s mm, n curtains` and `Cover c mm`.

  Identical tags in a group read once.
- **Sides.** A section wider than it is deep stacks above or below, on the side nearer
  each group; a deeper one stacks left or right. Stacks on one side are pushed apart
  along it; when a side overflows, one stack spills to the opposite side. Stacks never
  cross the concrete, the dimensions, the legend or the frame.
- **Overall dimensions** of the concrete's box, below and left of it: 0.10 mm lines,
  filled 30° arrows, whole millimetres.
- `render_svg(annotate=True)` uses the layout's scale and centre. With a `window`, or
  when no standard scale leaves room, it draws the bare section fitted as before.
  `annotate` is on the agent `render` tool, the MCP schema, `/api/render.svg`
  (`annotate=false`) and the CLI (`--no-annotate`).
- SVG only: the 3-D canvas draws no tags (§3.2 asks for none there).
- Not built yet: hook ticks for hoops and crossties from `hooks`. They belong with the
  hoop geometry and need their own overlap rules.
- Tests: `tests/test_render_annotate.py`. It has annotated goldens for the pier and the
  four `section_draft` fixtures, and checks that tags clear each other, the concrete and
  the frame (at 1200 × 500 and at the default 800 × 600), that each annotated drawing is
  at a standard scale, that the pier's tags sit beside their group, the office tag text, the flag on every surface, that nothing is stored, and
  that only plans of sections are annotated. The bare section goldens render with
  `annotate=False` and are unchanged.

### D5 — DXF (ADR 0034, Proposed)

Decided in [ADR 0034](../adrs/0034-dxf-export.md), which replaces the stdlib writer first
sketched here:
- `render/dxf.py` uses ezdxf, behind an optional `apeCAD[dxf]` extra.
- Output is AC1027 (R2013), model space at 1:1 mm.
- Layers come from `render/style.py` `layer_name`, with ByLayer weight and colour; crossties
  get their own `CROSSTIE` layer.
- Annotation is native `MTEXT` and `DIMENSION` in the ADR-006 and ADR-007 style names, placed
  by the D4 layout.
- Surfaces: an `export_dxf` agent and MCP tool, `GET /api/export.dxf`, and the CLI
  `export-dxf`.
