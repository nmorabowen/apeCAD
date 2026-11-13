"""Overlay legibility and the axes glyph in the SVG render (C8b; RGc3 findings F6 and F7).

Oracles, each named by what it must show:

- F6: over a drawn overlay, every outline, hoop, tie and bar of the section is drawn again,
  on a paper halo, inside the overlay group after its fields; with no overlay, none is.
- F6 (review round 1, F1): the valued circles and points come after that ink, each a fill of
  at least `MARKER_MIN_RADIUS_PX` with its `--ink-edge` ring outside the fill, on a paper disc
  under it; a styled one is drawn exactly as styled. Pixel oracle at 1:25 on the reviewer's
  reproducer (`rect_boundary_hoops`, `v2_rect_wall_results.json`, 800 x 600): the centre pixel
  of each bar marker is its status colour, in the SVG (an analytic point sampler, and resvg
  when the `png` extra is installed) and in the client (`tests/js/_raster.mjs` under Node).
- F7: every section plan carries one axes glyph at the world origin, x right and y up, at a
  fixed size on screen, under the annotation (review F2), and again inside an overlay so a
  field never hides it; a sketch, or any view but the plan, carries none.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import struct
import subprocess
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path
from typing import Any

import pytest

from _section_fixtures import rect_boundary_hoops
from _section_fixtures_v2 import BUILDERS_V2
from apeCAD.document import Document
from apeCAD.render import render_svg
from apeCAD.render.overlay import COLOR_TOKENS
from apeCAD.render.style import BACKGROUND, BLUE, SECTION_STYLE
from apeCAD.render.svg import AXES_ARM_PX, INK_LAYERS, MARKER_MIN_RADIUS_PX, MARKER_RING
from apeCAD.scratchpad.section_assets import SECTION_DIR
from apeCAD.scratchpad.transport import handle

SVG_NS = "{http://www.w3.org/2000/svg}"
HERE = Path(__file__).resolve().parent
RESULTS = HERE / "fixtures" / "section_overlay" / "valid"
DRAFTS = HERE / "fixtures" / "section_draft_v2"
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
    group = top[order.index("overlay")]
    inner = [_class(g) for g in group]
    assert inner.count("section-ink") == 1 and "section-ink" not in order
    # After every field layer, before the valued markers and the legends.
    at = inner.index("section-ink")
    assert at > max(i for i, c in enumerate(inner) if c == "overlay-layer")
    assert at < min(i for i, c in enumerate(inner) if c in ("overlay-markers", "overlay-legend"))
    ink = group[at]
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


def test_valued_markers_come_last_ringed_outside_a_minimum_fill_on_a_paper_disc() -> None:
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
    result = render_svg(rect_boundary_hoops(), view="top", overlay=overlay)
    assert result.scale_px_per_mm == pytest.approx(0.2)  # 1:25: the 8 mm radius is 1.6 px
    group = next(g for g in ET.fromstring(result.svg) if _class(g) == "overlay")
    kids = list(group)
    layer, ink, axes, markers = kids[0], kids[1], kids[2], kids[3]
    assert (_class(layer), _class(ink), _class(axes), _class(markers)) == (
        "overlay-layer", "section-ink", "axes", "overlay-markers")
    assert markers.get("data-layer") == "b"
    styled = list(layer)
    assert len(styled) == 1 and (styled[0].get("fill"), styled[0].get("stroke")) == (
        "#123456", "none")  # drawn as styled, in its layer, at its own 1.6 px
    assert float(styled[0].get("r") or 0) == pytest.approx(1.6)
    circles = list(markers)
    assert len(circles) == 4  # each valued marker: a paper disc, then the marker
    assert MARKER_MIN_RADIUS_PX == 3.0
    for disc, mark, fill in ((circles[0], circles[1], "#c64a1a"),
                             (circles[2], circles[3], "#2f74ad")):
        assert (disc.get("fill"), disc.get("stroke")) == (BACKGROUND, "none")
        assert disc.get("data-value") is None  # the paper disc carries no data
        assert (mark.get("fill"), mark.get("stroke"), mark.get("stroke-width")) == (
            fill, MARKER_RING, "1")
        # The fill reaches r - 0.5 = 3 px, the 1 px ring lies outside it, the paper 2 px past it.
        assert float(mark.get("r") or 0) == pytest.approx(MARKER_MIN_RADIUS_PX + 0.5)
        assert float(disc.get("r") or 0) == pytest.approx(MARKER_MIN_RADIUS_PX + 2.0)
        assert [disc.get(k) for k in ("cx", "cy")] == [mark.get(k) for k in ("cx", "cy")]
    assert circles[1].get("data-ids") == "3" and circles[1].get("data-value") == "yielded"


# --- F6 (review F1): the pixel oracle at 1:25 -------------------------------------------------

YIELDED, ELASTIC = "#d73027", "#1a9850"  # the fixture's categorical colours
BAR_MARKERS = (((43.0, -43.0), YIELDED), ((2957.0, -43.0), ELASTIC), ((1500.0, -150.0), YIELDED))
"""The reproducer's bar markers: the yielded corner bar (ids 12, 13), the elastic far corner
bar, and the yielded point at mid-wall (`v2_rect_wall_results.json`, layer `bars`)."""


def _reproducer() -> tuple[Document, Json, Json]:
    draft = json.loads((DRAFTS / "rect_boundary_hoops.json").read_text(encoding="utf-8"))
    overlay = json.loads((RESULTS / "v2_rect_wall_results.json").read_text(encoding="utf-8"))
    return rect_boundary_hoops(), draft, overlay


def _path_subpaths(d: str) -> list[tuple[list[tuple[float, float]], bool]]:
    """M, L, Z, h and v only: what `render/svg.py` and `overlay.py` write."""
    subs: list[tuple[list[tuple[float, float]], bool]] = []
    for cmd, args in re.findall(r"([MLZhv])([^MLZhv]*)", d):
        nums = [float(v) for v in args.split()]
        if cmd == "M":
            subs.append(([(nums[0], nums[1])], False))
        elif cmd == "L":
            subs[-1][0].append((nums[0], nums[1]))
        elif cmd in "hv":
            x, y = subs[-1][0][-1]
            subs[-1][0].append((x + nums[0], y) if cmd == "h" else (x, y + nums[0]))
        else:
            subs[-1] = (subs[-1][0], True)
    return subs


def _seg(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = dx * dx + dy * dy
    t = 0.0 if n == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / n))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def _inside(p: tuple[float, float], ring: list[tuple[float, float]]) -> bool:
    hit = False
    for (xi, yi), (xj, yj) in zip(ring, ring[-1:] + ring[:-1], strict=True):
        if (yi > p[1]) != (yj > p[1]) and p[0] < (xj - xi) * (p[1] - yi) / (yj - yi) + xi:
            hit = not hit
    return hit


def _sample_svg(svg: str, points: list[tuple[float, float]]) -> list[str | None]:
    """The colour each point's pixel centre is left with, painter's order, no anti-aliasing:
    the last fill that holds it or stroke within half its width. Text is ignored."""
    colours: list[str | None] = [None] * len(points)

    def walk(el: ET.Element, style: dict[str, str]) -> None:
        tag = el.tag.replace(SVG_NS, "")
        if tag in ("text", "defs"):
            return
        mine = {**style, **{k: v for k, v in el.attrib.items()
                            if k in ("fill", "stroke", "stroke-width")}}
        fill, stroke = mine.get("fill", "#000000"), mine.get("stroke", "none")
        half = float(mine.get("stroke-width", "1")) / 2.0
        for i, p in enumerate(points):
            if tag == "rect":
                x, y = float(el.get("x", "0")), float(el.get("y", "0"))
                w, h = float(el.get("width", "0")), float(el.get("height", "0"))
                if fill != "none" and x <= p[0] <= x + w and y <= p[1] <= y + h:
                    colours[i] = fill
            elif tag == "circle":
                d = math.hypot(p[0] - float(el.get("cx", "0")), p[1] - float(el.get("cy", "0")))
                r = float(el.get("r", "0"))
                if fill != "none" and d < r:
                    colours[i] = fill
                if stroke != "none" and abs(d - r) <= half:
                    colours[i] = stroke
            elif tag == "path":
                subs = _path_subpaths(el.get("d", ""))
                if fill != "none" and sum(_inside(p, pts) for pts, _ in subs if len(pts) > 2) % 2:
                    colours[i] = fill
                if stroke != "none":
                    for pts, closed in subs:
                        seq = [*pts, pts[0]] if closed else pts
                        if any(_seg(p, a, b) <= half for a, b in zip(seq, seq[1:])):
                            colours[i] = stroke
        for child in el:
            walk(child, mine)

    walk(ET.fromstring(svg), {})
    return colours


def _png_pixel(png: bytes, x: int, y: int) -> str:
    """One pixel of an 8-bit RGB or RGBA PNG, decoded with the stdlib (filters 0-4)."""
    pos, idat, width, bpp = 8, b"", 0, 4
    while pos < len(png):
        size, kind = struct.unpack(">I4s", png[pos : pos + 8])
        body = png[pos + 8 : pos + 8 + size]
        pos += 12 + size
        if kind == b"IHDR":
            width, _h, depth, colour = struct.unpack(">IIBB", body[:10])
            assert depth == 8 and colour in (2, 6), (depth, colour)
            bpp = 4 if colour == 6 else 3
        elif kind == b"IDAT":
            idat += body
    raw, stride = zlib.decompress(idat), width * bpp
    prev = bytearray(stride)
    for row in range(y + 1):
        start = row * (stride + 1)
        kind, line = raw[start], bytearray(raw[start + 1 : start + 1 + stride])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b, c = prev[i], (prev[i - bpp] if i >= bpp else 0)
            base = (0, a, b, (a + b) // 2)[kind] if kind < 4 else min(
                (abs(b - c), 0, a), (abs(a - c), 1, b), (abs(a + b - 2 * c), 2, c))[2]
            line[i] = (line[i] + base) & 255
        prev = line
    return "#{:02x}{:02x}{:02x}".format(*prev[x * bpp : x * bpp + 3])


def _centres(low: list[float], high: list[float], scale: float) -> list[tuple[float, float]]:
    return [((x - low[0]) * scale, (high[1] - y) * scale) for (x, y), _ in BAR_MARKERS]


DISC = ((0.0, 0.0), (2.0, 0.0), (-2.0, 0.0), (0.0, 2.0), (0.0, -2.0))
"""Each marker's centre and four points 2 px from it: inside the 3 px minimum fill. At 1:25 a
16 mm bar is 1.6 px, so before the fix only the centre was the status colour: 2 px out was its
ring and the bar's ink ring, which hid the colour on screen (review F1)."""


