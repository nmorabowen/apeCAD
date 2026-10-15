# ADR 0034 — DXF export of the drawing (stage D5)

**Status:** Proposed (2026-10-14)

Stage D5 of [ADR 0031](0031-ape-design-system.md), which named DXF a new output surface that
needs its own ADR. Builds on [ADR 0028](0028-agent-surface-mcp.md) (one catalog, thin
adapters, optional extras, one error envelope), [ADR 0033](0033-ape-drawing-style-errata.md)
(the per-renderer style tables are the drawing-style tables) and the D4 annotation
(`render/annotate.py`, PR #37).

## Context

The SVG render shows a draft to people and agents. APE's sets are drawn in Revit and
AutoCAD, and the place a section or a sketch enters them is a CAD file: a linked DXF in
Revit, or a DXF opened in AutoCAD. Today the engineer redraws it.

What a useful DXF needs:

- **Office graphics without rework.** Every line on a layer whose ByLayer weight and colour
  are the ADR-005 style (`0.40mm S-Black`, `0.30mm S-Blue`, …). Fills are the ADR-010 solids,
  and text and dimensions use the ADR-006 and ADR-007 type names, so that importing the file
  into the office template changes nothing.
- **R2000 or later.** Lineweights (group 370) arrived in R2000 and true colour (group 420) in
  R2004. R12 has neither, so an R12 file would lose exactly the information that makes it
  APE.
- **A valid file.** An R2000+ file needs handles, owner pointers, a CLASSES and an OBJECTS
  section, block records and dictionaries. AutoCAD refuses a file with a missing or
  mis-owned handle without saying which one.

`render/style.py` already carries `line_style`, `fill_name` and `layer_name` for every
drawable layer. It was built for this stage.

## Decision

1. **Write DXF with ezdxf, behind an optional `apeCAD[dxf]` extra.** ezdxf is MIT-licensed,
   pure Python and widely used. Core keeps `dependencies = []`, and importing `apeCAD`
   never imports ezdxf, the same rule as `mcp` (ADR 0028 decision 2). Without the extra,
   every DXF surface fails with `UNAVAILABLE` and the message names the extra. It never
   falls back to SVG.
2. **One writer, `render/dxf.py`, reading the same drawables and the same style table as
   the SVG.** Nothing about ink, weight or layer is decided twice.
   - **Model space at 1:1 in millimetres** (`$INSUNITS` = 4), world coordinates. A plan of a
     section lies at its own z, as in the document.
   - **Layers are the style table's `layer_name` values**, in English (`CONCRETE-CUT`,
     `CONCRETE-FILL`, `BAR`, `HOOP`, `CROSSTIE`, `COVER-GUIDE`, `WALL-AXIS`, `SKETCH`,
     `FACE`, `SOLID-EDGE`, `POINT`, `TAG`, `DIMENSION`, `VIEW-TITLE`). Each layer carries
     its ADR-005 style as ByLayer properties, and the style name goes in the layer
     description. Crossties move from `HOOP` to their own `CROSSTIE` layer, because their pen
     (0.20) differs from the hoop's (0.30) and ByLayer must hold one weight.
   - **Weights:** 0.10/0.20/0.30/0.40/0.50 mm map to DXF 9/20/30/40/50 (DXF has no 10).
   - **Colours:** Black is ACI 7. Dark Grey is ACI 8, and Grey is ACI 9. Blue (0, 0, 119)
     and Grey210 are true colours.
   - **Linetypes:** `H-` styles use a `HIDDEN` linetype whose dash pattern is in paper
     millimetres and is scaled by the drawing's scale.
3. **Geometry.**
   - Sketch curves, solid edges and face outlines are polylines, tessellated as for the
     render (one code path). Circles and arcs stay native `CIRCLE` and `ARC` where the
     document has them, so they stay editable.
   - The concrete cut is a closed polyline on `CONCRETE-CUT` and a solid `HATCH` in Grey210
     on `CONCRETE-FILL`.
   - A bar is a `CIRCLE` at its diameter plus a solid blue `HATCH`, both on `BAR`.
   - The review highlight is never written.
