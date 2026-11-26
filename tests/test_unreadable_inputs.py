"""An oversized input is a named refusal on every path, never a dropped connection
(apeSection#54 items 1 and 3; item 2 is the same class and closes with them).

Two inputs a JSON reader can be handed and Python cannot always handle:

- a list nested about 980 levels deep. It parses, but `repr` or a recursive check of it runs
  out of stack in an HTTP handler thread, which has less stack left than the main thread.
  The window is narrow (981 and 982 levels on 3.11.15) and depends on the Python, so the
  HTTP rows sweep every depth from 960 to 1000 and a few past 3.12's parser limit;
- an integer beyond the float range: `float()` raises `OverflowError`, and past 4300 digits
  `repr` raises `ValueError`. JSON carries any integer under 4300 digits.

`apeCAD.unreadable.refusing_unreadable` wraps each entry point. Each row asserts the coded
answer, the path it names, and that the document, its revision and its redo stack are what
they were.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from threading import Thread
from typing import cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from _section_fixtures_v2 import BUILDERS_V2
from apeCAD import Document
from apeCAD.agent import LocalTools
from apeCAD.cli import main as cli_main
from apeCAD.errors import INVALID_ARGUMENT, REFUSED, DocumentError, OpArgumentError
from apeCAD.ops.types import SCHEMA_ID
from apeCAD.scratchpad import transport
from apeCAD.scratchpad.server import ScratchpadServer
from apeCAD.section.templates import expand
from apeCAD.section.templates.plan import TemplateParamError
from apeCAD.section_draft import section_seed
from apeCAD.unreadable import NESTING_FLOOR, cause, refusing_unreadable

Json = dict[str, object]
BIG = "1" * 401  # 401 digits: parses, and no float holds it
BIG_BITS = int(BIG).bit_length()
TOO_LARGE = f"is an integer too large to read ({BIG_BITS} bits; a number holds 1024)"
WINDOW = [*range(960, 1001), 1500, 2500, 2980]


def _lists(levels: int) -> str:
    return "[" * levels + "0" + "]" * levels


def _point(x: str) -> str:
    return '{"op": "AddPoint", "x_mm": ' + x + ', "y_mm": 0, "z_mm": 0}'


def _line(start: str) -> str:
    return '{"op": "AddLine", "start_id": ' + start + ', "end_id": 1}'


def _log(op: str) -> str:
    return '{"schema": "' + SCHEMA_ID + '", "units": "mm", "ops": [' + op + "]}"


def _transport(action: str, document: str, op: str | None = None) -> str:
    tail = "" if op is None else ', "op": ' + op
    return (
        '{"transport_version": 1, "action": "' + action + '", "document": ' + document + tail
        + "}"
    )


EMPTY = json.dumps(Document().to_dict())


@pytest.fixture
def server() -> Iterator[ScratchpadServer]:
    """A document with a point on its log and another on its redo stack, at revision 3."""
    bound = ScratchpadServer(("127.0.0.1", 0), Document())
    session = bound.session
    session.apply("AddPoint", {"x_mm": 0, "y_mm": 0, "z_mm": 0})
    session.apply("AddPoint", {"x_mm": 100, "y_mm": 0, "z_mm": 0})
    session.undo()
    Thread(target=bound.serve_forever, daemon=True).start()
    yield bound
    bound.shutdown()
    bound.server_close()


def _post(server: ScratchpadServer, path: str, text: str) -> tuple[int, Json]:
    """The answer; a dropped connection raises here (`RemoteDisconnected`) and fails the row."""
    port = server.server_address[1]
    request = Request(f"http://127.0.0.1:{port}{path}", data=text.encode("utf-8"), method="POST")
    try:
        with urlopen(request, timeout=60) as response:
            return response.status, cast(Json, json.loads(response.read().decode("utf-8")))
    except HTTPError as refused:
        return refused.code, cast(Json, json.loads(refused.read().decode("utf-8")))


def _state(server: ScratchpadServer) -> tuple[str, int, bool, bool]:
    session = server.session
    return session.document.to_json(), session.revision, session.can_undo, session.can_redo


def _error(path: str, answer: Json) -> Json:
    if path == "/api/section/transport":
        assert answer["ok"] is False and answer["status"] == 422, answer
        return cast(Json, answer["error"])
    if isinstance(answer.get("error"), dict):  # an envelope: /api/ops
        return cast(Json, answer["error"])
    return {"code": answer["code"], "message": answer["error"]}


# ---- item 1: deep nesting in the handler thread's window ---------------------------------

DEEP_ROUTES: dict[str, tuple[str, Callable[[str], str]]] = {
    "op/AddLine": ("/api/op", _line),
    "op/AddPoint": ("/api/op", _point),
    "ops/AddLine": ("/api/ops", lambda v: '{"ops": [' + _line(v) + "]}"),
    "load/AddLine": ("/api/load", lambda v: _log(_line(v))),
    "transport/apply": ("/api/section/transport", lambda v: _transport("apply", EMPTY, _line(v))),
    "transport/undo": ("/api/section/transport", lambda v: _transport("undo", _log(_line(v)))),
}


@pytest.mark.parametrize("route", sorted(DEEP_ROUTES))
def test_a_deep_list_at_every_depth_of_the_window_is_answered(
    server: ScratchpadServer, route: str
) -> None:
    path, wrap = DEEP_ROUTES[route]
    before = _state(server)
    for levels in WINDOW:
        status, answer = _post(server, path, wrap(_lists(levels)))
        assert status in (400, 422), (levels, answer)
        assert _error(path, answer)["code"] in (INVALID_ARGUMENT, REFUSED), (levels, answer)
        assert _state(server) == before, levels


def test_the_handler_names_the_deep_field_python_cannot_print(server: ScratchpadServer) -> None:
    """At 981 levels on 3.11 the reader's own message would `repr` the list and overflow;
    the refusal names the field instead. On a Python where the reader manages to print it,
    the reader's own refusal names the same field."""
    for levels in (981, 982):
        status, answer = _post(server, "/api/op", _line(_lists(levels)))
        assert status == 400, answer
        assert answer["code"] == INVALID_ARGUMENT
        message = cast(str, answer["error"])
        assert message.startswith("AddLine.start_id"), message[:120]
        assert len(message) < 20_000


