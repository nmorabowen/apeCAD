"""Bar-layout ops (plan stage C3): AddBarRow and AddBarsAlongEdge, one gesture and one undo,
with exact collinearity on inclined layouts (ADR 0032)."""

from __future__ import annotations

import math
import random

import pytest

from apeCAD import Document, DocumentError
from apeCAD.catalog import apply
from apeCAD.entities import Bar, ConcreteFace, Point
from apeCAD.geometry import XYZ
from apeCAD.ops import AddBarRow, AddBarsAlongEdge, PointAt
from apeCAD.section.geometry import convex_hull_ccw, miter_offset
from apeCAD.section.layout import SNAP_GRID_MM, edge_positions, row_positions


def _xy(doc: Document, bar: Bar) -> tuple[float, float]:
    point = doc.entity(bar.point_id)
    assert isinstance(point, Point)
    return (point.xyz_mm.x_mm, point.xyz_mm.y_mm)


def _rect_face(doc: Document, corners: list[tuple[float, float]]) -> ConcreteFace:
    return doc.add_section_outline([PointAt(XYZ(x, y, 0.0)) for x, y in corners], "H30")


def _rotated(corners: list[tuple[float, float]], degrees: float) -> list[tuple[float, float]]:
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return [(x * c - y * s + 1234.5, x * s + y * c - 321.25) for x, y in corners]


RECT = [(0.0, 0.0), (2000.0, 0.0), (2000.0, 300.0), (0.0, 300.0)]


def test_row_by_count_places_both_ends_evenly() -> None:
    doc = Document()
    bars = doc.add_bar_row((60.0, 60.0), (1940.0, 60.0), "Ø16", count=5)
    assert [_xy(doc, bar) for bar in bars] == [
        (60.0, 60.0), (530.0, 60.0), (1000.0, 60.0), (1470.0, 60.0), (1940.0, 60.0)
    ]
    assert {bar.designation for bar in bars} == {"Ø16"}
    assert {bar.diameter_mm for bar in bars} == {16.0}


def test_row_by_spacing_centres_the_remainder() -> None:
    doc = Document()
    bars = doc.add_bar_row((0.0, 0.0), (1000.0, 0.0), "Ø12", spacing_mm=300.0)
    assert [_xy(doc, bar) for bar in bars] == [
        (50.0, 0.0), (350.0, 0.0), (650.0, 0.0), (950.0, 0.0)
    ]
    vertical = doc.add_bar_row((0.0, 100.0), (0.0, 400.0), "Ø12", spacing_mm=100.0)
    assert [_xy(doc, bar) for bar in vertical] == [
        (0.0, 100.0), (0.0, 200.0), (0.0, 300.0), (0.0, 400.0)
    ]


def test_a_row_is_one_op_and_one_undo() -> None:
    doc = Document()
    doc.add_bar(0.0, 0.0, "Ø16")
    before = doc.to_json()
    bars = doc.add_bar_row((0.0, 500.0), (900.0, 500.0), "Ø16", count=4)
    assert len(bars) == 4 and len(doc.ops()) == 2
    doc.undo()
    assert doc.to_json() == before
    assert len(doc.bars()) == 1 and len(doc.points()) == 1
    doc.redo()
    assert [b.entity_id for b in doc.bars()[1:]] == [b.entity_id for b in bars]


def test_a_row_replays_to_the_same_ids_and_positions() -> None:
    doc = Document()
    doc.add_bar_row((10.0, 20.0), (911.0, 433.0), "Ø20", count=7)
    again = Document.from_json(doc.to_json())
    assert again.bars() == doc.bars()
    assert again.points() == doc.points()
    committed = doc.ops()[-1]
    assert isinstance(committed, AddBarRow)
    assert len(committed.bar_ids) == len(committed.bar_point_ids) == 7


def test_an_inclined_row_stays_exactly_collinear_in_a_hoop() -> None:
    """ADR 0032: middle bars of an inclined row never survive as hull vertices."""
    doc = Document()
    row = doc.add_bar_row((13.7, 41.1), (2711.3, 1029.9), "Ø16", count=9)
    apex = doc.add_bar(400.0, 900.0, "Ø16")
    hoop = doc.add_hoop([*(bar.entity_id for bar in row), apex.entity_id], "Ø10", 100.0)
    assert set(hoop.bar_ids) == {row[0].entity_id, row[-1].entity_id, apex.entity_id}


