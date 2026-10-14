"""Handlers that move or clone point sets: translate, rotate, mirror, arrays (ADR 0012)."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import replace

from apeCAD.draft.create import ensure_loop_lines
from apeCAD.draft.state import DraftState
from apeCAD.entities import (
    Arc,
    Bar,
    Bezier,
    Box,
    Circle,
    ConcreteFace,
    CoverGuide,
    Crosstie,
    Ellipse,
    Entity,
    EntityId,
    Face,
    Hoop,
    Line,
    Point,
    Polyline,
    Solid,
    WallLeg,
)
from apeCAD.errors import DocumentError
from apeCAD.geometry import XYZ, mirror_xy, rotate_xy
from apeCAD.ops import ArrayLinear, ArrayPolar, Mirror, Rotate, Translate
from apeCAD.section.geometry import Point2, canonical_ring, signed_area


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
        for point_id in _carried_point_ids(state, entity):
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
    _restore_section_rings(state, moved)
    return moved if moved else {entity_ids[0]}


def _carried_point_ids(state: DraftState, entity: Entity) -> tuple[EntityId, ...]:
    """The points a move takes: the entity's own, and a concrete face's leg axes too."""
    ids = state.point_ids_of(entity)
    if not isinstance(entity, ConcreteFace):
        return ids
    legs = [leg for leg in _owned_by(state, entity.entity_id) if isinstance(leg, WallLeg)]
    return (*ids, *(pid for leg in legs for pid in (leg.start_id, leg.end_id)))


def _owned_by(state: DraftState, face_id: EntityId) -> list[WallLeg | CoverGuide]:
    """A face's legs and cover guide, which go wherever it goes (ADR 0024 decision 8)."""
    return [
        e
        for e in state.entities.values()
        if isinstance(e, (WallLeg, CoverGuide)) and e.face_id == face_id
    ]


def _restore_section_rings(state: DraftState, moved: set[EntityId]) -> None:
    """Keep stored section rings CCW after a move; a mirror reverses them (ADR 0024 P2).

    A hoop keeps its members and returns to the hull's form (CCW from the lowest (x, y));
    a concrete face is reversed when it turned clockwise.
    """
    for entity in list(state.entities.values()):
        if isinstance(entity, (Hoop, ConcreteFace)):
            point_ids = state.point_ids_of(entity)
            if moved.isdisjoint(point_ids):
                continue
            xy = {pid: _xy(state, pid) for pid in point_ids}
            if isinstance(entity, ConcreteFace):
                if signed_area([xy[pid] for pid in point_ids]) < 0.0:
                    state.entities[entity.entity_id] = replace(
                        entity, point_ids=entity.point_ids[::-1]
                    )
                continue
            by_bar = dict(zip(entity.bar_ids, point_ids, strict=True))
            bar_xy = {bar_id: xy[pid] for bar_id, pid in by_bar.items()}
            ring = tuple(canonical_ring(entity.bar_ids, bar_xy))
            if ring != entity.bar_ids:
                state.entities[entity.entity_id] = replace(entity, bar_ids=ring)


def _xy(state: DraftState, point_id: EntityId) -> Point2:
    xyz = state.require_point(point_id).xyz_mm
    return (xyz.x_mm, xyz.y_mm)


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
        elif isinstance(entity, Hoop):  # a hoop is cloned with its bars
            extras.extend(bar_id for bar_id in entity.bar_ids if bar_id not in entity_ids)
        elif isinstance(entity, Crosstie):
            for bar_id in (entity.bar_a_id, entity.bar_b_id):
                if bar_id not in entity_ids:
                    extras.append(bar_id)
        elif isinstance(entity, (WallLeg, CoverGuide)):  # a leg or guide needs its face
            extras.append(entity.face_id)
    ordered = list(dict.fromkeys([*extras, *entity_ids]))
    # A cloned face takes all its legs and its cover guide with it.
    for entity_id in list(ordered):
        if isinstance(state.entity(entity_id), ConcreteFace):
            ordered.extend(e.entity_id for e in _owned_by(state, entity_id))
    ordered = list(dict.fromkeys(ordered))
    # Owners after their parts: bars before the hoops and crossties that use them.
    ordered.sort(key=lambda entity_id: _clone_rank(state.entity(entity_id)))
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

    for entity_id in ordered:
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
        elif isinstance(entity, ConcreteFace):
            state.entities[new_id] = replace(
                entity,
                entity_id=new_id,
                point_ids=tuple(mapped_point(pid) for pid in entity.point_ids),
                label=None,
            )
        elif isinstance(entity, Bar):
            state.entities[new_id] = replace(
                entity, entity_id=new_id, point_id=mapped_point(entity.point_id), label=None
            )
        elif isinstance(entity, Hoop):
            state.entities[new_id] = replace(
                entity,
                entity_id=new_id,
                bar_ids=tuple(entity_map[bar_id] for bar_id in entity.bar_ids),
                label=None,
            )
        elif isinstance(entity, Crosstie):
            state.entities[new_id] = replace(
                entity,
                entity_id=new_id,
                bar_a_id=entity_map[entity.bar_a_id],
                bar_b_id=entity_map[entity.bar_b_id],
                label=None,
            )
        elif isinstance(entity, WallLeg):
            state.entities[new_id] = replace(
                entity,
                entity_id=new_id,
                start_id=mapped_point(entity.start_id),
                end_id=mapped_point(entity.end_id),
                face_id=entity_map[entity.face_id],
                label=None,
            )
        elif isinstance(entity, CoverGuide):
            state.entities[new_id] = replace(
                entity, entity_id=new_id, face_id=entity_map[entity.face_id], label=None
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
    _restore_section_rings(state, set(point_map.values()))


def _clone_rank(entity: object) -> int:
    if isinstance(entity, Solid):
        return 2
    if isinstance(entity, (Hoop, Crosstie, WallLeg, CoverGuide)):
        return 1
    return 0
