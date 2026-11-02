"""The unit the SVG writer draws: one entity's world-space polylines on one layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from apeCAD.render.views import Vec3

Layer = Literal[
    "face", "solid", "edge", "point", "concrete", "steel", "void", "cover", "leg", "hoop",
    "crosstie", "circular-tie", "bar",
]
# Back to front (C5 record §3): role decides overlap, void > steel > concrete (ADR 0039 D3).
SECTION_LAYERS: tuple[Layer, ...] = (
    "concrete", "steel", "void", "cover", "leg", "hoop", "crosstie", "circular-tie", "bar"
)
CUT_LAYERS: tuple[Layer, ...] = ("concrete", "steel")
"""The faces a plan's title, dimensions and annotation are taken from (C5 record §3)."""
Path3 = tuple[tuple[Vec3, ...], bool]  # points, closed


@dataclass(frozen=True, slots=True)
class Drawable:
    entity_id: int
    layer: Layer
    paths: tuple[Path3, ...]
    anchor: Vec3 | None
    label: str | None
    radius_mm: float = 0.0  # a bar's disc; 0 for everything else
    compound: bool = False
    """A v2 face (ADR 0039): `paths` are its outer boundary then its holes, one shape."""
