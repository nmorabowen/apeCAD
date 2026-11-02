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
