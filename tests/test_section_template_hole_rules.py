"""The exact hole rules R1 to R7 (ADR 0040 Errata 17), against the oracle of Errata 18.1 to 18.3.

C9-2a (apeSection#204). `section/templates/hole_rules.py` decides each rule exactly, in
`fractions.Fraction`, on the stored floats. The truth is `tests/_hole_rules_truth.py`, an
exact reference built differently that imports none of the product's predicate code (18.1).

- 18.2, the two-sided fuzz: one seeded fuzz over the seven templates and every rule, with
  circle and ring holes at gaps of -1, -0.01, 0, +0.01 and +1 mm from each limit and at the
  nearest floats on either side of contact; on grids of 0.01, 0.1, 1 and 5 mm; at `center_mm`
  offsets 0, 0.1, 1234.5 and 40000.3; coordinates built as `i/10`, `i*0.1` and
  `round(k*g, 6)`; inclined `polygon_column` edges; dyadic radii. Every verdict must equal the
  truth, and each rule must both refuse and accept. With one rule dropped, or with plain
  floats in place of `Fraction`, the fuzz must fail.
- 18.3, the hand cases.

Some fuzz families strip a part of a template's plan (its cover guide, bars, hoops or circular
tie) so that a rule is reached on both sides; the rules are a function of the `Plan` alone.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from fractions import Fraction as Q
from functools import cache

import pytest

from _hole_rules_truth import Truth, shape
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
    PlanCrosstie,
    PlanFace,
    PlanRing,
    TemplateParamError,
)

SEED = 20261122
OFFSETS = (0.0, 0.1, 1234.5, 40000.3)
GRIDS = (Q(1, 100), Q(1, 10), Q(1), Q(5))
PATHS = ("div", "mul", "round")  # i / 10, i * 0.1, round(i * 0.1, 6)
GAPS = (Q(-1), Q(-1, 100), Q(0), Q(1, 100), Q(1))
PATHS_PER_CASE = 3  # grid and path pairs drawn per (family, shape, gap, offset)

# --- templates, centred on (0, 0); a fuzz offset moves them to (off, -off) ----------------

BASES: dict[str, tuple[str, dict[str, object]]] = {
    "rc": ("rect_column", {
        "material": "C30", "b": 400, "h": 600, "cover": 40, "nx": 3, "ny": 3, "bar": "Ø20",
        "tie": "Ø10", "tie_spacing": 150, "crossties": "none"}),
    "rc_all": ("rect_column", {
        "material": "C30", "b": 400, "h": 600, "cover": 40, "nx": 3, "ny": 3, "bar": "Ø20",
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


@cache
def plan_at(base: str, off: float, strip: tuple[str, ...] = ()) -> Plan:
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


# --- hole shapes, on an axis: `along` is the coordinate the hole approaches the limit on ------


def to_xy(axis: int, along: float, across: float) -> tuple[float, float]:
    return (along, across) if axis == 0 else (across, along)


def build(kind: str, size: float, axis: int, side: int, near: float, across: float) -> PlanBoundary:
    """A hole whose controlling coordinate is `near`: a circle's centre, a ring's nearest side.

    A square's near edge and a diamond's near vertex lie at `near`; the rest of the ring
    reaches away from the limit (`side`), every coordinate computed in floats.
    """
    if kind == "circle":
        return PlanCircle(to_xy(axis, near, across), size)
    far, mid = near + side * 2 * size, near + side * size
    lo, hi = across - size, across + size
    if kind == "square":
        pts = [(near, lo), (far, lo), (far, hi), (near, hi)]
    else:
        pts = [(near, across), (mid, lo), (far, across), (mid, hi)]
    return PlanRing(tuple(to_xy(axis, a, c) for a, c in pts))


Limit = Callable[[Plan, Sequence[PlanBoundary]], Q]


@dataclass(frozen=True)
class Family:
    """Holes that approach one limit of one rule along an axis.

    `limit(plan, priors)` is the limit's coordinate on `axis` in that plan; the hole lies on
    the `side` of it where the rule holds, `gap` beyond it. `across` is the hole's other
    coordinate before the offset. `priors` are earlier holes (R2), given before the offset.
    """

    name: str
    rule: int
    base: str
    axis: int
    side: int
    limit: Limit
    across: Q
    shapes: tuple[tuple[str, float], ...]
    strip: tuple[str, ...] = ()
    priors: tuple[PlanBoundary, ...] = ()


def bar(i: int, axis: int, sign: int) -> Limit:
    """Bar i's centre on `axis`, moved by `sign` times its radius."""

    def limit(plan: Plan, _priors: Sequence[PlanBoundary]) -> Q:
        b = plan.bars[i]
        return Q(b.xy[axis]) + sign * Q(b.diameter_mm) / 2

    return limit


