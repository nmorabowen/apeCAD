# Architecture Decision Records

Each ADR captures one significant decision: **context**, **decision**,
**alternatives rejected**, and **consequences**.

ADRs are append-only. If a later decision reverses or amends an earlier
one, write a new ADR that supersedes it; do not edit history.

Status: `Proposed` → `Accepted` → `Amended` / `Superseded`.

| # | Title | Status |
|---|---|---|
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions in AProjects | Accepted |
| [0002](0002-spatial-scratchpad.md) | apeCAD is a spatial scratchpad, not a CAD modeller | Accepted |
| [0003](0003-python-document-web-client.md) | Python document is the public language; web GUI is a client | Accepted |
| [0004](0004-kernel-free-intent-document.md) | Kernel-free intent document; realize downstream | Accepted |
| [0005](0005-studio-is-consumer.md) | Studio is pick/show; apeCAD does not author inside Studio | Accepted |
| [0006](0006-one-source-of-truth.md) | One writer: the Python ops API; JSON is a file format | Accepted |
| [0007](0007-clean-room-inspiration.md) | Chili3D / SolveSpace / ArcCAD are principle sources only | Accepted |
| [0008](0008-face-extrude-mouse-nav.md) | Face + extrude is the solid; navigation is mouse | Accepted |
| [0009](0009-sketch-palette-live-dims.md) | Sketch palette and live dimensions | Accepted |
| [0010](0010-selection-inspector-ribbon.md) | Selection, inspector, and a command ribbon | Accepted |
| [0011](0011-window-select-modify-nodes.md) | Window selection, modify ops, and insert-node | Accepted |
| [0012](0012-kernel-free-modify-transform.md) | Kernel-free modify and transform | Accepted |
| [0013](0013-view-cube.md) | View cube is a client compass, not a document op | Accepted |
| [0014](0014-menubar-side-rail-prefs.md) | Menubar, side rail, and client preferences | Accepted |
| [0015](0015-selection-filter.md) | Viewport selection filter | Amended by 0017 |
| [0016](0016-extrude-wall-faces.md) | Extrude walls are selectable faces | Accepted |
| [0017](0017-face-loop-lines.md) | Face loops write Line records | Accepted |
| [0018](0018-brep-selection.md) | B-rep topology is the selection graph | Accepted |
| [0019](0019-instance-scratchpad-host.md) | Scratchpad host is per-instance, not machine-global | Accepted |
| [0020](0020-agent-surface.md) | AGENTS.md is the agent entry point | Accepted |
| [0021](0021-scratchpad-root-flag.md) | Scratchpad CLI accepts `--root` | Accepted |
| [0022](0022-ci-gates.md) | CI runs pytest, ruff check and pyright | Accepted |
| [0023](0023-module-boundaries.md) | Module boundaries and a line budget | Accepted |
| [0024](0024-section-mode-rc-intent.md) | Section mode: RC section entities are drawing intent | Accepted |
| [0025](0025-section-draft-contract.md) | The `apeCAD.section-draft` v1 contract | Accepted |
| [0026](0026-section-transport-and-client.md) | Stateless op transport and a 2-D section client | Accepted |
| [0027](0027-atomic-ops.md) | Ops are atomic; a refused op changes nothing | Accepted |
| [0028](0028-agent-surface-mcp.md) | One op catalog behind every surface; MCP, render and query tools | Accepted |
| [0029](0029-delete-takes-the-brep-subtree.md) | Delete takes the selection's whole B-rep subtree | Accepted |
| [0030](0030-one-gesture-one-op.md) | One drawing gesture is one op: creation ops take vertex references | Accepted |
| [0031](0031-ape-design-system.md) | The APE design system: UI tokens, UI voice and drawing output style | Accepted |
| [0032](0032-exact-collinear-bar-layouts.md) | Bar layouts snap to a lattice so inclined rows stay exactly collinear | Accepted |
| [0033](0033-ape-drawing-style-errata.md) | APE drawing style errata: cover guide ink and projection weights | Accepted |
| [0034](0034-dxf-export.md) | DXF export of the drawing (stage D5): ezdxf behind an optional extra, office layers | Accepted |
| [0035](0035-scratchpad-store-and-reconciler.md) | Scratchpad state store, two-signature reconciler, and dirty-flagged render loop | Accepted |
| [0036](0036-screen-space-lines-and-triangulation.md) | Ear-clipping triangulation, screen-space LineSegments2, and SelectionHalo | Accepted |
| [0037](0037-cad-turntable-and-svg-viewcube.md) | Cursor-pivot zero-roll Z-up CAD turntable and zero-GL 26-zone SVG ViewCube | Accepted |
| [0038](0038-visual-and-contrast-gates.md) | Programmatic WCAG/CVD token gates and deterministic still capture | Accepted |

## Template

```markdown
# ADR NNNN — short title

**Status:** Proposed | Accepted (YYYY-MM-DD)

## Context

What was at stake.

## Decision

What we chose.

## Alternatives rejected

| Rejected | Why |
|---|---|
| … | … |

## Consequences

What this forces on the code and on later ADRs.
```
