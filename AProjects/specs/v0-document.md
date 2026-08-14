# Spec — v0 document

**Status:** Draft  
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

GUI, snap, constraints, booleans, `to_gmsh`, `to_frame`, tessellation.

Those get their own specs after this document exists and has tests.
