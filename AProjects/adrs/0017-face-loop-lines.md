# ADR 0017 — Face loops write Line records

**Status:** Accepted (2026-08-14)

Amends [ADR 0015](0015-selection-filter.md) §5: Line filter must hit
every edge of a `Face`, including the twelve edges of a box. Amends
[ADR 0016](0016-extrude-wall-faces.md): walls go through `AddFace`, so
they get the same edges.

## Context

ADR 0015 refused to synthesise Line records for face loops: "Face
already holds the loop." The scratchpad Line filter only picks `Line`,
`Polyline`, `Arc`, and `Bezier`. Rect and Box write a point loop + Face
(and, after ADR 0016, wall Faces). There is nothing to hit. Outliner
Face children fall back to vertices. Window-select and Ctrl+A in Line
mode are empty on a box.

Element picking preferred a solid AABB over a nearer sketch line, so a
line in front of clay still selected the solid. Trim / Break / Node
used the first mesh hit, so a Face stole the click.

## Decision

1. **`AddFace` ensures a `Line` on every consecutive pair** of the
   loop (closed). Existing lines are reused by unordered endpoints
   (`_ensure_line`). No extra ops are logged; replay of `AddFace`
   recreates the same edges. Clone of a Face does the same on the
   mapped points.
2. **A rectangular box therefore has 12 lines** (4 base + 4 cap + 4
   vertical). Shared edges are one record. Deleting the solid drops
   cap/wall Faces and any Line that is no longer an edge of a surviving
   Face; the profile and its four base lines remain.
3. **Element click order is line, then point, then face, then solid**,
   each mapped to the B-rep root. A sketch line in front of a box
   selects the line. A box edge in Element still promotes to the solid.
4. **Trim, Extend, Break, and Node pick geometrically** (line aperture,
   then face for Node). First-mesh hit is not used for those verbs.
5. Face outlines stay a display overlay. In Line filter, curves draw
   with depth test off so edges show through clay.

## Alternatives rejected

| Rejected | Why |
|---|---|
| Keep ADR 0015 §5 (no Line records) | Line filter cannot pick a box |
| Client-only phantom edges | Selection is an entity id; Trim/Delete would be empty |
| Face stores `line_ids` | Reuse by endpoints already shares edges; deleting a line must not delete the Face |

## Consequences

`AddFace` / `AddBox` / `Extrude` grow Line counts (4 per new loop,
reusing shared edges). Tests that assumed a box had zero lines now
expect 12. Modelling-helpers documents that a Face loop is also a
Line cycle.
