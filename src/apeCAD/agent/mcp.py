"""MCP adapter (spec agent-surface-mcp, stages S3 and S5): serves a tool set over the `mcp` SDK.

Local mode serves `LocalTools`; `--attach-port N` / `--attach URL` serve `AttachTools`, which
edit the document of a running scratchpad (exit status 2 if its identity does not check out).

Needs the `mcp` extra (`pip install apeCAD[mcp]`); nothing outside this module and
`apeCAD.mcp` imports it, so `import apeCAD` stays stdlib-only.

- Every tool result is the §2 envelope as structured content, with the same JSON as a text
  block. A failed envelope (`REFUSED`, `STALE`, `NOT_FOUND`, ...) sets `isError: true`.
- `render` puts the SVG in the text block instead, and leaves it out of the envelope;
  `export_dxf` does the same with the DXF.
- An unknown tool, or arguments that do not fit the tool's input schema, are JSON-RPC
  invalid-params errors (`mcp_tools.check_arguments`).
- stdout carries JSON-RPC only; logs go to stderr.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import anyio
import mcp_types as types
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import MCPError

import apeCAD
from apeCAD.agent.attach import AttachTools, attach_or_exit
from apeCAD.agent.errors import Envelope
from apeCAD.agent.local import LocalTools
from apeCAD.agent.mcp_tools import TOOLS, ArgumentProblem, ToolSet, check_arguments

SERVER_NAME = "apeCAD"

log = logging.getLogger("apeCAD.mcp")


def tool_result(name: str, envelope: Envelope) -> types.CallToolResult:
    """Wrap one envelope as an MCP tool result."""
    ok = envelope.get("ok") is True
    payload = {"render": "svg", "export_dxf": "dxf"}.get(name)
    body = envelope.get(payload) if payload is not None else None
    if payload is not None and ok and isinstance(body, str):
        structured = {key: value for key, value in envelope.items() if key != payload}
        text = body
    else:
        structured = envelope
        text = json.dumps(envelope, separators=(",", ":"))
    return types.CallToolResult(
        content=[types.TextContent(text=text)],
        structured_content=structured,
        is_error=not ok,
    )


LOCAL_INSTRUCTIONS = (
    "apeCAD draws structural intent in millimetres. Call new_document, read "
    "list_ops for the op schemas, then apply_op / apply_ops; inspect, query_entities "
    "and render to look at the result."
)


def attach_instructions(document: str) -> str:
    return (
        "apeCAD draws structural intent in millimetres. This server is attached to a running "
        f"scratchpad: its one document is {document!r}, which a human may be editing too. "
        "Read list_ops for the op schemas, then apply_op / apply_ops with expect_revision; "
        "inspect, query_entities and render to look at the result. new_document, "
        "open_document and save_document are not available. DETACHED means the scratchpad "
        "stopped or restarted."
    )


def build_server(tools: ToolSet | None = None, *, instructions: str | None = None) -> Server:
    """An MCP server over one tool set (a fresh `LocalTools` unless given)."""
    local: ToolSet = tools if tools is not None else LocalTools()
    if instructions is None:
        instructions = (
            attach_instructions(local.document_id)
            if isinstance(local, AttachTools)
            else LOCAL_INSTRUCTIONS
        )

    async def list_tools(
        ctx: ServerRequestContext, params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        return types.ListToolsResult(
            tools=[
                types.Tool(name=t.name, description=t.description, input_schema=t.input_schema)
                for t in TOOLS.values()
            ]
        )

    async def call_tool(
        ctx: ServerRequestContext, params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        tool = TOOLS.get(params.name)
        if tool is None:
            raise MCPError(types.INVALID_PARAMS, f"unknown tool {params.name!r}")
        try:
            arguments = check_arguments(tool, params.arguments)
        except ArgumentProblem as exc:
            raise MCPError(types.INVALID_PARAMS, str(exc)) from None
        envelope = tool.call(local, arguments)
        if envelope.get("ok") is not True:
            log.info("%s failed: %s", tool.name, envelope.get("error"))
        return tool_result(tool.name, envelope)

    return Server(
        SERVER_NAME,
        version=apeCAD.__version__,
        instructions=instructions,
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


async def serve_stdio(tools: ToolSet) -> None:
    server = build_server(tools)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m apeCAD.mcp", description="apeCAD MCP server (stdio)"
    )
    target = parser.add_mutually_exclusive_group()
    target.add_argument(
        "--attach-port",
        type=int,
        default=None,
        metavar="N",
        help="attach to the scratchpad on 127.0.0.1:N instead of holding local documents",
    )
    target.add_argument(
        "--attach",
        default=None,
        metavar="URL",
        help="attach to the scratchpad at this loopback URL, e.g. http://127.0.0.1:8765",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="folder that relative paths resolve against; save_document and render's "
        "save_to must stay under it. When attaching, it must equal the scratchpad's root",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(name)s %(message)s"
    )
    root = Path(args.root) if args.root else None
    tools = attach_or_exit(args.attach, args.attach_port, root)
    if tools is None:
        log.info("serving %d tools over stdio (root: %s)", len(TOOLS), root or "cwd")
        anyio.run(serve_stdio, LocalTools(root))
    else:
        log.info("serving %d tools over stdio, attached to %s", len(TOOLS), tools.document_id)
        anyio.run(serve_stdio, tools)

