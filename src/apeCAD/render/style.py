"""SVG drawing style of the section-mode entities: the one table to swap for APE styling.

Plain neutral ink for now. The APE design system (ADR 0031) is not approved yet; when its
drawing-style table lands it maps these layers onto APE lineweights and ink here, and
nowhere else in the SVG writer.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LayerStyle:
    fill: str = "none"
    fill_opacity: float = 1.0
    stroke: str = "none"
    stroke_width: float = 0.0
    dash: str | None = None  # SVG stroke-dasharray, px

    def attrs(self) -> str:
        parts = [f'fill="{self.fill}"']
        if self.fill != "none" and self.fill_opacity < 1.0:
            parts.append(f'fill-opacity="{self.fill_opacity:g}"')
        parts.append(f'stroke="{self.stroke}"')
        if self.stroke != "none":
            parts.append(f'stroke-width="{self.stroke_width:g}"')
            parts.append('stroke-linecap="round" stroke-linejoin="round"')
        if self.dash is not None:
            parts.append(f'stroke-dasharray="{self.dash}"')
        return " ".join(parts)


# Back to front: the writer draws the layers in this order.
SECTION_STYLE: dict[str, LayerStyle] = {
    "concrete": LayerStyle(fill="#c8ccd1", fill_opacity=0.6, stroke="#1f2933", stroke_width=1.5),
    "cover": LayerStyle(stroke="#7b8794", stroke_width=0.75, dash="6 4"),
    "leg": LayerStyle(stroke="#7b8794", stroke_width=0.75, dash="14 4 2 4"),
    "hoop": LayerStyle(stroke="#1f2933", stroke_width=1.25),
    "crosstie": LayerStyle(stroke="#1f2933", stroke_width=1.0),
    "bar": LayerStyle(fill="#1f2933"),
}

MIN_BAR_RADIUS_PX = 1.5
"""A bar never draws smaller than this, so it stays visible on a whole-building fit."""
