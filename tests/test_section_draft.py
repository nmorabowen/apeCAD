"""Section mode stage C4 (ADR 0025): the `apeCAD.section-draft` v1, its fixtures and reopen."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import cast

import pytest

import apeCAD
from _section_fixtures import (
    BUILDERS,
    fixture_path,
)
from apeCAD import Document, DocumentError
from apeCAD.section.draft import (
    DRAFT_SCHEMA,
    DRAFT_SCHEMA_VERSION,
    REOPEN_NUMERIC,
    SECTION_LISTS,
)
from apeCAD.section_draft import (
    COMMIT_ENV,
    document_from_draft,
    producer_commit,
    section_block,
    section_draft,
)

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


# --- the contract text -------------------------------------------------------------------


def test_spec_contract_block_hash_is_unchanged() -> None:
    """ADR 0025 decision 1: the fenced block is the contract only while it hashes to this."""
    text = SPEC.read_text(encoding="utf-8").replace("\r\n", "\n")
    blocks = re.findall(r"^## The contract\n\n```\n(.*?)```\n", text, flags=re.S | re.M)
    assert len(blocks) == 1
    body = blocks[0] if blocks[0].endswith("\n") else blocks[0] + "\n"
    assert hashlib.sha256(body.encode("utf-8")).hexdigest() == CONTRACT_SHA256


def test_constants_and_version() -> None:
    assert (DRAFT_SCHEMA, DRAFT_SCHEMA_VERSION) == ("apeCAD.section-draft", 1)
    assert apeCAD.__version__ == "0.1.0"


# --- reopen (ADR 0025 decision 3, P9) -----------------------------------------------------


@pytest.mark.parametrize("name", NAMES)
def test_draft_written_today_reopens_without_warnings(name: str) -> None:
    built = BUILDERS[name]()
    draft = json.loads(json.dumps(section_draft(built, commit=None)))
    document, warnings = document_from_draft(draft)
    assert warnings == []
    assert document.to_dict() == built.to_dict()
    assert section_block(document) == section_block(built)


@pytest.mark.parametrize("name", NAMES)
def test_committed_fixture_reopens_without_warnings(name: str) -> None:
    _, warnings = document_from_draft(_load(name))
    assert warnings == []


def test_tampered_x_is_a_warning() -> None:
    draft = _load("rect_boundary_hoops")
    bar = _items(_section(draft)["bars"])[3]
    bar["x_mm"] = cast(float, bar["x_mm"]) + 0.5
    document, warnings = document_from_draft(draft)
    assert [(w["code"], w["ids"]) for w in warnings] == [(REOPEN_NUMERIC, [bar["id"]])]
    assert "x_mm" in cast(str, warnings[0]["message"])
    assert section_block(document) == _section(_load("rect_boundary_hoops"))


def test_difference_within_tolerance_is_silent() -> None:
    draft = _load("inclined_outline")
    bar = _items(_section(draft)["bars"])[0]
    bar["y_mm"] = cast(float, bar["y_mm"]) * (1.0 + 1e-12)
    assert document_from_draft(draft)[1] == []


def test_removed_bar_is_refused() -> None:
    draft = _load("rect_boundary_hoops")
    bars = cast(list[object], _section(draft)["bars"])
    bars.pop(0)
    with pytest.raises(DocumentError, match="ids missing from the draft"):
        document_from_draft(draft)


def test_extra_item_is_refused() -> None:
    draft = _load("l_wall_two_hoops")
    bars = cast(list[object], _section(draft)["bars"])
    bars.append({**_items(bars)[0], "id": 99_999})
    with pytest.raises(DocumentError, match="ids not in the document"):
        document_from_draft(draft)


def test_changed_hoop_membership_is_refused() -> None:
    draft = _load("l_wall_two_hoops")
    hoop = _items(_section(draft)["hoops"])[0]
    ring = cast(list[int], hoop["bar_ids"])
    hoop["bar_ids"] = ring[1:] + ring[:1]
    with pytest.raises(DocumentError, match="bar_ids"):
        document_from_draft(draft)


def test_changed_designation_is_refused() -> None:
    draft = _load("c_wall_crossties")
    tie = _items(_section(draft)["crossties"])[0]
    tie["designation"] = "Ø16"
    with pytest.raises(DocumentError, match="designation"):
        document_from_draft(draft)


def test_unknown_field_from_a_newer_writer_is_ignored() -> None:
    """ADR 0025 rule 6: an optional field added keeps version 1."""
    draft = _load("c_wall_crossties")
    _items(_section(draft)["bars"])[0]["grade"] = "A630"
    assert document_from_draft(draft)[1] == []


@pytest.mark.parametrize(
    ("key", "value", "match"),
    [
        ("schema", "apeCAD.section-seed", "unsupported draft schema"),
        ("schema", None, "unsupported draft schema"),
        ("version", 2, "version"),
        ("version", True, "version"),
        ("version", "1", "version"),
        ("units", "in", "units"),
    ],
)
def test_unknown_schema_version_or_units_is_refused(key: str, value: object, match: str) -> None:
    draft = _load("rect_boundary_hoops")
    draft[key] = value
    with pytest.raises(DocumentError, match=match):
        document_from_draft(draft)


def test_draft_without_section_or_document_is_refused() -> None:
    draft = _load("rect_boundary_hoops")
    no_section = copy.deepcopy(draft)
    del no_section["section"]
    with pytest.raises(DocumentError, match="section block"):
        document_from_draft(no_section)
    del draft["document"]
    with pytest.raises(DocumentError, match="document object"):
        document_from_draft(draft)


def test_section_draft_of_an_empty_document() -> None:
    draft = section_draft(Document(), commit=None)
    assert _section(draft) == {name: [] for name in SECTION_LISTS}
    assert document_from_draft(draft)[1] == []


# --- producer ------------------------------------------------------------------------------


def test_producer_commit_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(COMMIT_ENV, "abc123")
    assert producer_commit() == "abc123"
    producer = _obj(section_draft(Document())["producer"])
    assert producer == {"apeCAD_version": "0.1.0", "apeCAD_commit": "abc123"}


def test_producer_commit_is_a_sha_or_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(COMMIT_ENV, raising=False)
    commit = producer_commit()
    assert commit is None or re.fullmatch(r"[0-9a-f]{40}", commit)
