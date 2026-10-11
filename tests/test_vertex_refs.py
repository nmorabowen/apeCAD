"""One gesture is one op (ADR 0030): creation ops take point ids or coordinates."""

from __future__ import annotations

import json

import pytest

from apeCAD import Document, DocumentError
from apeCAD.draft.state import DraftState
from apeCAD.geometry import XYZ
from apeCAD.ops import AddFace, AddLineChain, Extrude, PointAt, op_from_dict, op_to_dict


def _at(x: float, y: float, z: float = 0.0) -> PointAt:
    return PointAt(XYZ(float(x), float(y), float(z)))


def _snapshot(document: Document) -> tuple[object, ...]:
    state: DraftState = document._state  # pyright: ignore[reportPrivateUsage]
    return (state.next_id, dict(state.entities), dict(state.labels))


def _assert_replays(document: Document) -> None:
    again = Document.from_json(document.to_json())
    assert _snapshot(again) == _snapshot(document)
    assert again.to_json() == document.to_json()


def _every_form() -> Document:
    """One gesture of each drawing tool, all from coordinates, on an empty document."""
    doc = Document()
    doc.add_line_chain([_at(0, 0), _at(1000, 0), _at(1000, 1000), _at(0, 1000)], label="L")
    doc.add_line(_at(-1000, 0), _at(-2000, 0))
    doc.add_polyline([_at(0, 5000), _at(1000, 5000), _at(2000, 6000)], closed=False)
    doc.add_face([_at(5000, 0), _at(6000, 0), _at(6000, 1000), _at(5000, 1000)], label="R")
    doc.add_circle(_at(9000, 0), 300.0)
    doc.add_ellipse(_at(9000, 3000), 300.0, 100.0)
    doc.add_arc(_at(0, 9000), _at(500, 9500), _at(1000, 9000))
    doc.add_bezier([_at(3000, 9000), _at(3500, 9500), _at(4000, 9500), _at(4500, 9000)])
    ring = [_at(0, 20000), _at(1000, 20000), _at(1000, 21000), _at(0, 21000)]
    doc.extrude(None, 500.0, ring=ring, label="B")
    return doc


def test_every_gesture_is_one_op() -> None:
    doc = _every_form()
    assert len(doc.ops()) == 9
    assert len(doc.lines()) >= 3 + 1 + 4 + 12  # chain, line, rect loop, box edges


def test_every_form_round_trips_and_replays() -> None:
    doc = _every_form()
    for op in doc.ops():
        assert op_from_dict(json.loads(json.dumps(op_to_dict(op)))) == op
    _assert_replays(doc)


def test_one_undo_removes_each_gesture_whole() -> None:
    doc = _every_form()
    for _ in range(9):
        doc.undo()
    assert doc.points() == ()
    assert doc.lines() == ()
    assert doc.ops() == ()


def test_box_ring_is_one_op_and_one_undo() -> None:
    doc = Document()
    doc.add_point(0.0, 0.0, 0.0)
    before = _snapshot(doc)
    ring = [_at(0, 0), _at(1000, 0), _at(1000, 1000), _at(0, 1000)]
    solid = doc.extrude(None, -400.0, ring=ring, label="box")
    assert solid.label == "box"
    assert len(doc.ops()) == 2
    assert len(doc.points()) == 8
    committed = doc.ops()[-1]
    assert isinstance(committed, Extrude)
    assert committed.face_id == solid.face_id
    assert committed.ring is not None and committed.ring[0] == 1  # reused, recorded as id
    _assert_replays(doc)
    doc.undo()
    assert _snapshot(doc)[1:] == before[1:]


def test_coordinates_reuse_a_point_within_one_millimetre() -> None:
    doc = Document()
    corner = doc.add_point(0.0, 0.0, 0.0).entity_id
    face = doc.add_face([_at(0.6, 0.0, 0.5), _at(1000, 0), _at(1000, 1000)])
    assert face.point_ids[0] == corner
    committed = doc.ops()[-1]
    assert isinstance(committed, AddFace)
    assert committed.point_ids[0] == corner
    assert committed.point_ids[1] == PointAt(XYZ(1000.0, 0.0, 0.0), face.point_ids[1])
    far = doc.add_face([_at(1.5, 0.0), _at(2000, 0), _at(2000, 2000)])
    assert far.point_ids[0] != corner
    _assert_replays(doc)


def test_coordinates_reuse_points_made_earlier_in_the_same_op() -> None:
    doc = Document()
    lines = doc.add_line_chain([_at(0, 0), _at(1000, 0), _at(0.3, 0.2)])
    assert lines[0].start_id == lines[1].end_id
    committed = doc.ops()[-1]
    assert isinstance(committed, AddLineChain)
    assert committed.point_ids[2] == lines[0].start_id
    assert committed.line_ids == tuple(line.entity_id for line in lines)
    _assert_replays(doc)


def test_the_old_point_ids_form_still_parses() -> None:
    op = op_from_dict({"op": "AddFace", "point_ids": [1, 2, 3], "label": None})
    assert op == AddFace(point_ids=(1, 2, 3))
    assert op_to_dict(op)["point_ids"] == [1, 2, 3]
    braced = op_from_dict({"op": "AddFace", "point_ids": [{"id": 1}, 2, {"xyz": [0, 0, 0]}]})
    assert braced == AddFace(point_ids=(1, 2, PointAt(XYZ(0.0, 0.0, 0.0))))
    plain = op_to_dict(Extrude(face_id=4, distance_mm=10.0))
    assert "ring" not in plain


@pytest.mark.parametrize(
    "vertex",
    [
        {},
        {"id": 1, "extra": 2},
        {"xyz": [0, 0]},
        {"xyz": [0, 0, "z"]},
        {"xyz": [0, 0, 0], "id": 0},
        {"id": None},
        True,
        "1",
    ],
)
def test_bad_vertex_refs_are_refused(vertex: object) -> None:
    with pytest.raises(DocumentError):
        op_from_dict({"op": "AddLine", "start_id": vertex, "end_id": 1})


def test_collapsed_coordinates_are_refused_atomically() -> None:
    doc = Document()
    doc.add_point(0.0, 0.0, 0.0)
    before = doc.to_json()
    with pytest.raises(DocumentError, match="collapsed"):
        doc.add_face([_at(0, 0), _at(0.5, 0), _at(1000, 1000)])
    with pytest.raises(DocumentError, match="same point"):
        doc.add_line_chain([_at(0, 0), _at(0.2, 0.2)])
    with pytest.raises(DocumentError, match="exists"):
        doc.add_line(PointAt(XYZ(5.0, 5.0, 0.0), 1), _at(100, 0))
    assert doc.to_json() == before


def test_extrude_needs_a_face_or_a_ring() -> None:
    with pytest.raises(DocumentError, match="face_id or a ring"):
        Extrude(face_id=None, distance_mm=10.0)
    with pytest.raises(DocumentError, match="three vertices"):
        Extrude(face_id=None, distance_mm=10.0, ring=(1, 2))
    with pytest.raises(DocumentError, match="segments"):
        Document().apply(AddLineChain(point_ids=(_at(0, 0), _at(9, 9)), line_ids=(7, 8)))