4. **Annotation follows `annotate`** (default on), as in the SVG. It is written only for a
   plan of a section, at the D4 standard scale:
   - **Tags:** `MTEXT` in the text style `Note - 2.0mm ArialNarrow Transparent` (ADR-007),
     with height = 2.0 mm × the scale n, so the tag prints at 2.0 mm. Leaders are lines on
     `TAG`.
   - **Overall dimensions:** native `DIMENSION` entities in the dimension style
     `Arrow - 2.5mm ArialNarrow Transparent` (ADR-006), on `DIMENSION`, so they stay
     associative.
   - **Title and scale note:** `SECTION <label>` in the ADR-009 display style and
     `SCALE 1:n`, on `VIEW-TITLE`.
   - **Placement:** the D4 layout (`plan_layout`) places everything. Its pixel positions
     convert back to model millimetres at that scale, so the DXF and the SVG agree.
5. **Surfaces, as thin adapters.**
   - A new agent tool `export_dxf(document, view="top", ids=None, annotate=True,
     save_to=None)` returns the envelope plus the DXF text, or the saved path under the
     root.
   - The MCP server registers it.
   - The scratchpad serves `GET /api/export.dxf` with the same query keys as
     `/api/render.svg`.
   - The CLI adds `python -m apeCAD.cli export-dxf FILE -o out.dxf`.
   - Only `view="top"` is accepted in v1. The DXF holds world coordinates and any CAD
     program projects them, so other views are a display concern, not an export.
6. **Version AC1027 (R2013).** It is current enough for every Revit and AutoCAD the office
   runs, and old enough for LibreCAD and QCAD to open.

## Alternatives rejected

| Rejected | Why |
|---|---|
| A stdlib R2013 writer (the ADR 0031 stage table's first idea) | Handles, owners, CLASSES and OBJECTS by hand are the most fragile code apeCAD could own, and a bad handle is a file AutoCAD silently refuses. |
| R12 by hand, stdlib only | No lineweights and no true colour: the office graphics, the reason for D5, would be lost. |
| ezdxf as a core dependency | Breaks the zero-dependency core (`dependencies = []`) that apeWorkbench and apeGmsh rely on when they launch the scratchpad. |
| Value-in-name layers (`0.40mm S-Black`) | Already rejected in ADR 0031: hiding the concrete would hide every 0.40 black line. |
| Exploded dimensions (lines and text) | Not editable in CAD; a native DIMENSION in the office dimension style is what the engineer would draw. |
| Paper space with a viewport and title block | Sheets are the Revit set's job (drawing-standards ADR-003). apeCAD hands over a drawing, not a sheet. |
| All four views | The DXF stores world coordinates; front, right and iso are views of the same geometry in any CAD program. |

## Consequences

- `pyproject.toml` gains the `dxf` extra (`ezdxf>=1.3,<2`). CI's `gates` job installs it,
  like `mcp`; the `core without extras` job checks that `import apeCAD` never imports ezdxf
  and that `export_dxf` answers `UNAVAILABLE`.
- `render/style.py` gains the `CROSSTIE` layer. The SVG output is unchanged, because SVG
  groups by drawable layer, not by DXF layer name.
- `render/annotate.py` exposes the layout in model millimetres for the writer, so tag and
  dimension placement stays in one place.
- Tests read the written file back with ezdxf and check the layer table (names, weights,
  colours, linetypes), the entity layers, the hatch colours, and the text and dimension
  style names. One golden DXF per section fixture, and an `UNAVAILABLE` test without the
  extra.
- A browser check is not enough here: the PR opens a fixture's DXF in a CAD program
  (LibreCAD or QCAD at least, AutoCAD or Revit if available) and shows a screenshot.
- `specs/ape-design.md` §4 D5 and `specs/agent-surface-mcp.md` (the new tool and route)
  are updated in the implementing PR.
