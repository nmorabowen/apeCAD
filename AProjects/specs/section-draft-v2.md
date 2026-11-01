# Spec — `apeCAD.section-draft` v2

**Status:** Specified (2026-11-01); the writer, reader and fixtures are not implemented yet
**ADRs:** 0006, 0023, 0024, 0025, 0026, 0039, 0040

The one text of the v2 section-draft contract (ADR 0039 decision 1, under ADR 0025's rules).
It is the v1 contract ([`section-draft.md`](section-draft.md)) widened to general sections:
many faces with a role, circles, holes, steel shapes and circular ties. v1 is not edited and
stays written for ever; HA-04 and apeConcrete's wall reader keep it. apeConcrete ADR-0026
(stage E1) pastes the fenced block below.

## The contract

```
{ "schema": "apeCAD.section-draft", "version": 2, "units": "mm",
  "frame": {"x": "right", "y": "up", "origin": "world"},
  "producer": {"apeCAD_version": "0.1.0", "apeCAD_commit": "<sha>|null"},
  "document": {"schema": "apeCAD.document.v1", "units": "mm", "ops": [...]},
  "section": {
    "faces": [{"id", "label", "role": "concrete"|"steel"|"void", "material": "<name>"|null,
               "boundary": <boundary>|null, "holes": [<boundary>, ...],
               "shape"?: {"catalog", "designation", "anchor_mm": [x,y], "rotation_deg"},
               "template_id"?}],             # many; at a point, void > steel > concrete
    "wall_legs": [{"id", "label", "start_mm": [x,y], "end_mm": [x,y], "thickness_mm",
                   "concrete_face_id",
                   "horizontal": {"designation", "spacing_mm", "curtains"} | null,
                   "template_id"?}],                                 # optional, as in v1
    "bars": [{"id", "label", "x_mm", "y_mm", "diameter_mm", "designation",
              "material"?, "template_id"?}],
    "hoops": [{"id", "label", "bar_ids": [...], "diameter_mm", "designation",
               "spacing_mm", "hooks": "135", "template_id"?}],      # strict CCW hull (P2)
    "crossties": [{"id", "label", "bar_a_id", "bar_b_id", "diameter_mm", "designation",
                   "spacing_mm", "hooks": "135-135"|"135-90",
                   "template_id"?}],                                 # "90-90" refused
    "circular_ties": [{"id", "label", "kind": "spiral"|"hoop", "center_mm": [x,y],
                       "centerline_radius_mm", "designation", "diameter_mm", "pitch_mm",
                       "template_id"?}],        # pitch_mm: spiral pitch | hoop spacing
    "cover_guides": [{"id", "face_id", "cover_mm", "tie_diameter_mm", "bar_diameter_mm",
                      "template_id"?}],
    "templates": [{"id", "template", "template_version", "params"}],  # ADR 0040; [] until C3
    "materials_used": ["<name>", ...] },                              # sorted, unique
  "warnings": [{"code", "ids", "message"}] }

<boundary> = {"kind": "ring", "ring_mm": [[x,y],...]}   # simple; boundary CCW, hole CW
           | {"kind": "circle", "center_mm": [x,y], "radius_mm": r}   # exact
```

SHA-256 of the block's content: the text between the fences, with LF line endings and a
final newline.

```text
eb0efd21715d46bc5fdab99ac20d979ab9569de4ed8ee7ce9ea9a7e2f83ae267
```

A pasted copy is the contract only when it hashes to this value. The check takes three lines:
read the text between the fences, normalise line endings to LF, ensure one trailing newline,
and run `sha256`. A key marked `?` is optional: it is absent when it has no value (an
additive field, ADR 0025 rule 6).

## Overlap precedence (ADR 0039 decision 3)

Outside the hashed block, which states it in one comment.

- A face's **region** is the inside of its `boundary` minus the inside of each of its
  `holes`. A hole removes material from its own face only.
- At a point, the faces whose regions contain it are ranked by role:
  **`void` > `steel` > `concrete`**. The point takes the highest. A `void` leaves no material;
  a `steel` or `concrete` face gives its `material`.
- The order of `faces[]` never decides. Undo, a reorder or a replay cannot change what a
  point is made of.
- Two faces of the same role whose regions overlap are a `same-role-overlap` warning. The
  consumer decides whether to merge them or refuse.

Worked cases (the fixtures below draw them):

| Section | Faces | What the precedence gives |
|---|---|---|
| Box with a void | a concrete ring, a void ring inside it | concrete with an opening, no hole drawn on the concrete |
| SRC, W in a rectangle | a concrete ring, a steel W ring over it | the W is steel, the rest concrete; no W-shaped hole is drawn |
| CFT, round | a concrete circle, a steel circle of the outer radius with a circle hole of the inner radius | the tube wall is steel, the core concrete |
| Bare steel shape | one steel ring, no concrete | steel only |

## Ring orientation

A `boundary` ring follows v1's rule: counter-clockwise, simple, given once with no repeated
closing point. A hole ring is simple and stored **clockwise**, the opposite orientation. The
op that adds a ring normalises it (it reverses a ring given the other way), so a reader can
rely on the stored orientation and never has to fix it. Circles carry no orientation.

## Hull arithmetic (ADR 0032)

Unchanged from v1 and outside the hashed block. `hoops[].bar_ids` is the strict CCW hull
computed with exact float predicates and no tolerance; a reader re-derives it the same way.
Circular ties have no hull: which bars a `circular_ties[]` entry encloses is geometry the
consumer derives (ADR 0039 decision 5).

## Lint codes

`warnings[]` carries apeCAD's section lint, advisory and never a gate (ADR 0025 rule 6,
ADR 0039 decision 7), in this order:

