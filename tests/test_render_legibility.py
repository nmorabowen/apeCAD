"""Overlay legibility and the axes glyph in the SVG render (C8b; RGc3 findings F6 and F7).

Oracles, each named by what it must show:

- F6: over a drawn overlay, every outline, hoop, tie and bar of the section is drawn again,
  on a paper halo, above the overlay and below the annotation; with no overlay, none is.
- F6: a valued circle or point marker is ringed in `--ink-edge` on a paper halo; a styled one
  is drawn exactly as styled.
- F7: every section plan carries one axes glyph at the world origin, x right and y up, at a
  fixed size on screen; a sketch, or any view but the plan, carries none.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest

from _section_fixtures import rect_boundary_hoops
from _section_fixtures_v2 import BUILDERS_V2
from apeCAD.document import Document
from apeCAD.render import render_svg
from apeCAD.render.overlay import COLOR_TOKENS
from apeCAD.render.style import BACKGROUND, BLUE, SECTION_STYLE
from apeCAD.render.svg import AXES_ARM_PX, INK_LAYERS, MARKER_RING

SVG_NS = "{http://www.w3.org/2000/svg}"
RESULTS = Path(__file__).resolve().parent / "fixtures" / "section_overlay" / "valid"
Json = dict[str, Any]


def _class(el: ET.Element) -> str:
    return el.get("class") or ""


def _results() -> Json:
    return json.loads((RESULTS / "rect_wall_results.json").read_text(encoding="utf-8"))


def _top(svg: str) -> list[ET.Element]:
    return list(ET.fromstring(svg))


def _marks(group: ET.Element) -> list[ET.Element]:
    return [el for el in group.iter() if el.tag in (f"{SVG_NS}path", f"{SVG_NS}circle")]


# --- F6: the section's ink over the overlay -----------------------------------------------


def test_the_section_ink_is_drawn_again_over_the_overlay_on_a_halo() -> None:
    svg = render_svg(rect_boundary_hoops(), view="top", overlay=_results()).svg
    top = _top(svg)
    order = [_class(g) for g in top]
    assert order.count("section-ink") == 1
    assert order.index("overlay") < order.index("section-ink") < order.index("annotation")
    ink = top[order.index("section-ink")]
    passes = [(_class(g), g.get("data-layer")) for g in ink]
    drawn = [layer for layer in INK_LAYERS if layer in order]
    assert drawn == ["concrete", "hoop", "crosstie", "bar"]  # this wall's layers, back to front
    # All the halos first, then all the ink, each in the layers' order.
    assert passes == [("halo", layer) for layer in drawn] + [("ink", layer) for layer in drawn]
    for group in ink:
        layer = group.get("data-layer") or ""
        section = top[order.index(layer)]
        assert len(_marks(group)) == len(_marks(section)), layer  # every mark, none missed
        if _class(group) == "halo":
            assert group.get("stroke") == BACKGROUND
        else:
            assert group.get("stroke") == SECTION_STYLE[layer].stroke
    # A bar is a ring at its own radius, unfilled, with its halo just outside it.
    bars = top[order.index("bar")]
    halo, ring = (next(g for g in ink if g.get("data-layer") == "bar" and _class(g) == c)
                  for c in ("halo", "ink"))
    assert ink.get("fill") == "none"
    for disc, outer, inner in zip(_marks(bars), _marks(halo), _marks(ring), strict=True):
        r = float(disc.get("r") or 0)
        assert float(inner.get("r") or 0) == pytest.approx(r)
        assert float(outer.get("r") or 0) == pytest.approx(r + 1.0)
        assert inner.get("cx") == disc.get("cx") and inner.get("cy") == disc.get("cy")


def test_without_an_overlay_the_section_is_drawn_once() -> None:
    svg = render_svg(rect_boundary_hoops(), view="top").svg
    assert 'class="section-ink"' not in svg


# --- F6: valued markers ---------------------------------------------------------------------


def test_valued_markers_are_ringed_on_a_halo_and_styled_ones_are_drawn_as_styled() -> None:
    assert MARKER_RING == COLOR_TOKENS["--ink-edge"]  # the client paints the same token
    scale = {"kind": "categorical", "domain": ["elastic", "yielded"],
             "colors": ["#2f74ad", "#c64a1a"], "unit": "", "title": "Bars"}
    primitives = [
        {"kind": "circle", "center": [100, -100], "radius": 8, "value": "yielded", "ids": [3]},
        {"kind": "point", "at": [200, -100], "value": "elastic"},
        {"kind": "circle", "center": [300, -100], "radius": 8, "style": {"fill": "#123456"}},
    ]
    overlay = {"schema": "apeCAD.section-overlay", "version": 1, "units": "mm", "revision": 0,
               "layers": [{"id": "b", "label": "", "visible": True, "scale": scale,
                           "primitives": primitives}]}
    svg = render_svg(rect_boundary_hoops(), view="top", overlay=overlay).svg
    layer = next(g for g in ET.fromstring(svg).iter(f"{SVG_NS}g")
                 if _class(g) == "overlay-layer")
    circles = list(layer)
    assert len(circles) == 5  # two valued markers of two circles each, one styled circle
    for halo, mark, fill in ((circles[0], circles[1], "#c64a1a"),
                             (circles[2], circles[3], "#2f74ad")):
        assert (halo.get("fill"), halo.get("stroke"), halo.get("stroke-width")) == (
            "none", BACKGROUND, "3")
        assert halo.get("data-value") is None  # the halo carries no data
        assert (mark.get("fill"), mark.get("stroke"), mark.get("stroke-width")) == (
            fill, MARKER_RING, "1")
        assert [halo.get(k) for k in ("cx", "cy", "r")] == [mark.get(k) for k in ("cx", "cy", "r")]
    assert circles[1].get("data-ids") == "3" and circles[1].get("data-value") == "yielded"
    assert (circles[4].get("fill"), circles[4].get("stroke")) == ("#123456", "none")


# --- F7: the axes glyph ----------------------------------------------------------------------


def _numbers(d: str) -> list[float]:
    return [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", d)]


@pytest.mark.parametrize("name", sorted(BUILDERS_V2))
def test_every_section_plan_carries_the_axes_glyph_at_the_world_origin(name: str) -> None:
    result = render_svg(BUILDERS_V2[name]())
    top = _top(result.svg)
    axes = [g for g in top if _class(g) == "axes"]
    assert len(axes) == 1
    order = [_class(g) for g in top]
    assert order.index("axes") > max(order.index(c) for c in order if c in INK_LAYERS)
    assert order.index("axes") < order.index("text")  # under the labels, over the drawing
    # The origin's pixel, from the envelope alone: x right and y down from the frame's corner.
    low, high = result.extents_mm["min"], result.extents_mm["max"]
    ox = (0.0 - low[0]) * result.scale_px_per_mm
    oy = (high[1] - 0.0) * result.scale_px_per_mm
    halo, ink, x_label, y_label = list(axes[0])
    assert halo.get("d") == ink.get("d")
    assert (halo.get("stroke"), ink.get("stroke")) == (BACKGROUND, BLUE)
    d = ink.get("d") or ""
    shafts = re.findall(r"M(-?[\d.]+) (-?[\d.]+) L(-?[\d.]+) (-?[\d.]+)", d)
    x_shaft, y_shaft = (tuple(map(float, s)) for s in shafts[:3:2])
    assert x_shaft == pytest.approx((ox, oy, ox + AXES_ARM_PX, oy), abs=0.01)  # x right
    assert y_shaft == pytest.approx((ox, oy, ox, oy - AXES_ARM_PX), abs=0.01)  # y up
    square = _numbers(d.split("Z")[0])
    assert square[:2] == pytest.approx([ox - 2.5, oy - 2.5], abs=0.01)  # the origin's box
    assert (x_label.text, y_label.text) == ("x", "y")
    assert float(x_label.get("x") or 0) > ox + AXES_ARM_PX
    assert float(y_label.get("y") or 0) < oy


def test_the_glyph_does_not_move_with_the_drawing_scale() -> None:
    """A fixed size on screen: the same arms at 1:10 and at 1:25."""
    arms: set[tuple[float, ...]] = set()
    for name in ("rect_column_ties", "rect_boundary_hoops"):
        d = re.search(r'<g class="axes".*?<path d="([^"]+)"', render_svg(BUILDERS_V2[name]()).svg,
                      re.S)
        assert d is not None
        values = _numbers(d.group(1).split("Z")[1])  # the shafts and heads, absolute pairs
        x0, y0 = values[0], values[1]
        arms.add(tuple(round(v - (x0 if i % 2 == 0 else y0), 2) for i, v in enumerate(values)))
    assert len(arms) == 1


def _sketch() -> Document:
    doc = Document()
    doc.add_box((0.0, 0.0, 0.0), (1000.0, 600.0, 400.0), label="block")
    return doc


@pytest.mark.parametrize("view", ["top", "front", "iso"])
def test_a_sketch_and_a_section_seen_from_aside_carry_no_axes_glyph(view: str) -> None:
    assert 'class="axes"' not in render_svg(_sketch(), view=view).svg
    if view != "top":
        assert 'class="axes"' not in render_svg(rect_boundary_hoops(), view=view).svg
