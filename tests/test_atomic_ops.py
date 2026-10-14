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
from apeCAD.entities import LegSteel, Line
from apeCAD.geometry import XYZ
from apeCAD.ops import (
    AddCrosstie,
    AddFaceFromLines,
    AddHoop,
    AddLine,
    AddWallChain,
    AddWallLeg,
    ArrayLinear,
    ArrayPolar,
    BreakCrossing,
    ChamferCorner,
    Delete,
    FilletCorner,
    InsertNode,
    JoinPolyline,
    Mirror,
    PointAt,
    SetBarSize,
    SetCover,
    SetLegReinforcement,
    SetMaterial,
    SetTransverse,
    Sew,
    Simplify,
    TrimLine,
)

SAMPLES_PER_OP = 60

_FLOATS = (0.0, -1.0, 1e-9, 0.5, 250.0, 1000.0, 2000.0, -4000.0, 1e300, 1.7e308, math.nan, math.inf)
_COORDS = (0.0, -1.0, 0.5, 1000.0, 1e300)
_INTS = (-1, 0, 1, 2, 3)
_LABELS = (None, "fresh", "corner", "  ")
_NAMES = ("t", "group", "")
_DESIGNATIONS = ("Ø16", "Ø10", "Ø32", "#4", "16", "")
_MATERIALS = ("H30", "H35", "  ")
_HOOKS = ("135", "135-135", "135-90", "90-90", "180")


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
    # Section mode (ADR 0024): a face, a 2 x 3 bar cage, a hoop and a crosstie.
    corners = ((0.0, -800.0), (400.0, -800.0), (400.0, -200.0), (0.0, -200.0))
    doc.add_concrete_face([PointAt(XYZ(x, y, 0.0)) for x, y in corners], "H30")
    bars = [
        doc.add_bar(x, y, "Ø16").entity_id
        for x in (60.0, 340.0)
        for y in (-740.0, -500.0, -260.0)
    ]
    hoop = doc.add_hoop(bars, "Ø10", 100.0)
    doc.add_crosstie(bars[1], bars[4], "Ø10", 100.0)
    doc.tag("cage", (hoop.entity_id,))
    # Stage C2: an L wall chain (a face and 2 legs), a free leg and a cover guide.
    axis = [PointAt(XYZ(x, y, 0.0)) for x, y in ((1000.0, -800.0), (2500.0, -800.0), (2500.0, 0.0))]
    steel = LegSteel("Ø10", 200.0, 2)
    wall = doc.add_wall_chain(axis, 250.0, "H30", horizontal=steel, label="wall")
    doc.set_cover(wall.entity_id, 40.0, 10.0, 20.0)
    outline = doc.add_section_outline(
        [PointAt(XYZ(x, y, 0.0)) for x, y in ((3000.0, -800.0), (3300.0, -800.0), (3300.0, 0.0))],
        "H30",
    )
    doc.add_wall_leg(
        PointAt(XYZ(3100.0, -700.0, 0.0)), PointAt(XYZ(3100.0, -100.0, 0.0)), 200.0,
        outline.entity_id,
    )
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
    if name in ("designation", "material", "hooks"):
        if optional and rng.random() < 0.4:
            return None
        pool = {"designation": _DESIGNATIONS, "material": _MATERIALS, "hooks": _HOOKS}[name]
        return rng.choice(pool)
    vertex = _mentions(hint, PointAt)
    if name == "ring" and rng.random() < 0.5:
        return None
    if name == "leg_ids" and rng.random() < 0.7:
        return ()  # ids the handler allocates, not references
    if name.endswith("_ids") or name == "ring":
        pick = _vertex if vertex else _pick_id
        return tuple(pick(rng, ids, point_ids) for _ in range(rng.randint(0, 5)))
    if name.endswith("_id"):
        if optional and rng.random() < 0.7:
            return None  # an id the handler allocates, not a reference
        return _vertex(rng, ids, point_ids) if vertex else _pick_id(rng, ids, point_ids)
    if name in ("copies", "count", "curtains"):
        return rng.choice(_INTS)
    if name == "horizontal":  # a wall leg's web steel (ADR 0024 P4), or none
        if rng.random() < 0.4:
            return None
        return LegSteel(rng.choice(_DESIGNATIONS), rng.choice(_FLOATS), rng.choice(_INTS))
    if get_origin(hint) is tuple:  # a wall chain's thicknesses: one, or one per segment
        return tuple(rng.choice(_FLOATS) for _ in range(rng.choice((0, 1, 1, 1, 2, 3))))
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


