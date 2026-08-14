# Spec — modelling helpers (scratchpad + intent)

**Status:** Implemented in part (2026-08-14)  
**ADRs:** 0003, 0004, 0008, 0009, 0010, 0011, 0012

## In the document (library base)

| Entity | Meaning |
|---|---|
| Face | Closed planar loop of point ids |
| Solid | Face extruded by a signed distance along a direction |
| Circle | Centre point + radius |
| Arc | Three points (start, on-arc, end) |
| Ellipse | Centre + axis-aligned radii |
| Bezier | Four cubic control points |

Ops: `AddFace`, `Extrude`, `AddCircle`, `AddArc`, `AddEllipse`,
`AddBezier`, `Translate`, `InsertNode`, `TrimLine`,
`AddFaceFromLines`, `Rotate`, `Mirror`, `ChamferCorner`,
`FilletCorner`, `Sew`, `Simplify`, `ArrayLinear`, `ArrayPolar`,
`Delete`.
`Box` stays as sugar. Regular polygon is a `Face`.
`Circle` and `Ellipse` are profiles: they fill as faces and can be
extruded without baking into a polyline.

`InsertNode` drops a shared Point onto a `Line`, `Face`, or `Polyline`
edge (reuse a Point within 1 mm). `Translate` / `Rotate` / `Mirror`
move the defining points of the named entities. `TrimLine` retargets
one end of a line onto a cut point. `AddFaceFromLines` needs ≥3 lines
that form one cycle. `ChamferCorner` and `FilletCorner` cut a convex
Face/Polyline vertex. `Sew` merges coincident points. `Simplify`
drops unshared collinear vertices. Arrays clone the selection.
`Delete` removes the named entities, anything that still referenced
them, and unused endpoints left behind.

## In the scratchpad (now)

- Parallel and perspective cameras
- LMB draw, MMB orbit, RMB pan, wheel zoom (no Orbit tool)
- Ghost line / rectangle / extrusion while drawing
- SNAP (F3): master snap on/off (nodes + grid)
- GRID (F9): 100 mm grid snap, only while SNAP is on
- ORTHO (F8): lock H/V; Shift inverts for one stroke
- Node snap overrides ORTHO (and typed length) so a snapped node keeps its real angle
- Snap marker: square at the active node/grid snap
- Type a length or angle in the command line at the bottom, then Enter
- Face/Rect tool = rectangle on XY, then `AddFace` (no height)
- Circle / Arc / Ellipse / Polygon / Bézier sketch tools
- Box tool = rectangle on XY, then pull height with the mouse, then `Face`+`Extrude`
- Alt+LMB also orbits (same as MMB)
- Ribbon (Select / Sketch / Solid / View) with apeCAD SVG icons
- Left dock: model tree with properties below it; drag the edges to
  resize; collapse to hide the dock
- Select tool: click a primitive; drag L→R window (inside) or R→L
  crossing (intersects); Shift adds; Esc returns to Select, then clears
- Modify: Trim, Node, Face (from lines), Chamfer, Fillet, Sew, Simplify,
  Delete (Del)
- Transform: Move, Rotate, Mirror, Array (linear), Polar
- Extrude the selected face, circle, or ellipse
- Live readout: X Y Z, ΔX ΔY, length, angle; dimension chips on the stroke

## Later (not this slice)

Typed dimensions as constraints, property *edits* (`SetRadius` and
friends), non-XY workplanes, push-pull of existing faces, boolean
solids, `to_gmsh`.
