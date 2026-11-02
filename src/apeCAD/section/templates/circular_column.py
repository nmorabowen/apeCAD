"""`circular_column`, version 1: a circular column with a spiral or hoop (ADR 0040 Errata 10).

Draws, in this order, the exact concrete circle of `diameter` centred on `center_mm`, `n_bars`
equal bars evenly on a circle from angle 0 counter-clockwise, one circular tie and the cover
guide.

A bar centre sits `cover + tie + bar / 2` inside the face (Errata 7), so r_b = diameter / 2 -
(cover + tie + bar / 2). The tie's centreline is at r_t = diameter / 2 - cover - tie / 2, with
`pitch_mm` = `pitch`. `tie_kind` is required, because a silent spiral would overstate the
confinement. A `hoop` differs from a `spiral` in `kind` alone: it is a `circular_ties[]` entry
too (ADR 0039 decision 5), and `hoops[]` stays empty.

Overlapping bars (closer than the mean of their diameters, lint's `bar-overlap` rule) are
refused by `n_bars`, or by `diameter` when even the fewest bars, three, overlap. The code
checks of bar count and spiral spacing (ACI 10.7.3.1) are the consumer's.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from apeCAD.section.designations import DESIGNATIONS
from apeCAD.section.geometry import Point2
from apeCAD.section.layout import on_circle
from apeCAD.section.templates.plan import (
    CircularTieKind,
    Params,
    Plan,
    PlanBar,
    PlanCircle,
    PlanCircularTie,
    PlanCoverGuide,
    PlanFace,
    finish,
    require_bar_count,
)

TEMPLATE = "circular_column"
VERSION = 1
TIE_KINDS = ("spiral", "hoop")
MIN_BARS = 3
"""The fewest bars that span an area (Errata 10)."""
FIELDS = (
    "material", "bar_material", "center_mm", "diameter", "cover", "n_bars", "bar", "tie_kind",
    "tie", "pitch",
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class CircularColumnParams:
    """`circular_column` v1 parameters; lengths in mm, bars as vocabulary designations."""

    material: str
    diameter: float
    cover: float
    n_bars: int
    bar: str
    tie_kind: str
    tie: str
    pitch: float
    bar_material: str | None = None
    center_mm: Point2 = (0.0, 0.0)


def parse(data: Mapping[str, object]) -> CircularColumnParams:
    """Read and check a `circular_column` parameter mapping; each fault is refused by name."""
    p = Params(TEMPLATE, data, FIELDS)
    n_bars = p.count("n_bars", MIN_BARS)
    require_bar_count(p, {"n_bars": n_bars})
    tie, tie_d = p.designation("tie")
    pitch = p.length("pitch")
    if pitch < tie_d:
        raise p.error(
            "pitch", f"{pitch:g} mm is under the tie's {tie_d:g} mm: its turns would overlap"
        )
    return CircularColumnParams(
        material=p.material("material"),
        bar_material=p.optional_material("bar_material"),
        center_mm=p.point("center_mm", (0.0, 0.0)),
        diameter=p.length("diameter"),
        cover=p.length("cover"),
        n_bars=n_bars,
        bar=p.designation("bar")[0],
        tie_kind=p.choice("tie_kind", TIE_KINDS),
        tie=tie,
        pitch=pitch,
    )


def expand_v1(data: Mapping[str, object]) -> Plan:
    """The `circular_column` v1 plan of a parameter mapping; refuses an inset that collapses."""
    q = parse(data)
    p = Params(TEMPLATE, {}, ())
    bar_d, tie_d = DESIGNATIONS[q.bar], DESIGNATIONS[q.tie]
    radius = q.diameter / 2.0
    inset = q.cover + tie_d + bar_d / 2.0
    r_bars = radius - inset
    if r_bars <= 0.0:
        raise p.error(
            "diameter",
            f"{q.diameter:g} mm leaves no room inside the bar-centre inset {inset:g} mm "
            "(cover + tie + bar / 2)",
        )
    r_tie = radius - q.cover - tie_d / 2.0
    kind: CircularTieKind = "spiral" if q.tie_kind == "spiral" else "hoop"
    spots = (on_circle(q.center_mm, r_bars, 360.0 * k / q.n_bars) for k in range(q.n_bars))
    plan = Plan(
        faces=(PlanFace("concrete", q.material, PlanCircle(q.center_mm, radius)),),
        bars=tuple(PlanBar(x, y, q.bar, bar_d, q.bar_material) for x, y in spots),
        circular_ties=(PlanCircularTie(kind, q.center_mm, r_tie, q.tie, tie_d, q.pitch),),
        cover_guides=(PlanCoverGuide(0, q.cover, tie_d, bar_d),),
    )
    fewest_gap = r_bars * math.sqrt(3.0)  # the chord of three bars

    def overlap(_i: int, _j: int) -> str:
        return "diameter" if fewest_gap < bar_d else "n_bars"

    return finish(TEMPLATE, plan, placement="center_mm", count="n_bars", overlap=overlap)
