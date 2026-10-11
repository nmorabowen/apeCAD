"""Handlers for identity and lifetime: delete, tag, set label."""

from __future__ import annotations

from dataclasses import replace

from apeCAD.brep import build_brep
from apeCAD.draft.state import DraftState
from apeCAD.draft.topology import referenced_ids
from apeCAD.entities import EntityId, Solid
from apeCAD.errors import DocumentError
from apeCAD.ops import Delete, SetLabel, Tag


def delete(state: DraftState, op: Delete) -> Delete:
    """Remove the selected entities with their whole B-rep subtree (ADR 0029).

    Computed on the state before anything is dropped:

    - **named**: the op's ids, plus every entity that references one of them (a line
      whose endpoint goes, a face that loses a vertex, a solid whose profile goes), to
      a fixpoint. These are always removed.
    - **parts**: the B-rep children (``brep.build_brep``), recursively, of the op's own
      ids and of every solid in *named*: a solid's profile, cap and walls; a face's
      edges; a line's endpoints; a circle's centre. An entity that dies only because it
      lost a part (a face missing a corner) does not take its own parts with it; a
      solid does, because it owns its profile, cap and walls.
    - A part **survives** if anything left in the draft still uses it (an edge shared
      with a kept face, a point a kept line ends at), and so do its own parts.
    """
    for entity_id in op.entity_ids:
        if entity_id not in state.entities:
            raise DocumentError(f"unknown entity id {entity_id}")
    named = _with_dependents(state, set(op.entity_ids))
    owners = set(op.entity_ids) | {
        entity_id for entity_id in named if isinstance(state.entities[entity_id], Solid)
    }
    children = build_brep(state.entities).children
    parts = _descendants(children, owners) - named
    kept_parts = _still_used(state, children, named, parts)
    for entity_id in sorted(named | (parts - kept_parts)):
        state.drop_entity(entity_id)
    return op


def tag(state: DraftState, op: Tag) -> Tag:
    for entity_id in op.entity_ids:
        if entity_id not in state.entities:
            raise DocumentError(f"cannot tag unknown entity id {entity_id}")
    members = state.tags.setdefault(op.name, set())
    members.update(op.entity_ids)
    return op


def set_label(state: DraftState, op: SetLabel) -> SetLabel:
    entity = state.entity(op.entity_id)
    if entity.label == op.label:
        return op
    if entity.label is not None:
        state.labels.pop(entity.label, None)
    state.reject_taken_label(op.label)
    state.register_label(op.entity_id, op.label)
    state.entities[op.entity_id] = replace(entity, label=op.label)
    return op


def _with_dependents(state: DraftState, named: set[EntityId]) -> set[EntityId]:
    """Grow the set with every entity that references a member, to a fixpoint."""
    grown = set(named)
    changed = True
    while changed:
        changed = False
        for entity in state.entities.values():
            if entity.entity_id in grown:
                continue
            if grown.intersection(referenced_ids(entity)):
                grown.add(entity.entity_id)
                changed = True
    return grown


def _descendants(
    children: dict[EntityId, tuple[EntityId, ...]], roots: set[EntityId]
) -> set[EntityId]:
    found: set[EntityId] = set()
    stack = [child for root in roots for child in children.get(root, ())]
    while stack:
        entity_id = stack.pop()
        if entity_id in found or entity_id in roots:
            continue
        found.add(entity_id)
        stack.extend(children.get(entity_id, ()))
    return found


def _still_used(
    state: DraftState,
    children: dict[EntityId, tuple[EntityId, ...]],
    named: set[EntityId],
    parts: set[EntityId],
) -> set[EntityId]:
    """Parts some surviving entity still uses, with their own parts, to a fixpoint."""
    kept: set[EntityId] = set()
    survivors = set(state.entities) - named - parts
    frontier = set(survivors)
    while frontier:
        used: set[EntityId] = set()
        for entity_id in frontier:
            used.update(children.get(entity_id, ()))
            used.update(referenced_ids(state.entities[entity_id]))
        frontier = (used & parts) - kept
        kept |= frontier
    return kept
