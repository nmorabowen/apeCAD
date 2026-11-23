"""The exact reference for the hole rules R1 to R7 (ADR 0040 Errata 18.1), apart from the product.

It imports none of the product's predicate code: only the `Plan` data classes it reads. It
works in `fractions.Fraction` on the stored floats, compares squared distances, and uses no
square root, no trigonometry, no shapely and no product geometry.

It is also built differently from `section/templates/hole_rules.py`, so the two do not share a
mistake by construction:

- every shape is a *core* (points, segments and maybe a closed region) grown by a radius, and
  d(A, B) = max(0, d(core A, core B) - grow A - grow B), so one function measures every pair;
- a point's place in a ring comes from its winding number, not from crossing parity;
- two segments meet when their exact parametric intersection lies on both, not by orientations;
- a point-to-segment distance is measured to the clamped foot point, not by a cross product;
- a hoop's hull is gift-wrapped (Jarvis), not built by a monotone chain;
- a disc kept within s of a hull uses the Minkowski split on r against s, not a signed distance.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction as Q

from apeCAD.section.templates.plan import Plan, PlanBoundary, PlanCircle

QP = tuple[Q, Q]
ZERO = Q(0)


def qp(p: tuple[float, float]) -> QP:
    return (Q(p[0]), Q(p[1]))


def orient(a: QP, b: QP, c: QP) -> Q:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def dist2(p: QP, q: QP) -> Q:
    return (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2


def foot_dist2(p: QP, a: QP, b: QP) -> Q:
    """Squared distance from p to the closed segment ab, through the clamped foot point."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    t = ZERO if length2 == 0 else ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2
    t = min(Q(1), max(ZERO, t))
    return dist2(p, (a[0] + t * dx, a[1] + t * dy))


def segments_meet(a: QP, b: QP, c: QP, d: QP) -> bool:
    """Closed segments ab and cd share a point: solve a + t(b - a) = c + u(d - c) exactly."""
    rx, ry = b[0] - a[0], b[1] - a[1]
    sx, sy = d[0] - c[0], d[1] - c[1]
    wx, wy = c[0] - a[0], c[1] - a[1]
    den = rx * sy - ry * sx
    if den != 0:
        t = (wx * sy - wy * sx) / den
        u = (wx * ry - wy * rx) / den
        return 0 <= t <= 1 and 0 <= u <= 1
    if wx * ry - wy * rx != 0:
        return False  # parallel, on different lines
    rr = rx * rx + ry * ry
    if rr == 0:
        return foot_dist2(a, c, d) == 0
    t0 = (wx * rx + wy * ry) / rr
    t1 = ((d[0] - a[0]) * rx + (d[1] - a[1]) * ry) / rr
    return max(min(t0, t1), ZERO) <= min(max(t0, t1), Q(1))


def closed(ring: Sequence[QP]) -> tuple[tuple[QP, QP], ...]:
    return tuple((ring[i], ring[(i + 1) % len(ring)]) for i in range(len(ring)))


def winding(p: QP, ring: Sequence[QP]) -> int:
    """Sunday's winding number of `ring` about p (p not on the ring)."""
    w = 0
    for a, b in closed(ring):
        if a[1] <= p[1]:
            if b[1] > p[1] and orient(a, b, p) > 0:
                w += 1
        elif b[1] <= p[1] and orient(a, b, p) < 0:
            w -= 1
    return w


def reaches(p: QP, a: QP, b: QP, reach: Q) -> bool:
    """p lies within `reach` of the box of segment ab (exact): a pair that fails this is
    more than `reach` apart, so the prunes below skip it without measuring it."""
    return (
        min(a[0], b[0]) - reach <= p[0] <= max(a[0], b[0]) + reach
        and min(a[1], b[1]) - reach <= p[1] <= max(a[1], b[1]) + reach
    )


def on_ring(p: QP, ring: Sequence[QP]) -> bool:
    return any(reaches(p, a, b, ZERO) and foot_dist2(p, a, b) == 0 for a, b in closed(ring))


def inside_or_on(p: QP, ring: Sequence[QP]) -> bool:
    return on_ring(p, ring) or winding(p, ring) != 0


def strictly_inside(p: QP, ring: Sequence[QP]) -> bool:
    return not on_ring(p, ring) and winding(p, ring) != 0


@dataclass(frozen=True)
class Core:
    """Points and segments, maybe bounding a closed region, grown by `grow`."""

    pts: tuple[QP, ...]
    segs: tuple[tuple[QP, QP], ...]
    ring: tuple[QP, ...] | None
    grow: Q = ZERO


def point(p: QP, grow: Q = ZERO) -> Core:
    return Core((p,), (), None, grow)


