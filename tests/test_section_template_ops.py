"""Section-template ops, entity and materialiser (ADR 0040, stage C3-S2, apeSection#49).

Add, edit, explode and delete; the committed op's version and child ids; replay, undo and
a frozen log; the catalog; the one materialiser on a synthetic circle plan (C4's forms);
the stage-S2 draft refusal; the seams that must not crash on a templated document; and
the cost of the lock on a document without templates.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import cast

import pytest

from apeCAD import Document
from apeCAD.agent import LocalTools
from apeCAD.catalog import CATALOG, apply, list_ops
from apeCAD.draft import dispatch
from apeCAD.draft.state import DraftState
from apeCAD.draft.templates import materialise
from apeCAD.entities import (
    Bar,
    CircleBoundary,
    CircularTie,
    CoverGuide,
    Crosstie,
    Entity,
    Hoop,
    Line,
    Point,
    RingBoundary,
    SectionFace,
    SectionTemplate,
)
from apeCAD.errors import INVALID_ARGUMENT, REFUSED, DocumentError, OpArgumentError
from apeCAD.ops import AddSectionTemplate, op_from_dict, op_to_dict
from apeCAD.scratchpad.payload import scene_payload
from apeCAD.section.lint import lint_section_v2
from apeCAD.section.templates.plan import (
    Plan,
    PlanBar,
    PlanCircle,
    PlanCircularTie,
    PlanCoverGuide,
    PlanFace,
    PlanHoop,
    PlanRing,
    PlanSteelShape,
)
from apeCAD.section_draft import section_draft, section_seed

RECT: dict[str, object] = {
    "material": "C30", "b": 400, "h": 600, "center_mm": [200, 300], "cover": 40, "nx": 3,
    "ny": 3, "bar": "Ø20", "tie": "Ø10", "tie_spacing": 150, "crossties": "all",
}  # fmt: skip
SMALL: dict[str, object] = {
    "material": "C30", "b": 300, "h": 300, "cover": 40, "nx": 2, "ny": 2, "bar": "Ø16",
    "tie": "Ø10", "tie_spacing": 150,
}  # fmt: skip

# Recorded by this slice and never regenerated: an add, an edit that moves and widens the
# column, and an unrelated line. Replay must rebuild exactly this drawing (ADR 0040 dec. 4).
FROZEN_LOG: list[dict[str, object]] = [
    {"op": "AddSectionTemplate", "template": "rect_column", "template_version": 1,
     "params": {"material": "C30", "b": 300, "h": 300, "cover": 40, "nx": 2, "ny": 2,
                "bar": "Ø16", "tie": "Ø10", "tie_spacing": 150},
     "label": "C1", "entity_id": 1, "child_ids": list(range(2, 17))},
    {"op": "EditSectionTemplate", "template_id": 1, "template_version": 1,
     "params": {"material": "C30", "b": 400, "h": 300, "cover": 40, "nx": 2, "ny": 2,
                "bar": "Ø16", "tie": "Ø10", "tie_spacing": 150, "center_mm": [1000, 0]},
     "child_ids": list(range(17, 32))},
    {"op": "AddPoint", "x_mm": 0, "y_mm": 1000, "z_mm": 0, "label": None, "entity_id": 32},
    {"op": "AddPoint", "x_mm": 500, "y_mm": 1000, "z_mm": 0, "label": None, "entity_id": 33},
    {"op": "AddLine", "start_id": 32, "end_id": 33, "label": None, "entity_id": 34},
]  # fmt: skip


def _doc(params: dict[str, object] = RECT) -> tuple[Document, SectionTemplate]:
    doc = Document()
    return doc, doc.add_section_template("rect_column", params)


def _entities(doc: Document) -> dict[int, Entity]:
    return {i: doc.entity(i) for i in doc.entity_ids()}


def _kinds(doc: Document, ids: tuple[int, ...]) -> list[str]:
    return [type(doc.entity(i)).__name__ for i in ids]


def _bar_xy(doc: Document) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for bar in doc.bars():
        point = doc.entity(bar.point_id)
        assert isinstance(point, Point)
        out.append((point.xyz_mm.x_mm, point.xyz_mm.y_mm))
    return out


# --- add ---------------------------------------------------------------------------------


def test_add_draws_the_plan_as_plain_v2_entities() -> None:
    doc, template = _doc()
    assert (template.template, template.template_version) == ("rect_column", 1)
    assert dict(template.params) == {**RECT, "center_mm": (200, 300)}  # stored read-only
    # 4 ring points, the face, 8 x (point, bar), the hoop, 2 crossties, the cover guide.
    assert _kinds(doc, template.child_ids) == [
        *["Point"] * 4, "SectionFace", *["Point", "Bar"] * 8, "Hoop", "Crosstie", "Crosstie",
        "CoverGuide",
    ]  # fmt: skip
    assert template.child_ids == tuple(range(2, 27))  # template first, then its children
    assert all(doc.entity(i).label is None for i in template.child_ids)
    (face,) = doc.section_faces()
    assert face.role == "concrete" and face.material == "C30" and not face.holes
    assert isinstance(face.boundary, RingBoundary)
    assert sorted(_bar_xy(doc)) == sorted(
        (x, y) for x in (60.0, 200.0, 340.0) for y in (60.0, 300.0, 540.0) if (x, y) != (200, 300)
    )
    (hoop,) = doc.hoops()
    assert len(hoop.bar_ids) == 4 and hoop.designation == "Ø10" and hoop.spacing_mm == 150.0
    assert {c.hooks for c in doc.crossties()} == {"135-135"}
    (guide,) = doc.cover_guides()
    assert (guide.face_id, guide.cover_mm) == (face.entity_id, 40.0)
    assert lint_section_v2(_entities(doc)) == ()  # C3 record §2: oracle expansions lint clean


def test_the_committed_op_records_version_entity_and_child_ids() -> None:
    doc, template = _doc()
    (op,) = doc.ops()
    assert isinstance(op, AddSectionTemplate)
    assert (op.template_version, op.entity_id, op.child_ids) == (1, 1, template.child_ids)
    payload = op_to_dict(op)
    assert payload["params"] == RECT and payload["template_version"] == 1
    assert op_from_dict(json.loads(json.dumps(payload))) == op


def test_children_get_fresh_points_and_later_ops_never_reuse_them() -> None:
    doc = Document()
    corner = doc.add_point(0.0, 0.0, 0.0).entity_id  # at the template's ring corner
    template = doc.add_section_template("rect_column", RECT)
    (face,) = doc.section_faces()
    assert isinstance(face.boundary, RingBoundary)
    assert corner not in face.boundary.point_ids  # not reused by the template
    line = doc.add_line(  # coordinates within 1 mm of a template point make a new point
        doc.add_point(0.4, 0.0, 0.0).entity_id, doc.add_point(-500.0, 0.0, 0.0).entity_id
    )
    assert not set((line.start_id, line.end_id)) & set(template.child_ids)


def test_bad_params_are_invalid_argument_and_change_nothing() -> None:
    doc = Document()
    for params, param in (({**RECT, "b": -1}, "b"), ({**RECT, "nx": 10**9}, "nx")):
        with pytest.raises(OpArgumentError) as caught:
            doc.add_section_template("rect_column", params)
        assert caught.value.code == INVALID_ARGUMENT and f": {param}: " in str(caught.value)
    with pytest.raises(OpArgumentError, match="box_column: template: unknown template"):
        doc.add_section_template("box_column", RECT)
    with pytest.raises(OpArgumentError, match="template_version: unknown version 2"):
        doc.add_section_template("rect_column", RECT, template_version=2)
    assert doc.ops() == () and doc.entity_ids() == frozenset()


# --- edit, explode, delete -------------------------------------------------------------


def test_edit_keeps_the_template_id_and_redraws_with_fresh_ids() -> None:
    doc, template = _doc()
    old = template.child_ids
    edited = doc.edit_section_template(template.entity_id, {**RECT, "center_mm": [1200, 300]})
    assert edited.entity_id == template.entity_id and edited.template_version == 1
    assert min(edited.child_ids) > max(old) and len(edited.child_ids) == len(old)
    assert not set(old) & doc.entity_ids()
    # Moving a template is an edit of its centre: every bar moves by (1000, 0).
    assert sorted(_bar_xy(doc)) == sorted(
        (x + 1000.0, y) for x in (60.0, 200.0, 340.0) for y in (60.0, 300.0, 540.0)
        if (x, y) != (200, 300)
    )  # fmt: skip


def test_edit_replaces_params_whole() -> None:
    doc, template = _doc()
    trimmed = {k: v for k, v in RECT.items() if k != "crossties"}
    edited = doc.edit_section_template(template.entity_id, trimmed)
    assert "crossties" not in edited.params and doc.crossties() == ()  # not merged
    with pytest.raises(OpArgumentError, match=r"rect_column: \w+: required"):
        doc.edit_section_template(template.entity_id, {"b": 450})


def test_explode_keeps_the_children_and_an_edit_after_it_is_refused() -> None:
    doc, template = _doc()
    before = {i: doc.entity(i) for i in template.child_ids}
    doc.explode_section_template(template.entity_id)
    assert doc.section_templates() == ()
    assert template.entity_id not in doc.entity_ids()
    assert all(doc.entity(i) is entity for i, entity in before.items())  # untouched objects
    with pytest.raises(DocumentError, match=f"unknown entity id {template.entity_id}") as caught:
        doc.edit_section_template(template.entity_id, RECT)
    assert caught.value.code == REFUSED
    bar = doc.bars()[0]
    doc.set_bar_size([bar.entity_id], "Ø25")  # a freehand drawing again: no lock
    assert doc.entity(bar.entity_id) != before[bar.entity_id]


def test_delete_of_the_template_removes_the_whole_subtree_only() -> None:
    doc = Document()
    line = doc.add_line(doc.add_point(0, 2000, 0).entity_id, doc.add_point(9, 2000, 0).entity_id)
    template = doc.add_section_template("rect_column", RECT)
    doc.delete([template.entity_id])
    assert doc.entity_ids() == {line.entity_id, line.start_id, line.end_id}


def test_template_of_finds_the_owner_by_reverse_lookup() -> None:
    doc, template = _doc()
    bar = doc.bars()[0]
    assert doc.template_of(bar.entity_id) == template
    assert not hasattr(bar, "template_id")  # membership lives on the template only
    loose = doc.add_point(5000, 0, 0)
    assert doc.template_of(loose.entity_id) is None


# --- replay, undo, a frozen log ---------------------------------------------------------


def test_replay_undo_and_redo_give_identical_ids() -> None:
    doc, template = _doc()
    doc.edit_section_template(template.entity_id, {**RECT, "b": 500})
    after_edit = doc.to_json()
    replayed = Document.from_json(after_edit)
    assert replayed.to_json() == after_edit
    assert {i: replayed.entity(i) for i in replayed.entity_ids()} == {
        i: doc.entity(i) for i in doc.entity_ids()
    }
    doc.undo()  # back to the first expansion, with its ids
    assert doc.section_templates()[0].child_ids == template.child_ids
    doc.redo()
    assert doc.to_json() == after_edit


def test_a_frozen_log_replays_to_the_same_drawing() -> None:
    doc = Document.from_dict({"schema": "apeCAD.document.v1", "units": "mm", "ops": FROZEN_LOG})
    (template,) = doc.section_templates()
    assert (template.entity_id, template.label) == (1, "C1")
    assert template.child_ids == tuple(range(17, 32))
    # b = 400, h = 300 at (1000, 0); d = 40 + 10 + 16 / 2 = 58.
    assert sorted(_bar_xy(doc)) == [(858.0, -92.0), (858.0, 92.0), (1142.0, -92.0), (1142.0, 92.0)]
    assert len(doc.entity_ids()) == 1 + 15 + 3
    assert [op_to_dict(op) for op in doc.ops()] == json.loads(json.dumps(FROZEN_LOG))


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"child_ids": list(range(2, 16))}, "records 14 child ids, but its expansion draws more"),
        ({"child_ids": list(range(2, 18))}, "records 16 child ids, but its expansion draws fewer"),
        ({"template_version": 2}, "template_version: unknown version 2"),
        ({"template_version": 1.0}, "template_version must be a whole number"),
        ({"params": [1]}, "params must be an object"),
    ],
)
def test_replay_refuses_a_log_that_no_longer_matches(
    change: dict[str, object], message: str
) -> None:
    log = [dict(FROZEN_LOG[0], **change)]
    with pytest.raises(DocumentError, match=message):
        Document.from_dict({"schema": "apeCAD.document.v1", "units": "mm", "ops": log})


# --- the catalog ------------------------------------------------------------------------


def test_the_catalog_lists_and_applies_the_template_ops() -> None:
    names = {item["name"] for item in list_ops()}
    assert {"AddSectionTemplate", "EditSectionTemplate", "ExplodeSectionTemplate"} <= names
    assert CATALOG["AddSectionTemplate"].params["properties"]["params"]["type"] == "object"  # type: ignore[index]
    doc = Document()
    applied = apply(doc, "AddSectionTemplate", {"template": "rect_column", "params": RECT})
    assert applied.created_id == 1 and len(applied.added) == 26
    edited = apply(doc, "EditSectionTemplate", {"template_id": 1, "params": SMALL})
    assert len(edited.removed) == 25 and len(edited.added) == 15
    exploded = apply(doc, "ExplodeSectionTemplate", {"template_id": 1})
    assert exploded.removed == (1,) and exploded.added == ()


@pytest.mark.parametrize(
    ("params", "fragment"),
    [
        ({"template": "rect_column", "params": {**RECT, "cover": 0}}, "cover: must be positive"),
        ({"template": "rect_column", "params": {**RECT, "zz": 1}}, "zz: unknown parameter"),
        ({"template": "rect_column", "params": "b=400"}, "params must be object"),
        ({"template": "rect_column", "params": RECT, "child_ids": [5]}, "child_ids"),
        ({"template": "box_column", "params": RECT}, "unknown template"),
        ({"template": "rect_column", "params": RECT, "template_version": 0}, "unknown version"),
    ],
)
def test_a_bad_catalog_call_is_invalid_argument(params: dict[str, object], fragment: str) -> None:
    doc = Document()
    with pytest.raises(OpArgumentError, match=fragment) as caught:
        apply(doc, "AddSectionTemplate", params)
    assert caught.value.code == INVALID_ARGUMENT
    assert doc.ops() == ()


# --- the materialiser carries C4's forms -----------------------------------------------


def test_the_materialiser_builds_circles_holes_steel_and_circular_ties() -> None:
    ring = PlanRing(((-30.0, -30.0), (30.0, -30.0), (30.0, 30.0), (-30.0, 30.0)))
    plan = Plan(
        faces=(
            PlanFace("concrete", "C50", PlanCircle((0.0, 0.0), 190.0)),
            PlanFace(
                "steel", "S355", PlanCircle((0.0, 0.0), 200.0),
                holes=(PlanCircle((0.0, 0.0), 190.0),),
                shape=PlanSteelShape("AISC 16", "HSS16x0.375", (0.0, 0.0), 15.0),
            ),
            PlanFace("void", None, ring),
        ),
        bars=tuple(
            PlanBar(150.0 * math.cos(k * math.pi / 2), 150.0 * math.sin(k * math.pi / 2), "Ø20",
                    20.0, "A630")
            for k in range(4)
        ),
        hoops=(PlanHoop((0, 1, 2, 3), "Ø10", 10.0, 100.0),),
        circular_ties=(PlanCircularTie("spiral", (0.0, 0.0), 165.0, "Ø10", 10.0, 75.0),),
        cover_guides=(PlanCoverGuide(0, 15.0, 10.0, 20.0),),
    )  # fmt: skip
    state = DraftState()
    ids = materialise(state, plan, (), "a synthetic plan")
    kinds = [type(state.entities[i]).__name__ for i in ids]
    assert kinds == [
        "Point", "SectionFace", "Point", "Point", "SectionFace", *["Point"] * 4, "SectionFace",
        *["Point", "Bar"] * 4, "Hoop", "Point", "CircularTie", "CoverGuide",
    ]  # fmt: skip
    core, tube, void = (e for i in ids if isinstance(e := state.entities[i], SectionFace))
    assert isinstance(core, SectionFace) and isinstance(core.boundary, CircleBoundary)
    assert isinstance(tube, SectionFace) and tube.role == "steel" and tube.shape is not None
    assert tube.shape.designation == "HSS16x0.375" and tube.shape.rotation_deg == 15.0
    assert isinstance(tube.holes[0], CircleBoundary) and tube.holes[0].radius_mm == 190.0
    assert isinstance(void, SectionFace) and void.material is None
    bars = [e for e in state.entities.values() if isinstance(e, Bar)]
    assert {b.material for b in bars} == {"A630"}
    (tie,) = [e for e in state.entities.values() if isinstance(e, CircularTie)]
    assert (tie.kind, tie.centerline_radius_mm, tie.pitch_mm) == ("spiral", 165.0, 75.0)
    (guide,) = [e for e in state.entities.values() if isinstance(e, CoverGuide)]
    assert guide.face_id == core.entity_id
    (hoop,) = [e for e in state.entities.values() if isinstance(e, Hoop)]
    assert hoop.bar_ids == tuple(b.entity_id for b in bars)
    # Replay with the recorded ids rebuilds the same entities.
    again = DraftState()
    assert materialise(again, plan, ids, "a synthetic plan") == ids
    assert again.entities == state.entities


def test_the_materialiser_hoop_equals_add_hoop() -> None:
    # The plan's hull indices give the ring `add_hoop` would store for the same bars.
    doc, _ = _doc()
    bars = [b.entity_id for b in doc.bars()]
    plain = Document()
    for x, y in _bar_xy(doc):
        plain.add_bar(x, y, "Ø20")
    hoop = plain.add_hoop([b.entity_id for b in plain.bars()], "Ø10", 150.0)
    order = {b.entity_id: k for k, b in enumerate(plain.bars())}
    (templated,) = doc.hoops()
    assert [bars.index(i) for i in templated.bar_ids] == [order[i] for i in hoop.bar_ids]


# --- until S3: the draft refuses a templated document ----------------------------------


@pytest.mark.parametrize("version", [1, 2])
def test_the_section_draft_refuses_a_template_by_name(version: int) -> None:
    doc, template = _doc()
    for write in (section_draft, section_seed):
        with pytest.raises(DocumentError, match=f"entity {template.entity_id} is a rect_column"):
            write(doc, version=version)
    doc.explode_section_template(template.entity_id)
    assert section_draft(doc, version=2)["version"] == 2  # a freehand drawing writes


# --- seams: nothing crashes on a templated document --------------------------------------


def test_every_surface_reads_a_templated_document(tmp_path: Path) -> None:
    tools = LocalTools(root=tmp_path)
    created = tools.new_document()
    name = cast(str, created["document"])
    params: dict[str, object] = {"template": "rect_column", "params": RECT}
    applied = tools.apply_op(name, "AddSectionTemplate", params)
    assert applied["ok"] is True, applied
    assert tools.inspect(name)["ok"] is True
    assert tools.query_entities(name)["ok"] is True
    assert tools.render(name)["ok"] is True
    dxf = tools.export_dxf(name)
    assert dxf["ok"] is True or cast(dict[str, object], dxf["error"])["code"] == "UNAVAILABLE"
    refused = tools.get_section_draft(name, 2)
    assert cast(dict[str, object], refused["error"])["code"] == REFUSED
    doc, _ = _doc()
    scene = scene_payload(doc)
    assert scene["document"] == doc.to_dict()
    brep = doc.brep()
    assert brep.children[1] == doc.section_templates()[0].child_ids  # the subtree
    assert all(brep.root[i] == 1 for i in doc.section_templates()[0].child_ids)
    doc.to_frame()
    assert lint_section_v2(_entities(doc)) == ()


def test_a_bar_and_line_seam_kinds_are_untouched() -> None:
    # The eight entity dataclasses gain no field (the card's Goal).
    for kind in (Bar, Hoop, Crosstie, CircularTie, CoverGuide, SectionFace, Point, Line):
        assert "template_id" not in kind.__dataclass_fields__


# --- the lock's cost on a document without templates -------------------------------------


def test_the_lock_costs_nothing_without_templates(monkeypatch: pytest.MonkeyPatch) -> None:
    doc = Document()
    for k in range(400):
        doc.add_line(doc.add_point(k, 0, 0).entity_id, doc.add_point(k, 50, 0).entity_id)
    payload = doc.to_dict()

    def best(n: int = 7) -> float:
        times: list[float] = []
        for _ in range(n):
            start = time.perf_counter()
            Document.from_dict(payload)
            times.append(time.perf_counter() - start)
        return min(times)

    guarded = best()
    bare = dispatch.apply_op

    def unguarded(state: DraftState, op: object) -> object:
        return dispatch.HANDLERS[type(op)](state, op)

    monkeypatch.setattr("apeCAD.document.apply_op", unguarded)
    plain = best()
    monkeypatch.setattr("apeCAD.document.apply_op", bare)
    assert guarded < plain * 1.15 + 0.002, (guarded, plain)
