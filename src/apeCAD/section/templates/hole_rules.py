"""The seven rules a template hole must pass, decided exactly (ADR 0040 Errata 17).

A version 2 template takes user holes (Errata 13). After the v1 function has drawn the
`Plan` and the holes are placed in floats, each hole must clear what the plan draws. The rules,
checked hole by hole in index order and, per hole, in the order R1 to R7 (17.2):

    R1 face          the hole lies in the interior of the outline of the plan's one concrete face
    R2 holes         it does not meet the face's own holes, nor an earlier user hole
    R3 cover         it stays more than `cover_mm` from the outline and from the face's own holes
    R4 bars          it stays more than d_b / 2 from each bar centre
    R5 crossties     it stays more than t / 2 from the segment between a crosstie's bar centres
    R6 hoops         every point lies closer than r_min to the hoop's bar-centre hull (inside
                     the cage), or the hole lies more than r_max + t from that hull (outside it)
    R7 circular ties every point lies closer than rho - t / 2 to the tie's centre, or the hole
                     lies more than rho + t / 2 from that centre

Every rule is a strict inequality, so contact is a clash (owner ruling, comment 4844). Every
comparison is decided in `fractions.Fraction` on the stored floats (17.5): an orientation, or a
squared distance against a squared sum of radii and clearances. No square root, trigonometry,
tolerance or float filter is used, so the verdict is the exact one on the stored floats. A
float filter could only be added under a stated error bound (17.5); none is used here.

The same exact arithmetic gives a placed ring's orientation, area and simplicity
(`exact_twice_area`, `exact_simplicity_fault`), which the hole step (Errata 13.2 step 6, 16.1)
decides exactly instead of with the float `section/geometry.py::signed_area` and `is_simple`.

The hole step itself (`holes.py`), the refusals of 16 and the registration of version 2 come in
C9-2b (Errata 21). This module registers nothing. It relies on these, by `path::symbol`:

- `section/templates/plan.py::Plan`, `PlanFace`, `PlanRing`, `PlanCircle`, `PlanHoop`,
  `PlanCrosstie`, `PlanCircularTie`, `PlanCoverGuide` and `TemplateParamError`;
- `section/templates/plan.py::hull_of`, through which `PlanHoop.bars` is a strict CCW hull;
- `geometry.py::require_finite`, which refuses a non-finite coordinate by name.

Paths are under `src/apeCAD/`.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from fractions import Fraction

from apeCAD.errors import DocumentError
from apeCAD.geometry import require_finite
from apeCAD.section.geometry import Point2
from apeCAD.section.templates.plan import (
    Plan,
    PlanBoundary,
    PlanCircle,
    TemplateParamError,
)

QPoint = tuple[Fraction, Fraction]
"""A point as exact rationals: the stored floats, unrounded."""


def _q(value: float) -> Fraction:
    """The exact value of a stored float. Every number the rules compare passes through here."""
    return Fraction(value)


def _qp(point: Point2, what: str) -> QPoint:
    x, y = point
    return (_q(require_finite(f"{what} x_mm", x)), _q(require_finite(f"{what} y_mm", y)))


# --- exact primitives -------------------------------------------------------------------


def _cross(o: QPoint, a: QPoint, b: QPoint) -> Fraction:
    """z of (a - o) x (b - o): > 0 when o, a, b turn counter-clockwise."""
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _d2(p: QPoint, q: QPoint) -> Fraction:
    dx, dy = p[0] - q[0], p[1] - q[1]
    return dx * dx + dy * dy


def _seg_d2(p: QPoint, a: QPoint, b: QPoint) -> Fraction:
    """The squared distance from p to the closed segment ab."""
    ex, ey = b[0] - a[0], b[1] - a[1]
    wx, wy = p[0] - a[0], p[1] - a[1]
    along = wx * ex + wy * ey
    if along <= 0:
        return wx * wx + wy * wy
    ee = ex * ex + ey * ey
    if along >= ee:
        return _d2(p, b)
    across = wx * ey - wy * ex
    return across * across / ee


def _within_box(p: QPoint, a: QPoint, b: QPoint) -> bool:
    return min(a[0], b[0]) <= p[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= p[1] <= max(a[1], b[1])


def _touch(a: QPoint, b: QPoint, c: QPoint, d: QPoint) -> bool:
    """The closed segments ab and cd share at least one point."""
    d1, d2 = _cross(c, d, a), _cross(c, d, b)
    d3, d4 = _cross(a, b, c), _cross(a, b, d)
    if ((d1 > 0 > d2) or (d1 < 0 < d2)) and ((d3 > 0 > d4) or (d3 < 0 < d4)):
        return True
    return (
        (d1 == 0 and _within_box(a, c, d))
        or (d2 == 0 and _within_box(b, c, d))
        or (d3 == 0 and _within_box(c, a, b))
        or (d4 == 0 and _within_box(d, a, b))
    )


Edge = tuple[QPoint, QPoint]
Box = tuple[Fraction, Fraction, Fraction, Fraction]
"""(x_min, y_min, x_max, y_max), exact."""
FBox = tuple[float, float, float, float]
"""(x_min, y_min, x_max, y_max) in floats, for the screens below."""


# --- the screens: exact, and in floats --------------------------------------------------
#
# A screen skips a pair only when the pair is already known to be more than `gap` apart along
# x or along y, so it never changes a verdict. It compares floats, and stays exact because
# (a) a box of stored floats is compared as those floats, which a float comparison decides
# exactly; and (b) a box grown by a gap is computed in `Fraction` and rounded outward to
# floats (`_down`, `_up`), so the float box contains the exact one: whatever lies outside it
# lies outside the exact one. That is the proven bound Errata 17.5 asks of a float filter.


def _down(value: Fraction) -> float:
    """The greatest float at or below `value`."""
    f = float(value)
    return f if f <= value else math.nextafter(f, -math.inf)


def _up(value: Fraction) -> float:
    """The least float at or above `value`."""
    f = float(value)
    return f if f >= value else math.nextafter(f, math.inf)


def _grown(box: Box, gap: Fraction) -> FBox:
    """`box` grown by `gap` on every side, rounded outward to floats."""
    return (_down(box[0] - gap), _down(box[1] - gap), _up(box[2] + gap), _up(box[3] + gap))


def _overlap(a: FBox, b: FBox) -> bool:
    """The closed boxes meet. False proves them apart."""
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def _fbox(points: Sequence[QPoint]) -> FBox:
    """The box of points that are stored floats, as those floats (exact)."""
    xs, ys = [float(p[0]) for p in points], [float(p[1]) for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _point_box(p: QPoint) -> Box:
    return (p[0], p[1], p[0], p[1])


# --- regions ----------------------------------------------------------------------------


def _edges(points: Sequence[QPoint]) -> tuple[Edge, ...]:
    n = len(points)
    return tuple((points[i], points[(i + 1) % n]) for i in range(n))


@dataclass(frozen=True, slots=True)
class _Disc:
    """A closed disc."""

    c: QPoint
    r: Fraction

    @property
    def box(self) -> Box:
        (x, y), r = self.c, self.r
        return (x - r, y - r, x + r, y + r)


@dataclass(frozen=True, slots=True)
class _Poly:
    """The closed region of a simple ring, in either orientation, with float boxes."""

    pts: tuple[QPoint, ...]
    edges: tuple[Edge, ...]
    box: Box
    fbox: FBox
    edge_fboxes: tuple[FBox, ...]


def _poly(points: Sequence[QPoint]) -> _Poly:
    edges = _edges(points)
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return _Poly(
        tuple(points),
        edges,
        (min(xs), min(ys), max(xs), max(ys)),
        _fbox(points),
        tuple(_fbox(e) for e in edges),
    )


_Region = _Disc | _Poly


def _region(boundary: PlanBoundary, what: str) -> _Region:
    if isinstance(boundary, PlanCircle):
        return _Disc(_qp(boundary.center_mm, f"{what} centre"), _q(boundary.radius_mm))
    pts = tuple(_qp(p, f"{what} vertex {i}") for i, p in enumerate(boundary.points_mm))
    if len(pts) < 3:
        raise DocumentError(f"{what}: a ring needs at least 3 vertices, got {len(pts)}")
    return _poly(pts)


def _near(poly: _Poly, box: Box, gap: Fraction) -> list[int]:
    """Indices of the edges of `poly` that the screen cannot prove more than `gap` from `box`."""
    reach = _grown(box, gap)
    return [i for i, b in enumerate(poly.edge_fboxes) if _overlap(b, reach)]


def _locate(p: QPoint, poly: _Poly) -> int:
    """1 when p is inside the ring's region, 0 on its boundary, -1 outside (exact crossings).

    A ray goes from p towards +x; the parity of the edges it crosses, half-open in y, tells
    inside from outside. Coordinates are compared as their stored floats (exact); only an
    edge that spans p in x needs an orientation.
    """
    px, py = float(p[0]), float(p[1])
    inside = False
    for (a, b), (x0, y0, x1, y1) in zip(poly.edges, poly.edge_fboxes, strict=True):
        if (float(a[1]) > py) != (float(b[1]) > py):  # the edge straddles the ray's line
            if x0 > px:
                inside = not inside  # wholly to the right of p: crossed, and p is not on it
                continue
            if x1 < px:
                continue  # wholly to the left
            side = _cross(a, b, p)
            if side == 0:
                return 0  # on the line, and within the edge's span in y: on the edge
            # It crosses to the right of p when p lies to the left of the upward edge.
            if (side > 0) == (b[1] > a[1]):
                inside = not inside
        elif x0 <= px <= x1 and y0 <= py <= y1 and _cross(a, b, p) == 0:
            return 0
    return 1 if inside else -1


def _poly_d2(p: QPoint, poly: _Poly) -> Fraction:
    """The squared distance from p to the closed region of `poly` (0 inside or on it)."""
    if _locate(p, poly) >= 0:
        return Fraction(0)
    return min(_seg_d2(p, a, b) for a, b in poly.edges)


def _touches(h: _Poly, o: _Poly, edges: Sequence[int]) -> bool:
    """Some edge of h meets one of the edges `edges` of o (screened by their float boxes)."""
    return any(
        _overlap(hb, o.edge_fboxes[j]) and _touch(a, b, *o.edges[j])
        for (a, b), hb in zip(h.edges, h.edge_fboxes, strict=True)
        for j in edges
    )


def _all_far(points: Sequence[QPoint], poly: _Poly, edges: Sequence[int], gap: Fraction) -> bool:
    """Every point is more than `gap` from each of the edges `edges` of `poly`."""
    g2 = gap * gap
    for v in points:
        reach = _grown(_point_box(v), gap)
        for j in edges:
            if _overlap(reach, poly.edge_fboxes[j]) and not _seg_d2(v, *poly.edges[j]) > g2:
                return False
    return True


def _ends(poly: _Poly, edges: Sequence[int]) -> list[QPoint]:
    """The vertices on the edges `edges` of `poly`."""
    n = len(poly.pts)
    return [poly.pts[k] for k in sorted({k for j in edges for k in (j, (j + 1) % n)})]


# --- clearances: each says whether a distance is strictly greater than a gap -----------------


def _clear_point(h: _Region, p: QPoint, gap: Fraction) -> bool:
    """d(h, p) > gap, for gap >= 0."""
    if isinstance(h, _Disc):
        reach = h.r + gap
        return _d2(h.c, p) > reach * reach
    reach = _grown(_point_box(p), gap)
    if not _overlap(reach, h.fbox):
        return True  # outside h's box by more than gap
    # No edge near p does not prove p clear: p may lie deep inside h.
    near = [j for j, b in enumerate(h.edge_fboxes) if _overlap(b, reach)]
    return _locate(p, h) < 0 and _all_far((p,), h, near, gap)


def _clear_segment(h: _Region, a: QPoint, b: QPoint, gap: Fraction) -> bool:
    """d(h, [a, b]) > gap, for gap >= 0."""
    if isinstance(h, _Disc):
        reach = h.r + gap
        return _seg_d2(h.c, a, b) > reach * reach
    seg = _poly((a, b))  # a two-point "ring": its edges are ab and ba
    if not _overlap(_grown(seg.box, gap), h.fbox):
        return True  # outside h's box by more than gap
    near = _near(h, seg.box, gap)  # may be empty with the segment deep inside h
    if _touches(seg, h, near) or _locate(a, h) >= 0:
        return False
    return _all_far(_ends(h, near), seg, (0,), gap) and _all_far((a, b), h, near, gap)


def _clear_region(h: _Region, s: _Region, gap: Fraction) -> bool:
    """d(h, s) > gap between two closed regions, for gap >= 0."""
    if isinstance(s, _Disc):
        return _clear_point(h, s.c, s.r + gap)
    if isinstance(h, _Disc):
        return _clear_point(s, h.c, h.r + gap)
    if not _overlap(_grown(h.box, gap), s.fbox):
        return True  # the boxes are more than gap apart
    near = _near(s, h.box, gap)  # only these edges of s can come within `gap` of h
    if _touches(h, s, near):
        return False
    # No boundaries meet, so the regions are disjoint unless one holds the other.
    if _locate(h.pts[0], s) >= 0 or _locate(s.pts[0], h) >= 0:
        return False
    every = range(len(h.edges))
    return _all_far(h.pts, s, near, gap) and _all_far(_ends(s, near), h, every, gap)


def _interior(h: _Region, o: _Region) -> bool:
    """h lies in the interior of o: h is inside o and d(h, boundary of o) > 0."""
    if isinstance(o, _Disc):
        return _within_point(h, o.c, o.r)
    near = _near(o, h.box, Fraction(0))  # only these edges of o can meet h
    if isinstance(h, _Disc):
        return _locate(h.c, o) > 0 and _all_far((h.c,), o, near, h.r)
    # Boundaries apart and one vertex inside: o is a simple ring, so all of h is inside.
    return not _touches(h, o, near) and _locate(h.pts[0], o) > 0


def _clear_outline(h: _Region, o: _Region, gap: Fraction) -> bool:
    """d(h, boundary of o) > gap, for an h already in the interior of o (R1 holds)."""
    if isinstance(o, _Disc):
        return _within_point(h, o.c, o.r - gap)
    near = _near(o, h.box, gap)  # an edge the screen proves further than `gap` is clear
    if isinstance(h, _Disc):
        return _all_far((h.c,), o, near, h.r + gap)
    every = range(len(h.edges))
    return _all_far(h.pts, o, near, gap) and _all_far(_ends(o, near), h, every, gap)


def _within_point(h: _Region, centre: QPoint, s: Fraction) -> bool:
    """Every point of h lies closer than s to `centre`."""
    if isinstance(h, _Disc):
        room = s - h.r
        return room > 0 and _d2(h.c, centre) < room * room
    return s > 0 and all(_d2(v, centre) < s * s for v in h.pts)


def _within_convex(h: _Region, hull: _Poly, s: Fraction) -> bool:
    """Every point of h lies closer than s > 0 to the closed convex CCW polygon `hull`.

    The distance to a convex set is convex, so over a ring region its greatest value is at a
    vertex. Over a disc of centre c and radius r it is max(0, r + sd(c)), where sd is the
    signed distance to the hull: d(c, hull) outside it, minus the least distance to an edge
    line inside it (the support-function form of the Minkowski sum).
    """
    if isinstance(h, _Poly):
        return all(_poly_d2(v, hull) < s * s for v in h.pts)
    if _locate(h.c, hull) > 0:
        depth = h.r - s  # needed: the least edge-line distance exceeds this
        if depth < 0:
            return True
        need = depth * depth
        return all(
            _cross(a, b, h.c) ** 2 > need * ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2)
            for a, b in hull.edges
        )
    room = s - h.r
    return room > 0 and _poly_d2(h.c, hull) < room * room


# --- the rules ----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Hoop:
    hull: _Poly
    r_min: Fraction
    r_max: Fraction
    t: Fraction


@dataclass(frozen=True, slots=True)
class _Exact:
    """The plan, read once into exact values."""

    outline: _Region
    own: tuple[_Region, ...]
    covers: tuple[Fraction, ...]
    bars: tuple[tuple[QPoint, Fraction], ...]
    crossties: tuple[tuple[QPoint, QPoint, Fraction], ...]
    hoops: tuple[_Hoop, ...]
    ties: tuple[tuple[QPoint, Fraction, Fraction], ...]


def _hull(points: Sequence[QPoint]) -> _Poly:
    """The strict CCW convex hull of `points`, by exact orientations (monotone chain).

    R6's P is the convex polygon on the hoop's bar centres. It is rebuilt here exactly rather
    than taken from the float order of `PlanHoop.bars`, so the rule's convexity holds on the
    stored floats whatever the offset.
    """
    ordered = sorted(set(points))
    if len(ordered) < 3:
        return _poly(ordered)
    chain: list[QPoint] = []
    for sweep in (ordered, ordered[::-1]):
        part: list[QPoint] = []
        for p in sweep:
            while len(part) >= 2 and _cross(part[-2], part[-1], p) <= 0:
                part.pop()
            part.append(p)
        chain.extend(part[:-1])
    return _poly(chain)


def _read_plan(plan: Plan) -> _Exact:
    concrete = [k for k, face in enumerate(plan.faces) if face.role == "concrete"]
    if len(concrete) != 1:
        raise DocumentError(
            f"the hole rules need a plan with one concrete face; this one has {len(concrete)}"
        )
    k = concrete[0]
    face = plan.faces[k]
    bars = tuple(
        (_qp(bar.xy, f"plan bar {i}"), _q(bar.diameter_mm) / 2) for i, bar in enumerate(plan.bars)
    )
    hoops: list[_Hoop] = []
    for i, hoop in enumerate(plan.hoops):
        hull = _hull([bars[j][0] for j in hoop.bars])
        if len(hull.pts) < 3:
            raise DocumentError(f"plan hoop {i}: its bar centres span no area")
        radii = [bars[j][1] for j in hoop.bars]
        hoops.append(_Hoop(hull, min(radii), max(radii), _q(hoop.diameter_mm)))
    return _Exact(
        outline=_region(face.boundary, f"plan face {k} boundary"),
        own=tuple(_region(v, f"plan face {k} hole {j}") for j, v in enumerate(face.holes)),
        covers=tuple(_q(g.cover_mm) for g in plan.cover_guides if g.face == k),
        bars=bars,
        crossties=tuple(
            (bars[x.bar_a][0], bars[x.bar_b][0], _q(x.diameter_mm) / 2) for x in plan.crossties
        ),
        hoops=tuple(hoops),
        ties=tuple(
            (
                _qp(t.center_mm, f"plan circular tie {i} centre"),
                _q(t.centerline_radius_mm),
                _q(t.diameter_mm),
            )
            for i, t in enumerate(plan.circular_ties)
        ),
    )


Rule = Callable[[_Exact, Sequence[_Region], int], str | None]
"""A rule: the plan, every hole, the hole to check; what it meets, or None when it clears."""

_ZERO = Fraction(0)


def _r1_face(s: _Exact, holes: Sequence[_Region], k: int) -> str | None:
    if not _interior(holes[k], s.outline):
        return "it is not inside the face's outline: it meets or crosses it"
    return None


def _r2_holes(s: _Exact, holes: Sequence[_Region], k: int) -> str | None:
    for j, own in enumerate(s.own):
        if not _clear_region(holes[k], own, _ZERO):
            return f"it meets the face's own hole {j}"
    for j in range(k):
        if not _clear_region(holes[k], holes[j], _ZERO):
            return f"it meets holes[{j}]"
    return None


def _r3_cover(s: _Exact, holes: Sequence[_Region], k: int) -> str | None:
    for cover in s.covers:
        if not _clear_outline(holes[k], s.outline, cover):
            return f"it is not more than the {float(cover):g} mm cover from the face's outline"
        for j, own in enumerate(s.own):
            if not _clear_region(holes[k], own, cover):
                return (
                    f"it is not more than the {float(cover):g} mm cover from the face's own "
                    f"hole {j}"
                )
    return None


def _r4_bars(s: _Exact, holes: Sequence[_Region], k: int) -> str | None:
    for i, (p, radius) in enumerate(s.bars):
        if not _clear_point(holes[k], p, radius):
            return f"it meets bar {i} at ({float(p[0]):g}, {float(p[1]):g})"
    return None


def _r5_crossties(s: _Exact, holes: Sequence[_Region], k: int) -> str | None:
    for i, (a, b, half) in enumerate(s.crossties):
        if not _clear_segment(holes[k], a, b, half):
            return f"it meets crosstie {i}"
    return None


def _r6_hoops(s: _Exact, holes: Sequence[_Region], k: int) -> str | None:
    for i, hoop in enumerate(s.hoops):
        inside = _within_convex(holes[k], hoop.hull, hoop.r_min)
        if not inside and not _clear_region(holes[k], hoop.hull, hoop.r_max + hoop.t):
            return (
                f"it meets hoop {i}: it is neither within {float(hoop.r_min):g} mm of the hoop's "
                f"bar-centre hull nor more than {float(hoop.r_max + hoop.t):g} mm outside it"
            )
    return None


def _r7_circular_ties(s: _Exact, holes: Sequence[_Region], k: int) -> str | None:
    for i, (centre, rho, t) in enumerate(s.ties):
        inner, outer = rho - t / 2, rho + t / 2
        if not _within_point(holes[k], centre, inner) and not _clear_point(holes[k], centre, outer):
            return (
                f"it meets circular tie {i}: it is neither closer than {float(inner):g} mm to "
                f"its centre nor more than {float(outer):g} mm from it"
            )
    return None


_RULES: tuple[tuple[int, Rule], ...] = (
    (1, _r1_face),
    (2, _r2_holes),
    (3, _r3_cover),
    (4, _r4_bars),
    (5, _r5_crossties),
    (6, _r6_hoops),
    (7, _r7_circular_ties),
)
"""The rules in the order they are checked (17.2)."""


@dataclass(frozen=True, slots=True)
class HoleClash:
    """The first rule a hole fails: `holes[index]` fails rule R`rule` and meets `what`."""

    index: int
    rule: int
    what: str

    @property
    def param(self) -> str:
        return f"holes[{self.index}]"

    @property
    def message(self) -> str:
        return f"R{self.rule}: {self.what}"


def first_clash(plan: Plan, holes: Sequence[PlanBoundary]) -> HoleClash | None:
    """The first clash of `holes`, placed in section coordinates, with `plan`; None if none.

    Holes are checked in index order and, per hole, rules R1 to R7 in order (17.2). A ring
    hole must already be simple with a non-zero area (the step checks that first, 16.1); its
    orientation does not matter here.
    """
    steel = _read_plan(plan)
    regions = [_region(h, f"holes[{k}]") for k, h in enumerate(holes)]
    for k in range(len(regions)):
        for rule, check in _RULES:
            what = check(steel, regions, k)
            if what is not None:
                return HoleClash(k, rule, what)
    return None


def require_holes_clear(template: str, plan: Plan, holes: Sequence[PlanBoundary]) -> None:
    """Refuse, as a `TemplateParamError` naming `holes[k]`, the first hole that clashes."""
    clash = first_clash(plan, holes)
    if clash is not None:
        raise TemplateParamError(template, clash.param, clash.message)


# --- exact ring predicates for the hole step (16.1) ----------------------------------------


def exact_twice_area(ring: Sequence[Point2]) -> Fraction:
    """Twice the shoelace area of `ring` on its stored floats, exactly: < 0 when clockwise."""
    pts = [_qp(p, f"ring vertex {i}") for i, p in enumerate(ring)]
    n = len(pts)
    return sum(
        (pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n)),
        Fraction(0),
    )


def exact_simplicity_fault(ring: Sequence[Point2]) -> str | None:
    """Why `ring` is not simple, decided exactly; None when it is.

    The same rule as `section/geometry.py::is_simple` (at least 3 vertices, none repeated, no
    two edges meeting except neighbours at their shared vertex), with every orientation in
    `Fraction` instead of floats.
    """
    n = len(ring)
    if n < 3:
        return f"a ring needs at least 3 vertices, got {n}"
    pts = [_qp(p, f"ring vertex {i}") for i, p in enumerate(ring)]
    seen: dict[QPoint, int] = {}
    for i, p in enumerate(pts):
        if p in seen:
            return f"vertices {seen[p]} and {i} repeat the point {ring[i]}"
        seen[p] = i
    for i in range(n):
        a, b, c = pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        if (
            _cross(a, b, c) == 0
            and (a[0] - b[0]) * (c[0] - b[0]) + (a[1] - b[1]) * (c[1] - b[1]) > 0
        ):
            return f"edges {i} and {(i + 1) % n} overlap"
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue  # the closing edge is adjacent to edge 0, handled above
            if _touch(a, b, pts[j], pts[(j + 1) % n]):
                return f"edges {i} and {j} cross or touch"
    return None


def exact_is_simple(ring: Sequence[Point2]) -> bool:
    """`ring` is simple, decided exactly on its stored floats."""
    return exact_simplicity_fault(ring) is None


__all__ = [
    "HoleClash",
    "exact_is_simple",
    "exact_simplicity_fault",
    "exact_twice_area",
    "first_clash",
    "require_holes_clear",
]
