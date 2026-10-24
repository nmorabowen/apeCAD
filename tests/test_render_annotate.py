"""Section annotation in the SVG render (ADR 0031 §3.5, spec ape-design §4 D4).

Annotation is derived at render time: tags with leaders, overall dimensions and a scale
note. It never writes an op, never changes the section-draft export, and turns off with
`annotate=False` (or `annotate=false` on `/api/render.svg`).
"""

from __future__ import annotations

import itertools
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable

import pytest

from _section_fixtures import BUILDERS
from apeCAD.document import Document
from apeCAD.entities import Bar, ConcreteFace, Crosstie, Hoop, WallLeg
from apeCAD.render import render_svg
from apeCAD.render.annotate import (
    STANDARD_SCALES,
    TAG_CHAR_PX,
    Layout,
    ToPx,
    crosses,
    dimension_text_boxes,
    leaders,
    plan_layout,
    section_notes,
)
from apeCAD.render.api import _bounds  # pyright: ignore[reportPrivateUsage]
from apeCAD.render.labels import text_box
from apeCAD.render.query import render_from_query
from apeCAD.render.scene import drawables, entity_map
from apeCAD.render.style import TEXT_PX
from apeCAD.render.views import VIEWS
from apeCAD.section_draft import section_draft
from test_render import _check_golden  # pyright: ignore[reportPrivateUsage]
from test_render_section import pier

SVG_NS = "{http://www.w3.org/2000/svg}"
Box = tuple[float, float, float, float]

CASES: dict[str, Callable[[], Document]] = {"pier": pier, **BUILDERS}


def _render(doc: Document, width: int = 1200, height: int = 500) -> ET.Element:
    return ET.fromstring(render_svg(doc, view="top", width=width, height=height).svg)


def _group(root: ET.Element, cls: str) -> list[ET.Element]:
    return [g for g in root.iter(f"{SVG_NS}g") if g.get("class") == cls]


def _tag_boxes(root: ET.Element) -> list[tuple[str, Box]]:
    out: list[tuple[str, Box]] = []
    for tag in _group(root, "tag"):
        text = tag.find(f"{SVG_NS}text")
        assert text is not None and text.text
        x, y = float(text.get("x", "0")), float(text.get("y", "0"))
        width = len(text.text) * TAG_CHAR_PX
        if text.get("text-anchor") == "end":
            x -= width
        out.append((text.text, (x, y - TEXT_PX, x + width, y + 2.0)))
    return out