def segment(a: QP, b: QP, grow: Q) -> Core:
    return Core((a, b), ((a, b),), None, grow)


def region(ring: Sequence[QP]) -> Core:
    pts = tuple(ring)
    return Core(pts, closed(pts), pts)


def outline(ring: Sequence[QP]) -> Core:
    """The closed polyline of a ring: its boundary only."""
    pts = tuple(ring)
    return Core(pts, closed(pts), None)


def shape(boundary: PlanBoundary) -> Core:
    if isinstance(boundary, PlanCircle):
        return point(qp(boundary.center_mm), Q(boundary.radius_mm))
    return region([qp(p) for p in boundary.points_mm])


def core_dist2(a: Core, b: Core) -> Q:
    """Squared distance between two cores (0 when they meet)."""
    for x, y in ((a, b), (b, a)):
        if x.ring is not None and any(inside_or_on(p, x.ring) for p in y.pts):
            return ZERO
    if any(segments_meet(*s, *t) for s in a.segs for t in b.segs):
        return ZERO
    found = [foot_dist2(p, *s) for p in a.pts for s in b.segs]
    found += [foot_dist2(p, *s) for p in b.pts for s in a.segs]
    if not found:
        found = [dist2(p, q) for p in a.pts for q in b.pts]
    return min(found)


def box_gap(a: Core, b: Core) -> Q:
    """How far apart the cores' boxes are along x or y (<= 0 when they overlap): a lower bound
    of d(core a, core b), exact. It only saves time; it never decides a pair the distance does
    not."""
    gaps = [ZERO]
    for axis in (0, 1):
        lo_a, hi_a = min(p[axis] for p in a.pts), max(p[axis] for p in a.pts)
        lo_b, hi_b = min(p[axis] for p in b.pts), max(p[axis] for p in b.pts)
        gaps += [lo_b - hi_a, lo_a - hi_b]
    return max(gaps)


def apart(a: Core, b: Core, gap: Q) -> bool:
    """d(a, b) > gap: `core_dist2` > reach squared, with the pairs proven further than `reach`
    by their boxes left unmeasured."""
    reach = a.grow + b.grow + gap
    if box_gap(a, b) > reach:
        return True
    for x, y in ((a, b), (b, a)):
        if x.ring is not None and any(inside_or_on(p, x.ring) for p in y.pts):
            return False
    if any(segments_meet(*s, *t) for s in a.segs for t in b.segs):
        return False
    pairs = [(p, s) for p in a.pts for s in b.segs] + [(p, s) for p in b.pts for s in a.segs]
    r2 = reach * reach
    if pairs:
        return not any(reaches(p, *s, reach) and foot_dist2(p, *s) <= r2 for p, s in pairs)
    return all(dist2(p, q) > r2 for p in a.pts for q in b.pts)


def all_closer(h: Core, centre: QP, s: Q) -> bool:
    """Every point of h is closer than s to `centre` (its farthest point is a core vertex)."""
    room = s - h.grow
    return room > 0 and max(dist2(v, centre) for v in h.pts) < room * room


def jarvis(points: Sequence[QP]) -> list[QP]:
    """The strict CCW convex hull, by gift wrapping."""
    pts = sorted(set(points))
    start = pts[0]
    hull = [start]
    current = start
    while True:
        candidate = pts[0] if pts[0] != current else pts[1]
        for p in pts:
            if p == current:
                continue
            turn = orient(current, candidate, p)
            # p is to the right of current -> candidate, or further along the same line
            if turn < 0 or (turn == 0 and dist2(current, p) > dist2(current, candidate)):
                candidate = p
        if candidate == start:
            return hull
        hull.append(candidate)
        current = candidate


def within_hull(h: Core, hull: Sequence[QP], s: Q) -> bool:
    """Every point of h is closer than s to the closed convex CCW polygon `hull`."""
    body = region(hull)
    if h.grow == 0:
        return all(core_dist2(point(v), body) < s * s for v in h.pts)
    c, r = h.pts[0], h.grow
    if r < s:  # the disc fits in hull + B(s) iff its centre is in hull + B(s - r)
        return core_dist2(point(c), body) < (s - r) ** 2
    need = (r - s) ** 2  # else its centre is in the open erosion of hull by r - s
    return all(
        orient(a, b, c) > 0 and orient(a, b, c) ** 2 > need * dist2(a, b) for a, b in closed(hull)
    )


