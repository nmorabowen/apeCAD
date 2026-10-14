# ADR 0032 — Bar layouts snap to a lattice so inclined rows stay exactly collinear

**Status:** Proposed (2026-10-14)

Settles the question PR #18 left open for plan stage C3 and apeConcrete's stage A11: exact
hull arithmetic, or a shared tolerance. Builds on [ADR 0024](0024-section-mode-rc-intent.md)
(P2, the strict hull) and [ADR 0025](0025-section-draft-contract.md) (apeConcrete re-derives
hoop rings and refuses a different one).

## Context

`Hoop.bar_ids` is the strict counter-clockwise convex hull of the hoop's bars, with
collinear bars dropped (P2). `section/geometry.convex_hull_ccw` computes it with exact
float predicates and no tolerance. That matches apeConcrete's
`shear/two_way/geometry.convex_hull`, so both repos get the same ring from the same floats.

Stage C3 adds the layout gestures `AddBarRow` and `AddBarsAlongEdge`. They interpolate bars
between two points. On a horizontal or vertical line the bars share one coordinate, so
their cross product is exactly 0. On an inclined line, plain interpolation
`a + k / n * (b - a)` rounds each bar off the line by an ulp or so. The exact predicate then
sees a middle bar either just inside, where it is dropped, or just outside, where it
survives as a hull vertex. A surviving middle bar becomes a "restrained" corner in
apeConcrete's confinement. With random inclined rows of 3 to 15 bars plus one point off the
line, plain interpolation gave a wrong hull in about two cases out of three
(`tests/test_section_rebar.py`).

There were two ways out:

- **(a)** The layout ops place inclined bars so that the exact predicate gives the
  mathematical answer.
- **(b)** Both repos use a shared collinearity tolerance in the hull.

## Decision

1. **Option (a): exact arithmetic stays, and the layout ops make it hold.** apeConcrete's
   hull and the section-draft contract are unchanged.
2. **The lattice.** An inclined layout first snaps its two ends to a grid of
   `SNAP_GRID_MM = 2**-10` mm, about 1 µm. Every bar then goes to
   `a + m * (b - a) / LATTICE_STEPS`, with `LATTICE_STEPS = 2**22` and m an integer
   (`section/layout.py`). Within `EXTENT_LIMIT_MM = 2**20` mm, about 1 km:
   - every coordinate is a multiple of 2⁻³² mm with at most 53 significant bits, so it is
     exact;
   - every difference of two bars is exact;
   - the two products of each cross product are the same real number, rounded once each,
     so they are equal.

   Any three bars of one layout therefore give a cross product of exactly 0. A bar moves
   from its ideal place by less than `SNAP_GRID_MM + length / 2**23`, which is under 2 µm
   for an 8 m row.
3. **Edge layouts share corners.** When any edge of a bar-centre ring is inclined,
   `AddBarsAlongEdge` snaps every vertex of the ring first. The corner that two edges share
   is then the same point on both, so a cage laid edge by edge is exactly collinear along
   every edge. A rotated 2000 × 300 cage of 20 bars hulls to its 4 corners. An
   axis-aligned layout is not snapped: it copies its constant coordinate, and its positions
   stay the ones the engineer typed.
4. **The extent is a refusal.** A layout that reaches beyond ±`EXTENT_LIMIT_MM` is refused,
   because the arithmetic of rule 2 is exact only within it.
5. **Scope.** The guarantee covers the bars that one layout op places, and corners shared
   through `AddBarsAlongEdge`. A bar placed with `AddBar` at hand-typed inclined
   coordinates is still the engineer's float. A row whose ends meet bars from another op
   gets no cross-op guarantee either. The `AddBarsAlongEdge` skip of a position within
   1 mm of an existing bar keeps that bar where it is.

## Alternatives rejected

| Rejected | Why |
|---|---|
| (b) A shared tolerance in both hulls | Two repos must implement one tolerance identically and forever. It changes apeConcrete's hull, which is already written and tested. It also makes "collinear" depend on scale. The section-draft contract would grow a number that every future reader must copy |
| Round positions to 0.001 mm decimals | Decimal values are not exact in binary, so the cross products still round unequally |
| Snap every bar to a grid, row or not | Moves hand-typed axis-aligned positions (60.1 mm becomes 60.0996 mm), and fixtures compared at 1e-12 against apeConcrete's declared sections would drift |
| Nudge middle bars inward | "Inward" depends on which hoop the row bounds; a row shared by two hoops has no inside |

## Consequences

- apeConcrete's A11 reader keeps its exact hull. `specs/section-draft.md` says so in a note
  outside the hashed block, so the contract hash is unchanged.
- Inclined layout positions carry long binary fractions in JSON (for example
  `1034.29364013671875`). They are exact and replay bit for bit.
- A future layout op (a hoop by rectangle, arrays along an inclined leg) must place its bars
  on the same lattice, or record why it does not.
- AddBarRow's remainder rule (centred) is ADR 0024's proposed answer to open q7. It is not
  settled here.
