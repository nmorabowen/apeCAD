# ADR 0039 — `apeCAD.section-draft` v2: general sections with many faces, roles, circles and spirals

**Status:** Accepted (2026-10-31)

Builds on [ADR 0024](0024-section-mode-rc-intent.md) (section mode) and
[ADR 0025](0025-section-draft-contract.md) (the v1 contract and its versioning rule). Its
consumer is apeSection, a new desktop app for section assessment (apeSection ADR-0001), read
through apeConcrete ADR-0026. Companions: [ADR 0040](0040-parametric-section-templates.md)
(templates) and [ADR 0041](0041-section-results-overlay.md) (results overlay).

## Context

v1 was cut for one consumer, HA-04's wall page. Its shape says so:

- `concrete_faces[]` holds **exactly one** solid face; `role: "void"` is reserved (P3).
- Every face is a polygon ring. A circular column would be a tessellated polygon, and the
  consumer could not tell a 32-gon from a circle.
- Transverse steel is a hoop around the strict hull of its bars, plus crossties. There is no
  spiral and no circular hoop.
- Nothing but concrete and bars can be drawn. A steel shape inside concrete (SRC), a filled
  tube (CFT) or a bare steel section has no entity.
- `wall_legs[]` is required by apeConcrete's wall reader, which refuses a face without one.

The owner's interview of 2026-10-31 asks apeSection to assess columns (rectangular, circular,
polygon), walls of any shape, hollow sections, beams and T-beams, SRC and CFT composites and
bare steel shapes, drawn freehand, from templates or from an import. Every item above blocks
some of that.

ADR 0025 rule 6 says an added optional field keeps `version` 1 and a changed meaning bumps it.
A void face, a second solid face and a steel face all change what "the section's concrete
area" means to a v1 reader. That is a changed meaning.

## Decision

1. **A new contract, `apeCAD.section-draft` v2, in its own spec.** The text lives in
   `specs/section-draft-v2.md` with its own SHA-256, under ADR 0025's rules (one home, a
   pasted copy that hashes differently is not the contract). v1 is not edited and stays
   written for ever: HA-04 and apeConcrete's wall reader keep it.
   - `section_draft(document, *, version=1 | 2)`. Version 1 is refused by name when the
     document holds anything v1 cannot say (a second face, a void, a circle, a steel face, a
     spiral). It never drops entities to fit.
   - `document_from_draft` reads v1 and v2. The `document` part (the ops log, ADR 0006) is the
     same `apeCAD.document.v1` in both; only the derived `section` block differs.
   - `apeCAD.section-seed` v2 is the v2 block with list indices in place of ids, as in ADR
     0025 decision 7. apeCAD alone turns a seed into ops.
2. **`faces[]` replaces `concrete_faces[]`.** Many faces, each
   `{id, label, role, material, boundary, holes}`:
   - `role` is `"concrete"`, `"steel"` or `"void"`.
   - `material` is a **name** (as in v1). apeCAD stores no property and no law; the
     consumer binds the name.
   - `boundary` is `{"kind": "ring", "ring_mm": [[x, y], ...]}` (CCW, simple, as in v1) or
     `{"kind": "circle", "center_mm": [x, y], "radius_mm": r}`. A circle is exact; the
     consumer chooses how to mesh it.
   - `holes[]` is a list of boundaries of the same two kinds, each strictly inside its face.
     A hole removes material from its own face only.
3. **Where faces overlap, the role decides, never the order.** A point belongs to the face of
   highest precedence among those that contain it: `void` > `steel` > `concrete`. A void cuts
   every face under it. A steel face laid on a concrete face displaces the concrete, so SRC
   is a W-shaped steel face drawn over a rectangle, with no W-shaped hole to draw. A CFT is a
   concrete circle under a steel circle that has a hole of the inner radius. Two faces of the
   same role that overlap are a lint warning (`same-role-overlap`). The consumer decides
   whether to merge them or refuse.
4. **Steel shapes are faces that carry their provenance.** A steel face may carry
   `shape = {catalog, designation, anchor_mm, rotation_deg}`. apeCAD stores and draws the
   ring it is given and never resolves a designation. The host resolves it (apeSection asks
   apeSteel) and passes the outline in the op (`AddSteelShape`), so apeCAD gains no dependency.
   A plate or a built-up shape is a plain steel face with no `shape`.
