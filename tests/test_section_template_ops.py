"""Section-template ops, entity and materialiser (ADR 0040, stage C3-S2, apeSection#49).

Add, edit, explode and delete; the committed op's version and child ids; replay, undo and
a frozen log; the catalog; the one materialiser on a synthetic circle plan (C4's forms);
version 1's draft refusal; the seams that must not crash on a templated document; and
the cost of the lock on a document without templates.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from threading import Thread
from typing import cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from _section_fixtures_v2 import T_BEAM_PARAMS
from apeCAD import Document
from apeCAD import document as document_module
from apeCAD.agent import LocalTools, tools
from apeCAD.agent.mcp_tools import TOOLS
from apeCAD.agent.session import Session
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
from apeCAD.ops import AddSectionTemplate, EditSectionTemplate, op_from_dict, op_to_dict
from apeCAD.ops.templates import MAX_PARAMS_DEPTH, MAX_PARAMS_VALUES, freeze_params
from apeCAD.ops.types import SCHEMA_ID
from apeCAD.scratchpad.payload import scene_payload
from apeCAD.scratchpad.server import ScratchpadServer
from apeCAD.section.lint import lint_section_v2
from apeCAD.section.templates.plan import (
    MAX_TEMPLATE_BARS,
    Plan,
    PlanBar,
    PlanCircle,
    PlanCircularTie,
    PlanCoverGuide,
    PlanFace,
    PlanHoop,
    PlanRing,
    PlanSteelShape,
    shown,
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
     "template_params": {"material": "C30", "b": 300, "h": 300, "cover": 40, "nx": 2, "ny": 2,
                "bar": "Ø16", "tie": "Ø10", "tie_spacing": 150},
     "label": "C1", "entity_id": 1, "child_ids": list(range(2, 17))},
    {"op": "EditSectionTemplate", "template_id": 1, "template_version": 1,
     "template_params": {"material": "C30", "b": 400, "h": 300, "cover": 40, "nx": 2, "ny": 2,
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
    assert payload["template_params"] == RECT and payload["template_version"] == 1
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
    ("index", "change", "message"),
    [
        (0, {"child_ids": list(range(2, 16))}, "records 14 child ids, but .* draws more"),
        (0, {"child_ids": list(range(2, 18))}, "records 16 child ids, but .* draws fewer"),
        (0, {"template_version": 2}, "template_version: unknown version 2"),
        (0, {"template_version": 1.0}, "template_version must be a whole number"),
        (0, {"template_params": [1]}, "template_params must be an object"),
        # Review of #57, finding 1: a child cannot take the template's own id.
        (0, {"child_ids": [1, *range(100, 114)]}, "records its own id among its child_ids"),
        # Finding 3: recorded ids must be the fresh ids live allocation gives, in order.
        (0, {"child_ids": list(range(16, 1, -1))}, "child id 16 where .* allocates 2"),
        (0, {"child_ids": list(range(3, 18))}, "child id 3 where .* allocates 2"),
        (1, {"child_ids": list(range(2, 17))}, "child id 2 where .* allocates 17"),
    ],
    ids=["fewer", "more", "version-2", "version-float", "params-list", "own-id", "reversed",
         "shifted", "edit-reuses-old-ids"],
)  # fmt: skip
def test_replay_refuses_a_log_that_no_longer_matches(
    index: int, change: dict[str, object], message: str
) -> None:
    log = [*FROZEN_LOG[:index], dict(FROZEN_LOG[index], **change)]
    with pytest.raises(DocumentError, match=message):
        Document.from_dict({"schema": "apeCAD.document.v1", "units": "mm", "ops": log})


def test_a_child_cannot_claim_the_template_id_live() -> None:
    doc = Document()
    op = AddSectionTemplate("rect_column", SMALL, child_ids=(1, *range(100, 114)))
    with pytest.raises(DocumentError, match="records its own id among its child_ids"):
        doc.apply(op)
    assert doc.ops() == ()


# --- the catalog ------------------------------------------------------------------------


def test_the_catalog_lists_and_applies_the_template_ops() -> None:
    names = {item["name"] for item in list_ops()}
    assert {"AddSectionTemplate", "EditSectionTemplate", "ExplodeSectionTemplate"} <= names
    assert CATALOG["AddSectionTemplate"].params["properties"]["template_params"]["type"] == "object"  # type: ignore[index]
    doc = Document()
    applied = apply(doc, "AddSectionTemplate", {"template": "rect_column", "template_params": RECT})
    assert applied.created_id == 1 and len(applied.added) == 26
    edited = apply(doc, "EditSectionTemplate", {"template_id": 1, "template_params": SMALL})
    assert len(edited.removed) == 25 and len(edited.added) == 15
    exploded = apply(doc, "ExplodeSectionTemplate", {"template_id": 1})
    assert exploded.removed == (1,) and exploded.added == ()


def _rect(**changes: object) -> dict[str, object]:
    """AddSectionTemplate catalog params for RECT, with `changes`."""
    return {"template": "rect_column", "template_params": RECT, **changes}


@pytest.mark.parametrize(
    ("params", "fragment"),
    [
        (_rect(template_params={**RECT, "cover": 0}), "cover: must be positive"),
        (_rect(template_params={**RECT, "zz": 1}), "zz: unknown parameter"),
        (_rect(template_params="b=400"), "template_params must be object"),
        (_rect(child_ids=[5]), "child_ids"),
        (_rect(template="box_column"), "unknown template"),
        (_rect(template_version=0), "unknown version"),
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


# --- version 1 refuses a templated document, by name (C3-S3 writes version 2) ------------


def test_the_section_draft_v1_refuses_a_template_by_name() -> None:
    doc, template = _doc()
    for write in (section_draft, section_seed):
        with pytest.raises(DocumentError, match=f"entity {template.entity_id} is a rect_column"):
            write(doc, version=1)
    doc.explode_section_template(template.entity_id)
    assert section_draft(doc, version=2)["version"] == 2  # a freehand drawing writes


# --- seams: nothing crashes on a templated document --------------------------------------


def test_every_surface_reads_a_templated_document(tmp_path: Path) -> None:
    tools = LocalTools(root=tmp_path)
    created = tools.new_document()
    name = cast(str, created["document"])
    params: dict[str, object] = {"template": "rect_column", "template_params": RECT}
    applied = tools.apply_op(name, "AddSectionTemplate", params)
    assert applied["ok"] is True, applied
    assert tools.inspect(name)["ok"] is True
    assert tools.query_entities(name)["ok"] is True
    assert tools.render(name)["ok"] is True
    dxf = tools.export_dxf(name)
    assert dxf["ok"] is True or cast(dict[str, object], dxf["error"])["code"] == "UNAVAILABLE"
    assert tools.get_section_draft(name, 2)["ok"] is True
    refused = tools.get_section_draft(name, 1)
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


def test_the_lock_costs_nothing_without_templates() -> None:
    doc = Document()
    for k in range(400):
        doc.add_line(doc.add_point(k, 0, 0).entity_id, doc.add_point(k, 50, 0).entity_id)
    payload = doc.to_dict()

    guarded, plain = interleaved_best(payload)
    assert guarded < plain * 1.3 + 0.002, (guarded, plain)  # measured 0.98x at 6000 ops


def interleaved_best(payload: dict[str, object], rounds: int = 9) -> tuple[float, float]:
    """Best replay time with the lock guard and with a bare handler, alternating the two so
    load on a busy machine falls on both alike."""
    bare = dispatch.apply_op

    def unguarded(state: DraftState, op: object) -> object:
        return dispatch.HANDLERS[type(op)](state, op)

    guarded: list[float] = []
    plain: list[float] = []
    try:
        for _ in range(rounds):
            for runner, times in ((bare, guarded), (unguarded, plain)):
                setattr(document_module, "apply_op", runner)
                start = time.perf_counter()
                Document.from_dict(payload)
                times.append(time.perf_counter() - start)
    finally:
        setattr(document_module, "apply_op", bare)
    return min(guarded), min(plain)


# --- HTTP: the flat request form (review of #57, finding 2) ----------------------------


@pytest.fixture
def server() -> Iterator[ScratchpadServer]:
    bound = ScratchpadServer(("127.0.0.1", 0), Document())
    thread = Thread(target=bound.serve_forever, daemon=True)
    thread.start()
    yield bound
    bound.shutdown()
    bound.server_close()


def _post(server: ScratchpadServer, path: str, body: dict[str, object]) -> dict[str, object]:
    port = server.server_address[1]
    request = Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request) as response:
        loaded: object = json.loads(response.read().decode("utf-8"))
    assert isinstance(loaded, dict)
    return cast(dict[str, object], loaded)


def test_the_flat_form_reaches_the_document_over_http(server: ScratchpadServer) -> None:
    # The op field is `template_params`, so the flat form never meets the envelope's `params`.
    add = {"op": "AddSectionTemplate", "template": "rect_column", "template_params": SMALL}
    added = _post(server, "/api/op", add)
    assert added["created_id"] == 1
    edit = {"op": "EditSectionTemplate", "template_id": 1, "template_params": RECT}
    _post(server, "/api/op", edit)
    batch = _post(server, "/api/ops", {"ops": [
        {"op": "AddSectionTemplate", "template": "rect_column",
         "template_params": {**SMALL, "center_mm": [3000, 0]}},
        {"op": "EditSectionTemplate", "template_id": 1, "template_params": SMALL},
    ]})  # fmt: skip
    assert batch["ok"] is True
    results = cast(list[dict[str, object]], batch["results"])
    assert [cast(dict[str, object], r["op"])["op"] for r in results] == [
        "AddSectionTemplate", "EditSectionTemplate",
    ]  # fmt: skip
    templates = server.session.document.section_templates()
    assert [dict(t.params)["nx"] for t in templates] == [2, 2]
    assert [dict(t.params).get("center_mm") for t in templates] == [None, (3000, 0)]


# --- deep params: a named refusal, never a RecursionError (review of #57) ----------------


TOO_DEEP = "template_params nests deeper than 16 levels"
# Levels inside `center_mm`; the params object is one more. The first is one past the cap;
# 900 is the deepest the HTTP rows send, under what Python 3.11's JSON parser accepts.
DEEP = [MAX_PARAMS_DEPTH, 500, 900]


def _nested(levels: int) -> object:
    value: object = 0
    for _ in range(levels):
        value = [value]
    return value


def _deep(levels: int) -> dict[str, object]:
    return {**SMALL, "center_mm": _nested(levels)}


def _too_deep_raw(levels: int) -> str:
    """The op as text, so the test client's own JSON encoder never recurses."""
    head = json.dumps(SMALL)[:-1]
    center = "[" * levels + "0" + "]" * levels
    return (
        '{"op": "AddSectionTemplate", "template": "rect_column", '
        f'"template_params": {head}, "center_mm": {center}}}}}'
    )