# ---- item 2: an integer beyond the float range over HTTP --------------------------------

BIG_ROUTES: dict[str, tuple[str, str, str]] = {
    "op": ("/api/op", _point(BIG), "AddPoint.x_mm"),
    "ops": ("/api/ops", '{"ops": [' + _point(BIG) + "]}", "AddPoint.x_mm"),
    "load": ("/api/load", _log(_point(BIG)), "document.ops[0].x_mm"),
    "tool": (
        "/api/tool",
        '{"tool": "apply_op", "arguments": {"op": "AddPoint", "params": '
        '{"x_mm": ' + BIG + ', "y_mm": 0, "z_mm": 0}}}',
        "AddPoint.x_mm",
    ),
    "transport/apply": (
        "/api/section/transport", _transport("apply", EMPTY, _point(BIG)), "request.op.x_mm"
    ),
    "transport/undo": (
        "/api/section/transport", _transport("undo", _log(_point(BIG))), "document.ops[0].x_mm"
    ),
}


@pytest.mark.parametrize("route", sorted(BIG_ROUTES))
def test_an_integer_no_float_holds_is_a_named_refusal(
    server: ScratchpadServer, route: str
) -> None:
    path, body, field = BIG_ROUTES[route]
    before = _state(server)
    status, answer = _post(server, path, body)
    assert status in (400, 422), answer
    error = _error(path, answer)
    assert error["code"] in (INVALID_ARGUMENT, REFUSED), answer
    assert f"{field} {TOO_LARGE}" in cast(str, error["message"]), error
    assert _state(server) == before


