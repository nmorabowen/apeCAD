# ADR 0002 — apeCAD is a spatial scratchpad, not a CAD modeller

**Status:** Accepted (2026-08-14)

## Context

The first impulse was “a simple CAD GUI like AutoCAD / SketchUp /
Plasticity” so apeConcrete, apeSteel, and apeGmsh could share diagrams.
That reads as a modeller: humans draw the building; the CAD file is the
model.

The actual need is narrower. Spatial description in prose does not
scale. Humans (and agents) need a **three-dimensional draft** to explain
what they want. If that draft is later useful as geometry, it can be
consumed. Usefulness as mesh is a bonus, not the product.

## Decision

apeCAD is a **spatial scratchpad**.

- Success = a labeled 3D draft that breaks verbal description of a
  complex object.
- Humans do not have to “draw the model.” They sketch enough for an
  agent or a colleague to understand the spatiality.
- The engineering source of truth for analysis remains the apeGmsh
  script (and Studio’s snapshot of it). The scratchpad is the
  **explanation artifact**.

## Alternatives rejected

| Rejected | Why |
|---|---|
| Full CAD modeller (Chili3D-class) | Complexity we explicitly do not want |
| Viewer-as-CAD inside apeGmsh | apeGmsh refuses to be CAD (Studio ADR 0095) |
| Script-only, no spatial draft | Leaves the verbal bottleneck unsolved |

## Consequences

v0 is a document + ops API, not a feature-history CAD. Drawing tools
are justified only insofar as they help explain spatiality. Push-pull,
constraints, and BREP history are out of scope until a later ADR.
