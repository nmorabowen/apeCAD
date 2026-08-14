# Spec — v0 document

**Status:** Implemented (2026-08-14)  
**ADRs:** 0002, 0004, 0006

## Goal

A kernel-free Python `Document` that can hold a spatial draft and
round-trip through JSON. No GUI, no Gmsh, no OCCT.

## Entities (minimum)

| Kind | Fields (intent) |
|---|---|
| Point | id, xyz (mm), label? |
| Line | id, start, end, label? |
| Polyline | id, points, closed?, label? |
| Box | id, origin, size, label? |
| Tag / layer | name, entity ids |

## Operations

Append-only log. Each op is typed, serializable, and undoable by
inverse or by replay.

Minimum verbs: `AddPoint`, `AddLine`, `AddBox`, `Tag`.

## Out of scope

[`to_gmsh`, `to_frame`](to-frame.md) are specified separately. Tessellation
and GUI remain out of scope.