1. The v1 codes that keep their meaning in v2, in v1's order: `bar-overlap`,
   `bar-outside-concrete`, `hoop-bar-not-in-face`, `crosstie-crosses-outside`,
   `face-without-cover-guide`, `inclined-wall-leg`, `tie-mismatch-in-core`.
2. The seven v2 codes:

| Code | Warns when |
|---|---|
| `same-role-overlap` | two faces of the same role have overlapping regions |
| `hole-outside-face` | a hole is not strictly inside its face's boundary |
| `void-outside-solid` | a void face's region is not covered by a concrete or steel face |
| `bar-in-void` | a bar centre lies where a void face wins |
| `bar-in-steel` | a bar centre lies where a steel face wins |
| `circular-tie-outside-face` | a circular tie's centreline is not inside a concrete face |
| `steel-shape-unresolved` | a steel face carries a `shape` but no ring (`boundary` is null). Only imported or seed content can raise it: `AddSteelShape` always requires a ring (Errata 6) |

`more-than-one-solid-face` and `face-without-wall-leg` are v1-only (ADR 0039 Errata 2): a v2
draft never carries them. Many faces are normal in v2, and a face without a leg is a wall
question the consumer asks only when the drawing is a wall (ADR 0039 decision 6).

## Rules

- Designations come from the closed vocabulary (ADR 0024 P12, ADR 0039 decision 9), for bars,
  hoops, crossties and circular ties alike. apeConcrete trusts the designation and refuses a
  `diameter_mm` that does not match it.
- `material` is a **name**, on faces and (optionally) bars. apeCAD stores no property and no
  law; the consumer binds the name (ADR 0039 decision 2).
- A circle is exact. apeCAD never tessellates it for the contract; the consumer chooses how to
  mesh it (ADR 0039 decision 2).
- apeCAD never resolves a steel `shape.designation`. The host resolves it and passes the ring
  in the op (`AddSteelShape`, ADR 0039 decision 4). Mirroring a face that carries `shape` is
  refused by name, because the provenance would be wrong for an asymmetric shape (Errata 7).
- `cover_guides` is drawing intent and `hooks` are intent, as in v1.
- A consumer reads the geometry from the entities, never by re-expanding `templates[]`
  (ADR 0040 decision 7).
- Version rule (ADR 0025 rule 6): an optional field added is additive and keeps `version` 2;
  a meaning changed bumps it.

