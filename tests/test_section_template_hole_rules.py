"""The exact hole rules R1 to R7 (ADR 0040 Errata 17), against the oracle of Errata 18.1 to 18.3.

C9-2a (apeSection#204). `section/templates/hole_rules.py` decides each rule exactly, in
`fractions.Fraction`, on the stored floats. The truth is `tests/_hole_rules_truth.py`, an
exact reference built differently that imports none of the product's predicate code (18.1).

- 18.2, the two-sided fuzz: one seeded generator. Per rule and per feature of the plan (the
  outline, its own holes, bars, crossties, hoops, circular ties and earlier holes) it places
  circle and ring holes wholly inside, wholly outside, straddling and touching, at contact,
  at the floats either side of it, and at gaps of +-1e-12 to +-1 mm; holes larger than their
  container, discs below and above r_min, one to four holes, collinear and on-vertex
  placements, every ring in a random start vertex and orientation. It runs on all eight
  templates, with parts stripped, at `center_mm` offsets 0, 0.1, 1234.5 and 40000.3, some
  holes snapped to grids of 0.01 to 5 mm by `i/10`, `i*0.1` and `round(k*g, 6)`. Every
  verdict must equal the truth, and each rule must both refuse and accept. With one rule
  dropped, or with plain floats in place of `Fraction`, the fuzz must fail.
- The break-once table, `tests/test_section_template_hole_mutants.py`, pins each mutant of
  the review rounds to a case that kills it.
- 18.3, the hand cases.

The rules are a function of the `Plan` alone, so a stripped plan (its cover guide, bars,
hoops or circular tie removed) is a fair plan: it lets every rule be reached on both sides.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace
from fractions import Fraction as Q
from functools import cache

import pytest

from _hole_rules_truth import Truth, fault, shape, simple, twice_area
from _section_fixtures_v2 import T_BEAM_PARAMS
from apeCAD.errors import DocumentError
from apeCAD.section.geometry import is_simple, signed_area
from apeCAD.section.templates import expand, hole_rules
from apeCAD.section.templates.hole_rules import (
    exact_is_simple,
    exact_simplicity_fault,
    exact_twice_area,
    first_clash,
    require_holes_clear,
)
from apeCAD.section.templates.plan import (
    Plan,
    PlanBar,
    PlanBoundary,
    PlanCircle,
    PlanCircularTie,
    PlanCoverGuide,
    PlanCrosstie,
    PlanFace,
    PlanRing,
    TemplateParamError,
)

SEED = 20261122
CASES = 8000  # sized so the generator kills the break-once table's `fuzz` rows
OFFSETS = (0.0, 0.1, 1234.5, 40000.3)
GRIDS = (Q(1, 100), Q(1, 10), Q(1), Q(5))
PATHS = ("div", "mul", "round")  # i / 10, i * 0.1, round(i * 0.1, 6)
EPS = (1e-12, 1e-9, 1e-6, 1e-3, 0.01, 0.1, 1.0)  # gaps from contact, taken either way
SIZES = (0.5, 2.5, 5.0, 8.25, 12.3, 12.5, 25.0)
NO_STEEL = ("bars", "hoops", "crossties", "circular_ties")
STRIPS: tuple[tuple[str, ...], ...] = (
    (), (), ("cover_guides",), NO_STEEL, ("cover_guides", *NO_STEEL), ("hoops",),
    ("cover_guides", "hoops"), ("crossties",), ("cover_guides", "bars", "hoops", "crossties"),
)  # fmt: skip

# --- templates, centred on (0, 0); a fuzz offset moves them to (off, -off) ----------------

BASES: dict[str, tuple[str, dict[str, object]]] = {
    "rc": ("rect_column", {
        "material": "C30", "b": 400, "h": 600, "cover": 40, "nx": 3, "ny": 3, "bar": "Ø20",
        "tie": "Ø10", "tie_spacing": 150, "crossties": "none"}),
    "rc_all": ("rect_column", {
        "material": "C30", "b": 400, "h": 600, "cover": 40, "nx": 3, "ny": 3, "bar": "Ø20",
        "tie": "Ø10", "tie_spacing": 150, "crossties": "all"}),
    # Ø8 bars under Ø10 crossties: a tie's end reaches past its bar, so R5 is met there.
    "rc_thin": ("rect_column", {
        "material": "C30", "b": 400, "h": 600, "cover": 40, "nx": 3, "ny": 3, "bar": "Ø8",
        "tie": "Ø10", "tie_spacing": 150, "crossties": "all"}),
    "pc": ("polygon_column", {
        "material": "C30", "ring": [[0, 0], [600, 0], [600, 300], [0, 500]], "cover": 40,
        "bar": "Ø20", "spacing_max": 150, "tie": "Ø10", "tie_spacing": 150}),
    "rh": ("rect_hollow", {
        "material": "C30", "b": 600, "h": 800, "t_x": 150, "t_y": 200, "cover": 40,
        "bar": "Ø16", "spacing_max": 200, "tie": "Ø10", "tie_spacing": 150}),
    "tb": ("t_beam", {**T_BEAM_PARAMS, "hf": 200, "center_mm": [0, 0]}),
    "cc": ("circular_column", {
        "material": "C30", "diameter": 600, "cover": 40, "n_bars": 6, "bar": "Ø20",
        "tie_kind": "spiral", "tie": "Ø10", "pitch": 75}),
    "cr": ("cft_round", {"material": "C50", "steel_material": "S355", "diameter": 400, "t": 10}),
    "ct": ("cft_rect", {
        "material": "C50", "steel_material": "S355", "b": 300, "h": 500, "t": 12}),
}  # fmt: skip


def disc_void(off: float) -> Plan:
    """A plan no template draws yet: a square face round a circular void, with a cover guide,
    so R2 and R3 meet a circular own hole."""
    square = ((-200.0, -200.0), (200.0, -200.0), (200.0, 200.0), (-200.0, 200.0))
    ring = PlanRing(tuple((off + x, -off + y) for x, y in square))
    face = PlanFace("concrete", "C30", ring, (PlanCircle((off + 30.0, -off - 20.0), 60.0),))
    return Plan(faces=(face,), cover_guides=(PlanCoverGuide(0, 40.0, 10.0, 20.0),))


HANDMADE = {"disc_void": disc_void}
ALL_BASES = (*BASES, *HANDMADE)


@cache
def plan_at(base: str, off: float, strip: tuple[str, ...] = ()) -> Plan:
    if base in HANDMADE:
        plan = HANDMADE[base](off)
    else:
        template, params = BASES[base]
        moved = dict(params)
        if template == "polygon_column":
            ring: list[list[int]] = params["ring"]  # type: ignore[assignment]
            moved["ring"] = [[x + off, y - off] for x, y in ring]
        else:
            moved["center_mm"] = [off, -off]
        plan = expand(template, moved, 1)
    return replace(plan, **{part: () for part in strip})


def placed(value: Q, grid: Q, path: str, base: float) -> float:
    """`value` snapped to `grid`, built along a rounding path, then added to `base` in floats."""
    i = round(value / grid)
    g = float(grid)
    if path == "div":
        local = i / round(1 / grid) if grid < 1 else float(i * grid)
    elif path == "mul":
        local = i * g
    else:
        local = round(i * g, 6)
    return base + local


# --- the generator: where a hole meets a limit, and how it is placed there ----------------

XY = tuple[float, float]


def unit(x: float, y: float) -> XY:
    n = math.hypot(x, y)
    return (x / n, y / n)


def _exact(v: float) -> float:
    if abs(v) < 1e-12:
        return 0.0
    return math.copysign(1.0, v) if abs(abs(v) - 1.0) < 1e-12 else v


def turn(angle: float) -> XY:
    """(cos, sin), exact at the quarter turns, so an aligned ring stays collinear with an axis."""
    return (_exact(math.cos(angle)), _exact(math.sin(angle)))


def ccw(ring: Sequence[XY]) -> list[XY]:
    """The ring in counter-clockwise order (floats: only for aiming holes, never a verdict)."""
    n = len(ring)
    area = sum(
        ring[i][0] * ring[(i + 1) % n][1] - ring[(i + 1) % n][0] * ring[i][1] for i in range(n)
    )
    return list(ring) if area > 0 else list(ring[::-1])


def float_hull(points: Sequence[XY]) -> list[XY]:
    """A CCW hull in floats: only for aiming holes, never for a verdict."""
    pts = sorted(set(points))
    chain: list[XY] = []
    for sweep in (pts, pts[::-1]):
        part: list[XY] = []
        for p in sweep:
            while len(part) >= 2 and (
                (part[-1][0] - part[-2][0]) * (p[1] - part[-2][1])
                - (part[-1][1] - part[-2][1]) * (p[0] - part[-2][0])
            ) <= 0:
                part.pop()
            part.append(p)
        chain.extend(part[:-1])
    return chain


def spot(ring: Sequence[XY], rng: random.Random, pokes: str, where: str) -> tuple[XY, XY]:
    """A point of a ring and an outward direction there.

    `where` is "edge" (inside an edge, along its normal), "corner" (a vertex, along a direction
    between its edges' normals) or "line" (a vertex, along one of its edges' lines, past it:
    the collinear placements). A vertex is drawn mostly from the corners that poke towards the
    hole (`pokes`, "convex" or "reflex"), where a hole's edge, not its vertex, comes nearest.
    """
    pts = ccw(ring)
    n = len(pts)
    normals = [
        unit(pts[(i + 1) % n][1] - pts[i][1], pts[i][0] - pts[(i + 1) % n][0]) for i in range(n)
    ]
    if where == "edge":
        i = rng.randrange(n)
        (ax, ay), (bx, by) = pts[i], pts[(i + 1) % n]
        t = rng.choice((0.5, rng.random()))
        return (ax + t * (bx - ax), ay + t * (by - ay)), normals[i]

    def turn_at(i: int) -> float:
        (ax, ay), (bx, by), (cx, cy) = pts[i - 1], pts[i], pts[(i + 1) % n]
        return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)

    wanted = [i for i in range(n) if (turn_at(i) > 0) == (pokes == "convex")]
    i = rng.choice(wanted) if wanted and rng.random() < 0.8 else rng.randrange(n)
    if where == "line":
        (ax, ay), (bx, by) = pts[i], pts[rng.choice((i - 1, (i + 1) % n))]
        sign = 1.0 if turn_at(i) > 0 else -1.0  # past a convex vertex is outward
        return pts[i], unit(sign * (ax - bx), sign * (ay - by))
    (px, py), (qx, qy) = normals[i - 1], normals[i]
    w = rng.choice((0.5, 0.5, 0.5, rng.random()))
    return pts[i], unit(px + w * (qx - px), py + w * (qy - py))


def centroid(h: PlanBoundary) -> XY:
    if isinstance(h, PlanCircle):
        return h.center_mm
    xs, ys = [x for x, _ in h.points_mm], [y for _, y in h.points_mm]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def room(h: PlanBoundary) -> float:
    """Half the smaller side of a boundary's box: a size of the container."""
    if isinstance(h, PlanCircle):
        return h.radius_mm
    xs, ys = [x for x, _ in h.points_mm], [y for _, y in h.points_mm]
    return min(max(xs) - min(xs), max(ys) - min(ys)) / 2


