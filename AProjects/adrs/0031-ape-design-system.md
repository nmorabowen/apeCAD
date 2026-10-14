# ADR 0031 — The APE design system: UI tokens, UI voice and drawing output style

**Status:** Accepted (2026-10-14). Proposed 2026-10-10; the owner approved it on 2026-10-14
with one change, English for all output (decision 2.1).

Derives the scratchpad's look, its text and its rendered drawings from APE Ingeniería's
existing standards instead of inventing a fourth style. Values and tables live in
[`specs/ape-design.md`](../specs/ape-design.md); the mockup is
[`design/ape-design-mockup.html`](../design/ape-design-mockup.html). Touches no code: the
stages at the end are scheduled after the agent-surface ([ADR 0028](0028-agent-surface-mcp.md))
and section-mode ([ADR 0024](0024-section-mode-rc-intent.md)–[0026](0026-section-transport-and-client.md))
waves.

## Context

On 2026-10-11 the owner asked to "bring ape-tone into the mix" on three axes: APE visual
identity in the UI, the office voice for UI text, and APE drawing standards for rendered
output. Today apeCAD follows none of them.

- **The chrome is a private palette.** `static/index.html` hard-codes a slate dark theme
  (`--bg #1d2229`, `--accent #4a90d9`, Segoe UI 12 px) and the client repeats raw hex in
  `draw.js`, `ghosts.js`, `viewport.js`, `viewcube.js` and `prefs.js`. There is no light
  theme. The trim preview in `ghosts.js` tells "keep" from "discard" by green `#7dce7d`
  versus red `#ff6b6b`, which a protanope cannot read.
- **The render is not a drawing.** `render/svg.py` draws every edge at 1.5 px in `#1f2933`,
  tints faces blue at 15 %, highlights in `#e8590c`, and sets text in generic
  `sans-serif` 11 px with the English words "empty draft" and the view name. Nothing maps
  to an APE pen, colour, typeface or layer.
- **The UI text is good but uncodified.** About 180 strings across `index.html` and 15
  `static/js/` modules. Most are already short imperatives ("Line: click the next point."),
  but nothing keeps them so: there are em-dash pauses, "OK" as a verdict, "(T)" shortcuts
  inside hints, "Rect" next to "Rectangle", and no rule for how a refused op reads.

APE already has a standard for each axis:

| Axis | Source (read-only) | What it fixes |
|---|---|---|
| Brand | `ape WebPage/src/styles/global.css` (APE web ADR-001 D3) | Paper `#f7f6f3` / carbon `#14181d`, one steel accent `#2f74ad` (`#3d8fce` on dark), Archivo Narrow + Saira SemiCondensed, square buttons, uppercase tracked kickers |
| Plots | `ape-workflow/ape-libraries/apeGraphStyle/src/apeGraphStyle/__init__.py` (derived from `LadrunoGraphStyle`) | Archivo Narrow bundled under the OFL, protanopia-safe colour (never red against green), faint solid grid `#E4E7EB` |
| apeCAD mark | `logo/README.md`, `logo/wordmark.svg`, `docs/styles.css` | Black field, paper `#f4f0e6`, vest orange `#c64a1a`, blueprint construction lettering |
| Lines and ink | `ape-workflow/drawing-standards/ADR-005-lineweights-and-element-ink.md`, `token-card.md` | `{0.10…0.50}mm {S\|H}-{Grey\|Dark Grey\|Black\|Blue}`; cut 0.40, projection 0.20–0.30, profile 0.50; structure black, annotation and rebar blue |
| Annotation | ADR-004 (graphic tokens), ADR-007 (text notes) | All annotation RGB (0, 0, 119); Arial Narrow; body 2.0 mm, titles 3.5 mm, headers 5.0 mm; Transparent by default |
| Display type | ADR-009 (dual typeface) | Bahnschrift (SemiBold) Condensed for view titles only; Arial Narrow for all working text |
| Fills | ADR-010 (filled regions) | Greys 210 / 192 / 128 only; concrete cut = `Solid - Grey210` |
| Rebar | `apeRevit/library/graphics-tokens.json` (`rebar_data`), skill `ape-drawing-standards` (`references/planillas-and-marks.md`) | Bar and stirrup graphics in (0, 0, 119); tag grammar `n Φd`, `@s cm - [n u] Φd` |
| Voice | skill `ape-tono`, `references/tone-standard.md` (v1, 2026-09-11) | Impersonal, declarative; *notas de plano* register is "imperative, telegraphic"; no dash pauses, ellipses, exclamations or questions; verdicts from a closed list |
| Language | drawing-standards ADR-007 D5, `token-card.md` | The office keeps internal names in English and sheet content in Spanish (not adopted here, see decision 2.1) |

