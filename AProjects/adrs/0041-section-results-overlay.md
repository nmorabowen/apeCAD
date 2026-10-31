# ADR 0041 — A read-only results overlay on the section client and the render tool

**Status:** Accepted (2026-10-31)

Builds on [ADR 0024](0024-section-mode-rc-intent.md) decision 2 (no mechanics in apeCAD),
[ADR 0026](0026-section-transport-and-client.md) (the 2-D client) and
[ADR 0028](0028-agent-surface-mcp.md) (headless render for agents).

## Context

apeSection (its ADR-0001) shows analysis results **on** the drawing: the neutral axis at a
chosen point of a P-M-M surface, fiber strain and stress, cracked and crushed fibers, the
confined cores apeConcrete derived, spalled cover, and yielded or fractured bars. Agents that
co-work with the tool must see the same picture without a browser (apeSection ADR-0005).

apeCAD must not compute any of it (ADR 0024 decision 2) and must not import apeConcrete (O5).
apeCAD can paint geometry and values that a host hands it.

## Decision

1. **A contract, `apeCAD.section-overlay` v1, owned here** (spec
   `specs/section-overlay.md`, SHA-256 as in ADR 0025). An overlay is display data in world
   millimetres:
   - `revision`: the document revision it was computed from;
   - `layers[] = {id, label, visible, primitives[]}`;
   - primitives: `polygon` (ring and optional holes), `circle`, `polyline`, `point`, and
     `label` (text anchored at a point). Each carries a `style` or a `value`;
   - `value` with a `scale = {kind: "sequential" | "diverging" | "categorical", domain,
     colors, unit, title}` that the client draws as a legend;
   - an optional `ids[]` per primitive that links it to apeCAD entities, for hover and
     highlighting.
   It has no meaning beyond "draw this". apeCAD never stores it in the ops log, the draft or
   the seed.
2. **The client gains `setOverlay(overlay | null)` and `getOverlayState()`.**
   `API_VERSION` and `CLIENT_API_VERSION` go to 2.
   - The client draws the overlay above the section and below the selection.
   - When the document revision moves past `overlay.revision`, the client dims the overlay and
     shows "stale". It never hides results without saying so, and it never recomputes them.
   - Labels and legend text are set through `textContent` only, as for draft labels (ADR 0026
     decision 4). Colours are validated as hex or design-system tokens (ADR 0031).
   - Size cap: `MAX_OVERLAY_PRIMITIVES` (initially 200 000, enough for a fine fiber mesh). Above
     it the client refuses, and never truncates.
3. **The render tool takes the same overlay.** `render(..., overlay=...)` in
   `apeCAD/render/` and the MCP `render` tool draw it into the SVG (and the PNG of the
   `apeCAD[png]` extra). An agent checking a result sees exactly what the engineer sees.
4. **The transport is unchanged.** The overlay is never posted to `handle`. The host holds it
   and passes it to the client or the render call directly. An overlay therefore cannot
   change the document.

## Alternatives rejected

| Rejected | Why |
|---|---|
| apeCAD computes stresses or the neutral axis | ADR 0024 decision 2, O5 |
| Store results in the ops log or draft | Results are regenerable from the draft. Storing them makes a second truth that goes stale silently |
| The host paints its own canvas on top of the client | Two coordinate systems and two hit-tests that must stay aligned through zoom and pan. The render tool for agents would not show it |
| Hide a stale overlay automatically | The engineer loses the last result without being told. Dimming is honest |
| Semantic overlays (`"neutral_axis"`, `"fiber_stress"` as kinds) | apeCAD would learn mechanics vocabulary and need a release per new result type. Geometric primitives plus values cover them all |

## Consequences

- A new spec, a client module `static/section/overlay.js` (at most 600 lines, ADR 0023)
  with `node --test` tests, an `overlay` argument on the render API, and an SVG layer.
- ADR 0038's visual and contrast gates gain the overlay scales: each scale's colours pass the
  CVD and contrast checks.
- `CLIENT_API_VERSION = 2` is a change for ape-web-tools, which embeds the client. HA-04 does
  not use the overlay and keeps working, but its version check must accept 2.
