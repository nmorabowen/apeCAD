# Spec — `apeCAD.section-draft` v1

**Status:** Implemented (2026-10-23)
**ADRs:** 0006, 0023, 0024, 0025, 0026

The one text of the section-draft contract (ADR 0025, plan decision P1). apeConcrete
ADR-0025 D8 and ape-web-tools ADR-0006 D4 paste the fenced block below. Its source is
ape-web-tools `docs/ha04-editor-plan.md` §4.1 at `f71e3e2`, and it was copied byte for byte.

## The contract

```
{ "schema": "apeCAD.section-draft", "version": 1, "units": "mm",
  "frame": {"x": "right", "y": "up", "origin": "world"},
  "producer": {"apeCAD_version": "0.1.0", "apeCAD_commit": "<sha>|null"},
  "document": {"schema": "apeCAD.document.v1", "units": "mm", "ops": [...]},
  "section": {
    "concrete_faces": [{"id", "label", "material", "role": "solid", "ring_mm": [[x,y],...]}],   # CCW, simple, exactly 1 in v1
    "wall_legs": [{"id", "label", "start_mm": [x,y], "end_mm": [x,y], "thickness_mm",
                   "concrete_face_id",
                   "horizontal": {"designation", "spacing_mm", "curtains"} | null}],
    "bars": [{"id", "label", "x_mm", "y_mm", "diameter_mm", "designation"}],
    "hoops": [{"id", "label", "bar_ids": [...], "diameter_mm", "designation",
               "spacing_mm", "hooks": "135"}],                       # strict CCW hull (P2)
    "crossties": [{"id", "label", "bar_a_id", "bar_b_id", "diameter_mm", "designation",
                   "spacing_mm", "hooks": "135-135"|"135-90"}],      # "90-90" refused
    "cover_guides": [{"id", "face_id", "cover_mm", "tie_diameter_mm", "bar_diameter_mm"}] },
  "warnings": [{"code", "ids", "message"}] }
```

SHA-256 of the block's content: the text between the fences, with LF line endings and a
final newline.

```text
8ee75d0ee7d4054a575e0f4d669872c828057ba6ebdfa4b8355d87f454a1181f
```

A pasted copy is the contract only when it hashes to this value. The check takes three lines:
read the text between the fences, normalise line endings to LF, ensure one trailing newline,
and run `sha256`.

## Hull arithmetic (ADR 0032)

Outside the hashed block, so the contract is unchanged. `hoops[].bar_ids` is computed with
exact float predicates and no tolerance, and a reader re-derives it the same way: no
collinearity tolerance is part of v1. apeCAD's layout ops (`AddBarRow`,
`AddBarsAlongEdge`) place inclined rows on a dyadic lattice, so the bars of one row are
exactly collinear in floats and a middle bar is never a hull vertex. A consumer reads
`x_mm` and `y_mm` as written and needs nothing more.

## Lint codes (stage C3)

`warnings[]` carries apeCAD's section lint (`apeCAD/section/lint.py`, `LINT_CODES`), in this
order: `bar-overlap`, `bar-outside-concrete`, `hoop-bar-not-in-face`,
`crosstie-crosses-outside`, `face-without-cover-guide`, `face-without-wall-leg`,
`inclined-wall-leg`, `tie-mismatch-in-core`, `more-than-one-solid-face`. `Document.section_lint()`
returns them; they are advisory (ADR 0025 rule 6).

## Rules (plan §4.1, verbatim)

- Designations come from the closed vocabulary (P12). apeConcrete trusts the designation and refuses a `diameter_mm` that does not match it.
- `cover_guides` is drawing intent. The translator ignores it, because clear cover is derived (ADR-0025 D4).
- `hooks` are intent. apeConcrete stores them as optional and ignores them in v1.
- Version rule: an optional field added is additive; a meaning changed bumps `version`.
- `apeCAD.section-seed` v1 is the same `section` block with list indices in place of ids. apeConcrete emits it, and apeCAD alone turns it into ops (C10).

## Field by field

All lengths are millimetres, in world coordinates (x right, y up, z = 0). Ids are apeCAD
entity ids (positive integers) and stay stable across replay.

