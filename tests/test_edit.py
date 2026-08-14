from __future__ import annotations

import pytest

from apeCAD import Arc, Document, DocumentError, Face, Line, Point, Polyline
from apeCAD.geometry import XYZ, line_intersect_xy, project_on_segment, segments_intersect_xy


def _square() -> tuple[Document, tuple[Line, Line, Line, Line], Face]:
    document = Document()
    a = document.add_point(0.0, 0.0, 0.0)
    b = document.add_point(4000.0, 0.0, 0.0)
    c = document.add_point(4000.0, 3000.0, 0.0)
    d = document.add_point(0.0, 3000.0, 0.0)
    ab = document.add_line(a.entity_id, b.entity_id)
    bc = document.add_line(b.entity_id, c.entity_id)
    cd = document.add_line(c.entity_id, d.entity_id)
    da = document.add_line(d.entity_id, a.entity_id)
    face = document.add_face((a.entity_id, b.entity_id, c.entity_id, d.entity_id))
    return document, (ab, bc, cd, da), face


def test_project_on_segment_midpoint() -> None:
    qx, qy, t = project_on_segment(50.0, 10.0, 0.0, 0.0, 100.0, 0.0)
    assert t == pytest.approx(0.5)
    assert qx == pytest.approx(50.0)
    assert qy == pytest.approx(0.0)


def test_segments_intersect_xy() -> None:
    hit = segments_intersect_xy(
        XYZ(0.0, 0.0, 0.0),
        XYZ(10.0, 0.0, 0.0),
        XYZ(5.0, -5.0, 0.0),
        XYZ(5.0, 5.0, 0.0),
    )
    assert hit is not None
    assert hit.x_mm == pytest.approx(5.0)
    assert hit.y_mm == pytest.approx(0.0)
    assert segments_intersect_xy(
        XYZ(0.0, 0.0, 0.0),
        XYZ(1.0, 0.0, 0.0),
        XYZ(0.0, 1.0, 0.0),
        XYZ(1.0, 1.0, 0.0),
    ) is None


def test_translate_moves_shared_points_once() -> None:
    document, (ab, _bc, _cd, _da), _face = _square()
    document.translate((ab.entity_id,), 100.0, 50.0)
    start = document.entity(ab.start_id)
    end = document.entity(ab.end_id)
    assert isinstance(start, Point)
    assert isinstance(end, Point)
    assert start.xyz_mm.to_tuple() == (100.0, 50.0, 0.0)
    assert end.xyz_mm.to_tuple() == (4100.0, 50.0, 0.0)
    loaded = Document.from_json(document.to_json())
    assert loaded.entity(ab.start_id).xyz_mm.to_tuple() == (100.0, 50.0, 0.0)  # type: ignore[union-attr]


def test_translate_box_origin() -> None:
    document = Document()
    box = document.add_box((0.0, 0.0, 0.0), (1000.0, 800.0, 200.0), label="pad")
    document.translate((box.entity_id,), 250.0, 0.0, 10.0)
    moved = document.entity_by_label("pad")
    assert moved.origin_xyz_mm.to_tuple() == (250.0, 0.0, 10.0)  # type: ignore[union-attr]


def test_insert_node_splits_line_and_face() -> None:
    document, (ab, _bc, _cd, _da), face = _square()
    node = document.insert_node(ab.entity_id, 2000.0, 0.0)
    assert isinstance(node, Point)
    assert node.xyz_mm.x_mm == pytest.approx(2000.0)
    updated = document.entity(ab.entity_id)
    assert isinstance(updated, Line)
    assert updated.end_id == node.entity_id
    assert len(document.lines()) == 5
    spliced = document.entity(face.entity_id)
    assert isinstance(spliced, Face)
    assert spliced.point_ids == (
        face.point_ids[0],
        node.entity_id,
        face.point_ids[1],
        face.point_ids[2],
        face.point_ids[3],
    )
    loaded = Document.from_json(document.to_json())
    assert loaded.entity(face.entity_id).point_ids == spliced.point_ids  # type: ignore[union-attr]


def test_insert_node_on_face_edge() -> None:
    document, (_ab, _bc, _cd, _da), face = _square()
    node = document.insert_node(face.entity_id, 4000.0, 1500.0)
    updated = document.entity(face.entity_id)
    assert isinstance(updated, Face)
    assert node.entity_id in updated.point_ids
    assert len(updated.point_ids) == 5
    assert len(document.lines()) == 5


def test_insert_node_rejects_endpoint() -> None:
    document, (ab, _bc, _cd, _da), _face = _square()
    with pytest.raises(DocumentError, match="endpoint"):
        document.insert_node(ab.entity_id, 0.0, 0.0)


