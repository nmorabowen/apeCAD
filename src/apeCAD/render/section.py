"""Section-mode entities (ADR 0024) as drawables: concrete, cover ring, leg axis, ties, bars.

Everything is plan geometry on the bars' and outline's own z. A hoop draws as a tie around
its bars: the hull of the bar centres, offset by each bar's radius plus half the tie
diameter, with round corners. Hoops and crossties carry their hook ticks (spec §3.2) as
extra open paths after the main one, so `paths[0]` is always the ring or the tie itself.
Nothing here is mechanics; apeConcrete owns that.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

from apeCAD.entities import (
    Bar,
    ConcreteFace,
    CoverGuide,
    Crosstie,
    Entity,
    EntityId,
    Hoop,
    Point,
    SectionEntity,
    WallLeg,
)
from apeCAD.render.drawable import Drawable, Path3
from apeCAD.render.tessellate import fan_points
from apeCAD.render.views import Vec3
from apeCAD.section.cover import cover_rings

HOOK_DEG = 135.0  # a hoop's closing hooks (`Hoop.hooks` is only "135")


def bar_point_ids(entities: Mapping[EntityId, Entity]) -> set[EntityId]:
    """Points that only place a bar: the bar's disc stands for them, so they draw no dot."""
    return {e.point_id for e in entities.values() if isinstance(e, Bar)}


def section_drawable(
    entities: Mapping[EntityId, Entity], entity: SectionEntity, tol_mm: float | None
) -> Drawable | None:
    eid, label = entity.entity_id, entity.label
    if isinstance(entity, ConcreteFace):
        ring = _xyz_all(entities, entity.point_ids)
        if len(ring) < 3:
            return None
        return Drawable(eid, "concrete", ((tuple(ring), True),), _mean(ring), label)
    if isinstance(entity, Bar):
        centre = _xyz(entities, entity.point_id)
        if centre is None:
            return None
        return Drawable(
            eid, "bar", (((centre,), False),), centre, label, radius_mm=entity.diameter_mm / 2.0
        )
    if isinstance(entity, Hoop):
        return _hoop(entities, entity, tol_mm)
    if isinstance(entity, Crosstie):
        return _crosstie(entities, entity)
    if isinstance(entity, WallLeg):
        ends = _xyz_all(entities, (entity.start_id, entity.end_id))
        if len(ends) != 2:
            return None
        return Drawable(eid, "leg", ((tuple(ends), False),), _mean(ends), label)
    return _cover(entities, entity)


def _hoop(
    entities: Mapping[EntityId, Entity], hoop: Hoop, tol_mm: float | None
) -> Drawable | None:
    bars = [e for i in hoop.bar_ids if isinstance(e := entities.get(i), Bar)]
    centres = _bar_centres(entities, hoop.bar_ids)
    if len(centres) < 2 or len(centres) != len(bars):
        return None
    offsets = [bar.diameter_mm / 2.0 + hoop.diameter_mm / 2.0 for bar in bars]
    ring = rounded_ring(centres, offsets, tol_mm)
    paths: list[Path3] = [(tuple(ring), True)]
    if len(centres) >= 3:
        paths.extend(_closing_ticks(centres, offsets[0], hoop.diameter_mm))
    return Drawable(hoop.entity_id, "hoop", tuple(paths), _mean(centres), hoop.label)


def _closing_ticks(centres: list[Vec3], radius: float, tie_mm: float) -> list[Path3]:
    """The two 135° hook tails at the closing corner, `centres[0]` (spec §3.2).

    One end arrives along the last edge and wraps CCW round the bar, the other leaves along
    the first edge and, traced backwards, wraps CW: each turns 135° from its leg and runs
    6 d_h into the core, tangent to the bar's tie circle on either side of it.
    """
    corner = centres[0]
    arriving = _unit(centres[-1], corner)
    leaving = _unit(corner, centres[1])
    back = (-leaving[0], -leaving[1])
    return [
        _tick(corner, radius, arriving, HOOK_DEG, 6.0 * tie_mm),
        _tick(corner, radius, back, -HOOK_DEG, 6.0 * tie_mm),
    ]


def _crosstie(entities: Mapping[EntityId, Entity], tie: Crosstie) -> Drawable | None:
    """Bar centre to bar centre, a hook tick at each end: `hooks` is "<at a>-<at b>".

    A 90° tail truly runs down the far face of its bar, on top of the hoop leg there, so it
    draws on the core side instead: tangent where the tie meets the bar's tie circle.
    """
    bar_ids = (tie.bar_a_id, tie.bar_b_id)
    ends = _bar_centres(entities, bar_ids)
    if len(ends) != 2:
        return None
    paths: list[Path3] = [(tuple(ends), False)]
    a, b = ends
    if math.hypot(b[0] - a[0], b[1] - a[1]) > 0.0:
        angles = [float(part) for part in tie.hooks.split("-")]
        arrivals = ((a, _unit(b, a)), (b, _unit(a, b)))
        for bar_id, (end, arriving), angle in zip(bar_ids, arrivals, angles, strict=True):
            bar = entities[bar_id]
            assert isinstance(bar, Bar)
            radius = bar.diameter_mm / 2.0 + tie.diameter_mm / 2.0
            length = 6.0 * tie.diameter_mm
            if angle == 90.0:
                paths.append(_core_side_tick(end, radius, arriving, length))
            else:
                paths.append(_tick(end, radius, arriving, angle, length))
    return Drawable(tie.entity_id, "crosstie", tuple(paths), _mean(ends), tie.label)



