"""The section-template lock (ADR 0040 decision 3, stage C3-S2, apeSection#49).

Every op family on a template child and on the template itself: a move, delete, edit or
transform of a child is `TEMPLATE_LOCKED` and changes nothing; a tag is allowed; the
template is moved by editing its params, deleted whole, or exploded. A fuzz runs every
handler's hostile samples on a templated document and checks the lock independently.
"""

from __future__ import annotations

import zlib
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest

from apeCAD import Document
from apeCAD.draft.dispatch import HANDLERS
from apeCAD.draft.state import RecordingEntities
from apeCAD.draft.topology import referenced_ids
from apeCAD.entities import Bar, Hoop, Point, SectionFace, SectionTemplate
from apeCAD.errors import TEMPLATE_LOCKED, DocumentError, TemplateLockedError
from apeCAD.geometry import XYZ
from apeCAD.ops import (
    AddBar,
    AddCrosstie,
    AddFaceHole,
    AddHoop,
    AddLine,
    ArrayLinear,
    ArrayPolar,
    Delete,
    EditSectionTemplate,
    ExplodeSectionTemplate,
    Mirror,
    Op,
    PointAt,
    Rotate,
    SetBarSize,
    SetCover,
    SetLabel,
    SetMaterial,
    Sew,
    Simplify,
    Tag,
    Translate,
)
from test_atomic_ops import (
    _all_entities,  # pyright: ignore[reportPrivateUsage]
    _assert_live_equals_replay,  # pyright: ignore[reportPrivateUsage]
    _fixture,  # pyright: ignore[reportPrivateUsage]
    _hostile_ops,  # pyright: ignore[reportPrivateUsage]
    _snapshot,  # pyright: ignore[reportPrivateUsage]
)
from test_section_template_ops import interleaved_best

RECT: dict[str, object] = {
    "material": "C30", "b": 400, "h": 600, "center_mm": [200, 300], "cover": 40, "nx": 3,
    "ny": 3, "bar": "Ø20", "tie": "Ø10", "tie_spacing": 150, "crossties": "all",
}  # fmt: skip


class Ids:
    """The template's id and one child of each kind, from a fresh templated document."""

    def __init__(self, doc: Document, template: SectionTemplate) -> None:
        self.template = template.entity_id
        kids = [doc.entity(i) for i in template.child_ids]
        self.point = next(e.entity_id for e in kids if isinstance(e, Point))
        self.points = [e.entity_id for e in kids if isinstance(e, Point)]
        self.face = next(e.entity_id for e in kids if isinstance(e, SectionFace))
        self.bars = [e.entity_id for e in kids if isinstance(e, Bar)]
        self.hoop = next(e.entity_id for e in kids if isinstance(e, Hoop))


def _fresh() -> tuple[Document, Ids]:
    doc = Document()
    template = doc.add_section_template("rect_column", RECT)
    return doc, Ids(doc, template)


def _at(x: float, y: float) -> PointAt:
    return PointAt(XYZ(x, y, 0.0))


# (case, the op built from the ids, locked?). One row per op family, on a child and on the
# template; "allowed" rows say what the op may do.
CASES: list[tuple[str, Callable[[Ids], Op], bool]] = [
    # move / transform
    ("translate a child point", lambda i: Translate((i.point,), 10.0, 0.0, 0.0), True),
    ("translate a child bar", lambda i: Translate((i.bars[0],), 10.0, 0.0, 0.0), True),
    ("translate the template", lambda i: Translate((i.template,), 10.0, 0.0, 0.0), True),
    ("rotate a child face", lambda i: Rotate((i.face,), 0.0, 0.0, 30.0), True),
    ("rotate the template", lambda i: Rotate((i.template,), 0.0, 0.0, 30.0), True),
    ("mirror the template", lambda i: Mirror((i.template,), 0.0, 0.0, 0.0, 1.0), True),
    ("mirror a child bar", lambda i: Mirror((i.bars[0],), 0.0, 0.0, 0.0, 1.0), True),
    # delete
    ("delete a child point", lambda i: Delete((i.point,)), True),
    ("delete a child bar", lambda i: Delete((i.bars[0],)), True),
    ("delete a child hoop", lambda i: Delete((i.hoop,)), True),
    ("delete a child face", lambda i: Delete((i.face,)), True),
    ("delete the template", lambda i: Delete((i.template,)), False),
    ("delete the template and a child", lambda i: Delete((i.template, i.bars[0])), False),
    # edit (section edits, graph edits, new references)
    ("resize a child bar", lambda i: SetBarSize((i.bars[0],), "Ø25"), True),
    ("set a child face's material", lambda i: SetMaterial((i.face,), "C40"), True),
    ("set a child face's cover", lambda i: SetCover(i.face, 30.0, 10.0, 20.0), True),
    ("hole a child face", lambda i: AddFaceHole(
        i.face, point_ids=(_at(150, 250), _at(250, 300), _at(150, 350))), True),  # fmt: skip
    ("sew two child points", lambda i: Sew((i.points[0], i.points[1]), 1000.0), True),
    ("simplify a child face (Simplify refuses a v2 face itself)", lambda i: Simplify((i.face,)),
     False),  # fmt: skip
    ("label a child bar", lambda i: SetLabel(i.bars[0], "B1"), True),
    ("line between child points", lambda i: AddLine(i.points[0], i.points[1]), True),
    ("crosstie between child bars", lambda i: AddCrosstie(i.bars[0], i.bars[2], "Ø10", 150.0),
     True),  # fmt: skip
    ("hoop round child bars", lambda i: AddHoop((i.bars[0], i.bars[2], i.bars[4]), "Ø10", 150.0),
     True),  # fmt: skip
    ("edit a child as a template", lambda i: EditSectionTemplate(i.bars[0], RECT), False),
    # tag and label: allowed
    ("tag a child", lambda i: Tag("cage", (i.bars[0], i.hoop)), False),
    ("tag the template", lambda i: Tag("columns", (i.template,)), False),
    ("label the template", lambda i: SetLabel(i.template, "C1"), False),
    # copies and freehand drawing beside the template: allowed (they own nothing of it)
    ("array a child bar", lambda i: ArrayLinear((i.bars[0],), 1000.0, 0.0, 0.0, 1), False),
    ("array a child face", lambda i: ArrayPolar((i.face,), 0.0, 0.0, 3, 360.0), False),
    ("line at a child point's xy", lambda i: AddLine(_at(0, 0), _at(-500, 0)), False),
    ("bar at a child bar's xy", lambda i: AddBar(1060.0, 60.0, "Ø20"), False),
    # the template's own ops
    ("edit the template", lambda i: EditSectionTemplate(i.template, {**RECT, "b": 450}), False),
    ("explode the template", lambda i: ExplodeSectionTemplate(i.template), False),
]