def bar_plus(i: int, axis: int, extra: Q) -> Limit:
    return lambda plan, _priors: Q(plan.bars[i].xy[axis]) + extra


def tie_face(axis: int, sign: int) -> Limit:
    """A circular tie's centre on `axis` plus rho -/+ t / 2: its inner (sign < 0) or outer face."""

    def limit(plan: Plan, _priors: Sequence[PlanBoundary]) -> Q:
        t = plan.circular_ties[0]
        rho, half = Q(t.centerline_radius_mm), Q(t.diameter_mm) / 2
        return Q(t.center_mm[axis]) + (rho - half if sign < 0 else rho + half)

    return limit


def outline_at(face: int, vertex: int, axis: int, extra: Q = Q(0)) -> Limit:
    """A ring vertex's coordinate on `axis` (a face's edge line), plus `extra`."""

    def limit(plan: Plan, _priors: Sequence[PlanBoundary]) -> Q:
        ring = plan.faces[face].boundary
        assert isinstance(ring, PlanRing)
        return Q(ring.points_mm[vertex][axis]) + extra

    return limit


def own_hole_at(vertex: int, axis: int, extra: Q = Q(0)) -> Limit:
    def limit(plan: Plan, _priors: Sequence[PlanBoundary]) -> Q:
        ring = plan.faces[0].holes[0]
        assert isinstance(ring, PlanRing)
        return Q(ring.points_mm[vertex][axis]) + extra

    return limit


def circle_edge(face: int, axis: int, extra: Q) -> Limit:
    """A circle outline's centre on `axis` plus its radius plus `extra`."""

    def limit(plan: Plan, _priors: Sequence[PlanBoundary]) -> Q:
        c = plan.faces[face].boundary
        assert isinstance(c, PlanCircle)
        return Q(c.center_mm[axis]) + Q(c.radius_mm) + extra

    return limit


def prior_right(plan: Plan, priors: Sequence[PlanBoundary]) -> Q:
    """The right-most x of the last prior hole."""
    h = priors[-1]
    if isinstance(h, PlanCircle):
        return Q(h.center_mm[0]) + Q(h.radius_mm)
    return max(Q(x) for x, _ in h.points_mm)


ALL = (("circle", 12.5), ("circle", 12.3), ("square", 12.5), ("diamond", 12.5))
ROUND = (("circle", 12.5), ("circle", 12.3), ("circle", 25.0), ("diamond", 12.5))
SMALL = (("circle", 2.5), ("circle", 5.0), ("square", 2.5), ("diamond", 2.5))
NO_STEEL = ("bars", "hoops", "crossties", "circular_ties")

