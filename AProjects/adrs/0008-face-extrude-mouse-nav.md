# ADR 0008 — Face + extrude is the solid; navigation is mouse

**Status:** Accepted (2026-08-14)

## Context

The first scratchpad treated orbit as a tool button, boxes as a typed
height, and solids as axis-aligned `Box` records. That fights how
people actually sketch: look with the mouse, rubber-band the stroke,
snap to grid and nodes, lock orthogonal, draw a face, then pull it
into a solid. Parallel projection is the modelling view; perspective
is for looking.

A constraint solver (SolveSpace) is still out of v0. Orthogonal and
length are **draw helpers** that write explicit coordinates, not
live equations.

## Decision

1. **Solids are `Face` + `Extrude`.** A planar loop is a first-class
   entity. Extrude is an intent op (distance along a direction,
   default the face normal). `Box` remains sugar, not the modelling
   primitive.
2. **Scratchpad navigation is mouse chords**, not a mode button:
   LMB draws, MMB (or Alt+LMB) orbits, RMB pans, wheel zooms.
3. **Both projections:** perspective and parallel (orthographic).
4. **Snap:** grid and existing nodes. Ghost strokes while drawing.
5. **Orthogonal + length** are client helpers (Shift; optional length
   field). They do not become a constraint graph until a later ADR.

## Alternatives rejected

| Rejected | Why |
|---|---|
| Orbit as a tool that disables drawing | CAD look/draw split belongs on mouse buttons |
| Fixed-height box as the only solid | Blocks later extrude-from-face |
| Constraint solver in v0 | Pointer-loop / compile-later (ADR 0003, 0004) |

## Consequences

The document grows `AddFace` / `Extrude` / `Solid`. The scratchpad
must be restarted to pick up static JS. Studio still does not author.
