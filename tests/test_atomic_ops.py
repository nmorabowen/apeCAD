"""Ops are atomic (ADR 0027): a refused op changes nothing, an accepted one replays."""

from __future__ import annotations

import math
import random
import types
import zlib
from dataclasses import fields
from typing import Any, Union, cast, get_args, get_origin, get_type_hints

import pytest

from apeCAD import Document, DocumentError
from apeCAD.draft.dispatch import HANDLERS
from apeCAD.draft.state import DraftState
from apeCAD.entities import Line
from apeCAD.geometry import XYZ
from apeCAD.ops import (
    AddFaceFromLines,
    BreakCrossing,
    ChamferCorner,
    FilletCorner,
    InsertNode,
    JoinPolyline,
    PointAt,
    Simplify,
    TrimLine,
)

SAMPLES_PER_OP = 60

_FLOATS = (0.0, -1.0, 1e-9, 0.5, 250.0, 1000.0, 2000.0, -4000.0, 1e300, 1.7e308, math.nan, math.inf)
_COORDS = (0.0, -1.0, 0.5, 1000.0, 1e300)
_INTS = (-1, 0, 1, 2, 3)
_LABELS = (None, "fresh", "corner", "  ")
_NAMES = ("t", "group", "")


def _snapshot(document: Document) -> tuple[object, ...]:
    state: DraftState = document._state  # pyright: ignore[reportPrivateUsage]
    tags = {name: frozenset(members) for name, members in state.tags.items()}
    return (state.next_id, dict(state.entities), dict(state.labels), tags)


def _assert_live_equals_replay(document: Document) -> None:
    assert _snapshot(Document.from_json(document.to_json())) == _snapshot(document)


def _fixture() -> Document:
    """One of every entity kind, a label and a tag, so hostile ids hit real targets."""
    doc = Document()
    a = doc.add_point(0.0, 0.0, 0.0, label="corner").entity_id
    b = doc.add_point(4000.0, 0.0, 0.0).entity_id
    c = doc.add_point(4000.0, 3000.0, 0.0).entity_id
    d = doc.add_point(0.0, 3000.0, 0.0).entity_id
    for start, end in ((a, b), (b, c), (c, d), (d, a), (a, c), (b, d)):
        doc.add_line(start, end)
    face = doc.add_face((a, b, c, d))
    doc.extrude(face.entity_id, 500.0)
    e = doc.add_point(6000.0, 0.0, 0.0).entity_id
    f = doc.add_point(7000.0, 1000.0, 0.0).entity_id
    g = doc.add_point(8000.0, 0.0, 0.0).entity_id
    h = doc.add_point(9000.0, 1000.0, 0.0).entity_id
    doc.add_polyline((e, f, g))
    m = doc.add_point(2000.0, 3000.0, 0.0).entity_id
    doc.add_polyline((c, m, d))  # collinear: Simplify can drop m
    doc.add_arc(e, f, g)
    doc.add_bezier((e, f, g, h))
    doc.add_circle(h, 300.0)
    doc.add_ellipse(e, 200.0, 100.0)
    doc.add_box((-5000.0, 0.0, 0.0), (1000.0, 1000.0, 1000.0))
    doc.tag("group", (a, face.entity_id))
    return doc


def _pick_id(rng: random.Random, ids: list[int], point_ids: list[int]) -> int:
    """Mostly real ids, often points, sometimes unknown or invalid ones."""
    roll = rng.random()
    if roll < 0.5:
        return rng.choice(point_ids)
    if roll < 0.85:
        return rng.choice(ids)
    return rng.choice((0, -1, 999))


def _mentions(hint: Any, target: type) -> bool:
    return hint is target or any(_mentions(arg, target) for arg in get_args(hint))


def _vertex(rng: random.Random, ids: list[int], point_ids: list[int]) -> object:
    """A vertex reference (ADR 0030): mostly ids, else coordinates, some on fixture points."""
    if rng.random() < 0.5:
        return _pick_id(rng, ids, point_ids)
    coords = _COORDS + (4000.0, 3000.0)
    xyz = XYZ(rng.choice(coords), rng.choice(coords), rng.choice((0.0, 0.5, 500.0)))
    return PointAt(xyz, _pick_id(rng, ids, point_ids) if rng.random() < 0.2 else None)


def _value(
    rng: random.Random, name: str, hint: Any, ids: list[int], point_ids: list[int]
) -> object:
    optional = get_origin(hint) in (Union, types.UnionType) and type(None) in get_args(hint)
    if hint is XYZ:
        return XYZ(rng.choice(_COORDS), rng.choice(_COORDS), rng.choice(_COORDS))
    if name == "label":
        return rng.choice(_LABELS)
    if name == "name":
        return rng.choice(_NAMES)
    if name == "closed":
        return rng.choice((False, True))
    vertex = _mentions(hint, PointAt)
    if name == "ring" and rng.random() < 0.5:
        return None
    if name.endswith("_ids") or name == "ring":
        pick = _vertex if vertex else _pick_id
        return tuple(pick(rng, ids, point_ids) for _ in range(rng.randint(0, 5)))
    if name.endswith("_id"):
        if optional and rng.random() < 0.7:
            return None  # an id the handler allocates, not a reference
        return _vertex(rng, ids, point_ids) if vertex else _pick_id(rng, ids, point_ids)
    if name in ("copies", "count"):
        return rng.choice(_INTS)
    return rng.choice(_FLOATS)


