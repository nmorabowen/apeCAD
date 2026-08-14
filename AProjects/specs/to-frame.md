# Spec — `to_frame()`

**Status:** Implemented (2026-08-14)  
**ADRs:** 0002, 0004, 0006

## Goal

Project a document into a **frame graph** apeSteel can consume later:
nodes, members, axes, lengths in millimetres. No apeSteel import.
Section catalog ids are optional (`None` until a later tagging convention).

## Mapping

| Draft | Frame |
|---|---|
| Point | Node |
| Line | One member, axis = end − start |
| Polyline | One member per segment; if `closed`, last→first |
| Box | Volume leftover (not a member) |
| Tag | Copied onto any node/member whose entity sits in the tag |

Fail loud on a zero-length segment.

## Out of scope

apeSteel `Element` construction, section catalogs, `to_gmsh`, GUI.
