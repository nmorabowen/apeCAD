from __future__ import annotations

import pytest

from apeCAD import Document, DocumentError


def test_line_becomes_a_member_with_length_and_axis() -> None:
    document = Document()
    a = document.add_point(0.0, 0.0, 0.0, label="A")
    b = document.add_point(6000.0, 0.0, 0.0, label="B")
    document.add_line(a.entity_id, b.entity_id, label="beam_B1")
    document.tag("level_1", [a.entity_id, b.entity_id])
    frame = document.to_frame()
    assert frame.units == "mm"
    assert len(frame.nodes) == 2
    member = frame.member_by_label("beam_B1")
    assert member.length_mm == 6000.0
    assert member.axis_xyz.to_tuple() == (1.0, 0.0, 0.0)
    assert member.section_id is None
    assert frame.node(a.entity_id).tags == ("level_1",)


def test_box_is_a_volume_not_a_member() -> None:
    document = Document()
    document.add_box((0.0, 0.0, 0.0), (6000.0, 4000.0, 200.0), label="slab_L2")
    frame = document.to_frame()
    assert frame.members == ()
    assert len(frame.volumes) == 1
    assert frame.volumes[0].label == "slab_L2"


def test_closed_polyline_emits_one_member_per_segment() -> None:
    document = Document()
    p1 = document.add_point(0.0, 0.0, 0.0)
    p2 = document.add_point(1000.0, 0.0, 0.0)
    p3 = document.add_point(0.0, 1000.0, 0.0)
    document.add_polyline(
        (p1.entity_id, p2.entity_id, p3.entity_id),
        closed=True,
        label="loop",
    )
    frame = document.to_frame()
    assert len(frame.members) == 3
    assert frame.member_by_label("loop[0]").length_mm == 1000.0
    assert frame.member_by_label("loop[2]").start_id == p3.entity_id


def test_zero_length_polyline_segment_is_rejected() -> None:
    document = Document()
    a = document.add_point(0.0, 0.0, 0.0)
    b = document.add_point(0.0, 0.0, 0.0)
    document.add_polyline((a.entity_id, b.entity_id))
    with pytest.raises(DocumentError, match="zero-length"):
        document.to_frame()
