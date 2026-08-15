"""Frame graph projected from a kernel-free draft. Units are millimetres."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from apeCAD.entities import Circle, Ellipse, EntityId, Face, Line, Point, Polyline, Solid
from apeCAD.errors import DocumentError
from apeCAD.geometry import XYZ
from apeCAD.ops import UNITS

if TYPE_CHECKING:
    from apeCAD.document import Document


@dataclass(frozen=True, slots=True)
class FrameNode:
    entity_id: EntityId
    xyz_mm: XYZ
    label: str | None
    tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FrameMember:
    entity_id: EntityId
    start_id: EntityId
    end_id: EntityId
    length_mm: float
    axis_xyz: XYZ
    label: str | None
    tags: tuple[str, ...]
    section_id: str | None = None
    segment_index: int | None = None


@dataclass(frozen=True, slots=True)
class FrameVolume:
    """A box in the draft. Not a frame member; kept so it is not dropped."""

    entity_id: EntityId
    origin_xyz_mm: XYZ
    size_xyz_mm: XYZ
    label: str | None
    tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FrameGraph:
    units: str
    nodes: tuple[FrameNode, ...]
    members: tuple[FrameMember, ...]
    volumes: tuple[FrameVolume, ...]

    def node(self, entity_id: EntityId) -> FrameNode:
        for node in self.nodes:
            if node.entity_id == entity_id:
                return node
        raise DocumentError(f"frame has no node {entity_id}")

    def member_by_label(self, label: str) -> FrameMember:
        matches = [member for member in self.members if member.label == label]
        if len(matches) != 1:
            raise DocumentError(f"expected one member labelled {label!r}, got {len(matches)}")
        return matches[0]


def document_to_frame(document: Document) -> FrameGraph:
    tags_by_entity = _tags_by_entity(document.tags())
    nodes = tuple(
        FrameNode(
            entity_id=point.entity_id,
            xyz_mm=point.xyz_mm,
            label=point.label,
            tags=_tags_for(point.entity_id, tags_by_entity),
        )
        for point in document.points()
    )
    points = {point.entity_id: point for point in document.points()}
    solid_edges = _solid_edge_keys(document)
    members: list[FrameMember] = []
    for line in document.lines():
        if frozenset((line.start_id, line.end_id)) in solid_edges:
            continue
        members.append(
            _member_from_segment(
                owner=line,
                start_id=line.start_id,
                end_id=line.end_id,
                points=points,
                tags_by_entity=tags_by_entity,
                segment_index=None,
            )
        )
    for polyline in document.polylines():
        members.extend(_members_from_polyline(polyline, points, tags_by_entity))
    volumes = tuple(_volumes_from_document(document, tags_by_entity))
    return FrameGraph(units=UNITS, nodes=nodes, members=tuple(members), volumes=volumes)


def _volumes_from_document(
    document: Document,
    tags_by_entity: dict[EntityId, tuple[str, ...]],
) -> list[FrameVolume]:
    volumes: list[FrameVolume] = []
    for box in document.boxes():
        volumes.append(
            FrameVolume(
                entity_id=box.entity_id,
                origin_xyz_mm=box.origin_xyz_mm,
                size_xyz_mm=box.size_xyz_mm,
                label=box.label,
                tags=_tags_for(box.entity_id, tags_by_entity),
            )
        )
    for solid in document.solids():
        volume = _solid_as_volume(document, solid, tags_by_entity)
        if volume is not None:
            volumes.append(volume)
    return volumes


def _solid_edge_keys(document: Document) -> set[frozenset[EntityId]]:
    keys: set[frozenset[EntityId]] = set()
    for solid in document.solids():
        face_ids = [solid.face_id, *solid.wall_ids]
        if solid.cap_id is not None:
            face_ids.append(solid.cap_id)
        for face_id in face_ids:
            face = document.entity(face_id)
            if not isinstance(face, Face):
                continue
            ids = face.point_ids
            count = len(ids)
            if count < 2:
                continue
            for index, start_id in enumerate(ids):
                keys.add(frozenset((start_id, ids[(index + 1) % count])))
    return keys


def _solid_as_volume(
    document: Document,
    solid: Solid,
    tags_by_entity: dict[EntityId, tuple[str, ...]],
) -> FrameVolume | None:
    face = document.entity(solid.face_id)
    if isinstance(face, Circle):
        center = document.entity(face.center_id)
        if not isinstance(center, Point):
            return None
        radius = face.radius_mm
        height = abs(solid.distance_mm)
        origin_z = center.xyz_mm.z_mm
        if solid.distance_mm < 0.0:
            origin_z -= height
        return FrameVolume(
            entity_id=solid.entity_id,
            origin_xyz_mm=XYZ(
                center.xyz_mm.x_mm - radius,
                center.xyz_mm.y_mm - radius,
                origin_z,
            ),
            size_xyz_mm=XYZ(radius * 2.0, radius * 2.0, height),
            label=solid.label,
            tags=_tags_for(solid.entity_id, tags_by_entity),
        )
    if isinstance(face, Ellipse):
        center = document.entity(face.center_id)
        if not isinstance(center, Point):
            return None
        height = abs(solid.distance_mm)
        origin_z = center.xyz_mm.z_mm
        if solid.distance_mm < 0.0:
            origin_z -= height
        return FrameVolume(
            entity_id=solid.entity_id,
            origin_xyz_mm=XYZ(
                center.xyz_mm.x_mm - face.radius_x_mm,
                center.xyz_mm.y_mm - face.radius_y_mm,
                origin_z,
            ),
            size_xyz_mm=XYZ(face.radius_x_mm * 2.0, face.radius_y_mm * 2.0, height),
            label=solid.label,
            tags=_tags_for(solid.entity_id, tags_by_entity),
        )
    if not isinstance(face, Face):
        return None
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    for point_id in face.point_ids:
        point = document.entity(point_id)
        if not isinstance(point, Point):
            return None
        xs.append(point.xyz_mm.x_mm)
        ys.append(point.xyz_mm.y_mm)
        zs.append(point.xyz_mm.z_mm)
    height = abs(solid.distance_mm)
    origin_z = min(zs)
    if solid.distance_mm < 0.0:
        origin_z -= height
    return FrameVolume(
        entity_id=solid.entity_id,
        origin_xyz_mm=XYZ(min(xs), min(ys), origin_z),
        size_xyz_mm=XYZ(max(xs) - min(xs), max(ys) - min(ys), height),
        label=solid.label,
        tags=_tags_for(solid.entity_id, tags_by_entity),
    )


def _members_from_polyline(
    polyline: Polyline,
    points: dict[EntityId, Point],
    tags_by_entity: dict[EntityId, tuple[str, ...]],
) -> tuple[FrameMember, ...]:
    ids = polyline.point_ids
    if polyline.closed and len(ids) < 3:
        raise DocumentError(
            f"closed polyline {polyline.entity_id} needs at least three points to form members"
        )
    pairs: list[tuple[EntityId, EntityId]] = [
        (ids[index], ids[index + 1]) for index in range(len(ids) - 1)
    ]
    if polyline.closed:
        pairs.append((ids[-1], ids[0]))
    return tuple(
        _member_from_segment(
            owner=polyline,
            start_id=start_id,
            end_id=end_id,
            points=points,
            tags_by_entity=tags_by_entity,
            segment_index=index,
        )
        for index, (start_id, end_id) in enumerate(pairs)
    )


def _member_from_segment(
    owner: Line | Polyline,
    start_id: EntityId,
    end_id: EntityId,
    points: dict[EntityId, Point],
    tags_by_entity: dict[EntityId, tuple[str, ...]],
    segment_index: int | None,
) -> FrameMember:
    start = points[start_id]
    end = points[end_id]
    dx = end.xyz_mm.x_mm - start.xyz_mm.x_mm
    dy = end.xyz_mm.y_mm - start.xyz_mm.y_mm
    dz = end.xyz_mm.z_mm - start.xyz_mm.z_mm
    length_mm = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length_mm == 0.0:
        raise DocumentError(
            f"zero-length member on entity {owner.entity_id} from {start_id} to {end_id}"
        )
    label = owner.label
    if label is not None and segment_index is not None:
        label = f"{label}[{segment_index}]"
    return FrameMember(
        entity_id=owner.entity_id,
        start_id=start_id,
        end_id=end_id,
        length_mm=length_mm,
        axis_xyz=XYZ(dx / length_mm, dy / length_mm, dz / length_mm),
        label=label,
        tags=_tags_for(owner.entity_id, tags_by_entity),
        section_id=None,
        segment_index=segment_index,
    )


def _tags_by_entity(tags: dict[str, frozenset[EntityId]]) -> dict[EntityId, tuple[str, ...]]:
    collected: dict[EntityId, list[str]] = {}
    for name, entity_ids in tags.items():
        for entity_id in entity_ids:
            collected.setdefault(entity_id, []).append(name)
    return {entity_id: tuple(sorted(names)) for entity_id, names in collected.items()}


def _tags_for(
    entity_id: EntityId,
    tags_by_entity: dict[EntityId, tuple[str, ...]],
) -> tuple[str, ...]:
    return tags_by_entity.get(entity_id, ())
