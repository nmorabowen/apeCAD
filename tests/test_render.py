"""SVG render (spec agent-surface-mcp §4 `render`, stage S4)."""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path

import pytest

from apeCAD.document import Document
from apeCAD.render import VIEW_NAMES, RenderArgumentError, render_svg
from apeCAD.render.query import render_from_query

GOLDEN_DIR = Path(__file__).resolve().parent / "fixtures" / "render"
# Set APECAD_UPDATE_GOLDEN=1 to rewrite the goldens after an intended change; review the diff.
UPDATE = os.environ.get("APECAD_UPDATE_GOLDEN") == "1"
SVG_NS = "{http://www.w3.org/2000/svg}"


def _line() -> Document:
    doc = Document()
    a = doc.add_point(0.0, 0.0, 0.0)
    b = doc.add_point(1000.0, 600.0, 400.0)
    doc.add_line(a.entity_id, b.entity_id, label="brace")
    return doc


def _face() -> Document:
    doc = Document()
    corners = [(0.0, 0.0), (1200.0, 0.0), (1200.0, 800.0), (0.0, 800.0)]
    ids = [doc.add_point(x, y, 0.0).entity_id for x, y in corners]
    doc.add_face(ids, label="deck")
    return doc


def _box() -> Document:
    doc = Document()
    doc.add_box((0.0, 0.0, 0.0), (1000.0, 600.0, 400.0), label="block")
    return doc


def _extruded_face() -> Document:
    doc = Document()
    outline = [(0.0, 0.0), (900.0, 0.0), (900.0, 300.0), (300.0, 300.0), (300.0, 700.0),
               (0.0, 700.0)]
    ids = [doc.add_point(x, y, 0.0).entity_id for x, y in outline]
    face = doc.add_face(ids)
    doc.extrude(face.entity_id, 500.0, label="ell")
    return doc


SCENES: dict[str, Callable[[], Document]] = {
    "line": _line,
    "face": _face,
    "box": _box,
    "extruded_face": _extruded_face,
}


def _check_golden(name: str, svg: str) -> None:
    path = GOLDEN_DIR / f"{name}.svg"
    if UPDATE:
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(svg.encode("utf-8"))
    assert path.is_file(), f"missing golden {path.name}; run with APECAD_UPDATE_GOLDEN=1"
    assert svg.encode("utf-8") == path.read_bytes(), f"{path.name} differs from the render"


@pytest.mark.parametrize("view", VIEW_NAMES)
@pytest.mark.parametrize("scene", sorted(SCENES))
def test_golden_views(scene: str, view: str) -> None:
    result = render_svg(SCENES[scene](), view=view)
    ET.fromstring(result.svg)
    assert result.view == view
    _check_golden(f"{scene}_{view}", result.svg)


def test_empty_draft_golden() -> None:
    result = render_svg(Document())
    assert result.view == "top"
    assert result.entities == 0
    assert "empty draft" in result.svg
    # No extents: a 1000 mm box plus the 5 % margin, fitted to the shorter side (600 px).
    assert result.scale_px_per_mm == pytest.approx(600.0 / 1100.0)
    _check_golden("empty_top", result.svg)


def test_output_is_deterministic() -> None:
    first = render_svg(_extruded_face(), view="iso", show_ids=True)
    second = render_svg(_extruded_face(), view="iso", show_ids=True)
    assert first.svg == second.svg


def test_default_view_is_iso_with_a_solid_else_top() -> None:
    assert render_svg(_box()).view == "iso"
    assert render_svg(_face()).view == "top"


def test_svg_shape_follows_the_spec() -> None:
    svg = render_svg(_box(), width=640, height=480).svg
    root = ET.fromstring(svg)
    assert root.get("viewBox") == "0 0 640 480"
    background = root.find(f"{SVG_NS}rect")
    assert background is not None and background.get("fill") == "#ffffff"
    ids = [g.get("data-id") for g in root.iter(f"{SVG_NS}g") if g.get("data-id")]
    assert len(ids) == len(set(ids))
    assert "iso" in svg and " mm</text>" in svg  # view name and scale bar