def test_inclined_rows_are_exact_where_plain_interpolation_is_not() -> None:
    rng = random.Random(32)
    plain_failures = 0
    for _ in range(300):
        a = (rng.uniform(-3000.0, 3000.0), rng.uniform(-3000.0, 3000.0))
        b = (rng.uniform(-3000.0, 3000.0), rng.uniform(-3000.0, 3000.0))
        n = rng.randint(3, 15)
        apex = (a[0] + 700.0, a[1] - 900.0)
        snapped = row_positions(a, b, n, None)
        plain = [
            (a[0] + k / (n - 1) * (b[0] - a[0]), a[1] + k / (n - 1) * (b[1] - a[1]))
            for k in range(n)
        ]
        hull = convex_hull_ccw({**dict(enumerate(snapped)), -1: apex})
        assert len(hull) == 3
        plain_failures += len(convex_hull_ccw({**dict(enumerate(plain)), -1: apex})) != 3
        # The lattice moves a bar by a couple of microns at most.
        for p, q in zip(snapped, plain, strict=True):
            assert math.hypot(p[0] - q[0], p[1] - q[1]) < 0.002
    assert plain_failures > 0  # the problem ADR 0032 solves is real


def test_row_refusals() -> None:
    with pytest.raises(DocumentError, match="exactly one of count and spacing_mm"):
        AddBarRow(0.0, 0.0, 100.0, 0.0, "Ø16", count=3, spacing_mm=50.0)
    with pytest.raises(DocumentError, match="exactly one of count and spacing_mm"):
        AddBarRow(0.0, 0.0, 100.0, 0.0, "Ø16")
    with pytest.raises(DocumentError, match="count must be 2 or more"):
        AddBarRow(0.0, 0.0, 100.0, 0.0, "Ø16", count=1)
    with pytest.raises(DocumentError, match="designation"):
        AddBarRow(0.0, 0.0, 100.0, 0.0, "#5", count=2)
    doc = Document()
    with pytest.raises(DocumentError, match="two distinct ends"):
        doc.add_bar_row((5.0, 5.0), (5.0, 5.0), "Ø16", count=2)
    with pytest.raises(DocumentError, match="longer than the row"):
        doc.add_bar_row((0.0, 0.0), (100.0, 0.0), "Ø16", spacing_mm=250.0)
    with pytest.raises(DocumentError, match="at most"):
        doc.add_bar_row((0.0, 0.0), (100000.0, 0.0), "Ø16", spacing_mm=1.0)
    assert doc.ops() == ()


def test_bars_along_edge_sit_on_the_bar_centre_ring() -> None:
    doc = Document()
    face = _rect_face(doc, RECT)
    doc.set_cover(face.entity_id, 40.0, 10.0, 20.0)  # bar centres 60 mm in
    bottom = doc.add_bars_along_edge(face.entity_id, 0, "Ø20", count=5)
    assert [_xy(doc, bar) for bar in bottom] == [
        (60.0, 60.0), (530.0, 60.0), (1000.0, 60.0), (1470.0, 60.0), (1940.0, 60.0)
    ]
    right = doc.add_bars_along_edge(face.entity_id, 1, "Ø20", spacing_mm=100.0)
    # 180 mm at <= 100 mm: two intervals; the shared corner bar is not doubled.
    assert [_xy(doc, bar) for bar in right] == [(1940.0, 150.0), (1940.0, 240.0)]
    assert len(doc.bars()) == 7


def test_an_edge_layout_is_one_op_and_one_undo() -> None:
    doc = Document()
    face = _rect_face(doc, RECT)
    doc.set_cover(face.entity_id, 40.0, 10.0, 20.0)
    doc.add_bars_along_edge(face.entity_id, 0, "Ø20", count=5)
    before = doc.to_json()
    doc.add_bars_along_edge(face.entity_id, 1, "Ø20", count=4)
    doc.undo()
    assert doc.to_json() == before
    assert len(doc.bars()) == 5
    again = Document.from_json(doc.to_json())
    assert again.bars() == doc.bars() and again.points() == doc.points()


