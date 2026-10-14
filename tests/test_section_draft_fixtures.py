"""Stage C4 fixtures (ADR 0025 decision 8): they match their builders and the spec field table."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import cast

import pytest

from _section_fixtures import (
    BUILDERS,
    fixture_draft,
    fixture_path,
    write_fixtures,
)
from apeCAD.section.designations import DESIGNATIONS
from apeCAD.section.draft import (
    SECTION_LISTS,
)
from apeCAD.section.geometry import convex_hull_ccw, is_simple, signed_area
from apeCAD.section.lint import LINT_CODES

SPEC = Path(__file__).resolve().parents[1] / "AProjects" / "specs" / "section-draft.md"
CONTRACT_SHA256 = "8ee75d0ee7d4054a575e0f4d669872c828057ba6ebdfa4b8355d87f454a1181f"
NAMES = sorted(BUILDERS)

Json = dict[str, object]


def _load(name: str) -> Json:
    return cast(Json, json.loads(fixture_path(name).read_text(encoding="utf-8")))


def _obj(value: object) -> Json:
    assert isinstance(value, dict)
    return cast(Json, value)


def _items(value: object) -> list[Json]:
    assert isinstance(value, list)
    return [_obj(item) for item in cast(list[object], value)]


def _section(draft: Json) -> Json:
    return _obj(draft["section"])


# --- the field table (specs/section-draft.md "Field by field") ----------------------------


def _number(value: object) -> float:
    assert isinstance(value, (int, float)) and not isinstance(value, bool), value
    assert math.isfinite(value)
    return float(value)


def _xy(value: object) -> tuple[float, float]:
    assert isinstance(value, list)
    pair = cast(list[object], value)
    assert len(pair) == 2
    return _number(pair[0]), _number(pair[1])


def _label(item: Json) -> None:
    assert item["label"] is None or isinstance(item["label"], str)


def _steel(item: Json) -> None:
    designation = item["designation"]
    assert isinstance(designation, str) and designation in DESIGNATIONS, designation
    assert _number(item["diameter_mm"]) == DESIGNATIONS[designation]
    assert _number(item["spacing_mm"]) > 0.0


def validate_draft(draft: Json) -> None:
    """Every field of the spec's table, for one draft; an assertion names what is wrong."""
    assert set(draft) >= {
        "schema", "version", "units", "frame", "producer", "document", "section", "warnings",
    }  # fmt: skip
    assert draft["schema"] == "apeCAD.section-draft" and draft["version"] == 1
    assert draft["units"] == "mm"
    assert draft["frame"] == {"x": "right", "y": "up", "origin": "world"}
    producer = _obj(draft["producer"])
    assert isinstance(producer["apeCAD_version"], str)
    assert producer["apeCAD_commit"] is None or isinstance(producer["apeCAD_commit"], str)
    document = _obj(draft["document"])
    assert document["schema"] == "apeCAD.document.v1" and document["units"] == "mm"
    assert isinstance(document["ops"], list)

    section = _section(draft)
    assert list(section) == list(SECTION_LISTS)
    ids: set[int] = set()
    for name in SECTION_LISTS:
        for item in _items(section[name]):
            entity_id = item["id"]
            assert type(entity_id) is int and entity_id > 0 and entity_id not in ids
            ids.add(entity_id)

    faces = _items(section["concrete_faces"])
    assert len(faces) == 1, "exactly one concrete face in v1"
    face_ids = {face["id"] for face in faces}
    for face in faces:
        _label(face)
        assert isinstance(face["material"], str) and face["material"]
        assert face["role"] == "solid"
        ring = [_xy(p) for p in cast(list[object], face["ring_mm"])]
        assert len(ring) >= 3 and ring[0] != ring[-1], "no repeated closing point"
        assert signed_area(ring) > 0.0, "CCW"
        assert is_simple(ring)

    for leg in _items(section["wall_legs"]):
        _label(leg)
        _xy(leg["start_mm"])
        _xy(leg["end_mm"])
        assert _number(leg["thickness_mm"]) > 0.0
        assert leg["concrete_face_id"] in face_ids
        if leg["horizontal"] is not None:
            horizontal = _obj(leg["horizontal"])
            assert set(horizontal) == {"designation", "spacing_mm", "curtains"}
            assert horizontal["designation"] in DESIGNATIONS
            assert _number(horizontal["spacing_mm"]) > 0.0
            assert type(horizontal["curtains"]) is int and horizontal["curtains"] >= 1

    bars = {bar["id"]: bar for bar in _items(section["bars"])}
    for bar in bars.values():
        _label(bar)
        _number(bar["x_mm"])
        _number(bar["y_mm"])
        _steel({**bar, "spacing_mm": 1.0})

    for hoop in _items(section["hoops"]):
        _label(hoop)
        _steel(hoop)
        assert hoop["hooks"] == "135"
        ring_ids = cast(list[int], hoop["bar_ids"])
        assert all(bar_id in bars for bar_id in ring_ids)
        positions = {i: (_number(bars[i]["x_mm"]), _number(bars[i]["y_mm"])) for i in ring_ids}
        assert convex_hull_ccw(positions) == ring_ids, "strict CCW hull (P2)"

    for tie in _items(section["crossties"]):
        _label(tie)
        _steel(tie)
        assert tie["hooks"] in ("135-135", "135-90")
        assert tie["bar_a_id"] in bars and tie["bar_b_id"] in bars
        assert tie["bar_a_id"] != tie["bar_b_id"]

    for guide in _items(section["cover_guides"]):
        assert guide["face_id"] in face_ids
        for key in ("cover_mm", "tie_diameter_mm", "bar_diameter_mm"):
            assert _number(guide[key]) >= 0.0

    for warning in _items(draft["warnings"]):
        assert set(warning) == {"code", "ids", "message"}
        assert warning["code"] in LINT_CODES
        assert isinstance(warning["message"], str)
        assert all(type(i) is int for i in cast(list[object], warning["ids"]))