def test_size_is_clamped() -> None:
    small = render_svg(_line(), width=10, height=5)
    assert (small.width, small.height) == (64, 64)
    big = render_svg(_line(), width=5000, height=9999)
    assert (big.width, big.height) == (2048, 2048)
    assert 'width="2048" height="2048"' in big.svg
    with pytest.raises(RenderArgumentError):
        render_svg(_line(), width=True)


def _x_line() -> Document:
    doc = Document()
    a = doc.add_point(0.0, 0.0, 0.0)
    b = doc.add_point(1000.0, 0.0, 0.0)
    doc.add_line(a.entity_id, b.entity_id)
    return doc


@pytest.mark.parametrize(
    ("margin", "span_mm"),
    [(0.0, 1000.0), (0.05, 1100.0), (0.1, 1200.0), (0.9, 1800.0), (-1.0, 1000.0)],
)
def test_margin_pads_the_larger_extent_and_clamps(margin: float, span_mm: float) -> None:
    result = render_svg(_x_line(), view="top", width=800, height=600, margin=margin)
    assert result.scale_px_per_mm == pytest.approx(800.0 / span_mm)
    low, high = result.extents_mm["min"], result.extents_mm["max"]
    assert high[0] - low[0] == pytest.approx(span_mm)
    assert (low[0] + high[0]) / 2.0 == pytest.approx(500.0)


def test_margin_must_be_a_number() -> None:
    with pytest.raises(RenderArgumentError):
        render_svg(_line(), margin=float("nan"))


def test_single_point_gets_a_1000_mm_box() -> None:
    doc = Document()
    doc.add_point(50.0, 50.0, 0.0)
    result = render_svg(doc, view="top", width=500, height=500, margin=0.0)
    assert result.scale_px_per_mm == pytest.approx(0.5)


def test_label_is_xml_escaped() -> None:
    doc = Document()
    doc.add_point(0.0, 0.0, 0.0, label='<script>alert("x")</script> & co')
    svg = render_svg(doc).svg
    assert "<script" not in svg
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; co" in svg
    texts = [t.text for t in ET.fromstring(svg).iter(f"{SVG_NS}text")]
    assert '<script>alert("x")</script> & co' in texts


def test_labels_and_ids_toggle() -> None:
    plain = render_svg(_box(), labels=False).svg
    assert "block" not in plain
    tagged = render_svg(_box(), show_ids=True).svg
    assert re.search(r">block #\d+</text>", tagged)
    assert ">#1</text>" in tagged


def test_ids_draw_the_entity_and_what_it_is_built_from() -> None:
    doc = _box()
    solid_id = doc.solids()[0].entity_id
    face_id = doc.faces()[0].entity_id
    only_face = render_svg(doc, ids=[face_id], view="top")
    assert f'data-id="{face_id}"' in only_face.svg
    assert f'data-id="{solid_id}"' not in only_face.svg
    assert only_face.entities == 1 + 4 + 4  # face, its edges, its corners
    assert render_svg(doc, ids=[solid_id]).svg == render_svg(doc).svg


def test_ids_set_the_extents() -> None:
    doc = _x_line()
    far = doc.add_point(5000.0, 0.0, 0.0)
    result = render_svg(doc, ids=[far.entity_id], view="top", margin=0.0)
    assert result.extents_mm["min"][0] < 5000.0 < result.extents_mm["max"][0]
    assert result.extents_mm["min"][0] > 1000.0


def test_unknown_ids_are_invalid_arguments() -> None:
    with pytest.raises(RenderArgumentError, match="unknown entity id 99") as caught:
        render_svg(_line(), ids=[99])
    assert caught.value.code == "INVALID_ARGUMENT"
    with pytest.raises(RenderArgumentError):
        render_svg(_line(), highlight=[99])
    with pytest.raises(RenderArgumentError):
        render_svg(_line(), view="bottom")


def test_highlight_draws_on_top_in_the_accent() -> None:
    doc = _line()
    line_id = doc.lines()[0].entity_id
    svg = render_svg(doc, highlight=[line_id]).svg
    assert f'<g data-highlight="{line_id}">' in svg
    assert svg.index('class="highlight"') > svg.index('class="points"')
    assert svg.index('class="highlight"') < svg.index('class="text"')


