# ADR 0016 — Extrude walls are selectable faces

**Status:** Accepted (2026-08-14)

Amends [ADR 0015](0015-selection-filter.md): Face filter must hit every
side of a `Solid`, not only the profile and cap. Vertex markers must
remain visible on every corner.

## Context

A box is `Face` + `Extrude`. The document already created the far cap
and the eight corners. The four vertical walls were implied, not
entities. Face-filter picking only tested the two planar loops, so a
click on a side missed. Vertex spheres were 80 mm world balls drawn
*under* the clay fill, so only the near bottom corners showed.

## Decision

1. **`Extrude` of a `Face` writes wall `Face` records** (one quad per
   profile edge) and stores their ids on `Solid.wall_ids`. Circles and
   ellipses stay a profile + cap point; they have no wall faces.
2. **The scratchpad draws the prism as those faces**, each tagged with
   its Face id, not one AABB tagged as the Solid. Element / Solid
   filter still promote a face hit to the solid.
3. **Vertices are screen-space dots** drawn after the clay, with depth
   test off, so every corner stays visible.

## Alternatives rejected

| Rejected | Why |
|---|---|
| Pick laterals with no entity id | Selection is an entity id; Move/Delete would be empty |
| Keep the AABB volume mesh | Hides vertices; cannot highlight one face |

## Consequences

A rectangular box has six faces in the outliner. Deleting the solid
drops the cap and the walls; the original profile remains. Replay of
existing `AddBox` / `Extrude` ops creates the walls.
