# ADR 0029 — Delete takes the selection's whole B-rep subtree

**Status:** Proposed (2026-10-11)

Amends `specs/modeling-helpers.md`, which said that `Delete` removes the named entities,
anything that still referenced them, and the unused endpoints left behind. It also builds on
[ADR 0018](0018-brep-selection.md): B-rep topology is the selection graph, and it is now the
delete graph too.

## Context

The owner reported on 2026-10-11 that deleting complex geometry leaves its B-rep behind:
"a 3D leave planes, plane leave lines". Reproduced on `main` @ `75d960a`:

| Delete | Left behind |
|---|---|
| A box solid (8 points, 12 lines, 6 faces, 1 solid) | The base face, its 4 edges and 4 points |
| A face | Its 4 edges and 4 points |

The cause was in `draft/meta.py`. The delete set grew **upward**, to everything that referenced
a deleted entity. A solid also took its cap, its walls, and the edges no live face used. It
never grew **downward** into the selection's own parts. The base profile, its loop lines (ADR
0017) and the points they end on all stayed. `tests/test_edit.py::test_delete_solid_keeps_profile`
pinned that behaviour. No ADR had decided it; the rule came from the spec line above.

ADR 0018 already defines the parts of an entity in one place, `brep.build_brep` (`children`):

- a solid's profile, walls and cap;
- a face's loop edges, or its points when an edge is missing;
- a line's endpoints;
- a circle's or ellipse's centre;
- an arc's three points;
- a polyline's or Bézier's points.

Selection already walks that graph.

## Decision

`Delete(entity_ids)` removes three groups, all computed on the draft before anything is
dropped:

1. **The selection and its dependents (always removed).** These are the op's ids, plus every
   entity that references one of them, to a fixpoint. This rule is unchanged: a line loses its
   endpoint, a face loses a vertex, a solid loses its profile.
2. **The parts of the selection and of every solid that dies.** That is the `build_brep`
   children, recursively.
   - An entity that dies only because it lost a part, such as a face missing a corner, does
     **not** take its own parts with it. Deleting one corner of a square removes the face and
     the two edges at that corner, and keeps the other two edges and three points. This is the
     same as before.
   - A solid does take its parts, because it owns its profile, cap and walls.
3. **The parts that survive** are those something left in the draft still uses, and their own
   parts survive with them. Examples: an edge shared with a kept face, a point a kept line ends
   on, a circle centre that is also a beam node.

Labels do not protect a part: a labelled profile face goes with its solid. Undo restores
everything, because undo replays the log (ADR 0006), and ADR 0027 keeps a refused delete
atomic.

## Alternatives rejected

| Rejected | Why |
|---|---|
| Keep the old rule (profile survives) | That is the reported defect. An extruded box is one gesture and one object to the user |
| Cascade parts from every dependent too | Deleting one vertex would erase the whole face's edges, and a line's far endpoint. Too eager for a scratchpad edit |
| Labelled parts survive | A box tool labels both the profile and the solid (`wall_L1`, `wall_L1_solid`), so the reported case would remain |
| A second, delete-only definition of "parts" | It would drift from selection's graph (ADR 0018). One graph serves both |
| Separate "Delete solid only" / "Explode" commands now | No request yet. They can be added as their own ops when someone needs to keep a profile |

## Consequences

- Deleting a box, an extruded face or a face leaves nothing behind unless a neighbour shares
  the parts. `tests/test_delete_cascade.py` pins each case, including replay equality.
- `test_delete_solid_keeps_profile` becomes `test_delete_solid_takes_its_profile`.
- `specs/modeling-helpers.md` states the new rule and points here.
- The **Ctrl+Z** complaint has a different cause. A draw gesture posts several ops (Box sends
  `AddPoint` ×4, then `AddFace`, then `Extrude`), so undo peels them one at a time. That is
  the separate "one gesture, one op" change ADR 0024 already commits to, and it is not decided
  here.