def test_params_at_the_cap_pass_it_and_one_more_level_is_refused() -> None:
    # 16 levels reach the template's own check, which names center_mm and not the depth.
    with pytest.raises(OpArgumentError, match="center_mm: must be") as at_cap:
        Document().add_section_template("rect_column", _deep(MAX_PARAMS_DEPTH - 1))
    assert TOO_DEEP not in str(at_cap.value)
    with pytest.raises(OpArgumentError, match=TOO_DEEP):
        Document().add_section_template("rect_column", _deep(MAX_PARAMS_DEPTH))


def test_objects_count_as_levels_and_a_cycle_terminates() -> None:
    chain: object = 0
    for _ in range(MAX_PARAMS_DEPTH):
        chain = {"a": chain}
    with pytest.raises(OpArgumentError, match=TOO_DEEP):
        AddSectionTemplate("rect_column", {**SMALL, "zz": chain})
    cycle: list[object] = []
    cycle.append(cycle)
    with pytest.raises(OpArgumentError, match=TOO_DEEP):
        AddSectionTemplate("rect_column", {**SMALL, "center_mm": cycle})


@pytest.mark.parametrize("levels", [*DEEP, 5000])
def test_deep_params_are_invalid_argument_in_process(levels: int) -> None:
    doc, _ = _doc(SMALL)
    before = doc.to_json()
    deep = _deep(levels)
    for name, params in (
        ("AddSectionTemplate", {"template": "rect_column", "template_params": deep}),
        ("EditSectionTemplate", {"template_id": 1, "template_params": deep}),
    ):
        session = Session(Document.from_json(before))
        out = tools.apply_op(session, name, params)
        assert out["ok"] is False
        error = cast(dict[str, object], out["error"])
        assert error["code"] == INVALID_ARGUMENT and TOO_DEEP in cast(str, error["message"])
        assert session.document.to_json() == before
    log = {"schema": SCHEMA_ID, "units": "mm", "ops": [
        {"op": "AddSectionTemplate", "template": "rect_column", "template_params": deep},
    ]}  # fmt: skip
    with pytest.raises(OpArgumentError, match=TOO_DEEP):
        Document.from_dict(log)