@pytest.mark.parametrize(("case", "build", "locked"), CASES, ids=[c[0] for c in CASES])
def test_each_op_family_on_a_child_and_on_the_template(
    case: str, build: Callable[[Ids], Op], locked: bool
) -> None:
    doc, ids = _fresh()
    op = build(ids)
    json_before, live_before = doc.to_json(), _snapshot(doc)
    if locked:
        with pytest.raises(TemplateLockedError) as caught:
            doc.apply(op)
        assert caught.value.code == TEMPLATE_LOCKED
        assert "edit the template's params, delete the template, or explode it" in str(
            caught.value
        )
        assert doc.to_json() == json_before and _snapshot(doc) == live_before  # atomic
        return
    try:
        doc.apply(op)
    except TemplateLockedError:
        pytest.fail(f"{case} is allowed, but the lock refused it")
    except DocumentError:
        assert doc.to_json() == json_before  # refused for its own reason, by name
        return
    _assert_live_equals_replay(doc)
    _assert_lock_holds(doc)


def test_an_edit_after_an_explode_is_refused() -> None:
    doc, ids = _fresh()
    doc.explode_section_template(ids.template)
    with pytest.raises(DocumentError, match=f"unknown entity id {ids.template}"):
        doc.edit_section_template(ids.template, RECT)
    doc.translate([ids.bars[0]], 10.0, 0.0, 0.0)  # its children are freehand now


def test_a_delete_of_one_template_leaves_another_locked() -> None:
    doc = Document()
    first = doc.add_section_template("rect_column", RECT)
    second = doc.add_section_template("rect_column", {**RECT, "center_mm": [2000, 300]})
    doc.delete([first.entity_id])
    assert doc.section_templates() == (second,)
    with pytest.raises(TemplateLockedError):
        doc.delete([second.child_ids[0]])


def test_a_changed_freehand_entity_cannot_take_a_child() -> None:
    # Rule 3 on an existing entity: sewing a freehand line's end onto a template point
    # rewires the line (a write the recording map sees), not the child.
    doc, ids = _fresh()
    a = doc.add_point(0.3, 0.0, 0.0).entity_id  # 0.3 mm from the template's corner point
    line = doc.add_line(a, doc.add_point(-500.0, 0.0, 0.0).entity_id)
    json_before = doc.to_json()
    for selection in ((a, ids.points[0]), (line.entity_id, ids.points[0])):
        with pytest.raises(TemplateLockedError, match=f"line {line.entity_id} would use point"):
            doc.apply(Sew(selection, 1.0))
        assert doc.to_json() == json_before


def test_the_recording_map_keeps_the_first_old_value_of_each_write() -> None:
    entities = RecordingEntities({1: Point(1, XYZ(0, 0, 0)), 2: Point(2, XYZ(1, 0, 0))})
    first = entities[1]
    entities[1] = Point(1, XYZ(5, 0, 0))
    entities[1] = Point(1, XYZ(6, 0, 0))
    entities[3] = Point(3, XYZ(7, 0, 0))
    entities.pop(2)
    assert entities.written == {1: first, 3: None, 2: Point(2, XYZ(1, 0, 0))}
    entities.reset()
    assert entities.written == {}
    del entities[3]
    assert entities.written == {3: Point(3, XYZ(7, 0, 0))}
    with pytest.raises(NotImplementedError):
        entities.clear()


