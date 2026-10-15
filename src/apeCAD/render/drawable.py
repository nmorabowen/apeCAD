"""The unit the SVG writer draws: one entity's world-space polylines on one layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from apeCAD.render.views import Vec3

Layer = Literal[
    "face", "solid", "edge", "point", "concrete", "cover", "leg", "hoop", "crosstie", "bar"
]
SECTION_LAYERS: tuple[Layer, ...] = ("concrete", "cover", "leg", "hoop", "crosstie", "bar")
Path3 = tuple[tuple[Vec3, ...], bool]  # points, closed


@dataclass(frozen=True, slots=True)
class Drawable:
    entity_id: int
    layer: Layer
    paths: tuple[Path3, ...]
    anchor: Vec3 | None
    label: str | None
    radius_mm: float = 0.0  # a bar's disc; 0 for everything else