## Decision

### 1. UI tokens: APE web identity, two themes, one accent

1. **Colour roles, not colours.** The chrome and the canvas read CSS custom properties by
   role (`--surface-0/1/2`, `--line`, `--text`, `--muted`, `--accent`, `--signal`,
   `--canvas`, `--grid-major/minor`, `--ink-edge`, `--ink-rebar`, `--ghost`, `--pick`), and
   the three.js side reads the same roles through one module. No module keeps a raw hex.
2. **Light theme is APE paper, dark theme is APE carbon.** Light: surfaces `#f7f6f3` /
   `#efede8` / `#ffffff`, text `#1c2127`, line `#d8d5cd`. Dark: `#0c1016` / `#14181d` /
   `#1c2127`, text `#e8ecf1`, line `#232a33`. The theme follows `prefers-color-scheme` and a
   Preferences override. The override is client state, never in the document
   ([ADR 0014](0014-menubar-side-rail-prefs.md)). The canvas background presets
   (`g2`/`g5`/`g6` in `prefs.js`) become theme-tied presets with the same mechanism.
3. **Steel is state, vest is attention.** `--accent` is APE steel (`#2f74ad` light,
   `#3d8fce` dark): selection, the active tool, focus, toggles that are on. `--signal` is
   apeCAD's vest orange (`#c64a1a` light, `#e2703a` dark): snap markers, the crossing
   window, the discard half of a trim preview, refusals. Nothing else is coloured. The two
   hues differ in lightness as well as hue, which is the apeGraphStyle protanopia rule, and
   the trim preview drops green and red.
4. **Drawing ink on the canvas.** In the light theme, section-mode entities on the canvas
   use the drawing colours of decision 3 (rebar `#000077`, concrete cut black on a
   Grey210 fill), so the canvas previews the sheet. The dark theme lifts rebar to `#8c9cf0`
   (6.9 : 1 on carbon); `#000077` is unreadable there (1.07 : 1).
5. **Type.** One UI face: **Archivo Narrow** (OFL, the face apeGraphStyle already bundles),
   vendored as WOFF2 under `static/fonts/` so the localhost tool needs no font CDN, falling
   back to Arial Narrow, then Segoe UI. 13 px body, 11 px kicker, 12 px monospace
   (Cascadia Mono, Consolas) for the command line and coordinates, tabular figures for
   every number. Saira SemiCondensed and Bahnschrift stay out of the chrome; the brand is
   the wordmark graphic.
6. **Spacing and chrome.** A 4 px scale (2, 4, 6, 8, 12, 16, 24). Menubar 28 px, rail
   buttons 32 px, tree rows 22 px. Radius 2 px on inputs and buttons, 0 on menus, panels
   and dialogs (APE web buttons are square). Panel heads use the APE kicker: 11 px,
   600 weight, uppercase, 0.12 em tracking. Focus is a 2 px steel outline. The status bar
   shows each mode (SNAP, GRID, ORTHO) as a chip that is steel when on and muted when off,
   instead of listing only what is on.
