from __future__ import annotations

import tomllib
from pathlib import Path

import apeCAD

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_version_is_present() -> None:
    # 0.1.0: the first writer of apeCAD.section-draft v1 (ADR 0025 decision 5, P13).
    assert apeCAD.__version__ == "0.1.0"


def test_version_matches_pyproject() -> None:
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    assert project["version"] == apeCAD.__version__