def _hostile_ops(
    op_type: type[object], ids: list[int], point_ids: list[int], seed: int
) -> list[object]:
    rng = random.Random(seed)
    hints = get_type_hints(op_type)
    built: list[object] = []
    for _ in range(SAMPLES_PER_OP * 4):
        kwargs = {
            f.name: _value(rng, f.name, hints[f.name], ids, point_ids) for f in fields(op_type)
        }
        try:
            built.append(op_type(**kwargs))
        except DocumentError:
            continue  # refused by __post_init__; never reaches a handler
        if len(built) == SAMPLES_PER_OP:
            break
    return built


def test_sew_refusal_leaves_live_document_equal_to_its_log() -> None:
    doc = Document()
    p1 = doc.add_point(0.0, 0.0, 0.0).entity_id
    p2 = doc.add_point(1000.0, 0.0, 0.0).entity_id
    p3 = doc.add_point(1000.0, 0.5, 0.0).entity_id
    face = doc.add_face((p1, p2, p3))
    q1 = doc.add_point(0.2, 0.0, 0.0).entity_id
    q2 = doc.add_point(-3000.0, 0.0, 0.0).entity_id
    line = doc.add_line(q1, q2)
    points_before = doc.points()
    json_before = doc.to_json()

    with pytest.raises(DocumentError, match="collapse a face"):
        doc.sew([line.entity_id, face.entity_id])

    assert doc.points() == points_before
    assert len(doc.points()) == 5
    assert doc.to_json() == json_before
    _assert_live_equals_replay(doc)


def test_refused_redo_keeps_the_redo_stack() -> None:
    doc = Document()
    doc.add_point(0.0, 0.0, 0.0, label="a")
    doc.undo()
    doc._redo.append(doc._redo[-1])  # pyright: ignore[reportPrivateUsage]
    doc.redo()
    with pytest.raises(DocumentError):
        doc.redo()  # same id twice: refused
    assert len(doc._redo) == 1  # pyright: ignore[reportPrivateUsage]
    _assert_live_equals_replay(doc)


@pytest.mark.parametrize("op_type", list(HANDLERS), ids=lambda t: t.__name__)
def test_hostile_params_are_atomic(op_type: type[object]) -> None:
    doc = _fixture()
    ids = sorted(e.entity_id for e in _all_entities(doc))
    point_ids = [p.entity_id for p in doc.points()]
    ops = _hostile_ops(op_type, ids, point_ids, seed=zlib.crc32(op_type.__name__.encode()))
    assert ops, f"no constructible {op_type.__name__} sample"
    for op in ops:
        json_before = doc.to_json()
        live_before = _snapshot(doc)
        try:
            doc.apply(op)  # type: ignore[arg-type]
        except DocumentError:
            assert doc.to_json() == json_before, op
            assert _snapshot(doc) == live_before, op
        else:
            _assert_live_equals_replay(doc)


def _all_entities(doc: Document) -> list[Any]:
    state: DraftState = doc._state  # pyright: ignore[reportPrivateUsage]
    return list(state.entities.values())


def _targeted_ops(doc: Document) -> list[object]:
    """Ops that need exact geometry, which random sampling never hits."""
    ab, bc, cd, da, ac, bd = (line.entity_id for line in doc.lines()[:6])
    a, b, c = (cast(Line, doc.entity(line)).start_id for line in (ab, bc, cd))
    face = doc.faces()[0].entity_id
    polyline, straight = (p.entity_id for p in doc.polylines()[:2])
    return [
        InsertNode(target_id=ab, x_mm=2000.0, y_mm=0.0),
        InsertNode(target_id=ab, x_mm=0.0, y_mm=0.0),
        InsertNode(target_id=face, x_mm=4000.0, y_mm=1500.0),
        TrimLine(line_id=ac, keep_id=a, x_mm=2000.0, y_mm=1500.0),
        TrimLine(line_id=ac, keep_id=999, x_mm=2000.0, y_mm=1500.0),
        BreakCrossing(line_a_id=ac, line_b_id=bd),
        BreakCrossing(line_a_id=ab, line_b_id=cd),
        AddFaceFromLines(line_ids=(ab, bc, cd, da)),
        AddFaceFromLines(line_ids=(ab, bc, ac, bd)),
        JoinPolyline(entity_ids=(ab, bc)),
        JoinPolyline(entity_ids=(ab, cd)),
        ChamferCorner(target_id=face, vertex_id=b, distance_mm=250.0),
        ChamferCorner(target_id=face, vertex_id=b, distance_mm=1e9),
        FilletCorner(target_id=face, vertex_id=c, radius_mm=250.0),
        FilletCorner(target_id=face, vertex_id=c, radius_mm=1e9),
        Simplify(entity_ids=(polyline, face)),
        Simplify(entity_ids=(straight,)),
    ]


@pytest.mark.parametrize("index", range(17))
def test_targeted_edge_cases_are_atomic(index: int) -> None:
    doc = _fixture()
    op = _targeted_ops(doc)[index]
    json_before = doc.to_json()
    live_before = _snapshot(doc)
    try:
        doc.apply(op)  # type: ignore[arg-type]
    except DocumentError:
        assert doc.to_json() == json_before
        assert _snapshot(doc) == live_before
    else:
        _assert_live_equals_replay(doc)
