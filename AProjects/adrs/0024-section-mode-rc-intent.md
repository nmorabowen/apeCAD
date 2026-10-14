# ADR 0024 — Section mode: RC section entities are drawing intent; apeConcrete owns the mechanics

**Status:** Accepted (2026-10-14). Proposed 2026-10-09; accepted by the owner on 2026-10-14

Amends [ADR 0002](0002-spatial-scratchpad.md) for one consumer: an RC section draft is the
source of truth for that section's geometry and reinforcement layout, not only an
explanation.

## Numbering

The cross-repo plan, ape-web-tools `docs/ha04-editor-plan.md` §3 at `f71e3e2`, reserved apeCAD
**0020** for this record. It reserved 0021 for the contract and 0022 for the transport. Those
numbers were already taken on `main`: 0020 (agent surface) and 0021 (`--root`) landed on
2026-09-25, and 0022 (CI) and 0023 (module boundaries) on 2026-10-09. The records therefore
land as:

| Plan number | Record | This repo |
|---|---|---|
| 0020 | Section mode | **0024** (this ADR) |
| 0021 | `apeCAD.section-draft` v1 contract | **[0025](0025-section-draft-contract.md)** |
| 0022 | Stateless transport and 2-D section client | **[0026](0026-section-transport-and-client.md)** |

The documents that cite the plan numbers must be corrected in their own repos. They are
ape-web-tools ADR-0006 ("Related" row and D4), the plan's §3 and §6 C0, and apeConcrete
ADR-0025 (status line, D8 and Consequences).

## Context

HA-04 is the ape-web-tools wall page. Its owner decided on 2026-10-03 (plan §1.1, O1–O7)
that walls are **drawn**, not declared:

- The Geometria tab becomes a CAD section editor, and drawing from scratch comes first (O3).
- Confinement is derived from the hoops the engineer draws (O4).
- apeCAD is the editor. apeCAD never imports apeConcrete (O5).
- The drawing is saved with every run and is the source of truth; apeConcrete's
  `WallSectionDocument` is recomputed from it (O6).

ADR 0002 calls a draft an *explanation artifact*, with analysis truth living in the apeGmsh
script. That framing does not fit a section that an engineer designs from. The draft needs new
entity kinds, and their meaning needs a single owner.

## Decision

1. **Section mode is a set of entity kinds and ops in the same document**, not a second
   document type. The kinds are `ConcreteFace`, `WallLeg`, `Bar`, `Hoop`, `Crosstie` and
   `CoverGuide`. They are frozen dataclasses in the `Entity` union, with ops that replay,
   undo, round-trip, cascade-delete and transform like every other op (ADR 0006).
2. **Intent only, no mechanics.** apeCAD stores what was drawn: outlines, legs with their
   horizontal steel, bar positions and designations, hoops as rings of bar ids, crossties,
   cover guides and materials as names. It runs no ACI check, no Mander model and no fiber
   section. It never computes confinement. Cores, restrained bars, hx, Ash and every design
   number belong to apeConcrete (its ADR-0025).
3. **One gesture is one composite op.** Examples are an outline, a wall chain, a bar row, bars
   along an edge, or a hoop by selection. One undo removes the gesture, and the log stays short
   because the transport replays it on every call (ADR 0026).
4. **Rules the document enforces, from the plan's P-decisions:**
   - **Hoop ring (P2).** `Hoop.bar_ids` is the *strict* counter-clockwise convex hull of the
     selected bars, with collinear bars dropped. It is computed from positions, so selection
     order does not matter. Fewer than 3 hull vertices is refused.
   - **One solid face (P3).** `ConcreteFace.role` is `"solid"` only, and `"void"` is
     reserved for a later version. A T or L wall is one polygon. A second solid face is
     a lint warning, not a refusal.
   - **Legs carry steel (P4).** `WallLeg` carries `horizontal = {designation, spacing_mm,
     curtains}` or null. A face without a leg, and an inclined leg, are lint warnings in
     apeCAD. apeConcrete's reader is the gate that refuses them.
   - **Closed vocabulary (P12).** `Bar`, `Hoop`, `Crosstie` and leg-steel designations come
     from a list copied from apeConcrete `rebar/bars.py` `METRIC_BARS`, in its canonical
     spelling: `Ø8`, `Ø10`, `Ø12`, `Ø14`, `Ø16`, `Ø18`, `Ø20`, `Ø22`, `Ø25`, `Ø28`, `Ø32`.
     Anything else is a `DocumentError`. A test checks the copy (ADR 0025). The catalog's US
     bars (`#3` to `#18`) are left out of v1, and adding them later is additive.