@dataclass(frozen=True)
class Anchor:
    """One limit of one rule: contact lies at `p + reach * u`. With `side` +1 the hole lies
    beyond it (its nearest point at the limit), with -1 short of it (its farthest point at the
    limit). An "around" anchor centres the hole on `p` instead. `sizes` are sizes worth trying
    here (a band's r_min, a container's size), besides `SIZES`."""

    p: XY
    u: XY
    reach: float
    side: int
    sizes: tuple[float, ...] = ()
    around: bool = False
    present: str = "any"  # what a ring hole turns to the limit: "edge", "vertex" or "any"


# Each family is one limit of one rule, on one feature of the plan: (rule, the plan parts it
# needs). "-around" families centre the hole on the feature, often larger than it. A ring
# feature (an outline, a void, a hoop's hull, an earlier hole) is met at an "@edge", at a
# "@corner" that pokes towards the hole, and along an edge's "@line" past a vertex.
_RINGED: dict[str, tuple[int, tuple[str, ...]]] = {
    "outline-in": (1, ()), "outline-out": (1, ()), "outline-cover": (3, ("cover_guides",)),
    "void-out": (2, ("holes",)), "void-in": (2, ("holes",)),
    "void-cover": (3, ("holes", "cover_guides")),
    "hoop-in": (6, ("hoops",)), "hoop-out": (6, ("hoops",)),
    "prior-out": (2, ()), "prior-in": (2, ()),
}  # fmt: skip
FAMILIES: dict[str, tuple[int, tuple[str, ...]]] = {
    **{f"{f}@{w}": v for f, v in _RINGED.items() for w in ("edge", "corner", "line")},
    "void-around": (2, ("holes",)), "prior-around": (2, ()),
    "bar": (4, ("bars",)), "bar-around": (4, ("bars",)),
    "crosstie": (5, ("crossties",)), "crosstie-end": (5, ("crossties",)),
    "tie-in": (7, ("circular_ties",)), "tie-out": (7, ("circular_ties",)),
    "tie-around": (7, ("circular_ties",)),
}  # fmt: skip


