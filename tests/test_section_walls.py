"""Section mode stage C2 (ADR 0024): outlines, wall chains and legs, leg steel, cover guides."""

from __future__ import annotations

import dataclasses
import json
import math
from typing import cast

import pytest

import apeCAD
from apeCAD import ConcreteFace, CoverGuide, Document, DocumentError, LegSteel, WallLeg
from apeCAD.catalog import apply
from apeCAD.geometry import XYZ
from apeCAD.ops import (
    AddSectionOutline,
    AddWallChain,
    PointAt,
    SetCover,
    op_from_dict,
    op_to_dict,
)
from apeCAD.scratchpad.payload import scene_payload
from apeCAD.section.geometry import signed_area

STEEL = LegSteel("Ø10", 200.0, 2)


def _at(x: float, y: float) -> PointAt:
    return PointAt(XYZ(float(x), float(y), 0.0))


def _ring_xy(doc: Document, face: ConcreteFace) -> list[tuple[float, float]]:
    ring: list[tuple[float, float]] = []
    for point_id in face.point_ids:
        point = doc.entity(point_id)
        assert isinstance(point, apeCAD.Point)
        ring.append((point.xyz_mm.x_mm, point.xyz_mm.y_mm))
    return ring


def _leg_xy(doc: Document, leg: WallLeg) -> tuple[tuple[float, float], tuple[float, float]]:
    ends: list[tuple[float, float]] = []
    for point_id in (leg.start_id, leg.end_id):
        point = doc.entity(point_id)
        assert isinstance(point, apeCAD.Point)
        ends.append((point.xyz_mm.x_mm, point.xyz_mm.y_mm))
    return ends[0], ends[1]


def _assert_one_op_one_undo(doc: Document) -> None:
    assert len(doc.ops()) == 1
    doc.undo()
    assert doc.ops() == ()
    assert doc.entity_ids() == frozenset()


def test_new_kinds_are_frozen_and_exported() -> None:
    for kind in (WallLeg, CoverGuide, LegSteel):
        assert kind.__name__ in apeCAD.__all__
        params = cast(object, getattr(kind, "__dataclass_params__"))  # noqa: B009
        assert getattr(params, "frozen") is True  # noqa: B009


def test_a_rectangle_outline_is_one_op_and_one_undo() -> None:
    doc = Document()
    # Given clockwise: stored counter-clockwise.
    face = doc.add_section_outline(
        [_at(0, 0), _at(0, 2000), _at(300, 2000), _at(300, 0)], "H30", label="P1"
    )
    assert face.role == "solid" and face.material == "H30"
    assert signed_area(_ring_xy(doc, face)) == pytest.approx(300.0 * 2000.0)
    assert len(doc.points()) == 4
    _assert_one_op_one_undo(doc)


def test_an_inclined_hexagon_outline_is_one_op_and_one_undo() -> None:
    doc = Document()
    angle = math.radians(30.0)
    hexagon = [
        _at(1000.0 * math.cos(angle + k * math.pi / 3), 1000.0 * math.sin(angle + k * math.pi / 3))
        for k in range(6)
    ]
    face = doc.add_section_outline(hexagon, "H35")
    assert len(face.point_ids) == 6
    assert signed_area(_ring_xy(doc, face)) > 0.0
    assert len(doc.concrete_faces()) == 1
    _assert_one_op_one_undo(doc)


def test_a_bow_tie_outline_is_refused_and_changes_nothing() -> None:
    doc = Document()
    doc.add_point(5000.0, 0.0, 0.0)
    before = doc.to_json()
    with pytest.raises(DocumentError, match="not simple"):
        doc.add_section_outline([_at(0, 0), _at(1000, 1000), _at(1000, 0), _at(0, 1000)], "H30")
    assert doc.to_json() == before
    assert len(doc.points()) == 1


def test_an_outline_has_no_role_argument() -> None:
    names = {field.name for field in dataclasses.fields(AddSectionOutline)}
    assert "role" not in names
    with pytest.raises(DocumentError, match="z = 0"):
        Document().add_section_outline([_at(0, 0), _at(100, 0), PointAt(XYZ(0, 100, 5))], "H30")


