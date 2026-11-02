"""The CFT core-cover exemption on rings (ADR 0039 Errata 9.2, ADR 0040 Errata 11, C4-S2).

A concrete core lying in a steel tube's hole needs no cover guide. On rings that rests on
`regions.curve_within`, whose segment probes used to end at `a + 1.0 * (b - a)`: at fractional
coordinates that rounds past the corner, so a core equal to the hole warned
`face-without-cover-guide`. The oracle is two-sided (lesson apeSection#53), the C4 record §6
fuzz: grids of 0.01, 0.1, 1 and 5 mm, offsets 0, 0.1, 1234.5 and 40000.3, and three ways to
compute a coordinate from a grid index. Truth is `fractions.Fraction` on the stored floats.

Rings are built through a `Plan` and the materialiser, which gives every vertex a fresh
point: `PointAt` merges points within 1 mm and would hide a one-step overhang.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from fractions import Fraction

import pytest

from apeCAD.draft.state import DraftState
from apeCAD.draft.templates import materialise
from apeCAD.section.geometry import Point2
from apeCAD.section.lint import lint_section_v2
from apeCAD.section.regions import segment_probes
from apeCAD.section.templates.plan import Plan, PlanCircle, PlanFace, PlanRing

GRIDS = (0.01, 0.1, 1.0, 5.0)
OFFSETS = (0.0, 0.1, 1234.5, 40000.3)
REPEATS = 50
"""Boxes per grid, offset and path; with six kinds each, 14 400 cases in all."""
Path = Callable[[float, int, float], float]


def _times(offset: float, k: int, g: float) -> float:
    return offset + k * g


def _divided(offset: float, k: int, g: float) -> float:
    steps = round(1.0 / g)
    return offset + (k / steps if steps >= 1 else k * g)


def _rounded(offset: float, k: int, g: float) -> float:
    return round(offset + k * g, 6)


PATHS: dict[str, Path] = {"k*g": _times, "k/round(1/g)": _divided, "round(k*g,6)": _rounded}
Box = tuple[float, float, float, float]  # x0, y0, x1, y1


def _ccw(box: Box) -> tuple[Point2, ...]:
    x0, y0, x1, y1 = box
    return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))


def _lint_codes(core: Box, hole: Box, outer: Box) -> set[str]:
    plan = Plan(
        faces=(
            PlanFace("concrete", "C50", PlanRing(_ccw(core))),
            PlanFace(
                "steel", "S355", PlanRing(_ccw(outer)), holes=(PlanRing(_ccw(hole)[::-1]),)
            ),
        )
    )
    state = DraftState()
    materialise(state, plan, (), "a CFT fuzz plan")
    return {w.code for w in lint_section_v2(state.entities)}


def _within(core: Box, hole: Box) -> bool:
    """The truth, in rationals on the stored floats: the core box lies in the hole box."""
    c, h = [Fraction(v) for v in core], [Fraction(v) for v in hole]
    return h[0] <= c[0] and h[1] <= c[1] and c[2] <= h[2] and c[3] <= h[3]


def _cases() -> list[tuple[str, Box, Box, Box]]:
    """(kind, core, hole, outer) over every grid, offset and path; seeded, so repeatable."""
    rng = random.Random(5353)
    out: list[tuple[str, Box, Box, Box]] = []
    for g in GRIDS:
        for offset in OFFSETS:
            for name, path in PATHS.items():
                for _ in range(REPEATS):
                    i0, j0 = rng.randint(-500, 500), rng.randint(-500, 500)
                    i1, j1 = i0 + rng.randint(20, 400), j0 + rng.randint(20, 400)

                    def box(a: int, b: int, c: int, d: int, p: Path = path) -> Box:
                        return (p(offset, a, g), p(offset, b, g), p(offset, c, g), p(offset, d, g))

                    hole = box(i0, j0, i1, j1)
                    wall = 10 * max(g, 1.0)
                    outer = (hole[0] - wall, hole[1] - wall, hole[2] + wall, hole[3] + wall)
                    out.append((f"equal {name}", hole, hole, outer))
                    out.append((f"inset {name}", box(i0 + 1, j0 + 1, i1 - 1, j1 - 1), hole, outer))
                    out.append((f"inset-x {name}", box(i0 + 1, j0, i1, j1), hole, outer))
                    out.append((f"over-x {name}", box(i0 - 1, j0, i1, j1), hole, outer))
                    out.append((f"over-y {name}", box(i0, j0, i1, j1 + 1), hole, outer))
                    other = PATHS[rng.choice([n for n in PATHS if n != name])]
                    cross = (other(offset, i0, g), other(offset, j0, g),
                             other(offset, i1, g), other(offset, j1, g))  # fmt: skip
                    out.append((f"cross-path {name}", cross, hole, outer))
    return out


CASES = _cases()


def test_the_fuzz_covers_every_grid_offset_and_path() -> None:
    assert len(CASES) == len(GRIDS) * len(OFFSETS) * len(PATHS) * REPEATS * 6
    kinds = {kind.split()[0] for kind, *_ in CASES}
    assert kinds == {"equal", "inset", "inset-x", "over-x", "over-y", "cross-path"}


def test_the_cft_core_exemption_is_exact_both_ways() -> None:
    """No false positive and no false negative, against the rationals."""
    false_pos: list[str] = []
    false_neg: list[str] = []
    for kind, core, hole, outer in CASES:
        warns = "face-without-cover-guide" in _lint_codes(core, hole, outer)
        within = _within(core, hole)
        if kind.startswith(("equal", "inset")):
            assert within, (kind, core, hole)  # the construction itself
        if kind.startswith("over"):
            assert not within, (kind, core, hole)
        if warns and within:
            false_pos.append(f"{kind}: core {core} hole {hole}")
        if not warns and not within:
            false_neg.append(f"{kind}: core {core} hole {hole}")
    assert false_pos == [], f"{len(false_pos)} false positives, first {false_pos[:3]}"
    assert false_neg == [], f"{len(false_neg)} false negatives, first {false_neg[:3]}"


def test_the_record_sample_lints_clean() -> None:
    """C4 record §1's sample: centre (-18.73, 15.15), 246.44 x 593.78, t 14.09."""
    cx, cy, b, h, t = -18.73, 15.15, 246.44, 593.78, 14.09
    outer = (cx - b / 2, cy - h / 2, cx + b / 2, cy + h / 2)
    hole = (outer[0] + t, outer[1] + t, outer[2] - t, outer[3] - t)
    assert _lint_codes(hole, hole, outer) == set()


def test_a_circle_core_in_its_circle_hole_still_lints_clean() -> None:
    plan = Plan(
        faces=(
            PlanFace("concrete", "C50", PlanCircle((0.1, 1234.5), 190.37)),
            PlanFace(
                "steel", "S355", PlanCircle((0.1, 1234.5), 200.0),
                holes=(PlanCircle((0.1, 1234.5), 190.37),),
            ),
        )
    )  # fmt: skip
    state = DraftState()
    materialise(state, plan, (), "a circle CFT")
    assert lint_section_v2(state.entities) == ()


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ((0.1, 0.2), (0.7, 0.2)),
        ((40000.3, 1234.5), (40000.3, 1234.51)),
        ((-18.73, 15.15), (227.71, 608.93)),
    ],
)
def test_segment_probes_end_exactly_at_both_ends(a: Point2, b: Point2) -> None:
    ring = ((-1e5, -1e5), (1e5, -1e5), (1e5, 1e5), (-1e5, 1e5))
    probes = segment_probes(a, b, ring)
    assert probes[0] == a and probes[1] == b  # identical floats, not a + 1.0 * (b - a)