@pytest.mark.parametrize("levels", DEEP)
@pytest.mark.parametrize(
    ("path", "wrap", "status"),
    [
        ("/api/op", "{}", 400),
        ("/api/ops", '{{"ops": [{}]}}', 400),
        ("/api/load", '{{"schema": "' + SCHEMA_ID + '", "units": "mm", "ops": [{}]}}', 400),
        ("/api/section/transport",
         '{{"transport_version": 1, "action": "apply", "document": null, "op": {}}}', 422),
    ],
)  # fmt: skip
def test_deep_params_are_answered_over_http(
    server: ScratchpadServer, path: str, wrap: str, status: int, levels: int
) -> None:
    before = server.session.document.to_json()
    port = server.server_address[1]
    body = wrap.format(_too_deep_raw(levels)).encode("utf-8")
    with pytest.raises(HTTPError) as caught:
        urlopen(Request(f"http://127.0.0.1:{port}{path}", data=body, method="POST"))
    assert caught.value.code == status
    answer = json.loads(caught.value.read().decode("utf-8"))
    error = answer["error"] if isinstance(answer["error"], dict) else answer
    assert error["code"] == INVALID_ARGUMENT
    assert TOO_DEEP in (error.get("message") or error["error"])
    assert server.session.document.to_json() == before


