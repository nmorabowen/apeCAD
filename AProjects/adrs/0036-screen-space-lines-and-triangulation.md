# ADR 0036 — Ear-clipping triangulation, screen-space LineSegments2, and SelectionHalo

**Status:** Accepted (2026-10-24)

## Context

Three rendering and picking limitations in the 3-D scratchpad affected structural engineering workflows:

1. **Concave polygon fan triangulation.** `draw.js` (`addFaceGraphic`, `addPlanarFace`) and `pick.js` (`rayHitsPolygon`) triangulated planar faces with a naive vertex-0 fan (`[0, i, i+1]`). For concave L-, T-, and C-shaped shear walls or slabs, the fan bridges across re-entrant corners, filling and picking the void outside the polygon.
2. **1 px `gl.LINES` cap.** WebGL's native `THREE.Line` / `THREE.LineSegments` ignores `linewidth > 1` on modern ANGLE/Direct3D/Metal drivers, making sketch curves, concrete outlines, hoops, and crossties render at the same 1 px weight regardless of hierarchy.
3. **Occluded selection inside solids.** When a reinforcing bar, hoop, crosstie, or internal B-rep edge is selected inside a concrete solid or face, depth-tested geometry or lack of a casing halo makes the selection hard to distinguish against the surrounding fill.

## Decision

1. **3-D plane projection + 2-D ear-clipping triangulation (`triangulatePolygon2D` / `triangulatePlanar3D` in `geom.js`).**
   - Project any 3-D planar polygon onto its dominant normal plane, normalize winding, and ear-clip convex ears that contain no reflex vertices (`triangulatePolygon2D`).
   - Use the resulting triangle index triples in `draw.js` (`addFaceGraphic`, `addPlanarFace`) and `pick.js` (`rayHitsPolygon`), so concave L/T/U/C polygons render and ray-pick accurately without external geometry kernels.
2. **Screen-space `LineSegments2` + `LineSegmentsGeometry` + `LineMaterial` (`worldUnits: false`).**
   - Upgrade wireframe/curve edges (`1.5 px`), section outlines and axes (`2.25 px`), and hoops/crossties/selected edges (`3.0 px`) in `draw.js` and `section.js` to screen-space `LineSegments2` with viewport resolution synced on resize and creation.
3. **Depth-exempt `SelectionHalo` (`depthTest: false`).**
   - Selected entities emit a two-pass screen-space halo (contrasting casing + `--pick` core with `depthTest: false` and elevated `renderOrder`) so selected bars, ties, and internal B-rep edges inside solids remain clearly visible at all viewing angles.

## Alternatives rejected

| Rejected | Why |
|---|---|
| Keep vertex-0 triangle fan | Fails on every L-, T-, and U-shaped RC wall or slab outline. |
| External earcut npm dependency | Unnecessary: a clean-room 2-D ear-clipping triangulator in `geom.js` is ~60 lines and keeps zero external runtime dependencies. |
| Native `THREE.LineBasicMaterial({ linewidth })` | Clamped to 1.0 px by WebGL/ANGLE on Windows, macOS, and Linux. |

## Consequences

- `geom.js` exports `triangulatePolygon2D` and `triangulatePlanar3D`, tested on concave L-shapes in `tests/js/geom.test.mjs`.
- `draw.js` and `section.js` build fat screen-space lines via `LineSegments2` and draw depth-exempt selection halos on selected entities.