7. **Icons.** Drawn on a 24-unit grid at 18 px, 1.5 stroke, **square caps and miter
   joins** (drafting, like the wordmark's construction strokes), vertices as filled
   3-unit squares (CAD grips), dashes `2 2`, tints at 20 % of `currentColor`. A bar is the
   one round glyph, because bars are round on a section.
8. **The mark.** The apeCAD wordmark (`logo/wordmark-transparent.svg`) replaces the text
   "apeCAD" in the menubar, inlined with `stroke="currentColor"` so it reads on both
   themes. This is the light variant `logo/README.md` says does not exist yet; the vest
   underline stays orange.

### 2. UI voice: the *notas de plano* register, in English

1. **Language policy: English for all output.** Decided by the owner on 2026-10-14. UI
   text, hints, menus, command-line messages, `DocumentError` messages, and everything
   apeCAD writes on a drawing (view titles, tags, notes, annotations, the empty
   placeholder) are **English**. Layer names, op names, error `code`s and JSON keys are
   identifiers and are English too. This departs from the office split in drawing-standards
   ADR-007 D5 (Spanish sheet content) by the owner's choice; the Revit set keeps its
   own Spanish sheets.
2. **All UI strings live in one table** (`static/js/strings.js`), keyed by id, so the text
   has one home and the lint in decision 2.3 has one file to check.
3. **Register.** The tone standard's *notas de plano* register: imperative and
   telegraphic. Its English rules apply: no *we* or *you*, no *please*, no *actually*, no
   *fine*, *OK* or *tight* as a status, no dash used as a pause, no ellipsis in a message,
   no exclamation, no question mark.
4. **Hint grammar.** `Tool: verb the object. Next step.` Sentence case, full stop, one
   or two sentences. Shortcuts go in tooltips and menus, not in hints.
5. **Result grammar.** Past participle, count, noun: "Moved 3 entities." "Grid 100 / 1000 mm."
   Units always, with a space.
6. **Refusal grammar.** A refused op reads `Refused: <reason>.` in `--signal`. The reason is
   the `DocumentError` text, first letter capitalised. New `DocumentError` messages state
   the values that refused them ("Fillet radius 120 mm exceeds the shorter edge, 80 mm."),
   the tone standard's "numbers first" rule. The 163 existing messages are reworded only
   when their module is touched; their `code`s never change (agents key on them,
   [ADR 0028](0028-agent-surface-mcp.md)).
7. **No verdicts.** apeCAD checks nothing ([ADR 0024](0024-section-mode-rc-intent.md) D2), so
   the UI never says *OK*, *pass*, *fail* or *cumple*. Section lint findings read as
   `Warning: <finding>.`; the five verdict words belong to apeConcrete's report.
8. **Lexicon.** "entity" for a document object, "element" only for the whole-element
   filter, "Rectangle" not "Rect", "Bézier" with the accent, British spelling as the UI
   already uses ("centre", "colour"), "Save as…" in sentence case. The ellipsis survives
   only on a menu item that opens a dialog, as the platform convention.

### 3. Drawing output style: APE pens, ink, type and fills

1. **A style table, not constants.** `render/style.py` (new, pure data) maps each drawable
   *role* to an ADR-005 line style, an ADR-010 fill, an ADR-007 text size and a layer
   name. `render/svg.py` reads it; a later DXF writer reads the same table. The full
   entity → role table is in the spec.
2. **Structure black, annotation and rebar blue.** Concrete faces in a section are *cut*:
   `0.40mm S-Black` on `Solid - Grey210 - Transparent`. Sketch curves and frame axes are
   `0.30mm S-Black`; solid and box edges seen in projection are `0.20mm S-Black`. Bars are
   filled discs at true diameter in (0, 0, 119); hoops `0.30mm S-Blue`, drawn as the bar
   hull offset by (d<sub>b</sub> + d<sub>h</sub>) / 2, which rounds each corner about its bar;
   crossties `0.20mm S-Blue`. Wall-leg axes `0.10mm H-Dark Grey`; cover guides
   `0.10mm H-Grey`. Every tag, label, dimension, scale bar and title is (0, 0, 119).
3. **Pens on screen.** An SVG with no plot scale draws a pen of *p* mm at
   `max(0.75, 5 p)` px (0.10 → 0.75, 0.20 → 1.0, 0.30 → 1.5, 0.40 → 2.0, 0.50 → 2.5), so the
   cut/projection hierarchy survives on screen. When a plot scale is given, widths are
   true paper millimetres in a millimetre viewBox.
4. **Type.** Working text in Arial Narrow (fallback Archivo Narrow), 2.0 mm body,
   1.75 mm dense; the view title in Bahnschrift SemiBold Condensed 3.5 mm with the scale
   line under it in Arial Narrow 2.0 mm (ADR-009). Text is Transparent (no mask) unless it
   sits on a hatch.
5. **English on the sheet, office tag structure.** View titles are `PLAN`,
   `FRONT ELEVATION`, `SECTION <label>`; the empty placeholder is `Empty drawing`. Bars
   tag as `n Φd` ("10 Φ20"), hoops as `Tie Φd @ s mm`, crossties as `Crosstie Φd @ s mm`,
   cover as `Cover c mm`. Spacings are in millimetres, like every other length apeCAD
   writes; the office's centimetre spacings (`@10 cm`) belong to the Revit planilla grammar,
   which apeCAD does not produce. The document keeps its `Ø16` designations
   (ADR 0024 P12, apeConcrete's spelling); `Ø → Φ` is a render-only mapping. apeCAD tags
   carry no `Mc` mark and no length: marks and planillas belong to the Revit set.
6. **Agent highlight is not ink.** The render's `highlight` set draws in vest orange over
   the drawing. It is a review aid, never written to DXF, and never mistaken for annotation
   blue.
7. **DXF later, same table.** Layers are English role names (`CONCRETE-CUT`, `BAR`,
   `HOOP`, `TAG`, …) carrying the ADR-005 style as ByLayer weight and colour, with the
   style name in the layer description. Lineweights map 0.10/0.20/0.30/0.40/0.50 mm to DXF
   9/20/30/40/50 (DXF has no 10). Black is ACI 7; blue and greys are true colour.

## Alternatives rejected

| Rejected | Why |
|---|---|
| Keep the slate palette and only rename tokens | It matches nothing APE owns, has no light theme and keeps the red/green trim preview. |
| Make the chrome apeCAD's black/paper/vest brand (the logo and `docs/` site) | One loud orange on black is a poster, not a work surface. Vest survives as the attention colour and the mark. |
| Use annotation blue (0, 0, 119) as the UI accent | It is the drawings' ink; on screen it would make every selected sketch line look like annotation. On carbon it is unreadable (1.07 : 1). |
| Spanish UI | apeCAD's code, docs, ADRs and agent surface are English, and `DocumentError` text is an agent contract. |
| English UI with Spanish sheet output (the office split of ADR-007 D5; this ADR's proposal of 2026-10-10) | The owner chose one language for all output (2026-10-14). |
| A bilingual toggle | Two packs to keep in step, for no reader who needs them. |
| Value-in-name DXF layers (`0.40mm S-Black`) | Hiding concrete would hide every 0.40 black line. Roles name layers; the style name rides in the description, so both conventions survive. |
| Rewrite all 163 `DocumentError` messages now | The ops modules are changing in parallel waves; a mass rewrite collides with every one. Reword on touch. |
| Load fonts from Google Fonts | The scratchpad is a localhost tool; a font CDN adds a network dependency the chrome does not need. three.js stays on its CDN ([ADR 0003](0003-python-document-web-client.md)). |

## Consequences

- `index.html`'s `<style>` (about 230 lines) moves to `static/css/app.css` with both
  themes; the server gains `/css/*.css` and `/fonts/*.woff2` routes. That also keeps
  `index.html` far below the 600-line ceiling ([ADR 0023](0023-module-boundaries.md)).
- A `static/js/theme.js` module becomes the only place three.js colours come from.
- A `static/js/strings.js` table holds every UI string, and a `node --test` check fails on
  forbidden patterns (dash pause, `OK`, `!`, `?`, *you*, *we*).
- `render/svg.py` output changes byte for byte. Any test or agent that pins the current
  SVG colours must move with stage D3 of the plan. Data attributes (`data-id`,
  `data-view`, `data-highlight`) do not change.
- The canvas and the SVG render share the rebar and concrete inks, so a section drawn on
  the light canvas looks like its render.
- The logo gets its first light variant (`currentColor` stroke). `logo/README.md` should
  record it when stage D1 lands.
- The render has no hidden-line removal (kernel-free, [ADR 0004](0004-kernel-free-intent-document.md)).
  `H-` styles are used for intent lines (axes, cover), never for computed hidden edges.
- DXF export is a new output surface and needs its own ADR when it is scheduled.

## Implementation stages

PR-sized, each after the waves it depends on. Files are named here so they can be
scheduled; the spec has the detail.

| Stage | Slice | Touches | After |
|---|---|---|---|
| D1 | UI tokens and themes | new `static/css/app.css`, `static/js/theme.js`, `static/fonts/ArchivoNarrow-{Regular,SemiBold}.woff2` + `OFL.txt`; `index.html` (drop `<style>`, inline wordmark, theme pref), `server.py` (css, font routes), `js/draw.js`, `ghosts.js`, `viewport.js`, `viewcube.js`, `prefs.js`, `prefs-ui.js`; `tests/js/theme.test.mjs`, `tests/test_scratchpad.py` (routes); `logo/README.md` | The section client (ADR 0026) lands, so its bar and hoop colours are born as tokens |
| D2 | UI strings | new `static/js/strings.js`, `tests/js/strings.test.mjs`; `index.html`, `js/tools.js`, `create.js`, `modify.js`, `transform.js`, `selection.js`, `outliner.js`, `grid-ui.js`, `docfile.js`, `commands.js`, `input.js`, `camera.js`, `viewcube.js`, `cmdline.js`, `render.js` | D1 (refusal colour), the S1 op catalog |
| D3 | Render style | new `render/style.py`; `render/svg.py`, `render/scene.py` (roles per drawable); `tests/test_render*.py` golden SVGs | Section entities (C1) in `scene.py`; the S2 agent render tool, so the style ships with it |
| D4 | Section annotation | new `render/annotate.py` (tags, view title, scale line, overall dimensions); `render/svg.py`; tests | D3 |
| D5 | DXF layers and export | new ADR, new `render/dxf.py`, an endpoint and an agent tool; tests | D3, owner's go-ahead |
