from __future__ import annotations

from apeCAD import Circle, Document, Ellipse, Face, Line, Point, Solid


def test_box_brep_is_eight_twelve_six_one() -> None:
    document = Document()
    solid = document.add_box((0.0, 0.0, 0.0), (6000.0, 4000.0, 200.0), label="slab")
    assert isinstance(solid, Solid)
    brep = document.brep()
    assert brep.root[solid.entity_id] == solid.entity_id
    faces = brep.children[solid.entity_id]
    assert len(faces) == 6
    edges: set[int] = set()
    vertices: set[int] = set()
    for face_id in faces:
        assert isinstance(document.entity(face_id), Face)
        assert brep.root[face_id] == solid.entity_id
        assert brep.solid[face_id] == solid.entity_id
        for edge_id in brep.children[face_id]:
            edges.add(edge_id)
            assert isinstance(document.entity(edge_id), Line)
            assert any(parent in faces for parent in brep.parents[edge_id])
            assert brep.root[edge_id] == solid.entity_id
            assert brep.solid[edge_id] == solid.entity_id
            for vertex_id in brep.children[edge_id]:
                vertices.add(vertex_id)
                assert isinstance(document.entity(vertex_id), Point)
                assert brep.root[vertex_id] == solid.entity_id
                assert brep.solid[vertex_id] == solid.entity_id
    assert len(edges) == 12
    assert len(vertices) == 8
    shared = [edge_id for edge_id in edges if len(brep.parents[edge_id]) == 2]
    assert len(shared) == 12


def test_circle_extrude_cap_is_a_circle() -> None:
    document = Document()
    center = document.add_point(0.0, 0.0, 0.0)
    circle = document.add_circle(center.entity_id, 1500.0, label="drum")
    solid = document.extrude(circle.entity_id, 400.0, label="column")
    assert isinstance(solid, Solid)
    assert solid.cap_id is not None
    cap = document.entity(solid.cap_id)
    assert isinstance(cap, Circle)
    assert cap.radius_mm == 1500.0
    lid = document.entity(cap.center_id)
    assert isinstance(lid, Point)
    assert lid.xyz_mm.z_mm == 400.0
    brep = document.brep()
    assert set(brep.children[solid.entity_id]) == {circle.entity_id, cap.entity_id}
    assert brep.root[cap.entity_id] == solid.entity_id
    assert brep.root[circle.entity_id] == solid.entity_id


def test_ellipse_extrude_cap_is_an_ellipse() -> None:
    document = Document()
    center = document.add_point(0.0, 0.0, 0.0)
    ellipse = document.add_ellipse(center.entity_id, 2000.0, 1000.0)
    solid = document.extrude(ellipse.entity_id, 300.0)
    assert isinstance(solid, Solid)
    assert solid.cap_id is not None
    cap = document.entity(solid.cap_id)
    assert isinstance(cap, Ellipse)
    assert cap.radius_x_mm == 2000.0
    assert cap.radius_y_mm == 1000.0


def test_sketch_line_is_its_own_brep_root() -> None:
    document = Document()
    a = document.add_point(0.0, 0.0, 0.0)
    b = document.add_point(1000.0, 0.0, 0.0)
    line = document.add_line(a.entity_id, b.entity_id)
    brep = document.brep()
    assert brep.root[line.entity_id] == line.entity_id
    assert line.entity_id not in brep.solid
    assert brep.root[a.entity_id] == line.entity_id
