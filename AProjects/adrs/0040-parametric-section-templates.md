# ADR 0040 — Parametric section templates are composite ops that keep their parameters in the log

**Status:** Accepted (2026-10-31)

Builds on [ADR 0006](0006-one-source-of-truth.md) (the ops log is the one source of truth),
[ADR 0024](0024-section-mode-rc-intent.md) (one gesture, one composite op),
[ADR 0028](0028-agent-surface-mcp.md) (the op catalog) and
[ADR 0039](0039-section-draft-v2-general-sections.md) (section-draft v2).

## Context

apeSection (its ADR-0001) asks for parametric templates beside freehand drawing: a
rectangular column from `b`, `h`, cover and bar counts, a circular column with a spiral, a
box, a T-beam, an SRC or CFT column. The engineer edits `b` and the drawing follows. The
engineer can also leave the template and keep editing by hand.

There are three places the parameters could live:

1. **In the apeCAD log**, as a composite op that remembers them.
2. **In apeConcrete**, which builds the section and sends a seed (ADR 0025 decision 7).
3. **In the host app**, which keeps the parameters and regenerates apeCAD ops on each change.

Option 2 loses the parameters: a seed becomes plain ops. Option 3 makes the app a second
writer of the log, the case ADR 0006 and ADR 0025 decision 7 refuse. It would also give the
section two sources of truth (the app's parameters and the log), which can drift apart.

A template is pure geometry: outline, holes, bar positions, ties. It needs no mechanics, so
it fits ADR 0024 decision 2.

## Decision

1. **A template is one composite op, `AddSectionTemplate{template, template_version,
   params}`.** It expands deterministically into ordinary section entities (faces, bars,
   hoops, crossties, circular ties, cover guides). Every child records the template entity's
   id as `template_id`, and the template entity keeps its `params`.
2. **Editing a template is one op, `EditSectionTemplate{template_id, params}`.** It deletes
   the children and expands again. The edit is atomic (ADR 0027), undo is one step, and replay
   reproduces the same ids, because allocation is deterministic.
3. **Template children are locked.** An op that edits, deletes or moves a template child is
   refused (`TEMPLATE_LOCKED`). So is a new entity that references one, such as a user
   crosstie between two template bars. To customise, the engineer either
   - changes the template's parameters (the patterns cover the usual crosstie and spiral
     layouts), or
   - runs `ExplodeSectionTemplate{template_id}`. That clears `template_id` from the children,
     drops the template entity, and leaves a freehand drawing. There is no "re-implode".
4. **Expansion functions are versioned and kept for ever.** `template_version` is part of the
   op. A change to how a template expands adds a version and keeps the old function, so a log
   recorded years ago replays to the same drawing (ADR 0025, P9). A test replays one frozen
   log per template version.
5. **The first catalog.** Each template is a module under `apeCAD/section/templates/` of at
   most 600 lines (ADR 0023):

   | Template | Parameters (all mm, designations from the closed list) |
   |---|---|
   | `rect_column` | `b`, `h`, `cover`, `nx`, `ny`, `bar`, `corner_bar?`, `tie`, `tie_spacing`, `crossties: "none" \| "all" \| "alternate"` |
   | `circular_column` | `diameter`, `cover`, `n_bars`, `bar`, `tie_kind: "spiral" \| "hoop"`, `tie`, `pitch` |
   | `polygon_column` | `ring`, `cover`, `bar`, `spacing_max`, `tie`, `tie_spacing` (bars along every edge, ADR 0032) |
   | `rect_hollow` | `b`, `h`, `t_x`, `t_y`, `cover`, `bar`, `spacing_max`, `tie`, `tie_spacing` |
   | `t_beam` | `bw`, `h`, `bf`, `hf`, `cover`, `bottom`, `top`, `slab_bars`, `stirrup`, `stirrup_spacing` |
   | `src_column` | a `rect_column`'s parameters + `steel_shape` (outline and provenance passed in by the host, ADR 0039 §4) |
   | `cft_round`, `cft_rect` | outer size, wall `t`, steel and concrete material names |

   Walls keep `AddWallChain` (ADR 0024), which is already one gesture. A wall template can be
   added later.
6. **Every template is in the op catalog** (ADR 0028), with a JSON Schema derived from its
   parameter dataclass. An agent lists the templates, fills in the parameters, and calls
   `apply_op`. The parameters are the agent's entire interface; it never has to compute a bar
   position.
7. **The draft shows templates.** The v2 `section` block gains
   `templates[] = {id, template, template_version, params}`, and children carry `template_id`
   (ADR 0039 §6). A consumer may show "Rectangular column 400×600" but must read the
   geometry from the children, never re-expand the parameters itself.

## Alternatives rejected

| Rejected | Why |
|---|---|
| The host app keeps the parameters and regenerates ops | A second writer of the log (ADR 0006), and two sources of truth that can drift |
| apeConcrete builds the section and sends a seed | The parameters are lost at the first edit. apeConcrete would also own drawing logic, and two repos would place bars |
| Unlocked children (edit a template bar in place, re-expand later) | A re-expansion would silently undo the user's edit, or the merge rules would become a second editor. Explode is explicit |
| Keep only the latest expansion code | An old run would replay to a different drawing (P9) |
| Templates in the client (JS) | The ops log is Python-side and replayed by the transport (ADR 0026). The client posts the op, and agents and the CLI get the same templates |

## Consequences