def has(plan: Plan, part: str) -> bool:
    if part == "holes":
        return any(f.holes for f in plan.faces if f.role == "concrete")
    return bool(getattr(plan, part))


def anchor(plan: Plan, family: str, rng: random.Random, priors: Sequence[PlanBoundary]) -> Anchor:
    k, face = next((k, f) for k, f in enumerate(plan.faces) if f.role == "concrete")
    covers = [g.cover_mm for g in plan.cover_guides if g.face == k]
    angle = rng.choice((0.0, math.pi / 2, math.pi, math.pi / 4, rng.uniform(0, 2 * math.pi)))
    family, _, where = family.partition("@")
    feature, _, limit = family.partition("-")
    present = {"edge": "any", "corner": "edge", "line": "vertex"}.get(where, "any")
    if feature in ("outline", "void", "prior"):
        pool = {"outline": (face.boundary,), "void": face.holes}.get(feature, priors)
        target = rng.choice(pool[-1:] if feature == "prior" and rng.random() < 0.6 else pool)
        # Larger than the container, for a hole in it or round it.
        big = (room(target) * 1.02, room(target) * 2.5) if limit in ("in", "around") else ()
        if limit == "around":
            return Anchor(centroid(target), turn(angle), 0.0, 1, big, around=True)
        concrete_side = limit in ("out", "cover") if feature != "outline" else limit != "out"
        if isinstance(target, PlanCircle):
            (cx, cy), r = target.center_mm, target.radius_mm
            out = turn(angle)
            p = (cx + r * out[0], cy + r * out[1])
        else:
            # The corners that poke towards the hole: reflex ones of the outline seen from the
            # concrete, convex ones of a void or a hole seen from outside it.
            pokes = "reflex" if concrete_side == (feature == "outline") else "convex"
            p, out = spot(target.points_mm, rng, pokes, where)
        inward = (-out[0], -out[1])
        u = out if (feature == "outline") != concrete_side else inward
        reach = rng.choice(covers) if limit == "cover" else 0.0
        sizes = big + ((reach / 2, reach, 2 * reach) if reach else ())
        return Anchor(p, u, reach, 1, sizes, present=present)
    if feature == "bar":
        b = rng.choice(plan.bars)
        r = b.diameter_mm / 2
        if limit == "around":
            return Anchor(b.xy, turn(angle), 0.0, 1, (r, r * 1.02, 3 * r), around=True)
        return Anchor(b.xy, turn(angle), r, 1, (r, 2 * r))
    if feature == "crosstie":
        x = rng.choice(plan.crossties)
        (ax, ay), (bx, by) = plan.bars[x.bar_a].xy, plan.bars[x.bar_b].xy
        dx, dy = unit(bx - ax, by - ay)
        half = x.diameter_mm / 2
        if limit == "end":
            s = rng.choice((1, -1))
            p = (ax, ay) if s < 0 else (bx, by)
            w = rng.choice((0.0, 0.0, rng.uniform(-1, 1)))  # off the axis of the tie, maybe
            return Anchor(p, unit(s * dx - w * dy, s * dy + w * dx), half, 1, (half, 2 * half))
        t, s = rng.random(), rng.choice((1, -1))
        p = (ax + t * (bx - ax), ay + t * (by - ay))
        return Anchor(p, (-s * dy, s * dx), half, 1, (half, 2 * half, 30.0))
    if feature == "hoop":
        hoop = rng.choice(plan.hoops)
        radii = [plan.bars[i].diameter_mm / 2 for i in hoop.bars]
        r_min, r_max = min(radii), max(radii)
        p, out = spot(float_hull([plan.bars[i].xy for i in hoop.bars]), rng, "convex", where)
        if limit == "in":  # within r_min of the hull: the hole's far side at r_min
            sizes = (r_min - 0.25, r_min, r_min + 0.25, r_min + 1.0, 3 * r_min)
            return Anchor(p, out, r_min, -1, sizes, present=present)
        reach = r_max + hoop.diameter_mm
        return Anchor(p, out, reach, 1, (r_min, reach), present=present)
    tie = rng.choice(plan.circular_ties)
    rho, half = tie.centerline_radius_mm, tie.diameter_mm / 2
    inner, outer = rho - half, rho + half
    if limit == "around":
        return Anchor(tie.center_mm, turn(angle), 0.0, 1, (inner * 0.7, inner, outer), around=True)
    if limit == "in":
        return Anchor(tie.center_mm, turn(angle), inner, -1, (inner / 2, inner * 1.01))
    return Anchor(tie.center_mm, turn(angle), outer, 1, (1.0, tie.diameter_mm))


