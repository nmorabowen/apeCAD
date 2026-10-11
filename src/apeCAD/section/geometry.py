"""Kernel-free planar geometry for section mode (ADR 0024 decision 7, ADR 0004).

Rings are sequences of (x_mm, y_mm) tuples in world millimetres on the z = 0 plane, x right
and y up. A ring is given once, with no repeated closing point. Predicates use exact float
arithmetic and no tolerance, so a consumer that re-derives a result with the same
arithmetic gets the same answer (apeConcrete re-derives hoop rings, ADR 0025).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from apeCAD.errors import DocumentError
from apeCAD.geometry import require_finite

Point2 = tuple[float, float]


def _cross(o: Point2, a: Point2, b: Point2) -> float:
    """z of (a - o) x (b - o): > 0 when o, a, b turn counter-clockwise."""
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _points(ring: Sequence[Point2], name: str = "ring") -> list[Point2]:
    points: list[Point2] = []
    for i, (x, y) in enumerate(ring):
        points.append(
            (require_finite(f"{name}[{i}].x_mm", x), require_finite(f"{name}[{i}].y_mm", y))
        )
    return points


def signed_area(ring: Sequence[Point2]) -> float:
    """Shoelace area in mm²: positive for a counter-clockwise ring, negative for clockwise."""
    points = _points(ring)
    n = len(points)
    twice = 0.0
    for i in range(n):
        x0, y0 = points[i]
        x1, y1 = points[(i + 1) % n]
        twice += x0 * y1 - x1 * y0
    return twice / 2.0


def ensure_ccw(ring: Sequence[Point2]) -> list[Point2]:
    """The ring as a counter-clockwise list: reversed when clockwise, copied otherwise."""
    points = _points(ring)
    if len(points) < 3:
        raise DocumentError(f"a ring needs at least 3 vertices, got {len(points)}")
    area = signed_area(points)
    if area == 0.0:
        raise DocumentError("a ring of zero area has no orientation")
    return points if area > 0.0 else points[::-1]


def _on_segment(p: Point2, a: Point2, b: Point2) -> bool:
    """p, known collinear with a and b, lies within the box of segment ab."""
    return min(a[0], b[0]) <= p[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= p[1] <= max(
        a[1], b[1]
    )


def _segments_touch(a: Point2, b: Point2, c: Point2, d: Point2) -> bool:
    """Closed segments ab and cd share at least one point."""
    d1 = _cross(c, d, a)
    d2 = _cross(c, d, b)
    d3 = _cross(a, b, c)
    d4 = _cross(a, b, d)
    if ((d1 > 0.0 and d2 < 0.0) or (d1 < 0.0 and d2 > 0.0)) and (
        (d3 > 0.0 and d4 < 0.0) or (d3 < 0.0 and d4 > 0.0)
    ):
        return True
    return (
        (d1 == 0.0 and _on_segment(a, c, d))
        or (d2 == 0.0 and _on_segment(b, c, d))
        or (d3 == 0.0 and _on_segment(c, a, b))
        or (d4 == 0.0 and _on_segment(d, a, b))
    )


def _simplicity_fault(points: Sequence[Point2]) -> str | None:
    """Why a ring is not simple, or None when it is."""
    n = len(points)
    if n < 3:
        return f"a ring needs at least 3 vertices, got {n}"
    seen: dict[Point2, int] = {}
    for i, p in enumerate(points):
        if p in seen:
            return f"vertices {seen[p]} and {i} repeat the point {p}"
        seen[p] = i
    for i in range(n):
        a, b = points[i], points[(i + 1) % n]
        # The next edge shares vertex b: it may only overlap this one by doubling back.
        c = points[(i + 2) % n]
        if _cross(a, b, c) == 0.0 and (a[0] - b[0]) * (c[0] - b[0]) + (a[1] - b[1]) * (
            c[1] - b[1]
        ) > 0.0:
            return f"edges {i} and {(i + 1) % n} overlap"
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue  # the closing edge is adjacent to edge 0, handled above
            if _segments_touch(a, b, points[j], points[(j + 1) % n]):
                return f"edges {i} and {j} cross or touch"
    return None


def is_simple(ring: Sequence[Point2]) -> bool:
    """At least 3 vertices, no repeated vertex, and no two edges meeting except at a shared
    vertex of neighbouring edges."""
    return _simplicity_fault(_points(ring)) is None


def convex_hull_ccw(points: Mapping[int, Point2]) -> list[int]:
    """The strict counter-clockwise convex hull of id -> (x, y), as a ring of ids.

    Collinear points are dropped, so three bars in a line are never hull vertices
    (ADR 0024 P2). The ring starts at the lowest (x, y) and depends only on positions,
    never on the mapping's order; among points at one exact position the smallest id
    stands for them. Fewer than 3 hull vertices is a DocumentError.
    """
    by_position: dict[Point2, int] = {}
    for entity_id, (x, y) in points.items():
        key = (
            require_finite(f"point {entity_id} x_mm", x),
            require_finite(f"point {entity_id} y_mm", y),
        )
        if key not in by_position or entity_id < by_position[key]:
            by_position[key] = entity_id
    ordered = sorted(by_position)
    if len(ordered) >= 3:
        lower: list[Point2] = []
        for p in ordered:
            while len(lower) >= 2 and _cross(lower[-2], lower[-1], p) <= 0.0:
                lower.pop()
            lower.append(p)
        upper: list[Point2] = []
        for p in reversed(ordered):
            while len(upper) >= 2 and _cross(upper[-2], upper[-1], p) <= 0.0:
                upper.pop()
            upper.append(p)
        hull = lower[:-1] + upper[:-1]
    else:
        hull = ordered
    if len(hull) < 3:
        raise DocumentError(
            f"a hull needs 3 non-collinear points; these {len(points)} give {len(hull)} "
            "hull vertices"
        )
    return [by_position[p] for p in hull]


def _left_normal(a: Point2, b: Point2) -> Point2:
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    length = math.hypot(dx, dy)
    return (-dy / length, dx / length)


def miter_offset(ring: Sequence[Point2], distance: float) -> list[Point2]:
    """Inset (distance > 0) or outset (distance < 0) a simple ring by mitred edges.

    Every edge moves `distance` mm along its inward normal and each vertex goes to where its
    two moved edges meet. The result is counter-clockwise, vertex i from vertex i of
    `ensure_ccw(ring)`. Refuses a ring that is not simple, an edge that collapses or flips,
    and a result that is not simple.
    """
    require_finite("distance", distance)
    points = _points(ring)
    fault = _simplicity_fault(points)
    if fault is not None:
        raise DocumentError(f"cannot offset a ring that is not simple: {fault}")
    points = ensure_ccw(points)
    if distance == 0.0:
        return points
    n = len(points)
    normals = [_left_normal(points[i], points[(i + 1) % n]) for i in range(n)]
    result: list[Point2] = []
    for i in range(n):
        n1 = normals[i - 1]
        n2 = normals[i]
        # n1 . p = d and n2 . p = d (relative to the vertex), closed form of the miter.
        scale = distance / (1.0 + n1[0] * n2[0] + n1[1] * n2[1])
        vx, vy = points[i]
        result.append((vx + scale * (n1[0] + n2[0]), vy + scale * (n1[1] + n2[1])))
    for i in range(n):
        a, b = points[i], points[(i + 1) % n]
        p, q = result[i], result[(i + 1) % n]
        if (b[0] - a[0]) * (q[0] - p[0]) + (b[1] - a[1]) * (q[1] - p[1]) <= 0.0:
            raise DocumentError(
                f"offset by {distance:g} mm collapses or flips edge {i}; "
                "the ring is too thin for it"
            )
    fault = _simplicity_fault(result)
    if fault is not None:
        raise DocumentError(f"offset by {distance:g} mm self-intersects: {fault}")
    return result


def _offset_polyline(axis: Sequence[Point2], half: Sequence[float]) -> list[Point2]:
    """Points of an open axis moved half[k] mm to the left of segment k, mitred at joints."""
    normals = [_left_normal(axis[k], axis[k + 1]) for k in range(len(axis) - 1)]
    out: list[Point2] = [
        (axis[0][0] + half[0] * normals[0][0], axis[0][1] + half[0] * normals[0][1])
    ]
    for k in range(1, len(axis) - 1):
        n1, n2 = normals[k - 1], normals[k]
        h1, h2 = half[k - 1], half[k]
        vx, vy = axis[k]
        det = n1[0] * n2[1] - n1[1] * n2[0]
        if det != 0.0:
            # Solve n1 . u = h1, n2 . u = h2 for the joint offset u.
            out.append(
                (vx + (h1 * n2[1] - h2 * n1[1]) / det, vy + (n1[0] * h2 - n2[0] * h1) / det)
            )
        elif h1 == h2:
            out.append((vx + h1 * n1[0], vy + h1 * n1[1]))
        else:  # a straight joint where the thickness steps
            out.append((vx + h1 * n1[0], vy + h1 * n1[1]))
            out.append((vx + h2 * n1[0], vy + h2 * n1[1]))
    last = axis[-1]
    out.append((last[0] + half[-1] * normals[-1][0], last[1] + half[-1] * normals[-1][1]))
    return out


def chain_outline(
    axis: Sequence[Point2], thickness_mm: float | Sequence[float]
) -> list[Point2]:
    """One counter-clockwise outline ring around a wall axis chain.

    `axis` is an open polyline of at least 2 points; `thickness_mm` is one wall thickness,
    or one per segment. Each segment is centred on its axis, joints are mitred, and the two
    ends are square. Refuses a closed or doubled-back axis and an outline that is not simple.
    """
    points = _points(axis, "axis")
    if len(points) < 2:
        raise DocumentError(f"a wall axis needs at least 2 points, got {len(points)}")
    segments = len(points) - 1
    if isinstance(thickness_mm, (int, float)):
        thicknesses = [float(thickness_mm)] * segments
    else:
        thicknesses = [float(t) for t in thickness_mm]
        if len(thicknesses) != segments:
            raise DocumentError(
                f"a wall axis of {segments} segments needs {segments} thicknesses, "
                f"got {len(thicknesses)}"
            )
    for k, t in enumerate(thicknesses):
        if not (require_finite(f"thickness_mm[{k}]", t) > 0.0):
            raise DocumentError(f"thickness_mm[{k}] must be positive, got {t!r}")
    if len(set(points)) != len(points):
        raise DocumentError("a wall axis must not repeat a point; closed chains are not walls")
    for k in range(1, segments):
        a, v, b = points[k - 1], points[k], points[k + 1]
        if _cross(a, v, b) == 0.0 and (a[0] - v[0]) * (b[0] - v[0]) + (a[1] - v[1]) * (
            b[1] - v[1]
        ) > 0.0:
            raise DocumentError(f"the wall axis doubles back at point {k}")
    half = [t / 2.0 for t in thicknesses]
    right = _offset_polyline(points, [-h for h in half])
    left = _offset_polyline(points, half)
    ring = right + left[::-1]
    fault = _simplicity_fault(ring)
    if fault is not None:
        raise DocumentError(f"the wall chain outline is not simple: {fault}")
    return ensure_ccw(ring)
