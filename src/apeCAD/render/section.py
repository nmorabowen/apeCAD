"""Section-mode entities (ADR 0024, 0039) as drawables: faces, cover ring, leg axis, ties, bars.

Everything is plan geometry on the bars' and outline's own z. A hoop draws as a tie around
its bars: the hull of the bar centres, offset by each bar's radius plus half the tie
diameter, with round corners. Hoops and crossties carry their hook ticks (spec §3.2) as
extra open paths after the main one, so `paths[0]` is always the ring or the tie itself.
Nothing here is mechanics; apeConcrete owns that.

A v2 face (ADR 0039) draws on the layer of its role, its outer boundary then its holes as
one compound drawable; a circle is tessellated here for display only (`circle_points`), the
contract keeps it exact. A circular tie draws its centreline circle. `not_drawn` names
whatever still draws nothing, so the `render` tool warns `not-drawn` instead of answering a
silent ok (apeSection#39).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping

from apeCAD.entities import (
    Arc,
    Bar,
    Bezier,
    Box,
    Circle,
    CircleBoundary,
    CircularTie,
    ConcreteFace,
    CoverGuide,
    Crosstie,
    Ellipse,
    Entity,
    EntityId,
    Face,
    FaceBoundary,
    Hoop,
    Line,
    Point,
    Polyline,
    SectionEntity,
    SectionFace,
    SectionTemplate,
    Solid,
    WallLeg,
)
from apeCAD.render.drawable import Drawable, Path3
from apeCAD.render.tessellate import circle_points, fan_points
from apeCAD.render.views import Vec3
from apeCAD.section.cover import CoverRings, circle_cover_rings, cover_rings

HOOK_DEG = 135.0  # a hoop's closing hooks (`Hoop.hooks` is only "135")

NOT_DRAWN = "not-drawn"
"""The `render` warning code for entities that draw nothing (apeSection#39)."""

SKETCH_KINDS = (Point, Line, Polyline, Box, Face, Solid, Circle, Arc, Ellipse, Bezier)
"""The kinds `scene.py` draws itself; every other kind is drawn here or not at all."""


def not_drawn(entities: Mapping[EntityId, Entity], draw_ids: Iterable[EntityId]) -> list[EntityId]:
    """Each id among `draw_ids` that draws nothing, ascending: any kind `scene.py` does not
    draw itself for which `section_drawable` answers None, so a kind added without a drawing
    is named by construction. A template draws its children instead (ADR 0040), and a bar's
    point is drawn by the bar's disc (a sketch kind), so neither is named."""
    skipped: list[EntityId] = []
    for i in sorted(draw_ids):
        entity = entities.get(i)
        if entity is None or isinstance(entity, SKETCH_KINDS):
            continue
        if isinstance(entity, SectionTemplate):
            continue
        if section_drawable(entities, entity, None) is None:
            skipped.append(i)
    return skipped


def not_drawn_reason(entities: Mapping[EntityId, Entity], entity_id: EntityId) -> str | None:
    """Why an entity `not_drawn` names draws nothing, when the geometry says: a cover guide
    whose cover ring collapses gives `CoverRings.reason`. None when no reason is known."""
    guide = entities.get(entity_id)
    if not isinstance(guide, CoverGuide):
        return None
    found = _cover_rings(entities, guide)
    if found is None or found[0].cover_ring_mm is not None:
        return None
    return found[0].reason


def bar_point_ids(entities: Mapping[EntityId, Entity]) -> set[EntityId]:
    """Points that only place a bar: the bar's disc stands for them, so they draw no dot."""
    return {e.point_id for e in entities.values() if isinstance(e, Bar)}


def section_drawable(
    entities: Mapping[EntityId, Entity],
    entity: SectionEntity | SectionTemplate,
    tol_mm: float | None,
) -> Drawable | None:
    if isinstance(entity, SectionTemplate):
        return None  # a template draws nothing of its own: its children are drawn (ADR 0040)
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
    if isinstance(entity, CoverGuide):
        return _cover(entities, entity)
    if isinstance(entity, SectionFace):
        return _section_face(entities, entity, tol_mm)
    # Checked, not assumed: a kind the union does not list yet must reach `return None`.
    if isinstance(entity, CircularTie):  # pyright: ignore[reportUnnecessaryIsInstance]
        return _circular_tie(entities, entity, tol_mm)
    return None  # a kind with no drawing: `not_drawn` names it


def _section_face(
    entities: Mapping[EntityId, Entity], face: SectionFace, tol_mm: float | None
) -> Drawable | None:
    """A v2 face on its role's layer: `paths[0]` is the outer boundary, then each hole, all
    one shape (`compound`), which `svg.py` fills even-odd so a hole stays open whatever its
    winding. Painting follows the layer (`SECTION_LAYERS`), never the id (ADR 0039 D3)."""
    paths: list[Path3] = []
    for boundary in (face.boundary, *face.holes):
        loop = _boundary(entities, boundary, tol_mm)
        if loop is None:
            return None  # an unresolved hole would fill: draw nothing, and be named
        paths.append((tuple(loop), True))
    outer = face.boundary
    anchor = (
        _xyz(entities, outer.center_id) if isinstance(outer, CircleBoundary)
        else _mean(list(paths[0][0]))
    )
    return Drawable(
        face.entity_id, face.role, tuple(paths), anchor, face.label, compound=True
    )


def _boundary(
    entities: Mapping[EntityId, Entity], boundary: FaceBoundary, tol_mm: float | None
) -> list[Vec3] | None:
    if isinstance(boundary, CircleBoundary):
        centre = _xyz(entities, boundary.center_id)
        return None if centre is None else circle_points(centre, boundary.radius_mm, tol_mm)
    ring = _xyz_all(entities, boundary.point_ids)
    return ring if len(ring) == len(boundary.point_ids) and len(ring) >= 3 else None


def _circular_tie(
    entities: Mapping[EntityId, Entity], tie: CircularTie, tol_mm: float | None
) -> Drawable | None:
    """The tie's centreline circle, at `centerline_radius_mm` about its centre (no hooks:
    the entity carries none)."""
    centre = _xyz(entities, tie.center_id)
    if centre is None:
        return None
    loop = circle_points(centre, tie.centerline_radius_mm, tol_mm)
    return Drawable(tie.entity_id, "circular-tie", ((tuple(loop), True),), centre, tie.label)


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
    """The cover ring, from `section/cover.py` as the scene computes it
    (`scratchpad/payload.py::_guide_rings`): a ring insets by mitred offset, a v2 circle by
    radius."""
    found = _cover_rings(entities, guide)
    if found is None:
        return None
    rings, z = found
    ring = rings.cover_ring_mm
    if ring is None:
        return None
    pts = tuple((x, y, z) for x, y in ring)
    return Drawable(guide.entity_id, "cover", ((pts, True),), None, guide.label)


def _cover_rings(
    entities: Mapping[EntityId, Entity], guide: CoverGuide
) -> tuple[CoverRings, float] | None:
    face = entities.get(guide.face_id)
    if isinstance(face, SectionFace):
        boundary = face.boundary
        if isinstance(boundary, CircleBoundary):
            centre = _xyz(entities, boundary.center_id)
            if centre is None:
                return None
            xy = (centre[0], centre[1])
            return circle_cover_rings(xy, boundary.radius_mm, guide), centre[2]
        point_ids = boundary.point_ids
    elif isinstance(face, ConcreteFace):
        point_ids = face.point_ids
    else:
        return None
    outline = _xyz_all(entities, point_ids)
    if len(outline) < 3:
        return None
    return cover_rings([(p[0], p[1]) for p in outline], guide), outline[0][2]


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