## Field by field

All lengths are millimetres, in world coordinates (x right, y up, z = 0). Ids are apeCAD
entity ids (positive integers) and stay stable across replay. Rows not listed (`frame`,
`producer`, `warnings[]`) are as in v1.

| Path | Type | Meaning | Who checks |
|---|---|---|---|
| `schema`, `version` | `"apeCAD.section-draft"`, `2` | Contract id and version; a reader that does not know `2` refuses it by name | both |
| `units` | `"mm"` | The only unit | both |
| `document` | object | The full ops log, `apeCAD.document.v1`, the same as in a v1 draft. Only the derived `section` block differs | apeCAD on reopen |
| `section.faces[]` | list, any count | `{id, label, role, material, boundary, holes}`, plus optional `shape` and `template_id` | apeCAD (rings simple and oriented) |
| `faces[].role` | `"concrete"`, `"steel"`, `"void"` | Decides overlaps, by precedence `void` > `steel` > `concrete`. A v1 `ConcreteFace` (live role `"solid"`) is written as `"concrete"` (Errata 3) | consumer |
| `faces[].material` | string or null | A name. Null on a `void` face, which has no material (Errata 6) | consumer binds it |
| `faces[].boundary` | boundary or null | `{"kind": "ring", "ring_mm"}`: CCW and simple. `{"kind": "circle", "center_mm", "radius_mm"}`: exact, `radius_mm` > 0. Null only on a steel face with a `shape` that arrived unresolved in an imported draft or a seed (`steel-shape-unresolved`, Errata 6) | apeCAD (ring); consumer refuses null when it needs the region |
| `faces[].holes[]` | list of boundaries | Same two kinds; a hole ring is stored CW. Each strictly inside its own face (`hole-outside-face`). Removes material from that face only. Holes carry no id | apeCAD lint; consumer |
| `faces[].shape` | object, optional, steel faces only | Provenance: `catalog`, `designation`, `anchor_mm`, `rotation_deg` (degrees, CCW). Stored and shown, never resolved by apeCAD. A plate or a built-up shape has none | host |
| `section.wall_legs[]` | list, optional content | Exactly as in v1. `concrete_face_id` names a `faces[]` entry | consumer, only for a wall |
| `section.bars[]` | list | As in v1, plus optional `material`, the bar steel's name; absent means the consumer's default | consumer |
| `section.hoops[]`, `section.crossties[]` | list | Exactly as in v1 (polygon hoops on the strict CCW hull; crossties between two bars) | as in v1 |
| `section.circular_ties[]` | list | `kind` `"spiral"` or `"hoop"`; centre `center_mm`; `centerline_radius_mm` > 0; `designation`, `diameter_mm`; `pitch_mm` is the pitch of a spiral and the spacing of a hoop. The enclosed bars are not listed: the consumer derives them | apeCAD (positive lengths); consumer |
| `section.cover_guides[]` | list | As in v1. `face_id` names a `faces[]` entry | apeCAD only |
| `section.templates[]` | list | `{id, template, template_version, params}` (ADR 0040 decision 7). Always present; empty until stage C3 emits it (Errata 4, 5) | display only |
| `*.template_id` | entity id, optional | On a template child: the id of its `templates[]` entry. Absent on freehand entities | display only |
| `section.materials_used` | list of strings | The sorted, de-duplicated names of every face `material` and bar `material` present. Nulls are not listed. The bar default is not listed | host that binds names |

## Designation vocabulary

Unchanged: v1's closed metric list (`Ø8` to `Ø32`), [`section-draft.md`](section-draft.md)
"Designation vocabulary". US bars stay additive later (ADR 0039 decision 9).

## Seed (`apeCAD.section-seed` v2)

The v2 `section` block with 0-based list indices in place of entity ids (ADR 0025
decision 7), under the same header as seed v1 with `"version": 2`:

