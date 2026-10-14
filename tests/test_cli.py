"""Stage S6: `python -m apeCAD.cli` against temp files (spec agent-surface-mcp §7, §9).

Exit status: 0 ok, 1 refusal or environment error, 2 bad argument.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from apeCAD.cli import main
from apeCAD.document import Document

SRC = Path(__file__).resolve().parents[1] / "src"
LINE = json.dumps({"start_id": {"xyz": [0, 0, 0]}, "end_id": {"xyz": [6000, 0, 0]}})


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, dict[str, Any]]:
    try:
        status = main(list(argv))
    except SystemExit as exc:  # argparse
        return int(exc.code or 0), {}
    out = capsys.readouterr().out
    return status, json.loads(out)


@pytest.fixture
def drawing(tmp_path: Path) -> Path:
    path = tmp_path / "draft.json"
    path.write_text(Document().to_json(), encoding="utf-8")
    return path


def test_ops(capsys: pytest.CaptureFixture[str]) -> None:
    status, envelope = _run(capsys, "ops")
    assert status == 0
    assert envelope["schema"] == "apeCAD.document.v1"
    assert "AddLine" in {op["name"] for op in envelope["ops"]}
    status, one = _run(capsys, "ops", "AddLine")
    assert status == 0
    assert [op["name"] for op in one["ops"]] == ["AddLine"]
    status, unknown = _run(capsys, "ops", "AddNothing")
    assert status == 2
    assert unknown["error"]["code"] == "UNKNOWN_OP"


def test_new_then_apply_writes_the_file_back(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    path = tmp_path / "sub" / "new.json"
    status, created = _run(capsys, "new", str(path))
    assert (status, created["revision"]) == (0, 0)
    status, again = _run(capsys, "new", str(path))
    assert (status, again["error"]["code"]) == (1, "IO_ERROR")

    status, applied = _run(capsys, "apply", str(path), "AddLine", LINE)
    assert status == 0
    assert applied["revision"] == 1
    assert applied["created_id"] is not None
    assert applied["path"] == str(path.resolve())
    assert [op["op"] for op in json.loads(path.read_text())["ops"]] == ["AddLine"]


def test_apply_a_batch(capsys: pytest.CaptureFixture[str], drawing: Path) -> None:
    point = {"op": "AddPoint", "params": {"x_mm": 0, "y_mm": 0, "z_mm": 0}}
    status, applied = _run(capsys, "apply", str(drawing), "-", json.dumps([point, point]))
    assert status == 0
    assert len(applied["results"]) == 2
    assert len(Document.from_json(drawing.read_text()).ops()) == 2


def test_apply_failures_leave_the_file_alone(
    capsys: pytest.CaptureFixture[str], drawing: Path, tmp_path: Path
) -> None:
    before = drawing.read_bytes()
    same = json.dumps({"start_id": {"xyz": [0, 0, 0]}, "end_id": {"xyz": [0, 0, 0]}})
    cases = [
        (("AddLine", same), 1, "REFUSED"),
        (("AddNothing", "{}"), 2, "UNKNOWN_OP"),
        (("AddLine", "{not json"), 2, "INVALID_ARGUMENT"),
        (("AddLine", json.dumps({"start_id": 1})), 2, "INVALID_ARGUMENT"),
    ]
    for (op, params), expected, code in cases:
        status, envelope = _run(capsys, "apply", str(drawing), op, params)
        assert (status, envelope["error"]["code"]) == (expected, code), envelope
    assert drawing.read_bytes() == before

    status, missing = _run(capsys, "apply", str(tmp_path / "nope.json"), "AddLine", LINE)
    assert (status, missing["error"]["code"]) == (1, "IO_ERROR")
    broken = tmp_path / "broken.json"
    broken.write_text("{]", encoding="utf-8")
    status, refused = _run(capsys, "inspect", str(broken))
    assert (status, refused["error"]["code"]) == (1, "REFUSED")


def test_inspect(capsys: pytest.CaptureFixture[str], drawing: Path) -> None:
    _run(capsys, "apply", str(drawing), "AddLine", LINE)
    status, envelope = _run(capsys, "inspect", str(drawing))
    assert status == 0
    assert envelope["ops"] == 1
    assert envelope["counts"]["line"] == 1
    assert envelope["extents_mm"] == {"min": [0, 0, 0], "max": [6000, 0, 0]}


def test_query(capsys: pytest.CaptureFixture[str], drawing: Path) -> None:
    _run(capsys, "apply", str(drawing), "AddLine", LINE)
    status, lines = _run(capsys, "query", str(drawing), "--kind", "line", "--detail", "full")
    assert status == 0
    assert lines["total"] == 1
    assert lines["items"][0]["kind"] == "line"
    status, near = _run(
        capsys, "query", str(drawing), "--window=-1,-1,-1,1,1,1", "--mode", "crossing"
    )
    assert (status, near["total"]) == (0, 2)  # the start point and the line through it
    status, paged = _run(capsys, "query", str(drawing), "--limit", "1")
    assert paged["next_cursor"] is not None
    for bad in (("--limit", "0"), ("--kind", "blob"), ("--window", "1,2"), ("--mode", "crossing")):
        status, envelope = _run(capsys, "query", str(drawing), *bad)
        assert (status, envelope["error"]["code"]) == (2, "INVALID_ARGUMENT"), bad


def test_render(capsys: pytest.CaptureFixture[str], drawing: Path, tmp_path: Path) -> None:
    _run(capsys, "apply", str(drawing), "AddLine", LINE)
    status, envelope = _run(capsys, "render", str(drawing), "--view", "top", "--size", "400x300")
    assert status == 0
    assert (envelope["width"], envelope["height"], envelope["view"]) == (400, 300, "top")
    assert envelope["svg"].startswith("<svg")

    out = tmp_path / "pics" / "top.svg"
    status, saved = _run(capsys, "render", str(drawing), "-o", str(out), "--show-ids")
    assert status == 0
    assert "svg" not in saved
    assert saved["path"] == str(out.resolve())
    assert out.read_text(encoding="utf-8").startswith("<svg")

    status, bad = _run(capsys, "render", str(drawing), "--size", "big")
    assert (status, bad["error"]["code"]) == (2, "INVALID_ARGUMENT")
    status, unknown_id = _run(capsys, "render", str(drawing), "--ids", "999")
    assert (status, unknown_id["error"]["code"]) == (2, "INVALID_ARGUMENT")


def test_a_bad_command_line_exits_2(capsys: pytest.CaptureFixture[str], drawing: Path) -> None:
    assert _run(capsys, "draw", str(drawing))[0] == 2
    assert _run(capsys, "apply", str(drawing))[0] == 2
    assert _run(capsys, "render", str(drawing), "--view", "bottom")[0] == 2


def test_runs_as_a_module(drawing: Path) -> None:
    env = dict(os.environ, PYTHONPATH=str(SRC))
    done = subprocess.run(
        [sys.executable, "-m", "apeCAD.cli", "apply", str(drawing), "AddLine", LINE],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["revision"] == 1
    refused = subprocess.run(
        [sys.executable, "-m", "apeCAD.cli", "apply", str(drawing), "AddNothing", "{}"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert refused.returncode == 2
    assert json.loads(refused.stdout)["error"]["code"] == "UNKNOWN_OP"