def test_line_intersect_xy_implied() -> None:
    hit = line_intersect_xy(
        XYZ(0.0, 0.0, 0.0),
        XYZ(10.0, 0.0, 0.0),
        XYZ(5.0, 1.0, 0.0),
        XYZ(5.0, 4.0, 0.0),
    )
    assert hit is not None
    point, t, u = hit
    assert point.x_mm == pytest.approx(5.0)
    assert point.y_mm == pytest.approx(0.0)
    assert t == pytest.approx(0.5)
    assert u == pytest.approx(-1.0 / 3.0)
    assert segments_intersect_xy(
        XYZ(0.0, 0.0, 0.0),
        XYZ(10.0, 0.0, 0.0),
        XYZ(5.0, 1.0, 0.0),
        XYZ(5.0, 4.0, 0.0),
    ) is None


def test_trim_line_keeps_the_named_end() -> None:
    document = Document()
    a = document.add_point(0.0, 0.0, 0.0)
    b = document.add_point(10.0, 0.0, 0.0)
    line = document.add_line(a.entity_id, b.entity_id)
    cut = document.trim_line(line.entity_id, a.entity_id, 5.0, 0.0)
    updated = document.entity(line.entity_id)
    assert isinstance(updated, Line)
    assert updated.start_id == a.entity_id
    assert updated.end_id == cut.entity_id
    assert cut.xyz_mm.x_mm == pytest.approx(5.0)


def test_trim_line_can_lengthen() -> None:
    document = Document()
    a = document.add_point(0.0, 0.0, 0.0)
    b = document.add_point(4000.0, 0.0, 0.0)
    line = document.add_line(a.entity_id, b.entity_id)
    far = document.trim_line(line.entity_id, a.entity_id, 10000.0, 0.0)
    updated = document.entity(line.entity_id)
    assert isinstance(updated, Line)
    assert updated.end_id == far.entity_id
    assert far.xyz_mm.x_mm == pytest.approx(10000.0)


def test_break_crossing_shares_the_node() -> None:
    document = Document()
    a = document.add_point(0.0, 0.0, 0.0)
    b = document.add_point(10000.0, 0.0, 0.0)
    c = document.add_point(5000.0, -4000.0, 0.0)
    d = document.add_point(5000.0, 4000.0, 0.0)
    across = document.add_line(a.entity_id, b.entity_id)
    down = document.add_line(c.entity_id, d.entity_id)
    node = document.break_crossing(across.entity_id, down.entity_id)
    assert node.xyz_mm.x_mm == pytest.approx(5000.0)
    assert node.xyz_mm.y_mm == pytest.approx(0.0)
    assert len(document.lines()) == 4
    users = [
        line
        for line in document.lines()
        if node.entity_id in (line.start_id, line.end_id)
    ]
    assert len(users) == 4
    loaded = Document.from_json(document.to_json())
    assert loaded.entity(node.entity_id)
    assert len(loaded.lines()) == 4


def test_join_polyline_open_chain() -> None:
    document = Document()
    a = document.add_point(0.0, 0.0, 0.0)
    b = document.add_point(1000.0, 0.0, 0.0)
    c = document.add_point(1000.0, 800.0, 0.0)
    ab = document.add_line(a.entity_id, b.entity_id, label="path")
    bc = document.add_line(b.entity_id, c.entity_id)
    joined = document.join_polyline((ab.entity_id, bc.entity_id))
    assert isinstance(joined, Polyline)
    assert joined.closed is False
    assert joined.point_ids in (
        (a.entity_id, b.entity_id, c.entity_id),
        (c.entity_id, b.entity_id, a.entity_id),
    )
    assert joined.label == "path"
    assert document.lines() == ()
    loaded = Document.from_json(document.to_json())
    assert loaded.entity_by_label("path").entity_id == joined.entity_id


def test_join_polyline_closes_a_loop() -> None:
    document, (ab, bc, cd, da), _face = _square()
    joined = document.join_polyline((ab.entity_id, bc.entity_id, cd.entity_id, da.entity_id))
    assert joined.closed is True
    assert len(joined.point_ids) == 4
    assert len(document.lines()) == 0


def test_join_polyline_rejects_a_branch() -> None:
    document = Document()
    a = document.add_point(0.0, 0.0, 0.0)
    b = document.add_point(1000.0, 0.0, 0.0)
    c = document.add_point(1000.0, 800.0, 0.0)
    d = document.add_point(2000.0, 0.0, 0.0)
    ab = document.add_line(a.entity_id, b.entity_id)
    bc = document.add_line(b.entity_id, c.entity_id)
    bd = document.add_line(b.entity_id, d.entity_id)
    with pytest.raises(DocumentError, match="branch"):
        document.join_polyline((ab.entity_id, bc.entity_id, bd.entity_id))


