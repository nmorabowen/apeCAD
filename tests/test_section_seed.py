"""Stage C10: apeCAD.section-seed v1 writer, reader, and round-trip tests (ADR 0025, 0026)."""

from __future__ import annotations

import copy
from typing import cast

import pytest

from _section_fixtures import BUILDERS
from apeCAD.errors import DocumentError
from apeCAD.section.draft import SEED_SCHEMA, SEED_SCHEMA_VERSION
from apeCAD.section_draft import (
    document_from_draft,
    document_from_section_seed,
    section_draft,
    section_seed,
)

Json = dict[str, object]


@pytest.mark.parametrize("name", sorted(BUILDERS))
def test_section_seed_round_trips_all_fixtures(name: str) -> None:
    original = BUILDERS[name]()
    seed = section_seed(original)
    assert seed["schema"] == SEED_SCHEMA
    assert seed["version"] == SEED_SCHEMA_VERSION
    assert seed["units"] == "mm"

    rebuilt = document_from_section_seed(seed)
    assert section_seed(rebuilt) == seed
    draft = section_draft(rebuilt, commit=None)
    reopened, warnings = document_from_draft(draft)
    assert warnings == []
    assert section_seed(reopened) == seed


def test_seed_uses_zero_based_indices_without_entity_ids() -> None:
    doc = BUILDERS["c_wall_crossties"]()
    seed = section_seed(doc)
    sec = cast(Json, seed["section"])
    faces = cast(list[Json], sec["concrete_faces"])
    legs = cast(list[Json], sec["wall_legs"])
    bars = cast(list[Json], sec["bars"])
    hoops = cast(list[Json], sec["hoops"])
    ties = cast(list[Json], sec["crossties"])
    guides = cast(list[Json], sec["cover_guides"])

    assert len(faces) == 1
    assert "id" not in faces[0]
    for leg in legs:
        assert leg["concrete_face_id"] == 0
    for g in guides:
        assert g["face_id"] == 0
    for h in hoops:
        for idx in cast(list[int], h["bar_ids"]):
            assert 0 <= idx < len(bars)
    for t in ties:
        assert 0 <= cast(int, t["bar_a_id"]) < len(bars)
        assert 0 <= cast(int, t["bar_b_id"]) < len(bars)


def test_seed_refuses_diameter_mismatch() -> None:
    seed = section_seed(BUILDERS["rect_boundary_hoops"]())
    sec = cast(Json, seed["section"])
    bars = cast(list[Json], sec["bars"])
    bad_bar = copy.deepcopy(seed)
    cast(list[Json], cast(Json, bad_bar["section"])["bars"])[0]["diameter_mm"] = 99.0
    with pytest.raises(DocumentError, match="diameter_mm"):
        document_from_section_seed(bad_bar)

    bad_hoop = copy.deepcopy(seed)
    cast(list[Json], cast(Json, bad_hoop["section"])["hoops"])[0]["diameter_mm"] = 25.0
    with pytest.raises(DocumentError, match="diameter_mm"):
        document_from_section_seed(bad_hoop)

    assert len(bars) > 0


def test_seed_refuses_out_of_range_indices() -> None:
    seed = section_seed(BUILDERS["c_wall_crossties"]())

    bad_face = copy.deepcopy(seed)
    cast(list[Json], cast(Json, bad_face["section"])["cover_guides"])[0]["face_id"] = 5
    with pytest.raises(DocumentError, match="out of range"):
        document_from_section_seed(bad_face)

    bad_hoop = copy.deepcopy(seed)
    cast(list[Json], cast(Json, bad_hoop["section"])["hoops"])[0]["bar_ids"] = [0, 1, 999]
    with pytest.raises(DocumentError, match="out of range"):
        document_from_section_seed(bad_hoop)

    bad_tie = copy.deepcopy(seed)
    cast(list[Json], cast(Json, bad_tie["section"])["crossties"])[0]["bar_a_id"] = -1
    with pytest.raises(DocumentError, match="out of range"):
        document_from_section_seed(bad_tie)


@pytest.mark.parametrize(
    "patch",
    [
        {"schema": "apeCAD.section-draft"},
        {"version": 2},
        {"version": True},
        {"units": "cm"},
        {"frame": {"x": "left", "y": "up", "origin": "world"}},
        {"section": []},
    ],
)
def test_seed_refuses_bad_header(patch: Json) -> None:
    seed = section_seed(BUILDERS["l_wall_two_hoops"]())
    seed.update(patch)
    with pytest.raises(DocumentError):
        document_from_section_seed(seed)


def test_section_seed_module_exports_and_flat_seed_accepted() -> None:
    from apeCAD.section import seed as seed_mod

    assert seed_mod.SEED_SCHEMA == "apeCAD.section-seed"
    assert seed_mod.SEED_SCHEMA_VERSION == 1
    assert callable(seed_mod.project_seed_section)
    assert callable(seed_mod.require_seed_header)

    nested_seed = section_seed(BUILDERS["l_wall_two_hoops"]())
    sec = cast(Json, nested_seed["section"])
    flat_seed: Json = {
        "schema": seed_mod.SEED_SCHEMA,
        "version": seed_mod.SEED_SCHEMA_VERSION,
        "units": "mm",
        "frame": {"x": "right", "y": "up", "origin": "world"},
        **sec,
    }
    rebuilt = document_from_section_seed(flat_seed)
    assert section_seed(rebuilt) == nested_seed