FAMILIES: tuple[Family, ...] = (
    # R1 face: the core outline of a CFT (no cover guide), circular and rectangular.
    Family("cr-core", 1, "cr", 0, -1, circle_edge(0, 0, Q(0)), Q(0), ROUND),
    Family("ct-core-right", 1, "ct", 0, -1, outline_at(0, 1, 0), Q(0), ALL),
    Family("ct-core-top", 1, "ct", 1, -1, outline_at(0, 2, 1), Q(30), ALL),
    # R2 holes: an earlier hole, and the face's own hole (rect_hollow's void).
    Family("cr-two-circles", 2, "cr", 0, 1, prior_right, Q(0), ALL,
           priors=(PlanCircle((-50.0, 0.0), 25.0),)),
    Family("ct-two-squares", 2, "ct", 0, 1, prior_right, Q(0), ALL,
           priors=(PlanRing(((-60.0, -20.0), (-20.0, -20.0), (-20.0, 20.0), (-60.0, 20.0))),)),
    Family("rh-void", 2, "rh", 0, 1, own_hole_at(2, 0), Q(0), ALL,
           strip=("cover_guides", *NO_STEEL)),
    # R3 cover: the t_beam flange (bottom, top, right), the void, a circular outline.
    Family("tb-flange-bottom", 3, "tb", 1, 1, outline_at(0, 3, 1, Q(30)), Q(275),
           (*ALL, ("circle", 25.0))),
    Family("tb-flange-top", 3, "tb", 1, -1, outline_at(0, 4, 1, Q(-30)), Q(275), ROUND),
    Family("tb-flange-right", 3, "tb", 0, -1, outline_at(0, 3, 0, Q(-30)), Q(200), ROUND),
    Family("rh-void-cover", 3, "rh", 0, 1, own_hole_at(2, 0, Q(40)), Q(0), ALL, strip=NO_STEEL),
    Family("cc-cover", 3, "cc", 1, -1, circle_edge(0, 1, Q(-40)), Q(0), ROUND, strip=NO_STEEL),
    # R4 bars.
    Family("rc-bar-right", 4, "rc", 0, -1, bar(3, 0, -1), Q(0), ALL),
    Family("rc-bar-top", 4, "rc", 1, -1, bar(5, 1, -1), Q(0), ALL),
    Family("tb-slab-bar", 4, "tb", 1, -1, bar(7, 1, -1), Q(425, 2), ALL),
    Family("cc-bar", 4, "cc", 0, -1, bar(0, 0, -1), Q(0), ALL),
    # R5 crossties: rect_column "all", its vertical tie (bars 1-5) and horizontal tie (3-7).
    Family("rc-tie-vertical", 5, "rc_all", 0, 1, bar_plus(1, 0, Q(5)), Q(120), ALL),
    Family("rc-tie-horizontal", 5, "rc_all", 1, 1, bar_plus(3, 1, Q(5)), Q(70), ALL),
    # R6 hoops: inside the cage (r_min), outside it (r_max + t).
    Family("rc-hoop-inside", 6, "rc", 0, -1, bar_plus(3, 0, Q(10)), Q(120),
           (*ALL, ("circle", 25.0))),
    Family("rh-inner-hoop-outside", 6, "rh", 0, 1, bar_plus(19, 0, Q(18)), Q(171, 2), SMALL),
    Family("rh-outer-hoop-inside", 6, "rh", 0, -1, bar_plus(5, 0, Q(8)), Q(171, 2), SMALL),
    # R7 circular ties: the spiral's inner face, and its outer face without the cover guide.
    Family("cc-spiral-inside", 7, "cc", 1, -1, tie_face(1, -1), Q(0), ROUND),
    Family("cc-spiral-outside", 7, "cc", 1, 1, tie_face(1, 1), Q(0),
           (("circle", 12.5), ("diamond", 12.5)), strip=("cover_guides",)),
)  # fmt: skip


@dataclass(frozen=True)
class NormalFamily:
    """Holes that approach an inclined edge along its normal (all in floats, no grid)."""

    name: str
    rule: int
    base: str
    edge: Callable[[Plan], tuple[tuple[float, float], tuple[float, float]]]
    tau: float
    offset: float  # from the edge to the limit, along the outward normal
    side: int  # +1: the rule holds beyond the limit, -1: on the edge's side of it
    shapes: tuple[tuple[str, float], ...]
    strip: tuple[str, ...] = ()


def outline_edge(i: int) -> Callable[[Plan], tuple[tuple[float, float], tuple[float, float]]]:
    def edge(plan: Plan) -> tuple[tuple[float, float], tuple[float, float]]:
        ring = plan.faces[0].boundary
        assert isinstance(ring, PlanRing)
        pts = ring.points_mm
        return pts[i], pts[(i + 1) % len(pts)]

    return edge