def test_join_polyline_and_line() -> None:
    document = Document()
    a = document.add_point(0.0, 0.0, 0.0)
    b = document.add_point(1000.0, 0.0, 0.0)
    c = document.add_point(2000.0, 0.0, 0.0)
    d = document.add_point(3000.0, 0.0, 0.0)
    poly = document.add_polyline((a.entity_id, b.entity_id, c.entity_id))
    extra = document.add_line(c.entity_id, d.entity_id)
    joined = document.join_polyline((poly.entity_id, extra.entity_id))
    assert joined.point_ids in (
        (a.entity_id, b.entity_id, c.entity_id, d.entity_id),
        (d.entity_id, c.entity_id, b.entity_id, a.entity_id),
    )
    assert document.polylines() == (joined,)
    assert document.lines() == ()


def test_add_face_from_lines_orders_the_loop() -> None:
    document = Document()
    a = document.add_point(0.0, 0.0, 0.0)
    b = document.add_point(4000.0, 0.0, 0.0)
    c = document.add_point(4000.0, 3000.0, 0.0)
    d = document.add_point(0.0, 3000.0, 0.0)
    lines = [
        document.add_line(a.entity_id, b.entity_id),
        document.add_line(c.entity_id, d.entity_id),
        document.add_line(b.entity_id, c.entity_id),
        document.add_line(d.entity_id, a.entity_id),
    ]
    face = document.add_face_from_lines([line.entity_id for line in lines], label="slab")
    assert isinstance(face, Face)
    assert set(face.point_ids) == {a.entity_id, b.entity_id, c.entity_id, d.entity_id}
    assert len(face.point_ids) == 4
    loaded = Document.from_json(document.to_json())
    assert loaded.entity_by_label("slab").entity_id == face.entity_id


def test_add_face_from_open_chain_is_rejected() -> None:
    document = Document()
    a = document.add_point(0.0, 0.0, 0.0)
    b = document.add_point(1.0, 0.0, 0.0)
    c = document.add_point(1.0, 1.0, 0.0)
    d = document.add_point(0.0, 1.0, 0.0)
    e = document.add_point(2.0, 0.0, 0.0)
    ab = document.add_line(a.entity_id, b.entity_id)
    bc = document.add_line(b.entity_id, c.entity_id)
    de = document.add_line(d.entity_id, e.entity_id)
    with pytest.raises(DocumentError, match="closed loop"):
        document.add_face_from_lines((ab.entity_id, bc.entity_id, de.entity_id))


def test_insert_node_undo_replays() -> None:
    document, (ab, _bc, _cd, _da), _face = _square()
    before = len(document.lines())
    document.insert_node(ab.entity_id, 2000.0, 0.0)
    document.undo()
    assert len(document.lines()) == before
    assert document.entity(ab.entity_id).end_id == ab.end_id  # type: ignore[union-attr]


def test_rotate_90_around_origin() -> None:
    document = Document()
    point = document.add_point(1000.0, 0.0, 0.0)
    document.rotate((point.entity_id,), 0.0, 0.0, 90.0)
    moved = document.entity(point.entity_id)
    assert isinstance(moved, Point)
    assert moved.xyz_mm.x_mm == pytest.approx(0.0, abs=1e-6)
    assert moved.xyz_mm.y_mm == pytest.approx(1000.0, abs=1e-6)
    loaded = Document.from_json(document.to_json())
    assert loaded.entity(point.entity_id).xyz_mm.y_mm == pytest.approx(1000.0)  # type: ignore[union-attr]


def test_mirror_across_x_axis() -> None:
    document = Document()
    point = document.add_point(200.0, 800.0, 0.0)
    document.mirror((point.entity_id,), 0.0, 0.0, 1000.0, 0.0)
    moved = document.entity(point.entity_id)
    assert isinstance(moved, Point)
    assert moved.xyz_mm.x_mm == pytest.approx(200.0)
    assert moved.xyz_mm.y_mm == pytest.approx(-800.0)


def test_chamfer_corner_cuts_a_square() -> None:
    document, (_ab, _bc, _cd, _da), face = _square()
    vertex = face.point_ids[1]
    chamfer = document.chamfer_corner(face.entity_id, vertex, 500.0)
    assert isinstance(chamfer, Line)
    updated = document.entity(face.entity_id)
    assert isinstance(updated, Face)
    assert vertex not in updated.point_ids
    assert len(updated.point_ids) == 5
    start = document.entity(chamfer.start_id)
    end = document.entity(chamfer.end_id)
    assert isinstance(start, Point)
    assert isinstance(end, Point)
    assert {start.xyz_mm.to_tuple(), end.xyz_mm.to_tuple()} == {
        (3500.0, 0.0, 0.0),
        (4000.0, 500.0, 0.0),
    }


