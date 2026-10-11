"""The closed bar vocabulary (ADR 0024 P12) against the spec and against apeConcrete."""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path

import pytest

from apeCAD import DocumentError
from apeCAD.section.designations import DESIGNATIONS, designation_for, require_designation

REPO = Path(__file__).resolve().parents[1]
SPEC = REPO / "AProjects" / "specs" / "section-draft.md"
BARS_PY = Path("src") / "apeConcrete" / "rebar" / "bars.py"


def _spec_table() -> dict[str, float]:
    text = SPEC.read_text(encoding="utf-8")
    section = text.split("## Designation vocabulary (v1)", 1)[1].split("\n## ", 1)[0]
    rows = re.findall(r"^\| (Ø\d+) \| (\d+) \|$", section, flags=re.MULTILINE)
    return {name: float(diameter) for name, diameter in rows}


def _apeconcrete_bars_py() -> Path | None:
    candidates: list[Path] = []
    env = os.environ.get("APECONCRETE_SRC")
    if env:
        root = Path(env)
        # Accept the repo root, its src/ folder, or the bars.py file itself.
        candidates += [root, root / BARS_PY, root / "apeConcrete" / "rebar" / "bars.py"]
    # The main checkout sits beside apeConcrete; a worktree is three levels deeper.
    for parent in (REPO, *REPO.parents):
        candidates.append(parent.parent / "apeConcrete" / BARS_PY)
    return next((path for path in candidates if path.is_file()), None)


def _metric_bar_diameters(bars_py: Path) -> list[int]:
    """The integer tuple METRIC_BARS is built from, read from the source text."""
    for node in ast.walk(ast.parse(bars_py.read_text(encoding="utf-8"))):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        if not any(isinstance(t, ast.Name) and t.id == "METRIC_BARS" for t in targets):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Tuple) and inner.elts and all(
                isinstance(e, ast.Constant) and type(e.value) is int for e in inner.elts
            ):
                return [e.value for e in inner.elts if isinstance(e, ast.Constant)]
    raise AssertionError(f"no integer tuple behind METRIC_BARS in {bars_py}")


def test_vocabulary_equals_the_spec_table() -> None:
    table = _spec_table()
    assert len(table) == 11
    assert dict(DESIGNATIONS) == table
    assert list(DESIGNATIONS) == list(table)


def test_vocabulary_matches_apeconcrete_metric_bars() -> None:
    bars_py = _apeconcrete_bars_py()
    if bars_py is None:
        pytest.skip("apeConcrete source not found beside this repo or at $APECONCRETE_SRC")
    diameters = _metric_bar_diameters(bars_py)
    assert {f"Ø{float(d):g}": float(d) for d in diameters} == dict(DESIGNATIONS)


def test_spelling_is_canonical() -> None:
    for name, diameter in DESIGNATIONS.items():
        assert name == f"Ø{diameter:g}"


def test_designation_for() -> None:
    assert designation_for(16.0) == "Ø16"
    assert designation_for(8) == "Ø8"
    for bad in (36.0, 16.5, 0.0, -16.0):
        with pytest.raises(DocumentError, match="no bar of diameter"):
            designation_for(bad)


def test_require_designation() -> None:
    assert require_designation("Ø25", 25.0) == 25.0
    with pytest.raises(DocumentError, match="unknown bar designation"):
        require_designation("#5", 15.9)
    with pytest.raises(DocumentError, match="unknown bar designation"):
        require_designation("16mm", 16.0)
    with pytest.raises(DocumentError, match="unknown bar designation"):
        require_designation("Ø36", 36.0)
    with pytest.raises(DocumentError, match="not 20.0 mm"):
        require_designation("Ø16", 20.0)


def test_vocabulary_is_read_only() -> None:
    with pytest.raises(TypeError):
        DESIGNATIONS["Ø36"] = 36.0  # type: ignore[index]