def hoop_edge(i: int) -> Callable[[Plan], tuple[tuple[float, float], tuple[float, float]]]:
    def edge(plan: Plan) -> tuple[tuple[float, float], tuple[float, float]]:
        ids = plan.hoops[0].bars
        return plan.bars[ids[i]].xy, plan.bars[ids[(i + 1) % len(ids)]].xy

    return edge


NORMAL_FAMILIES: tuple[NormalFamily, ...] = (
    # polygon_column's inclined edge (600, 300) -> (0, 500), and its hoop's inclined top edge.
    NormalFamily("pc-inclined-face", 1, "pc", outline_edge(2), 0.5, 0.0, -1,
                 (("circle", 2.5), ("diamond", 2.5)), strip=("cover_guides",)),
    NormalFamily("pc-inclined-cover", 3, "pc", outline_edge(2), 0.5, -40.0, -1,
                 (("circle", 2.5), ("diamond", 2.5)), strip=("hoops",)),
    NormalFamily("pc-inclined-hoop-out", 6, "pc", hoop_edge(2), 0.625, 20.0, 1,
                 (("circle", 2.5), ("diamond", 2.5)), strip=("cover_guides",)),
    NormalFamily("pc-inclined-hoop-in", 6, "pc", hoop_edge(2), 0.625, 10.0, -1,
                 (("circle", 12.5), ("diamond", 12.5))),
    # t_beam's right stirrup leg, 110 mm below the top (the hand case's place): both bands.
    NormalFamily("tb-leg-out", 6, "tb", hoop_edge(2), 440 / 502, 20.0, 1,
                 (("circle", 12.5), ("circle", 25.0), ("diamond", 12.5))),
    NormalFamily("tb-leg-in", 6, "tb", hoop_edge(2), 440 / 502, 8.0, -1,
                 (("circle", 12.5), ("circle", 25.0), ("diamond", 12.5))),
)  # fmt: skip


@dataclass(frozen=True)
class Case:
    family: str
    rule: int
    how: str  # "grid" (a gap on a grid and path), "ulp" (a float beside contact),
    # "normal" (along an inclined edge's normal), "equal" (a hole equal to a void or a core)
    gap: Q | None
    plan: Plan
    holes: tuple[PlanBoundary, ...]


def shift(h: PlanBoundary, off: float) -> PlanBoundary:
    if isinstance(h, PlanCircle):
        return PlanCircle((h.center_mm[0] + off, h.center_mm[1] - off), h.radius_mm)
    return PlanRing(tuple((x + off, y - off) for x, y in h.points_mm))


def axis_cases(rng: random.Random) -> list[Case]:
    grid_paths = [(g, p) for g in GRIDS for p in PATHS if g < 1 or p == "div"]
    out: list[Case] = []
    for f in FAMILIES:
        local = plan_at(f.base, 0.0, f.strip)
        for off in OFFSETS:
            plan = plan_at(f.base, off, f.strip)
            priors = tuple(shift(h, off) for h in f.priors)
            centre = (off, -off)
            limit0 = f.limit(local, f.priors)
            limit = f.limit(plan, priors)
            across_base = centre[1 - f.axis]
            for kind, size in f.shapes:
                lead = Q(size) if kind == "circle" else Q(0)  # a circle is placed by its centre
                for gap in GAPS:
                    for grid, path in rng.sample(grid_paths, PATHS_PER_CASE):
                        near = placed(limit0 + f.side * (gap + lead), grid, path, centre[f.axis])
                        across = placed(f.across, grid, path, across_base)
                        hole = build(kind, size, f.axis, f.side, near, across)
                        out.append(Case(f.name, f.rule, "grid", gap, plan, (*priors, hole)))
                # The float nearest contact on the stored floats, and its two neighbours.
                contact = limit + f.side * lead
                nearest = float(contact)
                across = across_base + float(f.across)
                for near in (math.nextafter(nearest, -math.inf), nearest,
                             math.nextafter(nearest, math.inf)):  # fmt: skip
                    hole = build(kind, size, f.axis, f.side, near, across)
                    out.append(Case(f.name, f.rule, "ulp", None, plan, (*priors, hole)))
    return out


