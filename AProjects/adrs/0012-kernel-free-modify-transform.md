# ADR 0012 — Kernel-free modify and transform

**Status:** Accepted (2026-08-14)

Amends [ADR 0011](0011-window-select-modify-nodes.md): rotate, mirror,
chamfer, fillet, sew, simplify, and arrays do **not** wait for a
kernel. Boolean solid chamfer/fillet still does.

## Context

Chili3D's public editing list (README only, ADR 0007) also names
chamfer, fillet, sew, simplify, rotate, mirror, and linear/circular
array. Those tools on a B-rep need OCCT. apeCAD is a scratchpad of
points, lines, and faces. The same *verbs* can run on that graph.

## Decision

1. **Rotate / Mirror** mutate defining points in XY (and a Box origin).
   Ellipse radii stay axis-aligned; only the centre moves.
2. **ChamferCorner / FilletCorner** act on a Face or Polyline vertex.
   Chamfer inserts two points and a line. Fillet inserts tangent
   points, a mid-arc point, and an `Arc`. Adjacent lines that were
   that corner are retargeted.
3. **Sew** merges coincident points in the selection (default 1 mm)
   so later lines share nodes. **Simplify** drops collinear vertices
   that are not shared with another loop.
4. **ArrayLinear / ArrayPolar** clone the selected subgraph (new
   unlabeled entities). Polar `count` includes the original; a 360°
   sweep does not duplicate at the wrap.
5. The scratchpad ribbon splits **Modify** (trim, node, face, chamfer,
   fillet, sew, simplify) from **Transform** (move, rotate, mirror,
   array, polar). `n` is polygon sides *or* array count.

## Alternatives rejected

| Rejected | Why |
|---|---|
| OCCT chamfer/fillet on solids | Kernel; AGPL; wrong product |
| Bake fillet as N face vertices only | Loses the `Arc` primitive |
| Copy-on-mirror as the only mode | In-place matches Translate/Rotate; copy is array |

## Consequences

Property *edits* (`SetRadius`), non-XY workplanes, push-pull, boolean,
and `to_gmsh` remain later.
