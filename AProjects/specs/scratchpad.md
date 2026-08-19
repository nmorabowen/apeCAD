# Spec — scratchpad client

**Status:** Implemented (2026-08-14)  
**ADRs:** 0002, 0003, 0005, 0006, 0013, 0014, 0015, 0016, 0017, 0018, 0019

## Goal

A localhost web canvas that **emits ops at the Python document**. Humans
sketch on the XY plane (z = 0) so a spatial draft can be explained
without prose. The browser does not own geometry, undo, or labels.

## Shape

```
python -m apeCAD
        → stdlib HTTP on 127.0.0.1:8765 (preferred; next free port if busy)
        → Three.js canvas (CDN)
        → POST /api/op  (same JSON as Document.to_json ops)
        → GET  /api/identity  ({name, pid, host, port, root})
```

No Node, no Qt, no TypeScript build. Vanilla JS is enough for v0.

## Tools

Line (chains until Esc), polyline (Enter to finish, click start to close), rectangle (face), circle, arc, ellipse, polygon, Bézier, box
(face then extrude). Select (click, window, crossing; filter Point / Line / Face / Solid / Element; hover preselects the B-rep hit). Move, rotate,
mirror, array, polar, trim (T), extend (E), break, insert-node,
face-from-lines, join (J), chamfer, fillet, sew, simplify, delete (Del).
Undo / redo / clear. Save JSON.
SNAP / GRIDSNAP / ORTHO / GRID. Live millimetre readout (X Y Z, Δ, length, angle).
Layout R4 ([ADR 0014](../adrs/0014-menubar-side-rail-prefs.md)):
thin File / Edit / View / Grid / Help menubar; left dock is a nested B-rep
outliner with properties below it, then a vertical icon rail;
viewport; bottom command line. Docks collapse and drag-resize.
File New/Open/Save talks to the JSON document. Visualization (clay,
lights, AO) lives in Preferences as client state, not in the
ops log. Grid spacing, units, minor style, and hidden-line scale live in Grid → Preferences (also client state). Count/`n` is not a chrome field. Right-click the outliner to
select, rename, duplicate, hide, fit, or delete.
View cube (upper right): Z-up named faces; click face / edge / corner.
ISO is always Front–Right–Top (+X −Y +Z), not the nearest octant. Fit, ISO,
Open, and New frame the camera from the model bounds (or the grid, if empty)
so millimetre parts and hundred-metre sites both fill the view. Clip planes
and orbit limits follow that radius. Camera is not in the ops log.

## Out of scope

Constraints, workplanes other than z = 0, Studio integration,
`to_gmsh`, a Node toolchain, image export.
