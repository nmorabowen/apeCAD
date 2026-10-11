"""The scratchpad's agent routes (spec agent-surface-mcp §6, stage S2) over HTTP on port 0."""

from __future__ import annotations

import json
from collections.abc import Iterator
from threading import Thread
from typing import cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from apeCAD.document import Document
from apeCAD.scratchpad.server import ScratchpadServer


@pytest.fixture
def server() -> Iterator[ScratchpadServer]:
    bound = ScratchpadServer(("127.0.0.1", 0), Document())
    thread = Thread(target=bound.serve_forever, daemon=True)
    thread.start()
    yield bound
    bound.shutdown()
    bound.server_close()


def _request(
    server: ScratchpadServer, path: str, body: dict[str, object] | None = None
) -> tuple[int, dict[str, object]]:
    port = server.server_address[1]
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        method="GET" if body is None else "POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request) as response:
            status, raw = response.status, response.read()
    except HTTPError as exc:
        status, raw = exc.code, exc.read()
    loaded: object = json.loads(raw.decode("utf-8"))
    assert isinstance(loaded, dict)
    return status, cast(dict[str, object], loaded)


def _ok(
    server: ScratchpadServer, path: str, body: dict[str, object] | None = None
) -> dict[str, object]:
    status, payload = _request(server, path, body)
    assert status == 200, payload
    return payload


def _point(x: float) -> dict[str, object]:
    return {"op": "AddPoint", "params": {"x_mm": x, "y_mm": 0, "z_mm": 0}}


def test_revision_starts_at_zero_and_counts_every_mutation(server: ScratchpadServer) -> None:
    assert _ok(server, "/api/revision") == {"revision": 0}
    flat = {"op": "AddPoint", "x_mm": 0, "y_mm": 0, "z_mm": 0}
    assert _ok(server, "/api/op", flat)["revision"] == 1
    assert _ok(server, "/api/op", _point(1000))["revision"] == 2  # the {op, params} form
    assert _ok(server, "/api/undo", {})["revision"] == 3
    assert _ok(server, "/api/redo", {})["revision"] == 4
    loaded = _ok(server, "/api/load", server.document.to_dict())
    assert loaded["revision"] == 5
    assert _ok(server, "/api/reset", {})["revision"] == 6
    assert _ok(server, "/api/revision") == {"revision": 6}


def test_op_with_a_stale_expect_revision_is_409(server: ScratchpadServer) -> None:
    body = {**_point(0), "expect_revision": 0}
    first = _ok(server, "/api/op", body)
    assert first["revision"] == 1 and first["created_id"] == 1
    status, resent = _request(server, "/api/op", body)
    assert status == 409
    assert resent["code"] == "STALE" and resent["revision"] == 1
    assert len(server.document.ops()) == 1


def test_refused_op_stays_400_with_a_code(server: ScratchpadServer) -> None:
    _ok(server, "/api/op", _point(0))
    status, refused = _request(
        server, "/api/op", {"op": "AddLine", "params": {"start_id": 1, "end_id": 1}}
    )
    assert status == 400 and refused["code"] == "REFUSED"
    status, undo = _request(server, "/api/undo", {"expect_revision": 7})
    assert status == 409 and undo["code"] == "STALE"


def test_post_ops_batch(server: ScratchpadServer) -> None:
    batch = {"ops": [_point(0), _point(1000)], "expect_revision": 0}
    applied = _ok(server, "/api/ops", batch)
    assert applied["ok"] is True and applied["revision"] == 1
    results = cast(list[dict[str, object]], applied["results"])
    assert [r["created_id"] for r in results] == [1, 2]
    log = server.document.to_json()
    bad = [_point(5), _point(6), {"op": "AddLine", "params": {"start_id": 1, "end_id": 1}}]
    status, failed = _request(server, "/api/ops", {"ops": bad})
    assert status == 400
    assert failed["ok"] is False and failed["revision"] == 1
    assert cast(dict[str, object], failed["error"])["index"] == 2
    assert server.document.to_json() == log
    status, stale = _request(server, "/api/ops", batch)
    assert status == 409 and cast(dict[str, object], stale["error"])["code"] == "STALE"
    status, extra = _request(server, "/api/ops", {"ops": [], "colour": 1})
    assert status == 400 and extra["code"] == "INVALID_ARGUMENT"


def test_inspect_document_and_entities_routes(server: ScratchpadServer) -> None:
    _ok(server, "/api/ops", {"ops": [_point(0), _point(1000), _point(2000)]})
    inspected = _ok(server, "/api/inspect")
    assert inspected["ok"] is True and inspected["revision"] == 1 and inspected["ops"] == 3
    document = _ok(server, "/api/document")
    assert document["document"] == server.document.to_dict()
    page = _ok(server, "/api/entities?kind=point&limit=2&detail=full")
    items = cast(list[dict[str, object]], page["items"])
    assert [item["id"] for item in items] == [1, 2] and page["total"] == 3
    assert items[0]["xyz_mm"] == [0.0, 0.0, 0.0]
    rest = _ok(server, f"/api/entities?kind=point&limit=2&cursor={page['next_cursor']}")
    assert [item["id"] for item in cast(list[dict[str, object]], rest["items"])] == [3]
    windowed = _ok(server, "/api/entities?window=500,-1,-1,2500,1,1&mode=inside&ids=1,2,3")
    assert [item["id"] for item in cast(list[dict[str, object]], windowed["items"])] == [2, 3]


def test_entities_route_errors(server: ScratchpadServer) -> None:
    _ok(server, "/api/ops", {"ops": [_point(0), _point(1000)]})
    page = _ok(server, "/api/entities?limit=1")
    _ok(server, "/api/op", _point(5))
    status, stale = _request(server, f"/api/entities?limit=1&cursor={page['next_cursor']}")
    assert status == 409 and cast(dict[str, object], stale["error"])["code"] == "STALE"
    for query in ("limit=x", "window=1,2,3", "mode=inside", "colour=red", "kind=blob"):
        status, bad = _request(server, f"/api/entities?{query}")
        assert status == 400, query
        assert cast(dict[str, object], bad["error"])["code"] == "INVALID_ARGUMENT", query
