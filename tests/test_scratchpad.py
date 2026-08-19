from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from apeCAD.document import Document
from apeCAD.scratchpad.server import STATIC_DIR, ScratchpadServer, serve


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


def test_serve_refuses_busy_port(server: ScratchpadServer) -> None:
    host, port = server.server_address[:2]
    with pytest.raises(OSError, match="already in use|no free port"):
        serve(host, port, open_browser=False, port_span=1)


def test_serve_binds_next_free_port(server: ScratchpadServer) -> None:
    host, port = server.server_address[:2]
    second = serve(host, port, open_browser=False, port_span=16)
    thread = Thread(target=second.serve_forever, daemon=True)
    thread.start()
    try:
        assert second.server_address[1] != port
        with urlopen(f"http://127.0.0.1:{second.server_address[1]}/api/identity") as response:
            payload: object = json.loads(response.read().decode("utf-8"))
        assert isinstance(payload, dict)
        assert payload["name"] == "apeCAD"
        assert payload["port"] == second.server_address[1]
    finally:
        second.shutdown()
        second.server_close()


def test_identity_reports_session_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APE_HABITAT_ROOT", str(tmp_path))
    bound = serve("127.0.0.1", 0, open_browser=False)
    thread = Thread(target=bound.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(f"http://127.0.0.1:{bound.server_address[1]}/api/identity") as response:
            payload: object = json.loads(response.read().decode("utf-8"))
        assert isinstance(payload, dict)
        assert payload["root"] == str(tmp_path.resolve())
        assert payload["name"] == "apeCAD"
    finally:
        bound.shutdown()
        bound.server_close()


def test_static_index_is_served(server: ScratchpadServer) -> None:
    port = server.server_address[1]
    with urlopen(f"http://127.0.0.1:{port}/") as response:
        html = response.read().decode("utf-8")
    assert "apeCAD scratchpad" in html
    assert 'id="sel-filters"' in html
    assert 'data-filter="point"' in html
    assert 'data-filter="element"' in html
    assert 'id="menubar"' in html
    assert 'id="rail"' in html
    assert 'id="props"' in html
    assert 'id="props-dock"' not in html
    assert 'id="sides"' not in html
    assert 'id="ctx-menu"' in html
    assert 'data-tool="polyline"' in html
    assert 'id="grid-snap"' in html
    assert 'data-cmd="grid-snap"' in html
    assert 'data-menu="grid"' in html
    assert 'id="grid-minor-on"' in html
    assert 'id="grid-prefs-dialog"' in html
    assert 'id="gpref-hidden-scale"' in html
    assert 'id="gpref-minor"' in html
    assert 'id="gpref-minor-style"' in html
    assert 'id="gpref-dot-size"' in html
    assert 'id="gpref-line-width"' in html
    assert 'id="gpref-auto"' in html
    assert 'id="gpref-unit"' in html
    assert 'data-cmd="grid-prefs"' in html
    assert 'data-cmd="perspective"' in html
    assert 'data-cmd="parallel"' in html
    assert 'data-cmd="view-top"' in html
    assert 'data-cmd="view-front"' in html
    assert (STATIC_DIR / "app.js").is_file()
    app = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert "chain: true" in app
    assert "Esc ends the chain" in app
    assert 'kind: "polyline"' in app
    assert 'setTool("move")' in app
    assert "picked == null && !event.shiftKey" in app
    assert "gridSnapOn" in app
    assert "isGridSnap" in app
    assert "gridMinorMm" in app
    assert "gridMajorMm" in app
    assert "grid-major" in app
    assert "hiddenLineScale" in app
    assert "gridHiddenScale" in app
    assert "gridDotSize" in app
    assert "gridLineWidth" in app
    assert "LineSegments2" in app
    assert "makeMinorDots" in app
    assert "displayUnit" in app
    assert "effectiveGrid" in app
    assert "niceLength" in app
    assert "sceneFrame" in app
    assert "lookAtScene" in app
    assert "goNamedView" in app
    assert "setProjectionMode" in app
    assert "new THREE.Vector3(1, -1, 1)" in app
    assert "makeGridHelper" in app
    assert "updateClipPlanes" in app
    assert "appendHiddenSpan" in app
    assert "pickByFilter" in app
    assert "setSelectFilter" in app
    assert "convertSelectionToFilter" in app
    assert "updatePreselect" in app
    assert 'selectFilter === "element"' in app
    assert "addSolidPrism" in app
    assert "addSolidVolumeFallback" in app
    assert "addVertexDot" in app
    assert "wall_ids" in app
    assert "sceneState.brep" in app


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


def test_set_label_via_op_api(server: ScratchpadServer) -> None:
    _call(
        server,
        "/api/op",
        "POST",
        {"op": "AddPoint", "x_mm": 0, "y_mm": 0, "z_mm": 0, "label": "A"},
    )
    renamed = _call(
        server,
        "/api/op",
        "POST",
        {"op": "SetLabel", "entity_id": 1, "label": "origin"},
    )
    points = renamed["points"]
    assert isinstance(points, list)
    assert points[0]["label"] == "origin"


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


def test_add_box_via_op_api_is_a_solid(server: ScratchpadServer) -> None:
    payload = _call(
        server,
        "/api/op",
        "POST",
        {
            "op": "AddBox",
            "origin_xyz_mm": [0, 0, 0],
            "size_xyz_mm": [6000, 4000, 200],
            "label": "slab_L2",
        },
    )
    assert payload["boxes"] == []
    solids = payload["solids"]
    assert isinstance(solids, list)
    assert len(solids) == 1
    assert solids[0]["label"] == "slab_L2"
    assert solids[0]["distance_mm"] == 200
    faces = payload["faces"]
    assert isinstance(faces, list)
    assert len(faces) == 6
    assert len(solids[0]["wall_ids"]) == 4
    assert payload["created_id"] == solids[0]["entity_id"]
    points = payload["points"]
    assert isinstance(points, list)
    assert len(points) == 8
    lines = payload["lines"]
    assert isinstance(lines, list)
    assert len(lines) == 12


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
    assert len(after_face["lines"]) == 4
    after_solid = _call(
        server,
        "/api/op",
        "POST",
        {"op": "Extrude", "face_id": 5, "distance_mm": 200, "label": "slab_solid"},
    )
    solids = after_solid["solids"]
    assert isinstance(solids, list)
    assert solids[0]["face_id"] == 5
    assert solids[0]["distance_mm"] == 200
    assert after_solid["created_id"] == solids[0]["entity_id"]
    assert solids[0]["cap_id"] is not None
    points = after_solid["points"]
    assert isinstance(points, list)
    assert len(points) == 8
    faces = after_solid["faces"]
    assert isinstance(faces, list)
    assert len(faces) == 6
    assert len(solids[0]["wall_ids"]) == 4
    assert len(after_solid["lines"]) == 12
    brep = after_solid["brep"]
    assert isinstance(brep, dict)
    solid_id = str(solids[0]["entity_id"])
    children = brep["children"]
    assert isinstance(children, dict)
    assert len(children[solid_id]) == 6
    assert len(brep["solid"]) == len(after_solid["points"]) + len(after_solid["lines"]) + 6


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


def test_load_json_replaces_the_document(server: ScratchpadServer) -> None:
    _call(
        server,
        "/api/op",
        "POST",
        {"op": "AddPoint", "x_mm": 0, "y_mm": 0, "z_mm": 0, "label": "A"},
    )
    scene = _call(server, "/api/scene")
    document = scene["document"]
    assert isinstance(document, dict)
    _call(server, "/api/reset", "POST", {})
    assert _call(server, "/api/scene")["points"] == []
    loaded = _call(server, "/api/load", "POST", document)
    points = loaded["points"]
    assert isinstance(points, list)
    assert points[0]["label"] == "A"


def test_load_accepts_a_scene_payload_wrapper(server: ScratchpadServer) -> None:
    _call(
        server,
        "/api/op",
        "POST",
        {"op": "AddPoint", "x_mm": 100, "y_mm": 0, "z_mm": 0, "label": "B"},
    )
    scene = _call(server, "/api/scene")
    _call(server, "/api/reset", "POST", {})
    loaded = _call(server, "/api/load", "POST", scene)
    points = loaded["points"]
    assert isinstance(points, list)
    assert points[0]["label"] == "B"


def test_load_bad_json_is_400(server: ScratchpadServer) -> None:
    port = server.server_address[1]
    request = Request(
        f"http://127.0.0.1:{port}/api/load",
        data=json.dumps({"ops": []}).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(HTTPError) as error:
        urlopen(request)
    assert error.value.code == 400