def _regular(n: int, star: float = 1.0) -> tuple[XY, ...]:
    radii = [1.0, star] * (n // 2) if star != 1.0 else [1.0] * n
    angles = [2 * math.pi * i / n for i in range(n)]
    return tuple((r * math.cos(t), r * math.sin(t)) for t, r in zip(angles, radii, strict=True))


SHAPES: dict[str, tuple[XY, ...]] = {
    "square": ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)),
    "triangle": ((-1.0, -0.6), (1.0, -0.6), (0.0, 1.0)),
    "pentagon": _regular(5),
    "hexagon": _regular(6),
    "sliver": ((-1.0, 0.0), (1.0, 0.0), (0.0, 0.05)),
    "ell": ((-1.0, -1.0), (1.0, -1.0), (1.0, -0.25), (-0.25, -0.25), (-0.25, 1.0), (-1.0, 1.0)),
    "star": _regular(10, 0.4),
}
CONVEX = ("square", "triangle", "pentagon", "hexagon", "sliver")  # each edge can face a limit


def place(a: Anchor, kind: str, size: float, eps: float, rng: random.Random) -> PlanBoundary:
    """A hole at `a`, `eps` clear of the limit (negative: past it).

    A ring presents to the limit either a vertex, set exactly at the limit point, or (a convex
    ring) an edge square to `u`, centred on it; a few are moved along the limit or turned by
    a hair. A zero `eps` on a vertex or a ring of the plan so puts a vertex or an edge on it.
    """
    (px, py), (ux, uy) = a.p, a.u
    sx, sy = a.side * ux, a.side * uy  # the hole reaches this way from the limit
    if a.around:
        dx = rng.choice((0.0, 0.0, 0.1, 5.0))  # off the centre, a little or not at all
        dy = rng.choice((0.0, 0.0, 0.1, 5.0))
        qx, qy = px + dx * ux, py + dy * uy
    else:
        d = a.reach + a.side * eps
        qx, qy = px + d * ux, py + d * uy
    if kind == "circle":
        return PlanCircle((qx, qy) if a.around else (qx + size * sx, qy + size * sy), size)
    jitter = rng.choice((0.0, 0.0, 0.0, 1e-7, -1e-7, 1e-3, -1e-3))
    base = SHAPES[kind]
    edge = {"edge": 0.9, "vertex": 0.0}.get(a.present, 0.5)
    if not a.around and kind in CONVEX and rng.random() < edge:
        i = rng.randrange(len(base))
        (ex, ey), (fx, fy) = base[i], base[(i + 1) % len(base)]
        normal = math.atan2(ex - fx, fy - ey)  # the edge's outward normal (the shape is CCW)
        c, s = turn(math.atan2(-sy, -sx) - normal + jitter)
        pts = [(size * (x * c - y * s), size * (x * s + y * c)) for x, y in base]
        (ex, ey), (fx, fy) = pts[i], pts[(i + 1) % len(pts)]
        mx, my = (ex + fx) / 2, (ey + fy) / 2
        return PlanRing(tuple((qx + (x - mx), qy + (y - my)) for x, y in pts))
    axis = math.atan2(sy, sx)
    if a.present == "vertex" and rng.random() < 0.5:  # an edge along u: on the feature's line
        rot = axis + rng.randrange(4) * math.pi / 2
    else:
        rot = rng.choice((rng.uniform(0, 2 * math.pi), axis + rng.randrange(8) * math.pi / 4))
    c, s = turn(rot + jitter)
    pts = [(size * (x * c - y * s), size * (x * s + y * c)) for x, y in base]
    if a.around:
        return PlanRing(tuple((qx + x, qy + y) for x, y in pts))
    k = min(range(len(pts)), key=lambda i: pts[i][0] * sx + pts[i][1] * sy)
    kx, ky = pts[k]
    lateral = 0.0 if a.present == "vertex" else rng.choice((0.0, 0.0, rng.uniform(-size, size)))
    qx, qy = qx - lateral * uy, qy + lateral * ux
    return PlanRing(
        tuple(
            (qx, qy) if i == k else (qx + (x - kx), qy + (y - ky)) for i, (x, y) in enumerate(pts)
        )
    )


def nudge(h: PlanBoundary, toward: XY) -> PlanBoundary:
    """Every coordinate moved one float towards `toward`'s signs: just either side of contact."""

    def move(p: XY) -> XY:
        return (
            math.nextafter(p[0], math.copysign(math.inf, toward[0])) if toward[0] else p[0],
            math.nextafter(p[1], math.copysign(math.inf, toward[1])) if toward[1] else p[1],
        )

    if isinstance(h, PlanCircle):
        return PlanCircle(move(h.center_mm), h.radius_mm)
    return PlanRing(tuple(move(p) for p in h.points_mm))


def snapped(h: PlanBoundary, grid: Q, path: str, base: XY) -> PlanBoundary:
    """`h` with each coordinate snapped to `grid` about `base` along a rounding path."""

    def move(p: XY) -> XY:
        return (
            placed(Q(p[0]) - Q(base[0]), grid, path, base[0]),
            placed(Q(p[1]) - Q(base[1]), grid, path, base[1]),
        )

    if isinstance(h, PlanCircle):
        return PlanCircle(move(h.center_mm), h.radius_mm)
    return PlanRing(tuple(move(p) for p in h.points_mm))


