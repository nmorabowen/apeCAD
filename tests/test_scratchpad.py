from __future__ import annotations

import json
from collections.abc import Iterator
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from apeCAD.document import Document
from apeCAD.scratchpad.server import STATIC_DIR, ScratchpadServer


@pytest.fixture
def server() -> Iterator[ScratchpadServer]:
    bound = ScratchpadServer(("127.0.0.1", 0), Document())
    thread = Thread(target=bound.serve_forever, daemon=True)
    thread.start()
    yield bound
    bound.shutdown()
    bound.server_close()


def _call(
    server: ScratchpadServer,
    path: str,
    method: str = "GET",
    body: dict[str, object] | None = None,
) -> dict[str, object]:
    port = server.server_address[1]
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request) as response:
        loaded: object = json.loads(response.read().decode("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_static_index_is_served(server: ScratchpadServer) -> None:
    port = server.server_address[1]
    with urlopen(f"http://127.0.0.1:{port}/") as response:
        html = response.read().decode("utf-8")
    assert "apeCAD scratchpad" in html
    assert 'id="viewcube"' in html
    assert (STATIC_DIR / "app.js").is_file()


def test_add_point_via_op_api(server: ScratchpadServer) -> None:
    payload = _call(
        server,
        "/api/op",
        "POST",
        {"op": "AddPoint", "x_mm": 0, "y_mm": 0, "z_mm": 0, "label": "A"},
    )
    points = payload["points"]
    assert isinstance(points, list)
    assert points[0]["label"] == "A"


def test_line_and_undo(server: ScratchpadServer) -> None:
    _call(server, "/api/op", "POST", {"op": "AddPoint", "x_mm": 0, "y_mm": 0, "z_mm": 0})
    _call(server, "/api/op", "POST", {"op": "AddPoint", "x_mm": 1000, "y_mm": 0, "z_mm": 0})
    after_line = _call(
        server,
        "/api/op",
        "POST",
        {"op": "AddLine", "start_id": 1, "end_id": 2, "label": "beam"},
    )
    lines = after_line["lines"]
    assert isinstance(lines, list)
    assert len(lines) == 1
    undone = _call(server, "/api/undo", "POST", {})
    assert undone["lines"] == []


def test_face_and_extrude_via_op_api(server: ScratchpadServer) -> None:
    for x_mm, y_mm in ((0, 0), (4000, 0), (4000, 3000), (0, 3000)):
        _call(
            server,
            "/api/op",
            "POST",
            {"op": "AddPoint", "x_mm": x_mm, "y_mm": y_mm, "z_mm": 0},
        )
    after_face = _call(
        server,
        "/api/op",
        "POST",
        {"op": "AddFace", "point_ids": [1, 2, 3, 4], "label": "slab"},
    )
    assert after_face["created_id"] == 5
    faces = after_face["faces"]
    assert isinstance(faces, list)
    assert faces[0]["entity_id"] == 5
    after_solid = _call(
        server,
        "/api/op",
        "POST",
        {"op": "Extrude", "face_id": 5, "distance_mm": 200, "label": "slab_solid"},
    )
    assert after_solid["created_id"] == 6
    solids = after_solid["solids"]
    assert isinstance(solids, list)
    assert solids[0]["face_id"] == 5
    assert solids[0]["distance_mm"] == 200


def test_translate_and_insert_node_via_op_api(server: ScratchpadServer) -> None:
    _call(server, "/api/op", "POST", {"op": "AddPoint", "x_mm": 0, "y_mm": 0, "z_mm": 0})
    _call(server, "/api/op", "POST", {"op": "AddPoint", "x_mm": 4000, "y_mm": 0, "z_mm": 0})
    _call(server, "/api/op", "POST", {"op": "AddLine", "start_id": 1, "end_id": 2})
    moved = _call(
        server,
        "/api/op",
        "POST",
        {"op": "Translate", "entity_ids": [3], "dx_mm": 100, "dy_mm": 0, "dz_mm": 0},
    )
    assert moved["created_id"] is None
    points = moved["points"]
    assert isinstance(points, list)
    assert points[0]["x_mm"] == 100
    assert points[1]["x_mm"] == 4100
    after_node = _call(
        server,
        "/api/op",
        "POST",
        {"op": "InsertNode", "target_id": 3, "x_mm": 2100, "y_mm": 0, "z_mm": 0},
    )
    assert after_node["created_id"] is not None
    lines = after_node["lines"]
    assert isinstance(lines, list)
    assert len(lines) == 2
    rotated = _call(
        server,
        "/api/op",
        "POST",
        {
            "op": "Rotate",
            "entity_ids": [1],
            "origin_x_mm": 0,
            "origin_y_mm": 0,
            "angle_deg": 90,
        },
    )
    points = rotated["points"]
    assert isinstance(points, list)


def test_delete_via_op_api(server: ScratchpadServer) -> None:
    _call(server, "/api/op", "POST", {"op": "AddPoint", "x_mm": 0, "y_mm": 0, "z_mm": 0})
    _call(server, "/api/op", "POST", {"op": "AddPoint", "x_mm": 1000, "y_mm": 0, "z_mm": 0})
    _call(server, "/api/op", "POST", {"op": "AddLine", "start_id": 1, "end_id": 2})
    gone = _call(server, "/api/op", "POST", {"op": "Delete", "entity_ids": [3]})
    assert gone["created_id"] is None
    assert gone["lines"] == []
    assert gone["points"] == []


def test_break_crossing_via_op_api(server: ScratchpadServer) -> None:
    _call(server, "/api/op", "POST", {"op": "AddPoint", "x_mm": 0, "y_mm": 0, "z_mm": 0})
    _call(server, "/api/op", "POST", {"op": "AddPoint", "x_mm": 10000, "y_mm": 0, "z_mm": 0})
    _call(server, "/api/op", "POST", {"op": "AddPoint", "x_mm": 5000, "y_mm": -4000, "z_mm": 0})
    _call(server, "/api/op", "POST", {"op": "AddPoint", "x_mm": 5000, "y_mm": 4000, "z_mm": 0})
    _call(server, "/api/op", "POST", {"op": "AddLine", "start_id": 1, "end_id": 2})
    _call(server, "/api/op", "POST", {"op": "AddLine", "start_id": 3, "end_id": 4})
    broken = _call(
        server,
        "/api/op",
        "POST",
        {"op": "BreakCrossing", "line_a_id": 5, "line_b_id": 6},
    )
    lines = broken["lines"]
    assert isinstance(lines, list)
    assert len(lines) == 4
    assert broken["created_id"] is not None


def test_join_polyline_via_op_api(server: ScratchpadServer) -> None:
    _call(server, "/api/op", "POST", {"op": "AddPoint", "x_mm": 0, "y_mm": 0, "z_mm": 0})
    _call(server, "/api/op", "POST", {"op": "AddPoint", "x_mm": 1000, "y_mm": 0, "z_mm": 0})
    _call(server, "/api/op", "POST", {"op": "AddPoint", "x_mm": 1000, "y_mm": 800, "z_mm": 0})
    _call(server, "/api/op", "POST", {"op": "AddLine", "start_id": 1, "end_id": 2})
    _call(server, "/api/op", "POST", {"op": "AddLine", "start_id": 2, "end_id": 3})
    joined = _call(
        server,
        "/api/op",
        "POST",
        {"op": "JoinPolyline", "entity_ids": [4, 5]},
    )
    assert joined["created_id"] is not None
    assert joined["lines"] == []
    polylines = joined["polylines"]
    assert isinstance(polylines, list)
    assert len(polylines) == 1
    assert polylines[0]["closed"] is False


def test_bad_op_is_400(server: ScratchpadServer) -> None:
    port = server.server_address[1]
    request = Request(
        f"http://127.0.0.1:{port}/api/op",
        data=json.dumps({"op": "AddLine", "start_id": 1, "end_id": 2}).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(HTTPError) as error:
        urlopen(request)
    assert error.value.code == 400
