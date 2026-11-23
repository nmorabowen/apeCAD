"""The word `holes` in the template texts (ADR 0040 Errata 21, C9-3, apeSection#302).

C9-3 adds `holes` (version 2) to `draft/templates.py::_WAYS_OUT`, the ways out a
`TEMPLATE_LOCKED` refusal names, and to `catalog/template_entries.py::_PARAMS`, the catalog's
words for `template_params`. Both keep their old text: the new words are appended, so a host
that matched the old text still finds it.

The oracles:

- each text is the old text with the new words appended, read from the live refusal and the
  live catalog, not from the module constants;
- each claim the new words make is run against the product: the caps they name are the step's
  constants, an edit without `holes` removes them, a v1 template refuses them until an edit names
  version 2, and the way out the refusal names (an edit of the params' holes at version 2) works;
- break-once mutants of each text (`WAYS_OUT_ROWS`, `PARAMS_ROWS`) are each killed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

import pytest

import apeCAD.draft.templates as draft_templates
from apeCAD import Document
from apeCAD.catalog import list_ops
from apeCAD.errors import TemplateLockedError
from apeCAD.geometry import XYZ
from apeCAD.ops import PointAt
from apeCAD.section.templates import holes
from apeCAD.section.templates.plan import TemplateParamError
from test_section_template_lock import WAYS_OUT

Json = dict[str, object]

OLD_WAYS_OUT = "edit the template's params, delete the template, or explode it (ADR 0040)"
OLD_PARAMS = (
    "The template's parameters, an object: lengths in mm, bars as designations from the "
    "closed vocabulary, `material` (required) and, on a template that places bars, "
    "`bar_material` (optional) as names. A missing, unknown or out-of-range one is refused "
    "by name (INVALID_ARGUMENT)."
)
OLD_EDIT = " They replace the old params whole."
RECT: Json = {
    "material": "C30", "b": 400, "h": 600, "center_mm": [200, 300], "cover": 40, "nx": 3,
    "ny": 3, "bar": "Ø20", "tie": "Ø10", "tie_spacing": 150,
}  # fmt: skip
DUCT: Json = {"center_mm": [0, 0], "radius_mm": 50}  # Errata 18.3's accepted duct


# --- _WAYS_OUT ------------------------------------------------------------------------------


def locked_message() -> str:
    """The refusal of `AddFaceHole` on a template's face: the route 13.3 keeps locked."""
    doc = Document()
    doc.add_section_template("rect_column", RECT, template_version=1)
    (face,) = doc.section_faces()
    with pytest.raises(TemplateLockedError) as caught:
        doc.add_face_hole(face.entity_id, center_id=PointAt(XYZ(200.0, 300.0, 0.0)), radius_mm=50.0)
    return str(caught.value)


def ways_out_pinned(message: str) -> bool:
    """The message ends with the pinned ways out: the old words first, then `holes`."""
    return message.endswith(f"; {WAYS_OUT}") and WAYS_OUT.startswith(OLD_WAYS_OUT)


def test_the_ways_out_keep_their_old_text_and_append_holes() -> None:
    assert WAYS_OUT.startswith(OLD_WAYS_OUT + "; ") and "holes" not in OLD_WAYS_OUT
    tail = WAYS_OUT[len(OLD_WAYS_OUT) :]
    assert "holes" in tail and "template_version 2" in tail
    message = locked_message()
    assert message.startswith("template child is locked: ")
    assert ways_out_pinned(message), message


def test_the_way_out_the_refusal_names_works() -> None:
    """"edit its params' holes (template_version 2)": the edit keeps the template and draws
    the hole that `AddFaceHole` was refused, as a child (Errata 13.3, 13.4)."""
    doc = Document()
    template = doc.add_section_template("rect_column", RECT, template_version=1)
    edited = doc.edit_section_template(
        template.entity_id, {**RECT, "holes": [DUCT]}, template_version=2
    )
    assert edited.template_version == 2
    (face,) = doc.section_faces()
    assert len(face.holes) == 1 and face.entity_id in edited.child_ids


@dataclass(frozen=True)
class WaysOutRow:
    name: str
    text: str


WAYS_OUT_ROWS = (
    WaysOutRow("old_text_dropped", WAYS_OUT[len(OLD_WAYS_OUT) + 2 :]),
    WaysOutRow("holes_dropped", OLD_WAYS_OUT),
    WaysOutRow("prepended", WAYS_OUT[len(OLD_WAYS_OUT) + 2 :] + "; " + OLD_WAYS_OUT),
    WaysOutRow("old_text_edited", WAYS_OUT.replace("explode it", "explode the template")),
    WaysOutRow("version_1", WAYS_OUT.replace("template_version 2", "template_version 1")),
    WaysOutRow("word_hole", WAYS_OUT.replace("params' holes", "params' hole")),
)


@pytest.mark.parametrize("row", WAYS_OUT_ROWS, ids=[r.name for r in WAYS_OUT_ROWS])
def test_each_ways_out_row_is_killed(row: WaysOutRow, monkeypatch: pytest.MonkeyPatch) -> None:
    assert row.text != draft_templates._WAYS_OUT  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(draft_templates, "_WAYS_OUT", row.text)
    assert not ways_out_pinned(locked_message()), f"{row.name} survives"


def test_the_ways_out_rows_are_distinct() -> None:
    assert len({r.name for r in WAYS_OUT_ROWS}) == len({r.text for r in WAYS_OUT_ROWS}) == 6


