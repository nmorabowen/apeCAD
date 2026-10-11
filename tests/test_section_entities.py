"""Section mode stage C1 (ADR 0024): entities, primitive ops, schema v1, graph integration."""

from __future__ import annotations

import dataclasses
import itertools
import json
from collections.abc import Iterator
from pathlib import Path
from threading import Thread
from typing import cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

import apeCAD
from apeCAD import Bar, ConcreteFace, Crosstie, Document, DocumentError, Hoop
from apeCAD.catalog import apply
from apeCAD.geometry import XYZ
from apeCAD.ops import (
    AddBar,
    AddConcreteFace,
    AddCrosstie,
    AddHoop,
    PointAt,
    SetBarSize,
    SetMaterial,
    SetTransverse,
    op_from_dict,
    op_to_dict,
)
from apeCAD.scratchpad.payload import scene_payload
from apeCAD.scratchpad.server import ScratchpadServer
from apeCAD.section.geometry import signed_area

FIXTURES = Path(__file__).parent / "fixtures"


def _xy(doc: Document, bar_id: int) -> tuple[float, float]:
    bar = doc.entity(bar_id)
    assert isinstance(bar, Bar)
    xyz = doc.entity(bar.point_id)
    assert isinstance(xyz, apeCAD.Point)
    return (xyz.xyz_mm.x_mm, xyz.xyz_mm.y_mm)


def _cage(doc: Document, xs: tuple[float, ...], ys: tuple[float, ...]) -> dict[str, int]:
    """Bars on a grid, keyed "x,y" so tests can name them by position."""
    return {f"{x:g},{y:g}": doc.add_bar(x, y, "Ø16").entity_id for y in ys for x in xs}


def _section() -> tuple[Document, dict[str, int]]:
    doc = Document()
    corners = ((0.0, 0.0), (400.0, 0.0), (400.0, 600.0), (0.0, 600.0))
    doc.add_concrete_face([PointAt(XYZ(x, y, 0.0)) for x, y in corners], "H30")
    bars = _cage(doc, (60.0, 340.0), (60.0, 300.0, 540.0))
    return doc, bars


def test_entity_kinds_are_frozen_and_exported() -> None:
    for kind in (Bar, Hoop, Crosstie, ConcreteFace):
        assert kind.__name__ in apeCAD.__all__
        assert dataclasses.is_dataclass(kind)
        params = cast(object, getattr(kind, "__dataclass_params__"))  # noqa: B009
        assert getattr(params, "frozen") is True  # noqa: B009
    doc, bars = _section()
    bar = doc.entity(bars["60,60"])
    with pytest.raises(dataclasses.FrozenInstanceError):
        bar.label = "x"  # type: ignore[misc]


def test_every_section_op_round_trips() -> None:
    doc, bars = _section()
    hoop = doc.add_hoop(list(bars.values()), "Ø10", 100.0, label="H1")
    tie = doc.add_crosstie(bars["60,300"], bars["340,300"], "Ø10", 150.0, hooks="135-90")
    doc.set_bar_size([bars["60,60"]], "Ø20")
    doc.set_material([doc.concrete_faces()[0].entity_id], "H35")
    doc.set_transverse([hoop.entity_id, tie.entity_id], spacing_mm=125.0)
    kinds = {type(op).__name__ for op in doc.ops()}
    assert {"AddConcreteFace", "AddBar", "AddHoop", "AddCrosstie"} <= kinds
    assert {"SetBarSize", "SetMaterial", "SetTransverse"} <= kinds
    for op in doc.ops():
        assert op_from_dict(json.loads(json.dumps(op_to_dict(op)))) == op
    reopened = Document.from_json(doc.to_json())
    assert reopened.to_json() == doc.to_json()
    assert reopened.bars() == doc.bars()
    assert reopened.hoops() == doc.hoops()
    assert reopened.crossties() == doc.crossties()
    assert reopened.concrete_faces() == doc.concrete_faces()
    assert json.loads(doc.to_json())["schema"] == "apeCAD.document.v1"