def _disc(centres: list[tuple[float, float]]) -> list[tuple[float, float]]:
    return [(x + dx, y + dy) for x, y in centres for dx, dy in DISC]


def _want() -> list[str]:
    return [colour for _at, colour in BAR_MARKERS for _point in DISC]


WINDOW_1_25 = ((-500.0, -1650.0, 0.0), (3500.0, 1350.0, 0.0))
"""4000 mm across 800 px: exactly 0.2 px/mm, the 1:25 plan's scale, with no annotation (a
window turns it off), so nothing but the section and the overlay sits on a bar's centre."""


def test_at_1_to_25_each_bar_marker_centre_pixel_is_its_status_colour_in_the_svg() -> None:
    doc, _draft, overlay = _reproducer()
    result = render_svg(doc, view="top", overlay=overlay, window=WINDOW_1_25, margin=0.0)
    assert result.scale_px_per_mm == pytest.approx(0.2)
    centres = _centres(result.extents_mm["min"], result.extents_mm["max"], result.scale_px_per_mm)
    assert _sample_svg(result.svg, _disc(centres)) == _want()


def test_on_the_annotated_1_to_25_plan_the_status_colour_shows_beside_each_leader_dot() -> None:
    """The reviewer's 800 x 600 render: a tag's leader ends in a 1 px annotation dot exactly on
    the bar it names, above the overlay (ADR 0041), so the centre is that dot. 2 px right of
    it and 2 px below it, inside the 3 px fill and clear of every leader, is the status colour."""
    doc, _draft, overlay = _reproducer()
    result = render_svg(doc, view="top", overlay=overlay)
    assert (result.width, result.height, result.scale_px_per_mm) == (800, 600, pytest.approx(0.2))
    centres = _centres(result.extents_mm["min"], result.extents_mm["max"], result.scale_px_per_mm)
    beside = [(x + dx, y + dy) for x, y in centres for dx, dy in ((2.0, 0.0), (0.0, 2.0))]
    want = [colour for _at, colour in BAR_MARKERS for _side in range(2)]
    assert _sample_svg(result.svg, beside) == want


