# ADR 0042 — DXF import to a section-seed v2: strict, in apeCAD, behind the `dxf` extra

**Status:** Accepted (2026-11-26), by the owner's ruling at the apeSection program's
acceptance gate 1 (apeSection#9 on the office Forgejo, comment 6417; quoted under "Ruling"
below). The owner merges this record.

Builds on [ADR 0034](0034-dxf-export.md) (the DXF writer, its `dxf` extra and its layers),
[ADR 0039](0039-section-draft-v2-general-sections.md) (section-draft and section-seed v2),
[ADR 0040](0040-parametric-section-templates.md) Errata 16–18 (exact ring predicates and
lesson #53's two-sided oracle), [ADR 0030](0030-one-gesture-one-op.md) (the 1 mm vertex
reuse) and [ADR 0023](0023-module-boundaries.md) (the 600-line budget).

## Context

apeSection (its ADR-0001 §6, phase 2) imports sections from DXF and ETABS. Its ADR-0005 §2
names one verb for it, `section_import` (DXF, ETABS, seed), which its host-api §8.6 reserves.
apeSection places no geometry (its ADR-0001 §2), so DXF entities must become faces and bars
here. Today apeCAD writes DXF (`render/dxf.py::export_dxf`) and reads none. Read at
`2e1a0a8`:

- **The seed is the existing door.** `section_draft.py::document_from_section_seed` replays an
  `apeCAD.section-seed` v1 or v2 as section-mode ops, and the transport's `seed` action
  (`scratchpad/transport.py::_seed`) exposes it under `MAX_OPS` (2000). A seed carries no
  `templates[]` (ADR 0039 Errata 5). Each face, hole and bar replays as one op.
- **Replay merges vertices.** `draft/state.py::DraftState.point_at` reuses any point within
  1 mm (`dx² + dy² + dz² <= 1`) that is not a bar's or a template's. Two DXF vertices closer
  than that do not replay as read.
- **v2 has no arcs.** A boundary is a ring (CCW, simple) or an exact circle, and a hole is a
  ring (stored CW) or a circle strictly inside its face (ADR 0039 decision 2, Errata 7).
- **The bar vocabulary is closed.** `section/designations.py::DESIGNATIONS` is Ø8 to Ø32,
  with no US bars. US `#5` is 15.875 mm, 0.125 mm from Ø16, so a loose snap would swap them
  silently.
- **The extent is bounded.** `section/layout.py::EXTENT_LIMIT_MM` is 2^20 mm.
- **What the writer draws.** Each section role has its layer (`render/style.py::SECTION_STYLE`):
  `CONCRETE-CUT`, `STEEL-CUT`, `VOID` and `BAR`.
  - A face is an LWPOLYLINE or a native CIRCLE on its role's layer, and its holes are further
    outlines on the **same** layer (`render/dxf.py::_write_face`). Its fill is a HATCH on a
    separate fill layer.
  - A void adds a WIPEOUT on `VOID`. A void with holes is refused on export
    (`_refuse_void_holes`; apeSection#59 item 2, which the program's survey had miscited as
    "apeCAD #59").
  - A bar is a CIRCLE plus a solid HATCH on `BAR`. Hoops, crossties, circular ties, legs,
    cover guides and tags have their own layers.
  - `$INSUNITS` is 4 (mm).
- **Holes are therefore read from nesting,** a float predicate. Lesson #53 requires that any
  new one be decided exactly, with a two-sided oracle. `section/templates/hole_rules.py`
  already decides region interiors and clearances in `fractions.Fraction` on the stored floats
  (`_interior`, `_clear_region`, `exact_simplicity_fault`, `exact_twice_area`). It is at 595
  of its 600 lines.
- **There is no geometry kernel** (ADR 0004): no union, offset or repair.
- **The extra exists.** `pyproject.toml` declares `dxf = ["ezdxf>=1.3,<2"]`. Without it,
  `render/dxf.py::DxfUnavailableError` answers `UNAVAILABLE`, and CI's `core` job proves the
  stdlib-only core.

## Decision

