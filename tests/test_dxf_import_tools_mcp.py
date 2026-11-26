"""IMP-1b (ADR 0042) over the MCP SDK: the `import_dxf` result body is the reader's answer.

Needs the `mcp` and `dxf` extras. The SDK's in-memory client calls the served tool; its
structured content and its text block must be the envelope the reader's own seed and report
(or refusal) make, byte for byte, on the v2 round trips and on every refusal of
`test_dxf_import_tools.REFUSALS`.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("ezdxf")
pytest.importorskip("mcp", reason="the mcp extra is not installed")

from mcp import Client  # noqa: E402

from _section_fixtures_v2 import BUILDERS_V2  # noqa: E402
from apeCAD.agent.local import LocalTools  # noqa: E402
from apeCAD.agent.mcp import build_server  # noqa: E402
from apeCAD.render.dxf import export_dxf  # noqa: E402
from test_dxf_import_tools import REFUSALS, expected  # noqa: E402

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _both(client: Client, data: bytes, kwargs: dict[str, object], path: str) -> list[Any]:
    by_data = await client.call_tool(
        "import_dxf", {"data": base64.b64encode(data).decode("ascii"), **kwargs}
    )
    by_path = await client.call_tool("import_dxf", {"path": path, **kwargs})
    return [by_data, by_path]


def _check(result: Any, want: dict[str, object]) -> None:
    assert result.is_error is (want["ok"] is not True)
    assert json.dumps(result.structured_content) == json.dumps(want)
    assert result.content[0].text == json.dumps(want, separators=(",", ":"))


async def test_the_mcp_body_is_the_readers_seed_and_report(tmp_path: Path) -> None:
    async with Client(build_server(LocalTools(tmp_path))) as client:
        listed = await client.list_tools()
        assert "import_dxf" in {tool.name for tool in listed.tools}
        for name in sorted(BUILDERS_V2):
            data = export_dxf(BUILDERS_V2[name]()).dxf.encode("utf-8")
            (tmp_path / f"{name}.dxf").write_bytes(data)
            want = expected(data, {})
            assert want["ok"] is True, name
            for result in await _both(client, data, {}, f"{name}.dxf"):
                _check(result, want)


async def test_every_refusal_reaches_the_mcp_body_by_name(tmp_path: Path) -> None:
    async with Client(build_server(LocalTools(tmp_path))) as client:
        for name in sorted(REFUSALS):
            build, reason, names, kwargs = REFUSALS[name]
            data = build()
            (tmp_path / f"{name}.dxf").write_bytes(data)
            want = expected(data, kwargs)
            message: Any = want["error"]
            assert message["message"].startswith(f"dxf {reason}: ") and names in str(message)
            for result in await _both(client, data, kwargs, f"{name}.dxf"):
                _check(result, want)
