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
