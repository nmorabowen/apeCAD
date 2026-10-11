"""Delete removes the selection's whole B-rep subtree, keeping shared parts (ADR 0029)."""

from __future__ import annotations

from apeCAD import Document


def _census(document: Document) -> dict[str, int]:
    return {
        "points": len(document.points()),
        "lines": len(document.lines()),
        "faces": len(document.faces()),
        "solids": len(document.solids()),
        "circles": len(document.circles()),
    }


EMPTY = {"points": 0, "lines": 0, "faces": 0, "solids": 0, "circles": 0}


def _square_face(document: Document, x0: float = 0.0, *, label: str | None = None) -> int:
    corners = [(x0, 0.0), (x0 + 1000.0, 0.0), (x0 + 1000.0, 1000.0), (x0, 1000.0)]
    ids = [document.add_point(x, y, 0.0).entity_id for x, y in corners]
    return document.add_face(ids, label=label).entity_id


def test_deleting_a_box_leaves_nothing_and_undo_restores_it() -> None:
    document = Document()
    box = document.add_box((0.0, 0.0, 0.0), (1000.0, 1000.0, 1000.0), label="slab")
    full = _census(document)
    document.delete((box.entity_id,))
    assert _census(document) == EMPTY
    document.undo()
    assert _census(document) == full
    assert document.entity_by_label("slab").entity_id == box.entity_id


def test_deleting_an_extruded_labelled_face_solid_takes_the_labelled_profile() -> None:
    document = Document()
    face_id = _square_face(document, label="wall_L1")
    solid = document.extrude(face_id, 3000.0, label="wall_L1_solid")
    document.delete((solid.entity_id,))
    assert _census(document) == EMPTY
    assert Document.from_json(document.to_json()).faces() == ()


def test_deleting_a_face_takes_its_edges_and_vertices() -> None:
    document = Document()
    face_id = _square_face(document)
    document.delete((face_id,))
    assert _census(document) == EMPTY


def test_a_neighbour_keeps_every_shared_part() -> None:
    document = Document()
    left = document.add_box((0.0, 0.0, 0.0), (1000.0, 1000.0, 1000.0))
    right = document.add_box((1000.0, 0.0, 0.0), (1000.0, 1000.0, 1000.0))
    alone = Document()
    alone.add_box((1000.0, 0.0, 0.0), (1000.0, 1000.0, 1000.0))
    document.delete((left.entity_id,))
    assert _census(document) == _census(alone)
    kept = document.entity(right.entity_id)
    assert kept.entity_id == right.entity_id
    brep = document.brep()
    assert all(child in brep.children for child in brep.children[right.entity_id])


def test_a_line_that_ends_on_a_deleted_face_keeps_its_endpoint() -> None:
    document = Document()
    face_id = _square_face(document)
    corner = document.entity(face_id)
    tail = document.add_point(-2000.0, 0.0, 0.0)
    line = document.add_line(tail.entity_id, corner.point_ids[0])  # type: ignore[union-attr]
    document.delete((face_id,))
    assert document.entity(line.entity_id)
    assert {p.entity_id for p in document.points()} == {
        tail.entity_id,
        corner.point_ids[0],  # type: ignore[union-attr]
    }
    assert len(document.lines()) == 1
    assert document.faces() == ()


def test_deleting_a_circle_takes_its_centre_unless_shared() -> None:
    document = Document()
    centre = document.add_point(0.0, 0.0, 0.0)
    circle = document.add_circle(centre.entity_id, 250.0)
    document.delete((circle.entity_id,))
    assert _census(document) == EMPTY

    shared = Document()
    node = shared.add_point(0.0, 0.0, 0.0, label="C1")
    other = shared.add_point(3000.0, 0.0, 0.0)
    shared.add_line(node.entity_id, other.entity_id, label="beam")
    ring = shared.add_circle(node.entity_id, 250.0)
    shared.delete((ring.entity_id,))
    assert shared.entity_by_label("C1").entity_id == node.entity_id
    assert shared.circles() == ()


def test_a_face_broken_by_a_deleted_vertex_does_not_take_its_other_edges() -> None:
    document = Document()
    face_id = _square_face(document)
    corner = document.entity(face_id).point_ids[0]  # type: ignore[union-attr]
    document.delete((corner,))
    assert document.faces() == ()
    assert len(document.lines()) == 2
    assert len(document.points()) == 3


def test_delete_replays_to_the_same_draft() -> None:
    document = Document()
    document.add_box((0.0, 0.0, 0.0), (1000.0, 1000.0, 1000.0))
    right = document.add_box((1000.0, 0.0, 0.0), (1000.0, 1000.0, 500.0))
    document.delete((right.entity_id,))
    replayed = Document.from_json(document.to_json())
    assert _census(replayed) == _census(document)
    assert [e.entity_id for e in replayed.points()] == [e.entity_id for e in document.points()]