| Path | Type | Meaning | Who checks |
|---|---|---|---|
| `schema`, `version` | `"apeCAD.section-draft"`, `1` | Contract id and version; any other pair is refused | both |
| `units` | `"mm"` | The only unit | apeConcrete refuses others |
| `frame` | object | Fixed: x right, y up, world origin. apeConcrete maps `y_from_top = -y_world` | apeConcrete |
| `producer.apeCAD_version` | string | `apeCAD.__version__` when written (0.1.0 from the first v1 writer) | provenance only |
| `producer.apeCAD_commit` | string or null | Git sha of the writer when known | provenance only |
| `document` | object | The full ops log, `apeCAD.document.v1`. The source of truth (ADR 0006) | apeCAD on reopen |
| `section.concrete_faces[]` | list, exactly 1 in v1 | `ring_mm` is CCW and simple, given once with no repeated closing point. `role` is `"solid"`; `"void"` is reserved. `material` is a name, not a law | apeCAD (simple, CCW); apeConcrete (count) |
| `section.wall_legs[]` | list | The axis from `start_mm` to `end_mm`, `thickness_mm`, the owning `concrete_face_id`, and `horizontal` = `{designation, spacing_mm, curtains}` or null | apeConcrete refuses a face without a leg, and an inclined leg (P4) |
| `section.bars[]` | list | Centre `x_mm`, `y_mm`; `diameter_mm` matching `designation` | apeConcrete refuses a mismatch (P12) |
| `section.hoops[]` | list | `bar_ids`: the strict CCW convex hull of the enclosed bars, collinear bars dropped (P2); `diameter_mm`, `designation`, `spacing_mm`, `hooks` (`"135"`) | apeCAD computes; apeConcrete re-derives and refuses a different ring |
| `section.crossties[]` | list | Two distinct bar ids, tie size and spacing; `hooks` is `"135-135"` or `"135-90"`, and `"90-90"` is refused | both |
| `section.cover_guides[]` | list | Drawing intent for snapping and lint. The translator ignores it; clear cover is derived | apeCAD only |
| `warnings[]` | list | `{code, ids, message}` from apeCAD's lint and reopen. Advisory; never gate on it | — |

## Designation vocabulary (v1)

Copied from apeConcrete `src/apeConcrete/rebar/bars.py` `METRIC_BARS`, in its canonical
spelling (`f"Ø{d:g}"`):

| Designation | `diameter_mm` |
|---|---|
| Ø8 | 8 |
| Ø10 | 10 |
| Ø12 | 12 |
| Ø14 | 14 |
| Ø16 | 16 |
| Ø18 | 18 |
| Ø20 | 20 |
| Ø22 | 22 |
| Ø25 | 25 |
| Ø28 | 28 |
| Ø32 | 32 |

US bars (`#3` to `#18`) are not in v1. Adding them is additive (rule: an optional field or
value added keeps the version).

## Seed (`apeCAD.section-seed` v1, stage C10)

The same `section` block with 0-based list indices in place of entity ids, under:

```json
{
  "schema": "apeCAD.section-seed",
  "version": 1,
  "units": "mm",
  "frame": {"x": "right", "y": "up", "origin": "world"},
  "section": {
    "concrete_faces": [{"label": null, "material": "concrete", "role": "solid", "ring_mm": [[x, y], ...]}],
    "wall_legs": [{"label": null, "start_mm": [x, y], "end_mm": [x, y], "thickness_mm": 300.0,
                   "concrete_face_id": 0,
                   "horizontal": {"designation": "Ø12", "spacing_mm": 250.0, "curtains": 2}}],
    "bars": [{"label": null, "x_mm": x, "y_mm": y, "diameter_mm": 16.0, "designation": "Ø16"}],
    "hoops": [{"label": null, "bar_ids": [0, 1, 2, 3], "diameter_mm": 10.0, "designation": "Ø10",
               "spacing_mm": 100.0, "hooks": "135"}],
    "crossties": [{"label": null, "bar_a_id": 0, "bar_b_id": 2, "diameter_mm": 10.0, "designation": "Ø10",
                   "spacing_mm": 100.0, "hooks": "135-90"}],
    "cover_guides": [{"face_id": 0, "cover_mm": 25.0, "tie_diameter_mm": 10.0, "bar_diameter_mm": 16.0}]
  }
}
```

