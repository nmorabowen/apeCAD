# ADR 0014 — Menubar, side rail, and client preferences

**Status:** Accepted (2026-08-14)

Amends [ADR 0010](0010-selection-inspector-ribbon.md): command chrome is a
**vertical rail**, not a top ribbon. File/Edit/View live in a thin
menubar. Visualization variables are **client preferences**, not ops.

## Context

Screens are wide. A labeled top ribbon steals the height the cube
needs. Plasticity keeps tools on a lateral strip; the outliner and
inspector collapse and drag-resize. apeCAD already has a left dock
that collapses and a splitter; that must apply to every dock.

The document is millimetre intent (ADR 0006). Camera is already not
in the JSON (ADR 0013). Clay color, grid, lights, and AO are the
same kind of thing: how we *look* at the draft, not what the draft
*is*. They still need a home — File / Open / Save / Preferences —
because a scratchpad that cannot reopen a JSON file is a demo.

## Decision

1. **Layout R4.** Thin menubar (File, Edit, View, Help). Left:
   one dock — nested B-rep outliner with the property readout
   **below** it — then a vertical icon rail. Center: viewport.
   Bottom: command line. No second properties panel. Groups
   (Select, Sketch, Solid, Transform, Modify, View) are separators
   on the rail, not a second horizontal ribbon. Entity ids and
   copy counts stay in the library; the chrome does not expose an
   `n` field.
2. **Docks collapse and drag-resize independently.** The left dock,
   command line, and (if needed) the rail each fold on their own.
   Splitters persist width/height for the session.
3. **File talks to the JSON document** (ADR 0006): New, Open, Save,
   Save As, Import JSON, Export JSON. Viewport image export and
   `to_frame` / `to_gmsh` export are later. Open replaces the live
   document; Import in v0 is Open.
4. **Preferences are client state.** Background, clay fill, edge
   weight, curve color, key light, AO, grid, show edges/curves/faces.
   They are not ops and are not stored in the document JSON. A later
   ADR may persist them in local storage or a user file.
5. **Edit** is undo / redo / delete / select-all (already ops or
   selection). **View** toggles grid, snap, ortho, projection, fit,
   view cube — still not ops.

## Alternatives rejected

| Rejected | Why |
|---|---|
| Keep the top command ribbon as home chrome | Steals height on 16:9 |
| Visualization sliders in the document | Camera-class state; forks the JSON |
| Preferences as ops (`SetClayColor`) | Not spatial intent |
| Merge Open and a second scene format | One writer, one JSON (ADR 0006) |

## Consequences

The scratchpad spec gains a menubar and File/Open. ADR 0010's
"ribbon groups commands" still holds as *grouping*, now vertical.
A successor ADR freezes the clay/grid look (G5, ~176 fill, black
edges, blue curves) as the default preference values.
