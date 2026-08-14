# ADR 0009 — Sketch palette and live dimensions

**Status:** Accepted (2026-08-14)

## Context

Chili3D's public sketch list is the right v0 palette for a spatial
scratchpad: line, rectangle, circle, arc, ellipse, polygon, Bézier.
The viewport should also show the measure of what is being drawn
(length, deltas, angle, radius) as coordinates in millimetres — a
readout, not a solver.

Chili3D remains AGPL; this ADR records the **principle** only
(ADR 0007). No Chili3D source is used.

## Decision

1. **Sketch curves are first-class intent:** `Circle`, `Arc`,
   `Ellipse`, `Bezier`. Rectangle and regular polygon stay closed
   `Face` loops of points. Polyline remains the free n-gon.
2. **Live dimensions are draw helpers.** The client shows X/Y/Z,
   ΔX/ΔY, length, and angle while drawing. They write explicit
   millimetre coordinates. They are not constraint equations
   (ADR 0008).
3. Tessellation of circles/arcs/ellipses/Béziers is a **viewport**
   concern. The document stores the compact intent.

## Alternatives rejected

| Rejected | Why |
|---|---|
| Discretize every circle into a polyline in the document | Loses the primitive; bad for later extrude/to_gmsh |
| Constraint dimensions in v0 | Still later (SolveSpace door, ADR 0004) |

## Consequences

The scratchpad gains a sketch toolbar and a coordinate/dimension
HUD. `to_frame` still ignores curves (members stay lines/polylines).
