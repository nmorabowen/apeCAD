"""The exact truth for ADR 0042's two float predicates: ring nesting (6) and bar size (7).

It imports nothing from apeCAD, so it shares no code with the product's predicates
(`section/templates/hole_rules.py`, `section/dxf_seed.py`). It works in `fractions.Fraction`
on the stored floats, with squared distances: no square root, trigonometry, tolerance or
float comparison. It is also built differently from `hole_rules`: boundaries meet by segment
intersection and squared segment distances, and a point's side is a winding number, where
`hole_rules` uses clearances and a crossing parity.

A region is `("ring", ((x, y), ...))`, a simple ring in either orientation, or
`("circle", ((cx, cy), r))`, the closed disc.
"""

from __future__ import annotations

from collections.abc import Sequence
from fractions import Fraction

Q = Fraction
QPoint = tuple[Fraction, Fraction]
Region = tuple[str, object]


def _qp(p: Sequence[float]) -> QPoint:
    return (Q(p[0]), Q(p[1]))


def _orient(a: QPoint, b: QPoint, c: QPoint) -> Fraction:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _between(p: QPoint, a: QPoint, b: QPoint) -> bool:
    """p, collinear with a and b, lies on the closed segment ab."""
    return (p[0] - a[0]) * (p[0] - b[0]) <= 0 and (p[1] - a[1]) * (p[1] - b[1]) <= 0


def segments_meet(a: QPoint, b: QPoint, c: QPoint, d: QPoint) -> bool:
    o1, o2, o3, o4 = _orient(a, b, c), _orient(a, b, d), _orient(c, d, a), _orient(c, d, b)
    if o1 * o2 < 0 and o3 * o4 < 0:
        return True
    return (
        (o1 == 0 and _between(c, a, b))
        or (o2 == 0 and _between(d, a, b))
        or (o3 == 0 and _between(a, c, d))
        or (o4 == 0 and _between(b, c, d))
    )


def _d2(p: QPoint, q: QPoint) -> Fraction:
    return (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2


def _seg_d2(p: QPoint, a: QPoint, b: QPoint) -> Fraction:
    """Squared distance from p to the closed segment ab, by the projection parameter."""
    ab = (b[0] - a[0], b[1] - a[1])
    length2 = ab[0] ** 2 + ab[1] ** 2
    if length2 == 0:
        return _d2(p, a)
    t = ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / length2
    t = min(max(t, Q(0)), Q(1))
    return _d2(p, (a[0] + t * ab[0], a[1] + t * ab[1]))


def _edges(ring: Sequence[QPoint]) -> list[tuple[QPoint, QPoint]]:
    return [(ring[i], ring[(i + 1) % len(ring)]) for i in range(len(ring))]


def winding(p: QPoint, ring: Sequence[QPoint]) -> int:
    """The winding number of `ring` about p (p not on the ring)."""
    w = 0
    for a, b in _edges(ring):
        if a[1] <= p[1] < b[1] and _orient(a, b, p) > 0:
            w += 1
        elif b[1] <= p[1] < a[1] and _orient(a, b, p) < 0:
            w -= 1
    return w


def _parts(r: Region) -> tuple[list[QPoint] | None, tuple[QPoint, Fraction] | None]:
    kind, data = r
    if kind == "ring":
        return [_qp(p) for p in data], None
    centre, radius = data
    return None, (_qp(centre), Q(radius))


def boundaries_meet(a: Region, b: Region) -> bool:
    ra, ca = _parts(a)
    rb, cb = _parts(b)
    if ra is not None and rb is not None:
        return any(segments_meet(p, q, s, t) for p, q in _edges(ra) for s, t in _edges(rb))
    if ra is None and rb is None:
        (c1, r1), (c2, r2) = ca, cb
        d2 = _d2(c1, c2)
        return (r1 - r2) ** 2 <= d2 <= (r1 + r2) ** 2
    ring, (c, r) = (ra, cb) if ra is not None else (rb, ca)
    # A segment meets the circle iff its nearest point is within r and its far end beyond.
    return any(_seg_d2(c, p, q) <= r * r <= max(_d2(c, p), _d2(c, q)) for p, q in _edges(ring))


def _boundary_point(r: Region) -> QPoint:
    ring, circle = _parts(r)
    if ring is not None:
        return ring[0]
    (cx, cy), radius = circle
    return (cx + radius, cy)


def _strictly_inside(p: QPoint, r: Region) -> bool:
    """p, not on r's boundary, lies in r's interior."""
    ring, circle = _parts(r)
    if ring is not None:
        return winding(p, ring) != 0
    c, radius = circle
    return _d2(p, c) < radius * radius


def relation(a: Region, b: Region) -> str:
    """ "contact" when the boundaries meet; else "inside" (a in b's interior), "contains", or
    "disjoint" (the closed regions are apart). Jordan: with boundaries apart, one boundary
    point of a decides whether a lies in b."""
    if boundaries_meet(a, b):
        return "contact"
    if _strictly_inside(_boundary_point(a), b):
        return "inside"
    if _strictly_inside(_boundary_point(b), a):
        return "contains"
    return "disjoint"


def twice_area(ring: Sequence[Sequence[float]]) -> Fraction:
    pts = [_qp(p) for p in ring]
    return sum((_orient((Q(0), Q(0)), p, q) for p, q in _edges(pts)), Q(0))


def bar_size(diameter_mm: float, sizes: Sequence[float], tolerance: Fraction) -> float | None:
    """The size D with |d - D| <= tolerance, exactly on the float d; None when none is."""
    d = Q(diameter_mm)
    found = [size for size in sizes if abs(d - Q(size)) <= tolerance]
    assert len(found) <= 1, f"{diameter_mm!r} matches {found}"
    return found[0] if found else None
