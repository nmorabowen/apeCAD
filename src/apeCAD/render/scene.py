"""What to draw: each entity becomes world-space polylines on one layer, plus a text anchor."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from apeCAD.document import Document
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
    Point,
    Polyline,
    Solid,
)
from apeCAD.render.drawable import Drawable, Layer, Path3
from apeCAD.render.section import bar_point_ids, section_drawable
from apeCAD.render.tessellate import arc_points, bezier_points, ellipse_points
from apeCAD.render.views import Vec3

__all__ = ["Drawable", "Layer", "Path3", "closure", "drawables", "entity_map"]


def entity_map(document: Document) -> dict[EntityId, Entity]:
    """Every entity, section-mode kinds included, by ascending id."""
    return {entity_id: document.entity(entity_id) for entity_id in sorted(document.entity_ids())}


def closure(
    ids: Iterable[EntityId], children: Mapping[EntityId, tuple[EntityId, ...]]
) -> set[EntityId]:
    """The ids plus everything they are built from (solid → faces → edges → vertices)."""
    seen: set[EntityId] = set()
    stack = list(ids)
    while stack:
        entity_id = stack.pop()
        if entity_id in seen:
            continue
        seen.add(entity_id)
        stack.extend(children.get(entity_id, ()))
    return seen


def drawables(
    entities: Mapping[EntityId, Entity],
    draw_ids: set[EntityId],
    tol_mm: float | None,
) -> list[Drawable]:
    out: list[Drawable] = []
    bar_points = bar_point_ids(entities)
    for entity_id, entity in entities.items():
        if entity_id not in draw_ids or entity_id in bar_points:
            continue
        drawable = _drawable(entities, entity, tol_mm)
        if drawable is not None:
            out.append(drawable)
    return out


def _xyz(entities: Mapping[EntityId, Entity], entity_id: EntityId) -> Vec3 | None:
    entity = entities.get(entity_id)
    return entity.xyz_mm.to_tuple() if isinstance(entity, Point) else None


def _all_xyz(entities: Mapping[EntityId, Entity], ids: Iterable[EntityId]) -> list[Vec3] | None:
    out: list[Vec3] = []
    for entity_id in ids:
        xyz = _xyz(entities, entity_id)
        if xyz is None:
            return None
        out.append(xyz)
    return out


def _mean(points: list[Vec3]) -> Vec3:
    count = len(points)
    return (
        sum(p[0] for p in points) / count,
        sum(p[1] for p in points) / count,
        sum(p[2] for p in points) / count,
    )


def _drawable(
    entities: Mapping[EntityId, Entity], entity: Entity, tol_mm: float | None
) -> Drawable | None:
    eid, label = entity.entity_id, entity.label
    if isinstance(entity, Point):
        xyz = entity.xyz_mm.to_tuple()
        return Drawable(eid, "point", (((xyz,), False),), xyz, label)
    if isinstance(entity, Line):
        ends = _all_xyz(entities, (entity.start_id, entity.end_id))
        if ends is None:
            return None
        return Drawable(eid, "edge", ((tuple(ends), False),), _mean(ends), label)
    if isinstance(entity, (Polyline, Face)):
        pts = _all_xyz(entities, entity.point_ids)
        if not pts:
            return None
        closed = isinstance(entity, Face) or entity.closed
        layer: Layer = "face" if isinstance(entity, Face) else "edge"
        return Drawable(eid, layer, ((tuple(pts), closed),), _mean(pts), label)
    if isinstance(entity, (Circle, Ellipse)):
        center = _xyz(entities, entity.center_id)
        if center is None:
            return None
        rx, ry = _radii(entity)
        loop = ellipse_points(center, rx, ry, tol_mm)
        return Drawable(eid, "edge", ((tuple(loop), True),), center, label)
    if isinstance(entity, Arc):
        ends = _all_xyz(entities, (entity.start_id, entity.mid_id, entity.end_id))
        if ends is None:
            return None
        pts = arc_points(ends[0], ends[1], ends[2], tol_mm)
        return Drawable(eid, "edge", ((tuple(pts), False),), ends[1], label)
    if isinstance(entity, Bezier):
        controls = _all_xyz(entities, entity.point_ids)
        if not controls:
            return None
        pts = bezier_points(controls, tol_mm)
        return Drawable(eid, "edge", ((tuple(pts), False),), pts[len(pts) // 2], label)
    if isinstance(entity, Box):
        return _box(entity)
    if isinstance(entity, Solid):
        return _solid(entities, entity)
    return section_drawable(entities, entity, tol_mm)  # the section-mode kinds (ADR 0024)


def _radii(entity: Circle | Ellipse) -> tuple[float, float]:
    if isinstance(entity, Circle):
        return entity.radius_mm, entity.radius_mm
    return entity.radius_x_mm, entity.radius_y_mm


def _box(box: Box) -> Drawable:
    ox, oy, oz = box.origin_xyz_mm.to_tuple()
    sx, sy, sz = box.size_xyz_mm.to_tuple()
    corners = [
        (ox + sx * i, oy + sy * j, oz + sz * k) for k in (0, 1) for j in (0, 1) for i in (0, 1)
    ]
    # Corner index bits: i = 1, j = 2, k = 4. An edge joins corners one bit apart.
    edges = [(a, a | bit) for bit in (1, 2, 4) for a in range(8) if not a & bit]
    paths = tuple(((corners[a], corners[b]), False) for a, b in edges)
    center = (ox + sx / 2.0, oy + sy / 2.0, oz + sz / 2.0)
    return Drawable(box.entity_id, "edge", paths, center, box.label)


def _solid(entities: Mapping[EntityId, Entity], solid: Solid) -> Drawable:
    """Face solids draw through their faces; a round profile adds four generator lines."""
    profile = entities.get(solid.face_id)
    cap = entities.get(solid.cap_id) if solid.cap_id is not None else None
    paths: list[Path3] = []
    anchor: Vec3 | None = None
    if isinstance(profile, (Circle, Ellipse)) and isinstance(cap, (Circle, Ellipse)):
        base = _xyz(entities, profile.center_id)
        top = _xyz(entities, cap.center_id)
        if base is not None and top is not None:
            rx, ry = _radii(profile)
            offset = (top[0] - base[0], top[1] - base[1], top[2] - base[2])
            for dx, dy in ((rx, 0.0), (0.0, ry), (-rx, 0.0), (0.0, -ry)):
                start = (base[0] + dx, base[1] + dy, base[2])
                end = (start[0] + offset[0], start[1] + offset[1], start[2] + offset[2])
                paths.append(((start, end), False))
            anchor = _mean([base, top])
    else:
        pts: list[Vec3] = []
        for loop in (profile, cap):
            if isinstance(loop, Face):
                pts.extend(_all_xyz(entities, loop.point_ids) or [])
        anchor = _mean(pts) if pts else None
    return Drawable(solid.entity_id, "edge", tuple(paths), anchor, solid.label)
