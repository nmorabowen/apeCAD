"""Plane predicates for the section lint: rings, circles and face regions (ADR 0039).

The v1 helpers (`locate`, `edge_distance`, `segment_inside`) are exact float predicates on a
ring, moved here unchanged from `apeCAD.section.lint`. The v2 part reads a face as a
`Region`: inside its boundary (a ring or an exact circle), outside each of its holes.
Point tests are exact. `boundary_probes` places probe points beside every boundary piece,
off segments by their normal and off circles radially at a point on the true arc, at a
distance of 1e-7 of the probed regions' extent; the probes are then tested exactly. So an
overlap found is real, and a region thinner than that offset can be missed. Lint is
advisory.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from apeCAD.entities import (
    CircleBoundary,
    ConcreteFace,
    Entity,
    EntityId,
    RingBoundary,
    SectionFace,
)
from apeCAD.section.geometry import Point2


def cross(o: Point2, a: Point2, b: Point2) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def distance(a: Point2, b: Point2) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def on_segment(p: Point2, a: Point2, b: Point2) -> bool:
    return (
        cross(a, b, p) == 0.0
        and min(a[0], b[0]) <= p[0] <= max(a[0], b[0])
        and min(a[1], b[1]) <= p[1] <= max(a[1], b[1])
    )


def locate(p: Point2, ring: Sequence[Point2]) -> int:
    """1 inside, 0 on the boundary, -1 outside (even-odd rule)."""
    n = len(ring)
    if n < 3:
        return -1
    inside = False
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        if on_segment(p, a, b):
            return 0
        if (a[1] > p[1]) != (b[1] > p[1]):
            x = a[0] + (p[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if x > p[0]:
                inside = not inside
    return 1 if inside else -1


def edge_distance(p: Point2, ring: Sequence[Point2]) -> float:
    """Shortest distance from p to the ring's edges."""
    best = math.inf
    n = len(ring)
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length2 = dx * dx + dy * dy
        t = 0.0 if length2 == 0.0 else ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2
        t = min(1.0, max(0.0, t))
        best = min(best, distance(p, (a[0] + t * dx, a[1] + t * dy)))
    return best


def segment_inside(a: Point2, b: Point2, ring: Sequence[Point2]) -> bool:
    """Segment ab stays inside the ring or on its boundary.

    Cut ab where it meets an edge or passes a vertex; it is inside when both ends and the
    midpoint of every piece between cuts are inside or on the boundary. The cut points
    themselves are not probed: they lie on an edge, where rounding may put them outside.
    """
    return all(locate(q, ring) >= 0 for q in segment_probes(a, b, ring))


def segment_probes(a: Point2, b: Point2, ring: Sequence[Point2]) -> list[Point2]:
    """Both ends of ab and the midpoint of every piece between its cuts by the ring."""
    cuts = {0.0, 1.0}
    n = len(ring)
    rx, ry = b[0] - a[0], b[1] - a[1]
    for i in range(n):
        c, d = ring[i], ring[(i + 1) % n]
        sx, sy = d[0] - c[0], d[1] - c[1]
        denominator = rx * sy - ry * sx
        if denominator != 0.0:
            t = ((c[0] - a[0]) * sy - (c[1] - a[1]) * sx) / denominator
            u = ((c[0] - a[0]) * ry - (c[1] - a[1]) * rx) / denominator
            if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
                cuts.add(t)
        length2 = rx * rx + ry * ry
        if length2 > 0.0:
            t = ((c[0] - a[0]) * rx + (c[1] - a[1]) * ry) / length2
            if 0.0 <= t <= 1.0:
                cuts.add(t)  # a vertex the segment may graze
    ordered = sorted(cuts)
    probes = [0.0, 1.0, *((s + e) / 2.0 for s, e in zip(ordered, ordered[1:], strict=False))]
    return [(a[0] + t * rx, a[1] + t * ry) for t in probes]


_CIRCLE_ARCS = 64
"""A circle is probed at the mid-angle of at least this many arcs, besides its cuts."""

_PROBE_OFFSET = 1e-7
"""Probe distance from a boundary piece, as a fraction of the probed regions' extent."""


@dataclass(frozen=True, slots=True)
class Curve:
    """A boundary or a hole: a ring, or a circle (`ring` empty, `center` and `radius`)."""

    ring: tuple[Point2, ...]
    center: Point2 = (0.0, 0.0)
    radius: float = 0.0

    def locate(self, p: Point2) -> int:
        if self.ring:
            return locate(p, self.ring)
        d2 = (p[0] - self.center[0]) ** 2 + (p[1] - self.center[1]) ** 2
        r2 = self.radius * self.radius
        return 1 if d2 < r2 else 0 if d2 == r2 else -1

    def distance(self, p: Point2) -> float:
        if self.ring:
            return edge_distance(p, self.ring)
        return abs(distance(p, self.center) - self.radius)

    def edges(self) -> list[tuple[Point2, Point2]]:
        n = len(self.ring)
        return [(self.ring[k], self.ring[(k + 1) % n]) for k in range(n)] if n >= 2 else []


