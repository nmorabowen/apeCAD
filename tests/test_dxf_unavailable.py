"""DXF without the `dxf` extra (ADR 0034): `import apeCAD` never imports ezdxf, and every
surface answers `UNAVAILABLE` instead of falling back. Runs in the core CI job too."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from apeCAD.agent import tools
from apeCAD.agent.session import Session
from apeCAD.document import Document
from apeCAD.render.dxf import DxfUnavailableError, export_dxf

SRC = Path(__file__).resolve().parents[1] / "src"


def test_import_apecad_does_not_import_ezdxf() -> None:
    code = (
        "import sys, apeCAD, apeCAD.agent.tools, apeCAD.render.dxf, apeCAD.scratchpad.server\n"
        "print(sorted(m for m in sys.modules if m == 'ezdxf' or m.startswith('ezdxf.')))\n"
    )
    env = dict(os.environ, PYTHONPATH=str(SRC))
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, env=env
    )
    assert out.stdout.strip() == "[]"


def test_without_the_extra_every_surface_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "ezdxf.filemanagement", None)  # import now fails
    document = Document()
    document.add_point(0.0, 0.0, 0.0)
    with pytest.raises(DxfUnavailableError) as caught:
        export_dxf(document)
    assert caught.value.code == "UNAVAILABLE" and "apeCAD[dxf]" in str(caught.value)
    envelope = tools.export_dxf(Session(document))
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "UNAVAILABLE"  # pyright: ignore[reportIndexIssue]
