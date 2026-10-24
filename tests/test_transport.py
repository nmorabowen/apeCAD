"""Stage C5: the stateless section transport (ADR 0026) and the redo round-trip it needs."""

from __future__ import annotations

import ast
import copy
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from threading import Thread
from typing import cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from _section_fixtures import l_wall_two_hoops
from apeCAD import catalog
from apeCAD.document import Document
from apeCAD.ops import op_to_dict
from apeCAD.scratchpad import transport
from apeCAD.scratchpad.payload import scene_payload
from apeCAD.scratchpad.server import ScratchpadServer
from apeCAD.scratchpad.transport import MAX_OPS, TRANSPORT_VERSION, handle
from apeCAD.section_draft import section_draft

Json = dict[str, object]

COLUMN: list[Json] = [
    {
        "op": "AddSectionOutline",
        "point_ids": [
            {"xyz": [0, 0, 0]},
            {"xyz": [400, 0, 0]},
            {"xyz": [400, 600, 0]},
            {"xyz": [0, 600, 0]},
        ],
        "material": "H30",
        "label": "C1",
    },
    {"op": "SetCover", "face_id": 5, "cover_mm": 40, "tie_diameter_mm": 10, "bar_diameter_mm": 16},
    {"op": "AddBar", "x_mm": 58, "y_mm": 58, "designation": "Ø16"},
    {"op": "AddBar", "x_mm": 342, "y_mm": 58, "designation": "Ø16"},
    {"op": "AddBar", "x_mm": 342, "y_mm": 542, "designation": "Ø16"},
    {"op": "AddBar", "x_mm": 58, "y_mm": 542, "designation": "Ø16"},
]


def _request(action: str, state: Json | None = None, **extra: object) -> Json:
    request: Json = {"transport_version": TRANSPORT_VERSION, "action": action}
    if state is not None:
        request["document"] = state["document"]
        request["redo"] = state["redo"]
    request.update(extra)
    return request


def _ok(response: Json) -> Json:
    assert response["ok"] is True and response["status"] == 200, response
    return response


def _refused(response: Json, code: str) -> str:
    assert response["ok"] is False and response["status"] == 422, response
    assert response["transport_version"] == TRANSPORT_VERSION
    error = cast(Json, response["error"])
    assert error["code"] == code, error
    return cast(str, error["message"])


def _apply(state: Json | None, op: Json) -> Json:
    return _ok(handle(_request("apply", state, op=op)))


def _column_state() -> Json:
    state: Json | None = None
    for op in COLUMN:
        state = _apply(state, op)
    assert state is not None
    return state


# --- Document.redo_ops / from_dict(redo=...) -------------------------------------------


def test_redo_stack_round_trips_through_json() -> None:
    original = Document()
    for op in COLUMN:
        name, params = catalog.split_request(op)
        catalog.apply(original, name, params)
    expected = original.to_dict()

    undone = Document.from_dict(expected)
    undone.undo()
    undone.undo()
    assert undone.redo_ops() == original.ops()[-2:]
    text = json.dumps(
        {"document": undone.to_dict(), "redo": [op_to_dict(op) for op in undone.redo_ops()]}
    )
    stored = json.loads(text)
    restored = Document.from_dict(stored["document"], redo=stored["redo"])
    assert restored.redo_ops() == undone.redo_ops()
    restored.redo()
    restored.redo()
    assert restored.to_dict() == expected
    assert scene_payload(restored) == scene_payload(original)
    assert restored.redo_ops() == ()


def test_redo_ops_lists_the_next_redo_first() -> None:
    document = Document()
    for op in COLUMN[:3]:
        name, params = catalog.split_request(op)
        catalog.apply(document, name, params)
    last, middle = document.ops()[2], document.ops()[1]
    document.undo()
    document.undo()
    assert document.redo_ops() == (middle, last)


# --- handle(): equivalence with a stateful Document ------------------------------------


def test_transport_sequence_equals_a_stateful_document() -> None:
    stateful = Document()
    state: Json | None = None
    created: list[object] = []
    for op in COLUMN:
        name, params = catalog.split_request(op)
        expected_id = catalog.apply(stateful, name, params).created_id
        state = _apply(state, op)
        assert state["created_id"] == expected_id
        created.append(expected_id)
    hoop: Json = {"op": "AddHoop", "bar_ids": created[2:], "designation": "Ø10", "spacing_mm": 100}
    name, params = catalog.split_request(hoop)
    catalog.apply(stateful, name, params)
    state = _apply(state, hoop)
    for action, step in (("undo", stateful.undo), ("undo", stateful.undo), ("redo", stateful.redo)):
        step()
        state = _ok(handle(_request(action, state)))
    assert state["document"] == stateful.to_dict()
    assert state["redo"] == [op_to_dict(op) for op in stateful.redo_ops()]
    assert state["scene"] == scene_payload(stateful)
    assert state["transport_version"] == TRANSPORT_VERSION


