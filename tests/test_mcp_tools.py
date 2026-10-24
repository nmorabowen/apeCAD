"""Stage S3 without the SDK: `import apeCAD` stays free of `mcp`, and the tool table's
top-level argument check (spec agent-surface-mcp §2, §9)."""

from __future__ import annotations

import base64
import json
import os
import struct
import subprocess
import sys
import types
from pathlib import Path
from typing import cast

import pytest

from apeCAD.agent.mcp_tools import TOOLS, ArgumentProblem, check_arguments
from apeCAD.agent.session import Session
from apeCAD.agent.tools import apecad_render, render
from apeCAD.cli import main as cli_main
from apeCAD.document import Document
from test_render import _fake_png  # pyright: ignore[reportPrivateUsage]

SRC = Path(__file__).resolve().parents[1] / "src"


def test_import_apecad_does_not_import_mcp_or_resvg() -> None:
    code = (
        "import sys, apeCAD, apeCAD.agent, apeCAD.agent.mcp_tools, apeCAD.mcp, apeCAD.render\n"
        "leaked = sorted(\n"
        "    m for m in sys.modules\n"
        "    if m in ('mcp', 'resvg_py') or m.startswith(('mcp.', 'mcp_', 'resvg_py.'))\n"
        ")\n"
        "print(leaked)\n"
    )
    env = dict(os.environ, PYTHONPATH=str(SRC))
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, env=env
    )
    assert out.stdout.strip() == "[]"


def test_check_arguments_is_the_top_level_schema() -> None:
    apply_op = TOOLS["apply_op"]
    assert check_arguments(apply_op, {"document": "doc-1", "op": "AddLine"}) == {
        "document": "doc-1",
        "op": "AddLine",
    }
    with pytest.raises(ArgumentProblem, match="needs"):
        check_arguments(apply_op, {"op": "AddLine"})
    with pytest.raises(ArgumentProblem, match="extra"):
        check_arguments(apply_op, {"document": "doc-1", "op": "AddLine", "colour": "red"})
    with pytest.raises(ArgumentProblem, match="wrong type"):
        check_arguments(apply_op, {"document": 1, "op": "AddLine"})
    with pytest.raises(ArgumentProblem, match="wrong type"):
        check_arguments(TOOLS["render"], {"document": "doc-1", "view": "side"})


def test_apecad_render_png_unavailable_and_rasterized(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    doc = Document()
    a = doc.add_point(0.0, 0.0, 0.0)
    b = doc.add_point(1000.0, 0.0, 0.0)
    doc.add_line(a.entity_id, b.entity_id)
    session = Session(doc)

    monkeypatch.setitem(sys.modules, "resvg_py", None)
    missing = apecad_render(session, format="png")
    assert missing["ok"] is False
    error = cast(dict[str, object], missing["error"])
    assert error["code"] == "UNAVAILABLE"
    assert "apeCAD[png]" in str(error["message"])
    assert "svg" not in missing

    fake = types.ModuleType("resvg_py")
    fake.svg_to_bytes = _fake_png  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "resvg_py", fake)
    rendered = render(
        session, root=tmp_path, format="png", view="top", width=400, height=300, save_to="out.png"
    )
    assert rendered["ok"] is True
    assert (rendered["width"], rendered["height"], rendered["view"]) == (400, 300, "top")
    assert "svg" not in rendered
    png_bytes = base64.b64decode(cast(str, rendered["png"]))
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert struct.unpack(">II", png_bytes[16:24]) == (400, 300)
    assert (tmp_path / "out.png").read_bytes() == png_bytes

    draft_path = tmp_path / "draft.json"
    draft_path.write_text(doc.to_json(), encoding="utf-8")
    out_png = tmp_path / "cli.png"
    status = cli_main(["render", str(draft_path), "-o", str(out_png), "--size", "256x128"])
    envelope = json.loads(capsys.readouterr().out)
    assert status == 0 and envelope["ok"] is True
    assert "png" not in envelope and envelope["path"] == str(out_png.resolve())
    assert struct.unpack(">II", out_png.read_bytes()[16:24]) == (256, 128)

    status = cli_main(["render", str(draft_path), "--format", "png", "--size", "160x120"])
    inline = json.loads(capsys.readouterr().out)
    assert status == 0 and inline["ok"] is True and "svg" not in inline
    inline_bytes = base64.b64decode(cast(str, inline["png"]))
    assert struct.unpack(">II", inline_bytes[16:24]) == (160, 120)

    monkeypatch.setitem(sys.modules, "resvg_py", None)
    status = cli_main(["render", str(draft_path), "--format", "png"])
    refused = json.loads(capsys.readouterr().out)
    assert status == 1 and refused["ok"] is False
    assert cast(dict[str, object], refused["error"])["code"] == "UNAVAILABLE"