def _section_targeted_ops(doc: Document) -> list[object]:
    """Section ops on the fixture's real bars, face, hoop and crosstie (ADR 0024)."""
    face = doc.concrete_faces()[0].entity_id
    bars = [bar.entity_id for bar in doc.bars()]
    hoop = doc.hoops()[0].entity_id
    tie = doc.crossties()[0].entity_id
    wall = doc.concrete_faces()[1].entity_id
    leg = doc.wall_legs()[0]
    guide = doc.cover_guides()[0].entity_id
    axis = (PointAt(XYZ(5000.0, 0.0, 0.0)), PointAt(XYZ(5000.0, 2000.0, 0.0)))
    return [
        AddHoop(bar_ids=tuple(bars), designation="Ø12", spacing_mm=80.0),
        AddHoop(bar_ids=tuple(bars[:3:2]), designation="Ø12", spacing_mm=80.0),  # collinear
        AddHoop(bar_ids=(bars[0], bars[1], face), designation="Ø12", spacing_mm=80.0),
        AddCrosstie(bar_a_id=bars[0], bar_b_id=bars[5], designation="Ø10", spacing_mm=100.0),
        AddCrosstie(bar_a_id=bars[0], bar_b_id=face, designation="Ø10", spacing_mm=100.0),
        SetBarSize(entity_ids=(bars[0], bars[3]), designation="Ø25"),
        SetBarSize(entity_ids=(bars[0], hoop), designation="Ø25"),
        SetMaterial(entity_ids=(face,), material="H40"),
        SetMaterial(entity_ids=(face, bars[0]), material="H40"),
        SetTransverse(entity_ids=(hoop, tie), designation="Ø12", spacing_mm=75.0),
        SetTransverse(entity_ids=(hoop,), hooks="135-90"),
        SetTransverse(entity_ids=(tie,), hooks="135-90"),
        Delete(entity_ids=(bars[1],)),
        Delete(entity_ids=(hoop,)),
        Mirror(entity_ids=(hoop, face), ax_mm=0.0, ay_mm=0.0, bx_mm=0.0, by_mm=1.0),
        ArrayLinear(entity_ids=(hoop, tie), dx_mm=1000.0, dy_mm=0.0, copies=2),
        ArrayPolar(entity_ids=(face, hoop), origin_x_mm=0.0, origin_y_mm=0.0, count=4),
        AddLine(start_id=doc.bars()[0].point_id, end_id=1),
        Sew(entity_ids=(bars[0], face), tolerance_mm=1e6),
        # Stage C2: wall chains, legs, leg steel and cover.
        AddWallChain(point_ids=axis, thickness_mm=(300.0,), material="H30"),
        AddWallChain(
            point_ids=axis, thickness_mm=(300.0,), material="H30", leg_ids=(leg.entity_id,)
        ),
        AddWallChain(point_ids=axis, thickness_mm=(1e6,), material="H30"),  # fine, just wide
        AddWallChain(point_ids=(*axis, axis[0]), thickness_mm=(300.0,), material="H30"),
        AddWallLeg(start_id=leg.start_id, end_id=leg.start_id, thickness_mm=200.0, face_id=wall),
        AddWallLeg(start_id=leg.start_id, end_id=leg.end_id, thickness_mm=200.0, face_id=hoop),
        SetLegReinforcement(leg_id=leg.entity_id, designation="Ø12", spacing_mm=150.0, curtains=1),
        SetLegReinforcement(leg_id=wall, designation="Ø12", spacing_mm=150.0, curtains=1),
        SetCover(face_id=wall, cover_mm=50.0, tie_diameter_mm=12.0, bar_diameter_mm=25.0),
        SetCover(face_id=wall, cover_mm=50.0, tie_diameter_mm=0.0, bar_diameter_mm=25.0,
                 entity_id=guide + 1000),
        SetCover(face_id=face, cover_mm=1e5, tie_diameter_mm=10.0, bar_diameter_mm=20.0),
        Delete(entity_ids=(wall,)),
        Delete(entity_ids=(leg.start_id,)),
        Mirror(entity_ids=(wall,), ax_mm=0.0, ay_mm=0.0, bx_mm=0.0, by_mm=1.0),
        ArrayLinear(entity_ids=(leg.entity_id, guide), dx_mm=0.0, dy_mm=5000.0, copies=2),
        Sew(entity_ids=(leg.entity_id,), tolerance_mm=1e6),
    ]


@pytest.mark.parametrize("index", range(35))
def test_section_edge_cases_are_atomic(index: int) -> None:
    doc = _fixture()
    op = _section_targeted_ops(doc)[index]
    json_before = doc.to_json()
    live_before = _snapshot(doc)
    try:
        doc.apply(op)  # type: ignore[arg-type]
    except DocumentError:
        assert doc.to_json() == json_before
        assert _snapshot(doc) == live_before
    else:
        _assert_live_equals_replay(doc)