def test_handle_does_not_mutate_its_request() -> None:
    state = _column_state()
    request = _request("undo", state)
    before = copy.deepcopy(request)
    _ok(handle(request))
    assert request == before


def test_scene_of_nothing_is_an_empty_document() -> None:
    response = _ok(handle(_request("scene")))
    assert response["document"] == Document().to_dict()
    assert response["redo"] == []


def test_a_new_apply_clears_the_redo_stack() -> None:
    state = _ok(handle(_request("undo", _column_state())))
    assert len(cast(list[object], state["redo"])) == 1
    state = _apply(state, {"op": "AddBar", "x_mm": 200, "y_mm": 58, "designation": "Ø16"})
    assert state["redo"] == []


# --- refusals --------------------------------------------------------------------------


def test_refused_op_is_422_and_changes_nothing() -> None:
    state = _column_state()
    hoop = {"op": "AddHoop", "bar_ids": [999, 998], "designation": "Ø10", "spacing_mm": 100}
    _refused(handle(_request("apply", state, op=hoop)), "REFUSED")
    _refused(handle(_request("apply", state, op={"op": "AddBar", "x_mm": 1})), "INVALID_ARGUMENT")
    _refused(handle(_request("apply", state, op={"op": "Explode"})), "UNKNOWN_OP")
    _refused(handle(_request("apply", state)), "INVALID_ARGUMENT")


def test_nothing_to_undo_or_redo_is_422() -> None:
    assert "nothing to undo" in _refused(handle(_request("undo")), "REFUSED")
    assert "nothing to redo" in _refused(handle(_request("redo", _column_state())), "REFUSED")


@pytest.mark.parametrize("version", [None, 0, 2, "1", 1.0, True])
def test_unknown_transport_version_is_refused(version: object) -> None:
    request = _request("scene")
    request["transport_version"] = version
    assert "transport_version" in _refused(handle(request), "INVALID_ARGUMENT")


@pytest.mark.parametrize(
    "request_",
    [
        None,
        [],
        "scene",
        {"transport_version": 1, "action": "explode"},
        {"transport_version": 1, "action": "scene", "extra": 1},
        {"transport_version": 1, "action": "scene", "document": []},
        {"transport_version": 1, "action": "scene", "redo": {}},
        {"transport_version": 1, "action": "scene", "redo": [{"op": "AddBar"}]},
        {"transport_version": 1, "action": "scene", "document": {"schema": "x"}},
        {"transport_version": 1, "action": "load"},
    ],
)
def test_malformed_requests_are_422(request_: object) -> None:
    response = handle(request_)
    assert response["ok"] is False and response["status"] == 422, response


def test_seed_action_and_load_with_seed_schema() -> None:
    from apeCAD.section_draft import section_seed

    built = l_wall_two_hoops()
    seed = section_seed(built)
    res_seed = _ok(handle(_request("seed", payload=seed)))
    assert res_seed["redo"] == []
    res_load = _ok(handle(_request("load", payload=seed)))
    assert res_load["document"] == res_seed["document"]
    assert res_load["scene"] == res_seed["scene"]
    assert "seed schema" in _refused(handle(_request("seed", payload={})), "REFUSED")


def test_max_ops_refuses_and_never_truncates() -> None:
    bars = [
        {"op": "AddBar", "x_mm": float(i), "y_mm": 0.0, "designation": "Ø16"}
        for i in range(MAX_OPS + 1)
    ]
    document = Document()
    for op in bars[:MAX_OPS]:
        name, params = catalog.split_request(op)
        catalog.apply(document, name, params)
    full: Json = {"document": document.to_dict(), "redo": []}
    _refused(handle(_request("apply", full, op=bars[-1])), "TOO_LARGE")
    _ok(handle(_request("scene", full)))
    over = document.to_dict()
    cast(list[object], over["ops"]).append(cast(list[object], over["ops"])[0])
    _refused(handle(_request("scene", {"document": over, "redo": []})), "TOO_LARGE")
    split: Json = {"document": document.to_dict(), "redo": [op_to_dict(document.ops()[0])]}
    _refused(handle(_request("scene", split)), "TOO_LARGE")
    _refused(handle(_request("load", payload=over)), "TOO_LARGE")
    draft = section_draft(Document(), commit=None)
    draft["document"] = over
    _refused(handle(_request("load", payload=draft)), "TOO_LARGE")


# --- load and draft --------------------------------------------------------------------


