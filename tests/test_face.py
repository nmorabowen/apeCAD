from __future__ import annotations

import pytest

from apeCAD import Circle, Document, DocumentError, Face, Point, Solid


def test_face_and_extrude_round_trip() -> None:
    document = Document()
    p1 = document.add_point(0.0, 0.0, 0.0)
    p2 = document.add_point(4000.0, 0.0, 0.0)
    p3 = document.add_point(4000.0, 3000.0, 0.0)
    p4 = document.add_point(0.0, 3000.0, 0.0)
    face = document.add_face(
        (p1.entity_id, p2.entity_id, p3.entity_id, p4.entity_id),
        label="slab",
    )
    assert len(document.lines()) == 4
    solid = document.extrude(face.entity_id, 200.0, label="slab_solid")
    assert isinstance(face, Face)
    assert isinstance(solid, Solid)
    assert solid.distance_mm == 200.0
    assert solid.cap_id is not None
    cap = document.entity(solid.cap_id)
    assert isinstance(cap, Face)
    assert len(cap.point_ids) == 4
    assert len(solid.wall_ids) == 4
    assert len(document.faces()) == 6
    assert len(document.points()) == 8
    assert len(document.lines()) == 12
    loaded = Document.from_json(document.to_json())
    assert loaded.entity_by_label("slab_solid").entity_id == solid.entity_id
    frame = loaded.to_frame()
    assert len(frame.volumes) == 1
    assert frame.volumes[0].size_xyz_mm.z_mm == 200.0


def test_add_face_reuses_existing_lines() -> None:
    document = Document()
    a = document.add_point(0.0, 0.0, 0.0)
    b = document.add_point(4000.0, 0.0, 0.0)
    c = document.add_point(4000.0, 3000.0, 0.0)
    d = document.add_point(0.0, 3000.0, 0.0)
    ab = document.add_line(a.entity_id, b.entity_id)
    bc = document.add_line(b.entity_id, c.entity_id)
    cd = document.add_line(c.entity_id, d.entity_id)
    da = document.add_line(d.entity_id, a.entity_id)
    document.add_face((a.entity_id, b.entity_id, c.entity_id, d.entity_id))
    assert len(document.lines()) == 4
    ids = {line.entity_id for line in document.lines()}
    assert ids == {ab.entity_id, bc.entity_id, cd.entity_id, da.entity_id}


def test_extrude_requires_a_face() -> None:
    document = Document()
    point = document.add_point(0.0, 0.0, 0.0)
    with pytest.raises(DocumentError, match="not a profile"):
        document.extrude(point.entity_id, 100.0)


def test_circle_is_an_extrudable_profile() -> None:
    document = Document()
    center = document.add_point(0.0, 0.0, 0.0)
    circle = document.add_circle(center.entity_id, 1500.0, label="drum")
    assert isinstance(circle, Circle)
    solid = document.extrude(circle.entity_id, 400.0, label="column")
    assert isinstance(solid, Solid)
    assert solid.face_id == circle.entity_id
    assert solid.cap_id is not None
    lid = document.entity(solid.cap_id)
    assert isinstance(lid, Point)
    assert lid.xyz_mm.z_mm == pytest.approx(400.0)
    assert len(document.points()) == 2
    frame = document.to_frame()
    assert frame.volumes[0].size_xyz_mm.z_mm == 400.0
    assert frame.volumes[0].size_xyz_mm.x_mm == 3000.0


def test_zero_extrude_is_rejected() -> None:
    document = Document()
    a = document.add_point(0.0, 0.0, 0.0)
    b = document.add_point(1.0, 0.0, 0.0)
    c = document.add_point(0.0, 1.0, 0.0)
    face = document.add_face((a.entity_id, b.entity_id, c.entity_id))
    with pytest.raises(DocumentError, match="cannot be zero"):
        document.extrude(face.entity_id, 0.0)
