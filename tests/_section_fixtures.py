"""Builders of the `apeCAD.section-draft` v1 fixtures (ADR 0025 decision 8, stage C4).

Each builder draws one section with the public ops. The committed JSON in
`tests/fixtures/section_draft/` is `section_draft(document, commit=None)` of it: no git sha,
so the bytes depend on the code alone. apeConcrete copies these files at a pinned apeCAD
sha (its stage A11).

Regenerate after a deliberate change, then review the diff:

    REGENERATE=1 PYTHONPATH=src python -m pytest -q tests/test_section_draft_fixtures.py
    PYTHONPATH=src python tests/_section_fixtures.py
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from pathlib import Path

from apeCAD import Document, LegSteel
from apeCAD.geometry import XYZ
from apeCAD.ops import PointAt
from apeCAD.section_draft import section_draft

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "section_draft"

CONCRETE = "concrete"


def _at(x: float, y: float) -> PointAt:
    return PointAt(XYZ(float(x), float(y), 0.0))


# --- rect_boundary_hoops: apeConcrete tests/fixtures/walls/rect_300x3000.json ------------
#
# One 3000 x 300 leg, confined 600 mm at each end. Bar positions are apeConcrete's
# `x_from_left` and `y_from_top` floats copied as written, with y_world = -y_from_top
# (specs/section-draft.md, `frame`): 18 boundary bars Ø16 per end, 43 mm in from the
# region's faces (25 cover + 10 hoop + 8); 14 web bars Ø12 in two curtains, 31 mm in.
# Hoop Ø10 @ 100 per end. apeConcrete's `legs_y = 4` is drawn as two crossties per end
# across the two long faces; `legs_x = 2` is the hoop alone.

_BOUNDARY_X = (
    (43.0, 128.66666666666606, 214.33333333333394, 300.0, 385.66666666666606,
     471.33333333333394, 557.0),
    (2443.0, 2528.666666666666, 2614.333333333334, 2700.0, 2785.666666666666,
     2871.333333333334, 2957.0),
)  # fmt: skip
_BOUNDARY_SIDE_Y = (185.66666666666697, 114.33333333333303)  # y_from_top, downward order
_WEB_X = (
    728.5714285714294, 985.7142857142862, 1242.8571428571431, 1500.0, 1757.1428571428569,
    2014.2857142857138, 2271.4285714285706,
)  # fmt: skip


def _boundary_ring(xs: tuple[float, ...]) -> list[tuple[float, float]]:
    """apeConcrete's order: the y=257 row left to right, up the right side, the y=43 row
    right to left, down the left side; as (x_from_left, y_from_top)."""
    ring = [(x, 257.0) for x in xs]
    ring += [(xs[-1], y) for y in _BOUNDARY_SIDE_Y] + [(xs[-1], 43.0)]
    ring += [(x, 43.0) for x in reversed(xs[:-1])]
    ring += [(xs[0], y) for y in reversed(_BOUNDARY_SIDE_Y)]
    return ring


def rect_boundary_hoops() -> Document:
    doc = Document()
    face = doc.add_wall_chain(
        [_at(0, -150), _at(3000, -150)],
        300.0,
        CONCRETE,
        horizontal=LegSteel("Ø12", 250.0, 2),
        label="rect_300x3000",
    )
    doc.set_cover(face.entity_id, 25.0, 10.0, 16.0)
    for label, xs in zip(("C1", "C2"), _BOUNDARY_X, strict=True):
        bars = {(x, y): doc.add_bar(x, -y, "Ø16").entity_id for x, y in _boundary_ring(xs)}
        doc.add_hoop(list(bars.values()), "Ø10", 100.0, label=label)
        for x in (xs[2], xs[4]):
            doc.add_crosstie(bars[(x, 257.0)], bars[(x, 43.0)], "Ø10", 100.0)
    for y in (269.0, 31.0):
        for x in _WEB_X:
            doc.add_bar(x, -y, "Ø12")
    return doc


# --- l_wall_two_hoops: an L of two 300 mm legs, a hoop at each free end ---------------------


def l_wall_two_hoops() -> Document:
    doc = Document()
    face = doc.add_wall_chain(
        [_at(0, 150), _at(2850, 150), _at(2850, 3000)],
        300.0,
        CONCRETE,
        horizontal=LegSteel("Ø10", 200.0, 2),
        label="L1",
    )
    doc.set_cover(face.entity_id, 25.0, 10.0, 16.0)
    # Free end of the horizontal leg: x 0..600, y 0..300.
    tip = doc.add_bar_row((43.0, 43.0), (557.0, 43.0), "Ø16", count=4)
    tip += doc.add_bar_row((43.0, 257.0), (557.0, 257.0), "Ø16", count=4)
    doc.add_hoop([bar.entity_id for bar in tip], "Ø10", 100.0, label="BE1")
    # Free end of the vertical leg: x 2700..3000, y 2400..3000.
    top = doc.add_bar_row((2743.0, 2443.0), (2743.0, 2957.0), "Ø16", count=4)
    top += doc.add_bar_row((2957.0, 2443.0), (2957.0, 2957.0), "Ø16", count=4)
    doc.add_hoop([bar.entity_id for bar in top], "Ø10", 100.0, label="BE2")
    return doc


# --- c_wall_crossties: a C of three legs; a hoop in the web with crossties ------------------


def c_wall_crossties() -> Document:
    doc = Document()
    face = doc.add_wall_chain(
        [_at(1500, 2850), _at(150, 2850), _at(150, 150), _at(1500, 150)],
        300.0,
        CONCRETE,
        label="C1",
    )
    doc.set_cover(face.entity_id, 25.0, 10.0, 16.0)
    web_leg = doc.wall_legs()[1]  # one leg per axis segment, in order: the second is the web
    doc.set_leg_reinforcement(web_leg.entity_id, "Ø12", 250.0, 2)
    left = doc.add_bar_row((43.0, 1100.0), (43.0, 1900.0), "Ø20", count=5)
    right = doc.add_bar_row((257.0, 1100.0), (257.0, 1900.0), "Ø20", count=5)
    doc.add_hoop([bar.entity_id for bar in (*left, *right)], "Ø12", 100.0, label="BE-web")
    for a, b in zip(left[1:-1], right[1:-1], strict=True):
        doc.add_crosstie(a.entity_id, b.entity_id, "Ø12", 100.0, hooks="135-90")
    return doc


# --- inclined_outline: a straight wall at 30 degrees, caged edge by edge (ADR 0032) ---------


def inclined_outline() -> Document:
    doc = Document()
    angle = math.radians(30.0)
    length = 3000.0
    end = (length * math.cos(angle), length * math.sin(angle))
    face = doc.add_wall_chain(
        [_at(0, 0), _at(*end)],
        250.0,
        CONCRETE,
        horizontal=LegSteel("Ø10", 200.0, 2),
        label="W-incl",
    )
    doc.set_cover(face.entity_id, 25.0, 10.0, 16.0)
    bars = doc.add_bars_along_edge(face.entity_id, 0, "Ø16", count=12)
    bars += doc.add_bars_along_edge(face.entity_id, 1, "Ø16", count=3)
    bars += doc.add_bars_along_edge(face.entity_id, 2, "Ø16", count=12)
    bars += doc.add_bars_along_edge(face.entity_id, 3, "Ø16", count=3)
    doc.add_hoop([bar.entity_id for bar in bars], "Ø10", 150.0, label="H1")
    return doc


BUILDERS: dict[str, Callable[[], Document]] = {
    "rect_boundary_hoops": rect_boundary_hoops,
    "l_wall_two_hoops": l_wall_two_hoops,
    "c_wall_crossties": c_wall_crossties,
    "inclined_outline": inclined_outline,
}


def fixture_draft(name: str) -> dict[str, object]:
    """The draft as committed: no commit sha."""
    return section_draft(BUILDERS[name](), commit=None)


def fixture_path(name: str) -> Path:
    return FIXTURE_DIR / f"{name}.json"


def fixture_text(draft: dict[str, object]) -> str:
    return json.dumps(draft, indent=2, ensure_ascii=False) + "\n"


def write_fixtures() -> list[Path]:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name in BUILDERS:
        path = fixture_path(name)
        path.write_text(fixture_text(fixture_draft(name)), encoding="utf-8", newline="\n")
        written.append(path)
    return written


if __name__ == "__main__":
    for written_path in write_fixtures():
        print(written_path)
