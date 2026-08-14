# ADR 0010 — Selection, inspector, and a command ribbon

**Status:** Accepted (2026-08-14)

## Context

The scratchpad can draw but cannot pick. Without selection there is no
project browser, no property inspector, and no "extrude this circle".
Chili3D's office-style ribbon and ArcCAD's typed entity properties are
the right *principles* (ADR 0007). Their source and icons stay out.

A circle is a closed planar profile, not a decorative curve. It must
be selectable and extrudable while keeping centre+radius as the
params (not a baked polyline in the document).

## Decision

1. **Selection is a first-class client mode.** LMB on Select picks an
   entity (viewport or browser). Esc cancels a draw, then returns to
   Select, then clears the pick. Highlight is viewport + browser.
2. **Two docks:** a project browser (entity list) and a properties
   panel (readout of the pick). Property *edits* (`SetRadius`, …) are
   a later op family; this slice displays ArcCAD-style params.
3. **Ribbon groups commands** (Select, Sketch, Solid, View) with
   apeCAD-drawn SVG icons. Not a Chili3D asset dump.
4. **Profiles:** `Face`, `Circle`, and `Ellipse` may be extruded.
   `Extrude.face_id` names the profile. The document keeps the
   compact intent; the viewport tessellates.

## Alternatives rejected

| Rejected | Why |
|---|---|
| Bake every circle into a Face of N points | Loses radius as a property |
| Property edits in this slice | Needs new mutating ops; display first |
| Copying Chili3D icons | Copyright / AGPL; we draw our own |

## Consequences

The scratchpad layout is ribbon + browser + viewport + properties.
Python `Extrude` accepts a profile id, not only a polygonal `Face`.