def test_set_ops_change_what_they_name_and_undo() -> None:
    doc, bars = _section()
    face = doc.concrete_faces()[0]
    hoop = doc.add_hoop(list(bars.values()), "Ø10", 100.0)
    tie = doc.add_crosstie(bars["60,300"], bars["340,300"], "Ø10", 150.0)
    doc.set_bar_size([bars["60,60"], bars["340,60"]], "Ø25")
    resized = [doc.entity(bars[key]) for key in ("60,60", "340,60")]
    for bar in resized:
        assert isinstance(bar, Bar) and (bar.designation, bar.diameter_mm) == ("Ø25", 25.0)
    doc.set_material([face.entity_id], "H40")
    assert doc.concrete_faces()[0].material == "H40"
    doc.set_transverse([hoop.entity_id, tie.entity_id], designation="Ø12", spacing_mm=80.0)
    doc.set_transverse([tie.entity_id], hooks="135-90")
    assert doc.hoops()[0] == dataclasses.replace(
        hoop, designation="Ø12", diameter_mm=12.0, spacing_mm=80.0
    )
    assert doc.crossties()[0].hooks == "135-90"
    for _ in range(4):
        doc.undo()
    assert doc.hoops()[0] == hoop
    assert doc.crossties()[0] == tie
    assert doc.concrete_faces()[0] == face
    assert doc.entity(bars["60,60"]) == dataclasses.replace(resized[0], designation="Ø16",
                                                           diameter_mm=16.0)


def test_bad_section_ops_are_refused() -> None:
    doc, bars = _section()
    face_id = doc.concrete_faces()[0].entity_id
    a, b = bars["60,60"], bars["340,60"]
    with pytest.raises(DocumentError, match="unknown bar designation"):
        AddBar(x_mm=0.0, y_mm=0.0, designation="#5")
    with pytest.raises(DocumentError, match="90-90"):
        AddCrosstie(bar_a_id=a, bar_b_id=b, designation="Ø10", spacing_mm=100.0, hooks="90-90")
    with pytest.raises(DocumentError, match="two distinct bars"):
        AddCrosstie(bar_a_id=a, bar_b_id=a, designation="Ø10", spacing_mm=100.0)
    with pytest.raises(DocumentError, match="spacing_mm must be positive"):
        AddHoop(bar_ids=(a, b), designation="Ø10", spacing_mm=0.0)
    with pytest.raises(DocumentError, match="hoop hooks"):
        AddHoop(bar_ids=(a, b), designation="Ø10", spacing_mm=100.0, hooks="135-90")
    with pytest.raises(DocumentError, match="material"):
        SetMaterial(entity_ids=(face_id,), material=" ")
    before = doc.to_json()
    with pytest.raises(DocumentError, match="hull"):
        doc.add_hoop([a, b], "Ø10", 100.0)  # two bars: no ring
    with pytest.raises(DocumentError, match="hull"):
        doc.add_hoop([bars["60,60"], bars["60,300"], bars["60,540"]], "Ø10", 100.0)  # collinear
    with pytest.raises(DocumentError, match="not a bar"):
        doc.add_hoop([a, b, face_id], "Ø10", 100.0)
    with pytest.raises(DocumentError, match="not a bar"):
        doc.set_bar_size([face_id], "Ø20")
    with pytest.raises(DocumentError, match="not a concrete face"):
        doc.set_material([a], "H30")
    with pytest.raises(DocumentError, match="not a hoop or a crosstie"):
        doc.set_transverse([a], spacing_mm=100.0)
    with pytest.raises(DocumentError, match="not simple"):
        doc.add_concrete_face(
            [PointAt(XYZ(x, y, 0.0)) for x, y in ((0, 0), (1, 1), (1, 0), (0, 1))], "H30"
        )
    with pytest.raises(DocumentError, match="z = 0"):
        doc.add_concrete_face(
            [PointAt(XYZ(x, y, 5.0)) for x, y in ((0, 0), (1, 0), (1, 1))], "H30"
        )
    assert doc.to_json() == before


