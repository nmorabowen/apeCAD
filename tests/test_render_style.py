"""The SVG drawing-style table (ADR 0031 §3, ADR 0033): every layer has a style, every
style is an office name, and the writer uses the table's ink."""

from __future__ import annotations

import re
from typing import get_args
from xml.etree import ElementTree as ET

from apeCAD import Document
from apeCAD.render import render_svg
from apeCAD.render.api import VIEW_NAMES
from apeCAD.render.drawable import SECTION_LAYERS, Layer
from apeCAD.render.style import (
    BLUE,
    SECTION_STYLE,
    SKETCH_STYLE,
    VIEW_TITLES,
    pen_px,
)

SVG_NS = "{http://www.w3.org/2000/svg}"
# ADR-005 D1: {0.10..0.50}mm {H|S}-{Grey|Dark Grey|Black|Blue}
_LINE_STYLE = re.compile(r"0\.[1-5]0mm [HS]-(Grey|Dark Grey|Black|Blue)")
# ADR-010 D1: {Role} [- Grey{N}] - {Opaque|Transparent}
_FILL_NAME = re.compile(
    r"(Solid|Concrete|Steel)( - (Grey(210|192|128)|Black|Blue))? - (Opaque|Transparent)"
)


def test_every_layer_has_a_style() -> None:
    assert set(get_args(Layer)) == set(SECTION_STYLE) | set(SKETCH_STYLE)
    assert tuple(SECTION_STYLE) == SECTION_LAYERS


def test_styles_use_office_names_and_pens() -> None:
    for name, style in {**SECTION_STYLE, **SKETCH_STYLE}.items():
        if style.stroke != "none":
            assert style.line_style is not None and _LINE_STYLE.fullmatch(style.line_style), name
            mm = float(style.line_style.split("mm")[0])
            assert style.stroke_width == pen_px(mm), name
        if style.fill_name is not None:
            assert _FILL_NAME.fullmatch(style.fill_name), name
        assert style.layer_name and style.layer_name == style.layer_name.upper(), name


def test_pens_keep_the_cut_projection_hierarchy() -> None:
    assert [pen_px(mm) for mm in (0.10, 0.20, 0.30, 0.40, 0.50)] == [0.75, 1.0, 1.5, 2.0, 2.5]
    assert SECTION_STYLE["concrete"].stroke_width > SECTION_STYLE["hoop"].stroke_width
    assert SKETCH_STYLE["edge"].stroke_width > SKETCH_STYLE["solid"].stroke_width
    for rebar in ("hoop", "crosstie", "bar"):
        assert SECTION_STYLE[rebar].stroke == BLUE


def test_titles_and_annotation_are_english_and_blue() -> None:
    doc = Document()
    doc.add_point(0.0, 0.0, 0.0)
    assert set(VIEW_TITLES) == set(VIEW_NAMES)
    for view, title in VIEW_TITLES.items():
        root = ET.fromstring(render_svg(doc, view=view).svg)
        heading = [t for t in root.iter(f"{SVG_NS}text") if t.get("class") == "view-title"]
        assert [t.text for t in heading] == [title]
        legend = next(g for g in root.iter(f"{SVG_NS}g") if g.get("class") == "legend")
        assert legend.get("fill") == BLUE and legend.get("stroke") == BLUE