def test_at_1_to_25_the_rasterised_png_agrees_where_resvg_is_installed() -> None:
    pytest.importorskip("resvg_py", reason="the png extra rasterises; CI installs dev and mcp")
    from apeCAD.render import render_png

    doc, _draft, overlay = _reproducer()
    result = render_svg(doc, view="top", overlay=overlay, window=WINDOW_1_25, margin=0.0)
    png = render_png(doc, view="top", overlay=overlay, window=WINDOW_1_25, margin=0.0).png
    centres = _centres(result.extents_mm["min"], result.extents_mm["max"], result.scale_px_per_mm)
    for (x, y), colour in zip(_disc(centres), _want(), strict=True):
        got = _png_pixel(png, int(x), int(y))  # anti-aliased: each channel within 24 of it
        assert all(abs(int(got[k : k + 2], 16) - int(colour[k : k + 2], 16)) <= 24
                   for k in (1, 3, 5)), (x, y, got, colour)


def test_at_1_to_25_each_bar_marker_centre_pixel_is_its_status_colour_in_the_client(
    tmp_path: Path,
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    _doc, draft, overlay = _reproducer()
    reply = handle({"transport_version": 1, "action": "load", "payload": draft})
    assert reply["ok"] is True
    (tmp_path / "scene.json").write_text(json.dumps(reply["scene"]), encoding="utf-8")
    (tmp_path / "overlay.json").write_text(json.dumps(overlay), encoding="utf-8")
    raster = (HERE / "js" / "_raster.mjs").as_uri()
    canvas2d, overlay_js, transport = (SECTION_DIR.joinpath(n).as_uri() for n in (
        "canvas2d.js", "overlay.js", "transport.js"))
    # The client at 1:25 (0.2 px/mm), the wall centred in 800 x 600, wired as apecad-section.js
    # wires it: the fields, then the section ink (canvas2d), then the markers.
    markers = json.dumps([list(p) for p, _c in BAR_MARKERS])
    disc = json.dumps([list(d) for d in DISC])
    script = f"""
    import fs from "node:fs";
    import {{ samplingContext }} from {raster!r};
    import {{ createViewport, renderSectionCanvas }} from {canvas2d!r};
    import {{ paintOverlay, parseOverlay }} from {overlay_js!r};
    import {{ normalizeScene }} from {transport!r};
    const read = (n) => JSON.parse(fs.readFileSync({str(tmp_path)!r} + "/" + n, "utf8"));
    const scene = normalizeScene(read("scene.json")), overlay = parseOverlay(read("overlay.json"));
    const view = createViewport({{ width: 800, height: 600 }});
    view.scale = 0.2; view.panX = 400 - 1500 * 0.2; view.panY = 300 + 150 * 0.2;
    const centres = {markers}.map((p) => view.worldToScreen(p));
    const at = centres.flatMap(([x, y]) => {disc}.map(([dx, dy]) => [x + dx, y + dy]));
    const s = samplingContext(at);
    renderSectionCanvas(s.canvas, view, {{ scene, gridOn: false,
      drawOverlay: (c, v) => paintOverlay(c, v, overlay, {{ pass: "field" }}),
      drawMarkers: (c, v) => paintOverlay(c, v, overlay, {{ pass: "markers" }}) }});
    console.log(JSON.stringify(s.colors));
    """
    out = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True,
                         text=True, timeout=60, check=False)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == _want()


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
