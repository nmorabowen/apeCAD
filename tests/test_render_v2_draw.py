"""`render` draws v2 (C5 record §3 "render", §5 C5-S1; apeSection#58).

The oracles name the answer from outside the code under test: the committed fixtures' ids,
the op arguments (radii, rings), the scene payload's cover rings, the chord-error bound of a
regular n-gon, and an ezdxf readback. No check compares SVG bytes or trig-fed floats
beyond the writer's 0.01 px rounding; goldens are C5-S2's.
"""

from __future__ import annotations

import json
import math
import re
import xml.etree.ElementTree as ET
from typing import Any, cast

import pytest

from _section_fixtures_v2 import BUILDERS_V2, fixture_path_v2
from apeCAD import Document
from apeCAD.geometry import XYZ
from apeCAD.ops import PointAt
from apeCAD.render import render_svg
from apeCAD.render.api import CHORD_ERROR_PX, RenderArgumentError, RenderResult
from apeCAD.render.scene import drawables, entity_map
from apeCAD.render.style import BACKGROUND, BLACK, BLUE, DARK_GREY, GREY210, SECTION_STYLE
from apeCAD.render.tessellate import MAX_SEGMENTS, MIN_SEGMENTS, circle_segments
from apeCAD.scratchpad.payload import scene_payload

SVG_NS = "{http://www.w3.org/2000/svg}"
Json = dict[str, Any]
Px = tuple[float, float]
PX_TOL = 0.02  # the writer rounds to 0.01 px; this is twice that (record §3 "Goldens")
MATERIAL = {"concrete": "C30", "steel": "S355", "void": None}


def _at(x: float, y: float) -> PointAt:
    return PointAt(XYZ(float(x), float(y), 0.0))


def _square(cx: float, cy: float, half: float, cw: bool = False) -> list[PointAt]:
    ring = [(cx - half, cy - half), (cx + half, cy - half), (cx + half, cy + half),
            (cx - half, cy + half)]
    return [_at(x, y) for x, y in (ring[::-1] if cw else ring)]


def _root(result: RenderResult) -> ET.Element:
    return ET.fromstring(result.svg)


def _layer_order(root: ET.Element) -> list[str]:
    return [g.get("class", "") for g in root if g.tag == f"{SVG_NS}g"]


def _layer(root: ET.Element, name: str) -> ET.Element:
    (group,) = [g for g in root if g.tag == f"{SVG_NS}g" and g.get("class") == name]
    return group


def _member(root: ET.Element, name: str, entity_id: int) -> ET.Element:
    (group,) = [g for g in _layer(root, name) if g.get("data-id") == str(entity_id)]
    return group


def _subpaths(data: str) -> list[list[Px]]:
    """Each `M … Z` run of a path's data as its vertices, px."""
    out: list[list[Px]] = []
    for run in re.findall(r"M[^M]*", data):
        assert run.rstrip().endswith("Z"), run
        out.append([(float(x), float(y)) for x, y in re.findall(r"(-?[\d.]+) (-?[\d.]+)", run)])
    return out


def _px(result: RenderResult, xy: tuple[float, float]) -> Px:
    u0, v1 = result.extents_mm["min"][0], result.extents_mm["max"][1]
    s = result.scale_px_per_mm
    return (xy[0] - u0) * s, (v1 - xy[1]) * s


# ---- faces: ring / circle outer x no / ring / circle hole x role ------------------------


def _face_doc(role: str, outer: str, hole: str) -> tuple[Document, int]:
    doc = Document()
    material = MATERIAL[role]
    if outer == "ring":
        face = doc.add_section_face(role, material, point_ids=_square(0, 0, 200))
    else:
        face = doc.add_section_face(role, material, center_id=_at(0, 0), radius_mm=200.0)
    if hole in ("ring", "ring-cw"):
        doc.add_face_hole(face.entity_id, point_ids=_square(60, 0, 40, cw=hole == "ring-cw"))
    elif hole == "circle":
        doc.add_face_hole(face.entity_id, center_id=_at(60, 0), radius_mm=40.0)
    return doc, face.entity_id


def _assert_circle(result: RenderResult, loop: list[Px], centre: tuple[float, float], r: float):
    s = result.scale_px_per_mm
    cx, cy = _px(result, centre)
    for x, y in loop:
        assert math.hypot(x - cx, y - cy) == pytest.approx(r * s, abs=PX_TOL)
    sides = len(loop)  # a regular n-gon's chord error is r (1 - cos(pi / n))
    assert r * s * (1.0 - math.cos(math.pi / sides)) <= CHORD_ERROR_PX + 1e-9


