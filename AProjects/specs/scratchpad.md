# Spec — scratchpad client

**Status:** Implemented (2026-08-14)  
**ADRs:** 0002, 0003, 0005, 0006, 0013

## Goal

A localhost web canvas that **emits ops at the Python document**. Humans
sketch on the XY plane (z = 0) so a spatial draft can be explained
without prose. The browser does not own geometry, undo, or labels.

## Shape

```
python -m apeCAD
        → stdlib HTTP on 127.0.0.1:8765
        → Three.js canvas (CDN)
        → POST /api/op  (same JSON as Document.to_json ops)
```

No Node, no Qt, no TypeScript build. Vanilla JS is enough for v0.

## Tools

Line, rectangle (face), circle, arc, ellipse, polygon, Bézier, box
(face then extrude). Select (click, window, crossing). Move, rotate,
mirror, array, polar, trim (T), extend (E), break, insert-node,
face-from-lines, join (J), chamfer, fillet, sew, simplify, delete (Del).
Undo / redo / clear. Save JSON.
SNAP / ORTHO / GRID. Live millimetre readout (X Y Z, Δ, length, angle).
Left dock: model tree, properties below; drag to resize; collapse.
Command line at the bottom: prompts plus typed length/angle (Enter).
View cube (upper right): Z-up named faces; click face / edge / corner;
ISO and Fit. Camera is not in the ops log.

## Out of scope

Constraints, workplanes other than z = 0, Studio integration,
`to_gmsh`, a Node toolchain.