```json
{
  "schema": "apeCAD.section-seed",
  "version": 2,
  "units": "mm",
  "frame": {"x": "right", "y": "up", "origin": "world"},
  "section": {
    "faces": [
      {"label": null, "role": "concrete", "material": "concrete",
       "boundary": {"kind": "circle", "center_mm": [0.0, 0.0], "radius_mm": 300.0}, "holes": []}
    ],
    "wall_legs": [],
    "bars": [{"label": null, "x_mm": 240.0, "y_mm": 0.0, "diameter_mm": 20.0, "designation": "Ø20"}],
    "hoops": [],
    "crossties": [],
    "circular_ties": [{"label": null, "kind": "spiral", "center_mm": [0.0, 0.0],
                       "centerline_radius_mm": 255.0, "designation": "Ø10", "diameter_mm": 10.0,
                       "pitch_mm": 75.0}],
    "cover_guides": [{"face_id": 0, "cover_mm": 40.0, "tie_diameter_mm": 10.0, "bar_diameter_mm": 20.0}]
  }
}
```

- `concrete_face_id` in `wall_legs[]` and `face_id` in `cover_guides[]` are 0-based indices
  into `section.faces[]`.
- `bar_ids` in `hoops[]` and `bar_a_id` / `bar_b_id` in `crossties[]` are 0-based indices
  into `section.bars[]`.
- Items omit their own `id` (or carry a 0-based index the reader ignores), as in seed v1.
- A seed carries no `templates[]`, no `template_id` and no `materials_used`. A seed replays
  into plain entities (ADR 0040 Context, option 2); `materials_used` is derived (Errata 5).
- apeCAD alone turns a seed into ops. A seed reader validates the header, every 0-based
  cross-reference, and `diameter_mm` against `designation` (rel 1e-9), as for seed v1.

## Writer and reader (planned, C1-S3)

Outside the hashed block, so the contract is unchanged. Names follow v1's table in
[`section-draft.md`](section-draft.md) "Writer and reader".

- `section_draft(document, *, version=1, commit="auto")`. `version=2` writes this block.
  `version=1` writes v1 and is refused by name when the document holds anything v1 cannot
  say: a second face, a void or steel face, a circle, a hole, a circular tie. It never drops
  entities to fit (ADR 0039 decision 1).
- Hosts ask for v2 explicitly. The transport's `action: "draft"` and the MCP and CLI
  `get_section_draft` take an optional `version`, 1 or 2, default 1, so HA-04 is unchanged.
  Any other value is refused by name (Errata 1).
- `document_from_draft` reads v1 and v2, replays `document` and recomputes `section`, with
  v1's reopen rules: a length beyond rel 1e-9 is one `reopen-numeric-difference` warning per
  item and the replay wins; anything else that differs is refused, including a role, a
  boundary of another kind, the number of holes, a material, a `shape`, a template id. A
  stored key the reader does not write is ignored. The stored `warnings[]` are not compared.
- An unknown `schema` or `version`, or `units` other than `"mm"`, is refused.
- Lists are in entity-id order; every length is written as a float.

## Fixtures (planned, C1-S3)

`tests/fixtures/section_draft_v2/<name>.json`, generated by a script (`REGENERATE=1`, as for
v1) and compared at rel 1e-12, written with `apeCAD_commit: null`. apeConcrete copies them at
a pinned apeCAD sha (its ADR-0026). ADR 0039 decision 8:

| Fixture | Checks |
|---|---|
| `rect_column_ties` | one concrete ring, bars, a polygon hoop and crossties |
| `circular_column_spiral` | a concrete circle, bars on a circle, a `spiral` circular tie |
| `box_with_void` | a concrete ring with a void face inside; `void` > `concrete` |
| `t_beam` | a non-convex concrete ring, top and bottom bars, stirrups |
| `src_w_in_rect` | a steel W ring with `shape` provenance over a concrete ring; `steel` > `concrete` |
| `cft_round` | a concrete circle under a steel circle with a circle hole |
| `bare_w_shape` | one steel face, no concrete, no bars |
| `rect_boundary_hoops` | v1's wall fixture written as v2: v1 and v2 describe the same wall |
