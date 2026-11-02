"""Section templates as pure functions to a `Plan` (ADR 0040, stage C3-S1, apeSection#48).

Oracles are hand-computed in the C3 decision record §2 and compared at rel 1e-12; bar
positions of `rect_column` and the `t_beam` ring are compared exactly with the v2 fixtures.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Sequence
from dataclasses import replace

import pytest

from _section_fixtures_v2 import FIXTURE_DIR, T_RING
from apeCAD import Document
from apeCAD.errors import INVALID_ARGUMENT, DocumentError
from apeCAD.section.geometry import Point2, signed_area
from apeCAD.section.layout import on_circle
from apeCAD.section.templates import TEMPLATES, circular_column, expand, latest_version
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
CIRCULAR_COLUMN: dict[str, object] = {
    "material": "concrete", "diameter": 600, "cover": 40, "n_bars": 8, "bar": "Ø20",
    "tie_kind": "spiral", "tie": "Ø10", "pitch": 75,
}  # fmt: skip
ORACLES = {
    "rect_column": RECT_COLUMN,
    "polygon_column": POLYGON_COLUMN,
    "rect_hollow": RECT_HOLLOW,
    "t_beam": T_BEAM,
    "circular_column": CIRCULAR_COLUMN,
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


def _ngon(n: int, radius: float = 1e5) -> list[list[float]]:
    """A convex regular n-gon (re-review of #56: polygon_column's O(n²) before the cap)."""
    step = 2.0 * math.pi / n
    return [[radius * math.cos(k * step), radius * math.sin(k * step)] for k in range(n)]


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


# --- circular_column (C4 record §6, rows 1 and 2) ------------------------------------------


def test_circular_column_oracle_row_1_the_fixture_column() -> None:
    plan = expand("circular_column", CIRCULAR_COLUMN)
    (face,) = plan.faces
    assert (face.role, face.material, face.holes) == ("concrete", "concrete", ())
    assert face.boundary == PlanCircle((0.0, 0.0), 300.0)
    assert math.isclose(math.pi * 300.0**2, 282_743.339, abs_tol=5e-4)
    # r_b = 300 - 40 - 10 - 10 = 240. A whole quarter turn is exact: an unsnapped cos 90° is
    # 1.5e-14 away from the axis, and these are exact comparisons.
    assert [plan.bars[k].xy for k in (0, 2, 4, 6)] == [(240, 0), (0, 240), (-240, 0), (0, -240)]
    k = 240.0 * math.sqrt(0.5)  # 169.706
    for bar, (sx, sy) in zip(
        [plan.bars[n] for n in (1, 3, 5, 7)], ((1, 1), (-1, 1), (-1, -1), (1, -1)), strict=True
    ):
        assert math.isclose(bar.x_mm, sx * k, rel_tol=REL)
        assert math.isclose(bar.y_mm, sy * k, rel_tol=REL)
    assert math.isclose(k, 169.706, abs_tol=5e-4)
    assert len(plan.bars) == 8
    assert {(b.designation, b.diameter_mm, b.material) for b in plan.bars} == {("Ø20", 20.0, None)}
    assert plan.circular_ties == (PlanCircularTie("spiral", (0.0, 0.0), 255.0, "Ø10", 10.0, 75.0),)
    assert plan.cover_guides == (PlanCoverGuide(0, 40.0, 10.0, 20.0),)
    assert plan.hoops == () and plan.crossties == ()


def test_circular_column_oracle_row_2_off_centre_with_a_hoop() -> None:
    plan = expand(
        "circular_column",
        {
            "material": "C30", "bar_material": "A630", "center_mm": [100, -50], "diameter": 500,
            "cover": 40, "n_bars": 6, "bar": "Ø16", "tie_kind": "hoop", "tie": "Ø8", "pitch": 150,
        },
    )  # fmt: skip
    assert plan.faces[0].boundary == PlanCircle((100.0, -50.0), 250.0)
    assert math.isclose(math.pi * 250.0**2, 196_349.541, abs_tol=5e-4)
    # r_b = 250 - 40 - 8 - 8 = 194; 194 sin 60° = 168.009.
    expected = [
        (294.0, -50.0), (197.0, 118.009), (3.0, 118.009),
        (-94.0, -50.0), (3.0, -218.009), (197.0, -218.009),
    ]  # fmt: skip
    for bar, (x, y) in zip(plan.bars, expected, strict=True):
        assert math.isclose(bar.x_mm, x, abs_tol=5e-4) and math.isclose(bar.y_mm, y, abs_tol=5e-4)
    assert plan.bars[0].xy == (294.0, -50.0) and plan.bars[3].xy == (-94.0, -50.0)  # exact
    assert plan.hoops == ()  # a hoop is a circular tie (ADR 0039 decision 5, Errata 10.2)
    assert plan.circular_ties == (PlanCircularTie("hoop", (100.0, -50.0), 206.0, "Ø8", 8.0, 150.0),)
    assert {bar.material for bar in plan.bars} == {"A630"}


def test_tie_kind_hoop_changes_only_the_kind() -> None:
    spiral = expand("circular_column", CIRCULAR_COLUMN)
    hoop = expand("circular_column", _with(CIRCULAR_COLUMN, tie_kind="hoop"))
    assert hoop.circular_ties[0].kind == "hoop"
    assert hoop == replace(
        spiral, circular_ties=(replace(spiral.circular_ties[0], kind="hoop"),)
    )


AT_THE_LIMIT: dict[str, object] = {
    "material": "C30", "diameter": 300, "cover": 40, "n_bars": 16, "bar": "Ø32",
    "tie_kind": "spiral", "tie": "Ø10", "pitch": 75,
}  # fmt: skip


def test_circular_column_bar_spacing_limit_by_hand() -> None:
    # r_b = 150 - 40 - 10 - 16 = 84. Chords 2 r_b sin(π / n): 32.78 mm at 16, 30.87 at 17; Ø32.
    assert math.isclose(2.0 * 84.0 * math.sin(math.pi / 16), 32.78, abs_tol=5e-3)
    assert math.isclose(2.0 * 84.0 * math.sin(math.pi / 17), 30.87, abs_tol=5e-3)
    assert len(expand("circular_column", AT_THE_LIMIT).bars) == 16
    with pytest.raises(TemplateParamError) as caught:
        expand("circular_column", _with(AT_THE_LIMIT, n_bars=17))
    assert caught.value.param == "n_bars"


def test_circular_column_pitch_limit_is_the_tie() -> None:
    plan = expand("circular_column", _with(CIRCULAR_COLUMN, pitch=10))
    assert plan.circular_ties[0].pitch_mm == 10.0
    with pytest.raises(TemplateParamError, match="^circular_column: pitch: 9.9 mm is under"):
        expand("circular_column", _with(CIRCULAR_COLUMN, pitch=9.9))


def test_tie_kind_is_required_and_the_choice_with_a_default_is_as_it_was() -> None:
    with pytest.raises(TemplateParamError, match="^circular_column: tie_kind: required$"):
        expand("circular_column", _with(CIRCULAR_COLUMN, tie_kind=_DROP))
    # The form with a default: absent takes it, and null is still refused, not defaulted.
    assert expand("rect_column", _with(RECT_COLUMN, crossties=_DROP)).crossties == ()
    with pytest.raises(TemplateParamError, match="crossties: must be one of .* got None$"):
        expand("rect_column", _with(RECT_COLUMN, crossties=None))


@pytest.mark.parametrize("n", range(3, 60))
@pytest.mark.parametrize("radius", [240.0, 123.456, 0.1 + 0.2 + 300.0])
def test_a_template_and_add_bars_on_circle_place_the_same_floats(n: int, radius: float) -> None:
    """One formula (`layout.on_circle`): the freehand op's bars, and the template's, exactly."""
    diameter = 2.0 * (radius + 16.0)  # cover 1 + tie 10 + bar 10 / 2 = 16
    r_bars = diameter / 2.0 - (1.0 + 10.0 + 5.0)
    doc = Document()
    freehand = []
    for bar in doc.add_bars_on_circle((12.5, -7.1), r_bars, n, "Ø10"):
        xyz = doc.entity(bar.point_id).xyz_mm  # pyright: ignore[reportAttributeAccessIssue]
        freehand.append((xyz.x_mm, xyz.y_mm))
    plan = expand(
        "circular_column",
        {
            "material": "C30", "center_mm": [12.5, -7.1], "diameter": diameter, "cover": 1,
            "n_bars": n, "bar": "Ø10", "tie_kind": "hoop", "tie": "Ø10", "pitch": 100,
        },
    )  # fmt: skip
    assert [bar.xy for bar in plan.bars] == freehand
    assert freehand == [on_circle((12.5, -7.1), r_bars, 360.0 * k / n) for k in range(n)]


def test_over_1000_n_bars_refuses_before_placing_a_bar(monkeypatch: pytest.MonkeyPatch) -> None:
    def placed(*_args: object) -> Point2:
        raise AssertionError("a bar was placed")

    monkeypatch.setattr(circular_column, "on_circle", placed)
    with pytest.raises(TemplateParamError, match="^circular_column: n_bars: .*at most 1000"):
        expand("circular_column", _with(CIRCULAR_COLUMN, n_bars=1001))


def test_on_circle_is_exact_at_every_whole_quarter_turn() -> None:
    for turn, xy in (
        (0.0, (7.0, 0.0)), (90.0, (0.0, 7.0)), (180.0, (-7.0, 0.0)), (270.0, (0.0, -7.0)),
        (360.0, (7.0, 0.0)), (-90.0, (0.0, -7.0)), (450.0, (0.0, 7.0)),
    ):  # fmt: skip
        assert on_circle((0.0, 0.0), 7.0, turn) == xy


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
    # Re-review of #56: the cap is checked before any O(n²) work on the ring.
    ("polygon_column", {"ring": _ngon(1001)}, "ring"),  # a bar per vertex: over 1000
    ("polygon_column", {"ring": _ngon(600)}, "spacing_max"),  # Σ ceil(L / 150) = 4200 bars
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
    ("rect_column", {"crossties": None}, "crossties"),  # `choice` with a default, as it was
    ("circular_column", {"material": ""}, "material"),
    ("circular_column", {"bar_material": 7}, "bar_material"),
    ("circular_column", {"diameter": _DROP}, "diameter"),
    ("circular_column", {"diameter": -600}, "diameter"),
    ("circular_column", {"diameter": 120}, "diameter"),  # r_b = 60 - 40 - 10 - 10 = 0
    ("circular_column", {"diameter": 60}, "diameter"),  # r_t = 30 - 40 - 5 < 0: no tie either
    ("circular_column", {"diameter": 122}, "diameter"),  # r_b = 1: even three bars overlap
    ("circular_column", {"cover": 0}, "cover"),
    ("circular_column", {"n_bars": _DROP}, "n_bars"),
    ("circular_column", {"n_bars": 2}, "n_bars"),
    ("circular_column", {"n_bars": 8.0}, "n_bars"),
    ("circular_column", {"n_bars": True}, "n_bars"),
    ("circular_column", {"n_bars": 1001}, "n_bars"),
    ("circular_column", {"n_bars": 10**9}, "n_bars"),
    ("circular_column", {"n_bars": 200}, "n_bars"),  # 2 x 240 sin(π / 200) = 7.5 mm, under Ø20
    ("circular_column", {"bar": "#5"}, "bar"),
    ("circular_column", {"tie": "Ø99"}, "tie"),
    ("circular_column", {"tie_kind": _DROP}, "tie_kind"),
    ("circular_column", {"tie_kind": None}, "tie_kind"),
    ("circular_column", {"tie_kind": "helix"}, "tie_kind"),
    ("circular_column", {"tie_kind": 1}, "tie_kind"),
    ("circular_column", {"pitch": _DROP}, "pitch"),
    ("circular_column", {"pitch": 0}, "pitch"),
    ("circular_column", {"pitch": 9.9}, "pitch"),  # under Ø10: the turns overlap
    ("circular_column", {"center_mm": [2.0**21, 0]}, "center_mm"),
    ("circular_column", {"center_mm": [1, 2, 3]}, "center_mm"),
    ("circular_column", {"start_angle_deg": 45}, "start_angle_deg"),
    ("circular_column", {"b": 300}, "b"),
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
    # Re-review: a 4000-vertex ring took 19 s, 20 000 took 458 s; spacing 0.01 mm on a box.
    cases: list[tuple[str, dict[str, object]]] = [
        ("rect_column", {"nx": 10**9}),
        ("t_beam", {"bottom": {"n": 10**9, "bar": "Ø20"}}),
        ("polygon_column", {"ring": _ngon(1001)}),
        ("polygon_column", {"ring": _ngon(20_000)}),
        ("polygon_column", {"spacing_max": 1e-6}),
        ("rect_hollow", {"spacing_max": 1e-6}),
        ("circular_column", {"n_bars": 1001}),
        ("circular_column", {"n_bars": 10**9}),
    ]
    for template, changes in cases:
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