def test_an_l_chain_gives_one_face_and_two_legs_in_one_op() -> None:
    doc = Document()
    axis = [_at(0, 0), _at(3000, 0), _at(3000, 2000)]
    face = doc.add_wall_chain(axis, 200.0, "H30", horizontal=STEEL, label="L1")
    assert face.label == "L1"
    assert sorted(_ring_xy(doc, face)) == sorted(
        [(0.0, -100.0), (3100.0, -100.0), (3100.0, 2000.0), (2900.0, 2000.0), (2900.0, 100.0),
         (0.0, 100.0)]
    )
    assert signed_area(_ring_xy(doc, face)) > 0.0
    legs = doc.wall_legs()
    assert len(legs) == 2
    assert [_leg_xy(doc, leg) for leg in legs] == [
        ((0.0, 0.0), (3000.0, 0.0)),
        ((3000.0, 0.0), (3000.0, 2000.0)),
    ]
    assert legs[0].end_id == legs[1].start_id  # the legs share the corner axis point
    assert all(leg.face_id == face.entity_id for leg in legs)
    assert all(leg.thickness_mm == 200.0 and leg.horizontal == STEEL for leg in legs)
    _assert_one_op_one_undo(doc)


def test_a_chain_takes_one_thickness_per_segment() -> None:
    doc = Document()
    doc.add_wall_chain([_at(0, 0), _at(3000, 0), _at(3000, 2000)], (300.0, 200.0), "H30")
    assert [leg.thickness_mm for leg in doc.wall_legs()] == [300.0, 200.0]
    with pytest.raises(DocumentError, match="1 or 2 thicknesses"):
        AddWallChain(point_ids=(1, 2, 3), thickness_mm=(1.0, 2.0, 3.0), material="H30")


def test_three_legs_on_a_t_polygon() -> None:
    doc = Document()
    tee = [
        (850, 0), (1150, 0), (1150, 1700), (2000, 1700), (2000, 2000), (0, 2000), (0, 1700),
        (850, 1700),
    ]
    face = doc.add_section_outline([_at(x, y) for x, y in tee], "H30", label="T1")
    junction = _at(1000, 1850)
    flange_left = doc.add_wall_leg(_at(0, 1850), junction, 300.0, face.entity_id, horizontal=STEEL)
    flange_right = doc.add_wall_leg(junction, _at(2000, 1850), 300.0, face.entity_id)
    web = doc.add_wall_leg(_at(1000, 0), junction, 300.0, face.entity_id, label="web")
    assert len(doc.wall_legs()) == 3
    # The junction is one point: coordinates within 1 mm reuse it (ADR 0030).
    assert flange_left.end_id == flange_right.start_id == web.end_id
    assert flange_right.horizontal is None
    assert len(doc.ops()) == 4


def test_a_leg_needs_a_concrete_face_and_two_distinct_ends() -> None:
    doc = Document()
    point = doc.add_point(0.0, 0.0, 0.0)
    face = doc.add_section_outline([_at(0, 0), _at(300, 0), _at(300, 300)], "H30")
    with pytest.raises(DocumentError, match="not a concrete face"):
        doc.add_wall_leg(_at(10, 10), _at(200, 10), 100.0, point.entity_id)
    with pytest.raises(DocumentError, match="two distinct axis points"):
        doc.add_wall_leg(_at(10, 10), _at(10.5, 10), 100.0, face.entity_id)
    with pytest.raises(DocumentError, match="positive"):
        doc.add_wall_leg(_at(10, 10), _at(200, 10), 0.0, face.entity_id)


def test_deleting_a_face_cascades_to_its_legs_and_cover_and_undo_restores_them() -> None:
    doc = Document()
    face = doc.add_wall_chain([_at(0, 0), _at(3000, 0), _at(3000, 2000)], 200.0, "H30")
    guide = doc.set_cover(face.entity_id, 40.0, 10.0, 20.0)
    children = doc.brep().children[face.entity_id]
    legs = [leg.entity_id for leg in doc.wall_legs()]
    assert set(legs) | {guide.entity_id} <= set(children)
    before = {entity_id: doc.entity(entity_id) for entity_id in doc.entity_ids()}

    doc.delete([face.entity_id])
    assert doc.entity_ids() == frozenset()  # face, ring, legs, axis points and guide

    doc.undo()
    assert {entity_id: doc.entity(entity_id) for entity_id in doc.entity_ids()} == before


def test_deleting_a_leg_keeps_the_face_and_a_shared_axis_point() -> None:
    doc = Document()
    face = doc.add_wall_chain([_at(0, 0), _at(3000, 0), _at(3000, 2000)], 200.0, "H30")
    first, second = doc.wall_legs()
    doc.delete([first.entity_id])
    assert doc.wall_legs() == (second,)
    assert face.entity_id in doc.entity_ids()
    assert first.start_id not in doc.entity_ids()
    assert first.end_id in doc.entity_ids()  # still the second leg's start