@pytest.mark.parametrize("levels", [MAX_PARAMS_DEPTH, 40])  # the SDK client won't send 100
def test_deep_params_come_back_from_mcp_call_tool(levels: int) -> None:
    pytest.importorskip("mcp", reason="the mcp extra is not installed")
    anyio = pytest.importorskip("anyio")
    from mcp import Client

    from apeCAD.agent.mcp import build_server

    async def call() -> dict[str, object]:
        async with Client(build_server()) as client:
            opened = await client.call_tool("new_document", {})
            result = await client.call_tool("apply_op", {
                "document": cast(dict[str, object], opened.structured_content)["document"],
                "op": "AddSectionTemplate",
                "params": {"template": "rect_column", "template_params": _deep(levels)},
            })  # fmt: skip
            assert result.is_error
            return cast(dict[str, object], result.structured_content)

    error = cast(dict[str, object], anyio.run(call)["error"])
    assert error["code"] == INVALID_ARGUMENT and TOO_DEEP in cast(str, error["message"])


# --- oversized ints: a named INVALID_ARGUMENT, never REFUSED or a ValueError (apeSection#51) --


# float(10**400) raises OverflowError; printing 10**5000 raises ValueError (the 4300-digit limit).
FLOAT_OVERFLOW = 10**400
UNPRINTABLE = 10**5000
POLYGON: dict[str, object] = {
    "material": "C30", "ring": [[0, 0], [600, 0], [600, 400], [0, 400]], "cover": 40,
    "bar": "Ø16", "spacing_max": 150, "tie": "Ø10", "tie_spacing": 150,
}  # fmt: skip
OVERSIZED: list[tuple[str, dict[str, object], str, object, str]] = [
    # template, its other params, the param, the value, the name the refusal must carry
    ("rect_column", SMALL, "b", FLOAT_OVERFLOW, "rect_column: b: must be finite"),
    ("rect_column", SMALL, "b", -FLOAT_OVERFLOW, "rect_column: b: must be finite"),
    ("rect_column", SMALL, "b", UNPRINTABLE, "rect_column: b: must be finite"),
    ("rect_column", SMALL, "b", [UNPRINTABLE], "rect_column: b: must be a number"),
    ("rect_column", SMALL, "nx", -UNPRINTABLE, "rect_column: nx: must be 2 or more"),
    ("rect_column", SMALL, "nx", UNPRINTABLE, "rect_column: nx: these parameters place"),
    ("rect_column", SMALL, "nx", [UNPRINTABLE], "rect_column: nx: must be a whole number"),
    ("rect_column", SMALL, "center_mm", [FLOAT_OVERFLOW, 0], "rect_column: center_mm: must be"),
    ("rect_column", SMALL, "center_mm", UNPRINTABLE, "rect_column: center_mm: must be"),
    ("rect_column", SMALL, "material", UNPRINTABLE, "rect_column: material: must be"),
    ("rect_column", SMALL, "bar", UNPRINTABLE, "rect_column: bar: unknown bar designation"),
    ("rect_column", SMALL, "crossties", UNPRINTABLE, "rect_column: crossties: must be one of"),
    ("polygon_column", POLYGON, "ring", [[FLOAT_OVERFLOW, 0]] * 3, "ring[0]: must be finite"),
    ("polygon_column", POLYGON, "ring", UNPRINTABLE, "polygon_column: ring: must be a list"),
    ("t_beam", T_BEAM_PARAMS, "bottom", {"n": UNPRINTABLE}, "t_beam: bottom"),
    ("t_beam", T_BEAM_PARAMS, "bottom", {"n": -UNPRINTABLE}, "t_beam: bottom"),
]  # fmt: skip