def test_window_overrides_fit() -> None:
    window = ((-1000.0, -1000.0, 0.0), (3000.0, 2000.0, 0.0))
    result = render_svg(_line(), view="top", width=400, height=300, window=window, margin=0.0)
    assert result.scale_px_per_mm == pytest.approx(0.1)
    with pytest.raises(RenderArgumentError):
        render_svg(_line(), window=((1.0, 0.0, 0.0), (0.0, 0.0, 0.0)))


def _curves() -> Document:
    doc = Document()
    c = doc.add_point(0.0, 0.0, 0.0)
    doc.add_circle(c.entity_id, 500.0)
    doc.add_ellipse(doc.add_point(1500.0, 0.0, 0.0).entity_id, 400.0, 200.0)
    s = doc.add_point(0.0, 1000.0, 0.0)
    m = doc.add_point(500.0, 1500.0, 0.0)
    e = doc.add_point(1000.0, 1000.0, 0.0)
    doc.add_arc(s.entity_id, m.entity_id, e.entity_id)
    ctrl = [doc.add_point(x, y, 0.0).entity_id for x, y in
            [(0.0, 2000.0), (300.0, 2600.0), (700.0, 1400.0), (1000.0, 2000.0)]]
    doc.add_bezier(ctrl)
    return doc


def test_curves_follow_the_chord_error_at_the_final_scale() -> None:
    small = render_svg(_curves(), view="top", width=200, height=200)
    large = render_svg(_curves(), view="top", width=2000, height=2000)
    ET.fromstring(small.svg)
    assert small.entities == large.entities
    assert large.svg.count(" L") > small.svg.count(" L")


def test_round_profile_solid_draws_generators() -> None:
    doc = Document()
    circle = doc.add_circle(doc.add_point(0.0, 0.0, 0.0).entity_id, 300.0)
    solid = doc.extrude(circle.entity_id, 1000.0)
    svg = render_svg(doc, view="front").svg
    group = re.search(rf'<g data-id="{solid.entity_id}">(.*?)</g>', svg)
    assert group is not None and group.group(1).count("<path") == 4


def test_save_to_writes_under_the_root(tmp_path: Path) -> None:
    result = render_svg(_box(), save_to="out/box.svg", root=tmp_path)
    assert result.path == str((tmp_path / "out" / "box.svg").resolve())
    assert (tmp_path / "out" / "box.svg").read_bytes() == result.svg.encode("utf-8")


@pytest.mark.parametrize("save_to", ["../escape.svg", "a/../../escape.svg", ".", ""])
def test_save_to_outside_the_root_is_invalid(tmp_path: Path, save_to: str) -> None:
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(RenderArgumentError) as caught:
        render_svg(_box(), save_to=save_to, root=root)
    assert caught.value.code == "INVALID_ARGUMENT"
    assert not (tmp_path / "escape.svg").exists()


def test_save_to_absolute_path_outside_the_root_is_invalid(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(RenderArgumentError):
        render_svg(_box(), save_to=str(tmp_path / "escape.svg"), root=root)
    with pytest.raises(RenderArgumentError, match="needs a root"):
        render_svg(_box(), save_to="box.svg")


def test_query_string_mirrors_the_parameters() -> None:
    doc = _box()
    by_query = render_from_query(doc, "view=top&width=400&height=300&margin=0.1&show_ids=true")
    direct = render_svg(doc, view="top", width=400, height=300, margin=0.1, show_ids=True)
    assert by_query.svg == direct.svg
    windowed = render_from_query(doc, "view=top&window=0,0,0,2000,1000,0&margin=0")
    assert windowed.scale_px_per_mm == pytest.approx(0.4)


@pytest.mark.parametrize(
    "query",
    ["bogus=1", "width=wide", "labels=maybe", "window=1,2,3", "format=png", "view=top&view=iso",
     "ids=1,x"],
)
def test_bad_query_is_invalid_argument(query: str) -> None:
    with pytest.raises(RenderArgumentError):
        render_from_query(_box(), query)