def test_leg_reinforcement_set_undo_and_json_round_trip() -> None:
    doc = Document()
    doc.add_wall_chain([_at(0, 0), _at(3000, 0)], 250.0, "H30")
    (leg,) = doc.wall_legs()
    assert leg.horizontal is None

    doc.set_leg_reinforcement(leg.entity_id, "Ø12", 150.0, 2)
    steel = LegSteel("Ø12", 150.0, 2)
    assert doc.wall_legs()[0].horizontal == steel

    reopened = Document.from_json(doc.to_json())
    assert reopened.wall_legs() == doc.wall_legs()
    assert [op_to_dict(op) for op in reopened.ops()] == [op_to_dict(op) for op in doc.ops()]
    raw = json.loads(doc.to_json())["ops"][-1]
    assert raw == {
        "op": "SetLegReinforcement",
        "leg_id": leg.entity_id,
        "designation": "Ø12",
        "spacing_mm": 150.0,
        "curtains": 2,
    }

    doc.undo()
    assert doc.wall_legs()[0].horizontal is None


@pytest.mark.parametrize(
    ("designation", "spacing", "curtains", "fragment"),
    [
        ("Ø11", 150.0, 2, "unknown bar designation"),
        ("Ø12", 0.0, 2, "spacing_mm must be positive"),
        ("Ø12", 150.0, 0, "curtains must be a positive count"),
    ],
)
def test_leg_steel_is_checked(
    designation: str, spacing: float, curtains: int, fragment: str
) -> None:
    doc = Document()
    doc.add_wall_chain([_at(0, 0), _at(3000, 0)], 250.0, "H30")
    with pytest.raises(DocumentError, match=fragment):
        doc.set_leg_reinforcement(doc.wall_legs()[0].entity_id, designation, spacing, curtains)


def test_every_c2_op_round_trips_through_json() -> None:
    doc = Document()
    face = doc.add_wall_chain(
        [_at(0, 0), _at(3000, 0), _at(3000, 2000)], (250.0, 200.0), "H30", horizontal=STEEL
    )
    outline = doc.add_section_outline([_at(5000, 0), _at(5300, 0), _at(5300, 2000)], "H35")
    doc.add_wall_leg(_at(5100, 100), _at(5200, 1500), 150.0, outline.entity_id, horizontal=STEEL)
    doc.set_leg_reinforcement(doc.wall_legs()[0].entity_id, "Ø8", 100.0, 1)
    doc.set_cover(face.entity_id, 40.0, 10.0, 20.0)
    kinds = {type(op).__name__ for op in doc.ops()}
    assert kinds == {
        "AddWallChain", "AddSectionOutline", "AddWallLeg", "SetLegReinforcement", "SetCover",
    }
    for op in doc.ops():
        assert op_from_dict(op_to_dict(op)) == op
    reopened = Document.from_json(doc.to_json())
    assert reopened.to_json() == doc.to_json()
    assert {i: reopened.entity(i) for i in reopened.entity_ids()} == {
        i: doc.entity(i) for i in doc.entity_ids()
    }
    chain = json.loads(doc.to_json())["ops"][0]
    assert chain["horizontal"] == {"designation": "Ø10", "spacing_mm": 200.0, "curtains": 2}
    assert len(chain["ring"]) == 6 and all("id" in vertex for vertex in chain["ring"])
    assert len(chain["leg_ids"]) == 2


def test_cover_inset_of_a_300_by_2000_face() -> None:
    doc = Document()
    face = doc.add_section_outline([_at(0, 0), _at(300, 0), _at(300, 2000), _at(0, 2000)], "H30")
    guide = doc.set_cover(face.entity_id, 40.0, 10.0, 20.0)
    (item,) = cast(list[dict[str, object]], scene_payload(doc)["cover_guides"])
    assert item["entity_id"] == guide.entity_id
    assert item["bar_centre_inset_mm"] == 60.0  # 40 cover + 10 tie + 20 / 2
    assert item["bar_centre_ring_mm"] == [[60.0, 60.0], [240.0, 60.0], [240.0, 1940.0],
                                          [60.0, 1940.0]]
    assert item["cover_ring_mm"] == [[40.0, 40.0], [260.0, 40.0], [260.0, 1960.0],
                                     [40.0, 1960.0]]
    assert item["reason"] is None


def test_a_collapsed_cover_inset_is_null_with_a_reason() -> None:
    doc = Document()
    face = doc.add_section_outline([_at(0, 0), _at(300, 0), _at(300, 2000), _at(0, 2000)], "H30")
    doc.set_cover(face.entity_id, 140.0, 10.0, 20.0)  # bar centres at 160 > 150: they cross
    (item,) = cast(list[dict[str, object]], scene_payload(doc)["cover_guides"])
    assert item["cover_ring_mm"] is not None
    assert item["bar_centre_ring_mm"] is None
    assert "bar-centre ring at 160 mm collapses" in cast(str, item["reason"])
    doc.set_cover(face.entity_id, 200.0, 10.0, 20.0)
    (item,) = cast(list[dict[str, object]], scene_payload(doc)["cover_guides"])
    assert item["cover_ring_mm"] is None and item["bar_centre_ring_mm"] is None
    assert "cover ring at 200 mm collapses" in cast(str, item["reason"])


