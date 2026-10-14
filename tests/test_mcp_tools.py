"""Stage S3 without the SDK: `import apeCAD` stays free of `mcp`, and the tool table's
top-level argument check (spec agent-surface-mcp §2, §9)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from apeCAD.agent.mcp_tools import TOOLS, ArgumentProblem, check_arguments

SRC = Path(__file__).resolve().parents[1] / "src"


def test_import_apecad_does_not_import_mcp() -> None:
    code = (
        "import sys, apeCAD, apeCAD.agent, apeCAD.agent.mcp_tools, apeCAD.mcp\n"
        "leaked = sorted(m for m in sys.modules if m == 'mcp' or m.startswith(('mcp.', 'mcp_')))\n"
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