@dataclass(frozen=True, slots=True)
class Region:
    """A face's region: inside its boundary, outside each of its holes."""

    face_id: EntityId
    role: str
    boundary: Curve
    holes: tuple[Curve, ...]

    def contains(self, p: Point2) -> bool:
        """Strictly inside: off every curve."""
        return self.boundary.locate(p) > 0 and all(h.locate(p) < 0 for h in self.holes)

    def covers(self, p: Point2) -> bool:
        """Inside or on a curve."""
        return self.boundary.locate(p) >= 0 and all(h.locate(p) <= 0 for h in self.holes)

    def clearance(self, p: Point2) -> float:
        return min(c.distance(p) for c in (self.boundary, *self.holes))


def curve_of(boundary: RingBoundary | CircleBoundary, xy: Mapping[EntityId, Point2]) -> Curve:
    if isinstance(boundary, RingBoundary):
        return Curve(tuple(xy[i] for i in boundary.point_ids if i in xy))
    return Curve((), xy.get(boundary.center_id, (0.0, 0.0)), boundary.radius_mm)


def regions_of(
    entities: Mapping[EntityId, Entity], xy: Mapping[EntityId, Point2]
) -> list[Region]:
    """Every v1 and v2 face as a region, in entity-id order (a v1 face is concrete)."""
    out: list[Region] = []
    for e in (entities[i] for i in sorted(entities)):
        if isinstance(e, ConcreteFace):
            ring = Curve(tuple(xy[i] for i in e.point_ids if i in xy))
            out.append(Region(e.entity_id, "concrete", ring, ()))
        elif isinstance(e, SectionFace):
            holes = tuple(curve_of(h, xy) for h in e.holes)
            out.append(Region(e.entity_id, e.role, curve_of(e.boundary, xy), holes))
    return out


def segment_in_region(a: Point2, b: Point2, region: Region) -> bool:
    """ab stays in the region's closure: inside its boundary, out of each hole's interior."""
    if not _segment_against(a, b, region.boundary, inside=True):
        return False
    return all(_segment_against(a, b, hole, inside=False) for hole in region.holes)


def _segment_against(a: Point2, b: Point2, curve: Curve, *, inside: bool) -> bool:
    if curve.ring:
        probes = segment_probes(a, b, curve.ring)
        return all((curve.locate(q) >= 0) if inside else (curve.locate(q) <= 0) for q in probes)
    if inside:  # a disc is convex
        return curve.locate(a) >= 0 and curve.locate(b) >= 0
    return _segment_distance(curve.center, a, b) >= curve.radius


def boundary_probes(regions: Sequence[Region]) -> list[Point2]:
    """Points just either side of the middle of every boundary piece of these regions.

    Every segment and every circle is cut where it meets another curve. A segment piece's
    midpoint is pushed off along its normal; a circle piece is probed at its mid-angle on the
    true arc, at radius r +- the offset. Two regions whose interiors meet have a piece of
    boundary between them, and a probe next to it lies in both.
    """
    curves = [c for r in regions for c in (r.boundary, *r.holes)]
    segments = [edge for c in curves for edge in c.edges()]
    circles = [c for c in curves if not c.ring and c.radius > 0.0]
    xs = [p[0] for a, b in segments for p in (a, b)]
    ys = [p[1] for a, b in segments for p in (a, b)]
    for c in circles:
        xs += [c.center[0] - c.radius, c.center[0] + c.radius]
        ys += [c.center[1] - c.radius, c.center[1] + c.radius]
    if not xs:
        return []
    eps = _PROBE_OFFSET * max(1.0, max(xs) - min(xs), max(ys) - min(ys))
    out: list[Point2] = []
    for a, b in segments:
        rx, ry = b[0] - a[0], b[1] - a[1]
        length = math.hypot(rx, ry)
        if length == 0.0:
            continue
        cuts = {0.0, 1.0}
        for c, d in segments:
            sx, sy = d[0] - c[0], d[1] - c[1]
            den = rx * sy - ry * sx
            if den != 0.0:
                t = ((c[0] - a[0]) * sy - (c[1] - a[1]) * sx) / den
                u = ((c[0] - a[0]) * ry - (c[1] - a[1]) * rx) / den
                if 0.0 < t < 1.0 and 0.0 <= u <= 1.0:
                    cuts.add(t)
        for circle in circles:
            cuts.update(t for t in _segment_circle(a, b, circle) if 0.0 < t < 1.0)
        ordered = sorted(cuts)
        nx, ny = -ry / length * eps, rx / length * eps
        for s, e in zip(ordered, ordered[1:], strict=False):
            mx, my = a[0] + (s + e) / 2.0 * rx, a[1] + (s + e) / 2.0 * ry
            out.extend(((mx + nx, my + ny), (mx - nx, my - ny)))
    for circle in circles:
        (cx, cy), r = circle.center, circle.radius
        angles = {2.0 * math.pi * k / _CIRCLE_ARCS for k in range(_CIRCLE_ARCS)}
        for a, b in segments:
            for t in _segment_circle(a, b, circle):
                if 0.0 <= t <= 1.0:
                    x, y = a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])
                    angles.add(math.atan2(y - cy, x - cx) % (2.0 * math.pi))
        for other in circles:
            angles.update(_circle_circle(circle, other))
        ordered = sorted(angles)
        for s, e in zip(ordered, [*ordered[1:], ordered[0] + 2.0 * math.pi], strict=True):
            mid = (s + e) / 2.0
            for radius in (r - eps, r + eps):
                out.append((cx + radius * math.cos(mid), cy + radius * math.sin(mid)))
    return out