def test_hoop_order_is_independent_of_selection_order() -> None:
    doc, bars = _section()
    ids = list(bars.values())
    rings = {doc.add_hoop(order, "Ø10", 100.0).bar_ids for order in itertools.permutations(ids)}
    assert len(rings) == 1
    (ring,) = rings
    assert ring == (bars["60,60"], bars["340,60"], bars["340,540"], bars["60,540"])


def test_two_by_six_selection_gives_a_four_bar_ring() -> None:
    doc = Document()
    bars = _cage(doc, (50.0, 250.0), tuple(50.0 + 200.0 * k for k in range(6)))
    hoop = doc.add_hoop(list(reversed(bars.values())), "Ø10", 100.0)
    assert hoop.bar_ids == (bars["50,50"], bars["250,50"], bars["250,1050"], bars["50,1050"])


def test_add_bar_always_allocates_a_fresh_point() -> None:
    doc = Document()
    existing = doc.add_point(100.0, 100.0, 0.0)
    first = doc.add_bar(100.0, 100.0, "Ø16")
    second = doc.add_bar(100.2, 100.0, "Ø16")
    assert len({existing.entity_id, first.point_id, second.point_id}) == 3
    assert isinstance(doc.ops()[1], AddBar) and doc.ops()[1].point_id == first.point_id
    # A drawn vertex never snaps onto a bar's point, and a bar's point is not a line end.
    line = doc.add_line(PointAt(XYZ(100.3, 100.0, 0.0)), PointAt(XYZ(900.0, 0.0, 0.0)))
    assert line.start_id == existing.entity_id
    with pytest.raises(DocumentError, match="belongs to bar"):
        doc.add_line(first.point_id, existing.entity_id)
    with pytest.raises(DocumentError, match="belongs to bar"):
        doc.sew([first.entity_id, line.entity_id], tolerance_mm=5.0)


def test_deleting_a_bar_cascades_to_its_hoop_and_crosstie_and_undo_restores() -> None:
    doc, bars = _section()
    hoop = doc.add_hoop(list(bars.values()), "Ø10", 100.0)
    tie = doc.add_crosstie(bars["60,300"], bars["340,300"], "Ø10", 100.0)
    corner = doc.entity(bars["60,60"])
    assert isinstance(corner, Bar)
    before = doc.to_json()
    doc.delete([corner.entity_id])
    ids = doc.entity_ids()
    assert corner.entity_id not in ids and corner.point_id not in ids
    assert hoop.entity_id not in ids
    assert tie.entity_id in ids  # it does not use that bar
    assert len(doc.bars()) == 5  # the hoop died for losing a part; its other bars stay
    doc.delete([bars["60,300"]])
    assert tie.entity_id not in doc.entity_ids()
    doc.undo()
    doc.undo()
    assert doc.to_json() == before
    assert doc.hoops() == (hoop,) and doc.crossties() == (tie,)


def test_deleting_a_hoop_takes_the_bars_only_it_uses() -> None:
    doc, bars = _section()
    hoop = doc.add_hoop(list(bars.values()), "Ø10", 100.0)
    tie = doc.add_crosstie(bars["340,60"], bars["340,540"], "Ø10", 100.0)
    doc.delete([hoop.entity_id])
    left = {bar.entity_id for bar in doc.bars()}
    # The ring is the 4 corners: two go with it, two stay for the crosstie, and the
    # mid-side bars were never in the ring.
    assert left == {bars["340,60"], bars["340,540"], bars["60,300"], bars["340,300"]}
    assert doc.crossties() == (tie,)
    assert doc.brep().children[tie.entity_id] == (bars["340,60"], bars["340,540"])


