"""Stage S5: attach mode against a scratchpad on port 0 (spec agent-surface-mcp §3, §9).

The tool set talks HTTP to a real `ScratchpadServer` in a thread. The MCP case skips when
the `mcp` extra is not installed; everything else needs only the stdlib.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from threading import Thread
from typing import Any, cast
from urllib.request import Request, urlopen

import pytest

from apeCAD.agent.attach import AttachError, AttachTools, attach_or_exit, attach_url, connect
from apeCAD.agent.hosted import INSTANCE_HEADER
from apeCAD.agent.session import Session
from apeCAD.document import Document
from apeCAD.scratchpad.server import ScratchpadServer

LINE: dict[str, object] = {"start_id": {"xyz": [0, 0, 0]}, "end_id": {"xyz": [6000, 0, 0]}}


class _Rebindable(ScratchpadServer):
    # A restart rebinds the same port at once; on POSIX that needs SO_REUSEADDR past TIME_WAIT.
    # Windows rebinds a closed port without it, and there the flag would allow double binds.
    allow_reuse_address = os.name != "nt"


def _start(port: int = 0, root: Path | None = None, pid: int | None = None) -> ScratchpadServer:
    server = _Rebindable(("127.0.0.1", port), Document(), root=root)
    if pid is not None:
        server.pid = pid
    Thread(target=server.serve_forever, daemon=True).start()
    return server


def _stop(server: ScratchpadServer) -> None:
    server.shutdown()
    server.server_close()


def _url(server: ScratchpadServer) -> str:
    return f"http://127.0.0.1:{server.server_address[1]}"


@pytest.fixture
def server() -> Iterator[ScratchpadServer]:
    started = _start()
    yield started
    _stop(started)


def _scene(server: ScratchpadServer) -> dict[str, Any]:
    with urlopen(f"{_url(server)}/api/scene") as response:
        return cast(dict[str, Any], json.loads(response.read()))


def _error_code(envelope: dict[str, object]) -> object:
    assert envelope["ok"] is False, envelope
    return cast(dict[str, object], envelope["error"])["code"]


def test_applies_through_the_tools_and_the_scene_shows_it(server: ScratchpadServer) -> None:
    tools = connect(_url(server))
    port = server.server_address[1]
    assert tools.document_id == f"apecad://127.0.0.1:{port}/{os.getpid()}"
    applied = tools.apply_op(tools.document_id, "AddLine", LINE, expect_revision=0)
    assert applied["ok"] is True, applied
    assert applied["revision"] == 1
    scene = _scene(server)
    assert scene["revision"] == 1
    assert [op["op"] for op in scene["document"]["ops"]] == ["AddLine"]

    # The same envelopes as local mode, from the scratchpad's session.
    assert tools.inspect(tools.document_id)["counts"] == {**_counts(), "point": 2, "line": 1}
    stale = tools.apply_op(tools.document_id, "AddLine", LINE, expect_revision=0)
    assert _error_code(stale) == "STALE"
    assert stale["revision"] == 1
    assert tools.undo(tools.document_id)["revision"] == 2
    assert tools.redo(tools.document_id)["ops"] == 1
    page = tools.query_entities(tools.document_id, kind="line")
    assert page["total"] == 1
    assert tools.list_ops("AddLine")["ok"] is True
    rendered = tools.render(tools.document_id, view="top")
    assert rendered["revision"] == 3
    assert str(rendered["svg"]).startswith("<svg")
    document = tools.get_document(tools.document_id)["document"]
    assert document == server.document.to_dict()


def _counts() -> dict[str, int]:
    return {
        kind: 0
        for kind in ("point", "line", "polyline", "box", "face", "solid", "circle", "arc")
        + ("ellipse", "bezier")
    }


def test_a_human_edit_is_seen_and_guards_expect_revision(server: ScratchpadServer) -> None:
    tools = connect(_url(server))
    body = json.dumps({"op": "AddPoint", "x_mm": 0, "y_mm": 0, "z_mm": 0}).encode()
    request = Request(f"{_url(server)}/api/op", data=body, method="POST")
    with urlopen(request) as response:
        assert json.loads(response.read())["revision"] == 1
    assert tools.inspect(tools.document_id)["revision"] == 1
    assert _error_code(tools.apply_op(tools.document_id, "AddLine", LINE, 0)) == "STALE"


def test_one_document_and_no_local_documents(server: ScratchpadServer) -> None:
    tools = connect(_url(server))
    assert _error_code(tools.new_document()) == "INVALID_ARGUMENT"
    assert _error_code(tools.open_document("x.json")) == "INVALID_ARGUMENT"
    assert _error_code(tools.save_document(tools.document_id, "x.json")) == "INVALID_ARGUMENT"
    missing = tools.inspect("doc-1")
    assert _error_code(missing) == "NOT_FOUND"
    assert "revision" not in missing


def test_stopping_the_scratchpad_is_detached_without_a_fallback() -> None:
    server = _start()
    tools = connect(_url(server))
    assert tools.apply_op(tools.document_id, "AddLine", LINE)["ok"] is True
    _stop(server)
    for envelope in (
        tools.apply_op(tools.document_id, "AddLine", LINE),
        tools.inspect(tools.document_id),
        tools.render(tools.document_id),
    ):
        assert _error_code(envelope) == "DETACHED"
        assert "revision" not in envelope
    # Nothing local to fall back on: no session, no document anywhere in the tool set.
    assert not any(isinstance(value, (Session, Document)) for value in vars(tools).values())
    assert _error_code(tools.new_document()) == "INVALID_ARGUMENT"


def test_a_restart_on_the_same_port_is_detached() -> None:
    first = _start()
    port = first.server_address[1]
    tools = connect(_url(first))
    assert tools.inspect(tools.document_id)["ok"] is True
    _stop(first)
    second = _start(port, pid=first.pid + 1)  # a new process: same port, another pid
    try:
        envelope = tools.apply_op(tools.document_id, "AddLine", LINE)
        assert _error_code(envelope) == "DETACHED"
        assert str(first.pid) in str(cast(dict[str, object], envelope["error"])["message"])
        assert second.document.ops() == ()  # the op did not land in the new instance
        # Re-attaching reads the new identity and works.
        again = connect(_url(second))
        assert again.document_id.endswith(f"/{first.pid + 1}")
        assert again.apply_op(again.document_id, "AddLine", LINE)["ok"] is True
    finally:
        _stop(second)


def test_the_instance_header_is_checked_on_every_route(server: ScratchpadServer) -> None:
    for path, data in (("/api/scene", None), ("/api/op", b"{}"), ("/api/tool", b"{}")):
        request = Request(f"{_url(server)}{path}", data=data, headers={INSTANCE_HEADER: "1"})
        with pytest.raises(Exception) as caught:
            urlopen(request)
        error = cast(Any, caught.value)
        assert error.code == 409
        assert json.loads(error.read())["code"] == "DETACHED"


def test_root_must_match(server: ScratchpadServer, tmp_path: Path) -> None:
    rooted = _start(root=tmp_path.resolve())
    try:
        assert connect(_url(rooted), tmp_path).root == tmp_path.resolve()
        with pytest.raises(AttachError, match="does not match"):
            connect(_url(rooted), tmp_path / "elsewhere")
    finally:
        _stop(rooted)
    with pytest.raises(AttachError, match="does not match"):  # the scratchpad has no root
        connect(_url(server), tmp_path)


def test_a_wrong_root_exits_2(
    server: ScratchpadServer, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    port = server.server_address[1]
    with pytest.raises(SystemExit) as caught:
        attach_or_exit(None, port, tmp_path)
    assert caught.value.code == 2
    assert "--root" in capsys.readouterr().err
    assert attach_or_exit(None, None, None) is None  # local mode


def test_attach_start_up_refusals(server: ScratchpadServer) -> None:
    assert attach_url(port=8771) == "http://127.0.0.1:8771"
    assert attach_url(attach="http://localhost:8771/") == "http://localhost:8771"
    for bad in ("http://192.168.1.5:8765", "https://127.0.0.1:8765", "127.0.0.1:8765"):
        with pytest.raises(AttachError):
            attach_url(attach=bad)
    with pytest.raises(AttachError, match="exactly one"):
        attach_url(attach="http://127.0.0.1:1", port=1)
    closed = _start()
    url = _url(closed)
    _stop(closed)
    with pytest.raises(AttachError, match="no apeCAD scratchpad"):
        connect(url)


def test_hosted_tool_route_refuses_unknown_tools_and_arguments(server: ScratchpadServer) -> None:
    tools = AttachTools(_url(server), server.pid)
    assert _error_code(tools._call("render", {})) == "INVALID_ARGUMENT"  # pyright: ignore[reportPrivateUsage]
    extra = tools._call("inspect", {"colour": "red"})  # pyright: ignore[reportPrivateUsage]
    assert _error_code(extra) == "INVALID_ARGUMENT"
    assert extra["revision"] == 0


def test_applies_through_mcp_and_the_scene_shows_it(server: ScratchpadServer) -> None:
    pytest.importorskip("mcp", reason="the mcp extra is not installed")
    import anyio
    from mcp import Client

    from apeCAD.agent.mcp import build_server

    tools = connect(_url(server))

    async def drive() -> list[Any]:
        async with Client(build_server(tools)) as client:
            applied = await client.call_tool(
                "apply_op", {"document": tools.document_id, "op": "AddLine", "params": LINE}
            )
            refused = await client.call_tool("new_document", {})
            return [applied, refused]

    applied, refused = anyio.run(drive)
    assert not applied.is_error
    assert applied.structured_content["revision"] == 1
    assert refused.is_error
    assert refused.structured_content["error"]["code"] == "INVALID_ARGUMENT"
    assert [op["op"] for op in _scene(server)["document"]["ops"]] == ["AddLine"]
