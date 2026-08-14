# ADR 0004 — Kernel-free intent document; realize downstream

**Status:** Accepted (2026-08-14)

## Context

apeGmsh already wraps Gmsh OCC: points, curves, surfaces, solids,
labels, Parts. A “v0 Python+NumPy CSG kernel until OCCT” would create
a third geometry world whose watertightness will not match Gmsh.
Solids that will be meshed will hit OCC at the handoff anyway.

apeSteel does not want BREP. It wants a frame graph.

## Decision

v0 apeCAD is a **kernel-free intent document**:

- Entities: points, lines/polylines, planar loops, labeled boxes /
  extrudes, layers/tags.
- No boolean engine, no tessellation as truth, no constraint solver.
- **Realize** through bridges: `to_gmsh(g)` uses existing
  `g.model.geometry` builders; `to_frame()` emits nodes, axes,
  lengths, section ids.
- Do not birth solids in a toy mesh and import STL into Gmsh.

## Alternatives rejected

| Rejected | Why |
|---|---|
| NumPy CSG / mesh booleans in v0 | Throwaway kernel; non-manifold handoff |
| OCCT / CadQuery / build123d as v0 | Second CadQuery; no scratchpad; heavy |
| Constraint solver in Python | Pointer-loop work; compile it if we ever need it |

## Consequences

The first useful consumer is likely **apeSteel’s frame graph**, then
apeGmsh labeled primitives. A geometry kernel is a later ADR, not a
startup task.