def test_bars_along_edge_need_a_cover_guide() -> None:
    doc = Document()
    face = _rect_face(doc, RECT)
    with pytest.raises(DocumentError, match="no cover guide"):
        doc.add_bars_along_edge(face.entity_id, 0, "Ø20", count=3)
    with pytest.raises(DocumentError, match="not a concrete face"):
        doc.add_bars_along_edge(face.point_ids[0], 0, "Ø20", count=3)
    doc.set_cover(face.entity_id, 40.0, 10.0, 20.0)
    with pytest.raises(DocumentError, match="out of range"):
        doc.add_bars_along_edge(face.entity_id, 4, "Ø20", count=3)
    with pytest.raises(DocumentError, match="edge_index must be 0 or more"):
        AddBarsAlongEdge(face_id=face.entity_id, edge_index=-1, designation="Ø20", count=3)


def test_a_collapsed_ring_and_a_full_edge_are_refused() -> None:
    doc = Document()
    thin = _rect_face(doc, [(0.0, 0.0), (1000.0, 0.0), (1000.0, 100.0), (0.0, 100.0)])
    doc.set_cover(thin.entity_id, 40.0, 10.0, 20.0)  # 2 x 60 mm > 100 mm
    with pytest.raises(DocumentError, match="no bar-centre ring"):
        doc.add_bars_along_edge(thin.entity_id, 0, "Ø20", count=3)
    face = _rect_face(doc, [(0.0, 500.0), (2000.0, 500.0), (2000.0, 800.0), (0.0, 800.0)])
    doc.set_cover(face.entity_id, 40.0, 10.0, 20.0)
    doc.add_bars_along_edge(face.entity_id, 0, "Ø20", count=3)
    with pytest.raises(DocumentError, match="already has a bar"):
        doc.add_bars_along_edge(face.entity_id, 0, "Ø20", count=2)


def test_an_inclined_cage_from_four_edges_hulls_to_its_four_corners() -> None:
    """A rotated wall: every edge inclined; the hoop around all bars keeps the 4 corners."""
    doc = Document()
    face = _rect_face(doc, _rotated(RECT, 23.0))
    doc.set_cover(face.entity_id, 25.0, 10.0, 16.0)
    placed: list[Bar] = []
    for edge, count in ((0, 9), (1, 3), (2, 9), (3, 3)):
        placed.extend(doc.add_bars_along_edge(face.entity_id, edge, "Ø16", count=count))
    assert len(placed) == 20  # 9 + 3 + 9 + 3 less the 4 shared corners
    hoop = doc.add_hoop([bar.entity_id for bar in placed], "Ø10", 100.0)
    assert len(hoop.bar_ids) == 4
    points = {p.entity_id: (p.xyz_mm.x_mm, p.xyz_mm.y_mm) for p in doc.points()}
    outline = [points[i] for i in face.point_ids]
    ring = miter_offset(outline, 43.0)
    corners = {_xy(doc, bar) for bar in placed if bar.entity_id in hoop.bar_ids}
    for corner in corners:
        assert min(math.hypot(corner[0] - x, corner[1] - y) for x, y in ring) < SNAP_GRID_MM


def test_edge_positions_share_snapped_corners() -> None:
    ring = miter_offset(_rotated(RECT, 40.0), 60.0)
    first = edge_positions(ring, 0, 4, None)
    second = edge_positions(ring, 1, 3, None)
    assert first[-1] == second[0]


def test_catalog_applies_the_layout_ops() -> None:
    doc = Document()
    face = _rect_face(doc, RECT)
    doc.set_cover(face.entity_id, 40.0, 10.0, 20.0)
    apply(doc, "AddBarsAlongEdge", {"face_id": face.entity_id, "edge_index": 0,
                                    "designation": "Ø16", "spacing_mm": 150})
    apply(doc, "AddBarRow", {"start_x_mm": 60, "start_y_mm": 150, "end_x_mm": 1940,
                             "end_y_mm": 150, "designation": "Ø16", "count": 3})
    committed = doc.ops()[-2:]
    assert isinstance(committed[0], AddBarsAlongEdge) and len(committed[0].bar_ids) == 14
    assert isinstance(committed[1], AddBarRow) and len(committed[1].bar_ids) == 3
