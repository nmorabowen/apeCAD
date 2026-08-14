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