def test_a_seed_load_is_covered_by_the_post_backstop(server: ScratchpadServer) -> None:
    """`/api/load` of a section-seed builds through no `Session` and no `from_dict`: the
    guard around every POST route names the field."""
    seed = json.dumps(section_seed(BUILDERS_V2["box_with_void"](), version=2))
    assert '"cover_mm": 40.0' in seed
    big_cover = seed.replace('"cover_mm": 40.0', f'"cover_mm": {BIG}')
    status, answer = _post(server, "/api/load", big_cover)
    assert status == 400, answer
    assert answer["code"] == INVALID_ARGUMENT
    assert f"{TOO_LARGE}" in cast(str, answer["error"]) and "cover_mm" in cast(str, answer["error"])


def test_the_server_keeps_serving(server: ScratchpadServer) -> None:
    assert _post(server, "/api/op", _point(BIG))[0] == 400
    assert _post(server, "/api/op", _line(_lists(981)))[0] == 400
    status, scene = _post(server, "/api/redo", "")
    assert status == 200 and scene["revision"] == 4


# ---- item 3 and the in-process paths -----------------------------------------------------


def _in_thread(call: Callable[[], object]) -> object:
    """Run `call` in a worker thread, as an HTTP handler or an MCP host would."""
    out: list[object] = []
    worker = threading.Thread(target=lambda: out.append(call()))
    worker.start()
    worker.join()
    assert out, "the call raised in its thread"
    return out[0]


def _deep(levels: int) -> object:
    value: object = 0
    for _ in range(levels):
        value = [value]
    return value


@pytest.mark.parametrize(
    ("value", "op", "field"),
    [
        (10**400, "AddPoint", "x_mm"),
        (10**5000, "AddPoint", "x_mm"),
        (10**5000, "AddLine", "start_id"),  # `repr` raised ValueError past 4300 digits
        (_deep(985), "AddPoint", "x_mm"),
        (_deep(985), "AddLine", "start_id"),
    ],
    ids=["10^400-point", "10^5000-point", "10^5000-line", "deep-point", "deep-line"],
)
def test_local_tools_refuse_an_unreadable_argument_by_name(
    value: object, op: str, field: str
) -> None:
    params: Json = (
        {"x_mm": value, "y_mm": 0, "z_mm": 0} if op == "AddPoint"
        else {"start_id": value, "end_id": 1}
    )
    tools = LocalTools()
    doc = cast(str, tools.new_document()["document"])
    one = cast(Json, _in_thread(lambda: tools.apply_op(doc, op, params)))
    batch = cast(Json, _in_thread(lambda: tools.apply_ops(doc, [{"op": op, "params": params}])))
    for out in (one, batch):
        assert out["ok"] is False, out
        error = cast(Json, out["error"])
        assert error["code"] == INVALID_ARGUMENT, error
        assert f"{op}.{field}" in cast(str, error["message"]), error
    assert cast(Json, batch["error"])["index"] == 0
    assert tools.session(doc).revision == 0


@pytest.mark.parametrize("value", [10**400, 10**5000], ids=["10^400", "10^5000"])
def test_from_dict_and_open_document_name_the_field(tmp_path: Path, value: int) -> None:
    payload: Json = {
        "schema": SCHEMA_ID, "units": "mm",
        "ops": [{"op": "AddPoint", "x_mm": value, "y_mm": 0, "z_mm": 0}],
    }
    with pytest.raises(DocumentError, match=r"^document\.ops\[0\]\.x_mm is an integer") as e:
        Document.from_dict(payload)
    assert e.value.code == REFUSED
    with pytest.raises(DocumentError, match=r"^redo\[0\]\.x_mm is an integer"):
        Document.from_dict({**payload, "ops": []}, redo=payload["ops"])  # type: ignore[arg-type]
    if value == 10**400:  # JSON carries it; 10^5000 is refused by the parser as not JSON
        path = tmp_path / "big.json"
        path.write_text(_log(_point(str(value))), encoding="utf-8")
        out = LocalTools().open_document(str(path))
        error = cast(Json, out["error"])
        assert out["ok"] is False and error["code"] == REFUSED
        assert "document.ops[0].x_mm is an integer too large" in cast(str, error["message"])


