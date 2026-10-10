"""Handlers that birth entities: points, curves, faces, solids (ADRs 0008, 0016, 0018)."""

from __future__ import annotations

from dataclasses import replace

from apeCAD.draft.state import DraftState, produced_id
from apeCAD.draft.topology import chain_from_segments, loop_from_lines
from apeCAD.entities import (
    Arc,
    Bezier,
    Circle,
    Ellipse,
    EntityId,
    Face,
    Line,
    Point,
    Polyline,
    Solid,
)
from apeCAD.errors import DocumentError
from apeCAD.geometry import XYZ
from apeCAD.ops import (
    AddArc,
    AddBezier,
    AddBox,
    AddCircle,
    AddEllipse,
    AddFace,
    AddFaceFromLines,
    AddLine,
    AddPoint,
    AddPolyline,
    Extrude,
    JoinPolyline,
)


def add_point(state: DraftState, op: AddPoint) -> AddPoint:
    state.reject_taken_label(op.label)
    entity_id = state.allocate_id(op.entity_id)
    state.register_label(entity_id, op.label)
    state.entities[entity_id] = Point(
        entity_id=entity_id,
        xyz_mm=XYZ(op.x_mm, op.y_mm, op.z_mm),
        label=op.label,
    )
    return replace(op, entity_id=entity_id)


def add_line(state: DraftState, op: AddLine) -> AddLine:
    if op.start_id == op.end_id:
        raise DocumentError(f"line start and end cannot be the same point id {op.start_id}")
    state.require_point(op.start_id)
    state.require_point(op.end_id)
    state.reject_taken_label(op.label)
    entity_id = state.allocate_id(op.entity_id)
    state.register_label(entity_id, op.label)
    state.entities[entity_id] = Line(
        entity_id=entity_id,
        start_id=op.start_id,
        end_id=op.end_id,
        label=op.label,
    )
    return replace(op, entity_id=entity_id)


def add_polyline(state: DraftState, op: AddPolyline) -> AddPolyline:
    for point_id in op.point_ids:
        state.require_point(point_id)
    state.reject_taken_label(op.label)
    entity_id = state.allocate_id(op.entity_id)
    state.register_label(entity_id, op.label)
    state.entities[entity_id] = Polyline(
        entity_id=entity_id,
        point_ids=op.point_ids,
        closed=op.closed,
        label=op.label,
    )
    return replace(op, entity_id=entity_id)


def add_box(state: DraftState, op: AddBox) -> AddBox:
    """AABB sugar: four points, a Face, and Extrude. One AddBox op in the log."""
    state.reject_taken_label(op.label)
    origin = op.origin_xyz_mm
    size = op.size_xyz_mm
    corners = (
        (origin.x_mm, origin.y_mm, origin.z_mm),
        (origin.x_mm + size.x_mm, origin.y_mm, origin.z_mm),
        (origin.x_mm + size.x_mm, origin.y_mm + size.y_mm, origin.z_mm),
        (origin.x_mm, origin.y_mm + size.y_mm, origin.z_mm),
    )
    point_ids: list[EntityId] = []
    for x_mm, y_mm, z_mm in corners:
        point_id, _created = state.point_at(x_mm, y_mm, z_mm, requested=None, tolerance_mm=0.0)
        point_ids.append(point_id)
    if len(set(point_ids)) != 4:
        raise DocumentError("box corners collapsed onto existing points")
    face_op = add_face(state, AddFace(point_ids=tuple(point_ids)))
    extrude_op = extrude(
        state,
        Extrude(
            face_id=produced_id(face_op),
            distance_mm=size.z_mm,
            direction_xyz=XYZ(0.0, 0.0, 1.0),
            label=op.label,
            entity_id=op.entity_id,
        ),
    )
    return replace(op, entity_id=extrude_op.entity_id)


def add_face(state: DraftState, op: AddFace) -> AddFace:
    for point_id in op.point_ids:
        state.require_point(point_id)
    state.reject_taken_label(op.label)
    entity_id = state.allocate_id(op.entity_id)
    state.register_label(entity_id, op.label)
    state.entities[entity_id] = Face(
        entity_id=entity_id,
        point_ids=op.point_ids,
        label=op.label,
    )
    ensure_loop_lines(state, op.point_ids)
    return replace(op, entity_id=entity_id)