def _tick(
    centre: Vec3, radius: float, arriving: tuple[float, float], turn_deg: float, length: float
) -> Path3:
    """A hook tail: the bend turns `turn_deg` (CCW positive) from `arriving` round the bar.

    The tail runs tangent to the circle of `radius` about `centre`, from its tangent point,
    for `length`: on the right of the tail for a CCW wrap, on the left for a CW one.
    """
    turn = math.radians(turn_deg)
    cos_t, sin_t = math.cos(turn), math.sin(turn)
    dx = arriving[0] * cos_t - arriving[1] * sin_t
    dy = arriving[0] * sin_t + arriving[1] * cos_t
    side = 1.0 if turn_deg > 0 else -1.0
    sx, sy = centre[0] + side * radius * dy, centre[1] - side * radius * dx
    z = centre[2]
    return ((sx, sy, z), (sx + length * dx, sy + length * dy, z)), False


def _core_side_tick(
    centre: Vec3, radius: float, arriving: tuple[float, float], length: float
) -> Path3:
    """A 90° tail drawn where the tie meets its bar's tie circle, square to the tie."""
    sx, sy = centre[0] - radius * arriving[0], centre[1] - radius * arriving[1]
    dx, dy = -arriving[1], arriving[0]
    z = centre[2]
    return ((sx, sy, z), (sx + length * dx, sy + length * dy, z)), False


def _unit(a: Vec3, b: Vec3) -> tuple[float, float]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy) or 1.0
    return dx / length, dy / length


def rounded_ring(centres: list[Vec3], offsets: list[float], tol_mm: float | None) -> list[Vec3]:
    """The CCW ring `centres` grown outward by `offsets[i]` at each vertex, round corners.

    At vertex i the outward normal turns from that of the edge arriving to that of the edge
    leaving; the ring follows an arc of radius `offsets[i]` between them. Two centres give a
    stadium. Each arc's last point is dropped: the next edge starts at the next arc.
    """
    count = len(centres)
    normals = [_right_normal(centres[i], centres[(i + 1) % count]) for i in range(count)]
    out: list[Vec3] = []
    for i, centre in enumerate(centres):
        start = math.atan2(normals[i - 1][1], normals[i - 1][0])
        end = math.atan2(normals[i][1], normals[i][0])
        sweep = (end - start) % (2.0 * math.pi)
        out.extend(fan_points(centre, offsets[i], start, sweep, tol_mm))
    return out


def _right_normal(a: Vec3, b: Vec3) -> tuple[float, float]:
    """Outward normal of edge a→b of a CCW ring (its right-hand side)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy) or 1.0
    return dy / length, -dx / length


def _cover(entities: Mapping[EntityId, Entity], guide: CoverGuide) -> Drawable | None:
    face = entities.get(guide.face_id)
    if not isinstance(face, ConcreteFace):
        return None
    outline = _xyz_all(entities, face.point_ids)
    if len(outline) < 3:
        return None
    ring = cover_rings([(p[0], p[1]) for p in outline], guide).cover_ring_mm
    if ring is None:
        return None
    z = outline[0][2]
    pts = tuple((x, y, z) for x, y in ring)
    return Drawable(guide.entity_id, "cover", ((pts, True),), None, guide.label)


def _xyz(entities: Mapping[EntityId, Entity], entity_id: EntityId) -> Vec3 | None:
    entity = entities.get(entity_id)
    return entity.xyz_mm.to_tuple() if isinstance(entity, Point) else None


def _xyz_all(entities: Mapping[EntityId, Entity], ids: tuple[EntityId, ...]) -> list[Vec3]:
    return [p for i in ids if (p := _xyz(entities, i)) is not None]


def _bar_centres(entities: Mapping[EntityId, Entity], bar_ids: tuple[EntityId, ...]) -> list[Vec3]:
    out: list[Vec3] = []
    for bar_id in bar_ids:
        bar = entities.get(bar_id)
        centre = _xyz(entities, bar.point_id) if isinstance(bar, Bar) else None
        if centre is not None:
            out.append(centre)
    return out


def _mean(points: list[Vec3]) -> Vec3:
    count = len(points)
    return (
        sum(p[0] for p in points) / count,
        sum(p[1] for p in points) / count,
        sum(p[2] for p in points) / count,
    )
