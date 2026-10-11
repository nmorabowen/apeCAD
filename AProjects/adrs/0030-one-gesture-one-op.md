# ADR 0030 — One drawing gesture is one op: creation ops take vertex references

**Status:** Proposed (2026-10-10)

Applies [ADR 0024](0024-section-mode-rc-intent.md) decision 3 ("one gesture is one composite
op") to the scratchpad's existing draw tools. Extends the `apeCAD.document.v0` codec
additively (see Consequences).

## Context

The owner reported that Ctrl+Z leaves pieces of a shape behind. The cause is
the client, not undo: every draw tool posted several ops per gesture. `ensurePoint` in
`static/js/create.js` posted an `AddPoint` per new vertex, then the tool posted the shape.
A box was `AddPoint` ×4, `AddFace`, `Extrude`: six ops, so six undos, and the first five
each left a face, then points, behind. Rect, polygon, circle, ellipse, arc, Bézier and
polyline did the same, and the line tool posted one `AddLine` per click.

Undo is a replay of the log ([ADR 0006](0006-one-source-of-truth.md)), so the history unit is
the op. The fix is to make the gesture one op. Short logs also matter on their own: the
stateless transport replays the whole log on every call
([ADR 0026](0026-section-transport-and-client.md)).

## Decision

1. **A vertex reference is a point id or coordinates.** Creation ops (`AddLine`,
   `AddPolyline`, `AddFace`, `AddCircle`, `AddEllipse`, `AddArc`, `AddBezier`, and the two
   below) accept, wherever they took a point id:
   - an existing point id: a plain integer, as in v0, or `{"id": n}`;
   - coordinates: `{"xyz": [x, y, z]}` in millimetres.

   In Python the field type is `VertexRef = EntityId | PointAt`
   (`apeCAD.ops.types`). Field names do not change: `point_ids`, `start_id`, `center_id`
   and so on now hold vertex references.
2. **The server resolves coordinates with the client's old 1 mm reuse.** The handler calls
   `DraftState.point_at` with its default 1 mm tolerance: an existing point within 1 mm is
   reused, else an unlabelled point is created. Vertices resolve in order, so a later vertex
   can reuse a point an earlier vertex of the same op created. Collapsed vertices (two refs
   onto one point where the entity needs distinct points) are refused, and the op is atomic
   ([ADR 0027](0027-atomic-ops.md)).
3. **The committed op records what it resolved, so replay is deterministic.** Like
   `ChamferCorner` records `start_id`/`end_id`, the committed op stores a reused vertex as its
   plain id and a created one as `{"xyz": [...], "id": n}`. On input, `xyz` together with
   `id` means "create point n here", without searching; `id` already taken is refused.
4. **Two composite forms for gestures that span ops.**
   - **`AddLineChain`** `{point_ids, label, line_ids}`: one Line per consecutive vertex pair;
     `label` names the first line; the committed op records `line_ids`. The line tool
     buffers clicks client-side and posts the chain on Esc, Enter (with no typed length) or a
     tool switch. Ctrl+Z mid-chain takes back the last buffered vertex.
   - **`Extrude` with a `ring`**: `face_id: null` plus `ring: [vertex refs]` makes the face,
     then extrudes it. The committed op records the created face as `face_id` and keeps the
     resolved ring. The box tool posts this; the solid carries the label (the face no longer
     gets one). `AddBox` stays as AABB sugar for scripts.
5. **Each draw tool posts exactly one op.** Rect and polygon: `AddFace`. Circle, ellipse,
   arc, Bézier, polyline: their own op with vertex refs. Line chain: `AddLineChain`. Box:
   `Extrude` with a ring. The client sends a snapped point's id and otherwise coordinates
   (`vertexRef` in `static/js/geom.js`); it no longer posts `AddPoint`.
6. **A batch is still not a history unit.** The agent-surface spec
   ([ADR 0028](0028-agent-surface-mcp.md), `specs/agent-surface-mcp.md`) says one undo undoes
   one op, not a batch. This ADR does not change that: it makes the gesture one op instead
   of making undo group ops.

## Alternatives rejected

| Rejected | Why |
|---|---|
| Group ops into undo transactions (a "gesture id" on each op, undo pops the group) | A second history structure over the log, against ADR 0006 and the spec's "a batch is not a history unit". Still replays six ops per box on every transport call |
| Keep `AddPoint` ops but delete orphan points on undo | Undo stays a multi-step peel for faces and solids; orphan detection is policy the log cannot replay |
| Box as `AddBox` | `AddBox` is an AABB with positive size and exact-match point reuse; the box tool snaps corners to existing points and drags height up or down |
| New field names (`vertices`, `start`, `center`) next to the old ones | Two fields per vertex, both optional, and a rule for which wins. Widening the existing field keeps one name and keeps v0 documents byte-identical |
| Committed op stores only ids (drop the coordinates) | The points do not exist before the op runs, so a replay from an empty draft could not recreate them |
| Line tool posts `AddPolyline` | The line tool makes separate `Line` entities that trim, break, extend and face-from-lines act on; a polyline is a different entity |

## Consequences

- **`apeCAD.document.v0` gains forms, additively.** Every v0 document still parses and
  re-serializes byte-identically: a plain id is still written as a plain int, and `ring` is
  omitted (not `null`) on a face-only `Extrude`. New documents may contain `{"xyz", "id"}`
  objects in vertex fields, an `Extrude` with `ring` and `face_id`, and `AddLineChain` ops.
  An apeCAD that predates this ADR refuses those ops (its codec wants integers there) rather
  than misreading them. The schema id stays `v0`. A consumer that replays logs (apeSketch
  ADR 0008 routes `.ape.json` files by `schema`) must learn the vertex object and the two
  new forms before it reads documents drawn after this change.
- The hostile-params test (`tests/test_atomic_ops.py`) now generates vertex references,
  including coordinates on fixture points and requested ids, for every op that takes them.
- `Document` typed methods accept `VertexRef` where they took a point id, plus
  `add_line_chain` and `extrude(..., ring=...)`.
- Section mode (ADRs 0024–0026) can reuse `VertexRef` for its composite ops.
