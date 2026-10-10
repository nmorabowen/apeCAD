"""Structural guards (ADR 0023): no god files, one handler per op, imports point down."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import get_args

from apeCAD.draft.dispatch import HANDLERS
from apeCAD.ops import Op

SRC = Path(__file__).resolve().parents[1] / "src" / "apeCAD"

# Every source file stays at or under this many lines. Split by responsibility before it.
MAX_LINES = 600

# Files that predate the budget. A ceiling may only go down: when a file shrinks, lower its
# number here in the same PR; when it is under MAX_LINES, delete its row. Never raise one.
LEGACY_CEILINGS: dict[str, int] = {
    "scratchpad/static/app.js": 4985,
}

# Inside apeCAD.draft a module may import only modules of a strictly lower rank.
DRAFT_RANK: dict[str, int] = {
    "state": 0,
    "topology": 1,
    "create": 2,
    "edit": 3,
    "transform": 3,
    "meta": 3,
    "dispatch": 4,
}

_SOURCE_SUFFIXES = {".py", ".js", ".html", ".css"}


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _source_files() -> list[Path]:
    return sorted(
        path
        for path in SRC.rglob("*")
        if path.suffix in _SOURCE_SUFFIXES and "__pycache__" not in path.parts
    )


def _apecad_imports(path: Path) -> set[str]:
    """Dotted apeCAD module names a Python file imports, expanding `from pkg import mod`."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names if alias.name.startswith("apeCAD"))
        elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("apeCAD"):
            module = node.module or ""
            found.add(module)
            found.update(f"{module}.{alias.name}" for alias in node.names)
    return found


def test_source_files_stay_under_the_line_budget() -> None:
    over: list[str] = []
    for path in _source_files():
        rel = path.relative_to(SRC).as_posix()
        lines = _line_count(path)
        ceiling = LEGACY_CEILINGS.get(rel, MAX_LINES)
        if lines > ceiling:
            over.append(f"{rel}: {lines} lines > {ceiling}; split it by responsibility")
    assert not over, "\n".join(over)


def test_legacy_ceilings_ratchet_down() -> None:
    stale: list[str] = []
    for rel, ceiling in LEGACY_CEILINGS.items():
        path = SRC / rel
        if not path.is_file():
            stale.append(f"{rel}: gone; delete its row")
            continue
        lines = _line_count(path)
        if lines <= MAX_LINES:
            stale.append(f"{rel}: {lines} lines is within MAX_LINES; delete its row")
        elif lines < ceiling:
            stale.append(f"{rel}: shrank to {lines}; lower its ceiling from {ceiling}")
    assert not stale, "\n".join(stale)


def test_every_op_has_exactly_one_handler() -> None:
    op_types = set(get_args(Op))
    assert set(HANDLERS) == op_types


def test_every_op_has_a_codec_entry() -> None:
    codec = (SRC / "ops" / "codec.py").read_text(encoding="utf-8")
    missing = [
        op_type.__name__
        for op_type in get_args(Op)
        if f'"op": "{op_type.__name__}"' not in codec
        or f'kind == "{op_type.__name__}"' not in codec
    ]
    assert not missing, f"ops without a to_dict and a parse branch: {missing}"


def test_draft_imports_point_down() -> None:
    violations: list[str] = []
    for name, rank in DRAFT_RANK.items():
        for imported in _apecad_imports(SRC / "draft" / f"{name}.py"):
            if imported.startswith("apeCAD.document") or imported.startswith(
                "apeCAD.scratchpad"
            ):
                violations.append(f"draft.{name} imports {imported}")
            parts = imported.split(".")
            if len(parts) == 3 and parts[1] == "draft" and parts[2] in DRAFT_RANK:
                if DRAFT_RANK[parts[2]] >= rank:
                    violations.append(f"draft.{name} imports same-or-higher draft.{parts[2]}")
    assert not violations, "\n".join(violations)


def test_draft_rank_covers_every_module() -> None:
    modules = {path.stem for path in (SRC / "draft").glob("*.py") if path.stem != "__init__"}
    assert modules == set(DRAFT_RANK)


def test_core_never_imports_the_scratchpad() -> None:
    offenders = [
        path.relative_to(SRC).as_posix()
        for path in SRC.rglob("*.py")
        if "scratchpad" not in path.relative_to(SRC).parts
        and path.name != "__main__.py"  # `python -m apeCAD` launches the scratchpad
        and any(name.startswith("apeCAD.scratchpad") for name in _apecad_imports(path))
    ]
    assert not offenders, f"the document layer must not depend on the web client: {offenders}"
