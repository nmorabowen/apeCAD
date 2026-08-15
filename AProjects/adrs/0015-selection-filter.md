# ADR 0015 — Viewport selection filter

**Status:** Amended (2026-08-14) by [ADR 0017](0017-face-loop-lines.md)

Amends [ADR 0010](0010-selection-inspector-ribbon.md) and
[ADR 0011](0011-window-select-modify-nodes.md): click and window
selection honour a **client filter** so a clay volume does not steal
every pick.

## Context

The scratchpad can already pick, but the first ray-hit wins. A `Solid`
is drawn as a filled volume; its profile, cap, edges, and vertices sit
inside or behind that mesh. Clicking a box therefore always selects the
solid. Window-select and Select-all scoop every nested Point with it.

A spatial scratchpad needs the same five picks a modeller reaches for:
a vertex, an edge, a face, a solid, or the whole object. Selection stays
a view (ADR 0011). The document does not store the filter.

## Decision

1. **Five exclusive filter modes**, client-only: Point, Line, Face,
   Solid, Element. Default is **Element**. Keys 1–5 while Select is
   active. A compact overlay on the viewport; the outliner ignores the
   filter so the tree can still name any entity.
2. **Element** maps a hit (click or window) to the B-rep root — the
   whole object. Nested vertices of a solid are not independently
   selected. Ctrl+A in this mode selects roots, not every Point.
3. **Sub-object modes** pick that kind even when nested. Point = `Point`.
   Line = `Line`, `Polyline`, `Arc`, `Bezier`. Face = `Face`, `Circle`,
   `Ellipse` (the extrudable profiles, including a solid's base and
   cap). Solid = `Solid`, `Box`. Lateral sides of an extrude are not
   Face entities and are not invented here.
4. **Click picking is geometric** for sub-objects: screen-space aperture
   for points and curves, ray-polygon for faces. A clay volume does not
   occlude a Point/Line/Face pick. Tool clicks (Trim, Node, …) keep the
   existing first-mesh hit so those verbs do not inherit the filter.
5. Face loops that were never `AddLine`d have no Line entity to pick.
   Line mode does not synthesise edges; use Face or Element.

## Alternatives rejected

| Rejected | Why |
|---|---|
| Store the filter in the document | Selection is a view (ADR 0011) |
| Additive multi-filter in this slice | Exclusive is enough; mix later if needed |
| Bake Line records for every face loop | Changes intent just to pick; Face already holds the loop |
| Kernel tessellation of lateral faces | No kernel (ADR 0004); sides are not entities |

## Consequences

The scratchpad overlay gains the five filters. Modelling-helpers
documents the default (Element) and the 1–5 keys. Push-pull of a
picked face remains later.
