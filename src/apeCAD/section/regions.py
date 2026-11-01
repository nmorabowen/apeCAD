"""Plane predicates for the section lint: rings, circles and face regions (ADR 0039).

The v1 helpers (`locate`, `edge_distance`, `segment_inside`) are exact float predicates on a
ring, moved here unchanged from `apeCAD.section.lint`. The v2 part reads a face as a
`Region`: inside its boundary (a ring or an exact circle), outside each of its holes.
Point tests are exact. `boundary_probes` samples a circle as chords only to place probe
points beside every boundary piece; the probes are then tested exactly, so an overlap found
is real, and a sliver thinner than the probe offset can be missed. Lint is advisory.
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


_CIRCLE_PROBE_SIDES = 64
"""A circle is sampled as this many chords for overlap probes only; tests stay exact."""


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

    def polygon(self) -> tuple[Point2, ...]:
        if self.ring:
            return self.ring
        n, (cx, cy), r = _CIRCLE_PROBE_SIDES, self.center, self.radius
        return tuple(
            (cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n))
            for k in range(n)
        )


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

    Every edge of every curve (circles as chords) is cut where it meets another edge; each
    piece's midpoint is pushed off the edge both ways. Two regions whose interiors meet have
    a piece of boundary between them, and a probe next to it lies in both.
    """
    edges = [
        (poly[k], poly[(k + 1) % len(poly)])
        for r in regions
        for poly in (c.polygon() for c in (r.boundary, *r.holes))
        if len(poly) >= 2
        for k in range(len(poly))
    ]
    xs = [p[0] for edge in edges for p in edge] or [0.0]
    ys = [p[1] for edge in edges for p in edge] or [0.0]
    eps = 1e-7 * max(1.0, max(xs) - min(xs), max(ys) - min(ys))
    out: list[Point2] = []
    for a, b in edges:
        rx, ry = b[0] - a[0], b[1] - a[1]
        length = math.hypot(rx, ry)
        if length == 0.0:
            continue
        cuts = {0.0, 1.0}
        for c, d in edges:
            sx, sy = d[0] - c[0], d[1] - c[1]
            den = rx * sy - ry * sx
            if den != 0.0:
                t = ((c[0] - a[0]) * sy - (c[1] - a[1]) * sx) / den
                u = ((c[0] - a[0]) * ry - (c[1] - a[1]) * rx) / den
                if 0.0 < t < 1.0 and 0.0 <= u <= 1.0:
                    cuts.add(t)
        ordered = sorted(cuts)
        nx, ny = -ry / length * eps, rx / length * eps
        for s, e in zip(ordered, ordered[1:], strict=False):
            mx, my = a[0] + (s + e) / 2.0 * rx, a[1] + (s + e) / 2.0 * ry
            out.extend(((mx + nx, my + ny), (mx - nx, my - ny)))
    return out


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
