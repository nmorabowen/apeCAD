"""Stage C1-S4 fixtures (ADR 0039 decision 8): they match their builders and the v2 spec.

Oracles: the spec's field table (`validate_v2`), areas and centroids worked out by hand for
every fixture (the numbers below, not the code), and v1's `rect_boundary_hoops` read entity
for entity against its v2 copy.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import cast

import pytest

from _section_fixtures import fixture_path as v1_fixture_path
from _section_fixtures_v2 import (
    BUILDERS_V2,
    FIXTURE_DIR,
    fixture_draft_v2,
    fixture_path_v2,
    fixture_text,
    write_fixtures_v2,
)
from test_section_draft_v2 import validate_v2

SPEC_V2 = Path(__file__).resolve().parents[1] / "AProjects" / "specs" / "section-draft-v2.md"
CONTRACT_SHA256_V2 = "eb0efd21715d46bc5fdab99ac20d979ab9569de4ed8ee7ce9ea9a7e2f83ae267"
NAMES = sorted(BUILDERS_V2)
V1_ONLY = {"more-than-one-solid-face", "face-without-wall-leg"}

Json = dict[str, object]


def _load(name: str) -> Json:
    return cast(Json, json.loads(fixture_path_v2(name).read_text(encoding="utf-8")))


def _obj(value: object) -> Json:
    assert isinstance(value, dict)
    return cast(Json, value)


def _items(value: object) -> list[Json]:
    assert isinstance(value, list)
    return [_obj(item) for item in cast(list[object], value)]


def _section(draft: Json) -> Json:
    return _obj(draft["section"])


def test_the_fixtures_pin_the_v2_contract_hash() -> None:
    """The fixtures are written against this text of the contract (as v1's are)."""
    text = SPEC_V2.read_text(encoding="utf-8").replace("\r\n", "\n")
    (block,) = re.findall(r"^## The contract\n\n```\n(.*?)```\n", text, flags=re.S | re.M)
    assert hashlib.sha256(block.encode("utf-8")).hexdigest() == CONTRACT_SHA256_V2


def test_the_fixture_set_is_decision_8s() -> None:
    assert sorted(path.stem for path in FIXTURE_DIR.glob("*.json")) == NAMES == sorted(
        [
            "rect_column_ties", "circular_column_spiral", "box_with_void", "t_beam",
            "src_w_in_rect", "cft_round", "bare_w_shape", "rect_boundary_hoops",
        ]
    )  # fmt: skip


# --- fixtures match their builders ------------------------------------------------------


def _same(stored: object, fresh: object, where: str) -> None:
    """Equal, with floats compared at rel 1e-12 (ADR 0039 decision 8)."""
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
        pytest.skip("set REGENERATE=1 to rewrite tests/fixtures/section_draft_v2/")
    assert len(write_fixtures_v2()) == len(BUILDERS_V2)


@pytest.mark.parametrize("name", NAMES)
def test_fixture_matches_its_builder(name: str) -> None:
    _same(_load(name), fixture_draft_v2(name), name)


@pytest.mark.parametrize("name", NAMES)
def test_fixture_validates_against_the_v2_field_table(name: str) -> None:
    validate_v2(_load(name))


@pytest.mark.parametrize("name", NAMES)
def test_fixture_is_lf_json_with_no_sha(name: str) -> None:
    raw = fixture_path_v2(name).read_bytes()
    text = raw.decode("utf-8").replace("\r\n", "\n")  # a CRLF checkout (autocrlf) is fine
    assert text.endswith("}\n") and not text.endswith("\n\n")
    assert all(line == line.rstrip() for line in text.split("\n")), "no trailing whitespace"
    draft = json.loads(text)
    assert draft["producer"] == {"apeCAD_version": "0.1.0", "apeCAD_commit": None}
    assert fixture_text(fixture_draft_v2(name)) == fixture_text(fixture_draft_v2(name))


# --- areas and centroids, worked out by hand ------------------------------------------------
#
# Each fixture's net area and centroid per material role, after the precedence
# void > steel > concrete. `minus` names the roles whose faces lie over the concrete in that
# fixture (and so are cut from it); every other pairing of faces there is disjoint.

_PI = math.pi
_T_AREA = 300 * 450 + 800 * 150  # web + flange = 255 000
_T_CY = (300 * 450 * 225 + 800 * 150 * 525) / _T_AREA  # 93 375 000 / 255 000
_W = 2 * 254 * 16.3 + (310 - 2 * 16.3) * 9.1  # W310x86 without fillets: 10 804.74

EXPECTED: dict[str, dict[str, tuple[float, float, float]]] = {
    # role: (area mm², centroid x, centroid y)
    "rect_column_ties": {"concrete": (400 * 600, 200.0, 300.0)},
    "circular_column_spiral": {"concrete": (_PI * 300**2, 0.0, 0.0)},
    "box_with_void": {"concrete": (400 * 600 - 200 * 300, 0.0, 0.0), "void": (60_000, 0.0, 0.0)},
    "t_beam": {"concrete": (_T_AREA, 0.0, _T_CY)},
    "src_w_in_rect": {"concrete": (500 * 500 - _W, 0.0, 0.0), "steel": (_W, 0.0, 0.0)},
    "cft_round": {
        "concrete": (_PI * 190**2, 0.0, 0.0),
        "steel": (_PI * (200**2 - 190**2), 0.0, 0.0),
    },
    "bare_w_shape": {"steel": (_W, 0.0, 0.0)},
    "rect_boundary_hoops": {"concrete": (3000 * 300, 1500.0, -150.0)},
}
MINUS = {"box_with_void": ("void",), "src_w_in_rect": ("steel",)}


def _moments(boundary: Json) -> tuple[float, float, float]:
    """Signed area and first moments (A, Sx = A*cx, Sy = A*cy) of one boundary."""
    if boundary["kind"] == "circle":
        cx, cy = cast(list[float], boundary["center_mm"])
        area = _PI * cast(float, boundary["radius_mm"]) ** 2
        return area, area * cx, area * cy
    ring = cast(list[list[float]], boundary["ring_mm"])
    a = sx = sy = 0.0
    for (x0, y0), (x1, y1) in zip(ring, [*ring[1:], ring[0]], strict=True):
        cross = x0 * y1 - x1 * y0
        a += cross / 2.0
        sx += (x0 + x1) * cross / 6.0
        sy += (y0 + y1) * cross / 6.0
    return a, sx, sy


def _region(face: Json) -> tuple[float, float, float]:
    """Boundary minus holes; a hole is subtracted by magnitude whatever its orientation."""
    a, sx, sy = _moments(_obj(face["boundary"]))
    for hole in _items(face["holes"]):
        ha, hx, hy = _moments(hole)
        sign = 1.0 if ha > 0 else -1.0
        a, sx, sy = a - sign * ha, sx - sign * hx, sy - sign * hy
    return a, sx, sy


@pytest.mark.parametrize("name", NAMES)
def test_areas_and_centroids_by_hand(name: str) -> None:
    faces = _items(_section(_load(name))["faces"])
    totals: dict[str, list[float]] = {}
    for face in faces:
        a, sx, sy = _region(face)
        total = totals.setdefault(cast(str, face["role"]), [0.0, 0.0, 0.0])
        total[0], total[1], total[2] = total[0] + a, total[1] + sx, total[2] + sy
    for role in MINUS.get(name, ()):
        concrete, over = totals["concrete"], totals[role]
        totals["concrete"] = [c - o for c, o in zip(concrete, over, strict=True)]
    assert set(totals) == set(EXPECTED[name])
    for role, (area, cx, cy) in EXPECTED[name].items():
        a, sx, sy = totals[role]
        assert math.isclose(a, area, rel_tol=1e-12), (role, a, area)
        assert math.isclose(sx / a, cx, rel_tol=1e-12, abs_tol=1e-9), (role, sx / a, cx)
        assert math.isclose(sy / a, cy, rel_tol=1e-12, abs_tol=1e-9), (role, sy / a, cy)


def test_cft_tube_hole_is_the_concrete_core() -> None:
    """Why `cft_round` subtracts nothing: the tube's hole is exactly the core's circle."""
    faces = {f["role"]: f for f in _items(_section(_load("cft_round"))["faces"])}
    assert _items(faces["steel"]["holes"]) == [_obj(faces["concrete"]["boundary"])]


def test_t_beam_is_non_convex_and_its_stirrup_hull_is_strict() -> None:
    section = _section(_load("t_beam"))
    (face,) = _items(section["faces"])
    assert len(cast(list[object], _obj(face["boundary"])["ring_mm"])) == 8
    (stirrup,) = _items(section["hoops"])
    assert stirrup["label"] == "stirrup" and len(cast(list[int], stirrup["bar_ids"])) == 4


# --- rect_boundary_hoops: v1 and v2 describe the same wall, entity for entity ----------------


def test_rect_boundary_hoops_v2_matches_v1_entity_for_entity() -> None:
    v1 = cast(Json, json.loads(v1_fixture_path("rect_boundary_hoops").read_text(encoding="utf-8")))
    v2 = _load("rect_boundary_hoops")
    assert v2["document"] == v1["document"]
    s1, s2 = _section(v1), _section(v2)
    for key in ("wall_legs", "bars", "hoops", "crossties", "cover_guides"):
        assert s2[key] == s1[key], key
    (f1,) = _items(s1["concrete_faces"])
    (f2,) = _items(s2["faces"])
    assert f2 == {
        "id": f1["id"],
        "label": f1["label"],
        "role": "concrete",
        "material": f1["material"],
        "boundary": {"kind": "ring", "ring_mm": f1["ring_mm"]},
        "holes": [],
    }
    assert s2["circular_ties"] == [] and s2["templates"] == []
    assert s2["materials_used"] == [f1["material"]]
    kept = [w for w in _items(v1["warnings"]) if w["code"] not in V1_ONLY]
    assert v2["warnings"] == kept