- New entity `SectionTemplate`, ops `AddSectionTemplate`, `EditSectionTemplate` and
  `ExplodeSectionTemplate`, an error code `TEMPLATE_LOCKED`, and a `template_id` field on
  section entities. Each op gets the five ADR 0023 steps and a catalog entry.
- `test_architecture.py` gains the `section/templates/` rank (below `draft/`, beside
  `section/layout.py`, which the templates reuse for bars along edges).
- The 2-D client gets a template panel driven by the catalog schemas, so a new template needs
  no client code.
- apeSection's project file stores only the draft. The parameters are inside it.

## Errata (2026-11-01)

Recorded with the pure templates (apeSection#48, stage C3-S1), from the C3 decision record
(apeSection#2, comment 1089) and the rulings after it. The Decision above is unchanged. These
points record two owner rulings and the record's readings where the Decision text left a
question open.

1. **Every template takes a material (owner's ruling Q1, "Add via erratum").** Decision 5's
   table names no material. Every template also takes `material` (required: the name of its
   concrete face) and an optional `bar_material` (the name of the bar steel). Without
   `bar_material` the bars carry no `material`, so the consumer's default applies (ADR 0039
   decision 6). Names only: apeCAD stores no property and no law. (`bar_material` is narrowed
   to templates that place bars by 11.3.)
2. **Version 1 starts narrow (owner's ruling Q4, "Yes, start narrow").** `polygon_column` v1
   is convex only (a reflex vertex is refused; see 8.4 for straight vertices), `rect_hollow`
   v1 places no crossties, and `t_beam` v1 is symmetric. Widening any of them is a new
   `template_version` (decision 4), never a change to v1.
3. **Intent is stored, expansion is derived.** A template is a pure function from its
   parameters to a `Plan` (faces with holes and an optional steel `shape`, bars, hoops,
   crossties, circular ties, cover guides), kept in `section/templates/` as
   `TEMPLATES[template][version]`. The committed op records the `params`, the
   `template_version` (the latest when the op names none) and the `child_ids`. Replay
   refuses a mismatch, as `AddWallChain` does for its ring.
4. **Membership lives on one entity.** `SectionTemplate{entity_id, template,
   template_version, params, child_ids, label}` is the only record of which entities a
   template owns. Decision 1's "every child records `template_id`" is read as a projection:
   the draft's `template_id` on a child is found by inverse lookup of `child_ids`, and the
   child entities themselves carry no field. Explode drops the entity, so every child is
   freehand again at once. A materialiser builds the children from the `Plan` with fresh
   points (never reusing an existing point) and no labels.
5. **The lock is one guard (decision 3).** `TEMPLATE_LOCKED` is a new error code whose
   exception subclasses `DocumentError` (orchestrator's ruling Q2). It is one op-agnostic
   check in `dispatch.apply_op`, active only while templates exist: after an op, each
   surviving template's children must be the identical objects they were, and no new entity
   may reference one. Tags are allowed.
6. **Edit, delete and move.** `EditSectionTemplate` replaces `params` whole and expands
   again with fresh ids. It keeps the template's id, and its `template_version` unless the op
   names one. Deleting a child is refused (`TEMPLATE_LOCKED`); `Delete{template_id}` removes
   the whole template through ADR 0029's subtree. A template moves when its `center_mm` is
   edited.
7. **Common parameters and refusals.** All lengths are millimetres and every bar is a
   designation from the closed list (ADR 0039 decision 9). `center_mm` is the centre of the
   gross bounding box, default `[0, 0]`. A bar centre sits `cover + tie + bar / 2` from the
   face it rests on (ADR 0024 open q6). A template refuses, by name, parameters that are not
   an object; a missing, unknown or mistyped parameter; a `template_version` that is not a
   whole number; an inset that collapses; a point outside the ADR 0032 extent; more than 1000
   bars, counted before any bar is placed and before any work that grows faster than the bar
   count (`rect_column` and `t_beam` from their counts; `polygon_column` from its vertex count,
   then from the bar-centre ring's edges, Σ max(1, ⌈L / spacing_max⌉); `rect_hollow` from both
   bar rings' edges); and two bars closer than the
   mean of their diameters (lint's `bar-overlap` rule), named by the parameter that sets their
   spacing. `TemplateParamError` is an `OpArgumentError` (`INVALID_ARGUMENT`) whose message
   starts `<template>: <param>:`.
8. **Four readings of the v1 templates (stage C3-S1), ruled on in the review of apeCAD #56.**
   1. *`polygon_column` takes no `center_mm` (approved).* Its `ring` is the placement: the
      record's oracle keeps the ring where it is given, so the template is moved by editing
      the ring.
   2. *`rect_hollow`'s wall rule (superseded).* "A wall thinner than 2 d is refused" was first
      read as "a wall must be thicker than 2 d". The review replaced it with point 7's
      no-overlap rule: the outer and inner bar rings, `t - 2 d` apart, must be at least a bar
      diameter apart. `t_beam` likewise needs `hf >= 2 cover + bar` when it has slab bars, so
      they keep cover to the flange soffit as well as to its top.
   3. *`rect_column` crossties (approved).* They are 135-135 and join the interior bars facing
      each other across the section. Counted from the corner (index 0) along each face,
      `alternate` ties the even indices only; the hoop holds the corners. So with `nx = 3`
      `alternate` ties nothing in that direction, the same as `none`, and an even `nx` gives
      a pattern that is not symmetric about the centre.
   4. *`polygon_column` refuses a straight vertex too.* The owner's Q4 ruling says convex
      only. Refusing a collinear vertex as well (strictly convex) is the builder's stricter
      reading, kept by the review: a later version may accept one.
9. **The ops carry their params as `template_params` (review of apeCAD #57).** The op
   catalog's request envelope already uses `params` (`{"op", "params"}`), so
   `AddSectionTemplate` and `EditSectionTemplate` name the field `template_params`, and the
   flat request form stays usable. The `SectionTemplate` entity and the draft's
   `templates[]` keep `params`.
10. **Readings of `circular_column` v1 (stage C4-S1, 2026-11-02; apeSection#2, comment 1170,
    ratified in comment 1172, "Ratify as written").** Decision 5's row, with Errata 1 and 7,
    leaves these open:
    1. *`tie_kind` is required.* Decision 5's row marks it with no `?`, and a silent spiral
       would overstate the confinement. `Params.choice` gains a form with no default, which
       refuses a missing parameter as `required`; its form with a default is unchanged. The
       parameter dataclass keeps `str`, because `catalog/schema.py` has no `Literal`.
    2. *A hoop is a circular tie.* `tie_kind: "hoop"` writes a `circular_ties[]` entry (ADR
       0039 decision 5) that differs from the spiral in `kind` alone; `hoops[]` stays empty.
    3. *`n_bars >= 3`*, the fewest that span an area. *`pitch >= tie`*, because a tie's turns
       cannot overlap. The 4 and 6 bars of ACI 318 §10.7.3.1 and spiral spacing are the
       consumer's checks, not the template's.
    4. *Placement.* Bars start at angle 0 and run counter-clockwise; a start angle would be a
       new version. Overlapping bars are refused by `n_bars`. The template and
       `AddBarsOnCircle` share one formula, `section/layout.py::on_circle`.

    5. *Three overlapping bars name `diameter` (owner's ruling, apeSection#2 comment 1181,
       "Name `diameter` (Recommended)").* When even the fewest bars, three, overlap, the
       refusal names `diameter` rather than `n_bars`, because no `n_bars` could cure it; above
       three bars an overlap still names `n_bars`. This mirrors `rect_column` naming `b` when
       its two corner bars overlap. It was recorded at C4-S1 as an orchestrator reading
       awaiting the owner, and is ratified here at C4-S2.
11. **The CFT core exemption and `cft_round` v1 (stage C4-S2, 2026-11-02; apeSection#2,
    comment 1170, rulings in comments 1172 and 1181).**
    1. *Exact probe ends.* `section/regions.py::segment_probes` probes the ends of a segment as
       `a` and `b` themselves, as its docstring promised, not as `a + 1.0 * (b - a)`, which
       rounds past a corner at fractional coordinates. So `curve_within` holds for identical
       rings, and a concrete core equal to its steel tube's hole no longer warns
       `face-without-cover-guide` against ADR 0039 Errata 9.2. The record's probe found 414
       false positives in 14,400 cases before and none after, with no false negative either
       way. The other readers of the probes, the v1 and v2 crosstie lints, gain exact ends
       too, and their verdicts can move. The review of apeCAD #61 found 19 of 19,203 random
       segments flipped: 18 toward the exact answer, and 1 away from it. In that one, a
       crosstie whose end bar's centre sits at the float midpoint of a slanted edge now warns
       `crosstie-crosses-outside` although exact rationals put it strictly inside; the bar
       already warns `bar-outside-concrete`. The cause predates the exact ends: `locate`
       (`regions.py`) crosses rays in inexact floats. It is tracked on apeSection#54.
       (Reworded at C4-S3, apeSection#57; it first said the crosstie lints "only gain exact
       ends".)
    2. *`cft_round` v1.* `material` names the core's concrete (Errata 1) and `steel_material`,
       required, the tube's steel. The core is a circle of diameter / 2 - t; the tube is a
       circle of diameter / 2 with a circle hole of the core's radius, the same floats. A `t`
       is refused unless the core sits strictly inside the tube in floats (a positive core
       radius below the outer one). It draws no bars, ties, cover guides or steel `shape`.
    3. *`bar_material` only where there are bars (owner's ruling Q1, comment 1172, "Refuse it
       (Recommended)").* A template that places no bars, `cft_round` and `cft_rect`, refuses
       `bar_material` by name whenever it is given, null included: an accepted parameter that
       draws nothing would stay in v1 for ever (decision 4), and a refused one can arrive in a
       later version. Errata 1's `bar_material` narrows to templates that place bars.
12. **`cft_rect` v1 (stage C4-S3, 2026-11-02; apeSection#57, the C4 record in apeSection#2
    comment 1170 §3 and §6 row 4).**
    1. *The core and the hole are one set of floats.* The tube is the b x h ring centred on
       `center_mm`, from its corners `x0 = cx - b / 2`, `x1 = cx + b / 2` (and `y0`, `y1`
       likewise). The core is that ring inset by `t`, computed once from those corners as
       `x0 + t`, `x1 - t`, `y0 + t`, `y1 - t`, counter-clockwise; the tube's one hole is the
       same four floats, clockwise from the south-west corner. A core recomputed as
       `cx ± (b - 2 t) / 2` can differ from the hole by an ulp. The corners are square: the
       contract has no arc (the record's §7).
    2. *Materials and refusals as `cft_round`* (Errata 11.2, 11.3): `material` is the core's
       concrete, `steel_material`, required, the tube's steel, and `bar_material` is refused.
       A `t` is refused unless the core sits strictly inside the tube in floats along both
       axes, and the refusal names the axis.
    3. *The size is checked before the wall* (review of apeCAD #61). `cft_round` checks
       `diameter`, and `cft_rect` checks `b` and `h`, against the ADR 0032 extent before the
       wall check, so a huge size is refused by its own name: `diameter` 1e308 had been
       refused as `t`, because 1e308 / 2 - 10 == 1e308 / 2 in floats. The placed section is
       then checked against `center_mm`, as before.
    4. *A wall under 1 / sqrt(2) mm does not survive a seed replay.* The seed replays its
       rings through `PointAt`, which reuses a point within 1 mm (ADR 0030): such a wall
       puts each tube corner within 1 mm of a core corner, the replay merges them, and the
       replayed tube warns `hole-outside-face`. The template, its draft and its
       explosion are exact at any wall; only the seed path loses it. v1 does not refuse a
       thin wall: a minimum wall would be the owner's to set, and could arrive in a later
       version.

## Errata (2026-11-20): template holes stay parametric

Recorded at stage C9-1 (apeSection#203). The sources are:

- the owner's ruling at review gate RGc4 (apeSection#161, comment 2949, item 4: "ADR: holes
  stay parametric (Recommended)");
- architect brief A (apeSection#203, comment 4822), which this record follows;
- the orchestrator's reconciliation of brief A with brief B (comment 4829);
- the owner's rulings on their differences (comment 4844).

The Decision and Errata 1 to 12 above are unchanged. Code is cited at apeCAD 131c340 by
`path::symbol`, with paths under `src/apeCAD/` unless they start with `tests/`.

13. **Holes are a template parameter: route (a).** Today a duct costs a template its
    parameters (RGc4 finding F8). `AddFaceHole` writes a template child, so
    `draft/templates.py::check_template_lock` refuses it as `TEMPLATE_LOCKED`. The only way
    out is `ExplodeSectionTemplate`, which is one way (decision 3).
    1. *The parameter.* Version 2 of every template takes an optional `holes`. It is a list
       of holes, each in one of two forms:
       - `{"center_mm": [x, y], "radius_mm": r}`, a circle;
       - `{"ring_mm": [[x, y], ...]}`, a simple ring of at least 3 vertices, given once and
         in either orientation.

       Coordinates are mm offsets from the template's `center_mm`, so the holes move with it
       (Errata 6). `polygon_column` has no `center_mm` (Errata 8.1), so its holes are in
       section coordinates, the frame of its `ring`. An absent `holes`, or `[]`, draws no
       hole. `null` is refused as not a list: a value refused now can arrive in a later
       version, and an accepted one stays for ever (Errata 11.3).
    2. *One shared step after expansion.* A new `section/templates/holes.py` wraps each v1
       function: `section/templates/__init__.py::TEMPLATES[t][2]` is the step around
       `TEMPLATES[t][1]`. No v1 module is edited. The step runs in this order, and the
       first check that fails is the refusal:
       1. It checks that the params are an object and checks their keys with
          `section/templates/plan.py::Params` against the template's v1 `FIELDS` plus
          `holes`. So a v2 unknown-parameter refusal lists `holes` among the known ones, and
          v1's refusal text is unchanged.
       2. It checks that `holes` is a list (16.1, first row).
       3. It counts the caps (16.2). The count covers only the list-valued `ring_mm` of
          object entries. An entry that is not an object, or whose `ring_mm` is not a list,
          counts as one hole and no vertices, and is refused as a shape fault at step 4. So
          `holes: [{"ring_mm": "x" * 300}]` is refused at `holes[0].ring_mm`, not by the
          vertex cap.
       4. It checks each hole's shape faults that need no placement, hole by hole in index
          order (16.1, the rows before "after placement").
       5. It runs the v1 function on the params without `holes`. Every v1 refusal and every
          v1 drawing is therefore unchanged.
       6. It places each hole once, in floats. On a template centred at `(cx, cy)`, the
          offset `(x, y)` becomes the point `(cx + x, cy + y)`; on `polygon_column` the point
          is taken as given. These placed floats are the ones the materialiser writes and the
          ones the rules decide on. Then, hole by hole in index order, it checks the extent
          and the ring's simplicity (16.1, the "after placement" rows).
       7. It decides the seven rules R1 to R7 (17) on the placed floats.
       8. It appends the holes, in index order and with rings stored clockwise, after the
          face's own holes on the plan's one concrete face (`plan.py::PlanFace.holes`).
    3. *Children, not a second editor.* Hole points are children, made by
       `draft/templates.py::materialise`, which already builds `PlanFace.holes`. So edit,
       undo, replay, delete and explode need no new code. The lock, `AddFaceHole`
       (`draft/section.py::add_face_hole`) and the "hole a child face" row of
       `tests/test_section_template_lock.py` are unchanged: `AddFaceHole` on a template face
       stays `TEMPLATE_LOCKED`. Without holes, version 2 gives version 1's `Plan` and
       child ids.
    4. *Edits.* `EditSectionTemplate` replaces params whole (Errata 6):
       - an edit without `holes` removes them, so a client that rebuilds params must carry
         `holes` through;
       - an edit whose new size invalidates a hole is refused by name before anything
         changes, because `draft/templates.py::edit_section_template` expands before it
         drops a child;
       - a v1 template gains holes only by an edit that names `template_version: 2`. On v1,
         `holes` is refused as an unknown parameter.
    5. *Explode.* Explode is unchanged. It stays the route for whatever `holes` cannot say,
       such as a duct that displaces a bar, or a hole in steel. User hole k keeps its draft
       identity `(face_id, n_own + k)`, where `n_own` is 1 on `rect_hollow` (its void stays
       index 0) and 0 elsewhere.

14. **Route (b) is rejected.** Route (b) was a lock exemption for `AddFaceHole` on a template
    face, re-applied after every edit. It is rejected for five reasons:
    - The lock would depend on which op ran. Errata 5 makes it one op-agnostic check of what
      an op wrote, and `draft/templates.py::_check_kept` would have to accept a face that
      only some ops may change.
    - Re-applying a hole after an edit is the merge that the "Unlocked children" row above
      rejects: a second editor.
    - An edit redraws the face with a fresh id, so each re-applied hole's
      `(face_id, hole_index)` and points would have to be remapped.
    - The hole's points would lie outside the template's `child_ids`, which is the only
      record of membership (Errata 4).
    - `params` would no longer describe the section (decision 6, Errata 3). A hole that no
      longer fits after an edit would also have no parameter to name in its refusal.

    *Void faces* (a template drawing a `void` face for a duct) are rejected too:
    `PlanFace.holes` and the explode route already express a duct as a hole.

15. **Holes arrive as `template_version` 2 of all seven templates.** This is the owner's
    ruling, comment 4844: "Version 2 (Recommended)". Errata 2, 10.4 and 11.3 already treat
    any newly accepted input as a new version, and the version then tells which apeCAD can
    replay a log.
    1. *Version 1 stays byte-identical:* its seven functions, its refusals and its seven
       frozen logs. `section/templates/__init__.py::latest_version` becomes 2, so an
       `AddSectionTemplate` that names no version records 2. At 131c340 the three template
       fixture builders in `tests/_section_fixtures_v2.py` (`rect_column_template`,
       `t_beam_template`, `cft_rect_template`) call `add_section_template` without a
       version, so they would record 2. Pinning them to version 1 is a duty of the slice
       that registers each v2: C9-2b pins `rect_column_template`, and C9-2c pins
       `t_beam_template` and `cft_rect_template` (21). With those pins the 11 fixtures in
       `tests/fixtures/section_draft_v2/` stay byte-identical.
    2. *What version 2 is.* Version 2 is version 1 composed with the step (13.2), its shape
       refusals and caps (16) and its rules (17). A later change to any of them that moves a
       drawing or a verdict is a version 3, which keeps version 2 as it merged.
    3. *The frozen-log rule.* There is one log per template version, as now
       (`tests/test_section_template_projection.py::test_one_frozen_log_per_template_version`).
       - Each `tests/fixtures/section_templates/<template>@v2.json` holds one template with
         a circle hole and a ring hole. Every clearance in it (17) is at least 1 mm.
       - It is recorded once and never regenerated. It replays to itself and to a recorded
         SHA-256 of its `section` block (`SECTION_SHA256` in the same test module).
       - The exception is `circular_column@v2`, whose bars come from sine and cosine. It is
         compared at rel 1e-12, as `circular_column@v1` is.
    4. *Version 1 replays under version 2.* Each v1 log's params, expanded under version 2,
       give the same section apart from `template_version`.

16. **Shape faults and caps are refused by name.** A refusal is a `TemplateParamError`
    (Errata 7), whose message starts `<template>: <param>:`.
    1. *Shape faults.* These are checked in this order, each naming the parameter shown.
       The first row is step 2 of 13.2; the caps (16.2) come next, as step 3; the rows up to
       the ring's vertices are step 4, hole by hole; the two "after placement" rows are
       step 6, after the v1 function has run:
       - `holes` is not a list, `null` included (`holes`);
       - an entry is not an object (`holes[k]`);
       - an entry has an unknown key (`holes[k].<key>`);
       - an entry does not hold exactly one of the two forms (`holes[k]`);
       - a `center_mm` is not two finite numbers (`holes[k].center_mm`);
       - a `radius_mm` is not a positive finite number (`holes[k].radius_mm`);
       - a `ring_mm` is not a list, or has fewer than 3 vertices (`holes[k].ring_mm`), or
         holds a vertex that is not two finite numbers (`holes[k].ring_mm[i]`);
       - after placement, a point lies outside the ADR 0032 extent (`holes[k]`, as
         `plan.py::require_extent` words it);
       - after placement, a ring is not simple or has zero area (`holes[k].ring_mm`).

       The simplicity, the zero area and the orientation of a placed ring are decided
       **exactly**, like the rules (17.5). They use an orientation predicate on the stored
       floats: the sign of twice the shoelace area, and the signs of the cross products in
       the crossing tests, computed in `fractions.Fraction`. `section/geometry.py::is_simple`
       and `::signed_area` sum in floats, so they are not the verdict. `signed_area` can
       get the sign wrong on a thin ring far from the origin (18.4). A ring the step accepts
       is stored clockwise by that exact sign, so `plan.py::_check_plan` passes it. A bad
       ring is therefore never left to the `DocumentError` of `_check_plan`.
    2. *Caps.* This is the owner's ruling, comment 4844: "32 / 256 (Recommended)". A
       template takes at most 32 holes, and at most 256 ring vertices across all its rings.
       Both caps name `holes`, and both are counted (13.2 step 3) before any other hole
       work. Only the list-valued `ring_mm` of object entries is counted; a malformed entry
       is left to the shape faults of 16.1 (13.2 step 3).
       - The largest params any version 2 accepts are a `polygon_column` ring of
         `plan.py::MAX_TEMPLATE_BARS` (1000) vertices plus holes at the caps. They hold
         3,935 values as `ops/templates.py::freeze_params` counts them, which is within
         `MAX_PARAMS_VALUES` (4,000). So the op never refuses params that the expansion
         would accept.
       - The rules' work is bounded before it starts, at
         (Σ n_k)(E + B + X + K + T) + Σ_{j<k} n_j n_k units, each a bounded amount of work.
         Here n_k is 1 for a circle hole and the vertex count for a ring hole; E counts the
         face's boundary edges (a circle counts 1); B counts the bars, X the crossties, K the
         hoops' hull edges and T the circular ties.

         A work-unit test asserts the count at the worst case, which is the
         `polygon_column` above. It bounds operations, not seconds (apeSection lesson #158).

17. **The predicate: seven rules, contact refused, decided exactly.**
    1. *The rulings.* The owner ruled "Refuse contact (Recommended)" in comment 4844: zero
       clearance to a bar, a tie, the cover line or another hole is a clash. The
       orchestrator ruled in comment 4829, restated with the owner's rulings in comment
       4844, that the rules are decided exactly, with no tolerance. Brief A's τ is dropped.
    2. *The order of the checks.* The step checks each hole in index order, and the rules in
       the order R1 to R7. The first rule that fails is the refusal: it names `holes[k]`
       and says what the hole meets.
    3. *Notation.*
       - H is hole k as placed: a closed disc or a closed polygonal region, in the stored
         floats.
       - F is the plan's one concrete face, with outline O and its own holes V_j.
       - d(A, B) is the distance between closed sets, 0 when they meet.
    4. *The rules.*

       | Rule | Accepted when |
       |---|---|
       | R1 face | H lies in the interior of O: H ⊂ O and d(H, ∂O) > 0 |
       | R2 holes | d(H, V_j) > 0 for each of the face's own holes, and d(H, holes[j]) > 0 for every j < k. A clash between two entries is named at the later one |
       | R3 cover, on a face with a cover guide of `cover_mm` c | d(H, ∂O ∪ ∂V) > c: the cover line is kept from the outline and from the face's own holes |
       | R4 bars, each of centre p and diameter d_b | d(H, p) > d_b / 2 |
       | R5 crossties, each on the segment [p, q] between its bars' centres, of diameter t | d(H, [p, q]) > t / 2 |
       | R6 hoops. P is the closed convex polygon on the hoop's bar centres (`PlanHoop.bars`), r_min and r_max are the least and greatest radius of those bars, and t is the hoop's diameter | either every point of H is closer than r_min to P (inside the cage), or d(H, P) > r_max + t (outside it) |
       | R7 circular ties, each of centre C, centreline radius ρ and diameter t | either every point of H is closer than ρ − t / 2 to C, or d(H, C) > ρ + t / 2 |

       So a hole may clear steel and the cover line by any positive amount, however small,
       but it may not touch them. R6 is conservative where a hoop's bars differ in size.
    5. *Exact decision.* Every comparison reduces to the sign of a polynomial in the stored
       floats:
       - orientations decide containment and crossing, and also a placed ring's
         simplicity, zero area and clockwise storage (16.1);
       - squared distances are compared with squared sums of radii and clearances. For
         example, a circle hole of centre c and radius r clears a bar when
         |c − p|² > (r + d_b / 2)².

       The step decides these with `fractions.Fraction`. A float filter may decide a
       comparison only where a stated error bound proves that the float sign equals the
       exact one; any other comparison falls through to `Fraction`. The verdict is
       therefore the exact one on the stored floats.
    6. *Lints.* The rules have these freehand counterparts in `section/lint.py`:
       - R1 refuses what `hole-outside-face` warns about on a freehand hole;
       - R4, R5 and R7 refuse what `bar-outside-concrete`, `crosstie-crosses-outside` and
         `circular-tie-outside-face` would warn about on the exploded drawing, and contact
         besides;
       - R2, R3 and R6 have no lint today.

       No lint code changes. A template whose holes clear every rule by at least 0.01 mm
       draws no lint warning (`section/lint.py::lint_section_v2` returns `()`). Closer than
       that, a float lint may still warn on a hole the exact rules accept; the lint is
       advisory.

18. **The oracle for C9-2.** This is apeSection lesson #53's two-sided oracle
    (apeSection `docs/program/slice_card.md`, "Float predicates").
    1. *The truth.* An exact reference is written in the test, apart from the product: it
       imports none of the product's predicate code. It works in `fractions.Fraction` on
       the stored floats, with squared distances, and uses no square root, no trigonometry,
       no shapely and no product geometry.
    2. *The fuzz.* One seeded fuzz covers the seven templates, every rule, and both sides of
       each hoop band and each circular-tie band, with circle holes and ring holes. Its
       inputs are:
       - gaps from each limit of −1, −0.01, 0, +0.01 and +1 mm, and the nearest floats on
         either side of contact;
       - grids of 0.01, 0.1, 1 and 5 mm;
       - `center_mm` offsets of 0, 0.1, 1234.5 and 40000.3;
       - coordinates built as `i/10`, as `i*0.1` and as `round(k*g, 6)`;
       - inclined `polygon_column` edges;
       - tangency at dyadic radii;
       - a hole equal to `rect_hollow`'s void, and a hole equal to a CFT core.

       It checks that:
       - every verdict equals the truth;
       - every case whose exact clearance on the stored floats is 0 or less (overlap or
         contact) is refused;
       - every case whose clearance is positive, and that no other rule refuses, is
         accepted;
       - each rule shows both verdicts, and the counts of both directions are reported;
       - the fuzz fails with any one rule dropped, and with the exact decision replaced by
         plain floats. Each of these is shown in a scratch tree.
    3. *Hand cases.*
       - `rect_column`: b 400, h 600, cover 40, `tie` Ø10, `bar` Ø20, nx = ny = 3, with a
         centred Ø100 circle.
         - With `crossties: "none"` it is accepted. The nearest bar centres are 140 mm from
           the hole's centre (80 mm clear of the bar), the outline is 150 mm from the hole
           (beyond the 40 mm cover), and the hole lies inside the hoop. The net concrete
           area is 400·600 − π·50² = 232,146.0 mm², the worked example of apeSection's
           `skills/apesection/references/template-holes.md`.
         - With `"all"` it is refused at `holes[0]` by R5: its two crossties pass through
           the hole's centre.
       - `rect_hollow`: a wall duct between two bars and between the two hoops is accepted.
         The same duct, moved until its clearance from the void is no more than the cover,
         is refused by R3.
       - `t_beam`: the params of `tests/_section_fixtures_v2.py::T_BEAM_PARAMS` with `hf`
         200, and a Ø50 circle (r = 25). It is centred on the centreline of the right
         stirrup leg, 15 mm (r_max + t / 2) outside the hull edge, 110 mm below the top,
         at about (116.75, 490). It sits in the flange, so it clears R3: it is about
         70.9 mm from the outline, against a 30 mm cover. It clears R4: the nearest bar, a
         top bar, is about 30.7 mm clear. It is refused by R6: its distance from the hull
         runs from 0 to about 40 mm, so it is neither within r_min = 8 mm of the hull nor
         beyond r_max + t = 20 mm. A duct on a leg lower in the web always fails R3 first,
         so it is not this case.
       - `cft_round` and `cft_rect`:
         - a hole tangent to the core's outline is refused by R1;
         - two holes that touch are refused by R2, at the later index;
         - holes 0.01 mm clear of the core's outline and of each other are accepted.
       - `circular_column`: a hole whose closure touches the spiral's inner face (ρ − t / 2)
         is refused by R7, and the same hole 0.01 mm inside that face is accepted.
    4. *Placement oracles.* The truth of 18.1 works on the stored floats, so it cannot tell
       where a hole lands: if step 6 of 13.2 placed `(x, y)` instead of `(cx + x, cy + y)`,
       18.1 to 18.3 would still pass. These oracles pin placement, at a non-zero,
       non-dyadic `center_mm` (for example `[1234.5, -40000.3]`):
       - every stored hole point (a circle's centre, each ring vertex, read from the draft's
         `faces[].holes[]`) equals the test's own `(cx + x, cy + y)`, computed in the test;
       - editing `center_mm` moves the holes with it: each stored point is the new
         `(cx + x, cy + y)`;
       - editing `b` leaves each hole at its offsets from `center_mm`, so the hole survives
         at its template coordinates (apeSection#204);
       - `polygon_column` holes stay in section coordinates: the stored points equal the
         given ones;
       - every stored ring hole is clockwise, whichever orientation it was given in.
         "Clockwise" means that the exact twice-shoelace area of the stored floats, summed
         in `fractions.Fraction`, is negative. The oracle includes the ring
         `[(39999.56872848823, 40000.99486747388), (40260.93513113888, 39758.30007034527),
         (40527.11796644146, 39511.13291895272)]`, given as section coordinates on
         `polygon_column` so that the stored floats are the given ones. `is_simple`
         accepts it, and the float `signed_area` returns +1.19e-07, but its exact sign is
         negative (twice the area is about −4.66e-09 mm²). So it is already clockwise. The
         step must store it unreversed, or refuse it by name if it fails the exact rules;
         it must never store it reversed into a counter-clockwise hole;
       - `rect_hollow`'s first user hole is at `hole_index` 1, after its void at 0 (13.5).
    5. *Op oracles.*
       - Editing `b` keeps the holes.
       - Undo is one step.
       - Each v2 log replays.
       - `AddFaceHole` on a template face stays `TEMPLATE_LOCKED`.
       - Without holes, version 2 equals version 1, in its plan and its child ids.
       - The work-unit test at the caps passes (16.2).

19. **Scope: all seven templates take holes, and explode stays.**
    - In `cft_round` and `cft_rect`, a hole cuts the concrete core, never the steel tube.
    - `rect_hollow`'s void stays derived from `t_x` and `t_y`, and is never a `holes`
      entry.
    - Explode stays for anything `holes` cannot say (13.5).

    **A known limit, for the owner to accept at merge.** R5 and R6 model a crosstie as the
    segment between its bars' centres and a hoop as the band around its bar-centre hull.
    They ignore the 135° hook tails that are drawn. So an accepted hole may overlap a drawn
    hook tail, short of the "contact is a clash" ruling (comment 4844). Modelling the tails
    would be a later version.

    Not built:
    - no change to the lock, `AddFaceHole`, the lint, `section/regions.py`, the draft
      writer or reader, the seed, render or the client JS;
    - no new error code or lint code;
    - no holes in steel faces, no hook tails, no rotation and no re-implode;
    - no rule for steel faces before `src_column` exists.

20. **No contract version moves,** so there is no separate `human-gate`.
    - *section-draft v2.* Holes use the existing `faces[].holes[]`. `templates[].params` is
      "display only" and is what the op recorded (the `section.templates[]` row of
      `AProjects/specs/section-draft-v2.md`), and a consumer never re-expands it
      (decision 7). `template_version` 2 is a value the shape already allows: apeConcrete's
      reader `src/apeConcrete/io/apecad.py::_read_templates` (apeConcrete 57fe5c6) accepts
      any positive whole version and any params object. The spec's hashed block and its
      SHA-256 do not change; C9-3 adds prose outside it.
    - *Client API 4* (`scratchpad/section_assets.py::CLIENT_API_VERSION`). The client prints
      params as JSON (`scratchpad/static/section/tools-v2.js::templateLines`) and already
      draws holes.
    - *Transport 1.* Params stay opaque.
    - *Document schema `apeCAD.document.v1`.* No op and no op field changes;
      `template_params` is already an object.
    - *The op catalog.* It is not a versioned contract, and it grows additively: each row's
      schema gains a `holes` property. That property uses only `type`, `items`, `anyOf`,
      `properties`, `required`, `additionalProperties`, `prefixItems`, `minItems` and
      `maxItems`. These are keywords that apeSection's schema-driven form reads
      (`web/src/tabs/geometry/schema.ts::FORM_KEYWORDS`, apeSection 923b039).

21. **The split.** This is brief A's split, by the owner's ruling in comment 4844. A version
    freezes when it merges, so each v2 merges with its refusals and its catalog row.
    - *C9-2a* adds `section/templates/hole_rules.py` (rule 17) and its oracle test (18.1 to
      18.3). Nothing is registered.
    - *C9-2b* adds:
      - `section/templates/holes.py`, the step of 13.2 with the refusals and caps of 16;
      - version 2 of `rect_column`, `rect_hollow` and `polygon_column` in
        `section/templates/__init__.py::TEMPLATES`;
      - their catalog rows in `catalog/template_params.py::_ROWS`, and
        `catalog/schema.py::_field_schema` for the union of the two hole records, which
        it refuses today (`no JSON schema for union`);
      - `tests/test_section_template_holes.py`, with the placement and op oracles
        (18.4, 18.5) for its three templates;
      - the seams, including the version 1 pin on `rect_column_template` in
        `tests/_section_fixtures_v2.py` (15.1), and `tests/test_section_client_v2.py`,
        whose props test asserts `"Template #{id} (rect_column v1) · locked"` for a
        template added without a version;
      - three v2 logs.
    - *C9-2c* does the same for `circular_column`, `t_beam`, `cft_round` and `cft_rect`,
      with four v2 logs. It pins version 1 on `t_beam_template` and `cft_rect_template`
      (15.1).
    - *C9-3* adds:
      - the word `holes` (version 2) in `draft/templates.py::_WAYS_OUT` and
        `catalog/template_entries.py::_PARAMS`, keeping their old text (the lock test pins
        `_WAYS_OUT`);
      - the lint-parity test of 17.6;
      - one section-draft v2 fixture with a parametric hole and its render golden, for
        consumers to vendor: `tests/fixtures/section_draft_v2/rect_column_template_hole.json`
        and `tests/fixtures/render/section_v2_rect_column_template_hole_top.svg`. They are
        built by a new builder in `tests/_section_fixtures_v2.py` that names version 2, and
        the fixture lists in `tests/test_section_draft_v2_fixtures.py` grow to include them;
      - the section-draft v2 spec prose, so that its template-log paragraph names the v2
        logs and its fixture table names the new fixture.
    - *C9-4* (apeSection#206) stands: apeSection moves its pin, re-vendors the C9-3 fixture,
      and makes its template-hole route parametric.

    *Order.* The slices run one after another: C9-2a, then C9-2b, then C9-2c, then C9-3,
    then C9-4. C9-2b and C9-2c share `section/templates/__init__.py`,
    `catalog/template_params.py`, `tests/test_section_template_holes.py` and the seam tests,
    so they cannot run in parallel. C9-3 needs every v2 merged, and C9-4 needs C9-3.

    *Mapping to the ledger.* This re-scopes the slice issues carded per group of templates
    before these rulings:
    - apeSection#204 (titled C9-2) becomes C9-2a and C9-2b;
    - apeSection#205 (titled C9-3) becomes C9-2c. Its template-hole fixture and render
      golden move to C9-3;
    - this record's C9-3 needs its own slice issue, which the orchestrator cards;
    - apeSection#206 stays C9-4.

    **The seams.** These are the tests that assume version 1 is the latest, or that 2 is
    unknown. They are found by a search, not from a list:

    ```
    git grep -n -E "template_version|latest_version|@v1| v1\)" -- tests ':!tests/fixtures' ':!tests/js'
    ```

    At 131c340 this finds six files: `test_atomic_ops.py`, `test_section_client_v2.py`
    (the `rect_column v1)` props line), `test_section_draft_v2.py`,
    `test_section_template_ops.py`, `test_section_template_projection.py` and
    `test_section_templates.py`. `tests/_section_fixtures_v2.py` is also a seam. Its three
    template builders name no version at 131c340, so C9-2b and C9-2c must each pin
    version 1 on theirs (15.1).

    These are ruled out, because they already handle holes or never re-expand:
    `materialise`, `draft/dispatch.py`, `draft/section.py`, `draft/topology.py`,
    `draft/transform.py`, `entities.py`, `section/draft_v2.py`, `section_draft.py`,
    `section/lint.py`, `section/regions.py`, `render/` and `scratchpad/static/section/`.

    **Recorded for later, not built now:**
    - a freehand `hole-overlap` lint, and lints for R3 and R6;
    - `rect_hollow` v1 drawing its inner hoop on the wall side of its bars, which squeezes
      wall ducts: a version 3 matter;
    - a ring vertex within 1 mm of another point does not survive a seed replay (Errata
      12.4). This is recorded, not refused.
