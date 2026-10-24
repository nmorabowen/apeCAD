from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path
from threading import Thread
from typing import cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from apeCAD.document import Document
from apeCAD.scratchpad import server as server_module
from apeCAD.scratchpad.server import STATIC_DIR, ScratchpadServer, main, serve


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


def _main_identity(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Run the CLI entry on `argv`; return `/api/identity` of the bound server."""
    seen: list[dict[str, object]] = []

    def serve_once(self: ScratchpadServer, poll_interval: float = 0.5) -> None:
        seen.append(self.identity_payload())

    monkeypatch.setattr(ScratchpadServer, "serve_forever", serve_once)
    main(argv)
    assert len(seen) == 1
    return seen[0]


def test_main_accepts_workbench_argv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Hand copy of apeWorkbench src/apeWorkbench/services/tools.py @ 4a7a068:
    # `ToolAdapter.argv` (line 210) + `CadAdapter.extra_argv` (line 261) build
    # this argv for port=0, open_browser=False; `CadAdapter.env` (line 259) and
    # `launch_tool` (line 600) set the two env vars. Re-check it if they change.
    # Workbench gives env and flag the same folder; here they differ, so the
    # assertion also shows that the flag wins.
    work = tmp_path / "work"
    habitat = tmp_path / "habitat"
    monkeypatch.setenv("APE_HABITAT_ROOT", str(habitat))
    monkeypatch.setenv("APECAD_SESSION_SKETCHES", str(habitat / "tools" / "apeCAD" / "files"))
    argv = ["--host", "127.0.0.1", "--port", "0", "--no-browser", "--root", str(work)]
    identity = _main_identity(argv, monkeypatch)
    assert identity["root"] == str(work.resolve())


def test_main_resolves_root_without_port(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # No --port takes the preferred-port branch; DEFAULT_PORT=0 keeps the bind ephemeral.
    monkeypatch.setattr(server_module, "DEFAULT_PORT", 0)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("APE_HABITAT_ROOT", str(tmp_path / "habitat"))
    identity = _main_identity(["--no-browser", "--root", "~/sub/../work"], monkeypatch)
    assert identity["root"] == str((tmp_path / "work").resolve())


def test_static_index_is_served(server: ScratchpadServer) -> None:
    port = server.server_address[1]
    with urlopen(f"http://127.0.0.1:{port}/") as response:
        html = response.read().decode("utf-8")
    assert "apeCAD scratchpad" in html
    assert 'id="sel-filters"' in html
    assert 'data-filter="point"' in html
    assert 'data-filter="element"' in html
    assert 'id="menubar"' in html
    assert 'id="brand"' in html
    assert 'rel="icon"' in html
    assert (STATIC_DIR / "favicon-32.png").is_file()
    assert (STATIC_DIR / "favicon.ico").is_file()
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
    app = _client_source()
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
    assert "disposeObject3D" in app
    assert "disposeObject3D(selectionHalos)" in app
    assert "wrapAutoDispose(selectionHalos)" in app
    assert "updateCameraMatrices" in app
    assert "raycaster.params.Line2 = { threshold: 12 }" in app
    assert "!input.isConnected" in app


def _client_source() -> str:
    """app.js plus its ES modules, so moving code between them keeps these asserts."""
    files = [STATIC_DIR / "app.js", *sorted((STATIC_DIR / "js").glob("*.js"))]
    return "\n".join(path.read_text(encoding="utf-8") for path in files)


def _reachable_modules() -> set[str]:
    """Names of js/*.js files that app.js imports, directly or through other modules."""
    seen: set[str] = set()
    queue = [STATIC_DIR / "app.js"]
    while queue:
        source = queue.pop().read_text(encoding="utf-8")
        for name in re.findall(r'from "\./(?:js/)?([a-z0-9_-]+\.js)"', source):
            if name not in seen and (STATIC_DIR / "js" / name).is_file():
                seen.add(name)
                queue.append(STATIC_DIR / "js" / name)
    return seen


def test_client_modules_are_served(server: ScratchpadServer) -> None:
    port = server.server_address[1]
    reachable = _reachable_modules()
    for module in sorted((STATIC_DIR / "js").glob("*.js")):
        assert module.name in reachable, f"{module.name} is not imported from app.js"
        with urlopen(f"http://127.0.0.1:{port}/js/{module.name}") as response:
            assert response.headers["Content-Type"].startswith("text/javascript")
            assert response.read() == module.read_bytes()


@pytest.mark.parametrize("path", ["/js/missing.js", "/js/../server.py", "/js/sub/geom.js"])
def test_client_module_paths_are_confined(server: ScratchpadServer, path: str) -> None:
    port = server.server_address[1]
    with pytest.raises(HTTPError) as caught:
        urlopen(f"http://127.0.0.1:{port}{path}")
    assert caught.value.code == 404


def test_vendor_three_is_served_and_confined(server: ScratchpadServer) -> None:
    port = server.server_address[1]
    with urlopen(f"http://127.0.0.1:{port}/") as response:
        html = response.read().decode("utf-8")
    assert "https://" not in html
    assert "/vendor/three/build/three.module.min.js" in html
    for rel in (
        "build/three.module.min.js",
        "build/three.core.min.js",
        "examples/jsm/lines/LineSegments2.js",
        "examples/jsm/lines/LineSegmentsGeometry.js",
        "examples/jsm/lines/LineMaterial.js",
    ):
        with urlopen(f"http://127.0.0.1:{port}/vendor/three/{rel}") as response:
            assert response.status == 200
            assert response.headers["Content-Type"].startswith("text/javascript")
            assert "immutable" in response.headers.get("Cache-Control", "")
            assert len(response.read()) > 100
    for bad in (
        "/vendor/three/../server.py",
        "/vendor/three/missing.js",
        "/vendor/three/LICENSE",
        "/vendor/three/examples/jsm/controls/OrbitControls.js",
    ):
        with pytest.raises(HTTPError) as caught:
            urlopen(f"http://127.0.0.1:{port}{bad}")
        assert caught.value.code == 404


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


def test_drawn_box_is_one_op_and_one_undo(server: ScratchpadServer) -> None:
    """The box tool posts one Extrude with a ring; one undo removes it whole (ADR 0030)."""
    before = _call(server, "/api/op", "POST", {"op": "AddPoint", "x_mm": 0, "y_mm": 0, "z_mm": 0})
    drawn = _call(
        server,
        "/api/op",
        "POST",
        {
            "op": "Extrude",
            "ring": [1, {"xyz": [1000, 0, 0]}, {"xyz": [1000, 800, 0]}, {"xyz": [0.4, 800, 0]}],
            "distance_mm": 500,
            "label": "box",
        },
    )
    solids = drawn["solids"]
    assert isinstance(solids, list) and len(solids) == 1
    assert len(cast(list[object], drawn["points"])) == 8
    undone = _call(server, "/api/undo", "POST", {})
    for key in ("points", "lines", "faces", "solids"):
        assert undone[key] == before[key], key


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


def _post_error(server: ScratchpadServer, path: str, body: object) -> tuple[int, dict[str, object]]:
    port = server.server_address[1]
    request = Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(HTTPError) as error:
        urlopen(request)
    loaded: object = json.loads(error.value.read().decode("utf-8"))
    assert isinstance(loaded, dict)
    return error.value.code, cast(dict[str, object], loaded)


def test_op_api_codes_unknown_ops_and_refusals(server: ScratchpadServer) -> None:
    """Spec agent-surface-mcp S1: both stay 400 (ADR 0026), and the body gains a code."""
    status, body = _post_error(server, "/api/op", {"op": "AddTeapot", "x_mm": 0})
    assert status == 400 and body["code"] == "UNKNOWN_OP"
    status, body = _post_error(server, "/api/op", {"op": "AddLine", "start_id": 1, "end_id": 2})
    assert status == 400 and body["code"] == "REFUSED"
    assert body["error"]  # the DocumentError text
    status, body = _post_error(server, "/api/op", {"op": "AddPoint", "x_mm": 0, "y_mm": 0})
    assert status == 400 and body["code"] == "INVALID_ARGUMENT"
    status, body = _post_error(
        server, "/api/op", {"op": "AddPoint", "x_mm": 0, "y_mm": 0, "z_mm": 0, "entity_id": 9}
    )
    assert status == 400 and body["code"] == "INVALID_ARGUMENT"
    assert _call(server, "/api/scene")["points"] == []


def test_op_api_accepts_op_and_params(server: ScratchpadServer) -> None:
    payload = _call(
        server,
        "/api/op",
        "POST",
        {"op": "AddPoint", "params": {"x_mm": 5, "y_mm": 0, "z_mm": 0, "label": "P"}},
    )
    assert payload["created_id"] == 1
    points = payload["points"]
    assert isinstance(points, list) and points[0]["label"] == "P"


def test_ops_route_lists_the_catalog(server: ScratchpadServer) -> None:
    from apeCAD.catalog import CATALOG

    listed = _call(server, "/api/ops")
    assert listed["ok"] is True
    assert listed["schema"] == "apeCAD.document.v1"
    ops = listed["ops"]
    assert isinstance(ops, list)
    assert [cast(dict[str, object], item)["name"] for item in ops] == list(CATALOG)
    one = _call(server, "/api/ops?name=Extrude")["ops"]
    assert isinstance(one, list) and len(one) == 1
    status, _type, raw = _get_raw(server, "/api/ops?name=AddTeapot")
    assert status == 400 and json.loads(raw)["code"] == "UNKNOWN_OP"


def test_undo_with_nothing_to_undo_is_refused(server: ScratchpadServer) -> None:
    status, body = _post_error(server, "/api/undo", {})
    assert status == 400 and body["code"] == "REFUSED"


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


def _get_raw(server: ScratchpadServer, path: str) -> tuple[int, str, bytes]:
    port = server.server_address[1]
    try:
        with urlopen(f"http://127.0.0.1:{port}{path}") as response:
            return response.status, response.headers["Content-Type"], response.read()
    except HTTPError as exc:
        return exc.code, exc.headers["Content-Type"], exc.read()


def test_render_svg_route_serves_the_current_draft(server: ScratchpadServer) -> None:
    server.document.add_box((0.0, 0.0, 0.0), (1000.0, 600.0, 400.0), label="<b>block</b>")
    status, content_type, body = _get_raw(server, "/api/render.svg?view=top&width=400&height=300")
    assert status == 200
    assert content_type.startswith("image/svg+xml")
    svg = body.decode("utf-8")
    assert svg.startswith("<svg ") and 'data-view="top"' in svg
    assert 'width="400" height="300"' in svg
    assert "&lt;b&gt;block&lt;/b&gt;" in svg and "<b>" not in svg
    _status, _type, default = _get_raw(server, "/api/render.svg")
    assert 'data-view="iso"' in default.decode("utf-8")


def test_render_svg_route_refuses_bad_parameters(server: ScratchpadServer) -> None:
    for query in ("view=bottom", "format=png", "save_to=x.svg", "ids=42"):
        status, content_type, body = _get_raw(server, f"/api/render.svg?{query}")
        assert status == 400, query
        assert content_type.startswith("application/json")
        payload = json.loads(body.decode("utf-8"))
        assert payload["code"] == "INVALID_ARGUMENT", query


def _find_headless_browser() -> str | None:
    for candidate in (
        shutil.which("msedge"),
        shutil.which("chromium"),
        shutil.which("google-chrome"),
        shutil.which("chrome"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    ):
        if candidate and Path(candidate).is_file():
            return str(candidate)
    return None


@pytest.mark.skipif(
    os.environ.get("APECAD_HEADLESS_BROWSER") != "1",
    reason="Opt-in local browser check (ADR 0022, ADR 0038); set APECAD_HEADLESS_BROWSER=1",
)
def test_headless_still_capture_returns_valid_png(
    server: ScratchpadServer, tmp_path: Path
) -> None:
    browser = _find_headless_browser()
    if browser is None:
        pytest.skip("No local Chromium/Edge binary found for APECAD_HEADLESS_BROWSER=1")
    server.document.add_box((0.0, 0.0, 0.0), (1000.0, 800.0, 500.0), label="blk")
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/?capture=1"
    dom_out = tmp_path / "dom.html"
    err_out = tmp_path / "stderr.log"
    with dom_out.open("wb") as out_f, err_out.open("wb") as err_f:
        proc = subprocess.Popen(
            [
                browser,
                "--headless=new",
                "--disable-gpu",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-extensions",
                f"--user-data-dir={tmp_path / 'profile'}",
                "--virtual-time-budget=2000",
                "--dump-dom",
                url,
            ],
            stdout=out_f,
            stderr=err_f,
        )
        try:
            proc.wait(timeout=20)
        finally:
            if proc.poll() is None:
                proc.kill()
    dom_text = dom_out.read_text(encoding="utf-8", errors="replace")
    match = re.search(r'data-apecad-still="data:image/png;base64,([A-Za-z0-9+/=]+)"', dom_text)
    assert match is not None, (
        f"Still data URL not found in DOM dump: {err_out.read_text(errors='replace')[:400]}"
    )
    raw_png = base64.b64decode(match.group(1))
    assert raw_png.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(raw_png) > 200
    assert "blk" in dom_text



