"""SVG drawing style: APE pens, ink, fills and type per drawable layer (ADR 0031 §3).

The one table the SVG writer reads; a later DXF writer reads the same `line_style` /
`fill_name` / `layer_name` fields. Values are the office drawing standards: ADR-005 line
styles (`{mm}mm {S|H}-{colour}`), ADR-010 fills, ADR-004/007 annotation blue (0, 0, 119)
in Arial Narrow, ADR-009 Bahnschrift for view titles. The table per entity is in
AProjects/specs/ape-design.md §3.2.
"""

from __future__ import annotations

from dataclasses import dataclass

BLACK = "#000000"
DARK_GREY = "#808080"  # ADR-005 Dark Grey, ADR-010 Grey128
GREY210 = "#d2d2d2"  # ADR-010 Grey210, the concrete cut solid
BLUE = "#000077"  # ADR-004 annotation and rebar ink
HIGHLIGHT = "#c64a1a"  # agent review aid (ADR 0031 §3.6); never ink, never exported
BACKGROUND = "#ffffff"

PX_PER_PAPER_MM = 5.0
MIN_PEN_PX = 0.75


def pen_px(mm: float) -> float:
    """Screen width of an ADR-005 pen when the SVG has no plot scale (ADR 0031 §3.3)."""
    return max(MIN_PEN_PX, PX_PER_PAPER_MM * mm)


HIDDEN_DASH = "6 3"  # ADR-005 `H-` pattern on screen
COVER_DASH = "3 2"  # the same pattern, shorter, so a cover ring reads apart from a leg axis

WORKING_FONT = "Arial Narrow, Archivo Narrow, sans-serif"  # ADR-007, ADR-009 working face
DISPLAY_FONT = (  # ADR-009 display face, view titles only
    "Bahnschrift SemiBold Condensed, Bahnschrift, Saira SemiCondensed, Archivo Narrow, sans-serif"
)
TEXT_PX = PX_PER_PAPER_MM * 2.0  # ADR-007 default body note, 2.0 mm
TITLE_PX = PX_PER_PAPER_MM * 3.5  # ADR-007 view title, 3.5 mm


@dataclass(frozen=True, slots=True)
class LayerStyle:
    fill: str = "none"
    fill_opacity: float = 1.0
    stroke: str = "none"
    stroke_width: float = 0.0
    dash: str | None = None  # SVG stroke-dasharray, px
    line_style: str | None = None  # ADR-005 name, for the reader and for DXF
    fill_name: str | None = None  # ADR-010 name
    layer_name: str = ""  # DXF layer (ADR 0031 §3.7)

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


def _line(mm: float, pattern: str, colour: str, ink: str, layer: str, **kw: str) -> LayerStyle:
    dash = kw.get("dash", HIDDEN_DASH if pattern == "H" else None)
    return LayerStyle(
        stroke=ink,
        stroke_width=pen_px(mm),
        dash=dash,
        line_style=f"{mm:.2f}mm {pattern}-{colour}",
        layer_name=layer,
    )


# Back to front: the writer draws the section layers in this order.
SECTION_STYLE: dict[str, LayerStyle] = {
    "concrete": LayerStyle(
        fill=GREY210,
        stroke=BLACK,
        stroke_width=pen_px(0.40),
        line_style="0.40mm S-Black",
        fill_name="Solid - Grey210 - Transparent",
        layer_name="CONCRETE-CUT",
    ),
    # Dark Grey, not ADR-005 Grey: Grey 192 vanishes on the Grey210 cut.
    "cover": _line(0.10, "H", "Dark Grey", DARK_GREY, "COVER-GUIDE", dash=COVER_DASH),
    "leg": _line(0.10, "H", "Dark Grey", DARK_GREY, "WALL-AXIS"),
    "hoop": _line(0.30, "S", "Blue", BLUE, "HOOP"),
    "crosstie": _line(0.20, "S", "Blue", BLUE, "HOOP"),
    "bar": LayerStyle(
        fill=BLUE,
        stroke=BLUE,
        stroke_width=pen_px(0.10),
        line_style="0.10mm S-Blue",
        fill_name="Solid - Blue - Opaque",
        layer_name="BAR",
    ),
}

# The other drawables (spec §3.2): 3-D faces and solids in projection, sketch curves, points.
SKETCH_STYLE: dict[str, LayerStyle] = {
    "face": _line(0.20, "S", "Black", BLACK, "FACE"),
    "solid": _line(0.20, "S", "Black", BLACK, "SOLID-EDGE"),
    "edge": _line(0.30, "S", "Black", BLACK, "SKETCH"),
    "point": LayerStyle(fill=BLACK, layer_name="POINT"),
}

POINT_RADIUS_PX = PX_PER_PAPER_MM * 0.25  # a 0.5 mm disc
ANNOTATION_PEN_PX = pen_px(0.10)  # scale bar, leaders
TITLE_RULE_PX = pen_px(0.30)  # the view title's underline

MIN_BAR_RADIUS_PX = 1.5
"""A bar never draws smaller than this, so it stays visible on a whole-building fit."""

# Spec §3.3 (English, 2026-10-14) for the views render_svg offers; `view.name` stays the
# identifier in `data-view`.
VIEW_TITLES: dict[str, str] = {
    "top": "PLAN",
    "front": "FRONT ELEVATION",
    "right": "RIGHT ELEVATION",
    "iso": "ISOMETRIC",
}
SECTION_TITLE = "SECTION"
EMPTY_TEXT = "Empty drawing"
