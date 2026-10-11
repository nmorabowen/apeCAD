"""Mutable entity store behind a Document. Only op handlers mutate it."""

from __future__ import annotations

from typing import Protocol

from apeCAD.entities import (
    Arc,
    Bezier,
    Circle,
    Ellipse,
    Entity,
    EntityId,
    Face,
    Line,
    Point,
    Polyline,
    Solid,
)
from apeCAD.errors import DocumentError
from apeCAD.geometry import XYZ


class Produced(Protocol):
    """A committed op that names the entity it created."""

    @property
    def entity_id(self) -> EntityId | None: ...


def produced_id(op: Produced) -> EntityId:
    if op.entity_id is None:
        raise DocumentError("internal error: committed op is missing entity_id")
    return op.entity_id


class DraftState:
    """Entities, labels, tags, and the id counter. Replaying the ops log rebuilds it."""

    def __init__(self) -> None:
        self.next_id: EntityId = 1
        self.entities: dict[EntityId, Entity] = {}
        self.labels: dict[str, EntityId] = {}
        self.tags: dict[str, set[EntityId]] = {}

    def copy(self) -> DraftState:
        """An independent trial copy. Entities are frozen, so sharing them is safe."""
        trial = DraftState()
        trial.next_id = self.next_id
        trial.entities = dict(self.entities)
        trial.labels = dict(self.labels)
        trial.tags = {name: set(members) for name, members in self.tags.items()}
        return trial

    def entity(self, entity_id: EntityId) -> Entity:
        try:
            return self.entities[entity_id]
        except KeyError as exc:
            raise DocumentError(f"unknown entity id {entity_id}") from exc

    def ordered(self) -> tuple[Entity, ...]:
        return tuple(self.entities[entity_id] for entity_id in sorted(self.entities))

    def points(self) -> tuple[Point, ...]:
        return tuple(e for e in self.ordered() if isinstance(e, Point))

    def require_point(self, entity_id: EntityId) -> Point:
        entity = self.entities.get(entity_id)
        if not isinstance(entity, Point):
            raise DocumentError(f"entity {entity_id} is not a point")
        return entity

    def allocate_id(self, requested: EntityId | None) -> EntityId:
        if requested is None:
            entity_id = self.next_id
            self.next_id += 1
            return entity_id
        if requested < 1:
            raise DocumentError(f"entity_id must be positive, got {requested}")
        if requested in self.entities:
            raise DocumentError(f"entity id {requested} already exists")
        if requested >= self.next_id:
            self.next_id = requested + 1
        return requested

    def register_label(self, entity_id: EntityId, label: str | None) -> None:
        if label is None:
            return
        existing = self.labels.get(label)
        if existing is not None:
            raise DocumentError(f"label {label!r} already belongs to entity {existing}")
        self.labels[label] = entity_id

    def reject_taken_label(self, label: str | None) -> None:
        if label is None:
            return
        existing = self.labels.get(label)
        if existing is not None:
            raise DocumentError(f"label {label!r} already belongs to entity {existing}")

    def drop_entity(self, entity_id: EntityId) -> None:
        entity = self.entities.pop(entity_id)
        if entity.label is not None:
            self.labels.pop(entity.label, None)
        empty_tags: list[str] = []
        for name, members in self.tags.items():
            members.discard(entity_id)
            if not members:
                empty_tags.append(name)
        for name in empty_tags:
            del self.tags[name]

    def point_at(
        self,
        x_mm: float,
        y_mm: float,
        z_mm: float,
        *,
        requested: EntityId | None,
        tolerance_mm: float = 1.0,
    ) -> tuple[EntityId, bool]:
        """Reuse a point within tolerance, else create an unlabelled one."""
        for point in self.points():
            dx = point.xyz_mm.x_mm - x_mm
            dy = point.xyz_mm.y_mm - y_mm
            dz = point.xyz_mm.z_mm - z_mm
            if dx * dx + dy * dy + dz * dz <= tolerance_mm * tolerance_mm:
                return point.entity_id, False
        entity_id = self.allocate_id(requested)
        self.entities[entity_id] = Point(
            entity_id=entity_id,
            xyz_mm=XYZ(x_mm, y_mm, z_mm),
            label=None,
        )
        return entity_id, True

    def point_ids_of(self, entity: Entity) -> tuple[EntityId, ...]:
        if isinstance(entity, Point):
            return (entity.entity_id,)
        if isinstance(entity, Line):
            return (entity.start_id, entity.end_id)
        if isinstance(entity, (Polyline, Face, Bezier)):
            return entity.point_ids
        if isinstance(entity, (Circle, Ellipse)):
            return (entity.center_id,)
        if isinstance(entity, Arc):
            return (entity.start_id, entity.mid_id, entity.end_id)
        if isinstance(entity, Solid):
            ids = list(self.point_ids_of(self.entity(entity.face_id)))
            if entity.cap_id is not None:
                ids.extend(self.point_ids_of(self.entity(entity.cap_id)))
            return tuple(dict.fromkeys(ids))
        return ()

    def line_between(self, start_id: EntityId, end_id: EntityId) -> Line | None:
        edge = {start_id, end_id}
        for entity in self.entities.values():
            if isinstance(entity, Line) and {entity.start_id, entity.end_id} == edge:
                return entity
        return None
