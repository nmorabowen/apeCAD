from __future__ import annotations

import json
import math

import pytest

from apeCAD import Document, DocumentError, Face, Line, Point, Polyline, Solid


def _portal() -> Document:
    document = Document()
    a = document.add_point(0.0, 0.0, 0.0, label="A")
    b = document.add_point(6000.0, 0.0, 0.0, label="B")
    document.add_line(a.entity_id, b.entity_id, label="beam_B1")
    document.add_box((0.0, 0.0, 0.0), (6000.0, 4000.0, 200.0), label="slab_L2")
    document.tag("level_1", [a.entity_id, b.entity_id])
    return document


def test_add_point_line_box_and_tag() -> None:
    document = _portal()
    beam = document.entity_by_label("beam_B1")
    slab = document.entity_by_label("slab_L2")
    assert isinstance(beam, Line)
    assert isinstance(slab, Solid)
    assert beam.start_id == document.entity_by_label("A").entity_id
    assert slab.distance_mm == 200.0
    assert isinstance(document.entity(slab.face_id), Face)
    assert document.boxes() == ()
    assert document.tagged("level_1") == frozenset(
        {document.entity_by_label("A").entity_id, document.entity_by_label("B").entity_id}
    )


def test_set_label_renames_and_clears() -> None:
    document = Document()
    point = document.add_point(0.0, 0.0, 0.0, label="A")
    document.set_label(point.entity_id, "origin")
    assert document.entity_by_label("origin").entity_id == point.entity_id
    with pytest.raises(DocumentError, match="unknown label"):
        document.entity_by_label("A")
    document.set_label(point.entity_id, None)
    assert document.entity(point.entity_id).label is None
    with pytest.raises(DocumentError, match="unknown label"):
        document.entity_by_label("origin")


def test_polyline_closed_loop() -> None:
    document = Document()
    p1 = document.add_point(0.0, 0.0, 0.0)
    p2 = document.add_point(1000.0, 0.0, 0.0)
    p3 = document.add_point(1000.0, 1000.0, 0.0)
    loop = document.add_polyline(
        (p1.entity_id, p2.entity_id, p3.entity_id),
        closed=True,
        label="loop",
    )
    assert isinstance(loop, Polyline)
    assert loop.closed is True
    assert len(document.polylines()) == 1


def test_duplicate_label_is_rejected() -> None:
    document = Document()
    document.add_point(0.0, 0.0, 0.0, label="A")
    with pytest.raises(DocumentError, match="already belongs"):
        document.add_point(1.0, 0.0, 0.0, label="A")
    assert len(document.points()) == 1


def test_line_requires_existing_distinct_points() -> None:
    document = Document()
    a = document.add_point(0.0, 0.0, 0.0)
    with pytest.raises(DocumentError, match="not a point"):
        document.add_line(a.entity_id, 99)
    with pytest.raises(DocumentError, match="cannot be the same"):
        document.add_line(a.entity_id, a.entity_id)


def test_box_size_must_be_positive() -> None:
    document = Document()
    with pytest.raises(DocumentError, match="positive"):
        document.add_box((0.0, 0.0, 0.0), (100.0, 0.0, 50.0))


def test_add_box_expands_to_face_and_extrude() -> None:
    document = Document()
    solid = document.add_box((0.0, 0.0, 0.0), (6000.0, 4000.0, 200.0), label="slab_L2")
    assert isinstance(solid, Solid)
    assert document.boxes() == ()
    face = document.entity(solid.face_id)
    assert isinstance(face, Face)
    assert len(face.point_ids) == 4
    assert solid.cap_id is not None
    cap = document.entity(solid.cap_id)
    assert isinstance(cap, Face)
    assert len(document.points()) == 8
    assert len(document.faces()) == 6
    assert len(solid.wall_ids) == 4
    assert len(document.lines()) == 12
    assert len(document.ops()) == 1
    assert document.ops()[0].__class__.__name__ == "AddBox"
    loaded = Document.from_json(document.to_json())
    restored = loaded.entity_by_label("slab_L2")
    assert isinstance(restored, Solid)
    assert len(restored.wall_ids) == 4
    cap_face = loaded.entity(restored.cap_id)
    assert isinstance(cap_face, Face)
    assert len(loaded.lines()) == 12
    for point_id in cap_face.point_ids:
        lid = loaded.entity(point_id)
        assert isinstance(lid, Point)
        assert lid.xyz_mm.z_mm == 200.0


def test_non_finite_coordinate_is_rejected() -> None:
    document = Document()
    with pytest.raises(DocumentError, match="finite"):
        document.add_point(math.nan, 0.0, 0.0)


def test_tag_unknown_entity_is_rejected() -> None:
    document = Document()
    with pytest.raises(DocumentError, match="unknown entity"):
        document.tag("ghost", [1])


def test_undo_and_redo() -> None:
    document = Document()
    document.add_point(0.0, 0.0, 0.0, label="A")
    document.add_point(1.0, 0.0, 0.0, label="B")
    document.undo()
    assert len(document.points()) == 1
    with pytest.raises(DocumentError, match="unknown label"):
        document.entity_by_label("B")
    document.redo()
    assert document.entity_by_label("B").entity_id == 2
    document.undo()
    document.add_point(2.0, 0.0, 0.0, label="C")
    with pytest.raises(DocumentError, match="nothing to redo"):
        document.redo()
    assert document.entity_by_label("C").entity_id == 2


def test_json_round_trip_replays_ops() -> None:
    original = _portal()
    original.add_polyline(
        (
            original.entity_by_label("A").entity_id,
            original.entity_by_label("B").entity_id,
        ),
        label="axis",
    )
    loaded = Document.from_json(original.to_json())
    assert loaded.to_dict() == original.to_dict()
    assert loaded.entity_by_label("beam_B1").entity_id == original.entity_by_label(
        "beam_B1"
    ).entity_id
    assert loaded.tagged("level_1") == original.tagged("level_1")
    assert isinstance(loaded.entity_by_label("axis"), Polyline)


def test_json_is_the_ops_log() -> None:
    document = Document()
    document.add_point(0.0, 0.0, 0.0, label="A")
    payload = json.loads(document.to_json())
    assert payload["schema"] == "apeCAD.document.v0"
    assert payload["units"] == "mm"
    assert payload["ops"][0]["op"] == "AddPoint"
    assert payload["ops"][0]["entity_id"] == 1


def test_unknown_schema_is_rejected() -> None:
    with pytest.raises(DocumentError, match="unsupported schema"):
        Document.from_dict({"schema": "other", "units": "mm", "ops": []})


def test_unknown_op_is_rejected() -> None:
    with pytest.raises(DocumentError, match="unknown operation"):
        Document.from_dict(
            {
                "schema": "apeCAD.document.v0",
                "units": "mm",
                "ops": [{"op": "NotARealOp"}],
            }
        )
