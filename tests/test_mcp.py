"""Stage S3: the MCP adapter, driven by the SDK's in-memory client (spec agent-surface-mcp §9).

Skips when the `mcp` extra is not installed; `test_mcp_tools.py` holds the checks that need
no SDK.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

from apeCAD.agent.mcp_tools import TOOLS

SRC = Path(__file__).resolve().parents[1] / "src"

mcp = pytest.importorskip("mcp", reason="the mcp extra is not installed")

from mcp import Client  # noqa: E402
from mcp.shared.exceptions import MCPError  # noqa: E402

from apeCAD.agent.local import LocalTools  # noqa: E402
from apeCAD.agent.mcp import build_server  # noqa: E402

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _structured(result: Any) -> dict[str, Any]:
    assert isinstance(result.structured_content, dict)
    return result.structured_content


async def _new_document(client: Client) -> str:
    result = await client.call_tool("new_document", {})
    assert not result.is_error
    return _structured(result)["document"]


async def test_lists_every_tool() -> None:
    async with Client(build_server()) as client:
        listed = await client.list_tools()
    names = {tool.name for tool in listed.tools}
    assert names == set(TOOLS)
    assert {"apply_op", "apply_ops", "render", "query_entities", "list_ops"} <= names
    apply_op = next(tool for tool in listed.tools if tool.name == "apply_op")
    assert apply_op.input_schema["required"] == ["document", "op"]


async def test_applies_a_line_and_a_hooped_section() -> None:
    local = LocalTools()
    async with Client(build_server(local)) as client:
        doc = await _new_document(client)
        line = await client.call_tool(
            "apply_op",
            {
                "document": doc,
                "op": "AddLine",
                "params": {"start_id": {"xyz": [0, 0, 0]}, "end_id": {"xyz": [6000, 0, 0]}},
                "expect_revision": 0,
            },
        )
        assert not line.is_error
        assert _structured(line)["revision"] == 1
        assert json.loads(line.content[0].text) == _structured(line)

        section = await _new_document(client)
        bars: list[int] = []
        for x, y in ((60, 60), (340, 60), (340, 540), (60, 540)):
            bar = await client.call_tool(
                "apply_op",
                {
                    "document": section,
                    "op": "AddBar",
                    "params": {"x_mm": x, "y_mm": y, "designation": "Ø16"},
                },
            )
            assert not bar.is_error, bar.content[0].text
            bars.append(_structured(bar)["created_id"])
        hoop = await client.call_tool(
            "apply_op",
            {
                "document": section,
                "op": "AddHoop",
                "params": {"bar_ids": bars, "designation": "Ø10", "spacing_mm": 100},
            },
        )
        assert not hoop.is_error, hoop.content[0].text
        assert _structured(hoop)["revision"] == 5

        inspected = _structured(await client.call_tool("inspect", {"document": section}))
        assert inspected["counts"]["bar"] == 4
        assert inspected["counts"]["hoop"] == 1

    assert len(local.session(doc).document.ops()) == 1
    assert len(local.session(section).document.ops()) == 5


async def test_refused_op_is_a_tool_error_with_refused() -> None:
    async with Client(build_server()) as client:
        doc = await _new_document(client)
        result = await client.call_tool(
            "apply_op",
            {
                "document": doc,
                "op": "AddLine",
                "params": {"start_id": {"xyz": [0, 0, 0]}, "end_id": {"xyz": [0, 0, 0]}},
            },
        )
        assert result.is_error
        envelope = _structured(result)
        assert envelope["ok"] is False
        assert envelope["error"]["code"] == "REFUSED"
        assert envelope["revision"] == 0
        assert json.loads(result.content[0].text) == envelope

        stale = await client.call_tool("undo", {"document": doc, "expect_revision": 3})
        assert stale.is_error
        assert _structured(stale)["error"]["code"] == "STALE"


async def test_unknown_tool_is_a_jsonrpc_error() -> None:
    async with Client(build_server()) as client:
        with pytest.raises(MCPError) as caught:
            await client.call_tool("draw_everything", {})
    assert caught.value.code == -32602
    assert "draw_everything" in caught.value.message


async def test_bad_arguments_are_a_jsonrpc_error() -> None:
    async with Client(build_server()) as client:
        doc = await _new_document(client)
        with pytest.raises(MCPError) as caught:
            await client.call_tool("apply_op", {"document": doc, "op": "AddLine", "bogus": 1})
    assert caught.value.code == -32602


async def test_render_returns_the_svg_as_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "resvg_py", None)
    async with Client(build_server()) as client:
        doc = await _new_document(client)
        await client.call_tool(
            "apply_op",
            {
                "document": doc,
                "op": "AddLine",
                "params": {"start_id": {"xyz": [0, 0, 0]}, "end_id": {"xyz": [1000, 0, 0]}},
            },
        )
        result = await client.call_tool("render", {"document": doc, "view": "top"})
        assert not result.is_error
        assert result.content[0].type == "text"
        assert result.content[0].text.startswith("<svg")
        envelope = _structured(result)
        assert "svg" not in envelope
        assert envelope["view"] == "top"
        assert envelope["entities"] >= 1

        png = await client.call_tool("render", {"document": doc, "format": "png"})
        assert png.is_error
        assert _structured(png)["error"]["code"] == "UNAVAILABLE"


async def test_render_png_returns_image_content(monkeypatch: pytest.MonkeyPatch) -> None:
    import types as pytypes

    from test_render import _fake_png  # pyright: ignore[reportPrivateUsage]

    fake = pytypes.ModuleType("resvg_py")
    fake.svg_to_bytes = _fake_png  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "resvg_py", fake)
    async with Client(build_server()) as client:
        doc = await _new_document(client)
        result = await client.call_tool(
            "render", {"document": doc, "format": "png", "width": 320, "height": 200}
        )
        assert not result.is_error
        assert result.content[0].type == "image"
        assert result.content[0].mime_type == "image/png"
        envelope = _structured(result)
        assert "png" not in envelope and "svg" not in envelope
        assert (envelope["width"], envelope["height"]) == (320, 200)


def test_module_entry_point_serves_stdio() -> None:
    """`python -m apeCAD.mcp` speaks JSON-RPC on stdout only: every line parses, a routing
    error is a JSON-RPC error, a tool failure is a result with `isError`."""
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "nope"}},
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "undo", "arguments": {"document": "doc-9"}},
        },
    ]
    process = subprocess.Popen(
        [sys.executable, "-m", "apeCAD.mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=_env(),
    )
    stdin, stdout, stderr = process.stdin, process.stdout, process.stderr
    assert stdin is not None and stdout is not None and stderr is not None
    lines: queue.Queue[str] = queue.Queue()
    threading.Thread(target=lambda: [lines.put(line) for line in stdout], daemon=True).start()
    stdin.write("".join(json.dumps(request) + "\n" for request in requests))
    stdin.flush()
    replies: list[dict[str, Any]] = []
    try:
        while len(replies) < 4:  # stdin stays open until every reply is in, as with a client
            replies.append(json.loads(lines.get(timeout=30)))
    finally:
        stdin.close()
        process.wait(timeout=30)
    log = stderr.read()
    stderr.close()
    by_id = {reply.get("id"): reply for reply in replies}
    assert by_id[1]["result"]["serverInfo"]["name"] == "apeCAD"
    assert {tool["name"] for tool in by_id[2]["result"]["tools"]} == set(TOOLS)
    assert by_id[3]["error"]["code"] == -32602
    assert by_id[4]["result"]["isError"] is True
    assert by_id[4]["result"]["structuredContent"]["error"]["code"] == "NOT_FOUND"
    assert "serving" in log


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(SRC), env.get("PYTHONPATH")]))
    return env
