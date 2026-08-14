# ADR 0011 — Window selection, modify ops, and insert-node

**Status:** Accepted (2026-08-14)

## Context

Click-select (ADR 0010) is not enough for a spatial scratchpad. Drafts
are made of many lines; the user must drag a window. Chili3D's *public*
tool list (not its source, ADR 0007) names the modify verbs a
scratchpad actually needs: move, trim, and break/split. Chamfer,
fillet, boolean, rotate, and mirror stay later — they want a kernel.

Other programs stop at trim/break. apeCAD's differentiator is that a
**node is a first-class Point** you can drop onto a line, face, or
polyline so later lines can share it.

## Decision

1. **Window / crossing selection is a client gesture.** Drag left→right
   is a window (entity fully inside). Drag right→left is a crossing
   (entity intersects). Shift adds. The document does not store
   selection.
2. **Modify ops are typed and replayable:** `Translate`, `TrimLine`,
   `InsertNode`, `AddFaceFromLines`. No OCCT. Trim only retargets a
   line endpoint onto a cut point; it does not split the cutter.
3. **Insert-node is the break/split.** The click projects onto the
   target edge. A nearby existing Point (~1 mm) is reused so
   connectivity is shared. A `Line` becomes two lines; a `Face` /
   `Polyline` gains a vertex; coincident lines and other loops that
   used that edge are updated.
4. **Face from selected lines** builds one closed cycle of ≥3 lines
   and records an `AddFace` loop of their point ids.

## Alternatives rejected

| Rejected | Why |
|---|---|
| Kernel trim/fillet (Chili3D/OCCT) | Wrong product; AGPL; not a scratchpad |
| Bake a node as a new unshared Point always | Breaks connectivity; later lines cannot join |
| Store selection in the document | Selection is a view; the ops log is the writer (ADR 0006) |
| Rotate / mirror / chamfer in this slice | Later; they are not required to assemble a frame |

## Consequences

The scratchpad ribbon gains a Modify group (Move, Trim, Node, Face).
The Python document can translate, insert nodes, trim lines, and
promote a line cycle to a Face. Property *edits* (`SetRadius`) remain
later.
