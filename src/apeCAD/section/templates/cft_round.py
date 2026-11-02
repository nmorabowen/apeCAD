"""`cft_round`, version 1: a round concrete-filled steel tube (ADR 0040 Errata 11).

Draws, in this order, the concrete core, an exact circle of radius diameter / 2 - t, and the
steel tube, a circle of radius diameter / 2 with a circle hole of the core's radius, both
centred on `center_mm` (ADR 0039 decision 3: a core under a tube holed to its outline). The
core and the hole are the same floats, so the lint's CFT exemption holds and the core needs
no cover guide (ADR 0039 Errata 9.2).

`material` is the core's concrete, `steel_material` the tube's steel; both are required. No
bars, ties or cover guides are drawn, so `bar_material` is refused by name (owner's ruling Q1).
A wall `t` is refused unless the core sits strictly inside the tube in floats.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from apeCAD.section.geometry import Point2
from apeCAD.section.templates.plan import (
    Params,
    Plan,
    PlanCircle,
    PlanFace,
    TemplateParamError,
    plan_points,
    require_extent,
)

TEMPLATE = "cft_round"
VERSION = 1
FIELDS = ("material", "steel_material", "center_mm", "diameter", "t")


@dataclass(frozen=True, slots=True)
class CftRoundParams:
    """`cft_round` v1 parameters; lengths in mm."""

    material: str
    steel_material: str
    diameter: float
    t: float
    center_mm: Point2 = (0.0, 0.0)


def refuse_bar_material(template: str, data: Mapping[str, object]) -> None:
    """Refuse `bar_material`, given at all, on a template that places no bars (Errata 11)."""
    if isinstance(data, Mapping) and "bar_material" in data:  # pyright: ignore[reportUnnecessaryIsInstance]
        raise TemplateParamError(
            template,
            "bar_material",
            f"{template} v1 places no bars, so it takes no bar_material (ADR 0040 Errata 11)",
        )


def parse(data: Mapping[str, object]) -> CftRoundParams:
    """Read and check a `cft_round` parameter mapping; each fault is refused by name."""
    refuse_bar_material(TEMPLATE, data)
    p = Params(TEMPLATE, data, FIELDS)
    return CftRoundParams(
        material=p.material("material"),
        steel_material=p.material("steel_material"),
        center_mm=p.point("center_mm", (0.0, 0.0)),
        diameter=p.length("diameter"),
        t=p.length("t"),
    )


def expand_v1(data: Mapping[str, object]) -> Plan:
    """The `cft_round` v1 plan of a parameter mapping."""
    q = parse(data)
    radius = q.diameter / 2.0
    # The size alone first, so a huge diameter is refused by its own name, not as a wall t
    # (review of apeCAD #61); the placed tube is checked against `center_mm` below.
    require_extent(TEMPLATE, "diameter", ((-radius, -radius), (radius, radius)))
    core = radius - q.t
    if not 0.0 < core < radius:
        raise Params(TEMPLATE, {}, ()).error(
            "t",
            f"{q.t:g} mm leaves no core strictly inside the tube of diameter {q.diameter:g} mm "
            f"(core radius {core:g} mm)",
        )
    plan = Plan(
        faces=(
            PlanFace("concrete", q.material, PlanCircle(q.center_mm, core)),
            PlanFace(
                "steel",
                q.steel_material,
                PlanCircle(q.center_mm, radius),
                holes=(PlanCircle(q.center_mm, core),),
            ),
        ),
    )
    require_extent(TEMPLATE, "center_mm", plan_points(plan))
    return plan
