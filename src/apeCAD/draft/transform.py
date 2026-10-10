"""Handlers that move or clone point sets: translate, rotate, mirror, arrays (ADR 0012)."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import replace

from apeCAD.draft.create import ensure_loop_lines
from apeCAD.draft.state import DraftState
from apeCAD.entities import (
    Arc,
    Bezier,
    Box,
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
from apeCAD.geometry import XYZ, mirror_xy, rotate_xy
from apeCAD.ops import ArrayLinear, ArrayPolar, Mirror, Rotate, Translate


def translate(state: DraftState, op: Translate) -> Translate:
    moved = _transform_points(
        state,
        op.entity_ids,
        lambda xyz: XYZ(
            xyz.x_mm + op.dx_mm,
            xyz.y_mm + op.dy_mm,
            xyz.z_mm + op.dz_mm,
        ),
    )
    if not moved:
        raise DocumentError("translate did not move any points")
    return op


def rotate(state: DraftState, op: Rotate) -> Rotate:
    angle = math.radians(op.angle_deg)

    def mapper(xyz: XYZ) -> XYZ:
        x_mm, y_mm = rotate_xy(xyz.x_mm, xyz.y_mm, op.origin_x_mm, op.origin_y_mm, angle)
        return XYZ(x_mm, y_mm, xyz.z_mm)

    moved = _transform_points(state, op.entity_ids, mapper)
    if not moved:
        raise DocumentError("rotate did not move any points")
    return op


def mirror(state: DraftState, op: Mirror) -> Mirror:
    def mapper(xyz: XYZ) -> XYZ:
        x_mm, y_mm = mirror_xy(xyz.x_mm, xyz.y_mm, op.ax_mm, op.ay_mm, op.bx_mm, op.by_mm)
        return XYZ(x_mm, y_mm, xyz.z_mm)

    moved = _transform_points(state, op.entity_ids, mapper)
    if not moved:
        raise DocumentError("mirror did not move any points")
    return op


def array_linear(state: DraftState, op: ArrayLinear) -> ArrayLinear:
    for index in range(1, op.copies + 1):
        dx = op.dx_mm * index
        dy = op.dy_mm * index
        dz = op.dz_mm * index
        _clone_graph(
            state,
            op.entity_ids,
            lambda xyz, dx=dx, dy=dy, dz=dz: XYZ(xyz.x_mm + dx, xyz.y_mm + dy, xyz.z_mm + dz),
        )
    return op


def array_polar(state: DraftState, op: ArrayPolar) -> ArrayPolar:
    full_turn = abs(abs(op.angle_deg) - 360.0) < 1e-9
    step = op.angle_deg / op.count if full_turn else op.angle_deg / (op.count - 1)
    for index in range(1, op.count):
        angle = math.radians(step * index)

        def mapper(
            xyz: XYZ,
            angle: float = angle,
        ) -> XYZ:
            x_mm, y_mm = rotate_xy(xyz.x_mm, xyz.y_mm, op.origin_x_mm, op.origin_y_mm, angle)
            return XYZ(x_mm, y_mm, xyz.z_mm)

        _clone_graph(state, op.entity_ids, mapper)
    return op


def _transform_points(
    state: DraftState,
    entity_ids: tuple[EntityId, ...],
    mapper: Callable[[XYZ], XYZ],
) -> set[EntityId]:
    moved: set[EntityId] = set()
    box_moved = False
    for entity_id in entity_ids:
        entity = state.entity(entity_id)
        for point_id in state.point_ids_of(entity):
            if point_id in moved:
                continue
            point = state.require_point(point_id)
            state.entities[point_id] = replace(point, xyz_mm=mapper(point.xyz_mm))
            moved.add(point_id)
        if isinstance(entity, Box):
            state.entities[entity_id] = replace(
                entity, origin_xyz_mm=mapper(entity.origin_xyz_mm)
            )
            box_moved = True
    if not moved and not box_moved:
        return set()
    return moved if moved else {entity_ids[0]}


def _clone_graph(
    state: DraftState,
    entity_ids: tuple[EntityId, ...],
    mapper: Callable[[XYZ], XYZ],
) -> None:
    """Copy the selected subgraph through mapper as new unlabelled entities."""
    extras: list[EntityId] = []
    for entity_id in entity_ids:
        entity = state.entity(entity_id)
        if isinstance(entity, Solid):
            if entity.face_id not in entity_ids:
                extras.append(entity.face_id)
            if entity.cap_id is not None and entity.cap_id not in entity_ids:
                extras.append(entity.cap_id)
            for wall_id in entity.wall_ids:
                if wall_id not in entity_ids:
                    extras.append(wall_id)
    ordered = list(dict.fromkeys([*extras, *entity_ids]))
    non_solids = [
        entity_id for entity_id in ordered if not isinstance(state.entity(entity_id), Solid)
    ]
    solids = [entity_id for entity_id in ordered if isinstance(state.entity(entity_id), Solid)]
    point_map: dict[EntityId, EntityId] = {}
    entity_map: dict[EntityId, EntityId] = {}

    def mapped_point(point_id: EntityId) -> EntityId:
        existing = point_map.get(point_id)
        if existing is not None:
            return existing
        point = state.require_point(point_id)
        new_id = state.allocate_id(None)
        state.entities[new_id] = Point(
            entity_id=new_id,
            xyz_mm=mapper(point.xyz_mm),
            label=None,
        )
        point_map[point_id] = new_id
        return new_id

    for entity_id in non_solids + solids:
        entity = state.entity(entity_id)
        if isinstance(entity, Point):
            entity_map[entity.entity_id] = mapped_point(entity.entity_id)
            continue
        new_id = state.allocate_id(None)
        entity_map[entity_id] = new_id
        if isinstance(entity, Line):
            state.entities[new_id] = Line(
                entity_id=new_id,
                start_id=mapped_point(entity.start_id),
                end_id=mapped_point(entity.end_id),
                label=None,
            )
        elif isinstance(entity, Polyline):
            state.entities[new_id] = Polyline(
                entity_id=new_id,
                point_ids=tuple(mapped_point(pid) for pid in entity.point_ids),
                closed=entity.closed,
                label=None,
            )
        elif isinstance(entity, Face):
            point_ids = tuple(mapped_point(pid) for pid in entity.point_ids)
            state.entities[new_id] = Face(
                entity_id=new_id,
                point_ids=point_ids,
                label=None,
            )
            ensure_loop_lines(state, point_ids)
        elif isinstance(entity, Box):
            state.entities[new_id] = Box(
                entity_id=new_id,
                origin_xyz_mm=mapper(entity.origin_xyz_mm),
                size_xyz_mm=entity.size_xyz_mm,
                label=None,
            )
        elif isinstance(entity, Circle):
            state.entities[new_id] = Circle(
                entity_id=new_id,
                center_id=mapped_point(entity.center_id),
                radius_mm=entity.radius_mm,
                label=None,
            )
        elif isinstance(entity, Ellipse):
            state.entities[new_id] = Ellipse(
                entity_id=new_id,
                center_id=mapped_point(entity.center_id),
                radius_x_mm=entity.radius_x_mm,
                radius_y_mm=entity.radius_y_mm,
                label=None,
            )
        elif isinstance(entity, Arc):
            state.entities[new_id] = Arc(
                entity_id=new_id,
                start_id=mapped_point(entity.start_id),
                mid_id=mapped_point(entity.mid_id),
                end_id=mapped_point(entity.end_id),
                label=None,
            )
        elif isinstance(entity, Bezier):
            state.entities[new_id] = Bezier(
                entity_id=new_id,
                point_ids=tuple(mapped_point(pid) for pid in entity.point_ids),
                label=None,
            )
        else:
            assert isinstance(entity, Solid)
            profile_id = entity_map.get(entity.face_id)
            if profile_id is None:
                raise DocumentError("polar/linear array could not clone the solid profile")
            cap_id = None
            if entity.cap_id is not None:
                cap_id = entity_map.get(entity.cap_id)
                if cap_id is None:
                    raise DocumentError("polar/linear array could not clone the solid cap")
            wall_ids: list[EntityId] = []
            for wall_id in entity.wall_ids:
                mapped_wall = entity_map.get(wall_id)
                if mapped_wall is None:
                    raise DocumentError("polar/linear array could not clone the solid wall")
                wall_ids.append(mapped_wall)
            state.entities[new_id] = Solid(
                entity_id=new_id,
                face_id=profile_id,
                distance_mm=entity.distance_mm,
                direction_xyz=entity.direction_xyz,
                cap_id=cap_id,
                wall_ids=tuple(wall_ids),
                label=None,
            )
