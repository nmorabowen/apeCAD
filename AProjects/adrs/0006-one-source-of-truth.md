# ADR 0006 — One writer: the Python ops API; JSON is a file format

**Status:** Accepted (2026-08-14)

## Context

A dual “edit Python or edit JSON” surface would fork the draft: humans
draw into a scene file while agents edit a script, and neither is
replayable as the other. apeSteel’s unit system is N-mm-tonne-s.
apeGmsh is units-agnostic. The document needs one writer and one
internal unit.

## Decision

1. The **Python ops API** is the only writer. Undo is the ops log.
2. **JSON** (or a later binary) is serialization for save/load and for
   agents that prefer a file snapshot. It is not a parallel editor.
3. Internal units are **millimetres**, aligned with apeSteel’s
   N-mm-tonne-s. The apeGmsh bridge states any conversion explicitly.
4. Every entity has a **label** (or is unnamed until labeled). Names
   are the handle for agents and for Studio.

## Alternatives rejected

| Rejected | Why |
|---|---|
| JSON scene as a second SoT | Two drafts, neither replayable |
| Viewer mutating OCC / `model.h5` | Studio 0095 already forbids that path |
| Unitless document | Breaks apeSteel coupling |

## Consequences

`Document.to_json()` / `from_json()` are round-trips of the ops API,
not a separate schema family. Bridge code must not invent a second
identity system besides labels.
