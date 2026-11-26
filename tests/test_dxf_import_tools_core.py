"""IMP-1b (ADR 0042) without the extras: UNAVAILABLE on every surface, and the parity listing.

Runs in CI's `core` job, where ezdxf is not installed, so `import_dxf` answers `UNAVAILABLE`
as it is. In the gate legs ezdxf's loader is hidden the way `test_dxf_unavailable.py` hides
it. The parity listing checks that the tool is on every surface and in every listing the repo
keeps: the MCP table, the local and attach tool sets, the CLI, the spec and AGENTS.md.
"""

from __future__ import annotations

import base64
import importlib.util
import inspect
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from apeCAD.agent import tools
from apeCAD.agent.attach import AttachTools
from apeCAD.agent.local import LocalTools
from apeCAD.agent.mcp_tools import TOOLS, ToolSet
from apeCAD.cli import build_parser
from apeCAD.cli import main as cli_main

REPO = Path(__file__).resolve().parents[1]
ANY_BYTES = b"0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n"


def test_without_the_extra_every_surface_is_unavailable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    if importlib.util.find_spec("ezdxf") is not None:
        monkeypatch.setitem(sys.modules, "ezdxf.filemanagement", None)  # import now fails
    (tmp_path / "in.dxf").write_bytes(ANY_BYTES)
    b64 = base64.b64encode(ANY_BYTES).decode("ascii")
    envelopes: list[dict[str, Any]] = [
        tools.import_dxf(data=b64),
        tools.import_dxf(tmp_path, False, path="in.dxf"),
        LocalTools(tmp_path).import_dxf(path="in.dxf"),
        AttachTools("http://127.0.0.1:9", 0, tmp_path).import_dxf(path="in.dxf"),
        TOOLS["import_dxf"].call(LocalTools(tmp_path), {"data": b64}),
    ]
    capsys.readouterr()
    assert cli_main(["import-dxf", str(tmp_path / "in.dxf")]) == 1
    envelopes.append(json.loads(capsys.readouterr().out))
    for envelope in envelopes:
        assert envelope["ok"] is False
        assert envelope["error"]["code"] == "UNAVAILABLE"
        assert "apeCAD[dxf]" in envelope["error"]["message"]
        assert "seed" not in envelope and "revision" not in envelope


def test_bad_arguments_are_named_before_the_extra_is_needed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The arguments are checked before any byte is read or decoded, so a core install names
    them too, and a bad argument with a missing file is the argument, not `IO_ERROR`."""
    monkeypatch.setitem(sys.modules, "ezdxf.filemanagement", None)
    b64 = base64.b64encode(ANY_BYTES).decode("ascii")
    want = {
        "code": "INVALID_ARGUMENT",
        "message": "dxf units: must be one of in, ft, mm, cm, m, got 'furlong'",
    }
    assert tools.import_dxf(data=b64, units="furlong")["error"] == want
    assert tools.import_dxf(data="not base64!", units="furlong")["error"] == want
    missing = LocalTools(tmp_path).import_dxf(path="none.dxf", units="furlong")
    assert missing["error"] == want


# --- the parity listing --------------------------------------------------------------------


def _methods(cls: type) -> set[str]:
    return {name for name, _ in inspect.getmembers(cls, inspect.isfunction)}


def test_every_mcp_tool_is_a_method_of_every_tool_set() -> None:
    assert "import_dxf" in TOOLS
    for cls in (ToolSet, LocalTools, AttachTools):
        assert set(TOOLS) <= _methods(cls), cls.__name__


def test_the_import_tool_is_in_every_listing() -> None:
    """The CLI, the spec's tool and CLI sections, the coupling map and AGENTS.md."""
    sub = next(a for a in build_parser()._actions if a.dest == "command")  # pyright: ignore[reportPrivateUsage]
    assert "import-dxf" in sub.choices  # pyright: ignore[reportOperatorIssue]
    spec = (REPO / "AProjects" / "specs" / "agent-surface-mcp.md").read_text(encoding="utf-8")
    assert "### `import_dxf`" in spec
    assert "python -m apeCAD.cli import-dxf FILE" in spec
    headings = [line for line in spec.splitlines() if line.startswith("### ")]
    for name in TOOLS:  # each tool has its §4 heading
        assert any(f"`{name}`" in heading for heading in headings), name
    agents = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    assert "import-dxf" in agents and "import_dxf" in agents
    coupling = (REPO / "AProjects" / "memory" / "coupling-map.md").read_text(encoding="utf-8")
    assert "import_dxf" in coupling