def _oversized_id(row: tuple[str, dict[str, object], str, object, str]) -> str:
    return f"{row[0]}-{row[2]}-{row[4].split(': ')[-1].replace(' ', '_')}"


@pytest.mark.parametrize("row", OVERSIZED, ids=[_oversized_id(r) for r in OVERSIZED])
def test_an_oversized_int_is_invalid_argument_on_every_in_process_path(
    row: tuple[str, dict[str, object], str, object, str],
) -> None:
    template, base, key, value, name = row
    params = {**base, key: value}
    add = {"template": template, "template_params": params}
    doc, _ = _doc(SMALL)
    before = doc.to_json()

    session = Session(Document.from_json(before))
    out = tools.apply_op(session, "AddSectionTemplate", add)
    assert out["ok"] is False
    error = cast(dict[str, object], out["error"])
    assert error["code"] == INVALID_ARGUMENT and name in cast(str, error["message"])
    assert session.document.to_json() == before

    out = tools.apply_ops(session, [{"op": "AddSectionTemplate", "params": add}], None)
    assert out["ok"] is False
    error = cast(dict[str, object], out["error"])
    assert error["code"] == INVALID_ARGUMENT and name in cast(str, error["message"])
    assert session.document.to_json() == before

    with pytest.raises(OpArgumentError, match=name.replace("[", r"\[")):
        doc.add_section_template(template, params)
    assert doc.to_json() == before

    log = {"schema": SCHEMA_ID, "units": "mm", "ops": [{"op": "AddSectionTemplate", **add}]}
    with pytest.raises(OpArgumentError, match=name.replace("[", r"\[")):
        Document.from_dict(log)


def test_an_oversized_int_is_invalid_argument_on_edit() -> None:
    doc, template = _doc(SMALL)
    before = doc.to_json()
    session = Session(doc)
    for params in ({**SMALL, "b": FLOAT_OVERFLOW}, {**SMALL, "nx": -UNPRINTABLE}):
        edit = {"template_id": template.entity_id, "template_params": params}
        out = tools.apply_op(session, "EditSectionTemplate", edit)
        assert out["ok"] is False
        assert cast(dict[str, object], out["error"])["code"] == INVALID_ARGUMENT
    assert session.document.to_json() == before