def test_the_lock_cost_does_not_grow_with_the_draft() -> None:
    # Review of #57, finding 4: the lock looks at an op's writes, not at the whole draft.
    doc = Document()
    doc.add_section_template("rect_column", {**RECT, "center_mm": [-5000, 300]})
    for k in range(1500):
        doc.add_line(doc.add_point(k, 0, 0).entity_id, doc.add_point(k, 50, 0).entity_id)
    payload = doc.to_dict()

    guarded, bare = interleaved_best(payload, rounds=5)
    assert guarded < bare * 1.6, (guarded, bare)  # 1.15x measured at 6000 ops; 2.4x before


def test_the_lock_names_the_child_and_its_template() -> None:
    doc, ids = _fresh()
    with pytest.raises(TemplateLockedError) as caught:
        doc.add_crosstie(ids.bars[0], ids.bars[2], "Ø10", 150.0)
    message = str(caught.value)
    assert f"bar {ids.bars[0]}" in message and "section template 1 (rect_column)" in message


@pytest.mark.parametrize("kind", ["linear", "polar"])
def test_an_array_of_the_template_is_refused_by_name(kind: str) -> None:
    doc, ids = _fresh()
    op: Op = (
        ArrayLinear((ids.template,), 1000.0, 0.0, 0.0, 1)
        if kind == "linear"
        else ArrayPolar((ids.template,), 0.0, 0.0, 3, 360.0)
    )
    json_before, live_before = doc.to_json(), _snapshot(doc)
    with pytest.raises(TemplateLockedError) as caught:
        doc.apply(op)
    assert caught.value.code == TEMPLATE_LOCKED
    message = str(caught.value)
    assert f"section template {ids.template} (rect_column)" in message
    assert "explode the template first to array its contents" in message
    assert doc.to_json() == json_before and _snapshot(doc) == live_before  # unchanged


# --- the fuzz: every handler's hostile samples on a templated document -------------------


def _assert_lock_holds(doc: Document) -> None:
    """The lock, checked independently of `check_template_lock`: every template's children
    exist, and nothing outside a template references one of its children."""
    owners: dict[int, int] = {}
    for template in doc.section_templates():
        for child in template.child_ids:
            assert child in doc.entity_ids(), (template, child)
            owners[child] = template.entity_id
    for entity_id in doc.entity_ids():
        entity = doc.entity(entity_id)
        if isinstance(entity, SectionTemplate):
            continue
        for ref in referenced_ids(entity):
            if ref in owners:
                assert owners.get(entity_id) == owners[ref], (entity, ref)


def _templated_fixture() -> tuple[Document, SectionTemplate]:
    doc = _fixture()
    template = doc.add_section_template("rect_column", {**RECT, "center_mm": [20000, 300]})
    return doc, template


def _aimed_at(template: SectionTemplate, ops: list[object]) -> list[object]:
    """The first samples again with the template's id first in `entity_ids`: random picks
    rarely land on one id, and every op that takes a selection must meet the template."""
    aimed: list[object] = []
    for op in ops[:6]:
        selection = getattr(op, "entity_ids", None)
        if not isinstance(selection, tuple):
            continue
        try:
            aimed.append(replace(op, entity_ids=(template.entity_id, *selection)))  # type: ignore[type-var]
        except DocumentError:
            continue
    return aimed


@pytest.mark.parametrize("op_type", list(HANDLERS), ids=lambda t: t.__name__)
def test_hostile_ops_on_a_templated_document_keep_the_lock(op_type: type[Any]) -> None:
    doc, template = _templated_fixture()
    ids = sorted(e.entity_id for e in _all_entities(doc))
    point_ids = [p.entity_id for p in doc.points()]
    seed = zlib.crc32(op_type.__name__.encode())  # the atomic test's samples
    ops = _hostile_ops(op_type, ids, point_ids, seed=seed)
    assert ops, f"no constructible {op_type.__name__} sample"
    ops += _aimed_at(template, ops)
    for op in ops:
        children = {
            t.entity_id: {c: doc.entity(c) for c in t.child_ids} for t in doc.section_templates()
        }
        json_before = doc.to_json()
        try:
            doc.apply(op)
        except DocumentError:
            assert doc.to_json() == json_before, op
            continue
        _assert_live_equals_replay(doc)
        _assert_lock_holds(doc)
        for template_id, before in children.items():
            now = doc.entity(template_id) if template_id in doc.entity_ids() else None
            if isinstance(now, SectionTemplate) and set(now.child_ids) == set(before):
                assert {c: doc.entity(c) for c in now.child_ids} == before, op
