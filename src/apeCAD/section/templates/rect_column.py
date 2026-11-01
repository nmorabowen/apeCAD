"""`rect_column`, version 1: a rectangular tied column (ADR 0040 decision 5, C3 record §2).

Draws the b x h ring, centred on `center_mm` (the centre of the gross bounding box), its
cover guide, `nx` bars along each horizontal face and `ny` along each vertical face
(2nx + 2ny - 4 in all, corners shared), one hoop on their strict hull and the crossties.

A bar centre sits `cover + tie + bar / 2` inside the face it rests on; a corner bar uses
`corner_bar` (default `bar`). Interior bars are evenly spaced between the corner bar centres.
Bars are listed counter-clockwise from the south-west corner.

Crossties are 135-135 and join the two interior bars facing each other across the section:
each interior column of the bottom face with the same column of the top face, then each
interior row of the right face with the same row of the left face. Bar positions along a
face are counted from the corner (index 0), so `alternate` ties the even indices only, and
`none` ties nothing; the hoop holds the corners.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from apeCAD.section.designations import DESIGNATIONS
from apeCAD.section.geometry import Point2
from apeCAD.section.templates.plan import (
    Params,
    Plan,
    PlanBar,
    PlanCoverGuide,
    PlanCrosstie,
    PlanFace,
    PlanHoop,
    PlanRing,
    finish,
    hull_of,
)

TEMPLATE = "rect_column"
VERSION = 1
CROSSTIE_PATTERNS = ("none", "all", "alternate")
FIELDS = (
    "material", "bar_material", "center_mm", "b", "h", "cover", "nx", "ny", "bar",
    "corner_bar", "tie", "tie_spacing", "crossties",
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class RectColumnParams:
    """`rect_column` v1 parameters; lengths in mm, bars as vocabulary designations."""

    material: str
    b: float
    h: float
    cover: float
    nx: int
    ny: int
    bar: str
    tie: str
    tie_spacing: float
    corner_bar: str | None = None
    crossties: str = "none"
    bar_material: str | None = None
    center_mm: Point2 = (0.0, 0.0)


def parse(data: Mapping[str, object]) -> RectColumnParams:
    """Read and check a `rect_column` parameter mapping; each fault is refused by name."""
    p = Params(TEMPLATE, data, FIELDS)
    return RectColumnParams(
        material=p.material("material"),
        bar_material=p.optional_material("bar_material"),
        center_mm=p.point("center_mm", (0.0, 0.0)),
        b=p.length("b"),
        h=p.length("h"),
        cover=p.length("cover"),
        nx=p.count("nx", 2),
        ny=p.count("ny", 2),
        bar=p.designation("bar")[0],
        corner_bar=p.designation("corner_bar")[0] if p.has("corner_bar") else None,
        tie=p.designation("tie")[0],
        tie_spacing=p.length("tie_spacing"),
        crossties=p.choice("crossties", CROSSTIE_PATTERNS, "none"),
    )


def expand_v1(data: Mapping[str, object]) -> Plan:
    """The `rect_column` v1 plan of a parameter mapping; refuses an inset that collapses."""
    q = parse(data)
    p = Params(TEMPLATE, {}, ())
    corner = q.corner_bar or q.bar
    bar_d, corner_d, tie_d = DESIGNATIONS[q.bar], DESIGNATIONS[corner], DESIGNATIONS[q.tie]
    cx, cy = q.center_mm
    x0, x1 = cx - q.b / 2.0, cx + q.b / 2.0
    y0, y1 = cy - q.h / 2.0, cy + q.h / 2.0
    dc = q.cover + tie_d + corner_d / 2.0  # corner bar centre inset
    di = q.cover + tie_d + bar_d / 2.0  # face bar centre inset
    for name, size in (("b", q.b), ("h", q.h)):
        if size - 2.0 * max(dc, di) <= 0.0:
            raise p.error(
                name,
                f"{size:g} mm leaves no room inside the bar-centre inset "
                f"{max(dc, di):g} mm (cover + tie + bar / 2) from both faces",
            )
    xa, xb, ya, yb = x0 + dc, x1 - dc, y0 + dc, y1 - dc

    def xi(i: int) -> float:
        return xa + i * (xb - xa) / (q.nx - 1)

    def yj(j: int) -> float:
        return ya + j * (yb - ya) / (q.ny - 1)

    spots: list[tuple[float, float, str]] = [(xa, ya, corner)]
    spots += [(xi(i), y0 + di, q.bar) for i in range(1, q.nx - 1)]
    spots.append((xb, ya, corner))
    spots += [(x1 - di, yj(j), q.bar) for j in range(1, q.ny - 1)]
    spots.append((xb, yb, corner))
    spots += [(xi(i), y1 - di, q.bar) for i in range(q.nx - 2, 0, -1)]
    spots.append((xa, yb, corner))
    spots += [(x0 + di, yj(j), q.bar) for j in range(q.ny - 2, 0, -1)]
    bars = tuple(
        PlanBar(x, y, name, DESIGNATIONS[name], q.bar_material) for x, y, name in spots
    )

    ne = q.nx + q.ny - 2  # index of the north-east corner bar
    nw = 2 * q.nx + q.ny - 3  # index of the north-west corner bar
    step = 2 if q.crossties == "alternate" else 1
    first = 2 if q.crossties == "alternate" else 1
    pairs: list[tuple[int, int]] = []
    if q.crossties != "none":
        pairs += [(i, ne + q.nx - 1 - i) for i in range(first, q.nx - 1, step)]
        pairs += [(q.nx - 1 + j, nw + q.ny - 1 - j) for j in range(first, q.ny - 1, step)]
    ring = PlanRing(((x0, y0), (x1, y0), (x1, y1), (x0, y1)))
    plan = Plan(
        faces=(PlanFace("concrete", q.material, ring),),
        bars=bars,
        hoops=(PlanHoop(hull_of(bars, range(len(bars))), q.tie, tie_d, q.tie_spacing),),
        crossties=tuple(PlanCrosstie(a, b, q.tie, tie_d, q.tie_spacing) for a, b in pairs),
        cover_guides=(PlanCoverGuide(0, q.cover, tie_d, bar_d),),
    )
    return finish(TEMPLATE, plan, placement="center_mm")