@pytest.mark.parametrize("version", [UNPRINTABLE, -UNPRINTABLE], ids=["big", "negative"])
def test_an_oversized_template_version_is_refused_by_name(version: object) -> None:
    doc, template = _doc(SMALL)
    before = doc.to_json()
    add = {"template": "rect_column", "template_version": version, "template_params": SMALL}
    edit = {
        "template_id": template.entity_id, "template_version": version, "template_params": SMALL,
    }  # fmt: skip
    session = Session(doc)
    for name, params in (("AddSectionTemplate", add), ("EditSectionTemplate", edit)):
        out = tools.apply_op(session, name, params)
        assert out["ok"] is False, name
        error = cast(dict[str, object], out["error"])
        assert error["code"] == INVALID_ARGUMENT and "template_version" in cast(
            str, error["message"]
        )
    assert session.document.to_json() == before


def test_a_template_version_holding_an_oversized_int_is_refused_by_name() -> None:
    version = cast(int, [UNPRINTABLE])  # JSON may carry anything
    with pytest.raises(OpArgumentError, match="template_version: must be a whole number"):
        AddSectionTemplate("rect_column", SMALL, template_version=version)
    with pytest.raises(OpArgumentError, match="template_version: must be a whole number"):
        EditSectionTemplate(1, SMALL, template_version=version)


def test_an_oversized_key_is_refused_by_name() -> None:
    with pytest.raises(DocumentError, match="keys must be strings"):
        AddSectionTemplate("rect_column", {**SMALL, UNPRINTABLE: 1})


@pytest.mark.parametrize(
    ("path", "status", "wrap"),
    [
        ("/api/op", 400, "{}"),
        ("/api/ops", 400, '{{"ops": [{}]}}'),
        ("/api/section/transport", 422,
         '{{"transport_version": 1, "action": "apply", "document": null, "op": {}}}'),
    ],
)  # fmt: skip
def test_a_400_digit_b_is_answered_invalid_argument_over_http(
    server: ScratchpadServer, path: str, status: int, wrap: str
) -> None:
    """A 400-digit int is JSON that parses (the limit is 4300 digits) and overflows a float."""
    before = server.session.document.to_json()
    params = json.dumps({**SMALL, "b": 0}).replace('"b": 0', f'"b": {FLOAT_OVERFLOW}')
    op = f'{{"op": "AddSectionTemplate", "template": "rect_column", "template_params": {params}}}'
    port = server.server_address[1]
    body = wrap.format(op).encode("utf-8")
    with pytest.raises(HTTPError) as caught:
        urlopen(Request(f"http://127.0.0.1:{port}{path}", data=body, method="POST"))
    assert caught.value.code == status
    answer = json.loads(caught.value.read().decode("utf-8"))
    error = answer["error"] if isinstance(answer["error"], dict) else answer
    assert error["code"] == INVALID_ARGUMENT
    assert "rect_column: b: must be finite" in (error.get("message") or error["error"])
    assert server.session.document.to_json() == before


# --- a shared-reference DAG: refused by name, never a hang (apeSection#51) ------------------


def _dag(levels: int = 5, width: int = 1000) -> object:
    """Few objects, within the depth cap, and `width ** levels` paths through them."""
    value: object = 0
    for _ in range(levels):
        value = [value] * width
    return value


def _within(seconds: float, call: Callable[[], object]) -> object:
    """`call()`, or a failure if it runs on: a daemon thread, so a hang cannot stall the suite."""
    results: list[object] = []

    def run() -> None:
        try:
            results.append(call())
        except Exception as exc:  # the refusal, or whatever else it raises, for the caller to read
            results.append(exc)

    thread = Thread(target=run, daemon=True)
    thread.start()
    thread.join(seconds)
    assert not thread.is_alive(), f"still running after {seconds} s"
    return results[0]


TOO_MANY = f"template_params holds more than {MAX_PARAMS_VALUES} values"
DAG_PARAMS: dict[str, object] = {**SMALL, "center_mm": _dag()}


