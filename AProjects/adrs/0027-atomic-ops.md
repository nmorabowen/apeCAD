# ADR 0027 — Ops are atomic; a refused op changes nothing

**Status:** Proposed (2026-10-10)

Amends [ADR 0007](0007-clean-room-inspiration.md): its list of principle sources gains
**cadcraft** (validate on a trial copy, then commit). Principles only, no code.

## Context

[ADR 0006](0006-one-source-of-truth.md) makes the ops log the only writer: undo replays it,
and JSON is the log. That holds only if the live `Document` always equals a replay of its own
log. [ADR 0026](0026-section-transport-and-client.md) makes it a hard contract: the stateless
transport rebuilds the document from the log on every request, so any gap between the live
document and the replay shows up as the drawing changing between two calls.

After [ADR 0023](0023-module-boundaries.md), `Document._apply` passed the live `DraftState`
straight to a handler. Handlers validate as they go. When a handler raised `DocumentError`
after it had started to mutate, the op was refused and not logged, but its partial edits
stayed in the live state.

Repro on `main` at `f5963ec`: points p1 (0, 0), p2 (1000, 0), p3 (1000, 0.5); face
[p1, p2, p3]; points q1 (0.2, 0), q2 (−3000, 0); line q1→q2; then `sew([line, face])`. It
raises "sew would collapse a face", but q1 has already been absorbed into p1. The live
document has 4 points. `Document.from_json(doc.to_json())` has 5.

Sew is not the only case. On the old `_apply`, the hostile-params test in
`tests/test_atomic_ops.py` breaks this contract for AddBox, Sew, Translate, Rotate, Mirror,
ArrayLinear, ArrayPolar and SetLabel. It also found two crashes that escaped as
`OverflowError` instead of a refusal: `Extrude.__post_init__` squared a 1e300 direction, and
InsertNode squared a 1e300 distance.

cadcraft (Apache-2.0 / MIT, github.com/storytold/cadcraft), a Rust AutoCAD-style CAD, runs
every command on a trial copy of the drawing. It checks that the result is finite and commits
only on success. We take that principle. We did not read or copy its code.

## Decision

1. **Every op runs on a trial copy.** `Document._apply` calls `DraftState.copy()` and runs the
   handler on the copy. It swaps the copy in only after the handler returns and the guard
   passes. On any failure the live state and the log are untouched. Entities are frozen
   dataclasses, so the copy is shallow: new entity and label dicts, and new tag sets.
2. **A post-op guard (`draft/invariants.py`, `check_state`).** It is cadcraft's "finite
   guard" plus referential integrity. After the handler returns, it checks that:
   - every float of a new or changed entity is finite, including each `XYZ` component;
   - every id an entity references exists;
   - every label points at an entity that carries that label;
   - every tag member exists;
   - each entity is stored under its own id, and that id is below `next_id`.

   A violation raises `DocumentError`, and step 1 discards the trial.
3. **Float overflow is a refusal.** An `ArithmeticError` raised inside a handler becomes
   `DocumentError`. `Extrude` checks its direction with `math.hypot`, which cannot overflow.
4. **A failed redo keeps its op.** `redo()` pops the op only after it commits.
5. **Whole-log replay is checked once.** `from_dict` and undo replay the log into one fresh
   state, run the guard once at the end, then swap it in. A load that fails is thrown away as
   a whole, so per-op copies would buy nothing. They would make replay quadratic: a 500-op
   log took 38 ms with a copy per op, against 4.8 ms with one guard at the end (3.4 ms before
   this change).

## Alternatives rejected

| Rejected | Why |
|---|---|
| Make each handler validate everything before it mutates | 27 handlers to audit by hand, and every new op could reintroduce the bug. The trial copy fixes the whole class in one place. |
| Snapshot, then restore on exception | Equivalent, but the trial copy cannot leave a half-restored state, and it makes "commit" one assignment. |
| Undo the partial edit by replaying the log after a failure | O(log length) on every refusal, and it hides the bug instead of preventing it. |
| Guard only `Point` coordinates | `XYZ` already rejects non-finite values. The gaps are scalar fields (`radius_mm`, `distance_mm`) and dangling ids after topology surgery. |

## Consequences

- Live equals replay is now a tested property. `tests/test_atomic_ops.py` samples hostile
  params for every row of `draft.dispatch.HANDLERS`, plus targeted geometry edge cases. Each
  op is either refused with `to_json()` and the live state byte-identical, or it succeeds and
  its replay matches the live state. A new op gets this coverage when it gets its `HANDLERS`
  row.
- Each interactive op now costs a shallow O(n) copy and an O(n) guard. That is fine at
  scratchpad sizes. If a profile ever shows it, the guard can narrow to the entities the op
  changed.
- Handlers may keep validating as they go. Partial mutation before a raise is now harmless,
  and a handler should not add its own rollback.
- When this ADR is accepted, ADR 0007's status line and its README row should say
  "Amended by 0027", as ADR 0015 does for 0017.
