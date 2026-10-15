# ADR 0033 — APE drawing style errata: cover guide ink and projection weights

**Status:** Proposed (2026-10-14)

Amends [ADR 0031](0031-ape-design-system.md) decision 3 ("Drawing output style") where
stage D3 found that the accepted text does not survive contact with the screen or with
#32's style tables. Everything else in ADR 0031 stands.

## Context

Stage D3 put ADR 0031 §3 into the SVG render and the 3-D canvas. Three points in its
Decision text did not hold up:

1. **Cover guide in Grey.** ADR 0031 §3.2 draws cover guides in `0.10mm H-Grey`, which is
   ADR-005 Grey, RGB 192. The guide sits on the concrete cut, which is ADR-010 Grey210, so
   it is grey 192 on grey 210: about 1.3 : 1. On screen, at 0.75 px and dashed, it does not
   show at all.
2. **A new `render/style.py`.** ADR 0031 §3.1 and its stage table create
   `render/style.py` as a new, pure-data file. #32 (`fix/render-section-entities`) had
   already created that file as the SVG style table for section entities, and `section.js`
   holds its client twin. A parallel table would split one fact across two homes.
3. **Faces and solids in one weight.** ADR 0031 §3.2 gives solid and box edges
   `0.20mm S-Black` and sketch curves `0.30mm S-Black`. The scene put boxes, solids and
   sketch curves on one `edge` layer, so the render could not tell them apart.

## Decision

1. **Cover guides and leg axes are `0.10mm H-Dark Grey`** (RGB 128) in the SVG render and
   on light canvases. The cover ring uses a shorter dash than the leg axis, so the two stay
   distinct. The DXF layer `COVER-GUIDE` carries the same style.
2. **#32's tables are the drawing-style tables.** `render/style.py` (`SECTION_STYLE`, plus
   a new `SKETCH_STYLE`) serves the SVG render, and `static/js/section.js` `SECTION_STYLE`
   serves the canvas, which reads its colours from the canvas roles of ADR 0031 §1. Each
   `LayerStyle` also records its ADR-005 line-style name, ADR-010 fill name and DXF layer,
   so D5 reads the same table.
3. **Boxes and solids draw on their own `solid` layer** at `0.20mm S-Black`. 3-D face
   outlines are also `0.20mm S-Black`, with no fill. Sketch lines, polylines and curves are
   `0.30mm S-Black`, including the `Line` entities that bound a face, because the render
   does not walk the B-rep to demote them.

## Alternatives rejected

| Rejected | Why |
|---|---|
| Keep Grey 192 for the cover guide as accepted | Invisible on the Grey210 cut; a guide nobody can see is no guide. |
| Drop the Grey210 fill under the guides | ADR-010 names Grey210 as the concrete cut solid; the fill is the office convention, the guide is apeCAD's own intent line. |
| A second style module beside #32's tables | Two homes for one fact (AProjects rule 1). |
| Demote face-bounding `Line` entities to 0.20 by walking the B-rep in the render | Doubles the render's knowledge of topology for a 0.5 px difference; revisit if a printed sheet shows it. |

## Consequences

- `specs/ape-design.md` §3 and §4 D3 describe the tables as built.
- `tests/fixtures/render/*.svg` (19 goldens) change: ink, pens, the `solids` group, type
  and the English view title.
- A DXF writer (D5, its own ADR) takes `line_style`, `fill_name` and `layer_name` from
  `render/style.py` and nothing else.
