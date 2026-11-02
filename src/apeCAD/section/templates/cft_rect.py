"""`cft_rect`, version 1: a rectangular concrete-filled steel tube (ADR 0040 Errata 12).

Draws, in this order, the concrete core and the steel tube, both centred on `center_mm`
(ADR 0039 decision 3: a core under a tube holed to its outline). The tube is the b x h ring;
the core is that ring inset by the wall `t`, computed once as `x0 + t`, `x1 - t`, `y0 + t`,
`y1 - t` from the tube's own corners. The core ring is counter-clockwise and the tube's one
hole is the same four floats, clockwise (specs/section-draft-v2.md "Ring orientation"), so the
lint's CFT exemption holds and the core needs no cover guide (ADR 0039 Errata 9.2). The
corners are square: the contract has no arc (C4 record §7).

`material` is the core's concrete, `steel_material` the tube's steel; both are required. No
bars, ties or cover guides are drawn, so `bar_material` is refused by name (owner's ruling Q1,
`cft_round.refuse_bar_material`). A wall `t` is refused unless the core sits strictly inside
the tube in floats, along both axes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from apeCAD.section.geometry import Point2
from apeCAD.section.templates.cft_round import refuse_bar_material
from apeCAD.section.templates.plan import (
    Params,
    Plan,
    PlanFace,
    PlanRing,
    plan_points,
    require_extent,
)

TEMPLATE = "cft_rect"
VERSION = 1
FIELDS = ("material", "steel_material", "center_mm", "b", "h", "t")


@dataclass(frozen=True, slots=True)
class CftRectParams:
    """`cft_rect` v1 parameters; lengths in mm."""

    material: str
    steel_material: str
    b: float
    h: float
    t: float
    center_mm: Point2 = (0.0, 0.0)


def parse(data: Mapping[str, object]) -> CftRectParams:
    """Read and check a `cft_rect` parameter mapping; each fault is refused by name."""
    refuse_bar_material(TEMPLATE, data)
    p = Params(TEMPLATE, data, FIELDS)
    return CftRectParams(
        material=p.material("material"),
        steel_material=p.material("steel_material"),
        center_mm=p.point("center_mm", (0.0, 0.0)),
        b=p.length("b"),
        h=p.length("h"),
        t=p.length("t"),
    )


def expand_v1(data: Mapping[str, object]) -> Plan:
    """The `cft_rect` v1 plan of a parameter mapping."""
    q = parse(data)
    p = Params(TEMPLATE, {}, ())
    # The size alone first, so a huge b or h is refused by its own name, not as a wall.
    require_extent(TEMPLATE, "b", ((-q.b / 2.0, 0.0), (q.b / 2.0, 0.0)))
    require_extent(TEMPLATE, "h", ((0.0, -q.h / 2.0), (0.0, q.h / 2.0)))
    cx, cy = q.center_mm
    x0, x1, y0, y1 = cx - q.b / 2.0, cx + q.b / 2.0, cy - q.h / 2.0, cy + q.h / 2.0
    kx0, kx1, ky0, ky1 = x0 + q.t, x1 - q.t, y0 + q.t, y1 - q.t
    walls = (("b", q.b, x0, kx0, kx1, x1), ("h", q.h, y0, ky0, ky1, y1))
    for axis, size, lo, k_lo, k_hi, hi in walls:
        if not lo < k_lo < k_hi < hi:
            raise p.error(
                "t",
                f"{q.t:g} mm leaves no core strictly inside the tube across {axis} = {size:g} mm "
                f"(core {k_lo:g} to {k_hi:g} mm in a tube {lo:g} to {hi:g} mm)",
            )
    core = ((kx0, ky0), (kx1, ky0), (kx1, ky1), (kx0, ky1))  # counter-clockwise
    plan = Plan(
        faces=(
            PlanFace("concrete", q.material, PlanRing(core)),
            PlanFace(
                "steel",
                q.steel_material,
                PlanRing(((x0, y0), (x1, y0), (x1, y1), (x0, y1))),
                holes=(PlanRing((core[0], core[3], core[2], core[1])),),  # the same, clockwise
            ),
        ),
    )
    require_extent(TEMPLATE, "center_mm", plan_points(plan))
    return plan
