# ADR 0007 — Chili3D / SolveSpace / ArcCAD are principle sources only

**Status:** Accepted (2026-08-14)

## Context

The architecture was informed by three open projects:

| Project | Principle taken |
|---|---|
| **Chili3D** | Document + commands + pluggable viewport; core ≠ kernel ≠ UI |
| **SolveSpace** | Intent (parameters, entities, constraints) can wait; keep the door open |
| **ArcCAD / jsketcher** | Typed operations with serializable params; push-pull as later UX |

Those projects are **not** dependencies and will not be forked.

Their licenses are not our licenses: Chili3D is AGPL-3.0 (WASM LGPL),
jsketcher/ArcCAD uses a custom assignment-style license, SolveSpace is
GPL-3.0. Copying source would infect or encumber this MIT tree.
Inspiration of architecture does not.

## Decision

- Implement apeCAD independently in this repository.
- Do not clone, vendor, or paste Chili3D, ArcCAD, jsketcher, or
  SolveSpace source here.
- Agents generating apeCAD code must not be pointed at those trees as
  implementation references. Human-written principle notes (this ADR,
  `AProjects/memory/`) are the allowed residue.
- apeCAD remains **MIT** until a future dependency forces a change
  (recorded in a new ADR).

## Alternatives rejected

| Rejected | Why |
|---|---|
| Fork Chili3D | AGPL; wrong product; TypeScript core |
| Embed SolveSpace solver | GPL; not needed for a scratchpad |
| Port jsketcher feature history | Custom license; CAD-class complexity |

## Consequences

Clean-room is a process, not a slogan: keep third-party CAD sources
out of this repo. If we later need a constraint library, choose a
permissively licensed one or write it — do not lift SolveSpace.