5. **Circular transverse steel.** A new `circular_ties[]` entry is
   `{id, label, kind, center_mm, centerline_radius_mm, designation, diameter_mm,
   pitch_mm}`. `kind` is `"spiral"` or `"hoop"`. For a spiral, `pitch_mm` is the pitch; for a
   hoop, it is the spacing. Which bars it encloses is geometry, so the consumer derives it, as
   apeConcrete ADR-0025 D4 does for a hull hoop. Polygon hoops and crossties are unchanged
   from v1.
6. **Optional fields beside the v1 ones.**
   - `bars[].material` is the bar steel's name. When it is absent, the consumer's default
     applies.
   - `bars[].template_id` and the same field on every other section entity, filled by ADR 0040.
   - `wall_legs[]` stays exactly as in v1 and stays optional. A face without a leg is a
     wall-lint warning only when the drawing is a wall; the consumer decides.
   - `materials_used`: the sorted set of material names, for a host that binds them.
7. **Lint keeps its rule: advisory, never a gate** (ADR 0025 rule 6). New codes:
   `same-role-overlap`, `hole-outside-face`, `void-outside-solid`, `bar-in-void`,
   `bar-in-steel`, `circular-tie-outside-face`, `steel-shape-unresolved` (a `shape` with no
   ring).
8. **Fixtures.** `tests/fixtures/section_draft_v2/`: `rect_column_ties`,
   `circular_column_spiral`, `box_with_void`, `t_beam`, `src_w_in_rect`, `cft_round`,
   `bare_w_shape`, plus `rect_boundary_hoops` written as v2, to check that v1 and v2 describe
   the same wall. They are generated by a script and compared at rel 1e-12, like v1's.
   apeConcrete copies them at a pinned sha (its ADR-0026).
9. **The vocabulary is unchanged.** Bar designations stay ADR 0024's closed list. US bars are
   still additive later.

## Alternatives rejected

| Rejected | Why |
|---|---|
| Extend v1 with optional fields and keep `version` 1 | A v1 reader that ignores `role: "void"` or a second face computes the wrong area and does not know it. ADR 0025 rule 6 is exactly this case |
| Edit v1's block in place | Recorded HA-04 runs hold v1 drafts for years (ADR 0025, P9) |
| Order-based overlap (last face drawn wins) | Undo or a reorder would change the mechanics. Role precedence is stable and readable |
| Holes only, no `void` role | An SRC or CFT void, or a duct through several faces, would need a matching hole in each face. A void face says it once |
| Tessellate circles inside apeCAD | The consumer cannot tell a circle from a polygon, and a mesh-size choice belongs to mechanics, not drawing |
| apeCAD resolves `W14x90` from a catalog | That would need apeSteel inside apeCAD, or a copied catalog that drifts. The host resolves it and apeCAD stores what it was given |
| Spirals as a hoop with a flag | A spiral is defined by centre, radius and pitch, not by a hull of bars; the hull rules (P2) do not apply |
| A separate "general section document" type | ADR 0024 already rejected a second document type: one ops log, one undo, one transport |

## Consequences

- New entities and ops in `entities.py`, `ops/section.py` and `draft/section.py`: a general
  `SectionFace` (role, boundary, holes), `CircularTie`, and ops `AddSectionFace`,
  `AddFaceHole`, `AddSteelShape`, `AddCircularTie`, `AddBarsOnCircle`. Each gets the five
  ADR 0023 steps and an op-catalog entry (ADR 0028), so agents draw them through MCP the day
  they land.
- `ConcreteFace` stays for v1 and HA-04. A v2 projection reads both kinds (a `ConcreteFace`
  is a `role: "concrete"` ring face).
- The 2-D client draws circles, holes, voids and steel faces, with each role styled through
  ADR 0031's design system tokens.
- apeConcrete's wall reader (`io/apecad.py`) keeps v1 and refuses v2 by name. Its general
  reader is new (apeConcrete ADR-0026).
- `AGENTS.md`'s cross-repo table and `memory/coupling-map.md` gain apeSection as a consumer.

## Errata (2026-11-01)

