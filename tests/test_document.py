from __future__ import annotations

import json
import math

import pytest

from apeCAD import Box, Document, DocumentError, Line, Polyline


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
    assert isinstance(slab, Box)
    assert beam.start_id == document.entity_by_label("A").entity_id
    assert slab.size_xyz_mm.z_mm == 200.0
    assert document.tagged("level_1") == frozenset(
        {document.entity_by_label("A").entity_id, document.entity_by_label("B").entity_id}
    )


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