5. **Bars own their points.** `AddBar` always allocates a fresh, unlabelled `Point` and never
   reuses a coincident one through `DraftState.point_at` (1 mm tolerance). Two bars may sit
   closer than that, and the lint reports `bar-overlap`.
6. **Plane and frame.** A section lives on the z = 0 plane, x right and y up, in world
   millimetres. apeConcrete flips y on its side (`y_from_top = -y_world`).
7. **Kernel-free geometry (ADR 0004 stands).** Signed area, `ensure_ccw`, `is_simple`, strict
   convex hull, miter offset (refusing a flip or a self-intersection) and outline chaining are
   plain Python. They live in a new `apeCAD/section/` package beside `draft/`, as ADR 0023
   requires. The section handlers are one more family module, `draft/section.py` (rank 3), with
   one `HANDLERS` row per op.
8. **Graph integration.**
   - Deleting a bar cascades to the hoops and crossties that use it, and deleting a face
     cascades to its legs and cover guide.
   - Mirror, rotate and arrays clone section entities with their points.
   - `Document.brep()` lists them, the scene payload ships them, and the 3-D client draws bars
     at minimum.
   - `to_frame()` excludes bar points; a bar is not a frame node.
9. **Schema v1.** `SCHEMA_ID` moves from `apeCAD.document.v0` to `apeCAD.document.v1` when the
   first section op lands. A new `SUPPORTED_SCHEMA_IDS` reads both. v1 is a superset: a v0 log
   is a valid v1 log. Writing v1 is a cross-repo change (`AGENTS.md`, "Cross-repo
   contracts": apeSketch routes `.ape.json` files by `schema`).

## Alternatives rejected

| Rejected | Why |
|---|---|
| A separate "section document" type | Splits undo, the transport, JSON and the B-rep index into two worlds. The kinds are small, and the dispatch table (ADR 0023) takes new rows cheaply |
| apeCAD computes cores, hx or Mander | Duplicates apeConcrete's mechanics, and the two would drift. O5 forbids the import, and copying the rules is worse |
| Hoops as polylines of points | Loses which bars are enclosed and which are restrained. apeConcrete needs bar ids (P2) |
| Hoop ring in the user's click order | Selection order would change the stored ring and the restrained set. The strict hull is deterministic |
| Refuse a face without a leg inside apeCAD | A modal refusal breaks typed drawing (plan §7, issue 2). The translator is the gate, and the editor warns |
| Voids in v1 | `WallSectionDocument` has one simple outline (P3). Reserved as `role: "void"` |
| Shapely or another kernel for offsets | ADR 0004. Miter offsets of simple polygons need no kernel, and no consumer uses one |

## Consequences

- apeCAD gains its first consumer whose *design numbers* depend on the draft. Contract
  discipline follows in ADR 0025: version constants, fixtures pinned at a sha, and a reader
  that refuses rather than guesses.
- ADR 0002 still holds for every other draft. Section mode is the exception, because O6 makes
  the drawing the source of truth.
- The founding "a service to apeConcrete, later" (`memory/founding-intent.md`) becomes now.
  `memory/coupling-map.md` gains the apeConcrete and ape-web-tools rows.
- Implementation follows plan stages C1–C3 (entities and ops, geometry, layout ops and lint),
  re-pathed to `ops/`, `draft/section.py` and `apeCAD/section/`.

## Owner decisions (2026-10-14)

The owner accepted this record and confirmed the proposed answers to the open questions from
the plan's §9. The plan's decisions P1–P15 that this record relies on are signed with it.

- **Several disjoint solid faces** (coupled piers, q5) stay a lint warning in v1
  (`more-than-one-solid-face`). apeConcrete's reader refuses them.
- **Cover guide** (q6): clear cover is measured to the outside of the transverse bar
  (ACI §20.5.1.3).
- **`AddBarRow` remainder** (q7): centred.
- **Curves** (arc edges, circular hoops) **and openings** stay out of scope for HA-04 (q14).
