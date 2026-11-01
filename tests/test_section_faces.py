"""Section-draft v2 faces (ADR 0039 decisions 2-4): AddSectionFace, AddFaceHole, AddSteelShape.

Oracles: ring orientation is the sign of the shoelace area (boundary CCW, hole CW, spec
`section-draft-v2.md` "Ring orientation"); a translate or rotate maps a steel shape's anchor
exactly as it maps a point; every op round-trips through `to_json` / `from_json` and undo /
redo; delete follows ADR 0029.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterator
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from apeCAD import (
    XYZ,
    CircleBoundary,
    Document,
    DocumentError,
    RingBoundary,
    SectionFace,
    SteelShape,
)
from apeCAD.catalog import apply
from apeCAD.ops import AddFaceHole, PointAt, op_from_dict, op_to_dict
from apeCAD.scratchpad.server import ScratchpadServer

RECT_CW = ((0.0, 0.0), (0.0, 500.0), (400.0, 500.0), (400.0, 0.0))
HOLE_CCW = ((100.0, 100.0), (300.0, 100.0), (300.0, 400.0), (100.0, 400.0))
W_RING = (
    (-150.0, -175.0), (150.0, -175.0), (150.0, -155.0), (6.0, -155.0), (6.0, 155.0),
    (150.0, 155.0), (150.0, 175.0), (-150.0, 175.0), (-150.0, 155.0), (-6.0, 155.0),
    (-6.0, -155.0), (-150.0, -155.0),
)  # fmt: skip


def _at(xy: tuple[tuple[float, float], ...]) -> list[PointAt]:
    return [PointAt(XYZ(x, y, 0.0)) for x, y in xy]


def _area(document: Document, ring: RingBoundary) -> float:
    xy: list[tuple[float, float]] = []
    for pid in ring.point_ids:
        point = document.entity(pid)
        xy.append((point.xyz_mm.x_mm, point.xyz_mm.y_mm))  # type: ignore[union-attr]
    return 0.5 * sum(
        a[0] * b[1] - b[0] * a[1] for a, b in zip(xy, xy[1:] + xy[:1], strict=True)
    )


def _face(document: Document, face_id: int) -> SectionFace:
    face = document.entity(face_id)
    assert isinstance(face, SectionFace)
    return face


def _reopened(document: Document) -> Document:
    copy = Document.from_json(document.to_json())
    assert copy.to_json() == document.to_json()
    assert copy.section_faces() == document.section_faces()
    return copy


# --- AddSectionFace ---------------------------------------------------------------------


def test_a_cw_ring_is_stored_ccw_and_round_trips() -> None:
    doc = Document()
    face = doc.add_section_face("concrete", "H30", point_ids=_at(RECT_CW), label="col")
    assert face.role == "concrete" and face.material == "H30" and face.holes == ()
    assert isinstance(face.boundary, RingBoundary)
    assert _area(doc, face.boundary) == pytest.approx(400.0 * 500.0, rel=1e-12)
    assert _reopened(doc).entity_by_label("col") == face


def test_a_circle_face_is_exact_and_reuses_a_centre_within_1_mm() -> None:
    doc = Document()
    centre = doc.add_point(0.0, 0.0, 0.0).entity_id
    face = doc.add_section_face(
        "concrete", "H30", center_id=PointAt(XYZ(0.4, 0.0, 0.0)), radius_mm=300.0
    )
    assert face.boundary == CircleBoundary(center_id=centre, radius_mm=300.0)
    _reopened(doc)


def test_a_void_has_no_material_and_solid_roles_need_one() -> None:
    doc = Document()
    void = doc.add_section_face("void", None, point_ids=_at(HOLE_CCW))
    assert void.material is None
    with pytest.raises(DocumentError, match="void face takes no material"):
        doc.add_section_face("void", "H30", point_ids=_at(HOLE_CCW))
    with pytest.raises(DocumentError, match="steel face needs a material"):
        doc.add_section_face("steel", None, point_ids=_at(RECT_CW))
    with pytest.raises(DocumentError, match="role must be one of"):
        doc.add_section_face("solid", "H30", point_ids=_at(RECT_CW))
    with pytest.raises(DocumentError, match="void face, which takes no material"):
        doc.set_material([void.entity_id], "H30")


@pytest.mark.parametrize(
    ("kwargs", "fragment"),
    [
        ({}, "exactly one boundary"),
        (
            {"point_ids": _at(RECT_CW), "center_id": PointAt(XYZ(0, 0, 0)), "radius_mm": 5.0},
            "exactly one boundary",
        ),
        ({"point_ids": _at(RECT_CW[:2])}, "at least 3 vertices"),
        ({"center_id": PointAt(XYZ(0, 0, 0))}, "both center_id and radius_mm"),
        ({"center_id": PointAt(XYZ(0, 0, 0)), "radius_mm": 0.0}, "radius_mm must be positive"),
        ({"point_ids": _at(((0, 0), (10, 10), (10, 0), (0, 10)))}, "not simple"),
        ({"center_id": PointAt(XYZ(0, 0, 5)), "radius_mm": 5.0}, "z = 0"),
    ],
)
def test_bad_boundaries_are_refused_by_name(kwargs: dict[str, object], fragment: str) -> None:
    doc = Document()
    with pytest.raises(DocumentError, match=fragment):
        doc.add_section_face("concrete", "H30", **kwargs)  # type: ignore[arg-type]
    assert doc.ops() == ()


def test_set_material_renames_a_v2_face() -> None:
    doc = Document()
    face = doc.add_section_face("steel", "A36", point_ids=_at(RECT_CW))
    doc.set_material([face.entity_id], "A992")
    assert _face(doc, face.entity_id).material == "A992"


# --- AddFaceHole ------------------------------------------------------------------------


def test_holes_are_indexed_stored_cw_and_replayed() -> None:
    doc = Document()
    face = doc.add_section_face("concrete", "H30", point_ids=_at(RECT_CW))
    first = doc.add_face_hole(face.entity_id, point_ids=_at(HOLE_CCW))
    second = doc.add_face_hole(
        face.entity_id, center_id=PointAt(XYZ(200.0, 450.0, 0.0)), radius_mm=20.0
    )
    assert (first, second) == (0, 1)
    holes = _face(doc, face.entity_id).holes
    assert isinstance(holes[0], RingBoundary) and isinstance(holes[1], CircleBoundary)
    assert _area(doc, holes[0]) == pytest.approx(-200.0 * 300.0, rel=1e-12)
    committed = doc.ops()[-1]
    assert isinstance(committed, AddFaceHole) and committed.hole_index == 1
    assert op_from_dict(op_to_dict(committed)) == committed
    assert _face(_reopened(doc), face.entity_id).holes == holes


def test_a_cw_hole_stays_cw() -> None:
    doc = Document()
    face = doc.add_section_face("concrete", "H30", point_ids=_at(RECT_CW))
    doc.add_face_hole(face.entity_id, point_ids=_at(HOLE_CCW[::-1]))
    hole = _face(doc, face.entity_id).holes[0]
    assert isinstance(hole, RingBoundary)
    assert _area(doc, hole) < 0.0


def test_a_recorded_hole_index_that_disagrees_is_refused() -> None:
    doc = Document()
    face = doc.add_section_face("concrete", "H30", point_ids=_at(RECT_CW))
    stale = AddFaceHole(
        face_id=face.entity_id, center_id=PointAt(XYZ(200, 250, 0)), radius_mm=10.0,
        hole_index=3,
    )  # fmt: skip
    with pytest.raises(DocumentError, match="records hole 3"):
        doc.apply(stale)


def test_a_v1_concrete_face_takes_no_hole() -> None:
    doc = Document()
    v1 = doc.add_concrete_face(_at(RECT_CW), "H30")
    with pytest.raises(DocumentError, match="v1 concrete face, which has no holes"):
        doc.add_face_hole(v1.entity_id, point_ids=_at(HOLE_CCW))
    bar = doc.add_bar(10.0, 10.0, "Ø16")
    with pytest.raises(DocumentError, match="is not a section face"):
        doc.add_face_hole(bar.entity_id, point_ids=_at(HOLE_CCW))


# --- AddSteelShape ----------------------------------------------------------------------


def _w(doc: Document) -> SectionFace:
    return doc.add_steel_shape(
        _at(W_RING), "A992", "AISC 16", "W14X90", (100.0, 0.0), label="W"
    )


def test_a_steel_shape_keeps_its_provenance_and_ring() -> None:
    doc = Document()
    face = _w(doc)
    assert face.role == "steel" and face.material == "A992"
    assert face.shape == SteelShape("AISC 16", "W14X90", (100.0, 0.0), 0.0)
    assert isinstance(face.boundary, RingBoundary) and len(face.boundary.point_ids) == 12
    assert _area(doc, face.boundary) > 0.0
    assert _reopened(doc).entity_by_label("W") == face


def test_a_steel_shape_needs_its_ring() -> None:
    doc = Document()
    with pytest.raises(DocumentError, match="needs its resolved ring"):
        doc.add_steel_shape([], "A992", "AISC 16", "W14X90", (0.0, 0.0))


def test_translate_and_rotate_carry_the_shape() -> None:
    doc = Document()
    face = _w(doc)
    doc.translate([face.entity_id], 50.0, 20.0, 0.0)
    shape = _face(doc, face.entity_id).shape
    assert shape is not None and shape.anchor_mm == (150.0, 20.0)
    doc.rotate([face.entity_id], 0.0, 0.0, 90.0)
    shape = _face(doc, face.entity_id).shape
    assert shape is not None and shape.rotation_deg == 90.0
    assert shape.anchor_mm[0] == pytest.approx(-20.0, abs=1e-9)
    assert shape.anchor_mm[1] == pytest.approx(150.0, abs=1e-9)
    _reopened(doc)


def test_mirror_of_a_shape_is_refused_and_changes_nothing() -> None:
    doc = Document()
    face = _w(doc)
    before = doc.to_json()
    with pytest.raises(DocumentError, match="W14X90"):
        doc.mirror([face.entity_id], 0.0, 0.0, 0.0, 1000.0)
    assert doc.to_json() == before


def test_mirror_of_a_plain_face_restores_ring_orientation() -> None:
    doc = Document()
    face = doc.add_section_face("steel", "A36", point_ids=_at(RECT_CW))
    doc.add_face_hole(face.entity_id, point_ids=_at(HOLE_CCW))
    doc.mirror([face.entity_id], 1000.0, 0.0, 1000.0, 1000.0)
    mirrored = _face(doc, face.entity_id)
    assert isinstance(mirrored.boundary, RingBoundary)
    assert isinstance(mirrored.holes[0], RingBoundary)
    assert _area(doc, mirrored.boundary) > 0.0
    assert _area(doc, mirrored.holes[0]) < 0.0


def test_polar_array_turns_cloned_shapes() -> None:
    doc = Document()
    face = _w(doc)
    doc.array_polar([face.entity_id], 0.0, 0.0, 4)
    turns = sorted(f.shape.rotation_deg for f in doc.section_faces() if f.shape is not None)
    assert turns == [0.0, 90.0, 180.0, 270.0]
    _reopened(doc)


# --- delete cascade (ADR 0029), B-rep, sew ------------------------------------------------


def test_deleting_a_face_takes_its_ring_and_hole_points() -> None:
    doc = Document()
    face = doc.add_section_face("concrete", "H30", point_ids=_at(RECT_CW))
    doc.add_face_hole(face.entity_id, center_id=PointAt(XYZ(200, 250, 0)), radius_mm=50.0)
    assert set(doc.brep().children[face.entity_id]) == {p.entity_id for p in doc.points()}
    doc.delete([face.entity_id])
    assert doc.points() == () and doc.section_faces() == ()
    doc.undo()
    assert len(doc.points()) == 5 and len(doc.section_faces()) == 1


def test_deleting_a_hole_vertex_takes_the_face_but_not_its_other_parts() -> None:
    doc = Document()
    face = doc.add_section_face("concrete", "H30", point_ids=_at(RECT_CW))
    doc.add_face_hole(face.entity_id, point_ids=_at(HOLE_CCW))
    hole = _face(doc, face.entity_id).holes[0]
    assert isinstance(hole, RingBoundary)
    doc.delete([hole.point_ids[0]])
    assert doc.section_faces() == ()
    assert len(doc.points()) == 7


def test_a_shared_centre_survives_deleting_one_owner() -> None:
    doc = Document()
    outer = doc.add_section_face(
        "concrete", "H30", center_id=PointAt(XYZ(0, 0, 0)), radius_mm=300.0
    )
    inner = doc.add_section_face("void", None, center_id=PointAt(XYZ(0, 0, 0)), radius_mm=100.0)
    doc.delete([inner.entity_id])
    assert doc.section_faces() == (outer,)
    assert len(doc.points()) == 1


def test_sew_rewires_a_face_ring() -> None:
    doc = Document()
    face = doc.add_section_face("concrete", "H30", point_ids=_at(RECT_CW))
    loose = doc.add_point(400.5, 500.0, 0.0)
    ring = face.boundary
    assert isinstance(ring, RingBoundary)
    corner = next(
        pid for pid in ring.point_ids if doc.entity(pid).xyz_mm == XYZ(400.0, 500.0, 0.0)  # type: ignore[union-attr]
    )
    doc.sew([corner, loose.entity_id])
    sewn = _face(doc, face.entity_id).boundary
    assert isinstance(sewn, RingBoundary) and len(sewn.point_ids) == 4
    assert set(sewn.point_ids) <= {p.entity_id for p in doc.points()}
    _reopened(doc)


# --- every op: undo / redo, the catalog and /api/op ---------------------------------------


def test_each_face_op_undoes_and_redoes() -> None:
    doc = Document()
    steps = [
        lambda: doc.add_section_face("concrete", "H30", point_ids=_at(RECT_CW)),
        lambda: doc.add_face_hole(1 + 4, point_ids=_at(HOLE_CCW)),
        lambda: _w(doc),
    ]
    for step in steps:
        before = doc.to_json()
        step()
        after = doc.to_json()
        doc.undo()
        assert doc.to_json() == before
        doc.redo()
        assert doc.to_json() == after


def test_catalog_apply_draws_a_cft() -> None:
    """A CFT (spec "Overlap precedence"): concrete circle under a steel tube with a hole."""
    doc = Document()
    core = apply(
        doc,
        "AddSectionFace",
        {"role": "concrete", "material": "H40", "center_id": {"xyz": [0, 0, 0]}, "radius_mm": 290},
    )
    tube = apply(
        doc,
        "AddSectionFace",
        {"role": "steel", "material": "A500", "center_id": 1, "radius_mm": 300},
    )
    hole = apply(
        doc, "AddFaceHole", {"face_id": tube.created_id, "center_id": 1, "radius_mm": 290}
    )
    assert hole.op["hole_index"] == 0 and hole.created_id is None
    shape = apply(
        doc,
        "AddSteelShape",
        {
            "point_ids": [{"xyz": [x, y, 0]} for x, y in W_RING],
            "material": "A992",
            "catalog": "AISC 16",
            "designation": "W14X90",
            "anchor_mm": [0, 0],
        },
    )
    faces = {f.entity_id: f for f in doc.section_faces()}
    assert faces[tube.created_id].holes == (CircleBoundary(1, 290.0),)  # type: ignore[index]
    assert faces[core.created_id].role == "concrete"  # type: ignore[index]
    assert faces[shape.created_id].shape is not None  # type: ignore[index]
    _reopened(doc)


@pytest.fixture
def server() -> Iterator[ScratchpadServer]:
    bound = ScratchpadServer(("127.0.0.1", 0), Document())
    thread = Thread(target=bound.serve_forever, daemon=True)
    thread.start()
    yield bound
    bound.shutdown()
    bound.server_close()


def _post(server: ScratchpadServer, body: dict[str, object]) -> dict[str, object]:
    port = server.server_address[1]
    request = Request(
        f"http://127.0.0.1:{port}/api/op",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request) as response:
        loaded: object = json.loads(response.read().decode("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_face_ops_post_through_the_op_api(server: ScratchpadServer) -> None:
    ring = [{"xyz": [x, y, 0]} for x, y in RECT_CW]
    _post(server, {"op": "AddSectionFace", "role": "concrete", "material": "H30", "point_ids": ring})
    _post(server, {"op": "AddFaceHole", "face_id": 5, "point_ids": [{"xyz": list(p) + [0]} for p in HOLE_CCW]})
    payload = _post(
        server,
        {"op": "AddSteelShape", "point_ids": [{"xyz": [x, y, 0]} for x, y in W_RING],
         "material": "A992", "catalog": "AISC 16", "designation": "W14X90", "anchor_mm": [0, 0]},
    )  # fmt: skip
    document = payload["document"]
    assert isinstance(document, dict)
    names = [op["op"] for op in document["ops"]]  # type: ignore[index]
    assert names == ["AddSectionFace", "AddFaceHole", "AddSteelShape"]
    with pytest.raises(HTTPError) as refused:
        _post(server, {"op": "AddSectionFace", "role": "void", "material": "H30", "point_ids": ring})
    assert refused.value.code == 400
    body = json.loads(refused.value.read().decode("utf-8"))
    assert body["code"] == "INVALID_ARGUMENT" and "no material" in body["error"]


def test_area_helper_matches_the_shoelace_oracle() -> None:
    doc = Document()
    face = doc.add_section_face("concrete", "H30", point_ids=_at(RECT_CW))
    assert isinstance(face.boundary, RingBoundary)
    assert math.isclose(_area(doc, face.boundary), 200000.0, rel_tol=1e-15)