def _segment_circle(a: Point2, b: Point2, circle: Curve) -> list[float]:
    """Parameters t (any value) where the line a + t(b - a) meets the circle."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    fx, fy = a[0] - circle.center[0], a[1] - circle.center[1]
    qa = dx * dx + dy * dy
    qb = 2.0 * (fx * dx + fy * dy)
    qc = fx * fx + fy * fy - circle.radius * circle.radius
    disc = qb * qb - 4.0 * qa * qc
    if qa == 0.0 or disc < 0.0:
        return []
    root = math.sqrt(disc)
    return [(-qb - root) / (2.0 * qa), (-qb + root) / (2.0 * qa)]


def _circle_circle(circle: Curve, other: Curve) -> list[float]:
    """Angles on `circle` (0 to 2 pi) of the points where `other` crosses it."""
    (x1, y1), r1 = circle.center, circle.radius
    (x2, y2), r2 = other.center, other.radius
    d = math.hypot(x2 - x1, y2 - y1)
    if d == 0.0 or d > r1 + r2 or d < abs(r1 - r2):
        return []
    along = (r1 * r1 - r2 * r2 + d * d) / (2.0 * d)
    half = math.sqrt(max(0.0, r1 * r1 - along * along))
    ux, uy = (x2 - x1) / d, (y2 - y1) / d
    base = math.atan2(uy, ux)
    spread = math.atan2(half, along)
    return [(base + spread) % (2.0 * math.pi), (base - spread) % (2.0 * math.pi)]


def curve_strictly_inside(inner: Curve, outer: Curve) -> bool:
    """`inner` lies in the interior of `outer` and touches it nowhere."""
    if not inner.ring:
        if outer.ring:
            return outer.locate(inner.center) > 0 and outer.distance(inner.center) > inner.radius
        return distance(inner.center, outer.center) + inner.radius < outer.radius
    if not all(outer.locate(p) > 0 for p in inner.ring):
        return False
    if not outer.ring:
        return True  # a disc is convex
    n, m = len(inner.ring), len(outer.ring)
    return not any(
        _touch(inner.ring[i], inner.ring[(i + 1) % n], outer.ring[j], outer.ring[(j + 1) % m])
        for i in range(n)
        for j in range(m)
    )


def curve_within(inner: Curve, outer: Curve) -> bool:
    """`inner` lies inside `outer` or on it: touching, or the same curve, counts as within."""
    if not inner.ring:
        if outer.ring:
            return outer.locate(inner.center) > 0 and outer.distance(inner.center) >= inner.radius
        return distance(inner.center, outer.center) + inner.radius <= outer.radius
    if not outer.ring:
        return all(outer.locate(p) >= 0 for p in inner.ring)  # a disc is convex
    n = len(inner.ring)
    return all(segment_inside(inner.ring[i], inner.ring[(i + 1) % n], outer.ring) for i in range(n))


def circle_in_region(center: Point2, radius: float, region: Region) -> bool:
    """A circle (the line, not the disc) lies in the region's interior."""
    if not curve_strictly_inside(Curve((), center, radius), region.boundary):
        return False
    for hole in region.holes:
        if hole.ring:
            inside = all(distance(p, center) < radius for p in hole.ring)
            outside = hole.locate(center) < 0 and hole.distance(center) > radius
        else:
            gap = distance(center, hole.center)
            inside = gap + hole.radius < radius
            outside = gap - hole.radius > radius
        if not (inside or outside):
            return False
    return True


def _segment_distance(p: Point2, a: Point2, b: Point2) -> float:
    return edge_distance(p, (a, b))


def _touch(a: Point2, b: Point2, c: Point2, d: Point2) -> bool:
    """Closed segments ab and cd share a point."""
    d1, d2 = cross(c, d, a), cross(c, d, b)
    d3, d4 = cross(a, b, c), cross(a, b, d)
    if _opposite(d1, d2) and _opposite(d3, d4):
        return True
    return any(on_segment(p, s, e) for p, s, e in ((a, c, d), (b, c, d), (c, a, b), (d, a, b)))


def _opposite(u: float, v: float) -> bool:
    """Strictly opposite signs, by sign rather than product (no underflow)."""
    return (u > 0.0 and v < 0.0) or (u < 0.0 and v > 0.0)