# --- fixtures -----------------------------------------------------------------------------


def _same(stored: object, fresh: object, where: str) -> None:
    """Equal, with floats compared at rel 1e-12 (ADR 0025 decision 8)."""
    if isinstance(fresh, float) and isinstance(stored, (int, float)):
        assert math.isclose(stored, fresh, rel_tol=1e-12), where
    elif isinstance(fresh, dict):
        fresh_obj = cast(Json, fresh)
        stored_obj = _obj(stored)
        assert list(stored_obj) == list(fresh_obj), where
        for key, value in fresh_obj.items():
            _same(stored_obj[key], value, f"{where}.{key}")
    elif isinstance(fresh, list):
        fresh_list = cast(list[object], fresh)
        assert isinstance(stored, list)
        stored_list = cast(list[object], stored)
        assert len(stored_list) == len(fresh_list), where
        for index, (a, b) in enumerate(zip(stored_list, fresh_list, strict=True)):
            _same(a, b, f"{where}[{index}]")
    else:
        assert stored == fresh, where


def test_regenerate_fixtures_when_asked() -> None:
    if os.environ.get("REGENERATE") != "1":
        pytest.skip("set REGENERATE=1 to rewrite tests/fixtures/section_draft/")
    assert len(write_fixtures()) == len(BUILDERS)


@pytest.mark.parametrize("name", NAMES)
def test_fixture_matches_its_builder(name: str) -> None:
    _same(_load(name), fixture_draft(name), name)


@pytest.mark.parametrize("name", NAMES)
def test_fixture_validates_against_the_field_table(name: str) -> None:
    validate_draft(_load(name))


@pytest.mark.parametrize("name", NAMES)
def test_fixture_round_trips_through_json(name: str) -> None:
    draft = fixture_draft(name)
    assert json.loads(json.dumps(draft)) == draft
    assert _load(name)["producer"] == {"apeCAD_version": "0.1.0", "apeCAD_commit": None}


def test_rect_fixture_reproduces_apeconcrete_rect_300x3000() -> None:
    section = _section(_load("rect_boundary_hoops"))
    (face,) = _items(section["concrete_faces"])
    assert face["ring_mm"] == [[0.0, -300.0], [3000.0, -300.0], [3000.0, 0.0], [0.0, 0.0]]
    bars = {bar["id"]: bar for bar in _items(section["bars"])}
    hoops = _items(section["hoops"])
    assert len(hoops) == 2
    for hoop, (x_min, x_max) in zip(hoops, ((0.0, 600.0), (2400.0, 3000.0)), strict=True):
        assert hoop["designation"] == "Ø10" and hoop["spacing_mm"] == 100.0
        inside = [
            bar
            for bar in bars.values()
            if bar["designation"] == "Ø16" and x_min < _number(bar["x_mm"]) < x_max
        ]
        assert len(inside) == 18
        assert {(_number(b["x_mm"]), _number(b["y_mm"])) for b in inside} >= {
            (x_min + 43.0, -43.0), (x_max - 43.0, -257.0)
        }  # fmt: skip
    assert sum(bar["designation"] == "Ø12" for bar in bars.values()) == 14
    (guide,) = _items(section["cover_guides"])
    assert (guide["cover_mm"], guide["tie_diameter_mm"], guide["bar_diameter_mm"]) == (
        25.0, 10.0, 16.0,
    )  # fmt: skip
    (leg,) = _items(section["wall_legs"])
    assert leg["horizontal"] == {"designation": "Ø12", "spacing_mm": 250.0, "curtains": 2}
