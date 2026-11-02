"""Stage C3-S3 (ADR 0040 decision 7, ADR 0039 Errata 4 and 5): templates in the section-draft.

The oracles are the numbers of the C3 decision record §2, typed here by hand; the frozen logs
in `tests/fixtures/section_templates/`, recorded once and never regenerated (ADR 0040 decision
4); and the committed fixtures those logs must replay to, byte for byte.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from threading import Thread
from typing import cast
from urllib.request import Request, urlopen

import pytest

from _section_fixtures_v2 import (
    RECT_COLUMN_PARAMS,
    T_BEAM_PARAMS,
    T_RING,
    fixture_path_v2,
    fixture_text,
)
from apeCAD import Document
from apeCAD.agent import LocalTools
from apeCAD.agent.mcp_tools import TOOLS
from apeCAD.agent.tools import list_ops
from apeCAD.catalog import CATALOG, list_templates
from apeCAD.catalog.schema import validate
from apeCAD.cli import main as cli_main
from apeCAD.entities import Entity, EntityId
from apeCAD.errors import DocumentError, TemplateLockedError
from apeCAD.geometry import XYZ
from apeCAD.ops import PointAt
from apeCAD.scratchpad.server import ScratchpadServer
from apeCAD.scratchpad.transport import TRANSPORT_VERSION, handle
from apeCAD.section.lint import lint_section_v2
from apeCAD.section.templates import TEMPLATES, TemplateParamError, expand
from apeCAD.section_draft import (
    document_from_draft,
    document_from_section_seed,
    section_block,
    section_draft,
    section_seed,
)

Json = dict[str, object]

LOG_DIR = Path(__file__).resolve().parent / "fixtures" / "section_templates"
CHILD_LISTS = ("faces", "wall_legs", "bars", "hoops", "crossties", "circular_ties", "cover_guides")
SMALL: Json = {
    "material": "C30", "b": 300, "h": 300, "cover": 40, "nx": 2, "ny": 2, "bar": "Ø16",
    "tie": "Ø10", "tie_spacing": 150,
}  # fmt: skip
LOG_OF_FIXTURE = {"rect_column@v1": "rect_column_template", "t_beam@v1": "t_beam_template"}
# Replayed drafts without a committed fixture of their own (the card names two new fixtures):
# the SHA-256 of `fixture_text(section)`, recorded with the logs. Only the `section` block: the
# whole draft also carries `producer.apeCAD_version`, which a version bump changes and no
# regeneration can repair (apeSection#51). The hand oracles below hold the numbers.
SECTION_SHA256 = {
    "polygon_column@v1": "b55388e7fc6f89609884e72f2aa99549ede4e02e76a525fa775d1baefa4f72cc",
    "rect_hollow@v1": "dc43d3fa41ad050a63a866ea5b1bfbbd2ec8a281db5df9ab4b81eb2ace09be3a",
}


def _log(stem: str) -> Json:
    return cast(Json, json.loads((LOG_DIR / f"{stem}.json").read_text(encoding="utf-8")))


def _replay(stem: str) -> Document:
    return Document.from_dict(_log(stem))


def _draft(doc: Document) -> Json:
    return section_draft(doc, version=2, commit=None)


def _committed(name: str) -> Json:
    return cast(Json, json.loads(fixture_path_v2(name).read_text(encoding="utf-8")))


def _section(draft: Json) -> Json:
    return cast(Json, draft["section"])


def _items(section: Json, name: str) -> list[Json]:
    return cast(list[Json], section[name])


def _entities(doc: Document) -> dict[EntityId, Entity]:
    return {entity_id: doc.entity(entity_id) for entity_id in doc.entity_ids()}


def _at(x: float, y: float) -> PointAt:
    return PointAt(XYZ(x, y, 0.0))


def _bars_xy(section: Json) -> set[tuple[float, float]]:
    return {(cast(float, b["x_mm"]), cast(float, b["y_mm"])) for b in _items(section, "bars")}


def _shoelace(ring: list[list[float]]) -> tuple[float, float, float]:
    """Area and centroid of a ring, computed here and not by the code under test."""
    a = sx = sy = 0.0
    for (x0, y0), (x1, y1) in zip(ring, [*ring[1:], ring[0]], strict=True):
        cross = x0 * y1 - x1 * y0
        a, sx, sy = a + cross / 2, sx + (x0 + x1) * cross / 6, sy + (y0 + y1) * cross / 6
    return a, sx / a, sy / a


# --- the projection ---------------------------------------------------------------------


def test_templates_lists_the_four_declared_fields_with_the_params_as_given() -> None:
    doc = Document()
    template = doc.add_section_template("rect_column", RECT_COLUMN_PARAMS, label="C1")
    section = _section(_draft(doc))
    assert section["templates"] == [
        {
            "id": template.entity_id,
            "template": "rect_column",
            "template_version": 1,
            "params": RECT_COLUMN_PARAMS,  # lists stay lists; the label is not in the contract
        }
    ]


def test_template_id_is_on_every_listed_child_and_on_nothing_else() -> None:
    doc = Document()
    ring = [_at(5000, 0), _at(5500, 0), _at(5500, 500)]
    freehand = doc.add_section_face("concrete", "C25", point_ids=ring)
    loose = doc.add_bar(5300.0, 100.0, "Ø16")
    first = doc.add_section_template("rect_column", SMALL)
    second = doc.add_section_template("rect_column", {**SMALL, "center_mm": [2000, 0]})
    section = _section(_draft(doc))
    owner = {i: t.entity_id for t in (first, second) for i in t.child_ids}
    seen: set[object] = set()
    for name in CHILD_LISTS:
        for item in _items(section, name):
            assert item.get("template_id") == owner.get(cast(int, item["id"])), (name, item)
            seen.add(item.get("template_id"))
    assert seen == {None, first.entity_id, second.entity_id}
    faces = {cast(int, f["id"]): f for f in _items(section, "faces")}
    assert "template_id" not in faces[freehand.entity_id]
    bars = {cast(int, b["id"]): b for b in _items(section, "bars")}
    assert "template_id" not in bars[loose.entity_id]


def test_template_id_follows_a_bar_material_and_the_key_order_of_the_block() -> None:
    doc = Document()
    doc.add_section_template("rect_column", {**SMALL, "bar_material": "A630"})
    section = _section(_draft(doc))
    assert list(_items(section, "bars")[0])[-2:] == ["material", "template_id"]
    assert section["materials_used"] == ["A630", "C30"]


def test_the_projection_is_deterministic_and_replays() -> None:
    doc = Document()
    doc.add_section_template("t_beam", T_BEAM_PARAMS)
    doc.add_section_template("rect_column", {**SMALL, "center_mm": [2000, 0]})
    assert fixture_text(_draft(doc)) == fixture_text(_draft(doc))
    assert fixture_text(_draft(Document.from_dict(doc.to_dict()))) == fixture_text(_draft(doc))
    assert fixture_text(_draft(Document.from_json(doc.to_json()))) == fixture_text(_draft(doc))


def test_the_order_of_templates_is_stable_under_edit_undo_and_replay() -> None:
    doc = Document()
    a = doc.add_section_template("rect_column", SMALL).entity_id
    b = doc.add_section_template("rect_column", {**SMALL, "center_mm": [2000, 0]}).entity_id
    before = fixture_text(_draft(doc))

    def order() -> list[object]:
        return [t["id"] for t in _items(_section(_draft(doc)), "templates")]

    assert order() == [a, b]
    doc.edit_section_template(a, {**SMALL, "b": 450})  # a's children now have higher ids than b's
    assert order() == [a, b]
    edited = _section(_draft(doc))
    (params, _) = (t["params"] for t in _items(edited, "templates"))
    assert cast(Json, params)["b"] == 450
    replayed = _section(_draft(Document.from_dict(doc.to_dict())))
    assert order() == [t["id"] for t in _items(replayed, "templates")]
    doc.undo()
    assert fixture_text(_draft(doc)) == before
    doc.redo()
    assert _section(_draft(doc)) == edited


def test_an_edit_moves_template_id_to_the_fresh_children() -> None:
    doc = Document()
    template = doc.add_section_template("rect_column", SMALL)
    old = set(template.child_ids)
    doc.edit_section_template(template.entity_id, {**SMALL, "center_mm": [1000, 0]})
    section = _section(_draft(doc))
    for name in CHILD_LISTS:
        for item in _items(section, name):
            assert item["template_id"] == template.entity_id
            assert item["id"] not in old


def test_explode_removes_templates_and_every_template_id_and_nothing_else() -> None:
    doc = Document()
    template = doc.add_section_template("t_beam", T_BEAM_PARAMS)
    before = _section(_draft(doc))
    doc.explode_section_template(template.entity_id)
    after = _section(_draft(doc))
    assert after["templates"] == []
    assert before["templates"] != []
    assert after["materials_used"] == before["materials_used"]
    for name in CHILD_LISTS:
        stripped = [
            {k: v for k, v in item.items() if k != "template_id"} for item in _items(before, name)
        ]
        assert _items(after, name) == stripped, name


def test_deleting_a_template_takes_its_entry_and_its_children_only() -> None:
    doc = Document()
    gone = doc.add_section_template("rect_column", SMALL)
    kept = doc.add_section_template("rect_column", {**SMALL, "center_mm": [2000, 0]})
    doc.delete([gone.entity_id])
    section = _section(_draft(doc))
    assert [t["id"] for t in _items(section, "templates")] == [kept.entity_id]
    for name in CHILD_LISTS:
        for item in _items(section, name):
            assert item["template_id"] == kept.entity_id, name


# --- hand oracles (C3 record §2) ---------------------------------------------------------


def test_rect_column_template_oracle() -> None:
    draft = _committed("rect_column_template")
    section = _section(draft)
    (face,) = _items(section, "faces")
    ring = cast(list[list[float]], cast(Json, face["boundary"])["ring_mm"])
    assert ring == [[0.0, 0.0], [400.0, 0.0], [400.0, 600.0], [0.0, 600.0]]
    assert _shoelace(ring) == (240_000.0, 200.0, 300.0)
    grid = {(x, y) for x in (60.0, 200.0, 340.0) for y in (60.0, 300.0, 540.0)}
    assert _bars_xy(section) == grid - {(200.0, 300.0)}  # 2 nx + 2 ny - 4 = 8: no centre bar
    assert {b["designation"] for b in _items(section, "bars")} == {"Ø20"}
    # The same bars as the freehand fixture of the same column.
    assert _bars_xy(section) == _bars_xy(_section(_committed("rect_column_ties")))
    ties = _items(section, "crossties")
    assert len(ties) == 2 and {t["hooks"] for t in ties} == {"135-135"}
    by_id = {b["id"]: (b["x_mm"], b["y_mm"]) for b in _items(section, "bars")}
    assert {frozenset((by_id[t["bar_a_id"]], by_id[t["bar_b_id"]])) for t in ties} == {
        frozenset(((200.0, 60.0), (200.0, 540.0))),
        frozenset(((60.0, 300.0), (340.0, 300.0))),
    }
    (hoop,) = _items(section, "hoops")
    corners = {by_id[i] for i in cast(list[int], hoop["bar_ids"])}
    assert corners == {(60.0, 60.0), (340.0, 60.0), (340.0, 540.0), (60.0, 540.0)}
    assert hoop["designation"] == "Ø10" and hoop["spacing_mm"] == 150.0
    assert draft["warnings"] == []


def test_t_beam_template_oracle() -> None:
    draft = _committed("t_beam_template")
    section = _section(draft)
    (face,) = _items(section, "faces")
    ring = cast(list[list[float]], cast(Json, face["boundary"])["ring_mm"])
    assert ring == [[float(x), float(y)] for x, y in T_RING]
    area, cx, cy = _shoelace(ring)
    assert area == 255_000.0
    assert cx == pytest.approx(0.0, abs=1e-9)
    assert cy == pytest.approx(366.176, abs=5e-4)
    assert _bars_xy(section) == {
        (0.0, 50.0), (100.0, 50.0), (-100.0, 50.0),
        (102.0, 552.0), (-102.0, 552.0),
        (212.5, 564.0), (-212.5, 564.0), (337.5, 564.0), (-337.5, 564.0),
    }  # fmt: skip
    assert draft["warnings"] == []


def test_polygon_column_log_oracle() -> None:
    section = _section(_draft(_replay("polygon_column@v1")))
    (face,) = _items(section, "faces")
    ring = cast(list[list[float]], cast(Json, face["boundary"])["ring_mm"])
    area, cx, cy = _shoelace(ring)
    assert area == 240_000.0 and cx == pytest.approx(275.0)
    assert cy == pytest.approx(204.167, abs=5e-4)
    bars = _bars_xy(section)
    assert len(bars) == 4 + 2 + 4 + 3  # intervals per edge
    # The record's corners to 3 decimals; an inclined ring's bars sit on the 1/1024 mm grid
    # (ADR 0032), so the tolerance is one grid step plus the rounding of the hand number.
    for corner in ((60.0, 60.0), (540.0, 60.0), (540.0, 256.754), (60.0, 416.754)):
        assert any(math.dist(corner, bar) < 1 / 1024 + 5e-4 for bar in bars), corner


def test_rect_hollow_log_oracle() -> None:
    section = _section(_draft(_replay("rect_hollow@v1")))
    (face,) = _items(section, "faces")
    outer = cast(list[list[float]], cast(Json, face["boundary"])["ring_mm"])
    (hole,) = cast(list[Json], face["holes"])
    inner = cast(list[list[float]], hole["ring_mm"])
    assert _shoelace(outer)[0] + _shoelace(inner)[0] == 360_000.0
    assert len(_items(section, "bars")) == 14 + 12
    assert len(_items(section, "hoops")) == 2 and _items(section, "crossties") == []


@pytest.mark.parametrize("stem", sorted(p.stem for p in LOG_DIR.glob("*.json")))
def test_each_oracle_section_has_no_lint(stem: str) -> None:
    doc = _replay(stem)
    assert lint_section_v2(_entities(doc)) == ()


# --- the frozen logs ----------------------------------------------------------------------


def test_one_frozen_log_per_template_version() -> None:
    """ADR 0040 decision 4: adding a template or a version without its log fails here."""
    wanted = {f"{name}@v{v}" for name, versions in TEMPLATES.items() for v in versions}
    assert {path.stem for path in LOG_DIR.glob("*.json")} == wanted


@pytest.mark.parametrize("stem", sorted(LOG_OF_FIXTURE))
def test_a_frozen_log_replays_to_its_fixture_byte_for_byte(stem: str) -> None:
    name = LOG_OF_FIXTURE[stem]
    committed = fixture_path_v2(name).read_bytes().decode("utf-8").replace("\r\n", "\n")
    assert fixture_text(_draft(_replay(stem))) == committed


def _section_sha256(draft: Json) -> str:
    return hashlib.sha256(fixture_text(_section(draft)).encode("utf-8")).hexdigest()


@pytest.mark.parametrize("stem", sorted(SECTION_SHA256))
def test_a_frozen_log_without_a_fixture_replays_to_its_recorded_section(stem: str) -> None:
    assert _section_sha256(_draft(_replay(stem))) == SECTION_SHA256[stem]


@pytest.mark.parametrize("stem", sorted(SECTION_SHA256))
def test_the_recorded_section_ignores_a_version_bump_and_sees_a_section_value(
    stem: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(import_module("apeCAD.section_draft"), "__version__", "9.9.9")
    draft = _draft(_replay(stem))
    assert cast(Json, draft["producer"])["apeCAD_version"] == "9.9.9"
    assert _section_sha256(draft) == SECTION_SHA256[stem]
    bar = _items(_section(draft), "bars")[0]
    bar["x_mm"] = cast(float, bar["x_mm"]) + 1.0
    assert _section_sha256(draft) != SECTION_SHA256[stem]


@pytest.mark.parametrize("stem", sorted(p.stem for p in LOG_DIR.glob("*.json")))
def test_a_frozen_log_replays_to_itself(stem: str) -> None:
    log = _log(stem)
    assert _replay(stem).to_dict() == log
    (op,) = cast(list[Json], log["ops"])
    assert op["op"] == "AddSectionTemplate" and op["template_version"] == 1
    assert cast(list[int], op["child_ids"]), "the log records its child ids"


# --- the seed carries no templates ------------------------------------------------------


def test_seed_v2_carries_no_templates_and_replays_as_a_plain_drawing() -> None:
    doc = Document()
    doc.add_section_template("t_beam", T_BEAM_PARAMS)
    seed = section_seed(doc, version=2)
    assert seed["version"] == 2
    block = _section(seed)
    assert "templates" not in block and "materials_used" not in block
    assert "template_id" not in json.dumps(seed)
    plain = document_from_section_seed(seed)
    assert plain.section_templates() == ()
    reopened = _section(_draft(plain))
    assert reopened["templates"] == []
    assert _bars_xy(reopened) == _bars_xy(_section(_draft(doc)))
    # Freehand, the same drawing can be edited: nothing is locked.
    bar = _items(reopened, "bars")[0]
    plain.delete([cast(int, bar["id"])])


def test_seed_v2_of_a_templated_draft_equals_the_seed_of_its_explosion() -> None:
    doc = Document()
    template = doc.add_section_template("rect_column", RECT_COLUMN_PARAMS)
    seed = section_seed(doc, version=2)
    doc.explode_section_template(template.entity_id)
    assert seed == section_seed(doc, version=2)


# --- version 1 still refuses, by name ----------------------------------------------------


@pytest.mark.parametrize(
    "write", [section_draft, section_seed, section_block], ids=["draft", "seed", "block"]
)
def test_version_1_refuses_a_template_by_name(write: Callable[..., Json]) -> None:
    doc = Document()
    template = doc.add_section_template("rect_column", SMALL)
    with pytest.raises(DocumentError, match=f"entity {template.entity_id} is a rect_column"):
        write(doc, version=1)
    with pytest.raises(DocumentError, match="version 1 cannot say"):
        write(doc)  # 1 is the default
    doc.explode_section_template(template.entity_id)
    with pytest.raises(DocumentError, match="v2 section face|cannot say"):
        write(doc, version=1)  # the children are v2 faces, still not version 1


def test_a_version_1_draft_of_a_templated_log_does_not_reopen() -> None:
    plain = Document()
    plain.add_section_outline([_at(0, 0), _at(100, 0), _at(100, 100)], material="C30")
    draft = section_draft(plain, version=1, commit=None)
    doc = Document()
    doc.add_section_template("rect_column", SMALL)
    forged = {**draft, "document": doc.to_dict()}
    with pytest.raises(DocumentError, match="is a rect_column template"):
        document_from_draft(forged)


# --- the reopen check: a stored `templates[]` and `template_id` must compare --------------


def _rect() -> Json:
    return copy.deepcopy(_committed("rect_column_template"))


@pytest.mark.parametrize("name", ["rect_column_template", "t_beam_template"])
def test_a_committed_template_fixture_reopens_clean(name: str) -> None:
    document, warnings = document_from_draft(_committed(name))
    assert warnings == []
    assert len(document.section_templates()) == 1


def _template(draft: Json) -> Json:
    return _items(_section(draft), "templates")[0]


def _param(key: str, value: object) -> Callable[[Json], None]:
    def change(draft: Json) -> None:
        cast(Json, _template(draft)["params"])[key] = value

    return change


def _field(key: str, value: object) -> Callable[[Json], None]:
    def change(draft: Json) -> None:
        _template(draft)[key] = value

    return change


def _no_template_id(name: str) -> Callable[[Json], None]:
    def change(draft: Json) -> None:
        del _items(_section(draft), name)[0]["template_id"]

    return change


def _other_template_id(name: str) -> Callable[[Json], None]:
    def change(draft: Json) -> None:
        _items(_section(draft), name)[0]["template_id"] = 999

    return change


def _empty_templates(draft: Json) -> None:
    _section(draft)["templates"] = []


def _extra_template(draft: Json) -> None:
    _items(_section(draft), "templates").append({**_template(draft), "id": 999})


def _no_templates_key(draft: Json) -> None:
    del _section(draft)["templates"]


@pytest.mark.parametrize(
    ("tamper", "message"),
    [
        (_param("b", 500), r"section\.templates\[id=1\]\.params\.b is 500"),
        (_param("b", 400.0), r"section\.templates\[id=1\]\.params\.b is 400\.0"),
        (_param("center_mm", [201, 300]), r"section\.templates\[id=1\]\.params is"),
        (_param("zz", 1), r"section\.templates\[id=1\]\.params is"),
        (_field("template_version", 2), r"section\.templates\[id=1\]\.template_version is 2"),
        (_field("template", "t_beam"), r"section\.templates\[id=1\]\.template is 't_beam'"),
        (_empty_templates, r"section\.templates differs .* ids missing from the draft \[1\]"),
        (_extra_template, r"section\.templates differs .* ids not in the document \[999\]"),
        (_no_templates_key, r"section\.templates is missing"),
        (_no_template_id("faces"), r"section\.faces\[id=\d+\]\s+has no 'template_id'"),
        (_no_template_id("bars"), r"section\.bars\[id=\d+\]\s+has no 'template_id'"),
        (_no_template_id("hoops"), r"section\.hoops\[id=\d+\]\s+has no 'template_id'"),
        (_no_template_id("crossties"), r"section\.crossties\[id=\d+\]\s+has no 'template_id'"),
        (_no_template_id("cover_guides"), r"section\.cover_guides\[id=\d+\]\s+has no"),
        (_other_template_id("faces"), r"section\.faces\[id=\d+\]\.template_id is 999"),
        (_other_template_id("bars"), r"section\.bars\[id=\d+\]\.template_id is 999"),
    ],
)  # fmt: skip
def test_a_stored_template_that_differs_is_refused_by_name(
    tamper: Callable[[Json], None], message: str
) -> None:
    draft = _rect()
    tamper(draft)
    with pytest.raises(DocumentError, match=message):
        document_from_draft(draft)


def test_a_stored_template_id_on_a_freehand_item_is_refused() -> None:
    doc = Document()
    doc.add_section_template("rect_column", SMALL)
    bar = doc.add_bar(2000.0, 0.0, "Ø16")
    draft = copy.deepcopy(_draft(doc))
    for item in _items(_section(draft), "bars"):
        if item["id"] == bar.entity_id:
            item["template_id"] = 1
    with pytest.raises(DocumentError, match=rf"section\.bars\[id={bar.entity_id}\]\.template_id"):
        document_from_draft(draft)


def test_params_compare_whatever_their_key_order() -> None:
    draft = _rect()
    template = _template(draft)
    template["params"] = dict(reversed(list(cast(Json, template["params"]).items())))
    assert document_from_draft(draft)[1] == []


def test_a_reopened_template_stays_locked_and_editable() -> None:
    document, _ = document_from_draft(_committed("rect_column_template"))
    (template,) = document.section_templates()
    with pytest.raises(TemplateLockedError):
        document.delete([template.child_ids[-1]])
    document.edit_section_template(template.entity_id, {**RECT_COLUMN_PARAMS, "b": 500})
    assert _items(_section(_draft(document)), "templates")[0]["id"] == template.entity_id


# --- the seams ---------------------------------------------------------------------------


def test_the_transport_and_the_tools_write_a_templated_draft(tmp_path: Path) -> None:
    tools = LocalTools(root=tmp_path)
    name = cast(str, tools.new_document()["document"])
    params: Json = {"template": "t_beam", "template_params": T_BEAM_PARAMS}
    tools.apply_op(name, "AddSectionTemplate", params)
    envelope = tools.get_section_draft(name, 2)
    assert envelope["ok"] is True, envelope
    assert cast(Json, envelope["draft"])["section"] == _section(_committed("t_beam_template"))
    refused = tools.get_section_draft(name, 1)
    assert refused["ok"] is False and "t_beam" in cast(str, cast(Json, refused["error"])["message"])


# --- the `templates` key of list_ops -----------------------------------------------------


def _rows() -> dict[str, Json]:
    return {cast(str, row["name"]): row for row in list_templates()}


def test_list_templates_has_one_row_per_template_and_is_json() -> None:
    rows = _rows()
    assert set(rows) == set(TEMPLATES)
    json.dumps(list_templates(), allow_nan=False)
    for name, row in rows.items():
        assert list(row) == ["name", "summary", "version", "versions", "params", "example"]
        assert row["version"] == max(TEMPLATES[name]) and row["versions"] == sorted(TEMPLATES[name])
        schema = cast(Json, row["params"])
        assert schema["type"] == "object" and schema["additionalProperties"] is False


@pytest.mark.parametrize("name", sorted(TEMPLATES))
def test_a_row_example_passes_its_schema_and_the_op_and_expands(name: str) -> None:
    row = _rows()[name]
    example = cast(Json, row["example"])
    validate(cast(Json, row["params"]), example, name)
    expand(name, example)
    doc = Document()
    params = {"template": name, "template_params": example}
    validate(CATALOG["AddSectionTemplate"].params, params, "AddSectionTemplate")
    doc.add_section_template(name, example)
    assert lint_section_v2(_entities(doc)) == ()


@pytest.mark.parametrize("name", sorted(TEMPLATES))
def test_a_row_says_what_its_expansion_requires_param_by_param(name: str) -> None:
    """The schema against the code that checks: required, optional, unknown and described."""
    row = _rows()[name]
    schema = cast(Json, row["params"])
    example = cast(Json, row["example"])
    properties = cast(dict[str, Json], schema["properties"])
    required = cast(list[str], schema["required"])
    assert all(isinstance(prop.get("description"), str) for prop in properties.values())
    assert set(example) <= set(properties)
    for key in required:
        reduced = {k: v for k, v in example.items() if k != key}
        with pytest.raises(TemplateParamError, match=f"{name}: {key}: required"):
            expand(name, reduced)
    for key in set(example) - set(required):  # an optional param may always go
        expand(name, {k: v for k, v in example.items() if k != key})
    assert set(required) <= set(example)
    with pytest.raises(TemplateParamError, match=f"{name}: zz: unknown parameter"):
        expand(name, {**example, "zz": 1})
    # A param the schema names is one the expansion accepts: its "known:" list is the schema's.
    with pytest.raises(TemplateParamError) as refused:
        expand(name, {**example, "zz": 1})
    known = str(refused.value).split("known: ")[1].split(", ")
    assert set(known) == set(properties)


def test_a_default_in_a_row_is_what_the_expansion_uses() -> None:
    rows = _rows()
    column = cast(dict[str, Json], cast(Json, rows["rect_column"]["params"])["properties"])
    assert column["center_mm"]["default"] == [0.0, 0.0]
    assert column["crossties"]["default"] == "none"
    assert column["bar_material"]["default"] is None
    required = {k: v for k, v in cast(Json, rows["rect_column"]["example"]).items()
                if k not in ("center_mm", "crossties")}  # fmt: skip
    plan = expand("rect_column", required)
    assert plan.crossties == () and plan.bars[0].x_mm < 0  # no ties, centred on the origin


def test_every_surface_lists_the_templates(tmp_path: Path) -> None:
    listed = list_ops()
    assert listed["templates"] == list_templates()
    assert LocalTools(root=tmp_path).list_ops()["templates"] == list_templates()
    # `name` selects an op, and the templates stay listed.
    one = list_ops("AddSectionTemplate")
    assert [op["name"] for op in cast(list[Json], one["ops"])] == ["AddSectionTemplate"]
    assert one["templates"] == list_templates()
    assert "templates" not in list_ops("AddTeapot")
    assert TOOLS["list_ops"].call(LocalTools(root=tmp_path), {})["templates"] == list_templates()


def test_the_cli_lists_the_templates(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main(["ops"]) == 0
    assert json.loads(capsys.readouterr().out)["templates"] == list_templates()


def _get(port: int, path: str) -> Json:
    with urlopen(f"http://127.0.0.1:{port}{path}") as response:
        return cast(Json, json.loads(response.read().decode("utf-8")))


def test_the_http_surfaces_list_the_templates() -> None:
    """`GET /api/ops`, and `POST /api/tool`, the route attach mode calls (agent/hosted.py)."""
    bound = ScratchpadServer(("127.0.0.1", 0), Document())
    Thread(target=bound.serve_forever, daemon=True).start()
    try:
        port = bound.server_address[1]
        assert _get(port, "/api/ops")["templates"] == list_templates()
        assert _get(port, "/api/ops?name=Extrude")["templates"] == list_templates()
        body = json.dumps({"tool": "list_ops", "arguments": {}}).encode("utf-8")
        request = Request(f"http://127.0.0.1:{port}/api/tool", data=body, method="POST")
        with urlopen(request) as response:
            assert json.loads(response.read().decode("utf-8"))["templates"] == list_templates()
    finally:
        bound.shutdown()
        bound.server_close()


def test_the_transport_writes_a_templated_draft() -> None:
    doc = Document()
    doc.add_section_template("rect_column", RECT_COLUMN_PARAMS)
    request: Json = {
        "transport_version": TRANSPORT_VERSION,
        "action": "draft",
        "document": doc.to_dict(),
        "redo": [],
    }
    written = handle({**request, "version": 2})
    assert written["ok"] is True, written
    assert _section(cast(Json, written["draft"])) == _section(_committed("rect_column_template"))
    refused = handle(request)  # the default is version 1: HA-04 still gets a refusal by name
    assert refused["ok"] is False and refused["status"] == 422
    assert "rect_column template" in cast(str, cast(Json, refused["error"])["message"])