def normal_cases() -> list[Case]:
    out: list[Case] = []
    for f in NORMAL_FAMILIES:
        for off in OFFSETS:
            plan = plan_at(f.base, off, f.strip)
            (ax, ay), (bx, by) = f.edge(plan)
            length = math.hypot(bx - ax, by - ay)
            nx, ny = (by - ay) / length, -(bx - ax) / length  # outward for a CCW ring
            tx, ty = -ny, nx
            fx, fy = ax + f.tau * (bx - ax), ay + f.tau * (by - ay)
            for kind, size in f.shapes:
                for gap in (*GAPS, None):
                    g = 0.0 if gap is None else float(gap)
                    d = f.offset + f.side * g  # the near point, from the edge along the normal
                    if kind == "circle":
                        c = d + f.side * size
                        hole: PlanBoundary = PlanCircle((fx + c * nx, fy + c * ny), size)
                    else:
                        steps = (d, d + f.side * size, d + f.side * 2 * size, d + f.side * size)
                        lat = (0.0, -size, 0.0, size)
                        hole = PlanRing(
                            tuple(
                                (fx + s * nx + w * tx, fy + s * ny + w * ty)
                                for s, w in zip(steps, lat, strict=True)
                            )
                        )
                    out.append(Case(f.name, f.rule, "normal", gap, plan, (hole,)))
    return out


@dataclass(frozen=True)
class Judged:
    """A case and the truth about it: its verdict, and whether its hole passes the family's
    rule (`clear`, a positive clearance) and every rule (`clear_all`) on the stored floats."""

    case: Case
    truth: tuple[int, int] | None
    clear: bool
    clear_all: bool


def equal_cases() -> list[Case]:
    """A hole equal to `rect_hollow`'s void (R2) and to a CFT core (R1), at every offset."""
    out: list[Case] = []
    for off in OFFSETS:
        rh = plan_at("rh", off)
        out.append(Case("rh-void-equal", 2, "equal", None, rh, (rh.faces[0].holes[0],)))
        for base in ("cr", "ct"):
            cft = plan_at(base, off)
            out.append(Case(f"{base}-core-equal", 1, "equal", None, cft, (cft.faces[0].boundary,)))
    return out


@cache
def fuzz() -> tuple[Judged, ...]:
    """Every case once, judged by the truth."""
    cases = axis_cases(random.Random(SEED)) + normal_cases() + equal_cases()
    seen: set[tuple[str, int, tuple[PlanBoundary, ...]]] = set()
    truths: dict[int, Truth] = {}
    out: list[Judged] = []
    for case in cases:
        key = (case.family, id(case.plan), case.holes)
        if key in seen:
            continue
        seen.add(key)
        truth = truths.setdefault(id(case.plan), Truth(case.plan))
        cores = [shape(h) for h in case.holes]
        # Every rule on every hole, so the verdict and the clearances come from one pass.
        passes = [[truth.passes(r, cores, k) for r in range(1, 8)] for k in range(len(cores))]
        first = next(
            ((k, r + 1) for k, row in enumerate(passes) for r, ok in enumerate(row) if not ok),
            None,
        )
        last = passes[-1]
        out.append(Judged(case, first, last[case.rule - 1], all(last)))
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
            bad.append(f"{c.family} {c.how} gap={c.gap}: got {got}, truth {j.truth}")
    return bad


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
    hows = ("grid", "ulp", "normal", "equal")
    report = "\n".join(
        f"R{r}: refused {sum(refused[(r, h)] for h in hows)}, "
        f"accepted {sum(accepted[(r, h)] for h in hows)}; "
        + ", ".join(f"{h} {refused[(r, h)]}/{accepted[(r, h)]}" for h in hows)
        for r in range(1, 8)
    )
    print(f"\n{len(judged)} cases (refused/accepted by how they were built)\n{report}")
    for r in range(1, 8):
        both = sum(refused[(r, h)] for h in hows) and sum(accepted[(r, h)] for h in hows)
        assert both, f"R{r} does not show both verdicts\n{report}"


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
    spike = [(0.0, 0.0), (2.0, 0.0), (1.0, 0.0), (1.0, 1.0)]
    assert exact_simplicity_fault(spike) == "edges 0 and 1 overlap"
    assert exact_twice_area([(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]) == 1


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