- `concrete_face_id` in `wall_legs[]` and `face_id` in `cover_guides[]` are 0-based indices into `section.concrete_faces[]`.
- `bar_ids` in `hoops[]` and `bar_a_id` / `bar_b_id` in `crossties[]` are 0-based indices into `section.bars[]`.
- Items in `concrete_faces[]`, `wall_legs[]`, `bars[]`, `hoops[]`, `crossties[]`, and `cover_guides[]` omit their own `id` (or carry a 0-based index that `document_from_section_seed` ignores).
- `document_from_section_seed(seed)` validates `schema == "apeCAD.section-seed"`, `version == 1`, `units == "mm"`, `frame` (when given), all 0-based cross-references, and `diameter_mm` against `designation` (rel 1e-9), then replays the section into a fresh `Document` (`AddSectionOutline`, `AddWallLeg`, `SetLegReinforcement`, `SetCover`, `AddBar`, `AddHoop`, `AddCrosstie`).
- `section_seed(document)` projects a `Document` into `apeCAD.section-seed` v1, mapping entity ids to 0-based indices in entity-id order.
- `apeCAD.scratchpad.transport.handle` accepts `action: "seed"` with `payload` set to a seed dict, and `action: "load"` also accepts `payload.schema == "apeCAD.section-seed"`.

## Writer and reader (stages C4 & C10)

Outside the hashed block, so the contract is unchanged.

| Name | Home | Does |
|---|---|---|
| `DRAFT_SCHEMA`, `DRAFT_SCHEMA_VERSION`, `project_section(entities)`, `compare_sections` | `apeCAD/section/draft.py` | The draft block from the entities, and the P9 comparison. Takes entities, never the `Document` (the `section/` layering rule) |
| `SEED_SCHEMA`, `SEED_SCHEMA_VERSION`, `project_seed_section(entities)`, `require_seed_header` | `apeCAD/section/seed.py` (re-exported in `apeCAD/section/draft.py`) | The seed block and header validation (ADR 0025 Decision 8) |
| `section_block(document)`, `section_draft(document, *, commit="auto")`, `document_from_draft(draft)`, `section_seed(document)`, `document_from_section_seed(seed)` | `apeCAD/section_draft.py` | The same over a `Document`. It sits above `document.py`, and nothing below imports it (`tests/test_architecture.py`) |
| `get_section_draft` tool, `GET /api/section/draft` | `agent/tools.py`, `scratchpad/server.py` | `{ok, revision, draft}`, read-only |

- Lists are in entity-id order. Rings are the stored ones, which the ops keep CCW (faces) and
  the strict CCW hull from the lowest (x, y) (hoops). Every length is written as a float.
- `producer.apeCAD_commit` is `APECAD_COMMIT` when set, else the HEAD of the git checkout the
  package runs from (an editable install), else null.
- `document_from_draft` replays `document` and recomputes `section`. Lengths (`ring_mm`,
  `start_mm`, `end_mm`, `*_mm` numbers) that differ beyond rel 1e-9 give one warning per item,
  `{code: "reopen-numeric-difference", ids: [id], message}`; the replay wins. Anything else that
  differs is refused: an id missing or extra in a list (also an id under another kind), a
  ring of another length, hoop membership or order, designations, labels, hooks, curtains,
  `horizontal` null against an object. A stored key the reader does not write is ignored, so
  an additive field (rule 6) still reopens. The stored `warnings[]` are not compared.
- An unknown `schema` or `version` (including `true` or `"1"`), or `units` other than `"mm"`,
  is refused.

## Fixtures

`tests/fixtures/section_draft/{rect_boundary_hoops, l_wall_two_hoops, c_wall_crossties,
inclined_outline}.json`, generated by `tests/_section_fixtures.py` (`REGENERATE=1`) and
compared at rel 1e-12. apeConcrete pins a copy at an apeCAD sha (its stage A11).

They are written with `apeCAD_commit: null`, so their bytes depend on the code alone; the sha
A11 pins is the merge commit that adds them.

| Fixture | Drawn as | Checks |
|---|---|---|
| `rect_boundary_hoops` | apeConcrete `tests/fixtures/walls/rect_300x3000.json`: a 3000 × 300 wall chain (leg Ø12 @ 250, 2 curtains), cover 25 / tie 10 / bar 16; 18 Ø16 bars per 600 mm end at apeConcrete's exact `x_from_left`, with `y_world = -y_from_top`; hoop Ø10 @ 100 per end; 14 Ø12 web bars | apeConcrete's `legs_y = 4` drawn as two crossties per end, at the third and fifth bar of the long faces (`legs_x = 2` is the hoop alone) |
| `l_wall_two_hoops` | An L wall chain, a hoop of two 4-bar rows at each free end | Two legs, two hoops |
| `c_wall_crossties` | A C wall chain, leg steel only on the web, a 10-bar hoop in the web with three `135-90` crossties | `horizontal: null` and an object; crossties |
| `inclined_outline` | A wall chain at 30°, caged with `AddBarsAlongEdge` on all four edges (ADR 0032) | Lattice positions; the hoop hulls to 4 corners; `inclined-wall-leg` in `warnings` |