def test_load_accepts_an_ops_log_and_drops_the_old_state() -> None:
    built = l_wall_two_hoops()
    stale = _ok(handle(_request("undo", _column_state())))
    response = _ok(handle(_request("load", stale, payload=built.to_dict())))
    assert response["document"] == built.to_dict()
    assert response["redo"] == []
    assert response["scene"] == scene_payload(built)


def test_load_accepts_a_section_draft() -> None:
    built = l_wall_two_hoops()
    response = _ok(handle(_request("load", payload=section_draft(built, commit=None))))
    assert response["document"] == built.to_dict()
    assert response["warnings"] == []


def test_load_refuses_a_draft_whose_section_disagrees_in_structure() -> None:
    draft = section_draft(l_wall_two_hoops(), commit=None)
    section = cast(Json, draft["section"])
    section["bars"] = cast(list[object], section["bars"])[1:]
    _refused(handle(_request("load", payload=draft)), "REFUSED")


def test_draft_action_returns_the_c4_draft() -> None:
    state = _column_state()
    response = _ok(handle(_request("draft", state)))
    draft = cast(Json, response["draft"])
    document = Document.from_dict(cast(Json, state["document"]))
    expected = section_draft(document, commit=None)
    cast(Json, draft["producer"])["apeCAD_commit"] = None
    assert draft == expected
    assert response["document"] == state["document"]


def test_a_500_op_replay_answers() -> None:
    document = Document()
    for i in range(500):
        name, params = catalog.split_request(
            {"op": "AddBar", "x_mm": float(i), "y_mm": 0.0, "designation": "Ø16"}
        )
        catalog.apply(document, name, params)
    state: Json = {"document": document.to_dict(), "redo": []}
    response = _ok(handle(_request("undo", state)))
    assert len(cast(list[object], response["redo"])) == 1


# --- the import boundary ---------------------------------------------------------------


def test_handle_imports_nothing_from_the_server() -> None:
    tree = ast.parse(Path(transport.__file__).read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    assert not any(name.startswith("apeCAD.scratchpad.server") for name in names)
    assert not any(name.startswith("apeCAD.agent") for name in names)
    code = (
        "import sys\n"
        "from apeCAD.scratchpad.transport import handle\n"
        "loaded = [m for m in sys.modules if m.startswith(('apeCAD.scratchpad.server',"
        " 'apeCAD.agent', 'http.server'))]\n"
        "assert not loaded, loaded\n"
    )
    src = str(Path(transport.__file__).resolve().parents[2])
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": src},
        check=False,
    )
    assert result.returncode == 0, result.stderr


# --- POST /api/section/transport -------------------------------------------------------


@pytest.fixture
def server() -> Iterator[ScratchpadServer]:
    bound = ScratchpadServer(("127.0.0.1", 0), Document())
    thread = Thread(target=bound.serve_forever, daemon=True)
    thread.start()
    yield bound
    bound.shutdown()
    bound.server_close()


def _post(server: ScratchpadServer, body: bytes) -> tuple[int, Json]:
    port = server.server_address[1]
    request = Request(
        f"http://127.0.0.1:{port}/api/section/transport",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request) as response:
            status, raw = response.status, response.read()
    except HTTPError as exc:
        status, raw = exc.code, exc.read()
    loaded: object = json.loads(raw.decode("utf-8"))
    assert isinstance(loaded, dict)
    return status, cast(Json, loaded)


def _post_json(server: ScratchpadServer, request: Json) -> Json:
    status, body = _post(server, json.dumps(request).encode("utf-8"))
    assert status == body["status"]
    return body


def test_http_apply_undo_redo_match_handle(server: ScratchpadServer) -> None:
    state: Json | None = None
    for op in COLUMN:
        state = _ok(_post_json(server, _request("apply", state, op=op)))
    assert state is not None
    assert state == _column_state()
    undone = _ok(_post_json(server, _request("undo", state)))
    redone = _ok(_post_json(server, _request("redo", undone)))
    assert redone["document"] == state["document"] and redone["redo"] == []
    assert server.document.ops() == ()  # stateless: the instance document is untouched


def test_http_refusal_is_a_422_body(server: ScratchpadServer) -> None:
    body = _post_json(server, _request("undo"))
    _refused(body, "REFUSED")
    status, garbage = _post(server, b"{not json")
    assert status == 422
    _refused(garbage, "INVALID_ARGUMENT")


def test_api_op_keeps_its_400(server: ScratchpadServer) -> None:
    port = server.server_address[1]
    request = Request(
        f"http://127.0.0.1:{port}/api/op",
        data=json.dumps({"op": "AddHoop", "bar_ids": [9, 8], "designation": "Ø10"}).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(HTTPError) as error:
        urlopen(request)
    assert error.value.code == 400