def test_a_shared_reference_dag_is_refused_by_name_and_quickly() -> None:
    made = _within(10.0, lambda: AddSectionTemplate("rect_column", DAG_PARAMS))
    assert isinstance(made, OpArgumentError) and str(made) == TOO_MANY
    assert made.code == INVALID_ARGUMENT
    one_wide = _within(10.0, lambda: AddSectionTemplate("rect_column", {"zz": [0] * 10**7}))
    assert isinstance(one_wide, OpArgumentError) and str(one_wide) == TOO_MANY


def test_a_shared_reference_dag_is_refused_on_every_in_process_path() -> None:
    doc, template = _doc(SMALL)
    before = doc.to_json()
    session = Session(doc)
    add = {"template": "rect_column", "template_params": DAG_PARAMS}
    edit = {"template_id": template.entity_id, "template_params": DAG_PARAMS}
    log = {"schema": SCHEMA_ID, "units": "mm", "ops": [{"op": "AddSectionTemplate", **add}]}
    for call in (
        lambda: tools.apply_op(session, "AddSectionTemplate", add),
        lambda: tools.apply_op(session, "EditSectionTemplate", edit),
        lambda: tools.apply_ops(session, [{"op": "AddSectionTemplate", "params": add}], None),
    ):
        out = cast(dict[str, object], _within(10.0, call))
        assert out["ok"] is False
        error = cast(dict[str, object], out["error"])
        assert error["code"] == INVALID_ARGUMENT and TOO_MANY in cast(str, error["message"])
        assert session.document.to_json() == before
    replayed = _within(10.0, lambda: Document.from_dict(log))
    assert isinstance(replayed, OpArgumentError) and str(replayed) == TOO_MANY


def test_the_budget_clears_the_largest_params_any_expansion_accepts() -> None:
    """The stop condition of the slice: a section accepted today is not refused by the budget."""
    n, radius = MAX_TEMPLATE_BARS, 90_000.0
    ring = [
        [radius * math.cos(2 * math.pi * i / n), radius * math.sin(2 * math.pi * i / n)]
        for i in range(n)
    ]  # a regular polygon: one bar per vertex, at the bar cap, and strictly convex
    largest = {**POLYGON, "bar_material": "A630", "spacing_max": 1000, "ring": ring}
    assert 1 + len(largest) + 3 * n <= MAX_PARAMS_VALUES
    made = Document().add_section_template("polygon_column", largest)
    assert len(cast(tuple[object, ...], made.params["ring"])) == n
    # A DAG inside the budget still freezes, and costs what a tree of that size costs.
    assert freeze_params({"a": [[0] * 40] * 40})["a"] == ((0,) * 40,) * 40


def test_a_ring_over_the_bar_cap_is_still_refused_as_a_ring() -> None:
    ring = [[float(i), 0.0] for i in range(MAX_TEMPLATE_BARS + 1)]
    with pytest.raises(OpArgumentError, match="polygon_column: ring: has 1001 vertices"):
        Document().add_section_template("polygon_column", {**POLYGON, "ring": ring})


# --- the docs name the templates (apeSection#51) ------------------------------------------


def test_the_list_ops_tool_description_names_the_templates() -> None:
    assert "section templates" in TOOLS["list_ops"].description


def test_the_agent_surface_spec_and_its_readme_row_name_adr_0040() -> None:
    specs = Path(__file__).resolve().parents[1] / "AProjects" / "specs"
    header = (specs / "agent-surface-mcp.md").read_text(encoding="utf-8").splitlines()[3]
    assert header.startswith("**ADRs:**") and "0040" in header
    rows = (specs / "README.md").read_text(encoding="utf-8").splitlines()
    (row,) = [line for line in rows if "(agent-surface-mcp.md)" in line]
    assert "0040" in row
    assert header.removeprefix("**ADRs:** ") == row.split("|")[3].strip()


def test_shown_prints_what_it_can_and_names_what_it_cannot() -> None:
    assert shown(5) == "5" and shown([1, "a"]) == "[1, 'a']"
    assert shown(UNPRINTABLE) == "an unprintable int"
    assert shown([UNPRINTABLE]) == "an unprintable list"