1. **apeCAD reads DXF into an `apeCAD.section-seed` v2 and a report, with ezdxf behind the
   existing `dxf` extra.**
   - The entry point is `dxf_import.py::import_dxf(data: bytes, *, layers=None, units=None,
     arc_chord_mm=None) -> DxfImport{seed, report}`. It sits above `document.py`, as
     `section_draft.py` does, and imports ezdxf lazily.
   - Its pure core, `section/dxf_seed.py`, takes the entities ezdxf read and builds the seed;
     it never imports ezdxf.
   - `import apeCAD` never loads ezdxf. Without the extra, `import_dxf` answers `UNAVAILABLE`,
     naming the extra, and never falls back.
   - The import never touches a document. The host replays the seed through the transport's
     `seed` action, or `document_from_section_seed`.
   - Only model space is read. Bytes ezdxf cannot read are refused as `dxf unreadable`;
     IMP-1a pins whether a binary DXF is read or refused so.
2. **The default layer map is the writer's own layers, so apeCAD's export round-trips.**
   - `CONCRETE-CUT` → `concrete` (material `"concrete"`), `STEEL-CUT` → `steel` (material
     `"steel"`), `VOID` → `void`, `BAR` → `bar` (material null).
   - `layers`, when given, **replaces** the map. Each entry is
     `name → {role, material?, designation?}`, with `role` one of `concrete`, `steel`,
     `void`, `bar`. Names match case-insensitively. Two names that match each other, an
     unknown role or a designation outside `DESIGNATIONS` is `INVALID_ARGUMENT`.
   - A `bar` entry may name a designation, which then applies to every circle on that layer.
   - Every other layer is unmapped: its entities are counted and never read.
3. **What is read, on mapped layers.**
   - On face layers: a closed LWPOLYLINE or a closed 2-D POLYLINE becomes a ring, and a
     CIRCLE an exact circle.
   - On the bar layer: a CIRCLE is a bar at its centre (decision 7).
   - Coordinates go from the entity's OCS to WCS, and z is dropped. An entity whose extrusion
     is not ±Z is refused.
   - Skipped and counted: HATCH, WIPEOUT, TEXT, MTEXT, DIMENSION, LEADER and POINT. Nothing
     else is skipped.
4. **Units are never guessed.** `units` wins, then `$INSUNITS` when it is 1 (in), 2 (ft),
   4 (mm), 5 (cm) or 6 (m), scaled by the exact factors 25.4, 304.8, 1, 10 and 1000. With
   neither, the import is refused as `dxf no-units`, and the host asks. When `units` and
   `$INSUNITS` disagree, `units` wins and the report warns.
5. **Arcs are refused unless tessellation is asked for.** A polyline with a bulge on a
   mapped layer is refused as `dxf arc`, naming its handle. With `arc_chord_mm`, its bulges
   are flattened to chords within that sagitta, and the report lists each tessellated
   entity. An ARC entity is refused as `dxf arc` either way: alone it never closes a ring, and
   LINE and ARC chaining is not read (decision 15). A polyline with a width (a donut, a thick
   line) is refused as `dxf width` either way.
