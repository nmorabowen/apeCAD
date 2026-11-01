"""`polygon_column`, version 1: a convex polygonal tied column (ADR 0040 decision 5).

Draws `ring` as given (normalised to CCW; it is the placement, so this template takes no
`center_mm`), its cover guide, bars along every edge of the bar-centre ring and one hoop on
their strict hull. The bar-centre ring is `ring` inset by `cover + tie + bar / 2` with
mitred edges (`miter_offset`, as `section.cover`); each of its edges takes the fewest equal
intervals no longer than `spacing_max` (`layout.edge_positions`, ADR 0032), so the bars on
an inclined edge stay exactly collinear and drop out of the hull.

Version 1 is convex only (owner ruling Q4, C3 record): a ring with a reflex vertex is
refused, and so is a straight (collinear) one (Errata 8.4, the builder's stricter reading). A
later version may widen it.

Overlapping bars (closer than the mean of their diameters) are refused: two neighbours on an
edge of several intervals by `spacing_max`, any other pair (a short edge, an acute corner, a
sliver whose opposite faces come close) by `ring`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from apeCAD.errors import DocumentError
from apeCAD.section.designations import DESIGNATIONS
from apeCAD.section.geometry import Point2, ensure_ccw, is_simple, miter_offset
from apeCAD.section.templates.plan import (
    MAX_TEMPLATE_BARS,
    Params,
    Plan,
    PlanBar,
    PlanCoverGuide,
    PlanFace,
    PlanHoop,
    PlanRing,
    finish,
    hull_of,
    layout_ring,
    point_value,
    require_bar_count,
    require_extent,
    ring_intervals,
    ring_positions,
)

TEMPLATE = "polygon_column"
VERSION = 1
FIELDS = (
    "material", "bar_material", "ring", "cover", "bar", "spacing_max", "tie", "tie_spacing",
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class PolygonColumnParams:
    """`polygon_column` v1 parameters; `ring` is CCW once parsed."""

    material: str
    ring: tuple[Point2, ...]
    cover: float
    bar: str
    spacing_max: float
    tie: str
    tie_spacing: float
    bar_material: str | None = None


def parse(data: Mapping[str, object]) -> PolygonColumnParams:
    """Read and check a `polygon_column` parameter mapping; each fault is refused by name."""
    p = Params(TEMPLATE, data, FIELDS)
    return PolygonColumnParams(
        material=p.material("material"),
        bar_material=p.optional_material("bar_material"),
        ring=_convex_ring(p),
        cover=p.length("cover"),
        bar=p.designation("bar")[0],
        spacing_max=p.length("spacing_max"),
        tie=p.designation("tie")[0],
        tie_spacing=p.length("tie_spacing"),
    )


def _convex_ring(p: Params) -> tuple[Point2, ...]:
    raw = p.sequence("ring")
    points = [point_value(p, f"ring[{i}]", v) for i, v in enumerate(raw)]
    if len(points) < 3:
        raise p.error("ring", f"needs 3 or more vertices, got {len(points)}")
    if len(points) > MAX_TEMPLATE_BARS:  # every inset vertex holds a bar: over the cap
        raise p.error(
            "ring",
            f"has {len(points)} vertices; each holds a bar, and a template places at most "
            f"{MAX_TEMPLATE_BARS}",
        )
    require_extent(p.template, "ring", points)
    if not is_simple(points):
        raise p.error("ring", "must be a simple polygon (no repeated vertex, no crossing)")
    ring = ensure_ccw(points)
    n = len(ring)
    for i in range(n):
        (ax, ay), (bx, by), (cx, cy) = ring[i - 1], ring[i], ring[(i + 1) % n]
        if (bx - ax) * (cy - by) - (by - ay) * (cx - bx) <= 0.0:
            raise p.error(
                "ring",
                f"vertex {i} ({bx:g}, {by:g}) is not a convex corner; "
                "polygon_column v1 takes strictly convex rings only",
            )
    return tuple(ring)


def expand_v1(data: Mapping[str, object]) -> Plan:
    """The `polygon_column` v1 plan of a parameter mapping."""
    q = parse(data)
    p = Params(TEMPLATE, {}, ())
    bar_d, tie_d = DESIGNATIONS[q.bar], DESIGNATIONS[q.tie]
    inset = q.cover + tie_d + bar_d / 2.0
    try:
        centre_ring = miter_offset(q.ring, inset)
    except DocumentError as exc:
        raise p.error(
            "ring", f"too small for the bar-centre inset {inset:g} mm: {exc}"
        ) from exc
    centre_ring = layout_ring(centre_ring)
    intervals = ring_intervals(centre_ring, q.spacing_max)  # bars per edge, corners shared
    require_bar_count(p, {"spacing_max": sum(intervals)})
    positions: list[Point2] = []
    edge_of: list[int] = []  # the edge each bar starts
    try:
        for edge, placed in enumerate(ring_positions(centre_ring, q.spacing_max)):
            positions += placed
            edge_of += [edge] * len(placed)
    except DocumentError as exc:  # the ring's extent was checked in parse
        raise p.error("spacing_max", str(exc)) from exc
    bars = tuple(PlanBar(x, y, q.bar, bar_d, q.bar_material) for x, y in positions)

    def overlap(i: int, j: int) -> str:
        n = len(bars)
        if (j - i) % n == 1 or (i - j) % n == 1:  # neighbours along one edge
            first = i if (j - i) % n == 1 else j
            if intervals[edge_of[first]] > 1:
                return "spacing_max"
        return "ring"

    plan = Plan(
        faces=(PlanFace("concrete", q.material, PlanRing(q.ring)),),
        bars=bars,
        hoops=(PlanHoop(hull_of(bars, range(len(bars))), q.tie, tie_d, q.tie_spacing),),
        cover_guides=(PlanCoverGuide(0, q.cover, tie_d, bar_d),),
    )
    return finish(TEMPLATE, plan, placement="ring", count="spacing_max", overlap=overlap)
