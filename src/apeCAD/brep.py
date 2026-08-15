"""Evaluated B-rep: vertices, edges, faces, and the solid they belong to."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass

from apeCAD.entities import (
    Arc,
    Bezier,
    Box,
    Circle,
    Ellipse,
    Entity,
    EntityId,
    Face,
    Line,
    Polyline,
    Solid,
)


@dataclass(frozen=True, slots=True)
class BrepIndex:
    """Parent/child graph derived from Face loops and Solid membership."""

    children: dict[EntityId, tuple[EntityId, ...]]
    parents: dict[EntityId, tuple[EntityId, ...]]
    root: dict[EntityId, EntityId]
    solid: dict[EntityId, EntityId]

    def to_payload(self) -> dict[str, object]:
        def as_lists(
            mapping: dict[EntityId, tuple[EntityId, ...]],
        ) -> dict[str, list[int]]:
            return {str(key): list(value) for key, value in sorted(mapping.items())}

        def as_ids(mapping: dict[EntityId, EntityId]) -> dict[str, int]:
            return {str(key): value for key, value in sorted(mapping.items())}

        return {
            "children": as_lists(self.children),
            "parents": as_lists(self.parents),
            "root": as_ids(self.root),
            "solid": as_ids(self.solid),
        }


def build_brep(entities: Mapping[EntityId, Entity]) -> BrepIndex:
    children: dict[EntityId, tuple[EntityId, ...]] = {}
    parent_lists: dict[EntityId, list[EntityId]] = defaultdict(list)
    for entity_id, entity in entities.items():
        kids = _children_of(entities, entity)
        children[entity_id] = kids
        for child_id in kids:
            if entity_id not in parent_lists[child_id]:
                parent_lists[child_id].append(entity_id)
    parents = {key: tuple(value) for key, value in parent_lists.items()}
    root: dict[EntityId, EntityId] = {}
    solid: dict[EntityId, EntityId] = {}
    for entity_id in entities:
        root[entity_id] = _walk_root(entity_id, parents, entities)
        owner = _owning_solid(entity_id, parents, entities)
        if owner is not None:
            solid[entity_id] = owner
    return BrepIndex(children=children, parents=parents, root=root, solid=solid)


def _line_between(
    entities: Mapping[EntityId, Entity],
    start_id: EntityId,
    end_id: EntityId,
) -> Line | None:
    edge = {start_id, end_id}
    for entity in entities.values():
        if isinstance(entity, Line) and {entity.start_id, entity.end_id} == edge:
            return entity
    return None


def _children_of(
    entities: Mapping[EntityId, Entity],
    entity: Entity,
) -> tuple[EntityId, ...]:
    if isinstance(entity, Solid):
        ids = [entity.face_id, *entity.wall_ids]
        if entity.cap_id is not None:
            ids.append(entity.cap_id)
        return tuple(entity_id for entity_id in ids if entity_id in entities)
    if isinstance(entity, Face):
        point_ids = entity.point_ids
        if len(point_ids) < 2:
            return tuple(pid for pid in point_ids if pid in entities)
        edges: list[EntityId] = []
        for index, start_id in enumerate(point_ids):
            end_id = point_ids[(index + 1) % len(point_ids)]
            line = _line_between(entities, start_id, end_id)
            if line is None:
                return tuple(pid for pid in point_ids if pid in entities)
            edges.append(line.entity_id)
        return tuple(edges)
    if isinstance(entity, Line):
        return (entity.start_id, entity.end_id)
    if isinstance(entity, (Circle, Ellipse)):
        return (entity.center_id,)
    if isinstance(entity, Arc):
        return (entity.start_id, entity.mid_id, entity.end_id)
    if isinstance(entity, (Polyline, Bezier)):
        return tuple(pid for pid in entity.point_ids if pid in entities)
    return ()


def _walk_root(
    entity_id: EntityId,
    parents: dict[EntityId, tuple[EntityId, ...]],
    entities: Mapping[EntityId, Entity],
) -> EntityId:
    seen: set[EntityId] = set()
    current = entity_id
    while True:
        options = parents.get(current, ())
        if not options:
            return current
        solid = next(
            (
                parent_id
                for parent_id in options
                if isinstance(entities.get(parent_id), (Solid, Box))
            ),
            None,
        )
        nxt = solid if solid is not None else options[0]
        if nxt in seen:
            return current
        seen.add(current)
        current = nxt


def _owning_solid(
    entity_id: EntityId,
    parents: dict[EntityId, tuple[EntityId, ...]],
    entities: Mapping[EntityId, Entity],
) -> EntityId | None:
    stack = list(parents.get(entity_id, ()))
    seen: set[EntityId] = set()
    while stack:
        parent_id = stack.pop()
        if parent_id in seen:
            continue
        seen.add(parent_id)
        entity = entities.get(parent_id)
        if isinstance(entity, Solid):
            return parent_id
        stack.extend(parents.get(parent_id, ()))
    return None