def test_a_face_has_one_cover_guide() -> None:
    doc = Document()
    face = doc.add_section_outline([_at(0, 0), _at(300, 0), _at(300, 2000), _at(0, 2000)], "H30")
    first = doc.set_cover(face.entity_id, 40.0, 10.0, 20.0)
    second = doc.set_cover(face.entity_id, 25.0, 0.0, 16.0)  # a wall without hoops
    assert second.entity_id == first.entity_id
    assert doc.cover_guides() == (second,)
    assert second.cover_mm == 25.0 and second.tie_diameter_mm == 0.0
    doc.undo()
    assert doc.cover_guides() == (first,)
    with pytest.raises(DocumentError, match="tie_diameter_mm"):
        SetCover(face_id=face.entity_id, cover_mm=40.0, tie_diameter_mm=-1.0, bar_diameter_mm=20.0)
    with pytest.raises(DocumentError, match="not a concrete face"):
        doc.set_cover(face.point_ids[0], 40.0, 10.0, 20.0)


def test_moving_a_face_takes_its_legs_and_a_clone_takes_legs_and_cover() -> None:
    doc = Document()
    face = doc.add_wall_chain([_at(0, 0), _at(3000, 0), _at(3000, 2000)], 200.0, "H30")
    doc.set_cover(face.entity_id, 40.0, 10.0, 20.0)
    doc.translate([face.entity_id], 1000.0, 0.0, 0.0)
    assert [_leg_xy(doc, leg) for leg in doc.wall_legs()] == [
        ((1000.0, 0.0), (4000.0, 0.0)),
        ((4000.0, 0.0), (4000.0, 2000.0)),
    ]
    doc.mirror([face.entity_id], 0.0, 0.0, 0.0, 1.0)
    moved = doc.concrete_faces()[0]
    assert signed_area(_ring_xy(doc, moved)) > 0.0  # still CCW
    assert _leg_xy(doc, doc.wall_legs()[0]) == ((-1000.0, 0.0), (-4000.0, 0.0))

    doc.array_linear([face.entity_id], 0.0, 5000.0, 0.0, copies=1)
    faces = doc.concrete_faces()
    assert len(faces) == 2 and len(doc.wall_legs()) == 4 and len(doc.cover_guides()) == 2
    copy = faces[1].entity_id
    assert {leg.face_id for leg in doc.wall_legs()} == {face.entity_id, copy}
    assert {guide.face_id for guide in doc.cover_guides()} == {face.entity_id, copy}
    reopened = Document.from_json(doc.to_json())
    assert reopened.wall_legs() == doc.wall_legs()


def test_scene_payload_ships_legs_and_cover_guides() -> None:
    doc = Document()
    face = doc.add_wall_chain([_at(0, 0), _at(3000, 0)], 250.0, "H30", horizontal=STEEL)
    doc.set_cover(face.entity_id, 40.0, 10.0, 20.0)
    scene = scene_payload(doc)
    (leg,) = cast(list[dict[str, object]], scene["wall_legs"])
    assert leg["face_id"] == face.entity_id and leg["thickness_mm"] == 250.0
    assert leg["horizontal"] == {"designation": "Ø10", "spacing_mm": 200.0, "curtains": 2}
    json.dumps(scene)


def test_catalog_examples_apply_to_an_outline() -> None:
    doc = Document()
    outline = apply(doc, "AddSectionOutline", _example("AddSectionOutline"))
    assert outline.created_id == 5
    leg = apply(doc, "AddWallLeg", _example("AddWallLeg"))
    assert leg.created_id == 8
    apply(doc, "SetLegReinforcement", _example("SetLegReinforcement"))
    assert doc.wall_legs()[0].horizontal == LegSteel("Ø12", 150.0, 2)
    cover = apply(doc, "SetCover", _example("SetCover"))
    assert isinstance(doc.entity(cast(int, cover.created_id)), CoverGuide)
    chain = apply(doc, "AddWallChain", _example("AddWallChain"))
    assert len(cast(list[int], chain.op["leg_ids"])) == 2


def _example(name: str) -> dict[str, object]:
    from apeCAD.catalog.entries import CATALOG

    return CATALOG[name].example