def extrude(state: DraftState, op: Extrude) -> Extrude:
    face = state.entities.get(op.face_id)
    if not isinstance(face, (Face, Circle, Ellipse)):
        raise DocumentError(
            f"entity {op.face_id} is not a profile (need a face, circle, or ellipse)"
        )
    state.reject_taken_label(op.label)
    cap_id = _extrude_cap(state, face, op)
    wall_ids: tuple[EntityId, ...] = ()
    if isinstance(face, Face):
        cap = state.entities.get(cap_id)
        if isinstance(cap, Face):
            wall_ids = _extrude_walls(state, face, cap)
    entity_id = state.allocate_id(op.entity_id)
    state.register_label(entity_id, op.label)
    state.entities[entity_id] = Solid(
        entity_id=entity_id,
        face_id=op.face_id,
        distance_mm=op.distance_mm,
        direction_xyz=op.direction_xyz,
        cap_id=cap_id,
        wall_ids=wall_ids,
        label=op.label,
    )
    return replace(op, entity_id=entity_id)


def _extrude_offset(op: Extrude) -> XYZ:
    direction = op.direction_xyz
    length = (direction.x_mm**2 + direction.y_mm**2 + direction.z_mm**2) ** 0.5
    scale = op.distance_mm / length
    return XYZ(
        direction.x_mm * scale,
        direction.y_mm * scale,
        direction.z_mm * scale,
    )


def _extrude_cap(state: DraftState, profile: Face | Circle | Ellipse, op: Extrude) -> EntityId:
    offset = _extrude_offset(op)
    if isinstance(profile, Face):
        lid_ids: list[EntityId] = []
        for point_id in profile.point_ids:
            point = state.require_point(point_id)
            lid_id, _created = state.point_at(
                point.xyz_mm.x_mm + offset.x_mm,
                point.xyz_mm.y_mm + offset.y_mm,
                point.xyz_mm.z_mm + offset.z_mm,
                requested=None,
                tolerance_mm=0.0,
            )
            lid_ids.append(lid_id)
        cap = add_face(state, AddFace(point_ids=tuple(lid_ids)))
        return produced_id(cap)
    center = state.require_point(profile.center_id)
    lid_id, _created = state.point_at(
        center.xyz_mm.x_mm + offset.x_mm,
        center.xyz_mm.y_mm + offset.y_mm,
        center.xyz_mm.z_mm + offset.z_mm,
        requested=None,
        tolerance_mm=0.0,
    )
    if isinstance(profile, Circle):
        cap_circle = add_circle(state, AddCircle(center_id=lid_id, radius_mm=profile.radius_mm))
        return produced_id(cap_circle)
    cap_ellipse = add_ellipse(
        state,
        AddEllipse(
            center_id=lid_id,
            radius_x_mm=profile.radius_x_mm,
            radius_y_mm=profile.radius_y_mm,
        ),
    )
    return produced_id(cap_ellipse)


def _extrude_walls(state: DraftState, profile: Face, cap: Face) -> tuple[EntityId, ...]:
    base = profile.point_ids
    lid = cap.point_ids
    if len(base) != len(lid) or len(base) < 3:
        return ()
    walls: list[EntityId] = []
    count = len(base)
    for index in range(count):
        nxt = (index + 1) % count
        wall = add_face(
            state, AddFace(point_ids=(base[index], base[nxt], lid[nxt], lid[index]))
        )
        walls.append(produced_id(wall))
    return tuple(walls)


def add_circle(state: DraftState, op: AddCircle) -> AddCircle:
    state.require_point(op.center_id)
    state.reject_taken_label(op.label)
    entity_id = state.allocate_id(op.entity_id)
    state.register_label(entity_id, op.label)
    state.entities[entity_id] = Circle(
        entity_id=entity_id,
        center_id=op.center_id,
        radius_mm=op.radius_mm,
        label=op.label,
    )
    return replace(op, entity_id=entity_id)


