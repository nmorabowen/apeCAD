"""`rect_hollow`, version 1: a rectangular hollow (box) section (ADR 0040 decision 5).

Draws the b x h ring centred on `center_mm` with one rectangular hole, stored clockwise
(specs/section-draft-v2.md "Ring orientation"). `t_x` is the thickness of the two walls
crossed by the x axis (left and right), `t_y` that of the two crossed by the y axis (bottom
and top), so the hole is (b - 2 t_x) x (h - 2 t_y).

Two bar rings, both at d = cover + tie + bar / 2 from their concrete face: the outer one is
the ring inset by d, the inner one the hole outset by d. Each edge of each takes the fewest
equal intervals no longer than `spacing_max` (`layout.edge_positions`). Bars are listed
counter-clockwise from the south-west corner, outer ring first. One hoop on each bar ring's
strict hull. The cover guide is on the face (its outline); the hole has none of its own.

Version 1 places no crossties (owner ruling Q4, C3 record). Overlapping bars (closer than
the mean of their diameters) are refused: across a wall, a wall whose bar rings sit less than
a bar diameter apart (t - 2 d < bar) by `t_x` or `t_y`; along an edge by `spacing_max`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from apeCAD.errors import DocumentError
from apeCAD.section.designations import DESIGNATIONS
from apeCAD.section.geometry import Point2
from apeCAD.section.layout import edge_positions
from apeCAD.section.templates.plan import (
    Params,
    Plan,
    PlanBar,
    PlanCoverGuide,
    PlanFace,
    PlanHoop,
    PlanRing,
    finish,
    hull_of,
    require_extent,
)

TEMPLATE = "rect_hollow"
VERSION = 1
FIELDS = (
    "material", "bar_material", "center_mm", "b", "h", "t_x", "t_y", "cover", "bar",
    "spacing_max", "tie", "tie_spacing",
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class RectHollowParams:
    """`rect_hollow` v1 parameters; lengths in mm, bars as vocabulary designations."""

    material: str
    b: float
    h: float
    t_x: float
    t_y: float
    cover: float
    bar: str
    spacing_max: float
    tie: str
    tie_spacing: float
    bar_material: str | None = None
    center_mm: Point2 = (0.0, 0.0)


def parse(data: Mapping[str, object]) -> RectHollowParams:
    """Read and check a `rect_hollow` parameter mapping; each fault is refused by name."""
    p = Params(TEMPLATE, data, FIELDS)
    return RectHollowParams(
        material=p.material("material"),
        bar_material=p.optional_material("bar_material"),
        center_mm=p.point("center_mm", (0.0, 0.0)),
        b=p.length("b"),
        h=p.length("h"),
        t_x=p.length("t_x"),
        t_y=p.length("t_y"),
        cover=p.length("cover"),
        bar=p.designation("bar")[0],
        spacing_max=p.length("spacing_max"),
        tie=p.designation("tie")[0],
        tie_spacing=p.length("tie_spacing"),
    )


def _rect(x0: float, y0: float, x1: float, y1: float) -> list[Point2]:
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def expand_v1(data: Mapping[str, object]) -> Plan:
    """The `rect_hollow` v1 plan of a parameter mapping."""
    q = parse(data)
    p = Params(TEMPLATE, {}, ())
    bar_d, tie_d = DESIGNATIONS[q.bar], DESIGNATIONS[q.tie]
    d = q.cover + tie_d + bar_d / 2.0
    for name, size, wall in (("t_x", q.b, q.t_x), ("t_y", q.h, q.t_y)):
        if wall - 2.0 * d < bar_d:
            raise p.error(
                name,
                f"a {wall:g} mm wall puts its outer and inner bars {wall - 2.0 * d:g} mm "
                f"apart (t - 2 x {d:g} mm), under the {bar_d:g} mm bar: they overlap",
            )
        if not size > 2.0 * wall:
            raise p.error(
                name, f"two {wall:g} mm walls leave no hole in {'b' if name == 't_x' else 'h'}"
                f" = {size:g} mm",
            )
    cx, cy = q.center_mm
    x0, x1, y0, y1 = cx - q.b / 2.0, cx + q.b / 2.0, cy - q.h / 2.0, cy + q.h / 2.0
    hx0, hx1, hy0, hy1 = x0 + q.t_x, x1 - q.t_x, y0 + q.t_y, y1 - q.t_y
    outer = _rect(x0 + d, y0 + d, x1 - d, y1 - d)
    inner = _rect(hx0 - d, hy0 - d, hx1 + d, hy1 + d)
    require_extent(TEMPLATE, "center_mm", _rect(x0, y0, x1, y1))
    rings: list[list[Point2]] = []
    try:
        for centre_ring in (outer, inner):
            positions: list[Point2] = []
            for edge in range(4):
                positions += edge_positions(centre_ring, edge, None, q.spacing_max)[:-1]
            rings.append(positions)
    except DocumentError as exc:  # the extent was checked above
        raise p.error("spacing_max", str(exc)) from exc
    bars = tuple(
        PlanBar(x, y, q.bar, bar_d, q.bar_material) for ring in rings for x, y in ring
    )
    n_outer = len(rings[0])
    hole = PlanRing(((hx0, hy0), (hx0, hy1), (hx1, hy1), (hx1, hy0)))  # clockwise
    plan = Plan(
        faces=(PlanFace("concrete", q.material, PlanRing(tuple(_rect(x0, y0, x1, y1))), (hole,)),),
        bars=bars,
        hoops=(
            PlanHoop(hull_of(bars, range(n_outer)), q.tie, tie_d, q.tie_spacing),
            PlanHoop(hull_of(bars, range(n_outer, len(bars))), q.tie, tie_d, q.tie_spacing),
        ),
        cover_guides=(PlanCoverGuide(0, q.cover, tie_d, bar_d),),
    )

    def overlap(i: int, j: int) -> str:
        if (i < n_outer) == (j < n_outer):  # one bar ring
            return "spacing_max"
        a, b = bars[i], bars[j]
        return "t_x" if abs(b.x_mm - a.x_mm) >= abs(b.y_mm - a.y_mm) else "t_y"

    return finish(TEMPLATE, plan, placement="center_mm", count="spacing_max", overlap=overlap)