6. **Rings of one role are disjoint, strictly nested, or refused.**
   - Each pair of rings and circles of the same role is decided **exactly**, on the scaled
     floats, with `hole_rules`'s region tests: disjoint (`_clear_region` at gap 0), one in the
     interior of the other (`_interior`), or else contact, refused as `dxf ring-contact`
     naming both handles. No second interior test is written.
   - Even nesting depth is a face and odd depth a hole of the face around it. Depth 2 is a new
     face (an island).
   - A hole is read from its face's own layer. A ring at odd depth on another layer of the
     same role is refused as `dxf hole-layer`, because the material it removes would be a
     guess.
   - A VOID ring nested in another is refused as `dxf nested-void` (the writer has no holed
     void to round-trip, apeSection#59).
   - Rings of different roles may overlap; ADR 0039 decision 3's precedence applies.
7. **A circle is a bar only within 0.01 mm of a bar size, or by its layer's designation.**
   - When the bar layer names a designation, it applies, and the report counts each circle
     whose drawn diameter differs from it by more than 0.01 mm.
   - Otherwise a circle of drawn diameter d is designation D when |d − D| ≤ 0.01 mm
     (`BAR_TOLERANCE_MM`, a constant, not an argument). For d in [D/2, 2D] the float
     subtraction is exact (Sterbenz), so the test is exact on the scaled float. Designations
     are at least 2 mm apart, so at most one matches.
   - Anything else is refused as `dxf bar-size`, naming the diameter and the handle. US
     `#5` (15.875 mm) is refused, never read as Ø16.
   - The seed's bar carries D's diameter, the circle's centre and the layer's `material`.
8. **Each ring is checked exactly before it is stored.** Its exact simplicity and orientation
   (`exact_simplicity_fault`, `exact_twice_area`) must agree with
   `section/geometry.py::is_simple` and `signed_area` on its stored order, as ADR 0040
   Errata 16.1 requires of template holes. A ring that is not simple, has zero area, or on
   which they disagree is refused as `dxf ring-not-simple`. Faces are stored CCW and holes CW
   (ADR 0039 Errata 7).
9. **Every seed replays to itself.** Every returned seed `s` satisfies
   `section_seed(document_from_section_seed(s), version=2) == s`. Otherwise the import is
   refused as `dxf replay-mismatch`, naming the vertex the 1 mm reuse merged. Vertices exactly
   1.0 mm apart merge, so they are refused; at the next float above 1.0 mm they are kept.
10. **Nothing on a mapped layer is dropped silently.** Each entity on a mapped layer is read,
    skipped as decision 3 lists, or refused, naming its type, layer and handle. An INSERT,
    LINE, SPLINE, ELLIPSE, 3-D polyline or open polyline is refused. `report.layers[]` lists
    every layer of the file with its count per entity type and its role (or null), and the
    counts sum to the model-space total. A file with no face or bar read is refused as
    `dxf no-geometry`.
11. **Caps are counted before the work they bound.** 8 MiB of input before parsing; 2 000
    mapped entities and 20 000 vertices before any geometry. Exceeding one is `TOO_LARGE`. One
    mapped entity becomes at most one op, so a seed within the cap fits the transport's
    `MAX_OPS`.
12. **Coordinates are kept as drawn.** A point outside `EXTENT_LIMIT_MM` is refused as
    `dxf extent`. No origin is moved.
13. **Determinism.** The same bytes and arguments give the same seed and report, byte for
    byte.
14. **Refusals use the existing codes only,** each message starting `dxf <reason>:` and naming
    the handle and layer where there is one:

    | Reason | Code |
    |---|---|
    | the `dxf` extra is missing | `UNAVAILABLE` |
    | a bad `layers`, `units` or `arc_chord_mm` argument | `INVALID_ARGUMENT` |
    | `too-large` | `TOO_LARGE` |
    | `unreadable`, `no-units`, `entity-unsupported`, `tilted`, `open-outline`, `arc`, `width`, `ring-not-simple`, `ring-contact`, `hole-layer`, `nested-void`, `bar-size`, `extent`, `no-geometry`, `replay-mismatch` | `REFUSED` |

    A new reason needs an erratum to this record. No new error code is added.
15. **Not read in v1:** hoops, ties, crossties, circular ties and spirals, legs, cover guides,
    labels and text, materials beyond the layer map, steel shape provenance, blocks, LINE or
    ARC chaining, SPLINE, ELLIPSE, and hatch-only faces. A steel face imports as a plain steel
    ring.
16. **No new op and no contract change.**
    - No op is added, so `catalog/`, `ops/section.py` and `draft/dispatch.py` are untouched.
    - `apeCAD.document.v1`, section-draft v1 and v2, section-seed v1 and v2,
      `TRANSPORT_VERSION` 1, the client API and the section overlay are byte-equal before and
      after.
    - The report is tool output, not an `apeCAD.*` contract. It grows only by additive keys.
17. **ETABS is not apeCAD's** (owner ruling 2). ETABS section import lives in apeSection. It
    reads `.e2k` through apeETABS's offline reader, with no COM, and maps each column to one
    `rect_column` or `circular_column` `AddSectionTemplate` request, so the parameters stay
    editable. apeCAD gains no ETABS vocabulary and imports no sibling. Live COM is deferred.
    The ETABS axis convention, shared with apeSection's demand adapter, is apeSection's to fix.

## Alternatives rejected

| Rejected | Why |
|---|---|
| apeSection reads the DXF and builds the seed or ops | Breaks apeSection ADR-0001 §2: nesting and bar placement are drawing. The layer table would be copied and drift |
| `import_dxf` returns catalog ops, or a draft | Ops: ids are allocated at apply, so a hole cannot name its face in the same batch, and there is nothing to self-check against. A draft: the host re-derives it anyway |
| A stdlib DXF reader | OCS, R12 POLYLINE and binary DXF by hand: the fragility ADR 0034 rejected for writing |
| A new `section/nesting.py` with its own interior test | Two interior tests in apeCAD that can disagree. `hole_rules` already decides it exactly |
| A unitless DXF read as mm with a 50 mm–50 m sanity check (apeConcrete's wall reader) | A guess. A 100 × 100 column drawn in cm reads as 100 × 100 mm and passes the window; the UI asks instead |
| A bar sized from 2r at `REL_TOL`, or snapped within a loose tolerance | `REL_TOL` refuses a hand-drawn 15.999; a loose snap reads `#5` as Ø16. 0.01 mm is stated and exact |
| A caller-set bar tolerance | It would reopen the snap the ruling closed |
| Bulges flattened silently at a fixed chord error | A silent change of the drawn geometry |
| Same-role overlaps only linted, with holes from void layers only | apeCAD's own export, and every usual hollow drawing, would import as two solids with the wrong area |
| ETABS parsed in apeCAD | A second e2k reader, ETABS words in a drawing library HA-04 consumes, and an axis map kept apart from apeSection's demands |
| ETABS mapped to a seed | The template parameters are lost at the first edit (ADR 0040 Context) |
| Live ETABS over COM | Untestable in the gates (licence, Windows session); an `.e2k` export covers the need |

## Consequences

- **New modules:** `dxf_import.py` and `section/dxf_seed.py`. `test_architecture.py` guards
  them as it guards `section_draft.py` (`test_section_draft_sits_above_the_document`):
  nothing below `dxf_import.py` imports it, and nothing but `dxf_import.py` imports ezdxf
  for reading.
- **`hole_rules.py` is locked by IMP-1a.** The interior and gap-0 clearance tests become
  public names. At 595 of 600 lines, the slice may first move the region predicates to a
  sibling module as a pure move under the same lock; the decisions they make do not change.
- **The round-trip oracle.** For every v2 fixture `export_dxf` accepts,
  `import_dxf(export_dxf(F))` gives back F's faces (role, ring or circle, holes) and each
  bar's centre and designation. They match bitwise, or at rel 1e-12 where ezdxf's float text
  does not round-trip; the slice measures that and states it. Labels, materials, steel shape
  provenance and decision 15's entities are not compared. A holed void cannot be exported
  (apeSection#59 item 2), so it has no round-trip case.
- **CI.** The `core` job asserts that `import_dxf` answers `UNAVAILABLE`. The gate legs
  install `dxf` already.
- **Agent surfaces** (IMP-1b): `import_dxf` becomes a tool (local, attach, MCP) and the CLI
  command `import-dxf`, listed in `AProjects/specs/agent-surface-mcp.md` and AGENTS.md. The
  three surfaces return the same seed and report.
- **Cross-repo.** AGENTS.md's contracts table and `AProjects/memory/coupling-map.md` gain the
  `import_dxf` seam, consumed by apeSection. apeSection pins `apeCAD[dxf]`, so ezdxf enters
  its install; its layering test keeps ezdxf out of `apeSection`.
- **Open work this meets.** If apeCAD#85 (B6, inputs refused by name at every entry point)
  lands first, the new entry points use its guard.

## Slices

| Slice | Repo | Owns | Lock | Size |
|---|---|---|---|---|
| ADR 0042 | apeCAD | this record and its index row; the owner merges it | none | S |
| IMP-1a | apeCAD | `section/dxf_seed.py`, `dxf_import.py`, the `hole_rules.py` public names (or the pure move); `tests/test_dxf_import{,_core,_fuzz}.py`, `tests/_dxf_import_truth.py`, `tests/fixtures/dxf_import/make_fixtures.py` (fixtures built by script); `tests/test_architecture.py` | `hole_rules.py` | M |
| IMP-1b | apeCAD | `agent/{tools,local,attach,mcp_tools}.py`, `cli.py`, the MCP spec, AGENTS.md, the coupling map; 3 tests | none | S |
| PIN | apeSection | `pyproject.toml` (`apeCAD[dxf]` at the IMP-1b merge), `PINS`, the pin test | pin | S, no gate |
| IMP-2a | apeSection | the `section_import` verb for `dxf` and `seed` (`etabs` answers `UNAVAILABLE`), HOST_API 1.11 additive, the additive `sections[].source` project-v1 key (ruling 4) | the verb registry | M |
| IMP-2b | apeSection | the web import dialog | web | S–M |
| IMP-3 | apeSection | the ETABS adapter in `apeSection.imports`, through apeETABS (pinned `etabs` extra) | the verb registry | M |

Order: ADR 0042, IMP-1a, IMP-1b, PIN, IMP-2a, IMP-2b. IMP-3 waits for apeSection's ADR-0001
erratum (gate 4, shared with its demand adapter D2) and the owner's `.e2k` fixtures
(ruling 3).

**IMP-1a oracles.**

- **(a) Decision 6, lesson #53's two-sided fuzz.** Gaps of −1, −0.01, 0, +0.01 and +1 mm and
  the nearest floats either side of contact; grids of 0.01 to 5 mm; offsets of 0, 0.1, 1234.5
  and 40000.3; coordinates built as `i/10` and as `i*0.1`. The truth is written in `Fraction`
  in `tests/_dxf_import_truth.py`, which imports no product geometry. The counts in both
  directions are reported, and the fuzz fails if a float test replaces the exact one.
- **(b) Decision 7** at D ± 0.01 mm and at the neighbouring floats of each bound.
- **(c)** The three rings of ADR 0040 Errata 18.4 are refused (decision 8).
- **(d) Decision 9.** Vertices exactly 1.0 mm apart are refused; at the next float above
  1.0 mm they are kept.
- **(e) Fault files, each refused by name:** no units; an open polyline; a bulge; an ARC; a
  donut; an INSERT on `BAR`; touching rings; crossing rings; a bow-tie; a hole on another
  layer of its role; a nested VOID; a 24.9 mm circle; `#5`; a point out of extent; each cap.
  An inch file (× 25.4) and an OCS-mirrored circle (x negated) import correctly.
- **(f)** The round trip of Consequences.
- **(g)** The `core` job answers `UNAVAILABLE`.

**IMP-1b oracle.** The tool, the MCP body and the CLI return the same seed and report.

## Ruling

The owner answered the four questions of acceptance gate 1 on 2026-11-26, relayed verbatim
in apeSection#9, comment 6417:

1. *Accept apeCAD ADR 0042: DXF → section-seed v2 in apeCAD, strict (units never guessed,
   arcs refused unless tessellation is asked for, bars within 0.01 mm or a layer
   designation, every seed self-replaying), with no new op?* — **"Accept (Recommended)".**
   The comment records the acceptance as also covering apeCAD's writer layers as the default
   map and that nothing on a mapped layer is dropped silently.
2. *ETABS section import moves from apeCAD to apeSection, through apeETABS's offline `.e2k`
   reader, as `rect_column` / `circular_column` template requests, with live COM deferred?*
   — **"Move to apeSection (Recommended)".**
3. *Will you commit real ETABS 21/22 `.e2k` exports with column rebar, and table exports for
   demands?* — **"Yes, I'll provide them (Recommended)".** Until they arrive, IMP-3 is
   blocked on the owner; the DXF slices proceed.
4. *A `sections[].source` provenance key, additive in project v1, accepted with this gate?*
   — **"Accept, additive (Recommended)".**

## Errata (2026-11-26): the import caps are lowered

Recorded after review round 1 of IMP-1a (apeCAD PR #87; apeSection#373, comment 6501), which
found the import's time quadratic in the counts decision 11 caps. The Decision text above is
kept as accepted; this erratum replaces decision 11's two geometry caps and nothing else.
Code is cited at apeCAD d4d93d4 by `path::symbol`, with paths under `src/apeCAD/`.

1. **The geometry caps are 2,000 vertices and 500 mapped entities (owner's ruling, quoted
   under "Ruling" below).** Decision 11 now reads: 8 MiB of input before parsing (unchanged);
   **500** mapped entities and **2,000** vertices before any geometry.
   1. *The names stay.* `section/dxf_seed.py::MAX_MAPPED_ENTITIES` becomes 500 (was 2000)
      and `MAX_VERTICES` 2000 (was 20000). `section/dxf_options.py::MAX_BYTES` is unchanged.
   2. *What they count is unchanged.* Mapped entities are the entities on mapped layers that
      decision 3 does not skip: face rings and circles, which are the shapes nesting
      (decision 6) relates pairwise, and bar circles. The ruling's "nested entities" is this
      count; bars are in it, as before, so it bounds the input of `_nest` from above.
      Vertices are polyline vertices on mapped layers, and the chords that `arc_chord_mm`
      adds count as each bulge is flattened (`_tessellate`), before any ring is checked.
   3. *Refused by name, as before.* A larger drawing is refused `TOO_LARGE`, its message
      starting `dxf too-large:` and naming the count found and the cap. No reason and no
      code is added (decision 14).
   4. *Counted before any geometry, as before.* Both counts are checked before any ring is
      checked for simplicity, any pair is nested and any seed is replayed, so a refused file
      costs only its parse.
   5. *Within the transport.* One mapped entity is at most one op, so a seed within the cap
      is at most 500 ops, a quarter of the transport's `MAX_OPS` (2000).
2. **How the caps relate to the measurements.** IMP-2a's target is 3 s for one import, the
   stall bound of apeSection's host-api v1 §7 item 5. Times are wall times of `import_dxf`,
   parse, core and replay together (decision 9), one run each, with the caps lifted.
   1. *The review's measurements (comment 6501, at apeCAD 3a62c90),* for one ring: 2,000
      vertices about 2.4 s, 8,000 about 36 s, and 20,000, the old cap, about 228 s. Time
      grows with the square of the vertex count, mostly in the shared float
      `section/geometry.py::is_simple`. Nesting grows with the square of the shape count in
      `section/dxf_seed.py::_nest`: 2,000 concentric circles take about 22 s.
   2. *Re-measured at d4d93d4 for this erratum,* on the office workstation, Python 3.11.15:
      one ring of 1,000, 2,000 and 4,000 vertices, 0.61 s, 2.39 s and 9.35 s; 250, 500 and
      1,000 concentric circles, 0.39 s, 1.55 s and 6.23 s; a 1,996-vertex ring around 499
      bars, 2.57 s; a 1,500-vertex ring around 499 circular holes, 2.28 s.
   3. *What the caps meet.* 2,000 is the largest round vertex count whose single ring meets
      3 s (2.4 s; 4,000 takes 9 s). 500 is where concentric circles, the review's nesting
      case, take 1.55 s, about a sixteenth of 2,000's 22 s, as the quadratic law gives. One
      outline at the caps with its holes or bars stays under 3 s: a 1,996-vertex ring with
      499 bars takes 2.57 s, and a 1,500-vertex ring with 499 circular holes 2.28 s.
   4. *What they do not meet: many nested rings.* Rings are related exactly in
      `fractions.Fraction` (decision 6), and a ring pair costs far more than a circle pair,
      most where the coordinates are not short binary fractions. Measured at d4d93d4, N
      concentric squares, 4 vertices each:
      - axis-aligned, N = 500 (the two caps at once): 6.9 s, also 7.1 s with every
        coordinate offset by 1234.5;
      - rotated 30°: N = 100, 2.82 s; 150, 6.33 s; 200, 11.35 s; 500, 70.4 s;
      - 125 concentric 16-gons (2,000 vertices): 3.25 s.

      So the caps hold the target for one outline with its holes and bars, and do not hold it
      for a drawing of more than about 100 nested rings. Such a drawing is not a section
      (decision 6 reads even depth as faces and odd depth as holes), but the caps admit it.
      The owner rules at this record's merge whether the caps stand so, or a ring count is
      added by a further erratum.
3. **Raised only by a further erratum.** The caps may be raised, or a cap added, only by an
   erratum to this record that cites new measurements, once faster checks land: an
   `is_simple` below quadratic, and a nesting that decides fewer pairs exactly. No slice
   raises them on its own.
4. **The code lands in its own slice, before IMP-1b.** IMP-1b first exposes `import_dxf` to
   agents and the CLI, so the lowered caps land before it, in a slice that owns
   `section/dxf_seed.py`'s two constants and the cap tests of
   `tests/test_dxf_import{,_core}.py`. Its oracles:
   - each cap at its bound is read, and one above it is refused `TOO_LARGE` with
     `dxf too-large:`, before any geometry (a file over the entity cap whose rings cross is
     refused `too-large`, not `ring-contact`);
   - a bulge whose chords pass 2,000 vertices is refused while it is tessellated;
   - the cases of items 2.2 to 2.4 are re-timed at the slice's head and the times stated in
     its PR; a test asserts the counts and refusals, never a wall time, which CI's machines
     would make flaky.

   The Slices table gains a row:

   | Slice | Repo | Owns | Lock | Size |
   |---|---|---|---|---|
   | IMP-1c (caps) | apeCAD | `section/dxf_seed.py`'s `MAX_MAPPED_ENTITIES` and `MAX_VERTICES`; the cap tests | none | S |

   The order becomes: ADR 0042, IMP-1a, this erratum, IMP-1c, IMP-1b, PIN, IMP-2a, IMP-2b.

### Ruling

The owner answered on 2026-11-26, relayed verbatim in apeSection#9, comment 6533, item 3
("ADR 0042 import caps"): **"Lower to ~2,000 / ~500 (Recommended)".** The comment records:
the caps become about 2,000 vertices and about 500 nested entities; a larger drawing is
refused by name; this is an ADR 0042 erratum PR in apeCAD, owner-merged, landing before
IMP-1b.