# --- _PARAMS --------------------------------------------------------------------------------


def described(op: str) -> str:
    rows = {cast(str, row["name"]): row for row in list_ops()}
    params = cast(Json, rows[op]["params"])
    field = cast(Json, cast(Json, params["properties"])["template_params"])
    return cast(str, field["description"])


def params_pinned(add: str, edit: str) -> bool:
    """The add row is the old words, then the holes words; the edit row is the add row, then
    the old edit words, then the edit's holes words. Each number is the step's constant."""
    if not add.startswith(OLD_PARAMS + " ") or not edit.startswith(add + OLD_EDIT + " "):
        return False
    tail, edit_tail = add[len(OLD_PARAMS) :], edit[len(add + OLD_EDIT) :]
    claims = (
        "Version 2 of every template also takes `holes` (optional)",
        f"at most {holes.MAX_HOLES} holes",
        "a circle {center_mm: [x, y], radius_mm}",
        "a simple ring {ring_mm: [[x, y], ...]} of 3 or more vertices",
        f"at most {holes.MAX_HOLE_VERTICES} vertices across the rings",
        "mm offsets from center_mm (on polygon_column, section coordinates)",
        "inside the concrete face and clear the face's own holes, the other holes, the cover, "
        "the bars, crossties, hoops and circular ties",  # R1 to R7, in order (Errata 17.4)
        "contact is a clash, refused by name (R1 to R7)",
    )
    edit_claims = (
        "An edit without `holes` removes them",
        "a version 1 template takes them only by an edit that names template_version 2",
    )
    return all(c in tail for c in claims) and all(c in edit_tail for c in edit_claims)


def test_the_params_words_keep_their_old_text_and_append_holes() -> None:
    add, edit = described("AddSectionTemplate"), described("EditSectionTemplate")
    assert "holes" not in OLD_PARAMS
    assert params_pinned(add, edit), (add, edit)
    assert (holes.MAX_HOLES, holes.MAX_HOLE_VERTICES) == (32, 256)  # Errata 16.2


def test_what_the_edit_words_say_holds() -> None:
    """"An edit without `holes` removes them; a version 1 template takes them only by an edit
    that names template_version 2" (Errata 13.4)."""
    doc = Document()
    held = doc.add_section_template("rect_column", {**RECT, "holes": [DUCT]}, template_version=2)
    doc.edit_section_template(held.entity_id, {**RECT, "b": 420})
    (face,) = doc.section_faces()
    assert face.holes == ()
    doc = Document()
    old = doc.add_section_template("rect_column", RECT, template_version=1)
    with pytest.raises(TemplateParamError) as caught:
        doc.edit_section_template(old.entity_id, {**RECT, "holes": [DUCT]})
    assert caught.value.param == "holes" and "unknown parameter" in str(caught.value)
    doc.edit_section_template(old.entity_id, {**RECT, "holes": [DUCT]}, template_version=2)
    (face,) = doc.section_faces()
    assert len(face.holes) == 1


@dataclass(frozen=True)
class ParamsRow:
    name: str
    mutate: Callable[[str, str], tuple[str, str]]


def _both(old: str, new: str) -> Callable[[str, str], tuple[str, str]]:
    return lambda add, edit: (add.replace(old, new), edit.replace(old, new))


CUT = len(OLD_PARAMS) + 1  # where the appended words start

PARAMS_ROWS = (
    ParamsRow("old_text_dropped", lambda a, e: (a[CUT:], e[CUT:])),
    ParamsRow("holes_dropped",
              lambda a, e: (OLD_PARAMS, OLD_PARAMS + OLD_EDIT + e[len(a + OLD_EDIT) :])),
    ParamsRow("prepended", lambda a, e: (a[CUT:] + " " + OLD_PARAMS, e[CUT:] + " " + OLD_PARAMS)),
    ParamsRow("old_text_edited", _both("refused by name (INVALID", "refused (INVALID")),
    ParamsRow("cap_33", _both("at most 32 holes", "at most 33 holes")),
    ParamsRow("cap_255", _both("at most 256 vertices", "at most 255 vertices")),
    ParamsRow("ring_form_dropped", _both(" or a simple ring {ring_mm: [[x, y], ...]}", "")),
    ParamsRow("offsets_dropped", _both("mm offsets from center_mm", "mm")),
    ParamsRow("contact_dropped", _both("contact is a clash, refused", "refused")),
    ParamsRow("hoops_dropped", _both("crossties, hoops and circular", "crossties and circular")),
    ParamsRow("edit_holes_dropped", lambda a, e: (a, a + OLD_EDIT)),
    ParamsRow("edit_version_1", _both("names template_version 2", "names template_version 1")),
    ParamsRow("edit_old_text_dropped", lambda a, e: (a, e.replace(OLD_EDIT, ""))),
)  # fmt: skip


@pytest.mark.parametrize("row", PARAMS_ROWS, ids=[r.name for r in PARAMS_ROWS])
def test_each_params_row_is_killed(row: ParamsRow) -> None:
    add, edit = described("AddSectionTemplate"), described("EditSectionTemplate")
    mutated = row.mutate(add, edit)
    assert mutated != (add, edit), f"{row.name} no longer applies"
    assert not params_pinned(*mutated), f"{row.name} survives"


def test_the_params_rows_are_distinct() -> None:
    add, edit = described("AddSectionTemplate"), described("EditSectionTemplate")
    assert len({r.name for r in PARAMS_ROWS}) == len({r.mutate(add, edit) for r in PARAMS_ROWS})
