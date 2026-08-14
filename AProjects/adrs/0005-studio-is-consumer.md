# ADR 0005 — Studio is pick/show; apeCAD does not author inside Studio

**Status:** Accepted (2026-08-14)

## Context

apeGmsh ADR 0095 defines `apeGmsh.studio`: Cursor stays the IDE; a
Python daemon replays the script; the Qt `ViewerWindow` is the v1 host.
Invariants: the `.py` file is analysis source of truth; the viewport
**never write-backs** CAD; “viewer as parametric CAD” is rejected.

apeCAD needs a place for spatial sketching. Putting that sketching
inside Studio as a “CAD mode” would silently reverse 0095.

## Decision

- **Studio** consumes snapshots and selection names. It does not
  mutate an apeCAD document.
- **apeCAD** is a separate library (and, later, a separate scratchpad
  window). Its write path is the Python ops API, used from Cursor,
  agents, or the web client.
- Shared contract with Studio: **labels / names first**, not tags.
- If SketchUp-class drawing ever becomes the daily human loop *inside
  the Studio shell*, that is a habitat amendment recorded as a new
  ADR in **both** repos. It is not implied by this one.

## Alternatives rejected

| Rejected | Why |
|---|---|
| Studio CAD mode | Violates apeGmsh ADR 0095 INV-2 |
| Merge apeCAD into `g.studio()` | Studio is a sidecar, not a modeller |
| Rewrite Studio visualizers in Three.js | Already rejected in 0095 (~55k LOC) |

## Consequences

apeCAD can ship a drawing client without touching Studio. Studio
integration is read-only (highlight, envelope, stills) until a
future joint ADR.