def test_brep_children_of_section_entities() -> None:
    doc, bars = _section()
    hoop = doc.add_hoop(list(bars.values()), "Ø10", 100.0)
    children = doc.brep().children
    assert children[hoop.entity_id] == hoop.bar_ids
    bar = doc.entity(bars["60,60"])
    assert isinstance(bar, Bar)
    assert children[bar.entity_id] == (bar.point_id,)
    face = doc.concrete_faces()[0]
    assert children[face.entity_id] == face.point_ids


def test_mirror_keeps_hoop_and_face_rings_counter_clockwise() -> None:
    doc, bars = _section()
    face = doc.concrete_faces()[0]
    hoop = doc.add_hoop(list(bars.values()), "Ø10", 100.0)
    doc.mirror([hoop.entity_id, face.entity_id], 1000.0, 0.0, 1000.0, 1.0)  # about x = 1000
    mirrored = doc.hoops()[0]
    assert set(mirrored.bar_ids) == set(hoop.bar_ids)
    xy = {bar_id: _xy(doc, bar_id) for bar_id in mirrored.bar_ids}
    assert xy[mirrored.bar_ids[0]] == min(xy.values())  # the hull's form: lowest first
    fresh = doc.add_hoop(list(mirrored.bar_ids), "Ø10", 100.0)
    assert fresh.bar_ids == mirrored.bar_ids
    assert _xy(doc, bars["60,60"]) == (1940.0, 60.0)
    ring = doc.concrete_faces()[0].point_ids
    points = [cast(apeCAD.Point, doc.entity(pid)).xyz_mm for pid in ring]
    assert signed_area([(p.x_mm, p.y_mm) for p in points]) > 0.0
    assert Document.from_json(doc.to_json()).to_json() == doc.to_json()


def test_array_linear_of_a_hoop_clones_it_with_its_bars() -> None:
    doc, bars = _section()
    hoop = doc.add_hoop(list(bars.values()), "Ø10", 100.0)
    doc.array_linear([hoop.entity_id], 1000.0, 0.0, copies=2)
    hoops = doc.hoops()
    # The ring holds the 4 corner bars (the mid-side bars are collinear), so each copy adds 4.
    assert len(hoops) == 3 and len(doc.bars()) == 6 + 2 * 4
    for index, copy in enumerate(hoops[1:], start=1):
        assert copy.designation == hoop.designation and copy.spacing_mm == hoop.spacing_mm
        assert set(copy.bar_ids).isdisjoint(hoop.bar_ids)
        shifted = [_xy(doc, b) for b in copy.bar_ids]
        original = [_xy(doc, b) for b in hoop.bar_ids]
        assert shifted == [(x + 1000.0 * index, y) for x, y in original]
    assert Document.from_json(doc.to_json()).hoops() == hoops


def test_to_frame_has_no_bar_nodes() -> None:
    doc, bars = _section()
    doc.add_hoop(list(bars.values()), "Ø10", 100.0)
    a = doc.add_point(0.0, 0.0, 3000.0).entity_id
    b = doc.add_point(0.0, 0.0, 6000.0).entity_id
    doc.add_line(a, b)
    frame = doc.to_frame()
    bar_points = {bar.point_id for bar in doc.bars()}
    node_ids = {node.entity_id for node in frame.nodes}
    assert node_ids.isdisjoint(bar_points)
    assert {a, b} <= node_ids
    assert len(frame.members) == 1


def test_a_v0_document_written_by_main_loads_unchanged() -> None:
    """tests/fixtures/document_v0/main-942c16f.json was written by apeCAD at 942c16f."""
    text = (FIXTURES / "document_v0" / "main-942c16f.json").read_text(encoding="utf-8")
    raw = json.loads(text)
    assert raw["schema"] == "apeCAD.document.v0"
    doc = Document.from_json(text)
    assert [op_to_dict(op) for op in doc.ops()] == raw["ops"]
    assert json.loads(doc.to_json()) == {**raw, "schema": "apeCAD.document.v1"}
    assert doc.solids() and doc.lines()