def test_fillet_corner_adds_an_arc() -> None:
    document, (_ab, _bc, _cd, _da), face = _square()
    vertex = face.point_ids[1]
    fillet = document.fillet_corner(face.entity_id, vertex, 400.0)
    assert isinstance(fillet, Arc)
    updated = document.entity(face.entity_id)
    assert isinstance(updated, Face)
    assert vertex not in updated.point_ids
    assert len(updated.point_ids) == 6
    loaded = Document.from_json(document.to_json())
    assert len(loaded.arcs()) == 1


def test_sew_merges_coincident_points() -> None:
    document = Document()
    a = document.add_point(0.0, 0.0, 0.0)
    b = document.add_point(1000.0, 0.0, 0.0)
    c = document.add_point(0.4, 0.0, 0.0)
    d = document.add_point(0.0, 1000.0, 0.0)
    ab = document.add_line(a.entity_id, b.entity_id)
    cd = document.add_line(c.entity_id, d.entity_id)
    document.sew((ab.entity_id, cd.entity_id), tolerance_mm=1.0)
    assert len(document.points()) == 3
    sewn = document.entity(cd.entity_id)
    assert isinstance(sewn, Line)
    assert sewn.start_id == a.entity_id


def test_simplify_drops_collinear_vertex() -> None:
    document = Document()
    a = document.add_point(0.0, 0.0, 0.0)
    mid = document.add_point(2000.0, 0.0, 0.0)
    b = document.add_point(4000.0, 0.0, 0.0)
    c = document.add_point(4000.0, 3000.0, 0.0)
    d = document.add_point(0.0, 3000.0, 0.0)
    face = document.add_face((a.entity_id, mid.entity_id, b.entity_id, c.entity_id, d.entity_id))
    document.simplify((face.entity_id,))
    simplified = document.entity(face.entity_id)
    assert isinstance(simplified, Face)
    assert mid.entity_id not in simplified.point_ids
    assert len(simplified.point_ids) == 4


def test_array_linear_and_polar() -> None:
    document = Document()
    a = document.add_point(0.0, 0.0, 0.0)
    b = document.add_point(1000.0, 0.0, 0.0)
    line = document.add_line(a.entity_id, b.entity_id)
    document.array_linear((line.entity_id,), 0.0, 2000.0, copies=2)
    assert len(document.lines()) == 3
    document.array_polar((a.entity_id,), 0.0, 0.0, count=4)
    assert len(document.points()) >= 6
    loaded = Document.from_json(document.to_json())
    assert len(loaded.lines()) == 3


def test_delete_line_sweeps_unused_points() -> None:
    document = Document()
    a = document.add_point(0.0, 0.0, 0.0, label="A")
    b = document.add_point(1000.0, 0.0, 0.0, label="B")
    line = document.add_line(a.entity_id, b.entity_id, label="beam")
    document.delete((line.entity_id,))
    assert document.lines() == ()
    assert document.points() == ()
    with pytest.raises(DocumentError, match="unknown label"):
        document.entity_by_label("beam")
    document.undo()
    assert document.entity_by_label("beam").entity_id == line.entity_id
    assert document.entity_by_label("A").entity_id == a.entity_id


def test_delete_keeps_shared_points() -> None:
    document, (ab, _bc, _cd, _da), face = _square()
    document.delete((ab.entity_id,))
    assert document.entity(ab.start_id)
    assert document.entity(ab.end_id)
    assert len(document.lines()) == 3
    assert document.entity(face.entity_id)


def test_delete_point_cascades_to_users() -> None:
    document, (_ab, _bc, _cd, _da), face = _square()
    corner = face.point_ids[0]
    document.delete((corner,))
    with pytest.raises(DocumentError, match="unknown entity"):
        document.entity(corner)
    with pytest.raises(DocumentError, match="unknown entity"):
        document.entity(face.entity_id)
    assert len(document.lines()) == 2


def test_delete_solid_keeps_profile() -> None:
    document, _lines, face = _square()
    solid = document.extrude(face.entity_id, 200.0, label="wall")
    document.delete((solid.entity_id,))
    assert document.solids() == ()
    assert document.entity(face.entity_id)
    loaded = Document.from_json(document.to_json())
    assert loaded.solids() == ()
    assert loaded.entity(face.entity_id)


def test_delete_face_cascades_to_solid() -> None:
    document, _lines, face = _square()
    solid = document.extrude(face.entity_id, 200.0)
    document.delete((face.entity_id,))
    with pytest.raises(DocumentError, match="unknown entity"):
        document.entity(solid.entity_id)


def test_delete_unknown_id_is_rejected() -> None:
    document = Document()
    with pytest.raises(DocumentError, match="at least one"):
        document.delete(())
    with pytest.raises(DocumentError, match="unknown entity"):
        document.delete((1,))