def _assert_square(result: RenderResult, loop: list[Px], centre: tuple[float, float], h: float):
    cx, cy = centre
    corners = {(cx - h, cy - h), (cx + h, cy - h), (cx + h, cy + h), (cx - h, cy + h)}
    expected = sorted(_px(result, c) for c in corners)
    assert len(loop) == 4
    for got, want in zip(sorted(loop), expected, strict=True):
        assert got == pytest.approx(want, abs=PX_TOL)


@pytest.mark.parametrize("role", ["concrete", "steel", "void"])
@pytest.mark.parametrize("outer", ["ring", "circle"])
@pytest.mark.parametrize("hole", ["none", "ring", "ring-cw", "circle"])
def test_a_face_is_one_even_odd_path_with_its_holes(role: str, outer: str, hole: str) -> None:
    doc, face_id = _face_doc(role, outer, hole)
    result = render_svg(doc, view="top", annotate=False)
    root = _root(result)
    paths = list(_member(root, role, face_id))
    assert [p.tag for p in paths] == [f"{SVG_NS}path"]  # one compound path, never one per ring
    (path,) = paths
    assert path.get("fill-rule") == "evenodd"  # a hole stays open, whatever its winding
    loops = _subpaths(path.get("d", ""))
    assert len(loops) == (1 if hole == "none" else 2)
    if outer == "ring":
        _assert_square(result, loops[0], (0.0, 0.0), 200.0)
    else:
        _assert_circle(result, loops[0], (0.0, 0.0), 200.0)
    if hole == "circle":
        _assert_circle(result, loops[1], (60.0, 0.0), 40.0)
    elif hole != "none":
        _assert_square(result, loops[1], (60.0, 0.0), 40.0)
    assert result.entities >= 1


def test_role_styles_and_paint_order_follow_the_record() -> None:
    expected = ["concrete", "steel", "void", "cover", "leg", "hoop", "crosstie",
                "circular-tie", "bar"]  # fmt: skip
    assert list(SECTION_STYLE) == expected
    steel, void, tie = SECTION_STYLE["steel"], SECTION_STYLE["void"], SECTION_STYLE["circular-tie"]
    assert (steel.fill, steel.stroke, steel.line_style) == (DARK_GREY, BLACK, "0.40mm S-Black")
    assert (void.fill, void.fill_name, void.line_style) == (BACKGROUND, None, "0.40mm S-Black")
    assert (tie.stroke, tie.line_style, tie.dash) == (BLUE, "0.30mm S-Blue", None)


def test_a_void_made_before_what_it_cuts_still_paints_on_top() -> None:
    """Painting by id would put the void (id first) under the concrete (record §6)."""
    doc = Document()
    void = doc.add_section_face("void", None, point_ids=_square(0, 0, 50))
    steel = doc.add_section_face("steel", "S355", point_ids=_square(0, 0, 120))
    concrete = doc.add_section_face("concrete", "C30", point_ids=_square(0, 0, 200))
    assert void.entity_id < steel.entity_id < concrete.entity_id
    root = _root(render_svg(doc, view="top", annotate=False))
    order = [name for name in _layer_order(root) if name in MATERIAL]
    assert order == ["concrete", "steel", "void"]
    assert _layer(root, "void").get("fill") == BACKGROUND  # paper over what it cuts
    for role, face in (("concrete", concrete), ("steel", steel), ("void", void)):
        _member(root, role, face.entity_id)


def test_a_highlighted_face_keeps_its_hole_open() -> None:
    doc, face_id = _face_doc("steel", "circle", "circle")
    root = _root(render_svg(doc, view="top", highlight=[face_id], annotate=False))
    (group,) = [g for g in root if g.get("class") == "highlight"]
    (path,) = list(next(g for g in group if g.get("data-highlight") == str(face_id)))
    assert path.get("fill-rule") == "evenodd" and len(_subpaths(path.get("d", ""))) == 2


def test_steel_fill_clears_the_adr_0038_contrast_gate() -> None:
    """Canvas strokes need >= 2.2:1 (ADR 0038 §2): the steel fill against the concrete fill,
    its own black outline, and a blue bar drawn over it."""

    def luminance(hex_colour: str) -> float:
        channels = [int(hex_colour[i : i + 2], 16) / 255.0 for i in (1, 3, 5)]
        lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

    def contrast(a: str, b: str) -> float:
        hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
        return (hi + 0.05) / (lo + 0.05)

    fill = SECTION_STYLE["steel"].fill
    for other in (GREY210, BLACK, BLUE):
        assert contrast(fill, other) >= 2.2, other


# ---- circular ties, cover guides --------------------------------------------------------


