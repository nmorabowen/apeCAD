"""Bar positions for the layout gestures: a row between two points, bars along an edge.

Exact collinearity (ADR 0032). The strict hull (`convex_hull_ccw`) uses exact float
predicates and no tolerance, and apeConcrete re-derives hoop rings the same way. Bars
interpolated along an inclined line are not exactly collinear in floats, so a middle bar
could survive as a hull vertex. An inclined layout therefore puts its bars on a dyadic
lattice: both ends are snapped to a grid of `SNAP_GRID_MM`, and every bar sits at
`a + m * (b - a) / LATTICE_STEPS` for an integer m. Within `EXTENT_LIMIT_MM` every such
coordinate, every difference of two and every product the hull forms is either exact or
rounds the same real number twice, so any three bars of one layout give a cross product
of exactly 0. An axis-aligned layout copies its constant coordinate and needs no snap.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from apeCAD.errors import DocumentError
from apeCAD.section.geometry import Point2

SNAP_GRID_MM = 2.0**-10
"""Grid the ends of an inclined layout snap to (about 1 µm)."""
LATTICE_STEPS = 2**22
"""Lattice points between the two ends of an inclined layout."""
EXTENT_LIMIT_MM = 2.0**20
"""|x| and |y| bound (about 1 km): lattice coordinates and their differences stay exact.

Coordinates are multiples of 2**-32 mm below 2**20 mm, differences below 2**21 mm: 53
bits at most. A bar moves from its ideal place by under SNAP_GRID_MM + length / 2**23."""
MAX_LAYOUT_BARS = 1000
"""Most bars one layout op places."""
DUPLICATE_BAR_MM = 1.0
"""A layout position this close to an existing bar is taken (the point-reuse distance)."""


def snap(value: float) -> float:
    """`value` on the `SNAP_GRID_MM` grid; exact, because the grid is a power of two."""
    return round(value / SNAP_GRID_MM) * SNAP_GRID_MM


def is_inclined(a: Point2, b: Point2) -> bool:
    """Neither horizontal nor vertical."""
    return a[0] != b[0] and a[1] != b[1]


def row_positions(
    start: Point2, end: Point2, count: int | None, spacing_mm: float | None
) -> list[Point2]:
    """Bars from `start` towards `end`, by count (ends included) or by spacing.

    By spacing, the row holds as many whole spacings as fit, and the remainder is split
    evenly between the two ends (centred, ADR 0024 open q7, the proposed default).
    """
    _require_extent((start, end), "a bar row")
    a, b = (_snap_point(start), _snap_point(end)) if is_inclined(start, end) else (start, end)
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    if length == 0.0:
        raise DocumentError(f"a bar row needs two distinct ends, got {start} and {end}")
    if count is not None:
        params = _count_params(count)
    else:
        spacing = _require_spacing(spacing_mm)
        intervals = math.floor(length / spacing + 1e-9)
        if intervals < 1:
            raise DocumentError(
                f"spacing {spacing:g} mm is longer than the row ({length:g} mm)"
            )
        _require_bar_count(intervals + 1)
        margin = max(0.0, length - intervals * spacing) / 2.0
        params = [(margin + k * spacing) / length for k in range(intervals + 1)]
    return _place(a, b, params)


def edge_positions(
    ring: Sequence[Point2], edge_index: int, count: int | None, spacing_mm: float | None
) -> list[Point2]:
    """Bars on edge `edge_index` of a ring (vertex i to i + 1), both corners included.

    By count, the edge is split evenly. By spacing, it takes the fewest equal intervals
    no longer than `spacing_mm`. When any edge of the ring is inclined, every vertex is
    snapped first, so the corner two edges share is the same point on both.
    """
    if not 0 <= edge_index < len(ring):
        raise DocumentError(
            f"edge_index {edge_index} is out of range for a ring of {len(ring)} edges"
        )
    _require_extent(ring, "a bar-centre ring")
    points = list(ring)
    if any(is_inclined(points[i - 1], points[i]) for i in range(len(points))):
        points = [_snap_point(p) for p in points]
    a = points[edge_index]
    b = points[(edge_index + 1) % len(points)]
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    if length == 0.0:
        raise DocumentError(f"edge {edge_index} of the bar-centre ring has no length")
    if count is not None:
        params = _count_params(count)
    else:
        spacing = _require_spacing(spacing_mm)
        intervals = max(1, math.ceil(length / spacing - 1e-9))
        _require_bar_count(intervals + 1)
        params = [k / intervals for k in range(intervals + 1)]
    return _place(a, b, params)


def _place(a: Point2, b: Point2, params: Sequence[float]) -> list[Point2]:
    """Points at parameters t in [0, 1] from a to b; the lattice when the line is inclined."""
    if is_inclined(a, b):
        ux = (b[0] - a[0]) / LATTICE_STEPS
        uy = (b[1] - a[1]) / LATTICE_STEPS
        out: list[Point2] = []
        for t in params:
            m = round(t * LATTICE_STEPS)
            out.append((a[0] + m * ux, a[1] + m * uy))
        return out
    placed: list[Point2] = []
    for t in params:
        if t == 0.0:
            placed.append(a)
        elif t == 1.0:
            placed.append(b)
        elif a[1] == b[1]:
            placed.append((a[0] + t * (b[0] - a[0]), a[1]))
        else:
            placed.append((a[0], a[1] + t * (b[1] - a[1])))
    return placed


def _count_params(count: int) -> list[float]:
    if count < 2:
        raise DocumentError(f"count must be 2 or more (both ends hold a bar), got {count}")
    _require_bar_count(count)
    return [k / (count - 1) for k in range(count)]


def _require_spacing(spacing_mm: float | None) -> float:
    if spacing_mm is None or not (math.isfinite(spacing_mm) and spacing_mm > 0.0):
        raise DocumentError(f"spacing_mm must be positive and finite, got {spacing_mm!r}")
    return spacing_mm


def _require_bar_count(count: int) -> None:
    if count > MAX_LAYOUT_BARS:
        raise DocumentError(
            f"this layout would place {count} bars; one op places at most {MAX_LAYOUT_BARS}"
        )


def _require_extent(points: Sequence[Point2], what: str) -> None:
    for x, y in points:
        if not (abs(x) <= EXTENT_LIMIT_MM and abs(y) <= EXTENT_LIMIT_MM):
            raise DocumentError(
                f"{what} reaches ({x:g}, {y:g}); bar layouts stay within "
                f"±{EXTENT_LIMIT_MM:g} mm, where their positions are exact (ADR 0032)"
            )


def _snap_point(p: Point2) -> Point2:
    return (snap(p[0]), snap(p[1]))
