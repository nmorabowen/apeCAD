"""Handlers for identity and lifetime: delete, tag, set label."""

from __future__ import annotations

from dataclasses import replace

from apeCAD.draft.state import DraftState
from apeCAD.draft.topology import referenced_ids
from apeCAD.entities import EntityId, Face, Point, Solid
from apeCAD.errors import DocumentError
from apeCAD.ops import Delete, SetLabel, Tag


def delete(state: DraftState, op: Delete) -> Delete:
    for entity_id in op.entity_ids:
        if entity_id not in state.entities:
            raise DocumentError(f"unknown entity id {entity_id}")
    doomed: set[EntityId] = set(op.entity_ids)
    _expand_doomed(state, doomed)
    attached: set[EntityId] = set()
    for entity_id in doomed:
        attached.update(referenced_ids(state.entities[entity_id]))
    for entity_id in list(doomed):
        state.drop_entity(entity_id)
    still_used: set[EntityId] = set()
    for entity in state.entities.values():
        still_used.update(referenced_ids(entity))
    for point_id in attached:
        leftover = state.entities.get(point_id)
        if isinstance(leftover, Point) and point_id not in still_used:
            state.drop_entity(point_id)
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


def _live_face_uses_edge(
    state: DraftState,
    start_id: EntityId,
    end_id: EntityId,
    doomed: set[EntityId],
) -> bool:
    edge = {start_id, end_id}
    for entity in state.entities.values():
        if entity.entity_id in doomed or not isinstance(entity, Face):
            continue
        ids = entity.point_ids
        for index, point_id in enumerate(ids):
            if {point_id, ids[(index + 1) % len(ids)]} == edge:
                return True
    return False


def _expand_doomed(state: DraftState, doomed: set[EntityId]) -> None:
    """Grow the delete set: solids take caps, walls, and edges no live face uses."""
    changed = True
    while changed:
        changed = False
        for entity in list(state.entities.values()):
            if entity.entity_id not in doomed or not isinstance(entity, Solid):
                continue
            if entity.cap_id is not None and entity.cap_id not in doomed:
                doomed.add(entity.cap_id)
                changed = True
            for wall_id in entity.wall_ids:
                if wall_id not in doomed:
                    doomed.add(wall_id)
                    changed = True
            for face_id in (entity.cap_id, *entity.wall_ids):
                if face_id is None:
                    continue
                face = state.entities.get(face_id)
                if not isinstance(face, Face):
                    continue
                ids = face.point_ids
                for index, start_id in enumerate(ids):
                    end_id = ids[(index + 1) % len(ids)]
                    if _live_face_uses_edge(state, start_id, end_id, doomed):
                        continue
                    line = state.line_between(start_id, end_id)
                    if line is not None and line.entity_id not in doomed:
                        doomed.add(line.entity_id)
                        changed = True
        for entity in list(state.entities.values()):
            if entity.entity_id in doomed:
                continue
            if doomed.intersection(referenced_ids(entity)):
                doomed.add(entity.entity_id)
                changed = True
