"""What agents read about a draft: entity kinds, bounding boxes, items and `inspect` (§4)."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import cast

from apeCAD.agent.session import Session
from apeCAD.brep import BrepIndex
from apeCAD.document import Document
from apeCAD.entities import Arc, Bezier, Box, Circle, Ellipse, Entity, EntityId, Line, Point, Solid
from apeCAD.geometry import XYZ
from apeCAD.ops import UNITS
from apeCAD.render.tessellate import arc_points, bezier_points
from apeCAD.render.views import Vec3

KINDS = ("point", "line", "polyline", "box", "face", "solid", "circle", "arc", "ellipse", "bezier")
"""The kinds `inspect.counts` always lists, even at zero. A newer kind is listed when present."""

Bbox = tuple[Vec3, Vec3]


def kind_of(entity: Entity) -> str:
    return type(entity).__name__.lower()


def entity_map(document: Document) -> dict[EntityId, Entity]:
    return {entity_id: document.entity(entity_id) for entity_id in sorted(document.entity_ids())}


class Extents:
    """Axis-aligned bounding boxes in mm, memoised per entity.

    Points, boxes and curves use their own geometry (an arc or Bézier its tessellation, so
    a Bézier's control points do not widen it). Lines, polylines, faces and solids take the
    union of what they are built from in the B-rep.
    """

    def __init__(self, entities: Mapping[EntityId, Entity], brep: BrepIndex) -> None:
        self._entities = entities
        self._children = brep.children
        self._memo: dict[EntityId, Bbox | None] = {}

    def of(self, entity_id: EntityId) -> Bbox | None:
        if entity_id in self._memo:
            return self._memo[entity_id]
        self._memo[entity_id] = None  # a cycle reads as "no extent" instead of recursing
        entity = self._entities.get(entity_id)
        found = None if entity is None else self._own(entity)
        self._memo[entity_id] = found
        return found

    def union(self, ids: list[EntityId]) -> Bbox | None:
        return _union([self.of(entity_id) for entity_id in ids])

    def _own(self, entity: Entity) -> Bbox | None:
        if isinstance(entity, Point):
            xyz = entity.xyz_mm.to_tuple()
            return xyz, xyz
        if isinstance(entity, Box):
            origin = entity.origin_xyz_mm.to_tuple()
            size = entity.size_xyz_mm.to_tuple()
            far = (origin[0] + size[0], origin[1] + size[1], origin[2] + size[2])
            return _of_points([origin, far])
        if isinstance(entity, (Circle, Ellipse)):
            center = self._xyz(entity.center_id)
            if center is None:
                return None
            if isinstance(entity, Circle):
                rx = ry = entity.radius_mm
            else:
                rx, ry = entity.radius_x_mm, entity.radius_y_mm
            cx, cy, cz = center
            return (cx - rx, cy - ry, cz), (cx + rx, cy + ry, cz)
        if isinstance(entity, Arc):
            ends = [self._xyz(i) for i in (entity.start_id, entity.mid_id, entity.end_id)]
            if ends[0] is None or ends[1] is None or ends[2] is None:
                return None
            return _of_points(arc_points(ends[0], ends[1], ends[2], None))
        if isinstance(entity, Bezier):
            controls = [self._xyz(i) for i in entity.point_ids]
            known = [xyz for xyz in controls if xyz is not None]
            if not known or len(known) != len(controls):
                return None
            return _of_points(bezier_points(known, None))
        return self.union(list(self._children.get(entity.entity_id, ())))

    def _xyz(self, entity_id: EntityId) -> Vec3 | None:
        entity = self._entities.get(entity_id)
        return entity.xyz_mm.to_tuple() if isinstance(entity, Point) else None


def _of_points(points: list[Vec3]) -> Bbox | None:
    if not points:
        return None
    low = (min(p[0] for p in points), min(p[1] for p in points), min(p[2] for p in points))
    high = (max(p[0] for p in points), max(p[1] for p in points), max(p[2] for p in points))
    return low, high


def _union(boxes: list[Bbox | None]) -> Bbox | None:
    corners = [corner for box in boxes if box is not None for corner in box]
    return _of_points(corners)


def bbox_json(box: Bbox | None) -> dict[str, list[float]] | None:
    if box is None:
        return None
    return {"min": list(box[0]), "max": list(box[1])}


def _json_value(value: object) -> object:
    if isinstance(value, XYZ):
        return list(value.to_tuple())
    if isinstance(value, tuple):
        return [_json_value(item) for item in cast(tuple[object, ...], value)]
    return value


def summary_item(
    entity: Entity, tags: Mapping[str, frozenset[EntityId]], extents: Extents
) -> dict[str, object]:
    eid = entity.entity_id
    return {
        "id": eid,
        "kind": kind_of(entity),
        "label": entity.label,
        "tags": sorted(name for name, ids in tags.items() if eid in ids),
        "bbox_mm": bbox_json(extents.of(eid)),
    }


def full_item(
    entity: Entity,
    tags: Mapping[str, frozenset[EntityId]],
    extents: Extents,
    brep: BrepIndex,
) -> dict[str, object]:
    """The summary plus the entity's own fields (scene payload names) and its B-rep links."""
    item = summary_item(entity, tags, extents)
    for field in dataclasses.fields(entity):
        if field.name not in ("entity_id", "label"):
            item[field.name] = _json_value(getattr(entity, field.name))
    item["brep_parents"] = list(brep.parents.get(entity.entity_id, ()))
    item["brep_children"] = list(brep.children.get(entity.entity_id, ()))
    return item


def inspect_payload(session: Session) -> dict[str, object]:
    """Counts, extents, labels, tags and a B-rep summary of the session's draft.

    `brep` counts solids (and legacy boxes), then the faces, lines and points that belong to
    a solid; `free_lines` counts lines that bound no face.
    """
    document = session.document
    entities = entity_map(document)
    brep = document.brep()
    counts: dict[str, int] = dict.fromkeys(KINDS, 0)
    for entity in entities.values():
        counts[kind_of(entity)] = counts.get(kind_of(entity), 0) + 1
    in_solid = set(brep.solid)
    owned = {kind: 0 for kind in ("face", "line", "point")}
    for entity_id, entity in entities.items():
        if entity_id in in_solid and kind_of(entity) in owned:
            owned[kind_of(entity)] += 1
    free_lines = sum(
        1
        for entity_id, entity in entities.items()
        if isinstance(entity, Line)
        and not any(kind_of(entities[p]) == "face" for p in brep.parents.get(entity_id, ()))
    )
    labels = {e.label: e.entity_id for e in entities.values() if e.label is not None}
    return {
        "units": UNITS,
        "ops": len(document.ops()),
        "counts": counts,
        "extents_mm": bbox_json(Extents(entities, brep).union(list(entities))),
        "labels": dict(sorted(labels.items())),
        "tags": {name: sorted(ids) for name, ids in document.tags().items()},
        "brep": {
            "solids": sum(1 for e in entities.values() if isinstance(e, (Solid, Box))),
            "faces": owned["face"],
            "edges": owned["line"],
            "vertices": owned["point"],
            "free_lines": free_lines,
        },
        "can_undo": session.can_undo,
        "can_redo": session.can_redo,
    }