Recorded while writing [`specs/section-draft-v2.md`](../specs/section-draft-v2.md)
(apeSection#25, stage C1-S1). The Decision above is unchanged. These points record one owner
ruling and the apeSection program orchestrator's rulings where the Decision text left a
question open.

1. **Hosts request v2 explicitly (owner's ruling, "Explicit version arg").** The transport's
   `action: "draft"` and the MCP and CLI `get_section_draft` take an optional `version`, 1 or
   2, default 1; any other value is refused by name. A host that asks for nothing still gets
   v1, so ape-web-tools HA-04 is unchanged. This carries decision 1's
   `section_draft(document, *, version=1 | 2)` to the hosts.
2. **`more-than-one-solid-face` and `face-without-wall-leg` apply to v1 drafts only.** Many
   faces are normal in v2, and decision 6 makes a face without a leg a question the consumer
   asks only for a wall. A v2 draft carries the other seven v1 codes and the seven of
   decision 7.
3. **The live `FaceRole "solid"` maps to the v2 role `"concrete"`.** A v1 `ConcreteFace`
   (`entities.py`, role `"solid"`) is written in v2 as a `role: "concrete"` ring face with no
   holes. v1 drafts keep writing `"solid"`.
4. **`template_id` is declared here and emitted by ADR 0040 (stage C3).** The v2 block
   declares the optional `template_id` on every section entity now, so the contract's hash
   does not move when templates land. Until C3, no entity carries it.
5. **`templates[]` is declared with it, and a seed carries neither (orchestrator's ruling).**
   ADR 0040 decision 7 adds `templates[] = {id, template, template_version, params}` to the v2
   block. The block declares it now: always present, and empty until C3. `apeCAD.section-seed`
   v2 carries no `templates[]`, no `template_id` and no `materials_used`. A seed replays into
   plain entities (ADR 0040 Context, option 2), and `materials_used` is derived.
6. **Two nulls (orchestrator's ruling).** A `void` face has `material: null`: it has no
   material. A steel face with a `shape` may have `boundary: null` only in a draft or seed
   that arrives unresolved. The `AddSteelShape` op always requires a ring, so
   `steel-shape-unresolved` (decision 7, "a `shape` with no ring") fires only on imported or
   seed content. Every other face has a boundary.
7. **Ring orientation and mirroring (orchestrator's ruling).** A `boundary` ring follows v1's
   rule: CCW and simple. A hole ring is stored with the opposite orientation (CW), and the op
   that adds a ring normalises it. The contract block states both. Mirroring a face that
   carries steel `shape` provenance is refused by name, because the stored `designation`,
   `anchor_mm` and `rotation_deg` would describe the wrong outline for an asymmetric shape.
8. **Five readings from the review of apeCAD PR #48 (orchestrator's rulings).** The spec
   states each one outside its hashed block, so the contract's SHA-256 is unchanged.
   1. *A steel face with no ring.* Seed v2 refuses a designation-only steel face, by name:
      the host resolves the outline before it seeds. With `AddSteelShape` requiring a ring,
      no path writes `boundary: null`, so `steel-shape-unresolved` is retired as a
      **reserved** code that is never emitted. This supersedes the `boundary: null` half of
      point 6. The block still admits null, and a reader refuses it by name.
   2. *`version=1` and v2-only fields.* A document whose bars carry `material`, or whose
      entities carry `template_id`, is refused by name for `version=1`, the same as a v2-only
      entity. Fields are never dropped to fit.
   3. *The kept v1 codes on many faces.* `face-without-cover-guide` applies to concrete faces
      only. A bar gets one location code at most, by precedence `bar-in-void` >
      `bar-in-steel` > `bar-outside-concrete`. A hole, which has no entity id, is identified
      as `(face_id, hole_index)`, the pair the hole ops record (C1-S2).
   4. *`material` on solid faces.* Required and non-null on `concrete` and `steel` faces;
      only a `void` face has null, and `SetMaterial` refuses a void (C1-S2).
   5. *`shape.anchor_mm`.* The point, in section coordinates, where the shape's catalog
      origin (its centroid) is placed. Reopen compares it as a length (warn beyond rel 1e-9),
      not structurally.
9. **Two readings from review gate RGc1 (apeSection#39, stage C1-S5).** The spec states each
   one outside its hashed block, so the contract's SHA-256 is unchanged.
   1. *"A second face" means a second v2 face.* Decision 1's and the spec's refusal of "a
      second face" for `version=1` concerns v2 faces: every `AddSectionFace` or
      `AddSteelShape` face is refused for v1 anyway. Two v1 `ConcreteFace`s keep writing v1
      with the `more-than-one-solid-face` warning, so HA-04 is unchanged.
   2. *The CFT-core exemption.* `face-without-cover-guide` does not fire for a concrete face
      that lies wholly inside a hole of a steel face (touching or equal to the hole counts as
      inside): a CFT core is confined by the tube and has no cover to draw. A concrete face
      not under a steel face's hole still raises it, holes of its own or not. The
      `cft_round` fixture loses its one warning; no other fixture changes.
