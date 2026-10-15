"""SVG render of section-mode entities (ADR 0024): concrete, cover, leg, hoops, ties, bars.

Regression for 2026-10-14: a 300 x 3000 pier drawn through the op API rendered only its
bar points, as dots. The pier here is built with the same ops.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET

import pytest

from _section_fixtures import rect_boundary_hoops
from apeCAD.catalog import apply
from apeCAD.document import Document
from apeCAD.entities import Bar, Point
from apeCAD.render import render_svg
from apeCAD.render.style import MIN_BAR_RADIUS_PX, SECTION_STYLE
from test_render import _check_golden  # pyright: ignore[reportPrivateUsage]

SVG_NS = "{http://www.w3.org/2000/svg}"


def pier() -> Document:
    """The 2026-10-14 pier: outline, leg, 25 mm cover, 2 x 16 Ø16 bars, two Ø10 hoops."""
    doc = Document()
    corners = [[0, 0, 0], [3000, 0, 0], [3000, 300, 0], [0, 300, 0]]
    face = apply(doc, "AddSectionOutline", {
        "point_ids": [{"xyz": c} for c in corners], "material": "H30", "label": "pier",
    }).created_id
    apply(doc, "AddWallLeg", {
        "start_id": {"xyz": [0, 150, 0]}, "end_id": {"xyz": [3000, 150, 0]},
        "thickness_mm": 300, "face_id": face,
        "horizontal": {"designation": "Ø10", "spacing_mm": 200, "curtains": 2},
    })
    apply(doc, "SetCover", {
        "face_id": face, "cover_mm": 25, "tie_diameter_mm": 10, "bar_diameter_mm": 16,
    })
    for edge in (0, 2):
        apply(doc, "AddBarsAlongEdge", {
            "face_id": face, "edge_index": edge, "designation": "Ø16", "count": 16,
        })
    for label, inside in (("BE-left", lambda x: x <= 600.0), ("BE-right", lambda x: x >= 2400.0)):
        ids = [bar.entity_id for bar in doc.bars() if inside(_bar_xy(doc, bar)[0])]
        apply(doc, "AddHoop", {
            "bar_ids": ids, "designation": "Ø10", "spacing_mm": 100, "label": label,
        })
    return doc


def _bar_xy(doc: Document, bar: Bar) -> tuple[float, float]:
    point = doc.entity(bar.point_id)
    assert isinstance(point, Point)
    return point.xyz_mm.x_mm, point.xyz_mm.y_mm


def _layer(root: ET.Element, name: str) -> list[ET.Element]:
    groups = [g for g in root.iter(f"{SVG_NS}g") if g.get("class") == name]
    assert len(groups) <= 1
    return [] if not groups else [g for g in groups[0] if g.get("data-id")]


def test_pier_golden_top() -> None:
    result = render_svg(pier(), view="top", annotate=False)
    ET.fromstring(result.svg)
    _check_golden("section_pier_top", result.svg)


def test_rect_boundary_hoops_golden_top() -> None:
    result = render_svg(
        rect_boundary_hoops(), view="top", width=1200, height=300, annotate=False
    )
    ET.fromstring(result.svg)
    _check_golden("section_rect_boundary_hoops_top", result.svg)


def test_pier_draws_every_section_entity() -> None:
    doc = pier()
    root = ET.fromstring(render_svg(doc, view="top").svg)
    counts = {name: len(_layer(root, name)) for name in SECTION_STYLE}
    assert counts == {"concrete": 1, "cover": 1, "leg": 1, "hoop": 2, "crosstie": 0, "bar": 32}
    # A bar's own point is drawn by its disc, not again as a dot.
    dots = {g.get("data-id") for g in _layer(root, "points")}
    assert not dots & {str(bar.point_id) for bar in doc.bars()}
    assert len(dots) == 6  # the four outline corners and the two leg ends
    labels = {t.text for t in root.iter(f"{SVG_NS}text") if t.get("data-for")}
    assert labels == {"pier", "BE-left", "BE-right"}


def test_crossties_draw_between_their_bars() -> None:
    root = ET.fromstring(render_svg(rect_boundary_hoops(), view="top").svg)
    assert len(_layer(root, "crosstie")) == 4
    assert len(_layer(root, "hoop")) == 2


def test_bars_draw_at_their_true_diameter() -> None:
    result = render_svg(pier(), view="top", width=2048, height=400)
    root = ET.fromstring(result.svg)
    radii = {float(c.get("r", "0")) for g in _layer(root, "bar") for c in g}
    assert radii == {round(8.0 * result.scale_px_per_mm, 2)}


def test_hoop_wraps_its_bars_by_bar_radius_plus_half_the_tie() -> None:
    doc = pier()
    result = render_svg(doc, view="top", width=2048, height=2048)
    root = ET.fromstring(result.svg)
    hoop = doc.entity_by_label("BE-left")
    group = next(g for g in _layer(root, "hoop") if g.get("data-id") == str(hoop.entity_id))
    ring = _path_points(group[:1])  # the ring; its hook ticks follow
    scale = result.scale_px_per_mm
    wrapped = [_bar_xy(doc, bar) for bar in doc.bars() if _bar_xy(doc, bar)[0] <= 600.0]
    centres = [_px(result.extents_mm, scale, xy) for xy in wrapped]
    gaps = [min(math.dist(p, c) for c in centres) / scale for p in ring]
    assert min(gaps) == pytest.approx(13.0, abs=0.05)  # 16 / 2 + 10 / 2
    assert max(gaps) == pytest.approx(13.0, abs=0.05)


def _px(extents: dict[str, list[float]], scale: float, xy: tuple[float, float]) -> tuple[
    float, float
]:
    u0, v1 = extents["min"][0], extents["max"][1]
    return (xy[0] - u0) * scale, (v1 - xy[1]) * scale


def _path_points(group: ET.Element | list[ET.Element]) -> list[tuple[float, float]]:
    data = " ".join(p.get("d", "") for p in group)
    pairs = re.findall(r"[ML](-?[\d.]+) (-?[\d.]+)", data)
    return [(float(x), float(y)) for x, y in pairs]


@pytest.mark.parametrize(("width", "height"), [(800, 600), (300, 600), (2048, 128), (64, 64)])
@pytest.mark.parametrize("show_ids", [False, True])
def test_the_whole_pier_is_inside_the_frame(width: int, height: int, show_ids: bool) -> None:
    result = render_svg(pier(), view="top", width=width, height=height, show_ids=show_ids)
    root = ET.fromstring(result.svg)
    margin_px = 0.05 * 3000.0 * result.scale_px_per_mm
    xs: list[float] = []
    ys: list[float] = []
    for name in SECTION_STYLE:
        for group in _layer(root, name):
            for x, y in _path_points(group):
                xs.append(x)
                ys.append(y)
            for c in group.iter(f"{SVG_NS}circle"):
                cx, cy, r = (float(c.get(k, "0")) for k in ("cx", "cy", "r"))
                xs += (cx - r, cx + r)
                ys += (cy - r, cy + r)
    # A bar never draws below MIN_BAR_RADIUS_PX, so a tiny frame may eat that much margin.
    slack = MIN_BAR_RADIUS_PX + 0.01
    assert min(xs) >= margin_px - slack and max(xs) <= width - margin_px + slack
    assert min(ys) >= 0.0 and max(ys) <= height
    for text in root.iter(f"{SVG_NS}text"):
        if not text.get("data-for") or width < 300:  # 64 px cannot hold "pier #5" at all
            continue
        x = float(text.get("x", "0"))
        span = 6.6 * len(text.text or "")
        left, right = (x - span, x) if text.get("text-anchor") == "end" else (x, x + span)
        assert left >= 0.0 and right <= width, text.text


def test_section_label_is_escaped() -> None:
    doc = pier()
    hoop = doc.entity_by_label("BE-right")
    doc.set_label(hoop.entity_id, 'BE <2> & "end"')
    svg = render_svg(doc, view="top").svg
    assert "BE &lt;2&gt; &amp; &quot;end&quot;" in svg
    ET.fromstring(svg)


def test_section_ids_highlight_and_limit_the_drawing() -> None:
    doc = pier()
    hoop = doc.entity_by_label("BE-left")
    marked = ET.fromstring(render_svg(doc, view="top", highlight=[hoop.entity_id]).svg)
    accent = [g for g in marked.iter(f"{SVG_NS}g") if g.get("data-highlight")]
    # The hoop and the bars it is built from.
    assert len(accent) == 1 + len(hoop.bar_ids)  # pyright: ignore[reportAttributeAccessIssue]
    only = render_svg(doc, view="top", ids=[hoop.entity_id])
    root = ET.fromstring(only.svg)
    assert len(_layer(root, "hoop")) == 1
    assert len(_layer(root, "bar")) == len(hoop.bar_ids)  # pyright: ignore[reportAttributeAccessIssue]
    assert _layer(root, "concrete") == []
    # The fit follows the hoop: about 600 mm of the 3000 mm pier.
    span = only.extents_mm["max"][0] - only.extents_mm["min"][0]
    assert span < 1000.0