def turned(hole: PlanBoundary, k: int) -> PlanBoundary:
    """A ring started at vertex k mod n, reversed when (k div n) is odd; a circle as it is."""
    if isinstance(hole, PlanCircle):
        return hole
    pts = hole.points_mm
    n = len(pts)
    pts = pts[k % n :] + pts[: k % n]
    return PlanRing(pts[::-1] if (k // n) % 2 else pts)


@dataclass(frozen=True)
class Case:
    family: str  # which limit of which feature the last hole was aimed at (`FAMILIES`)
    rule: int
    how: str  # a placement of `MODES`, or "equal"
    plan: Plan
    holes: tuple[PlanBoundary, ...]


# How far from the limit: just past it or just clear (a gap of `EPS`), at contact, a float
# either side of contact, straddling it, wholly across it, or far clear of it.
MODES = ("near-", "near+", "near-", "near+", "contact", "ulp", "straddle", "across", "far")
CLEAR = ("near+", "far")


def one_hole(
    plan: Plan, family: str, mode: str, rng: random.Random, priors: Sequence[PlanBoundary]
) -> PlanBoundary | None:
    """One hole of `family` placed by `mode`; None when snapping folded the ring."""
    a = anchor(plan, family, rng, priors)
    circles = {"edge": 0.15, "vertex": 0.1}.get(a.present, 0.6 if a.side < 0 else 0.35)
    if rng.random() < circles:
        kind = "circle"
    else:
        kind = rng.choice(CONVEX if a.present == "edge" else tuple(SHAPES))
    size = rng.choice(a.sizes if a.sizes and rng.random() < 0.5 else SIZES)
    eps = {
        "near-": -rng.choice(EPS),
        "near+": rng.choice(EPS),
        "contact": 0.0,
        "ulp": 0.0,
        "straddle": -size,
        "across": -2 * size - rng.choice((0.0, 1e-9, 1.0)),
        "far": rng.choice((5.0, 40.0)),
    }[mode]
    hole = place(a, kind, size, eps, rng)
    if mode == "ulp":
        sign = rng.choice((1, -1)) * a.side
        hole = nudge(hole, (sign * a.u[0], sign * a.u[1]))
    if rng.random() < 0.2:
        grid, path = rng.choice(GRIDS), rng.choice(PATHS)
        outline = next(f for f in plan.faces if f.role == "concrete").boundary
        base = outline.center_mm if isinstance(outline, PlanCircle) else outline.points_mm[0]
        hole = snapped(hole, grid, path, base)
        # A grid coarse for the hole may fold a ring: the rules take simple rings only.
        folded = isinstance(hole, PlanRing) and not simple(hole.points_mm)
        if folded or (isinstance(hole, PlanRing) and not twice_area(hole.points_mm)):
            return None
    if isinstance(hole, PlanRing):
        hole = turned(hole, rng.randrange(2 * len(hole.points_mm)))
    return hole


# The limits with the most ways to be wrong get more cases: the bands, covers and ties.
WEIGHTS = {"hoop-in": 3, "crosstie": 3, "crosstie-end": 4, "tie-in": 4, "tie-out": 4,
           "tie-around": 2}  # fmt: skip


def has_corner(plan: Plan, family: str) -> bool:
    """`plan` has a corner of the kind `family` meets at "@corner" or "@line": one that pokes
    towards the hole. A circle has none. Near a hull's corner the band within r_min lies in
    the corner bar, so "hoop-in" is met at edges only."""
    feature, _, limit = family.partition("@")[0].partition("-")
    face = next(f for f in plan.faces if f.role == "concrete")
    if feature == "prior":
        return limit == "out"
    if feature == "hoop":
        return limit == "out"
    ring = face.boundary if feature == "outline" else face.holes[0]
    if isinstance(ring, PlanCircle):
        return False
    if feature == "void" or limit == "out":
        return True  # every ring has a convex corner
    pts = ccw(ring.points_mm)
    n = len(pts)
    return any(
        (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) < 0
        for a, b, c in ((pts[i - 1], pts[i], pts[(i + 1) % n]) for i in range(n))
    )


def strata() -> list[tuple[str, str]]:
    """Every (template, family) whose feature the template draws, `WEIGHTS` times over."""
    out: list[tuple[str, str]] = []
    for base in ALL_BASES:
        plan = plan_at(base, 0.0)
        for f, (_, needs) in FAMILIES.items():
            if not all(has(plan, n) for n in needs):
                continue
            if f.endswith(("@corner", "@line")) and not has_corner(plan, f):
                continue
            if f == "crosstie-end" and not any(
                x.diameter_mm > min(plan.bars[x.bar_a].diameter_mm, plan.bars[x.bar_b].diameter_mm)
                for x in plan.crossties
            ):
                continue  # the tie's ends lie inside its bars: R4 meets them first
            out += [(base, f)] * WEIGHTS.get(f.partition("@")[0], 1)
    return out


def generated(n: int, seed: int) -> list[Case]:
    """`n` cases, dealt round the strata and, within one, round the modes."""
    rng = random.Random(seed)
    truths: dict[int, Truth] = {}
    layers = strata()
    out: list[Case] = []
    i = 0
    while len(out) < n:
        base, family = layers[i % len(layers)]
        mode = MODES[(i // len(layers)) % len(MODES)]
        i += 1
        rule, needs = FAMILIES[family]
        strips = [s for s in STRIPS if not set(needs) & set(s)]
        if rule >= 4 and rng.random() < 0.7:  # the steel rules, mostly past the cover
            strips = [s for s in strips if "cover_guides" in s]
        strip = rng.choice(strips)
        plan = plan_at(base, rng.choice(OFFSETS), strip)
        truth = truths.setdefault(id(plan), Truth(plan))
        others = [f for f, (_, ns) in FAMILIES.items() if all(has(plan, x) for x in ns)]
        count = rng.choice((2, 2, 3, 4) if family.startswith("prior") else (1,) * 8 + (2, 3, 4))
        holes: list[PlanBoundary] = []
        while len(holes) < count - 1:  # earlier holes that pass, so the last one is judged
            for _try in range(4):
                pick = rng.choice([f for f in others if holes or not f.startswith("prior")])
                hole = one_hole(plan, pick, rng.choice(CLEAR), rng, holes)
                if hole is None:
                    continue
                cores = [shape(h) for h in (*holes, hole)]
                if all(truth.passes(r, cores, len(holes)) for r in range(1, 8)):
                    break
            if hole is not None:
                holes.append(hole)
        last = one_hole(plan, family, mode, rng, holes)
        if last is not None:
            out.append(Case(family, rule, mode, plan, (*holes, last)))
    return out


def equal_cases() -> list[Case]:
    """A hole equal to `rect_hollow`'s void (R2) and to a CFT core (R1), at every offset."""
    out: list[Case] = []
    for off in OFFSETS:
        rh = plan_at("rh", off)
        out.append(Case("rh-void-equal", 2, "equal", rh, (rh.faces[0].holes[0],)))
        for base in ("cr", "ct"):
            cft = plan_at(base, off)
            out.append(Case(f"{base}-core-equal", 1, "equal", cft, (cft.faces[0].boundary,)))
    return out


@dataclass(frozen=True)
class Judged:
    """A case and the truth about it: its verdict, and whether its last hole passes the rule it
    was aimed at (`clear`, a positive clearance) and every hole every rule (`clear_all`)."""

    case: Case
    truth: tuple[int, int] | None
    clear: bool
    clear_all: bool


@cache
def fuzz() -> tuple[Judged, ...]:
    """Every case, judged by the truth."""
    truths: dict[int, Truth] = {}
    out: list[Judged] = []
    for case in generated(CASES, SEED) + equal_cases():
        truth = truths.setdefault(id(case.plan), Truth(case.plan))
        first = truth.verdict(case.holes)
        last = len(case.holes) - 1
        clear = truth.passes(case.rule, [shape(h) for h in case.holes], last)
        out.append(Judged(case, first, clear, first is None))
    return tuple(out)


def verdict(case: Case) -> tuple[int, int] | None:
    clash = first_clash(case.plan, case.holes)
    return None if clash is None else (clash.index, clash.rule)


def mismatches(judged: Sequence[Judged]) -> list[str]:
    bad: list[str] = []
    for j in judged:
        try:
            got: object = verdict(j.case)
        except Exception as exc:  # a mutant may also crash; that is a failure too
            got = ("crash", type(exc).__name__)
        if got != j.truth:
            c = j.case
            bad.append(f"{c.family} {c.how}: got {got}, truth {j.truth}: {c.holes}")
    return bad


HOWS = (*dict.fromkeys(MODES), "equal")


def test_the_fuzz_agrees_with_the_truth_and_shows_both_verdicts_of_every_rule() -> None:
    judged = fuzz()
    bad = mismatches(judged)
    assert not bad, f"{len(bad)} of {len(judged)} verdicts differ from the truth:\n" + "\n".join(
        bad[:20]
    )
    refused: Counter[tuple[int, str]] = Counter()
    accepted: Counter[tuple[int, str]] = Counter()
    for j in judged:
        rule, last = j.case.rule, len(j.case.holes) - 1
        # Exact clearance 0 or less (overlap or contact) is refused; a positive clearance that
        # no other rule refuses is accepted (18.2).
        if not j.clear:
            assert j.truth is not None, j.case
        if j.clear_all:
            assert j.truth is None, j.case
        if j.truth == (last, rule):
            refused[(rule, j.case.how)] += 1
        elif j.truth is None:
            accepted[(rule, j.case.how)] += 1
    report = "\n".join(
        f"R{r}: refused {sum(refused[(r, h)] for h in HOWS)}, "
        f"accepted {sum(accepted[(r, h)] for h in HOWS)}; "
        + ", ".join(f"{h} {refused[(r, h)]}/{accepted[(r, h)]}" for h in HOWS)
        for r in range(1, 8)
    )
    print(f"\n{len(judged)} cases (refused/accepted by how they were placed)\n{report}")
    for r in range(1, 8):
        both = sum(refused[(r, h)] for h in HOWS) and sum(accepted[(r, h)] for h in HOWS)
        assert both, f"R{r} does not show both verdicts\n{report}"
        assert refused[(r, "ulp")] + accepted[(r, "ulp")], f"R{r}: no float beside contact"


# --- the reverts of 18.2: the fuzz must fail without any one rule, and on plain floats ------


@pytest.mark.parametrize("dropped", range(1, 8))
def test_the_fuzz_fails_with_one_rule_dropped(
    dropped: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Only a case the truth refuses by the dropped rule can tell the mutant apart, so only
    # those run here; the whole fuzz fails too (shown in a scratch tree, in the PR body).
    kept = tuple(r for r in hole_rules._RULES if r[0] != dropped)  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(hole_rules, "_RULES", kept)
    telling = [j for j in fuzz() if j.truth is not None and j.truth[1] == dropped]
    assert mismatches(telling), f"the fuzz cannot tell R{dropped} is missing"


def test_the_fuzz_fails_on_plain_floats(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hole_rules, "_q", float)
    bad = mismatches(fuzz())
    print(f"\nplain floats: {len(bad)} of {len(fuzz())} verdicts differ from the truth")
    assert bad, "the fuzz cannot tell plain floats from the exact decision"


# --- 18.3, the hand cases ------------------------------------------------------------------

RECT_COLUMN = {
    "material": "C30", "b": 400, "h": 600, "center_mm": [200, 300], "cover": 40, "nx": 3,
    "ny": 3, "bar": "Ø20", "tie": "Ø10", "tie_spacing": 150,
}  # fmt: skip


def clash(plan: Plan, *holes: PlanBoundary) -> tuple[int, int] | None:
    got = first_clash(plan, holes)
    assert (None if got is None else (got.index, got.rule)) == Truth(plan).verdict(holes)
    return None if got is None else (got.index, got.rule)


def test_rect_column_centred_duct() -> None:
    hole = PlanCircle((200.0, 300.0), 50.0)
    plan = expand("rect_column", {**RECT_COLUMN, "crossties": "none"}, 1)
    assert clash(plan, hole) is None
    assert 400 * 600 - math.pi * 50**2 == pytest.approx(232_146.0, abs=0.05)
    ties = expand("rect_column", {**RECT_COLUMN, "crossties": "all"}, 1)
    assert clash(ties, hole) == (0, 5)
    with pytest.raises(TemplateParamError) as raised:
        require_holes_clear("rect_column", ties, [hole])
    assert raised.value.param == "holes[0]"
    assert str(raised.value).startswith("rect_column: holes[0]: R5: it meets crosstie 0")


def test_rect_hollow_wall_duct() -> None:
    plan = plan_at("rh", 0.0)
    # Between outer bars (242, 0) and (242, 171), and between the hoops: beyond the inner hull
    # (x = 208) by more than 18, within 8 of the outer hull (x = 242).
    assert clash(plan, PlanCircle((238.0, 85.5), 5.0)) is None
    # Moved towards the void until it is 40 mm (the cover) from it: R3, contact refused.
    assert clash(plan, PlanCircle((195.0, 85.5), 5.0)) == (0, 3)
    assert clash(plan, PlanCircle((194.99, 85.5), 5.0)) == (0, 3)


def test_t_beam_duct_on_the_stirrup_leg_in_the_flange() -> None:
    plan = expand("t_beam", {**T_BEAM_PARAMS, "hf": 200}, 1)
    hole = PlanCircle((116.75, 490.0), 25.0)
    assert clash(plan, hole) == (0, 6)
    truth = Truth(plan)

    cores = [shape(hole)]
    assert all(truth.passes(r, cores, 0) for r in (1, 2, 3, 4, 5))  # it clears R3 and R4


@pytest.mark.parametrize("base", ["cr", "ct"])
def test_cft_core_tangent_touching_and_clear(base: str) -> None:
    plan = plan_at(base, 0.0)
    core = plan.faces[0].boundary
    assert clash(plan, core) == (0, 1)  # a hole equal to the core touches its outline
    if isinstance(core, PlanCircle):
        tangent = PlanCircle((190.0 - 25.0, 0.0), 25.0)
        clear = PlanCircle((190.0 - 25.01, 0.0), 25.0)
        a, b = PlanCircle((-50.0, 0.0), 25.0), PlanCircle((0.0, 0.0), 25.0)
        b_clear = PlanCircle((0.01, 0.0), 25.0)
    else:
        tangent = PlanRing(((88.0, -25.0), (138.0, -25.0), (138.0, 25.0), (88.0, 25.0)))
        clear = PlanRing(((88.0, -25.0), (137.99, -25.0), (137.99, 25.0), (88.0, 25.0)))
        a = PlanRing(((-60.0, -20.0), (-20.0, -20.0), (-20.0, 20.0), (-60.0, 20.0)))
        b = PlanRing(((-20.0, -20.0), (20.0, -20.0), (20.0, 20.0), (-20.0, 20.0)))
        b_clear = PlanRing(((-19.99, -20.0), (20.0, -20.0), (20.0, 20.0), (-19.99, 20.0)))
    assert clash(plan, tangent) == (0, 1)
    assert clash(plan, clear) is None
    assert clash(plan, a, b) == (1, 2)  # two holes that touch: named at the later one
    assert clash(plan, a, b_clear) is None


def test_circular_column_spiral_inner_face() -> None:
    plan = plan_at("cc", 0.0)  # rho 255, t 10: the inner face is 250 from the centre
    assert clash(plan, PlanCircle((0.0, 225.0), 25.0)) == (0, 7)
    assert clash(plan, PlanCircle((0.0, 224.99), 25.0)) is None


def test_a_hole_equal_to_the_void_meets_it() -> None:
    plan = plan_at("rh", 0.0)
    assert clash(plan, plan.faces[0].holes[0]) == (0, 2)


# --- exact ring predicates (16.1), on the three rings of 18.4 -----------------------------

FLOAT_ORIENTATION_WRONG = (
    (39999.56872848823, 40000.99486747388),
    (40260.93513113888, 39758.30007034527),
    (40527.11796644146, 39511.13291895272),
)
WRONG_ONCE_REVERSED = (
    (-0.003034104320175181, -0.14196400488515),
    (-39578.90871125873, -28092.58529687345),
    (-0.00039359544240611885, -0.14008981597695389),
    (-0.000311942809276937, -0.14003186030764175),
)
FLOAT_SIMPLICITY_WRONG = (
    (0.005211328185895844, -0.061594004755554),
    (1329.183505433143, 219.15109444252522),
    (3091.0945986391544, 509.73157507462827),
)


def test_exact_orientation_and_simplicity_where_floats_are_wrong() -> None:
    ring = FLOAT_ORIENTATION_WRONG
    assert float(exact_twice_area(ring)) == pytest.approx(-4.66e-09, rel=0.01)
    assert signed_area(ring) > 0.0 and is_simple(ring) and exact_is_simple(ring)
    ring = WRONG_ONCE_REVERSED
    assert float(exact_twice_area(ring)) == pytest.approx(1.89e-13, rel=0.01)
    assert exact_twice_area(ring[::-1]) == -exact_twice_area(ring)
    assert signed_area(ring[::-1]) > 0.0 and exact_is_simple(ring[::-1])
    ring = FLOAT_SIMPLICITY_WRONG
    assert float(exact_twice_area(ring)) == pytest.approx(-1.328e-11, rel=0.01)
    assert not is_simple(ring) and not is_simple(ring[::-1])
    assert exact_is_simple(ring) and exact_is_simple(ring[::-1])


def test_exact_simplicity_faults_are_named() -> None:
    assert (
        exact_simplicity_fault([(0.0, 0.0), (1.0, 0.0)])
        == "a ring needs at least 3 vertices, got 2"
    )
    assert "repeat" in (exact_simplicity_fault([(0.0, 0.0), (1.0, 0.0), (0.0, 0.0)]) or "")
    bow = [(0.0, 0.0), (1.0, 1.0), (1.0, 0.0), (0.0, 1.0)]
    assert exact_simplicity_fault(bow) == "edges 0 and 2 cross or touch"
    # A T-touch: vertex 3 lies on edge 0 without crossing it (only the collinear clauses see it).
    tee = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (2.0, 0.0), (0.0, 4.0)]
    assert exact_simplicity_fault(tee) == "edges 0 and 2 cross or touch"
    assert not exact_is_simple(tee)
    spike = [(0.0, 0.0), (2.0, 0.0), (1.0, 0.0), (1.0, 1.0)]
    assert exact_simplicity_fault(spike) == "edges 0 and 1 overlap"
    assert exact_twice_area([(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]) == 1


def every_turn(ring: Sequence[XY]) -> list[tuple[XY, ...]]:
    """`ring` started at each vertex, in both orientations."""
    n = len(ring)
    out: list[tuple[XY, ...]] = []
    for k in range(2 * n):
        pts = (*ring[k % n :], *ring[: k % n])
        out.append(pts[::-1] if k // n else pts)
    return out


NAMED_RINGS: dict[str, tuple[XY, ...]] = {
    "bow-tie": ((0.0, 0.0), (1.0, 1.0), (1.0, 0.0), (0.0, 1.0)),
    "reversed bow-tie": ((0.0, 1.0), (1.0, 0.0), (1.0, 1.0), (0.0, 0.0)),
    "T-touch": ((0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (2.0, 0.0), (0.0, 4.0)),
    "spike": ((0.0, 0.0), (2.0, 0.0), (1.0, 0.0), (1.0, 1.0)),
    "repeat": ((0.0, 0.0), (2.0, 0.0), (1.0, 1.0), (2.0, 2.0), (0.0, 2.0), (1.0, 1.0)),
    "vertex on the closing edge": ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (2.0, 0.0)),
    "vertex on a far edge": ((0.5, 1.0), (1.0, 0.0), (1.5, 1.0), (2.0, 0.0), (0.0, 0.0)),
    "collinear, apart": ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (3.0, 1.0), (3.0, 0.0), (2.0, 0.0),
                         (2.0, -1.0), (0.0, -1.0)),
    "straight vertex": ((0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (2.0, 1.0), (0.0, 1.0)),
    "square": ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
    "ell": ((0.0, 0.0), (2.0, 0.0), (2.0, 1.0), (1.0, 1.0), (1.0, 2.0), (0.0, 2.0)),
    "float orientation wrong": FLOAT_ORIENTATION_WRONG,
    "wrong once reversed": WRONG_ONCE_REVERSED,
    "float simplicity wrong": FLOAT_SIMPLICITY_WRONG,
}  # fmt: skip


@pytest.mark.parametrize("name", NAMED_RINGS)
def test_exact_simplicity_in_every_start_vertex_and_orientation(name: str) -> None:
    """The first fault, by name, and the twice-area equal the truth's, however the ring is
    started and turned; whether it is simple does not depend on either."""
    turns = every_turn(NAMED_RINGS[name])
    for ring in turns:
        assert exact_simplicity_fault(ring) == fault(ring), ring
        assert exact_twice_area(ring) == twice_area(ring), ring
    assert len({exact_is_simple(ring) for ring in turns}) == 1


def test_exact_simplicity_fuzz_on_a_small_grid() -> None:
    """Rings of 3 to 6 vertices on a 4 x 4 grid (dense in collinear, touching and repeated
    vertices), placed at an offset or not, in every start vertex and orientation."""
    rng = random.Random(SEED)
    simple_ones = 0
    for _ in range(1000):
        n = rng.randint(3, 6)
        grid = [(float(rng.randint(0, 3)), float(rng.randint(0, 3))) for _ in range(n)]
        scale, off = rng.choice(((1.0, 0.0), (0.1, 40000.3), (12.5, 1234.5)))
        ring = tuple((x * scale + off, y * scale - off) for x, y in grid)
        for turned_ring in every_turn(ring):
            assert exact_simplicity_fault(turned_ring) == fault(turned_ring), turned_ring
            assert exact_twice_area(turned_ring) == twice_area(turned_ring), turned_ring
        simple_ones += fault(ring) is None
    assert 0 < simple_ones < 1000  # both answers


# --- refusals by name ----------------------------------------------------------------------


def test_a_plan_without_one_concrete_face_is_refused_by_name() -> None:
    plan = Plan(faces=(PlanFace("void", None, PlanCircle((0.0, 0.0), 10.0)),))
    with pytest.raises(DocumentError, match="one concrete face; this one has 0"):
        first_clash(plan, [PlanCircle((0.0, 0.0), 1.0)])


def test_a_malformed_hole_is_refused_by_name() -> None:
    plan = plan_at("cr", 0.0)
    with pytest.raises(DocumentError, match=r"holes\[0\]: a ring needs at least 3 vertices"):
        first_clash(plan, [PlanRing(((0.0, 0.0), (1.0, 0.0)))])
    with pytest.raises(DocumentError, match=r"holes\[1\] centre x_mm must be a finite"):
        first_clash(plan, [PlanCircle((0.0, 0.0), 1.0), PlanCircle((math.nan, 0.0), 1.0)])


def test_no_holes_is_no_clash() -> None:
    assert first_clash(plan_at("rc", 0.0), []) is None


# --- a hole that swallows what it must clear, far from every edge of it ----------------------


def square(cx: float, cy: float, half: float) -> PlanRing:
    return PlanRing(
        (
            (cx - half, cy - half),
            (cx + half, cy - half),
            (cx + half, cy + half),
            (cx - half, cy + half),
        )
    )


def test_a_hole_that_swallows_steel_or_a_hole_is_refused() -> None:
    """Far from the hole's edges, so no edge screen sees it: only the containment test can."""
    face = PlanFace("concrete", "C30", square(0.0, 0.0, 1000.0))
    bars = (PlanBar(-10.0, 0.0, "Ø20", 20.0), PlanBar(10.0, 0.0, "Ø20", 20.0))
    big = square(0.0, 0.0, 400.0)
    assert clash(Plan(faces=(face,), bars=bars), big) == (0, 4)
    tie = PlanCrosstie(0, 1, "Ø10", 10.0, 150.0)
    assert clash(Plan(faces=(face,), bars=bars, crossties=(tie,)), big) == (0, 4)
    assert clash(Plan(faces=(face,)), square(0.0, 0.0, 5.0), big) == (1, 2)
    assert clash(Plan(faces=(face,)), big, square(0.0, 0.0, 5.0)) == (1, 2)
    # R7: the tie's centre lies deep inside a hole too big to sit within the spiral.
    spiral = PlanCircularTie("spiral", (0.0, 0.0), 255.0, "Ø10", 10.0, 75.0)
    assert clash(Plan(faces=(face,), circular_ties=(spiral,)), big) == (0, 7)
    assert clash(Plan(faces=(face,), circular_ties=(spiral,)), square(0.0, 0.0, 100.0)) is None


def test_the_float_screens_round_outward() -> None:
    third = Q(1, 3)
    assert hole_rules._down(third) < third < hole_rules._up(third)  # pyright: ignore[reportPrivateUsage]
    assert hole_rules._down(Q(0.5)) == hole_rules._up(Q(0.5)) == 0.5  # pyright: ignore[reportPrivateUsage]
    box = (Q(0.1), Q(-40000.3), Q(1234.5), Q(0.3))
    lo_x, lo_y, hi_x, hi_y = hole_rules._grown(box, Q(1, 100))  # pyright: ignore[reportPrivateUsage]
    assert lo_x <= box[0] - Q(1, 100) and lo_y <= box[1] - Q(1, 100)
    assert hi_x >= box[2] + Q(1, 100) and hi_y >= box[3] + Q(1, 100)
