"""Stage C4 surfaces: the `get_section_draft` tool (local, hosted, MCP) and its HTTP route."""

from __future__ import annotations

import json
from threading import Thread
from typing import cast
from urllib.request import urlopen

from _section_fixtures import l_wall_two_hoops
from apeCAD.agent import LocalTools
from apeCAD.agent.hosted import call_hosted
from apeCAD.agent.mcp_tools import TOOLS
from apeCAD.agent.session import Session
from apeCAD.scratchpad.server import ScratchpadServer
from apeCAD.section_draft import section_block


def _draft(envelope: dict[str, object]) -> dict[str, object]:
    assert envelope["ok"] is True, envelope
    draft = envelope["draft"]
    assert isinstance(draft, dict)
    return cast(dict[str, object], draft)


def test_local_tool_returns_the_draft_without_a_new_revision() -> None:
    tools = LocalTools()
    doc = cast(str, tools.new_document()["document"])
    session = tools.session(doc)
    built = l_wall_two_hoops()
    for op in built.ops():
        session.document.apply(op)
    before = session.document.to_dict()
    envelope = tools.get_section_draft(doc)
    draft = _draft(envelope)
    assert envelope["revision"] == session.revision
    assert draft["schema"] == "apeCAD.section-draft" and draft["version"] == 1
    assert draft["section"] == section_block(built)
    assert draft["document"] == before == session.document.to_dict()
    assert tools.get_section_draft("doc-404")["ok"] is False


def test_hosted_and_mcp_tables_name_the_tool() -> None:
    session = Session(l_wall_two_hoops())
    draft = _draft(call_hosted(session, {"tool": "get_section_draft", "arguments": {}}))
    assert draft["section"] == section_block(session.document)
    refused = call_hosted(session, {"tool": "get_section_draft", "arguments": {"x": 1}})
    assert refused["ok"] is False
    tool = TOOLS["get_section_draft"]
    assert tool.required == ("document",) and set(tool.properties) == {"document"}


def test_http_route_serves_the_draft() -> None:
    server = ScratchpadServer(("127.0.0.1", 0), l_wall_two_hoops())
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        with urlopen(f"http://127.0.0.1:{port}/api/section/draft") as response:
            assert response.status == 200
            payload = cast(dict[str, object], json.loads(response.read().decode("utf-8")))
        assert _draft(payload)["section"] == section_block(server.document)
    finally:
        server.shutdown()
        server.server_close()
