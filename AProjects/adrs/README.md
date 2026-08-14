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
