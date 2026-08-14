# ADR 0013 — View cube is a client compass, not a document op

**Status:** Accepted (2026-08-14)

Amends [ADR 0008](0008-face-extrude-mouse-nav.md): named views are a
widget on the canvas. Mouse chords still orbit, pan, and zoom.

## Context

The scratchpad already has parallel/perspective and MMB orbit. Finding
plan, front, and an isometric again is still guesswork. A view cube is
the usual compass. It must not become a second source of truth: camera
pose is not spatial intent (ADR 0006). Chili3D’s cube is a principle
only (ADR 0007).

The draft is **Z-up**, sketched on **XY** (z = 0). Named faces follow
that, not a Y-up mechanical cube.

## Decision

1. **The cube is view state.** Clicks do not POST ops. Save JSON does
   not store camera, projection, or the last named view.
2. **Placement:** overlay, upper-right of the stage, own small canvas
   so picks never hit the draft.
3. **Z-up names:** Top = +Z, Bottom = −Z, Front = −Y, Back = +Y,
   Right = +X, Left = −X. Screen-up is +Z except Top/Bottom (+Y).
4. **Hits:** face → that elevation/plan; edge → two-axis view;
   corner → isometric of that octant. ISO is the Right–Front–Top
   corner (+X −Y +Z). Fit frames
   the current points, keeping the current direction.
5. **Motion:** short ease to the new camera on a sphere about the
   existing orbit target. Distance is preserved except on Fit.
6. **MMB orbit stays the look tool.** The cube does not capture a
   drag-orbit in this slice.

## Alternatives rejected

| Rejected | Why |
|---|---|
| Named-view ops in the document | Camera is not intent; the ledger is geometry |
| Ribbon-only Front/Top buttons | No compass while orbiting |
| Y-up mechanical labels | Fights XY sketch and Z-up cameras |
| Copying a third-party cube | ADR 0007; we draw our own faces |

## Consequences

The scratchpad spec gains a view cube. Workplanes other than z = 0
remain later; when they exist, the cube still orients to **world**
axes unless a successor ADR says otherwise.