def test_the_in_process_transport_names_the_field() -> None:
    request: Json = {
        "transport_version": 1, "action": "apply", "document": Document().to_dict(),
        "op": {"op": "AddLine", "start_id": 10**5000, "end_id": 1},
    }
    out = transport.handle(request)
    error = cast(Json, out["error"])
    assert out["status"] == 422 and error["code"] == INVALID_ARGUMENT
    assert cast(str, error["message"]).startswith("request.op.start_id is an integer too large")


def test_the_cli_refuses_a_too_deep_params_argument(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`cli.py::_json_arg` let the parser's `RecursionError` out (apeSection#54 item 3)."""
    path = tmp_path / "doc.json"
    assert cli_main(["new", str(path)]) == 0
    capsys.readouterr()
    before = path.read_bytes()
    assert cli_main(["apply", str(path), "AddPoint", _lists(100_000)]) == 2
    error = cast(Json, json.loads(capsys.readouterr().out)["error"])
    assert error == {
        "code": INVALID_ARGUMENT,
        "message": "PARAMS_JSON is nested too deeply to parse as JSON",
    }
    assert path.read_bytes() == before


@pytest.mark.parametrize("version", [10**5000, -(10**5000)], ids=["10^5000", "-10^5000"])
def test_expand_names_a_version_it_cannot_print(version: int) -> None:
    """`section/templates/__init__.py` printed the version with `repr` (apeSection#54 item 3)."""
    with pytest.raises(TemplateParamError, match="unknown version an unprintable int"):
        expand("rect_column", {}, version=version)


# ---- the guard itself ---------------------------------------------------------------------


def test_an_error_with_no_oversized_cause_propagates_unchanged() -> None:
    """A bug that raises one of the caught classes on an ordinary input stays loud."""
    for error in (ValueError("a bug"), OverflowError("a bug"), RecursionError("a bug")):
        with pytest.raises(type(error), match="a bug"):
            with refusing_unreadable("AddPoint", lambda: {"x_mm": 1.0}, OpArgumentError):
                raise error


def test_nesting_under_the_floor_is_not_blamed_for_a_recursion_error() -> None:
    shallow = {"x_mm": _deep(NESTING_FLOOR - 1)}
    assert cause(shallow, "AddPoint", deep_first=True) is None
    deep = {"x_mm": _deep(NESTING_FLOOR)}
    assert cause(deep, "AddPoint", deep_first=True) == (
        f"AddPoint.x_mm is nested {NESTING_FLOOR} levels deep, too deep to read"
    )


def test_the_deep_path_stops_where_plain_list_nesting_starts() -> None:
    value = {"ops": [{"op": "AddLine", "start_id": _deep(900)}], "units": "mm"}
    assert cause(value, "document", deep_first=True) == (
        "document.ops[0].start_id is nested 900 levels deep, too deep to read"
    )
    objects: object = 0
    for _ in range(900):
        objects = {"a": objects}
    named = cause({"x_mm": objects}, "AddPoint", deep_first=True)
    assert named == "AddPoint.x_mm.a.a.a.a.a.a.a is nested 893 levels deep, too deep to read"


def test_a_container_that_holds_itself_is_named() -> None:
    loop: list[object] = []
    loop.append(loop)
    assert cause({"x_mm": loop}, "AddPoint", deep_first=True) == "AddPoint contains itself"


def test_a_shared_reference_dag_is_scanned_once_per_container() -> None:
    """2^200 paths, 200 containers: the scan is linear in containers, not in paths. It runs
    in a daemon thread, so a scan that walks paths fails at the limit instead of hanging."""
    node: object = 10**400
    for _ in range(200):
        node = [node, node]
    found: list[str | None] = []

    def scan() -> None:
        found.append(cause({"x_mm": node}, "AddPoint", deep_first=True))
        found.append(cause({"x_mm": node}, "AddPoint", deep_first=False))

    worker = threading.Thread(target=scan, daemon=True)
    worker.start()
    worker.join(timeout=10.0)  # WALL_GUARD: about 1 ms on a quiet machine
    assert not worker.is_alive(), "the scan walks paths, not containers"
    named, large = found
    assert named == "AddPoint.x_mm is nested 200 levels deep, too deep to read"
    assert large is not None and large.startswith("AddPoint.x_mm[0][0]")