class Truth:
    """R1 to R7 of Errata 17.4 on one plan, by the cores above."""

    def __init__(self, plan: Plan) -> None:
        faces = [f for f in plan.faces if f.role == "concrete"]
        assert len(faces) == 1, "the fuzz only builds plans with one concrete face"
        face = faces[0]
        index = plan.faces.index(face)
        self.circle = face.boundary if isinstance(face.boundary, PlanCircle) else None
        self.ring = None if self.circle else [qp(p) for p in face.boundary.points_mm]  # type: ignore[union-attr]
        self.own = [shape(v) for v in face.holes]
        self.covers = [Q(g.cover_mm) for g in plan.cover_guides if g.face == index]
        bars = [qp(b.xy) for b in plan.bars]
        self.bars = [point(bars[i], Q(b.diameter_mm) / 2) for i, b in enumerate(plan.bars)]
        self.ties = [
            segment(bars[x.bar_a], bars[x.bar_b], Q(x.diameter_mm) / 2) for x in plan.crossties
        ]
        self.hoops = [
            (
                jarvis([bars[i] for i in h.bars]),
                min(Q(plan.bars[i].diameter_mm) / 2 for i in h.bars),
                max(Q(plan.bars[i].diameter_mm) / 2 for i in h.bars),
                Q(h.diameter_mm),
            )
            for h in plan.hoops
        ]
        self.spirals = [
            (qp(t.center_mm), Q(t.centerline_radius_mm), Q(t.diameter_mm))
            for t in plan.circular_ties
        ]

    def passes(self, rule: int, holes: Sequence[Core], k: int) -> bool:
        h = holes[k]
        if rule == 1:
            if self.circle is not None:
                return all_closer(h, qp(self.circle.center_mm), Q(self.circle.radius_mm))
            assert self.ring is not None
            return apart(h, outline(self.ring), ZERO) and strictly_inside(h.pts[0], self.ring)
        if rule == 2:
            return all(apart(h, v, ZERO) for v in self.own) and all(
                apart(h, holes[j], ZERO) for j in range(k)
            )
        if rule == 3:
            for c in self.covers:
                if self.circle is not None:
                    edge = all_closer(h, qp(self.circle.center_mm), Q(self.circle.radius_mm) - c)
                else:
                    assert self.ring is not None
                    edge = apart(h, outline(self.ring), c)
                if not (edge and all(apart(h, v, c) for v in self.own)):
                    return False
            return True
        if rule == 4:
            return all(apart(h, b, ZERO) for b in self.bars)
        if rule == 5:
            return all(apart(h, t, ZERO) for t in self.ties)
        if rule == 6:
            return all(
                within_hull(h, hull, r_min) or apart(h, region(hull), r_max + t)
                for hull, r_min, r_max, t in self.hoops
            )
        assert rule == 7
        return all(
            all_closer(h, c, rho - t / 2) or apart(h, point(c), rho + t / 2)
            for c, rho, t in self.spirals
        )

    def verdict(self, holes: Sequence[PlanBoundary]) -> tuple[int, int] | None:
        """(k, rule) of the first clash, or None: holes in index order, rules 1 to 7."""
        cores = [shape(h) for h in holes]
        for k in range(len(cores)):
            for rule in range(1, 8):
                if not self.passes(rule, cores, k):
                    return (k, rule)
        return None


# --- a ring's simplicity and area (16.1), for the exact ring predicates of the hole step ------


def fault(ring: Sequence[tuple[float, float]]) -> str | None:
    """The first reason `ring` is not simple, in the order `exact_simplicity_fault` names it;
    None when it is simple.

    Too few vertices; else the first vertex that repeats an earlier one; else, edge by edge,
    edge i and its next neighbour sharing more than their common vertex (one's far end lies
    on the other), then edge i meeting a later edge that is not its neighbour.
    """
    n = len(ring)
    if n < 3:
        return f"a ring needs at least 3 vertices, got {n}"
    pts = [qp(p) for p in ring]
    for i in range(n):
        if pts[i] in pts[:i]:
            return f"vertices {pts.index(pts[i])} and {i} repeat the point {ring[i]}"
    edges = closed(pts)
    for i in range(n):
        (a, b), (_, c) = edges[i], edges[(i + 1) % n]
        if foot_dist2(c, a, b) == 0 or foot_dist2(a, b, c) == 0:
            return f"edges {i} and {(i + 1) % n} overlap"
        for j in range(i + 2, n - 1 if i == 0 else n):
            if segments_meet(*edges[i], *edges[j]):
                return f"edges {i} and {j} cross or touch"
    return None


def simple(ring: Sequence[tuple[float, float]]) -> bool:
    return fault(ring) is None


def twice_area(ring: Sequence[tuple[float, float]]) -> Q:
    """Twice the signed area, by the trapezoid sum: > 0 when counter-clockwise."""
    pts = [qp(p) for p in ring]
    return sum(((a[0] - b[0]) * (a[1] + b[1]) for a, b in closed(pts)), ZERO)
