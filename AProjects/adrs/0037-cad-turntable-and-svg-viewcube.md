# ADR 0037 — Cursor-pivot zero-roll Z-up CAD turntable and zero-GL 26-zone SVG ViewCube

**Status:** Accepted (2026-10-24)

Amends [ADR 0013](0013-view-cube.md) (the view cube remains a client compass, now rendered as a zero-WebGL 26-zone SVG instead of a second `THREE.WebGLRenderer`).

## Context

1. **Second WebGL context.** `viewcube.js` instantiated a second `THREE.WebGLRenderer` and six `256×256` `CanvasTexture` instances solely to draw a `108×108` orientation gizmo. Each extra WebGL context consumes browser GPU resources and risks context loss in multi-pane workbenches (`apeWorkbench`).
2. **Center-locked orbit and zoom.** Standard `OrbitControls` orbits around a fixed `target` and zooms toward the screen center rather than the cursor's 3-D point, and lacks pointer-cancel cleanup and frustum centering when side docks resize.

## Decision

1. **Pure-math Z-up CAD turntable (`static/js/navigation.js`).**
   - Provide pure, unit-tested camera math helpers: `headingBasis(yaw, pitch)`, `orbitAroundCursor(pose, pivot, dYaw, dPitch)`, `panKeepPoint(pose, dRight, dUp)`, and `zoomAtCursor(pose, cursorWorld, factor)`.
   - Enforce a zero-roll Z-up turntable frame (`WORLD_UP = (0, 0, 1)`) with cursor-pivot orbit, zoom-to-cursor, `pointercancel` / `lostpointercapture` cleanup, and `camera.setViewOffset` support when docks shift the stage center.
2. **Zero-WebGL 26-zone SVG ViewCube (`static/js/viewcube.js`).**
   - Replace the second `THREE.WebGLRenderer` with an inline SVG 3-D projection of the cube's 26 interactive zones (6 faces, 12 edges, 8 corners), a ground-plane compass ring (`N`, `E`, `S`, `W`), 90° CW/CCW roll buttons, and drag-to-orbit.
   - `apeCAD` drops from 2 WebGL contexts to 1.

## Alternatives rejected

| Rejected | Why |
|---|---|
| Keep the second `THREE.WebGLRenderer` for the ViewCube | Wastes a hardware WebGL context and 6 textures for a 26-zone polyhedron that projects analytically in ~100 lines of SVG. |
| Trackball free-roll rotation | Introduces camera roll so vertical columns and walls tilt sideways during orbit. |

## Consequences

- `static/js/navigation.js` is a pure module tested in `tests/js/navigation.test.mjs`.
- `static/js/viewcube.js` uses zero WebGL contexts and renders crisp vector zones styled by the active theme tokens.
