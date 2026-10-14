# Spec — `apeCAD.section-draft` v1

**Status:** Proposed (2026-10-09)
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

## Seed (`apeCAD.section-seed` v1)

The same `section` block with list indices in place of ids, under
`{"schema": "apeCAD.section-seed", "version": 1, "units": "mm", "section": {...}}`.
apeConcrete writes it; apeCAD alone turns it into ops (plan stage C10). The field-level text is
written when C10 starts, by amending this spec.

## Fixtures

`tests/fixtures/section_draft/{rect_boundary_hoops, l_wall_two_hoops, c_wall_crossties,
inclined_outline}.json`, generated by `tests/_section_fixtures.py` (`REGENERATE=1`) and
compared at rel 1e-12. apeConcrete pins a copy at an apeCAD sha (its stage A11).
