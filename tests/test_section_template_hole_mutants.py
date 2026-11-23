"""The break-once table of the hole rules (C9-2a review rounds 1 and 2, apeCAD #74).

Each row is one mutant class of `section/templates/hole_rules.py` that a review found: the
source edit that makes it, and a case that kills it. A case is a plan and holes (or a ring,
for the exact ring predicates of 16.1) on which the product agrees with the truth of
`tests/_hole_rules_truth.py` and the mutant does not. The mutant is built in-process from the
module's source text; no file is edited. A row whose edit no longer applies fails by name, so
a change to the module re-pins its rows. A new mutant class must add a row.

A row marked `fuzz` must also die under the seeded generator of
`test_section_template_hole_rules.py`. The others need a plan no template draws or a ring of
its own, and say so; the simplicity fuzz there kills the ring rows too.

The reviews' other mutants were found equivalent; the PR body argues each in one line.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from types import ModuleType

import pytest

from _hole_rules_truth import Truth, fault, twice_area
from apeCAD.errors import DocumentError
from apeCAD.section.templates import hole_rules
from apeCAD.section.templates.plan import (
    Plan,
    PlanBar,
    PlanBoundary,
    PlanCircle,
    PlanCircularTie,
    PlanCrosstie,
    PlanFace,
    PlanHoop,
    PlanRing,
)
from test_section_template_hole_rules import NO_STEEL, Judged, fuzz, plan_at

XY = tuple[float, float]


@cache
def mutant(edits: tuple[tuple[str, str], ...]) -> ModuleType:
    """`hole_rules` with `edits` applied to its source, as a fresh module."""
    source = Path(hole_rules.__file__).read_text(encoding="utf-8")
    for old, new in edits:
        assert source.count(old) == 1, f"the edit no longer applies; re-pin the row: {old!r}"
        source = source.replace(old, new)
    name = f"{hole_rules.__name__}_mutant_{len(MUTANTS)}"
    module = ModuleType(name)
    module.__file__ = hole_rules.__file__
    sys.modules[name] = module  # dataclasses look their module up while the source runs
    exec(compile(source, hole_rules.__file__, "exec"), module.__dict__)
    MUTANTS.append(name)
    return module


MUTANTS: list[str] = []


# --- cases ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Holes:
    """Holes on a plan: the verdict is (index, rule) of the first clash, or a refusal."""

    plan: Callable[[], Plan]
    holes: tuple[PlanBoundary, ...]
    refusal: str | None = None  # the product refuses the plan by this message

    def expected(self) -> object:
        if self.refusal is not None:
            return ("refused", self.refusal)
        return Truth(self.plan()).verdict(self.holes)

    def run(self, module: ModuleType) -> object:
        try:
            clash = module.first_clash(self.plan(), self.holes)
        except DocumentError as exc:
            return ("refused", str(exc))
        return None if clash is None else (clash.index, clash.rule)


@dataclass(frozen=True)
class Ring:
    """A ring for the exact ring predicates: its first fault, by name, and its twice-area."""

    ring: tuple[XY, ...]

    def expected(self) -> object:
        return (fault(self.ring), twice_area(self.ring))

    def run(self, module: ModuleType) -> object:
        return (module.exact_simplicity_fault(self.ring), module.exact_twice_area(self.ring))


def square(cx: float, cy: float, half: float) -> PlanRing:
    lo_x, lo_y, hi_x, hi_y = cx - half, cy - half, cx + half, cy + half
    return PlanRing(((lo_x, lo_y), (hi_x, lo_y), (hi_x, hi_y), (lo_x, hi_y)))


def ring(*points: XY) -> PlanRing:
    return PlanRing(tuple(points))


def at(base: str, strip: tuple[str, ...] = ()) -> Callable[[], Plan]:
    return lambda: plan_at(base, 0.0, strip)


def hand(**parts: object) -> Callable[[], Plan]:
    """A plan no template draws: a 400 mm square face and the given parts."""
    face = PlanFace("concrete", "C30", square(0.0, 0.0, 200.0))
    return lambda: Plan(faces=(face,), **parts)  # type: ignore[arg-type]


# A Ø20 bar at the origin; Ø8 bars under a Ø10 crosstie (its ends reach past the bars); a
# spiral whose inner face has a negative radius; a hoop on three collinear bars.
BAR = hand(bars=(PlanBar(0.0, 0.0, "Ø20", 20.0),))
THIN_TIE = hand(
    bars=(PlanBar(0.0, 0.0, "Ø8", 8.0), PlanBar(0.0, 100.0, "Ø8", 8.0)),
    crossties=(PlanCrosstie(0, 1, "Ø10", 10.0, 150.0),),
)
INSIDE_OUT_SPIRAL = hand(
    circular_ties=(PlanCircularTie("spiral", (0.0, 0.0), 4.0, "Ø10", 10.0, 75.0),)
)
FLAT_HOOP = hand(
    bars=tuple(PlanBar(x, 0.0, "Ø20", 20.0) for x in (-100.0, 0.0, 100.0)),
    hoops=(PlanHoop((0, 1, 2), "Ø10", 10.0, 150.0),),
)
NO_COVER = ("cover_guides",)
BARE = ("cover_guides", *NO_STEEL)


@dataclass(frozen=True)
class Row:
    name: str
    what: str
    edits: tuple[tuple[str, str], ...]
    case: Holes | Ring
    fuzz: bool = True


ROWS: tuple[Row, ...] = (
    # --- round 1 ------------------------------------------------------------------------------
    Row("r1_outline_ends", "R3 without the outline's own vertices: t_beam's re-entrant corner",
        (("    return _all_far(h.pts, o, near, gap) and _all_far(_ends(o, near), h, every, gap)",
          "    return _all_far(h.pts, o, near, gap)"),),
        Holes(at("tb", NO_STEEL),
              (ring((110.0, 100.0), (150.0, 140.0), (110.0, 180.0), (70.0, 140.0)),))),
    Row("r1_region_ends", "R6 without the hull's vertices: an edge faces the hull corner",
        (("    return _all_far(h.pts, s, near, gap) and _all_far(_ends(s, near), h, every, gap)",
          "    return _all_far(h.pts, s, near, gap)"),),
        Holes(at("rc", NO_COVER),
              (ring((145.0, 260.0), (165.0, 240.0), (185.0, 260.0), (165.0, 280.0)),))),
    Row("r1_convex_first", "R6's inner band checks the first vertex only",
        (("return all(_poly_d2(v, hull) < s * s for v in h.pts)",
          "return _poly_d2(h.pts[0], hull) < s * s"),),
        Holes(at("rc", NO_COVER),
              (ring((120.0, 100.0), (155.0, 100.0), (155.0, 110.0), (120.0, 110.0)),))),
    Row("r1_depth1", "R6's inner band: a disc of radius in [r_min, r_min + 1) waved through",
        (("        if depth < 0:\n", "        if depth < 1:\n"),),
        Holes(at("rc", NO_COVER), (PlanCircle((139.6, 120.0), 10.5),))),
    # --- round 2: the squared distance to a segment -------------------------------------------
    Row("segd2_along_neg", "behind a segment's start, the line's distance (R4: a hair clear)",
        (("    if along <= 0:", "    if along <= -1:"),),
        Holes(BAR,
              (ring((10.0, 0.03125), (10.0, 20.03125), (30.0, 20.03125), (30.0, 0.03125)),))),
    Row("segd2_ee_plus", "past a segment's end, the line's distance (R4: a hair clear)",
        (("    if along >= ee:", "    if along >= ee + 1:"),),
        Holes(BAR,
              (ring((10.0, -20.03125), (10.0, -0.03125), (30.0, -0.03125), (30.0, -20.03125)),))),
    Row("segd2_a_to_b", "behind a crosstie's start, the distance to its end (R5)",
        (("        return wx * wx + wy * wy\n", "        return _d2(p, b)\n"),),
        Holes(THIN_TIE, (PlanCircle((0.0, -5.0), 0.5),))),
    Row("segd2_b_to_a", "past a crosstie's end, the distance to its start (R5)",
        (("        return _d2(p, b)\n    across", "        return _d2(p, a)\n    across"),),
        Holes(THIN_TIE, (PlanCircle((0.0, 105.0), 0.5),))),
    # --- R5: a crosstie against a ring hole ---------------------------------------------------
    Row("cs_ab_drop", "R5 without the tie's ends against the hole's edges",
        (("    return _all_far(_ends(h, near), seg, (0,), gap) and _all_far((a, b), h, near, gap)",
          "    return _all_far(_ends(h, near), seg, (0,), gap)"),),
        Holes(THIN_TIE, (ring((-10.0, -4.5), (10.0, -4.5), (10.0, -20.0), (-10.0, -20.0)),))),
    Row("cs_ab_a_only", "R5 checks the tie's start only: the hole is past its end",
        (("and _all_far((a, b), h, near, gap)", "and _all_far((a,), h, near, gap)"),),
        Holes(THIN_TIE, (ring((-10.0, 104.5), (10.0, 104.5), (10.0, 120.0), (-10.0, 120.0)),))),
    Row("cs_ab_b_only", "R5 checks the tie's end only: the hole is behind its start",
        (("and _all_far((a, b), h, near, gap)", "and _all_far((b,), h, near, gap)"),),
        Holes(THIN_TIE, (ring((-10.0, -4.5), (10.0, -4.5), (10.0, -20.0), (-10.0, -20.0)),))),
    Row("cs_touch_drop", "R5 without the crossing test: a duct straddles a crosstie",
        (("    if _touches(seg, h, near) or _locate(a, h) >= 0:", "    if _locate(a, h) >= 0:"),),
        Holes(at("rc_all"), (square(70.0, 0.0, 30.0),))),
    # --- touching segments: collinear but apart -----------------------------------------------
    Row("wbox_xonly", "a point beyond a vertical segment, in its x range, taken as on it",
        (("<= max(a[0], b[0]) and min(a[1], b[1]) <= p[1] <= max(a[1], b[1])",
          "<= max(a[0], b[0])"),),
        Holes(at("rh", BARE), (ring((150.0, 210.0), (160.0, 195.0), (170.0, 210.0)),))),
    Row("touch_c1_nobox", "a hole's vertex on the void edge's line, past the corner, as touching",
        (("(d1 == 0 and _within_box(a, c, d))", "(d1 == 0)"),),
        Holes(at("rh", BARE), (ring((150.0, 210.0), (160.0, 195.0), (170.0, 210.0)),))),
    # Only a plan corner whose other edge is slanted lets the edge boxes pass this pair to
    # the exact test; the generator rarely builds one, so the row alone pins it.
    Row("touch_c3_nobox", "a face's corner on a hole edge's line, past it, as touching",
        (("(d3 == 0 and _within_box(c, a, b))", "(d3 == 0)"),),
        Holes(at("pc", BARE),
              (ring((500.0, 300.0), (550.0, 300.0), (550.0, 280.0), (500.0, 280.0)),)),
        fuzz=False),
    # --- where a point lies -------------------------------------------------------------------
    Row("loc_straddle_ge_a", "a ray through a vertex counted twice (half-open on one end only)",
        (("if (float(a[1]) > py) != (float(b[1]) > py):",
          "if (float(a[1]) >= py) != (float(b[1]) > py):"),),
        Holes(at("pc", BARE), (PlanCircle((100.0, 300.0), 5.0),))),
    Row("loc_elif_noy", "a point on a vertical edge's line, beyond it, taken as on the edge",
        (("and y0 <= py <= y1 and _cross(a, b, p) == 0:", "and _cross(a, b, p) == 0:"),),
        Holes(at("tb", NO_STEEL), (PlanCircle((150.0, 200.0), 5.0),))),
    # --- R1, R2, R7: containment ------------------------------------------------------------
    Row("in_loc_drop", "R1 without containment: a ring wholly outside the face",
        (("    return not _touches(h, o, near) and _locate(h.pts[0], o) > 0",
          "    return not _touches(h, o, near)"),),
        Holes(at("rc"), (square(1000.0, 0.0, 20.0),))),
    Row("wp_room_drop", "a disc larger than the round core it is in",
        (("        return room > 0 and _d2(h.c, centre) < room * room",
          "        return _d2(h.c, centre) < room * room"),),
        Holes(at("cr"), (PlanCircle((0.0, 0.0), 200.0),))),
    Row("wp_s_drop", "R7 within a spiral whose inner face has a negative radius",
        (("    return s > 0 and all(_d2(v, centre) < s * s for v in h.pts)",
          "    return all(_d2(v, centre) < s * s for v in h.pts)"),),
        Holes(INSIDE_OUT_SPIRAL, (square(0.0, 0.0, 0.5),)),
        fuzz=False),
    Row("cr_sdisc_nogap", "R3 from a circular own hole without the cover",
        (("        return _clear_point(h, s.c, s.r + gap)",
          "        return _clear_point(h, s.c, s.r)"),),
        Holes(at("disc_void"),
              (ring((100.0, -25.0), (110.0, -25.0), (110.0, -15.0), (100.0, -15.0)),))),
    Row("r2_prev_last_only", "R2 against the last earlier hole only: three holes",
        (("    for j in range(k):\n", "    for j in range(max(k - 1, 0), k):\n"),),
        Holes(at("cr"), (PlanCircle((-50.0, 0.0), 25.0), PlanCircle((60.0, 0.0), 10.0),
                         PlanCircle((-40.0, 0.0), 5.0)))),
    # --- R6 ------------------------------------------------------------------------------------
    Row("wc_depth_drop", "R6's inner band asks a disc below r_min to clear the edges by r_min - r",
        (("        if depth < 0:\n            return True\n",
          "        if False:\n            return True\n"),),
        Holes(at("rc", NO_COVER), (PlanCircle((137.0, 120.0), 5.0),))),
    Row("hull_lt", "a hoop on collinear bars kept, not refused: the hull keeps collinear points",
        (("_cross(part[-2], part[-1], p) <= 0", "_cross(part[-2], part[-1], p) < 0"),),
        Holes(FLAT_HOOP, (PlanCircle((0.0, 150.0), 5.0),),
              refusal="plan hoop 0: its bar centres span no area"),
        fuzz=False),
    # --- the ring predicates: every start and orientation runs in the simplicity fuzz --------
    Row("touch_d1d2_onedir", "a crossing seen one way round: the reversed bow-tie",
        (("if ((d1 > 0 > d2) or (d1 < 0 < d2)) and", "if ((d1 > 0 > d2)) and"),),
        Ring(((0.0, 1.0), (1.0, 0.0), (1.0, 1.0), (0.0, 0.0))), fuzz=False),
    Row("touch_d3d4_onedir", "a crossing seen one way round: the bow-tie",
        (("and ((d3 > 0 > d4) or (d3 < 0 < d4)):", "and ((d3 > 0 > d4)):"),),
        Ring(((0.0, 0.0), (1.0, 1.0), (1.0, 0.0), (0.0, 1.0))), fuzz=False),
    Row("touch_c1", "vertex 1 on the closing edge: named late, as an overlap",
        (("(d1 == 0 and _within_box(a, c, d))", "(False)"),),
        Ring(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (2.0, 0.0))), fuzz=False),
    Row("touch_c2", "vertex 1 on edge 3: named at edge 1, not edge 0",
        (("(d2 == 0 and _within_box(b, c, d))", "(False)"),),
        Ring(((0.5, 1.0), (1.0, 0.0), (1.5, 1.0), (2.0, 0.0), (0.0, 0.0))), fuzz=False),
)  # fmt: skip


@pytest.mark.parametrize("row", ROWS, ids=[r.name for r in ROWS])
def test_each_row_kills_its_mutant(row: Row) -> None:
    expected = row.case.expected()
    assert row.case.run(hole_rules) == expected, f"{row.name}: the product disagrees with the truth"
    got = row.case.run(mutant(row.edits))
    assert got != expected, f"{row.name} ({row.what}) survives its case: {got}"


def kills(module: ModuleType, judged: Sequence[Judged]) -> bool:
    for j in judged:
        try:
            clash = module.first_clash(j.case.plan, j.case.holes)
        except Exception:  # a crash is a kill too
            return True
        if (None if clash is None else (clash.index, clash.rule)) != j.truth:
            return True
    return False


def test_the_generator_kills_every_fuzz_row() -> None:
    judged = fuzz()
    alive = [r.name for r in ROWS if r.fuzz and not kills(mutant(r.edits), judged)]
    assert not alive, f"the generator lets these through: {alive}"


def test_the_rows_are_distinct() -> None:
    names = [r.name for r in ROWS]
    assert len(set(names)) == len(names)
    assert len({r.edits for r in ROWS}) == len(ROWS)
