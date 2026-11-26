"""ADR 0042 oracle (a): the nesting of rings of one role, lesson #53's two-sided fuzz.

Decision 6 nests the rings and circles of one role exactly, with `hole_rules`'s region tests,
and refuses contact. This fuzz pins it against `tests/_dxf_import_truth.py`, which imports no
product geometry, in both directions:

- every pair the truth finds apart is read as two faces, every pair it finds strictly nested
  is read as a face and its hole, and every pair whose boundaries meet is refused as
  `dxf ring-contact`; the counts of each verdict are printed (`pytest -s`) and floored;
- with the exact decision replaced by plain floats (`hole_rules._q = float`), the same fuzz
  disagrees with the truth, so it would catch that regression.

Inputs: gaps of -1, -0.01, 0, +0.01 and +1 mm from each contact, and the nearest floats on
either side of contact; grids of 0.01, 0.1, 1 and 5 mm; offsets of 0, 0.1, 1234.5 and
40000.3 mm; coordinates built as `i/10` and `i*0.1` (and `i/100`, `i*0.01` for the 0.01 grid);
squares, a slanted triangle, circles, a diamond in a circle, and circle pairs. It runs on the
pure core, without ezdxf.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from fractions import Fraction

import pytest

from _dxf_import_truth import Region, relation
from apeCAD.section.dxf_options import DxfRefusedError
from apeCAD.section.dxf_seed import RawEntity, relate, seed_from_entities
from apeCAD.section.templates import hole_rules
from apeCAD.section.templates.plan import PlanCircle, PlanRing

Q = Fraction
OFFSETS = (Q(0), Q(1, 10), Q(12345, 10), Q(400003, 10))
GRIDS = (Q(1, 100), Q(1, 10), Q(1), Q(5))
GAPS = (Q(-1), Q(-1, 100), Q(0), Q(1, 100), Q(1))
BUILDS: dict[str, Callable[[Fraction], float]] = {
    "i/10": lambda v: int(v * 10) / 10,
    "i*0.1": lambda v: int(v * 10) * 0.1,
    "i/100": lambda v: int(v * 100) / 100,
    "i*0.01": lambda v: int(v * 100) * 0.01,
}
"""Each turns an exact decimal coordinate into a float, as a drawing program might."""

Pt = tuple[float, float]


@dataclass(frozen=True)
class Case:
    name: str
    a: Region
    b: Region


def _builds(*values: Fraction) -> list[str]:
    """The builds that represent every value exactly as a decimal of their precision."""
    tenths = all((v * 10).denominator == 1 for v in values)
    return [k for k in BUILDS if tenths or k in ("i/100", "i*0.01")]


def _ring(build: str, *xy: Fraction) -> Region:
    f = BUILDS[build]
    return ("ring", tuple((f(xy[k]), f(xy[k + 1])) for k in range(0, len(xy), 2)))


def _circle(build: str, cx: Fraction, cy: Fraction, r: Fraction) -> Region:
    f = BUILDS[build]
    return ("circle", ((f(cx), f(cy)), f(r)))


def _rect(o: Fraction, x0: Fraction, y0: Fraction, x1: Fraction, y1: Fraction) -> list[Fraction]:
    return [o + x0, o + y0, o + x1, o + y0, o + x1, o + y1, o + x0, o + y1]


def _scenarios(
    o: Fraction, g: Fraction, gap: Fraction
) -> Iterator[tuple[str, list[str], Region, Region]]:
    """Pairs at `gap` from contact: (name, builds, a, b). Sizes are multiples of the grid."""
    w, h, r = 40 * g, 30 * g, 20 * g
    a_rect = _rect(o, Q(0), Q(0), w, h)
    side = _rect(o, w + gap, h / 3, w + gap + w / 2, h)
    for build in _builds(*a_rect, *side):
        yield "side", [build], _ring(build, *a_rect), _ring(build, *side)
    if gap < 3 * w / 4:
        inner = _rect(o, w / 4, h / 4, w - gap, 3 * h / 4)
        for build in _builds(*a_rect, *inner):
            yield "inner", [build], _ring(build, *a_rect), _ring(build, *inner)
    # A slanted hypotenuse from (o + w, o) to (o, o + h); a square's corner at its midpoint,
    # moved by `gap` along x: outward (disjoint side) or inward (nested side).
    tri = [o, o, o + w, o, o, o + h]
    mx, my = o + w / 2, o + h / 2
    s = g * 4
    out = [mx + gap, my, mx + gap + s, my, mx + gap + s, my + s, mx + gap, my + s]
    inn = [mx - gap, my, mx - gap - s, my, mx - gap - s, my - s, mx - gap, my - s]
    for build in _builds(*tri, *out):
        yield "slant-out", [build], _ring(build, *tri), _ring(build, *out)
    if gap < w / 4:
        for build in _builds(*tri, *inn):
            yield "slant-in", [build], _ring(build, *tri), _ring(build, *inn)
    cx, cy = o + r, o + r
    beside = _rect(o, 2 * r + gap, Q(0), 2 * r + gap + w / 2, h)
    for build in _builds(cx, cy, r, *beside):
        yield "circle-side", [build], _circle(build, cx, cy, r), _ring(build, *beside)
    if gap < r / 2:
        in_rect = (o + w / 2, o + h / 2, h / 2 - gap)  # touches the rect's top and bottom
        for build in _builds(*in_rect, *a_rect):
            disc = _circle(build, *in_rect)
            yield "circle-in-rect", [build], disc, _ring(build, *a_rect)
        k = r - gap
        diamond = [cx + k, cy, cx, cy + k, cx - k, cy, cx, cy - k]
        for build in _builds(cx, cy, r, *diamond):
            yield "diamond-in-circle", [build], _ring(build, *diamond), _circle(build, cx, cy, r)
        r2 = r / 2
        for build in _builds(cx, cy, r, r2 + gap):
            inner_c = _circle(build, cx + r2 - gap, cy, r2)
            yield "circle-in-circle", [build], inner_c, _circle(build, cx, cy, r)
    for build in _builds(cx, cy, r, gap):
        outer = _circle(build, cx + 2 * r + gap, cy, r)
        yield "circle-circle", [build], _circle(build, cx, cy, r), outer


def _nudged(region: Region, toward: float) -> Region:
    """Every coordinate of `region` (not a radius) moved one float along x towards `toward`."""
    kind, data = region
    if kind == "ring":
        pts: tuple[Pt, ...] = data
        return ("ring", tuple((math.nextafter(x, toward), y) for x, y in pts))
    (x, y), r = data
    return ("circle", ((math.nextafter(x, toward), y), r))


def cases() -> list[Case]:
    out: list[Case] = []
    for o in OFFSETS:
        for g in GRIDS:
            for gap in GAPS:
                for name, builds, a, b in _scenarios(o, g, gap):
                    label = f"{name} o={float(o)} g={float(g)} gap={float(gap)} {builds[0]}"
                    out.append(Case(label, a, b))
                    if gap == 0:  # the nearest floats on either side of contact
                        out.append(Case(label + " b+ulp", a, _nudged(b, math.inf)))
                        out.append(Case(label + " b-ulp", a, _nudged(b, -math.inf)))
    return out


CASES = cases()


def _plan(region: Region) -> PlanRing | PlanCircle:
    kind, data = region
    if kind == "ring":
        return PlanRing(data)
    centre, radius = data
    return PlanCircle(centre, radius)


def _simple(region: Region) -> bool:
    return (
        region[0] == "circle" or hole_rules.exact_simplicity_fault(_plan(region).points_mm) is None
    )


def _entity(region: Region, handle: str) -> RawEntity:
    kind, data = region
    if kind == "ring":
        return RawEntity(
            "LWPOLYLINE",
            "CONCRETE-CUT",
            handle,
            points=data,
            closed=True,
            bulges=(0.0,) * len(data),
        )
    centre, radius = data
    return RawEntity("CIRCLE", "CONCRETE-CUT", handle, center=centre, radius=radius)


def _read_verdict(case: Case) -> str:
    """What the import makes of the pair: "disjoint" (two faces), "nested" (a face and its
    hole), or "contact" (refused as ring-contact)."""
    try:
        built = seed_from_entities([_entity(case.a, "A"), _entity(case.b, "B")], insunits=4)
    except DxfRefusedError as exc:
        assert exc.reason == "ring-contact", f"{case.name}: refused as {exc}"
        return "contact"
    faces = built.seed["section"]["faces"]
    return "disjoint" if len(faces) == 2 else "nested"


def _truth(case: Case) -> str:
    verdict = relation(case.a, case.b)
    return "nested" if verdict in ("inside", "contains") else verdict


def _product(case: Case) -> str:
    return relate(hole_rules.region(_plan(case.a), "a"), hole_rules.region(_plan(case.b), "b"))


def test_the_fuzz_is_well_formed() -> None:
    assert len(CASES) > 2000
    assert all(_simple(c.a) and _simple(c.b) for c in CASES)


def test_nesting_matches_the_exact_truth_both_ways() -> None:
    tally: Counter[str] = Counter()
    for case in CASES:
        truth = relation(case.a, case.b)
        assert _product(case) == truth, case.name
        assert relation(case.b, case.a) == {"inside": "contains", "contains": "inside"}.get(
            truth, truth
        ), case.name
        expected = "nested" if truth in ("inside", "contains") else truth
        assert _read_verdict(case) == expected, case.name
        tally[expected] += 1
    print(f"\nADR 0042 nesting fuzz: {len(CASES)} pairs; {dict(sorted(tally.items()))}")
    # Both directions hold many rows: apart and nested are read, contact is refused.
    assert tally["contact"] >= 300 and tally["disjoint"] >= 300 and tally["nested"] >= 300


def test_plain_floats_disagree_with_the_truth(monkeypatch: pytest.MonkeyPatch) -> None:
    """With the stored floats compared as floats, not `Fraction`s, the fuzz catches it."""
    monkeypatch.setattr(hole_rules, "_q", float)
    wrong = [case.name for case in CASES if _product(case) != relation(case.a, case.b)]
    print(f"\nwith plain floats, {len(wrong)} of {len(CASES)} pairs disagree; e.g. {wrong[:3]}")
    assert wrong
