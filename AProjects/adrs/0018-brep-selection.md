# ADR 0018 — B-rep topology is the selection graph

**Status:** Accepted (2026-08-14)

Amends [ADR 0015](0015-selection-filter.md): click, window, and
filter conversion walk the document B-rep, not a single-parent tree
guessed in the viewport. Amends [ADR 0016](0016-extrude-wall-faces.md):
the cap of a circle or ellipse extrude is the same kind of profile,
not a naked Point.

## Context

A box is already a prism of records (8 vertices, 12 edges, 6 faces,
1 solid). The scratchpad still indexed each edge under one face
(last writer wins) and window-picked a solid only if its *own* AABB
qualified. Shared edges, Element mode, and Solid-filter drags then
missed the object. Selection is how the scratchpad *handles*
geometry; if the B-rep cannot be picked, the draft is a picture.

Circle/ellipse extrude stored the far centre as `Solid.cap_id`. Face
filter had nothing to hit at the far end.

## Decision

1. **The document evaluates B-rep.** `Document.brep()` lists children,
   parents (an edge may have two faces), the root, and the owning
   solid. The scene payload ships that index. The client does not
   invent a second topology.
2. **Element is the B-rep root.** Nested vertices, edges, and faces of
   a solid are not independent Element hits; Point/Line/Face/Solid
   filters still pick that kind. Switching 1–5 converts the current
   pick along the graph (solid → its faces, face → its edges, …).
3. **A hit on a child selects the solid in Solid/Element window
   filters.** Hover preselection and live marquee preview the same
   mapping. Selecting an element tints every vertex, edge, and face
   under it.
4. **Circle/ellipse extrude writes a cap profile** (same radii, new
   centre). Still no wall faces — those would be a kernel surface.

## Alternatives rejected

| Rejected | Why |
|---|---|
| Keep a single parent map in the client | Shared edges belong to two faces |
| Tessellate circles into Face+Line loops | Loses centre+radius (ADR 0010) |
| Store `line_ids` on Face | Endpoints already share edges (ADR 0017) |

## Consequences

The scratchpad Select tool is a B-rep browser. Modelling-helpers
names the prism counts (box = 8/12/6/1) and the cap-profile rule.
Push-pull of a picked face remains later.
