# Spec — modelling helpers (scratchpad + intent)

**Status:** Implemented in part (2026-08-14)  
**ADRs:** 0003, 0004, 0008, 0009, 0010, 0011, 0012, 0013, 0015, 0016, 0017

## In the document (library base)

| Entity | Meaning |
|---|---|
| Face | Closed planar loop of point ids; each consecutive pair also has a `Line` (reused if it already exists) |
| Solid | Face extruded by a signed distance; far-end vertices (and a cap face) are created |
| Circle | Centre point + radius |
| Arc | Three points (start, on-arc, end) |
| Ellipse | Centre + axis-aligned radii |
| Bezier | Four cubic control points |

Ops: `AddFace`, `Extrude`, `AddCircle`, `AddArc`, `AddEllipse`,
`AddBezier`, `Translate`, `InsertNode`, `TrimLine`, `BreakCrossing`,
`AddFaceFromLines`, `JoinPolyline`, `Rotate`, `Mirror`, `ChamferCorner`,
`FilletCorner`, `Sew`, `Simplify`, `ArrayLinear`, `ArrayPolar`,
`Delete`.
`AddBox` is sugar: it writes a `Face` + `Extrude` (`Solid`). The `Box`
entity is not created. Regular polygon is a `Face`.
`Circle` and `Ellipse` are profiles: they fill as faces and can be
extruded without baking into a polyline.

`InsertNode` drops a shared Point onto a `Line`, `Face`, or `Polyline`
edge (reuse a Point within 1 mm). `Translate` / `Rotate` / `Mirror`
move the defining points of the named entities. `TrimLine` retargets
one end of a line onto a cut point (shorten *or* lengthen). The
scratchpad trims/extends against the infinite cutter so near-misses
still meet; click the stub to remove or the short end to grow.
`BreakCrossing` inserts one shared node on two crossing lines.
`JoinPolyline` consumes a connected chain of lines/polylines (shared
point ids; sew first if ends only coincide) and records one polyline,
open or closed. `AddFaceFromLines` needs ≥3 lines that form one cycle. `ChamferCorner` and `FilletCorner` cut a convex
Face/Polyline vertex. `Sew` merges coincident points. `Simplify`
drops unshared collinear vertices. Arrays clone the selection.
`Delete` removes the named entities, anything that still referenced
them, and unused endpoints left behind. Extrude of a Face also writes a
wall Face per profile edge (`Solid.wall_ids`) so every side is selectable.
A rectangular box therefore has six faces and twelve lines (shared edges
are one record).

## In the scratchpad (now)

- Perspective (vanishing points) and Parallel (axonometric, no vanishing points). O toggles those two 3D lenses.
- Orthographic views: Top / Front / Right / Left / Back / Bottom — true axis look (Top is +Z, screen-up +Y), parallel lens. Polar-orbit clamp is off for these views so they do not skew.
- LMB draw, MMB orbit, RMB pan, wheel zoom (no Orbit tool)
- Ghost line / rectangle / extrusion while drawing
- Line chains: each click continues from the last end until Esc; still stores `Line`s that share points
- Polyline: click vertices, Enter to finish open, click start or type C to close; stores `AddPolyline`. Join remains a repair tool.
- SNAP (F3): snap to existing nodes (vertices)
- GRIDSNAP (F7): snap to minor and major grid intersections; independent of SNAP and of grid visibility
- GRID (F9): show or hide the grid helper; does not control snapping. Major lines are continuous solids. Minor is dots at intersections (default) or hidden linetype (dash 2/3, gap 1/3 of the dash period).
- Show minor: Grid menu checkbox; hides minor dots/lines only. Snap to minor is unchanged (F7).
- Grid preferences: Grid → Preferences. Units mm / cm / m / in (display only; document stays millimetres). Auto spacing (default on) picks a 1–2–5 minor/major from the model plan size (~10 major cells across); empty scene uses the stored 100 / 1000 mm. Manual values, presets, or `grid 50 500` turn auto off. `grid auto` / `grid manual`. Dot size default 1.5 px. Line thickness default 1 px. Hidden scale default 0.25 when minor style is lines. Client pref, not in the JSON.
- ORTHO (F8): lock H/V; Shift inverts for one stroke
- Node snap overrides ORTHO (and typed length) so a snapped node keeps its real angle
- Snap square appears on node snap and on minor/major grid snap (when GRIDSNAP is on); major crossings use a larger square
- Type a length or angle in the command line at the bottom, then Enter
- Length, size, and radius live in the properties dock, not as labels on the stroke
- Face/Rect tool = rectangle on XY, then `AddFace` (no height)
- Circle / Arc / Ellipse / Polygon / Bézier sketch tools
- Box tool = rectangle on XY, then pull height with the mouse, then `Face`+`Extrude`
- Alt+LMB also orbits (same as MMB)
- Ribbon (Select / Sketch / Solid / View) with apeCAD SVG icons
- Left dock: nested B-rep tree (Solid → Face/Edge/Vertex) with
  properties below it; drag the edges to resize; collapse to hide
  the dock. No `n` field; polygon and array counts stay in the library.
  Right-click: select, rename, duplicate, hide/show, fit, delete.
- Select tool: click a primitive; click empty space to deselect; drag L→R window (inside) or R→L
  crossing (intersects); Shift adds; Esc returns to Select, then clears
- Selection filter (viewport overlay; keys 1–5 on Select): Point, Line, Face, Solid, or
  Element (default). Element maps the hit to the B-rep root (the whole object). Sub-object
  modes pick that kind even when nested under a solid. Outliner clicks ignore the filter.
  Ctrl+A respects it. `AddFace` writes Line records on the loop, so Line mode hits box
  edges. Element prefers a nearer line over a solid behind it.
- Modify: Trim (T), Extend (E), Break, Node, Face (from lines), Join (J),
  Chamfer, Fillet, Sew, Simplify, Delete (Del)
- Transform: Move (M), Rotate, Mirror, Array (linear), Polar
- Extrude the selected face, circle, or ellipse (replicates the profile knots at the far end)
- Live readout: X Y Z, ΔX ΔY, length, angle in the command line; properties hold committed sizes

## Later (not this slice)

Typed dimensions as constraints, property *edits* (`SetRadius` and
friends), non-XY workplanes, push-pull of existing faces, boolean
solids, `to_gmsh`.