def test_the_spiral_draws_at_its_centreline_radius() -> None:
    doc = BUILDERS_V2["circular_column_spiral"]()
    (tie,) = doc.circular_ties()
    assert tie.centerline_radius_mm == 255.0  # the fixture's op argument
    result = render_svg(doc, view="top")
    (path,) = list(_member(_root(result), "circular-tie", tie.entity_id))
    (loop,) = _subpaths(path.get("d", ""))
    _assert_circle(result, loop, (0.0, 0.0), 255.0)  # not the face's 300, nor a diameter


def _scene_guides(doc: Document) -> dict[int, Json]:
    guides = cast(list[Json], scene_payload(doc)["cover_guides"])
    return {cast(int, g["entity_id"]): g for g in guides}


@pytest.mark.parametrize("name", sorted(BUILDERS_V2))
def test_cover_rings_are_the_scenes(name: str) -> None:
    doc = BUILDERS_V2[name]()
    entities = entity_map(doc)
    scene = _scene_guides(doc)
    for guide in doc.cover_guides():
        (d,) = drawables(entities, {guide.entity_id}, 0.5)
        assert d.layer == "cover"
        assert [[x, y] for x, y, _z in d.paths[0][0]] == scene[guide.entity_id]["cover_ring_mm"]


def test_a_circle_faces_cover_ring_is_inset_by_the_cover() -> None:
    doc = BUILDERS_V2["circular_column_spiral"]()
    (guide,) = doc.cover_guides()
    (d,) = drawables(entity_map(doc), {guide.entity_id}, 0.5)
    for x, y, _z in d.paths[0][0]:
        assert math.hypot(x, y) == pytest.approx(300.0 - 40.0, abs=1e-9)


# ---- every committed id is drawn, on its layer (record §4 invariant 1) -----------------

LAYER_OF = {"wall_legs": "leg", "bars": "bar", "hoops": "hoop", "crossties": "crosstie",
            "circular_ties": "circular-tie", "cover_guides": "cover"}  # fmt: skip


@pytest.mark.parametrize("name", sorted(BUILDERS_V2))
def test_every_committed_section_id_is_drawn_on_its_layer(name: str) -> None:
    draft = cast(Json, json.loads(fixture_path_v2(name).read_text(encoding="utf-8")))
    section = cast(Json, draft["section"])
    root = _root(render_svg(BUILDERS_V2[name](), view="top"))
    for key, items in section.items():
        if key == "templates" or not isinstance(items, list) or not items:
            continue
        if not isinstance(items[0], dict):
            continue  # materials_used: names, not entities
        for item in cast(list[Json], items):
            layer = item["role"] if key == "faces" else LAYER_OF.get(key)
            assert layer is not None, f"section key {key!r} has no layer: a new kind?"
            group = _member(root, layer, cast(int, item["id"]))
            marks = [e for e in group if e.tag in (f"{SVG_NS}path", f"{SVG_NS}circle")]
            assert marks, (name, key, item["id"])


# ---- segment counts: sqrt only ----------------------------------------------------------


