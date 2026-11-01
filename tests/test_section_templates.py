"""Section templates as pure functions to a `Plan` (ADR 0040, stage C3-S1, apeSection#48).

Oracles are hand-computed in the C3 decision record §2 and compared at rel 1e-12; bar
positions of `rect_column` and the `t_beam` ring are compared exactly with the v2 fixtures.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Sequence

import pytest

from _section_fixtures_v2 import FIXTURE_DIR, T_RING
from apeCAD.errors import INVALID_ARGUMENT, DocumentError
from apeCAD.section.geometry import Point2, signed_area
from apeCAD.section.templates import TEMPLATES, expand, latest_version
from apeCAD.section.templates.plan import (
    Plan,
    PlanBar,
    PlanCircle,
    PlanCircularTie,
    PlanCoverGuide,
    PlanCrosstie,
    PlanFace,
    PlanHoop,
    PlanRing,
    PlanSteelShape,
    TemplateParamError,
)

REL = 1e-12

RECT_COLUMN: dict[str, object] = {
    "material": "C30", "b": 400, "h": 600, "center_mm": [200, 300], "cover": 40,
    "nx": 3, "ny": 3, "bar": "Ø20", "tie": "Ø10", "tie_spacing": 150, "crossties": "all",
}  # fmt: skip
POLYGON_COLUMN: dict[str, object] = {
    "material": "C30", "ring": [[0, 0], [600, 0], [600, 300], [0, 500]], "cover": 40,
    "bar": "Ø20", "spacing_max": 150, "tie": "Ø10", "tie_spacing": 150,
}  # fmt: skip
RECT_HOLLOW: dict[str, object] = {
    "material": "C30", "b": 600, "h": 800, "t_x": 150, "t_y": 200, "cover": 40,
    "bar": "Ø16", "spacing_max": 200, "tie": "Ø10", "tie_spacing": 150,
}  # fmt: skip
T_BEAM: dict[str, object] = {
    "material": "C30", "bw": 300, "h": 600, "bf": 800, "hf": 150, "center_mm": [0, 300],
    "cover": 30, "bottom": {"n": 3, "bar": "Ø20"}, "top": {"n": 2, "bar": "Ø16"},
    "slab_bars": {"n": 2, "bar": "Ø12"}, "stirrup": "Ø10", "stirrup_spacing": 150,
}  # fmt: skip
ORACLES = {
    "rect_column": RECT_COLUMN,
    "polygon_column": POLYGON_COLUMN,
    "rect_hollow": RECT_HOLLOW,
    "t_beam": T_BEAM,
}


def _ring(plan: Plan, face: int = 0) -> tuple[Point2, ...]:
    boundary = plan.faces[face].boundary
    assert isinstance(boundary, PlanRing)
    return boundary.points_mm


def _moments(ring: Sequence[Point2]) -> tuple[float, float, float]:
    """Signed area and first moments (Sx, Sy) of a ring, by the shoelace formula."""
    a = sx = sy = 0.0
    for i in range(len(ring)):
        (x0, y0), (x1, y1) = ring[i], ring[(i + 1) % len(ring)]
        c = x0 * y1 - x1 * y0
        a += c / 2.0
        sx += (x0 + x1) * c / 6.0
        sy += (y0 + y1) * c / 6.0
    return a, sx, sy


def _area_centroid(plan: Plan) -> tuple[float, float, float]:
    """Net area and centroid of face 0: its ring plus its (clockwise, so negative) holes."""
    rings = [_ring(plan)]
    for hole in plan.faces[0].holes:
        assert isinstance(hole, PlanRing)
        rings.append(hole.points_mm)
    a = sx = sy = 0.0
    for ring in rings:
        da, dsx, dsy = _moments(ring)
        a, sx, sy = a + da, sx + dsx, sy + dsy
    return a, sx / a, sy / a


def _with(base: dict[str, object], **changes: object) -> dict[str, object]:
    out = dict(base)
    for key, value in changes.items():
        if value is _DROP:
            out.pop(key, None)
        else:
            out[key] = value
    return out


_DROP = object()


# --- the oracles (C3 record §2) ---------------------------------------------------------


def test_rect_column_oracle_matches_the_rect_column_ties_fixture() -> None:
    plan = expand("rect_column", RECT_COLUMN)
    a, cx, cy = _area_centroid(plan)
    assert math.isclose(a, 240_000.0, rel_tol=REL)
    assert math.isclose(cx, 200.0, rel_tol=REL) and math.isclose(cy, 300.0, rel_tol=REL)
    fixture = json.loads((FIXTURE_DIR / "rect_column_ties.json").read_text(encoding="utf-8"))
    expected = sorted((b["x_mm"], b["y_mm"]) for b in fixture["section"]["bars"])
    assert sorted(bar.xy for bar in plan.bars) == expected  # exact, not approximate
    assert {x for x, _ in expected} == {60.0, 200.0, 340.0}
    assert {y for _, y in expected} == {60.0, 300.0, 540.0}
    assert all(bar.designation == "Ø20" and bar.diameter_mm == 20.0 for bar in plan.bars)
    (hoop,) = plan.hoops
    assert [plan.bars[i].xy for i in hoop.bars] == [(60, 60), (340, 60), (340, 540), (60, 540)]
    assert (hoop.designation, hoop.diameter_mm, hoop.spacing_mm) == ("Ø10", 10.0, 150.0)
    ties = {frozenset((plan.bars[t.bar_a].xy, plan.bars[t.bar_b].xy)) for t in plan.crossties}
    assert ties == {
        frozenset({(200.0, 60.0), (200.0, 540.0)}),
        frozenset({(340.0, 300.0), (60.0, 300.0)}),
    }
    assert all(t.hooks == "135-135" and t.spacing_mm == 150.0 for t in plan.crossties)
    assert plan.cover_guides == (PlanCoverGuide(0, 40.0, 10.0, 20.0),)
    assert plan.faces[0].role == "concrete" and plan.faces[0].material == "C30"


def test_polygon_column_oracle() -> None:
    plan = expand("polygon_column", POLYGON_COLUMN)
    a, cx, cy = _area_centroid(plan)
    assert math.isclose(a, 240_000.0, rel_tol=REL)
    assert math.isclose(cx, 275.0, rel_tol=REL)
    assert math.isclose(cy, 204.0 + 1.0 / 6.0, rel_tol=REL)
    assert len(plan.bars) == 13  # edges split into 4, 2, 4 and 3 intervals
    (hoop,) = plan.hoops
    corners = [plan.bars[i].xy for i in hoop.bars]
    k = 60.0 * math.sqrt(10.0) / 3.0  # the 1:3 top edge moves down 60 / cos(atan(1/3))
    expected = [(60.0, 60.0), (540.0, 60.0), (540.0, 500.0 - 180.0 - k), (60.0, 500.0 - 20.0 - k)]
    for (x, y), (ex, ey) in zip(corners, expected, strict=True):
        # The corners of an inclined layout snap to the 2**-10 mm grid (ADR 0032).
        assert abs(x - ex) <= 2.0**-10 and abs(y - ey) <= 2.0**-10
    assert math.isclose(expected[2][1], 256.754, abs_tol=5e-4)
    assert math.isclose(expected[3][1], 416.754, abs_tol=5e-4)


def test_polygon_column_counts_bars_per_edge() -> None:
    plan = expand("polygon_column", POLYGON_COLUMN)
    xy = [bar.xy for bar in plan.bars]
    bottom = [p for p in xy if p[1] == 60.0]
    right = [p for p in xy if p[0] == xy[4][0]]
    assert len(bottom) == 5 and len(right) == 3  # 4 and 2 intervals, corners included
    assert len(set(xy)) == 13


def test_rect_hollow_oracle() -> None:
    plan = expand("rect_hollow", RECT_HOLLOW)
    a, cx, cy = _area_centroid(plan)
    assert math.isclose(a, 360_000.0, rel_tol=REL)
    assert math.isclose(cx, 0.0, abs_tol=1e-9) and math.isclose(cy, 0.0, abs_tol=1e-9)
    (hole,) = plan.faces[0].holes
    assert isinstance(hole, PlanRing) and signed_area(hole.points_mm) == -120_000.0  # CW
    assert len(plan.bars) == 26
    outer, inner = plan.hoops
    assert len(outer.bars) == 4 and len(inner.bars) == 4
    assert max(outer.bars) < 14 <= min(inner.bars)  # 14 outer bars, then 12 inner
    assert {plan.bars[i].xy for i in outer.bars} == {(-242, -342), (242, -342), (242, 342),
                                                     (-242, 342)}  # fmt: skip
    assert {plan.bars[i].xy for i in inner.bars} == {(-208, -258), (208, -258), (208, 258),
                                                     (-208, 258)}  # fmt: skip
    assert plan.crossties == ()


def test_t_beam_oracle_ring_is_the_fixture_ring() -> None:
    plan = expand("t_beam", T_BEAM)
    a, cx, cy = _area_centroid(plan)
    assert math.isclose(a, 255_000.0, rel_tol=REL)
    assert math.isclose(cx, 0.0, abs_tol=1e-9)
    # (300 x 450 x 225 + 800 x 150 x 525) / 255 000 = 93 375 000 / 255 000
    assert math.isclose(cy, 93_375_000.0 / 255_000.0, rel_tol=REL)
    assert math.isclose(cy, 366.176, abs_tol=5e-4)
    assert list(_ring(plan)) == [(float(x), float(y)) for x, y in T_RING]
    assert [bar.xy for bar in plan.bars] == [
        (-100, 50), (0, 50), (100, 50), (-102, 552), (102, 552),
        (-337.5, 564), (-212.5, 564), (212.5, 564), (337.5, 564),
    ]  # fmt: skip
    (stirrup,) = plan.hoops
    assert {plan.bars[i].xy for i in stirrup.bars} == {(-100, 50), (100, 50), (102, 552),
                                                       (-102, 552)}  # fmt: skip
    assert (stirrup.designation, stirrup.spacing_mm) == ("Ø10", 150.0)


@pytest.mark.parametrize("template", sorted(ORACLES))
def test_plans_are_deterministic(template: str) -> None:
    params = ORACLES[template]
    first = expand(template, params)
    again = expand(template, dict(reversed(list(params.items()))))
    assert first == again and hash(first) == hash(again)
    assert first == expand(template, params, version=1)


@pytest.mark.parametrize("template", sorted(ORACLES))
def test_every_hoop_is_the_strict_ccw_hull_of_its_bars(template: str) -> None:
    plan = expand(template, ORACLES[template])
    for hoop in plan.hoops:
        assert signed_area([plan.bars[i].xy for i in hoop.bars]) > 0.0


# --- materials (owner ruling Q1) and layouts ---------------------------------------------


@pytest.mark.parametrize("template", sorted(ORACLES))
def test_material_and_bar_material(template: str) -> None:
    plain = expand(template, ORACLES[template])
    assert all(bar.material is None for bar in plain.bars)  # the draft's default
    named = expand(template, _with(ORACLES[template], material="C40", bar_material="A630"))
    assert named.faces[0].material == "C40"
    assert {bar.material for bar in named.bars} == {"A630"}
    with pytest.raises(TemplateParamError, match="material: required"):
        expand(template, _with(ORACLES[template], material=_DROP))


def test_rect_column_crosstie_patterns_and_bar_count() -> None:
    base = _with(RECT_COLUMN, b=600, h=600, center_mm=[300, 300], nx=5, ny=4)
    assert len(expand("rect_column", base).bars) == 2 * 5 + 2 * 4 - 4
    counts = {
        pattern: len(expand("rect_column", _with(base, crossties=pattern)).crossties)
        for pattern in ("none", "all", "alternate")
    }
    # Interior columns 1..3 and rows 1..2; `alternate` keeps the even ones (column 2, row 2).
    assert counts == {"none": 0, "all": 3 + 2, "alternate": 1 + 1}
    alt = expand("rect_column", _with(base, crossties="alternate"))
    xs = sorted({alt.bars[t.bar_a].xy[0] for t in alt.crossties if alt.bars[t.bar_a].xy[1] == 60})
    assert xs == [300.0]  # the middle column of five, at 60 + 2 x 120


def test_rect_column_corner_bar() -> None:
    plan = expand("rect_column", _with(RECT_COLUMN, corner_bar="Ø25"))
    corners = [plan.bars[i] for i in (0, 2, 4, 6)]
    assert {b.designation for b in corners} == {"Ø25"}
    assert corners[0].xy == (62.5, 62.5)  # 40 + 10 + 12.5
    assert plan.bars[1].xy == (200.0, 60.0)  # a Ø20 rests on the tie at 40 + 10 + 10


def test_t_beam_without_slab_bars() -> None:
    plan = expand("t_beam", _with(T_BEAM, slab_bars=_DROP))
    assert len(plan.bars) == 5


def test_polygon_column_accepts_a_clockwise_ring() -> None:
    ring = POLYGON_COLUMN["ring"]
    assert isinstance(ring, list)
    cw = expand("polygon_column", _with(POLYGON_COLUMN, ring=list(reversed(ring))))
    assert signed_area(_ring(cw)) > 0.0
    assert sorted(b.xy for b in cw.bars) == sorted(
        b.xy for b in expand("polygon_column", POLYGON_COLUMN).bars
    )


# --- refusals, each by name -------------------------------------------------------------

REFUSALS: list[tuple[str, dict[str, object], str]] = [
    ("rect_column", {"material": ""}, "material"),
    ("rect_column", {"material": None}, "material"),
    ("rect_column", {"bar_material": 7}, "bar_material"),
    ("rect_column", {"b": _DROP}, "b"),
    ("rect_column", {"b": -400}, "b"),
    ("rect_column", {"h": "600"}, "h"),
    ("rect_column", {"cover": 0}, "cover"),
    ("rect_column", {"cover": math.inf}, "cover"),
    ("rect_column", {"nx": 1}, "nx"),
    ("rect_column", {"ny": 3.0}, "ny"),
    ("rect_column", {"ny": True}, "ny"),
    ("rect_column", {"bar": "#5"}, "bar"),
    ("rect_column", {"corner_bar": "Ø21"}, "corner_bar"),
    ("rect_column", {"tie": "Ø10.0"}, "tie"),
    ("rect_column", {"tie_spacing": 0}, "tie_spacing"),
    ("rect_column", {"crossties": "every"}, "crossties"),
    ("rect_column", {"center_mm": [1, 2, 3]}, "center_mm"),
    ("rect_column", {"center_mm": "0,0"}, "center_mm"),
    ("rect_column", {"center_mm": [2.0**21, 0]}, "center_mm"),
    ("rect_column", {"b": 120}, "b"),  # 120 <= 2 x 60: the inset collapses
    ("rect_column", {"h": 100, "b": 600}, "h"),
    ("rect_column", {"nx": 600, "b": 100_000}, "nx"),  # 2 x 600 + 2 = 1202 bars > 1000
    # Review of #56. Finding 1: the cap is checked from the params, before anything is built.
    ("rect_column", {"nx": 10**9}, "nx"),
    ("rect_column", {"ny": 10**9}, "ny"),
    # Finding 2: overlapping bars (gap < (da + db) / 2), named by what sets their spacing.
    ("rect_column", {"b": 121}, "b"),  # the bottom corners sit 1 mm apart
    ("rect_column", {"nx": 100}, "nx"),  # 280 / 99 = 2.8 mm between Ø20 bars
    ("rect_column", {"ny": 30}, "ny"),
    ("rect_column", {"h": 135, "b": 600}, "h"),  # corners 15 mm apart, under Ø20
    ("rect_column", {"spacing": 150}, "spacing"),
    ("polygon_column", {"ring": [[0, 0], [600, 0]]}, "ring"),
    ("polygon_column", {"ring": [[0, 0], [600, 0], [0, 500], [600, 500]]}, "ring"),
    ("polygon_column", {"ring": [[0, 0], [600, 0], [300, 100], [600, 500], [0, 500]]}, "ring"),
    ("polygon_column", {"ring": [[0, 0], [300, 0], [600, 0], [600, 500], [0, 500]]}, "ring"),
    ("polygon_column", {"ring": [[0, 0], [100, 0], [0, 100]]}, "ring"),  # inset collapses
    ("polygon_column", {"ring": [[0, 0], "x", [0, 100]]}, "ring[1]"),
    ("polygon_column", {"ring": "square"}, "ring"),
    ("polygon_column", {"spacing_max": -1}, "spacing_max"),
    ("polygon_column", {"center_mm": [0, 0]}, "center_mm"),
    ("polygon_column", {"ring": [[0, 0], [1000, 0], [1000, 130], [0, 121]]}, "ring"),  # sliver
    ("polygon_column", {"ring": [[0, 0], [2000, 0], [0, 150]]}, "ring"),  # acute corner
    ("polygon_column", {"spacing_max": 5}, "spacing_max"),  # neighbours 5 mm apart
    ("polygon_column", {"spacing_max": 0.1}, "spacing_max"),  # finding 4: > 1000 on an edge
    ("polygon_column", {"ring": [[0, 0], [2.0**21, 0], [0, 500]]}, "ring"),  # extent
    ("rect_hollow", {"t_x": 116}, "t_x"),  # t - 2d = 0: the bar rings coincide
    ("rect_hollow", {"t_x": 117, "t_y": 117}, "t_x"),  # t - 2d = 1 mm, under Ø16
    ("rect_hollow", {"t_y": 131}, "t_y"),  # t - 2d = 15 mm, under Ø16
    ("rect_hollow", {"spacing_max": 10}, "spacing_max"),  # 484 / 49 = 9.9 mm, under Ø16
    ("rect_hollow", {"spacing_max": 0.1}, "spacing_max"),  # finding 4: > 1000 on an edge
    ("rect_hollow", {"center_mm": [2.0**21, 0]}, "center_mm"),
    ("rect_hollow", {"t_y": 100}, "t_y"),
    ("rect_hollow", {"t_x": 300}, "t_x"),  # two 300 mm walls fill b = 600
    ("rect_hollow", {"spacing_max": _DROP}, "spacing_max"),
    ("t_beam", {"bf": 300}, "bf"),
    ("t_beam", {"hf": 600}, "hf"),
    ("t_beam", {"hf": 0}, "hf"),
    ("t_beam", {"hf": 40}, "hf"),  # a 40 mm flange cannot hold Ø12 under 30 mm cover
    ("t_beam", {"bottom": _DROP}, "bottom"),
    ("t_beam", {"bottom": [3, "Ø20"]}, "bottom"),
    ("t_beam", {"bottom": {"n": 1, "bar": "Ø20"}}, "bottom.n"),
    ("t_beam", {"top": {"n": 2, "bar": "Ø99"}}, "top.bar"),
    ("t_beam", {"top": {"n": 2, "bar": "Ø16", "x": 1}}, "top.x"),
    ("t_beam", {"slab_bars": {"n": 0, "bar": "Ø12"}}, "slab_bars.n"),
    ("t_beam", {"slab_bars": {"n": 4, "bar": "Ø12"}}, "slab_bars.n"),  # 31.25 < 36 to the tip
    ("t_beam", {"bw": 100}, "bottom.bar"),  # 100 <= 2 x 50
    ("t_beam", {"h": 90, "hf": 50}, "h"),
    ("t_beam", {"stirrup": None}, "stirrup"),
    ("t_beam", {"bottom": {"n": 10**9, "bar": "Ø20"}}, "bottom.n"),  # finding 1
    ("t_beam", {"slab_bars": {"n": 10**9, "bar": "Ø12"}}, "slab_bars.n"),
    ("t_beam", {"bottom": {"n": 300, "bar": "Ø20"}}, "bottom.n"),  # finding 2
    ("t_beam", {"top": {"n": 20, "bar": "Ø16"}}, "top.n"),
    ("t_beam", {"bw": 119}, "bw"),  # the two bottom end bars 19 mm apart, under Ø20
    ("t_beam", {"h": 99, "hf": 50}, "hf"),  # the slab rule fires first (2 x 30 + 12 = 72)
    ("t_beam", {"h": 99, "hf": 50, "slab_bars": _DROP}, "h"),  # rows 1 mm apart
    ("t_beam", {"hf": 45}, "hf"),  # finding 3: 3 mm under the slab bars
    ("t_beam", {"hf": 71.9}, "hf"),
]


@pytest.mark.parametrize(("template", "changes", "param"), REFUSALS)
def test_bad_params_are_refused_by_name(
    template: str, changes: dict[str, object], param: str
) -> None:
    with pytest.raises(TemplateParamError) as caught:
        expand(template, _with(ORACLES[template], **changes))
    assert (caught.value.template, caught.value.param) == (template, param)
    assert str(caught.value).startswith(f"{template}: {param}: ")
    assert caught.value.code == INVALID_ARGUMENT


def test_unknown_template_and_version_are_refused_by_name() -> None:
    assert set(TEMPLATES) == set(ORACLES)
    assert {name: latest_version(name) for name in TEMPLATES} == dict.fromkeys(ORACLES, 1)
    with pytest.raises(TemplateParamError, match="^box_column: template: unknown template"):
        expand("box_column", {})
    for version in (0, 2):
        with pytest.raises(TemplateParamError, match="template_version: unknown version"):
            expand("rect_column", RECT_COLUMN, version=version)
    for bad in (True, 1.0, "1"):  # finding 4: 1.0 == 1 but is not a version
        with pytest.raises(TemplateParamError, match="template_version: must be a whole"):
            expand("rect_column", RECT_COLUMN, version=bad)


@pytest.mark.parametrize("template", sorted(ORACLES))
@pytest.mark.parametrize("params", [[1, 2], "b=400", None, 7])
def test_params_that_are_not_an_object_are_refused(template: str, params: object) -> None:
    with pytest.raises(TemplateParamError, match=f"^{template}: params: params must be an obj"):
        expand(template, params)  # pyright: ignore[reportArgumentType]


def test_the_bar_cap_refuses_before_building() -> None:
    # Finding 1: 10**9 bars used to run out of memory; the refusal must be immediate.
    start = time.perf_counter()
    for template, changes in (("rect_column", {"nx": 10**9}), ("t_beam", {"bottom": {
            "n": 10**9, "bar": "Ø20"}})):  # fmt: skip
        with pytest.raises(TemplateParamError, match="a template places at most 1000"):
            expand(template, _with(ORACLES[template], **changes))
    assert time.perf_counter() - start < 1.0


def test_hf_at_the_slab_rule_limit_is_accepted() -> None:
    plan = expand("t_beam", _with(T_BEAM, hf=72))  # 2 x 30 + 12: the bars touch both covers
    slab = plan.bars[5:]
    assert {bar.xy[1] for bar in slab} == {564.0}
    assert 600.0 - 72.0 == 564.0 - 6.0 - 30.0  # soffit cover is exactly 30 mm


@pytest.mark.parametrize("template", sorted(ORACLES))
def test_no_oracle_expansion_has_overlapping_bars(template: str) -> None:
    plan = expand(template, ORACLES[template])
    bars = plan.bars
    for i, a in enumerate(bars):
        for b in bars[i + 1 :]:
            assert math.dist(a.xy, b.xy) >= (a.diameter_mm + b.diameter_mm) / 2.0


# --- the Plan carries C4's forms (circles, holes, steel shapes, circular ties) -----------


def test_plan_carries_circles_steel_shapes_and_circular_ties() -> None:
    core = PlanFace("concrete", "C50", PlanCircle((0.0, 0.0), 190.0))
    tube = PlanFace(
        "steel",
        "S355",
        PlanCircle((0.0, 0.0), 200.0),
        holes=(PlanCircle((0.0, 0.0), 190.0),),
        shape=PlanSteelShape("AISC", "HSS16x0.375", (0.0, 0.0)),
    )
    duct = PlanFace("void", None, PlanRing(((-20.0, -20.0), (20.0, -20.0), (20.0, 20.0))))
    bars = tuple(PlanBar(150.0 * math.cos(k), 150.0 * math.sin(k), "Ø20", 20.0) for k in (0, 2, 4))
    plan = Plan(
        faces=(core, tube, duct),
        bars=bars,
        circular_ties=(PlanCircularTie("spiral", (0.0, 0.0), 165.0, "Ø10", 10.0, 75.0),),
        cover_guides=(PlanCoverGuide(0, 15.0, 10.0, 20.0),),
    )
    assert plan == Plan(
        faces=(core, tube, duct),
        bars=bars,
        circular_ties=plan.circular_ties,
        cover_guides=plan.cover_guides,
    )


BROKEN_PLANS: list[tuple[str, dict[str, object]]] = [
    ("at least one face", {"faces": ()}),
    ("has no material", {"faces": (PlanFace("void", "C30", PlanCircle((0, 0), 1.0)),)}),
    ("needs a material", {"faces": (PlanFace("concrete", None, PlanCircle((0, 0), 1.0)),)}),
    ("only a steel face", {
        "faces": (PlanFace("concrete", "C30", PlanCircle((0, 0), 1.0),
                           shape=PlanSteelShape("AISC", "W8x10", (0, 0))),)}),
    ("positive radius", {"faces": (PlanFace("concrete", "C30", PlanCircle((0, 0), 0.0)),)}),
    ("must be CCW", {"faces": (PlanFace("concrete", "C30", PlanRing(((0, 0), (0, 1), (1, 0)))),)}),
    ("must be CW", {"faces": (PlanFace("concrete", "C30", PlanCircle((0, 0), 5.0),
                                       holes=(PlanRing(((0, 0), (1, 0), (0, 1))),)),)}),
    ("not simple", {"faces": (PlanFace("concrete", "C30",
                                       PlanRing(((0, 0), (1, 1), (1, 0), (0, 1)))),)}),
    ("out of range", {"hoops": (PlanHoop((0, 1, 2), "Ø10", 10.0, 100.0),)}),
    ("out of range", {"crossties": (PlanCrosstie(0, 3, "Ø10", 10.0, 100.0),)}),
    ("to itself", {"crossties": (PlanCrosstie(1, 1, "Ø10", 10.0, 100.0),)}),
    ("not a vocabulary bar", {"bars": (PlanBar(0, 0, "Ø20", 16.0),)}),
    ("positive radius and pitch", {
        "circular_ties": (PlanCircularTie("hoop", (0, 0), 50.0, "Ø10", 10.0, 0.0),)}),
    ("not concrete", {"faces": (PlanFace("steel", "S355", PlanCircle((0, 0), 5.0)),),
                      "cover_guides": (PlanCoverGuide(0, 1.0, 10.0, 20.0),)}),
    ("out of range", {"cover_guides": (PlanCoverGuide(1, 1.0, 10.0, 20.0),)}),
]  # fmt: skip


@pytest.mark.parametrize(("message", "fields"), BROKEN_PLANS)
def test_a_plan_that_breaks_its_invariants_is_refused(
    message: str, fields: dict[str, object]
) -> None:
    base: dict[str, object] = {
        "faces": (PlanFace("concrete", "C30", PlanCircle((0.0, 0.0), 100.0)),),
        "bars": (PlanBar(0.0, 0.0, "Ø20", 20.0), PlanBar(10.0, 0.0, "Ø20", 20.0)),
    }
    with pytest.raises(DocumentError, match=message):
        Plan(**{**base, **fields})  # pyright: ignore[reportArgumentType]

