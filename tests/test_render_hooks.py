"""Hook ticks on hoops and crossties (spec ape-design.md §3.2): geometry and SVG grouping."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET

import pytest

from _section_fixtures import c_wall_crossties, rect_boundary_hoops
from apeCAD.document import Document
from apeCAD.entities import Bar, Entity, EntityId, Point
from apeCAD.render import render_svg
from apeCAD.render.drawable import Drawable
from apeCAD.render.section import section_drawable
from apeCAD.render.views import Vec3

SVG_NS = "{http://www.w3.org/2000/svg}"


def _entities(doc: Document) -> dict[EntityId, Entity]:
    return {i: doc.entity(i) for i in doc.entity_ids()}


def _centre(doc: Document, bar_id: EntityId) -> tuple[float, float]:
    bar = doc.entity(bar_id)
    assert isinstance(bar, Bar)
    point = doc.entity(bar.point_id)
    assert isinstance(point, Point)
    return point.xyz_mm.x_mm, point.xyz_mm.y_mm


def _direction(a: Vec3 | tuple[float, float], b: Vec3 | tuple[float, float]) -> tuple[
    float, float
]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    return dx / length, dy / length


def _angle_deg(u: tuple[float, float], v: tuple[float, float]) -> float:
    dot = max(-1.0, min(1.0, u[0] * v[0] + u[1] * v[1]))
    return math.degrees(math.acos(dot))


def _offset(centre: tuple[float, float], start: Vec3, along: tuple[float, float]) -> float:
    """Distance from `centre` to the line through `start` along `along`."""
    rx, ry = centre[0] - start[0], centre[1] - start[1]
    return abs(rx * along[1] - ry * along[0])


def _drawable(doc: Document, entity_id: EntityId) -> Drawable:
    entity = doc.entity(entity_id)
    d = section_drawable(_entities(doc), entity, None)  # pyright: ignore[reportArgumentType]
    assert d is not None
    return d


def test_a_135_90_crosstie_draws_one_135_and_one_90_tick() -> None:
    doc = c_wall_crossties()
    tie = doc.crossties()[0]
    assert tie.hooks == "135-90"
    d = _drawable(doc, tie.entity_id)
    assert len(d.paths) == 3
    (a, b), _ = d.paths[0]
    ticks = [path for path, closed in d.paths[1:] if not closed]
    assert len(ticks) == 2
    bends: list[float] = []
    for (start, end), bar_id, arriving in zip(
        ticks, (tie.bar_a_id, tie.bar_b_id), (_direction(b, a), _direction(a, b)), strict=True
    ):
        tail = _direction(start, end)
        bends.append(_angle_deg(arriving, tail))
        assert math.dist(start, end) == pytest.approx(6.0 * tie.diameter_mm)
        # Tangent to the bar's tie circle: radius of the bar plus half the tie.
        radius = 20.0 / 2.0 + tie.diameter_mm / 2.0
        assert _offset(_centre(doc, bar_id), start, tail) == pytest.approx(radius)
        assert math.dist(start[:2], _centre(doc, bar_id)) == pytest.approx(radius)
    assert bends == [pytest.approx(135.0), pytest.approx(90.0)]


def test_a_135_135_crosstie_draws_two_135_ticks() -> None:
    doc = c_wall_crossties()
    left, right = doc.crossties()[0].bar_a_id, doc.crossties()[0].bar_b_id
    tie = doc.add_crosstie(left, right, "Ø12", 100.0)
    d = _drawable(doc, tie.entity_id)
    (a, b), _ = d.paths[0]
    arrivals = (_direction(b, a), _direction(a, b))
    bends = [_angle_deg(arr, _direction(*p)) for arr, (p, _) in zip(arrivals, d.paths[1:],
                                                                      strict=True)]
    assert bends == [pytest.approx(135.0), pytest.approx(135.0)]


def test_hoop_draws_two_135_ticks_at_its_closing_corner() -> None:
    doc = rect_boundary_hoops()
    for hoop in doc.hoops():
        d = _drawable(doc, hoop.entity_id)
        ring, closed = d.paths[0]
        assert closed
        assert len(d.paths) == 3
        corner = _centre(doc, hoop.bar_ids[0])
        last, second = _centre(doc, hoop.bar_ids[-1]), _centre(doc, hoop.bar_ids[1])
        radius = 16.0 / 2.0 + hoop.diameter_mm / 2.0
        (s1, e1), _ = d.paths[1]
        (s2, e2), _ = d.paths[2]
        t1, t2 = _direction(s1, e1), _direction(s2, e2)
        # Each tail turns 135° from its leg: one arriving along the last edge, the other
        # leaving along the first edge, traced backwards.
        assert _angle_deg(_direction(last, corner), t1) == pytest.approx(135.0)
        assert _angle_deg(_direction(second, corner), t2) == pytest.approx(135.0)
        for start, end, tail in ((s1, e1, t1), (s2, e2, t2)):
            assert math.dist(start, end) == pytest.approx(6.0 * hoop.diameter_mm)
            assert _offset(corner, start, tail) == pytest.approx(radius)
            assert _inside(end[:2], [p[:2] for p in ring])  # into the core
        # On either side of the bar, not on top of each other.
        assert math.dist(s1, s2) == pytest.approx(2.0 * radius)


def _inside(point: tuple[float, ...], ring: list[tuple[float, ...]]) -> bool:
    x, y = point
    inside = False
    for i, (ax, ay) in enumerate(ring):
        bx, by = ring[i - 1]
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            inside = not inside
    return inside


def test_ticks_draw_in_their_entity_group_with_its_pen() -> None:
    doc = c_wall_crossties()
    root = ET.fromstring(render_svg(doc, view="top", annotate=False).svg)
    for layer, count in (("hoop", len(doc.hoops())), ("crosstie", len(doc.crossties()))):
        groups = [g for g in root.iter(f"{SVG_NS}g") if g.get("class") == layer]
        assert len(groups) == 1
        members = [g for g in groups[0] if g.get("data-id")]
        assert len(members) == count
        # The entity's own path, then its two ticks, under the layer's one stroke.
        assert all(len(list(g)) == 3 for g in members)
        assert all(p.get("stroke") is None for g in members for p in g)
