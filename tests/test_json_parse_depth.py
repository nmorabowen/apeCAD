"""A JSON text too deep to parse is refused by name on every path (apeSection#51).

`json.loads` raises `RecursionError` past a depth that depends on the Python: 980 levels on
3.11.15 and 2987 on 3.12.10. Uncaught, the HTTP handler thread dies and the client gets a
dropped connection. `OVERFLOWS` overflows both. Every row asserts the answer and that the
document, its revision and its redo stack are what they were: the failure is in the parse.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from threading import Thread
from typing import cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from apeCAD import Document
from apeCAD.agent import LocalTools
from apeCAD.cli import main as cli_main
from apeCAD.errors import INVALID_ARGUMENT, REFUSED, DocumentError
from apeCAD.ops.types import SCHEMA_ID
from apeCAD.scratchpad.server import ScratchpadServer

Json = dict[str, object]

OVERFLOWS = 100_000
TOO_DEEP_BODY = "body is nested too deeply to parse as JSON"
TOO_DEEP_DOCUMENT = "document JSON is nested too deeply to parse"
POINT: Json = {"x_mm": 0, "y_mm": 0, "z_mm": 0}


def _lists(levels: int) -> str:
    return "[" * levels + "0" + "]" * levels


def _objects(levels: int) -> str:
    return '{"a":' * levels + "0" + "}" * levels


DEEP = {
    "lists": _lists(OVERFLOWS),
    "objects": _objects(OVERFLOWS),
    "inside_an_object": '{"op": "AddPoint", "x_mm": ' + _lists(OVERFLOWS) + "}",
    "inside_the_ops": '{"schema": "' + SCHEMA_ID + '", "units": "mm", "ops": '
    + _lists(OVERFLOWS) + "}",
}  # fmt: skip


@pytest.fixture
def server() -> Iterator[ScratchpadServer]:
    """A document with a point on its log and another on its redo stack, at revision 3."""
    bound = ScratchpadServer(("127.0.0.1", 0), Document())
    session = bound.session
    session.apply("AddPoint", POINT)
    session.apply("AddPoint", {**POINT, "x_mm": 100})
    session.undo()
    assert session.revision == 3 and session.can_undo and session.can_redo
    Thread(target=bound.serve_forever, daemon=True).start()
    yield bound
    bound.shutdown()
    bound.server_close()


def _post(server: ScratchpadServer, path: str, text: str) -> tuple[int, Json]:
    port = server.server_address[1]
    request = Request(f"http://127.0.0.1:{port}{path}", data=text.encode("utf-8"), method="POST")
    try:
        with urlopen(request) as response:
            return response.status, cast(Json, json.loads(response.read().decode("utf-8")))
    except HTTPError as refused:
        return refused.code, cast(Json, json.loads(refused.read().decode("utf-8")))


def _state(server: ScratchpadServer) -> tuple[str, int, bool, bool]:
    session = server.session
    return session.document.to_json(), session.revision, session.can_undo, session.can_redo


@pytest.mark.parametrize("body", sorted(DEEP))
@pytest.mark.parametrize(
    "path",
    ["/api/op", "/api/ops", "/api/tool", "/api/load", "/api/undo", "/api/redo", "/api/reset"],
)
def test_a_too_deep_body_is_a_named_400(server: ScratchpadServer, path: str, body: str) -> None:
    before = _state(server)
    status, answer = _post(server, path, DEEP[body])
    assert status == 400, answer
    assert answer == {"error": TOO_DEEP_BODY, "code": INVALID_ARGUMENT, "revision": 3}
    assert _state(server) == before


@pytest.mark.parametrize("body", sorted(DEEP))
def test_a_too_deep_body_is_a_named_transport_refusal(
    server: ScratchpadServer, body: str
) -> None:
    before = _state(server)
    status, answer = _post(server, "/api/section/transport", DEEP[body])
    assert status == 422, answer
    assert answer["ok"] is False and answer["status"] == 422
    error = cast(Json, answer["error"])
    assert error["code"] == INVALID_ARGUMENT and error["message"] == TOO_DEEP_BODY
    assert _state(server) == before


def test_the_server_keeps_serving_after_a_too_deep_body(server: ScratchpadServer) -> None:
    assert _post(server, "/api/op", DEEP["lists"])[0] == 400
    status, scene = _post(server, "/api/redo", "")
    assert status == 200 and scene["revision"] == 4


@pytest.mark.parametrize("levels", [100, 900, 975, 985, 2500, 2985, 2995, 5000])
@pytest.mark.parametrize(
    ("path", "wrap"),
    [
        ("/api/op", '{{"op": "AddLine", "start_id": {}, "end_id": 1}}'),
        ("/api/ops", '{{"ops": {}}}'),
        ("/api/tool", '{{"tool": {}}}'),
        ("/api/load", '{{"schema": {}}}'),
        ("/api/undo", '{{"expect_revision": {}}}'),
    ],
)
def test_a_body_around_the_parser_limit_is_answered_on_either_side(
    server: ScratchpadServer, path: str, wrap: str, levels: int
) -> None:
    """Parsed or not, the answer is a coded refusal: the depth reaches the readers either way."""
    before = _state(server)
    status, answer = _post(server, path, wrap.format(_lists(levels)))
    assert status == 400, answer
    error = cast(Json, answer["error"] if isinstance(answer["error"], dict) else answer)
    assert error["code"] in (INVALID_ARGUMENT, REFUSED)
    assert _state(server) == before


@pytest.mark.parametrize("text", sorted(DEEP))
def test_from_json_refuses_a_too_deep_text_by_name(text: str) -> None:
    with pytest.raises(DocumentError, match=TOO_DEEP_DOCUMENT) as refused:
        Document.from_json(DEEP[text])
    assert refused.value.code == REFUSED


def test_from_json_still_replays_a_document_and_still_raises_on_bad_json() -> None:
    doc = Document()
    doc.add_point(1.0, 2.0, 0.0)
    assert Document.from_json(doc.to_json()).to_json() == doc.to_json()
    with pytest.raises(ValueError):
        Document.from_json("{not json")


@pytest.mark.parametrize("text", sorted(DEEP))
def test_open_document_refuses_a_too_deep_file_and_opens_nothing(
    tmp_path: Path, text: str
) -> None:
    path = tmp_path / "deep.json"
    path.write_text(DEEP[text], encoding="utf-8")
    tools = LocalTools()
    kept = cast(str, tools.new_document()["document"])
    tools.apply_op(kept, "AddPoint", POINT)
    before = tools.session(kept).document.to_json()
    out = tools.open_document(str(path))
    assert out == {
        "ok": False,
        "error": {"code": REFUSED, "message": f"deep.json: {TOO_DEEP_DOCUMENT}"},
    }
    assert tools.session(kept).document.to_json() == before
    assert tools.new_document()["document"] == "doc-2"  # nothing was registered


def test_the_cli_refuses_a_too_deep_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "deep.json"
    path.write_text(DEEP["lists"], encoding="utf-8")
    assert cli_main(["inspect", str(path)]) == 1
    error = cast(Json, json.loads(capsys.readouterr().out)["error"])
    assert error["code"] == REFUSED and TOO_DEEP_DOCUMENT in cast(str, error["message"])
