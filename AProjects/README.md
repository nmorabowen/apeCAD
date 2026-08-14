# AProjects

Working memory for apeCAD. This folder is the project brain: why decisions
were made, what the product is, and how agents and humans should continue.

Published user docs, when they exist, live under `docs/`. Code lives under
`src/`. **Facts about intent belong here**, not in chat logs.

| Folder | Holds |
|---|---|
| [`memory/`](memory/README.md) | Standing context: product intent, glossary, coupling map |
| [`adrs/`](adrs/README.md) | Architecture Decision Records (append-only) |
| [`specs/`](specs/README.md) | Specifications for slices (v0 document, bridges, scratchpad) |
| [`guides/`](guides/README.md) | How to work in this repo (agents and humans) |

## Rules

1. One fact, one home. If an ADR decides it, do not re-decide it in a spec.
2. ADRs are append-only. Amend with a new ADR; do not rewrite history.
3. Memory notes are living. ADRs are not.
4. Keep notes short. Link to ADRs instead of restating them.
5. Chili3D, SolveSpace, and ArcCAD are **principle sources only**. Do not
   copy their source into this tree ([ADR 0007](adrs/0007-clean-room-inspiration.md)).