def _concrete_box(root: ET.Element) -> Box:
    paths = (p for g in _group(root, "concrete") for p in g.iter(f"{SVG_NS}path"))
    data = " ".join(p.get("d", "") for p in paths)
    pts = [(float(x), float(y)) for x, y in re.findall(r"[ML](-?[\d.]+) (-?[\d.]+)", data)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _layout(doc: Document, width: int, height: int) -> Layout:
    entities = entity_map(doc)
    items = drawables(entities, set(entities), None)
    notes = section_notes(VIEWS["top"], entities, items, labels=True)  # as render_svg
    bounds = _bounds(VIEWS["top"], items)
    assert notes is not None and bounds is not None
    layout = plan_layout(notes, bounds, width, height, 0.05)
    assert layout is not None
    return layout


def _to_px(layout: Layout, width: int, height: int) -> ToPx:
    (cu, cv), s = layout.centre_mm, layout.scale_px_per_mm
    return lambda uv: (width / 2.0 + (uv[0] - cu) * s, height / 2.0 - (uv[1] - cv) * s)


def _overlap(a: Box, b: Box) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


@pytest.mark.parametrize("name", sorted(CASES))
def test_annotated_golden(name: str) -> None:
    svg = render_svg(CASES[name](), view="top", width=1200, height=500).svg
    ET.fromstring(svg)
    _check_golden(f"section_{name}_top_annotated", svg)


@pytest.mark.parametrize(("width", "height"), [(1200, 500), (800, 600)])  # 800 x 600: default
@pytest.mark.parametrize("name", sorted(CASES))
def test_tags_clear_each_other_the_concrete_and_the_frame(
    name: str, width: int, height: int
) -> None:
    root = _render(CASES[name](), width, height)
    tags = _tag_boxes(root)
    assert tags, "a section gets tags"
    concrete = _concrete_box(root)
    for (a_text, a), (b_text, b) in itertools.combinations(tags, 2):
        assert not _overlap(a, b), (a_text, b_text)
    for text, box in tags:
        assert not _overlap(box, concrete), text
        assert box[0] >= 0.0 and box[2] <= width and box[1] >= 0.0 and box[3] <= height, text
    for dim in _group(root, "dimension"):
        label = dim.find(f"{SVG_NS}text")
        assert label is not None and label.text and label.text.isdigit()
    layout = _layout(CASES[name](), width, height)
    to_px = _to_px(layout, width, height)
    for box in dimension_text_boxes(layout.notes, to_px, leaders(layout)):
        for line in leaders(layout):
            for a, b in zip(line, line[1:], strict=False):
                assert not crosses(box, a, b), "a leader crosses a dimension text"
        for text, tag in tags:
            assert not _overlap(box, tag), text


def test_pier_tags_sit_beside_the_group_they_label() -> None:
    root = _render(pier())
    tags = _tag_boxes(root)
    texts = [text for text, _ in tags]
    assert texts.count("6 Φ16") == 2  # one per end, each tie tag headed by its hoop's label
    assert {"BE-left: Tie Φ10 @ 100 mm", "BE-right: Tie Φ10 @ 100 mm"} <= set(texts)
    assert {"20 Φ16", "Cover 25 mm", "Φ10 @ 200 mm, 2 curtains"} <= set(texts)
    assert not any("Ø" in text for text in texts), "the drawing prints Φ"
    ties = sorted(box[0] for text, box in tags if ": Tie " in text)
    concrete = _concrete_box(root)
    third = (concrete[2] - concrete[0]) / 3.0
    assert ties[0] < concrete[0] + third and ties[1] > concrete[2] - third
    for tag in _group(root, "tag"):  # leaders stay short: each stack sits by its group
        path = tag.find(f"{SVG_NS}path")
        assert path is not None
        ends = re.findall(r"[ML](-?[\d.]+) (-?[\d.]+)", path.get("d", ""))
        x0, x1 = float(ends[0][0]), float(ends[-1][0])  # target, then the stack
        assert abs(x1 - x0) < 0.25 * 1200, tag.findtext(f"{SVG_NS}text")
    dims = sorted(d.findtext(f"{SVG_NS}text") or "" for d in _group(root, "dimension"))
    assert dims == ["300", "3000"]


@pytest.mark.parametrize("name", sorted(CASES))
def test_annotated_drawings_use_a_standard_scale(name: str) -> None:
    result = render_svg(CASES[name](), view="top")
    note = re.search(r"SCALE 1:(\d+)", result.svg)
    assert note is not None and int(note.group(1)) in STANDARD_SCALES
    assert result.scale_px_per_mm == pytest.approx(5.0 / int(note.group(1)))


def test_crosstie_and_web_steel_tags() -> None:
    texts = {text for text, _ in _tag_boxes(_render(BUILDERS["c_wall_crossties"]()))}
    assert any(text.startswith("Crosstie Φ") and " @ " in text for text in texts), texts
    walls = {text for text, _ in _tag_boxes(_render(BUILDERS["rect_boundary_hoops"]()))}
    assert any(text.endswith("curtains") for text in walls), walls


def test_scale_note_sits_under_the_section_title() -> None:
    root = _render(pier())
    note = [t for t in root.iter(f"{SVG_NS}text") if t.get("class") == "scale-note"]
    assert len(note) == 1 and re.fullmatch(r"SCALE 1:\d+", note[0].text or "")


def test_annotate_off_gives_the_bare_drawing() -> None:
    doc = pier()
    bare = render_svg(doc, view="top", annotate=False).svg
    assert 'class="annotation"' not in bare and "SCALE 1:" not in bare
    assert render_from_query(doc, "view=top&annotate=false").svg == bare
    assert 'class="annotation"' in render_from_query(doc, "view=top").svg


def test_annotation_is_drawn_not_stored() -> None:
    doc = BUILDERS["c_wall_crossties"]()
    before_ops, before_draft = doc.to_json(), section_draft(doc, commit=None)
    render_svg(doc, view="top")
    assert doc.to_json() == before_ops
    assert section_draft(doc, commit=None) == before_draft


def test_only_a_plan_of_a_section_is_annotated() -> None:
    doc = pier()
    assert 'class="annotation"' not in render_svg(doc, view="front").svg
    assert 'class="annotation"' not in render_svg(Document(), view="top").svg
    tiny = render_svg(doc, view="top", width=200, height=120).svg
    assert 'class="annotation"' not in tiny, "too small to annotate legibly"


def _labelled(name: str) -> Document:
    """The fixture with a label on more kinds of entity than the face and the hoops: the
    first and last bar, the first crosstie and the first wall leg."""
    doc = CASES[name]()
    entities = entity_map(doc)
    bars = [e for e in entities.values() if isinstance(e, Bar)]
    extra = [bars[0], bars[-1]]
    extra += [e for e in entities.values() if isinstance(e, Crosstie)][:1]
    extra += [e for e in entities.values() if isinstance(e, WallLeg)][:1]
    for i, entity in enumerate(extra):
        doc.set_label(entity.entity_id, f"L-{i + 1}")
    return doc


def _labels(root: ET.Element) -> list[tuple[str, Box]]:
    out: list[tuple[str, Box]] = []
    for t in root.iter(f"{SVG_NS}text"):
        if t.get("data-for") and t.text:
            x, y = float(t.get("x", "0")), float(t.get("y", "0"))
            out.append((t.text, text_box(x, y, t.get("text-anchor") == "end", len(t.text))))
    return out


def _outline(root: ET.Element) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for g in _group(root, "concrete"):
        for path in g.iter(f"{SVG_NS}path"):
            pts = [(float(x), float(y))
                   for x, y in re.findall(r"[ML](-?[\d.]+) (-?[\d.]+)", path.get("d", ""))]
            segments += list(zip(pts, pts[1:] + pts[:1], strict=True))
    return segments


@pytest.mark.parametrize(("width", "height"), [(1200, 500), (800, 600)])
@pytest.mark.parametrize("name", sorted(CASES))
def test_labels_clear_tags_dimensions_and_the_outline(name: str, width: int, height: int) -> None:
    doc = _labelled(name)
    root = _render(doc, width, height)
    labels = _labels(root)
    assert {text for text, _ in labels} >= {"L-1", "L-2"}, labels
    tags = _tag_boxes(root)
    layout = _layout(doc, width, height)
    dims = dimension_text_boxes(layout.notes, _to_px(layout, width, height), leaders(layout))
    outline = _outline(root)
    for (a_text, a), (b_text, b) in itertools.combinations(labels, 2):
        assert not _overlap(a, b), (a_text, b_text)
    for text, box in labels:
        assert box[0] >= 0.0 and box[2] <= width and box[1] >= 0.0 and box[3] <= height, text
        for tag_text, tag in tags:
            assert not _overlap(box, tag), (text, tag_text)
        for dim in dims:
            assert not _overlap(box, dim), (text, "dimension text")
        for a, b in outline:
            assert not crosses(box, a, b), (text, "concrete outline")


@pytest.mark.parametrize("name", sorted(CASES))
def test_face_and_hoop_labels_are_not_drawn_twice(name: str) -> None:
    doc = CASES[name]()
    entities = entity_map(doc)
    root = _render(doc)
    drawn = {int(t.get("data-for", "0")) for t in root.iter(f"{SVG_NS}text") if t.get("data-for")}
    named = {e.entity_id for e in entities.values() if isinstance(e, (ConcreteFace, Hoop))}
    assert not drawn & named, "the title names the face; tie tags name the hoops"
    texts = {text for text, _ in _tag_boxes(root)}
    for hoop in (e for e in entities.values() if isinstance(e, Hoop)):
        assert any(text.startswith(f"{hoop.label}: Tie ") for text in texts), hoop.label
    bare = ET.fromstring(render_svg(doc, view="top", annotate=False).svg)
    assert {int(t.get("data-for", "0")) for t in bare.iter(f"{SVG_NS}text")
            if t.get("data-for")} >= named, "a bare drawing keeps every label"
    plain = {text for text, _ in _tag_boxes(_render_no_labels(doc))}
    assert not any(": Tie " in text for text in plain), "labels=false drops the prefix"


def _render_no_labels(doc: Document) -> ET.Element:
    return ET.fromstring(render_svg(doc, view="top", labels=False).svg)


def test_annotate_reexports_annotate_tags_symbols() -> None:
    from apeCAD.render import annotate, annotate_tags

    for name in annotate_tags.__all__:
        assert getattr(annotate, name) is getattr(annotate_tags, name), name