def add_arc(state: DraftState, op: AddArc) -> AddArc:
    start = state.require_point(op.start_id)
    mid = state.require_point(op.mid_id)
    end = state.require_point(op.end_id)
    cross = (mid.xyz_mm.x_mm - start.xyz_mm.x_mm) * (end.xyz_mm.y_mm - start.xyz_mm.y_mm) - (
        mid.xyz_mm.y_mm - start.xyz_mm.y_mm
    ) * (end.xyz_mm.x_mm - start.xyz_mm.x_mm)
    if abs(cross) < 1e-6:
        raise DocumentError("arc points are collinear")
    state.reject_taken_label(op.label)
    entity_id = state.allocate_id(op.entity_id)
    state.register_label(entity_id, op.label)
    state.entities[entity_id] = Arc(
        entity_id=entity_id,
        start_id=op.start_id,
        mid_id=op.mid_id,
        end_id=op.end_id,
        label=op.label,
    )
    return replace(op, entity_id=entity_id)


def add_ellipse(state: DraftState, op: AddEllipse) -> AddEllipse:
    state.require_point(op.center_id)
    state.reject_taken_label(op.label)
    entity_id = state.allocate_id(op.entity_id)
    state.register_label(entity_id, op.label)
    state.entities[entity_id] = Ellipse(
        entity_id=entity_id,
        center_id=op.center_id,
        radius_x_mm=op.radius_x_mm,
        radius_y_mm=op.radius_y_mm,
        label=op.label,
    )
    return replace(op, entity_id=entity_id)


def add_bezier(state: DraftState, op: AddBezier) -> AddBezier:
    for point_id in op.point_ids:
        state.require_point(point_id)
    state.reject_taken_label(op.label)
    entity_id = state.allocate_id(op.entity_id)
    state.register_label(entity_id, op.label)
    state.entities[entity_id] = Bezier(
        entity_id=entity_id,
        point_ids=op.point_ids,
        label=op.label,
    )
    return replace(op, entity_id=entity_id)


def add_face_from_lines(state: DraftState, op: AddFaceFromLines) -> AddFaceFromLines:
    lines: list[Line] = []
    for line_id in op.line_ids:
        entity = state.entity(line_id)
        if not isinstance(entity, Line):
            raise DocumentError(f"entity {line_id} is not a line")
        lines.append(entity)
    loop = loop_from_lines(lines)
    face_op = add_face(state, AddFace(point_ids=loop, label=op.label, entity_id=op.entity_id))
    return replace(op, entity_id=face_op.entity_id)


def join_polyline(state: DraftState, op: JoinPolyline) -> JoinPolyline:
    segments: list[tuple[EntityId, EntityId]] = []
    consumed: list[EntityId] = []
    for entity_id in op.entity_ids:
        entity = state.entity(entity_id)
        if isinstance(entity, Line):
            segments.append((entity.start_id, entity.end_id))
        elif isinstance(entity, Polyline):
            ids = entity.point_ids
            for index in range(len(ids) - 1):
                segments.append((ids[index], ids[index + 1]))
            if entity.closed:
                segments.append((ids[-1], ids[0]))
        else:
            raise DocumentError(f"entity {entity_id} is not a line or polyline")
        consumed.append(entity_id)
    point_ids, closed = chain_from_segments(segments)
    inherited: list[str] = []
    for entity_id in consumed:
        source = state.entities[entity_id]
        if source.label is not None:
            inherited.append(source.label)
    label = op.label if op.label is not None else (
        inherited[0] if len(inherited) == 1 else None
    )
    owner = state.labels.get(label) if label is not None else None
    if owner is not None and owner not in consumed:
        raise DocumentError(f"label {label!r} already belongs to entity {owner}")
    for entity_id in consumed:
        state.drop_entity(entity_id)
    entity_id = state.allocate_id(op.entity_id)
    state.register_label(entity_id, label)
    state.entities[entity_id] = Polyline(
        entity_id=entity_id,
        point_ids=point_ids,
        closed=closed,
        label=label,
    )
    return replace(op, entity_id=entity_id, label=label)


def ensure_line(state: DraftState, start_id: EntityId, end_id: EntityId) -> Line:
    existing = state.line_between(start_id, end_id)
    if existing is not None:
        return existing
    op = add_line(state, AddLine(start_id=start_id, end_id=end_id))
    entity = state.entities[produced_id(op)]
    assert isinstance(entity, Line)
    return entity


def ensure_loop_lines(state: DraftState, point_ids: tuple[EntityId, ...]) -> None:
    """Face loops write Line records for every edge (ADR 0017)."""
    count = len(point_ids)
    if count < 2:
        return
    for index, start_id in enumerate(point_ids):
        end_id = point_ids[(index + 1) % count]
        if start_id != end_id:
            ensure_line(state, start_id, end_id)