def test_catalog_examples_apply_to_a_section() -> None:
    doc = Document()
    for x, y in ((60, 60), (340, 60), (340, 540), (60, 540)):
        apply(doc, "AddBar", {"x_mm": x, "y_mm": y, "designation": "Ø16"})
    hoop = apply(doc, "AddHoop", {"bar_ids": [2, 4, 6, 8], "designation": "Ø10", "spacing_mm": 100})
    assert hoop.created_id == 9
    apply(doc, "SetTransverse", {"entity_ids": [9], "spacing_mm": 150})
    assert doc.hoops()[0].spacing_mm == 150.0


def test_scene_payload_ships_the_section_lists() -> None:
    doc, bars = _section()
    hoop = doc.add_hoop(list(bars.values()), "Ø10", 100.0)
    tie = doc.add_crosstie(bars["60,300"], bars["340,300"], "Ø10", 100.0)
    scene = scene_payload(doc)
    assert [item["entity_id"] for item in cast(list[dict[str, object]], scene["bars"])] == list(
        bars.values()
    )
    assert cast(list[dict[str, object]], scene["hoops"])[0]["bar_ids"] == list(hoop.bar_ids)
    assert cast(list[dict[str, object]], scene["crossties"])[0]["entity_id"] == tie.entity_id
    face = cast(list[dict[str, object]], scene["concrete_faces"])[0]
    assert face["role"] == "solid" and face["material"] == "H30"
    point_ids = {cast(int, p["entity_id"]) for p in cast(list[dict[str, object]], scene["points"])}
    assert {bar.point_id for bar in doc.bars()} <= point_ids  # the client draws them as dots


@pytest.fixture
def server() -> Iterator[ScratchpadServer]:
    bound = ScratchpadServer(("127.0.0.1", 0), Document())
    thread = Thread(target=bound.serve_forever, daemon=True)
    thread.start()
    yield bound
    bound.shutdown()
    bound.server_close()


def _post(server: ScratchpadServer, body: dict[str, object]) -> tuple[int, dict[str, object]]:
    port = server.server_address[1]
    request = Request(
        f"http://127.0.0.1:{port}/api/op",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def test_add_bar_then_add_hoop_over_http(server: ScratchpadServer) -> None:
    ids: list[int] = []
    for x, y in ((60, 60), (340, 60), (340, 540), (60, 540)):
        status, body = _post(server, {"op": "AddBar", "x_mm": x, "y_mm": y, "designation": "Ø16"})
        assert status == 200
        ids.append(cast(int, body["created_id"]))
    status, body = _post(server, {"op": "AddHoop", "bar_ids": ids[:2], "designation": "Ø10",
                                  "spacing_mm": 100})
    assert status == 400 and body["code"] == "REFUSED"  # a 2-bar hoop
    status, body = _post(server, {"op": "AddHoop", "bar_ids": ids[::-1], "designation": "Ø10",
                                  "spacing_mm": 100})
    assert status == 200
    hoops = cast(list[dict[str, object]], body["hoops"])
    assert hoops[0]["bar_ids"] == ids
    assert len(cast(list[object], body["bars"])) == 4


def test_section_ops_need_a_valid_designation_over_http(server: ScratchpadServer) -> None:
    status, body = _post(server, {"op": "AddBar", "x_mm": 0, "y_mm": 0, "designation": "#5"})
    assert status == 400 and "designation" in cast(str, body["error"])


def test_set_ops_are_section_only() -> None:
    assert SetBarSize(entity_ids=(1,), designation="Ø8").designation == "Ø8"
    with pytest.raises(DocumentError, match="needs a designation"):
        SetTransverse(entity_ids=(1,))
    with pytest.raises(DocumentError, match="at least one"):
        SetMaterial(entity_ids=(), material="H30")
    assert AddConcreteFace(point_ids=(1, 2, 3), material=" H30 ").material == "H30"