def test_circle_counts_bound_the_chord_error_and_use_no_acos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The tier-1 count: the fewest sides n with r (1 - cos(pi / n)) <= tol. Ours may be one
    more (it bounds 1 - cos x by x^2 / 2), never fewer."""
    cases = [(r, t) for r in (1.5, 10.0, 190.0, 255.0, 300.0, 1e4) for t in (0.01, 0.1, 0.5, 2.0)]
    exact = {(r, t): math.ceil(math.pi / math.acos(1.0 - t / r)) for r, t in cases if t < r}

    def no_acos(_x: float) -> float:
        raise AssertionError("acos: its last ulp is platform-dependent")

    monkeypatch.setattr(math, "acos", no_acos)
    for r, t in cases:
        n = circle_segments(r, t)
        if t >= r:
            assert n == MIN_SEGMENTS
        elif MIN_SEGMENTS < n < MAX_SEGMENTS:
            assert r * (1.0 - math.cos(math.pi / n)) <= t * (1.0 + 1e-12)
            assert n - exact[(r, t)] in (0, 1), (r, t)
    render_svg(BUILDERS_V2["cft_round"](), view="top")  # circles all the way, no acos


# ---- annotation: steel joins concrete, ties are tagged ---------------------------------


def _tags(svg: str) -> list[str]:
    return re.findall(r'<g class="tag">.*?<text[^>]*>([^<]*)</text>', svg)


def test_circular_ties_are_tagged_with_their_bars() -> None:
    svg = render_svg(BUILDERS_V2["circular_column_spiral"](), view="top").svg
    assert _tags(svg) == ["8 Φ20", "Spiral Φ10 @ 75 mm", "Cover 40 mm"]
    doc = Document()
    doc.add_section_face("concrete", "C30", center_id=_at(0, 0), radius_mm=300.0)
    doc.add_bars_on_circle((0.0, 0.0), 240.0, 6, "Ø16")
    doc.add_circular_tie("hoop", _at(0, 0), 254.0, "Ø10", 100.0, label="H1")
    assert _tags(render_svg(doc, view="top").svg) == ["6 Φ16", "H1: Tie Φ10 @ 100 mm"]


def test_steel_alone_takes_the_title_and_the_dimensions() -> None:
    root = _root(render_svg(BUILDERS_V2["bare_w_shape"](), view="top"))
    title = [t.text for t in root.iter(f"{SVG_NS}text") if t.get("class") == "view-title"]
    assert title == ["SECTION"]  # was PLAN: no concrete, no section
    dims = [g for g in root.iter(f"{SVG_NS}g") if g.get("class") == "dimension"]
    texts = sorted(t.text or "" for g in dims for t in g.iter(f"{SVG_NS}text"))
    assert texts == ["254", "310"]  # the W's bf and d


# ---- DXF: faces by role, holes as islands, voids as later WIPEOUTs ----------------------


def _dxf(document: Document) -> Any:
    ezdxf: Any = pytest.importorskip("ezdxf")
    from apeCAD.render.dxf import export_dxf

    doc = ezdxf.read(__import__("io").StringIO(export_dxf(document, annotate=False).dxf))
    auditor = doc.audit()
    assert not auditor.has_errors and not auditor.has_fixes, auditor.errors
    return doc


def _index(entities: list[Any], layer: str, kind: str) -> list[int]:
    return [i for i, e in enumerate(entities) if (e.dxf.layer, e.dxftype()) == (layer, kind)]


def test_dxf_box_with_void_masks_the_void_after_the_concrete() -> None:
    msp = list(_dxf(BUILDERS_V2["box_with_void"]()).modelspace())
    (fill,) = _index(msp, "CONCRETE-FILL", "HATCH")
    (wipe,) = _index(msp, "VOID", "WIPEOUT")
    assert len(_index(msp, "CONCRETE-CUT", "LWPOLYLINE")) == 1
    assert len(_index(msp, "VOID", "LWPOLYLINE")) == 1
    bars = _index(msp, "BAR", "CIRCLE")
    assert len(bars) == 4 and fill < wipe < min(bars)  # masks the concrete, never a bar
    corners = {(round(v.x, 6), round(v.y, 6)) for v in msp[wipe].boundary_path_wcs()}
    assert corners == {(-100.0, -150.0), (100.0, -150.0), (100.0, 150.0), (-100.0, 150.0)}
    assert len(msp[fill].paths) == 1


def test_dxf_cft_round_hatches_the_tube_with_its_hole_as_an_island() -> None:
    doc = _dxf(BUILDERS_V2["cft_round"]())
    msp = list(doc.modelspace())
    circles = sorted((e.dxf.layer, round(e.dxf.radius, 9)) for e in msp if e.dxftype() == "CIRCLE")
    assert circles == [("CONCRETE-CUT", 190.0), ("STEEL-CUT", 190.0), ("STEEL-CUT", 200.0)]
    (core,) = _index(msp, "CONCRETE-FILL", "HATCH")
    (tube,) = _index(msp, "STEEL-FILL", "HATCH")
    assert core < tube  # steel over concrete
    paths = list(msp[tube].paths)
    assert [p.path_type_flags & 17 for p in paths] == [1, 16]  # external, then an island
    assert [round(p.edges[0].radius, 9) for p in paths] == [200.0, 190.0]
    layers = {layer.dxf.name for layer in doc.layers}
    assert {"STEEL-CUT", "STEEL-FILL", "VOID", "CIRCULAR-TIE"} <= layers


def test_dxf_draws_the_spiral_as_a_native_circle() -> None:
    msp = list(_dxf(BUILDERS_V2["circular_column_spiral"]()).modelspace())
    (tie,) = _index(msp, "CIRCULAR-TIE", "CIRCLE")
    assert msp[tie].dxf.radius == pytest.approx(255.0, abs=1e-9)


def test_dxf_refuses_a_void_with_holes_by_id() -> None:
    pytest.importorskip("ezdxf")
    from apeCAD.render.dxf import export_dxf

    doc, face_id = _face_doc("void", "ring", "circle")
    with pytest.raises(RenderArgumentError) as caught:
        export_dxf(doc)
    assert f"[{face_id}]" in str(caught.value) and "WIPEOUT" in str(caught.value)
