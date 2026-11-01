"""Cover rings of a concrete face, from its cover guide (ADR 0024, plan stage C2).

Clear cover is measured to the outside of the transverse bar (ADR 0024 open q6, the
proposed default, ACI 318-25 §20.5.1.3): the cover ring is the outline inset by
`cover_mm`, and bar centres sit on the outline inset by `cover + tie + bar / 2`. Both are
plain mitred offsets (`miter_offset`); nothing here is mechanics.

A v2 face whose boundary is a circle insets to concentric circles. `circle_cover_rings`
samples them as polygons for the scratchpad to draw and snap to; the section-draft keeps the
exact circle (specs/section-draft-v2.md "Rules").
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from apeCAD.entities import CoverGuide
from apeCAD.errors import DocumentError
from apeCAD.section.geometry import Point2, miter_offset


def bar_centre_inset_mm(guide: CoverGuide) -> float:
    """How far bar centres sit inside the outline: cover + tie + bar / 2."""
    return guide.cover_mm + guide.tie_diameter_mm + guide.bar_diameter_mm / 2.0


@dataclass(frozen=True, slots=True)
class CoverRings:
    """The two inset rings, CCW; a ring is None when its inset collapses, with the reason."""

    cover_ring_mm: list[Point2] | None
    bar_centre_ring_mm: list[Point2] | None
    reason: str | None


def cover_rings(outline: Sequence[Point2], guide: CoverGuide) -> CoverRings:
    """Inset `outline` by the guide's cover and by its bar-centre inset."""
    rings: list[list[Point2] | None] = []
    reason: str | None = None
    for what, inset in (
        ("cover ring", guide.cover_mm),
        ("bar-centre ring", bar_centre_inset_mm(guide)),
    ):
        try:
            rings.append(miter_offset(outline, inset))
        except DocumentError as exc:
            rings.append(None)
            if reason is None:
                reason = f"the {what} at {inset:g} mm collapses: {exc}"
    return CoverRings(cover_ring_mm=rings[0], bar_centre_ring_mm=rings[1], reason=reason)


CIRCLE_RING_SIDES = 96
"""Vertices of a sampled cover circle; display and snapping only, never the contract."""


def circle_cover_rings(center: Point2, radius_mm: float, guide: CoverGuide) -> CoverRings:
    """The cover and bar-centre circles of a circular face, sampled CCW from angle 0."""
    rings: list[list[Point2] | None] = []
    reason: str | None = None
    for what, inset in (
        ("cover ring", guide.cover_mm),
        ("bar-centre ring", bar_centre_inset_mm(guide)),
    ):
        r = radius_mm - inset
        if r <= 0.0:
            rings.append(None)
            if reason is None:
                reason = f"the {what} at {inset:g} mm collapses: the radius is {radius_mm:g} mm"
            continue
        step = 2.0 * math.pi / CIRCLE_RING_SIDES
        rings.append(
            [
                (center[0] + r * math.cos(k * step), center[1] + r * math.sin(k * step))
                for k in range(CIRCLE_RING_SIDES)
            ]
        )
    return CoverRings(cover_ring_mm=rings[0], bar_centre_ring_mm=rings[1], reason=reason)
