"""Agent tool bodies in local mode (spec agent-surface-mcp §2–§5, stage S2), in-process."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from apeCAD.agent import MAX_BATCH, LocalTools
from apeCAD.ops import SCHEMA_ID


def _point(x: float, y: float = 0.0, z: float = 0.0) -> dict[str, object]:
    return {"op": "AddPoint", "params": {"x_mm": x, "y_mm": y, "z_mm": z}}


def _line(start: int, end: int) -> dict[str, object]:
    return {"op": "AddLine", "params": {"start_id": start, "end_id": end}}


def _error(envelope: dict[str, object]) -> dict[str, object]:
    assert envelope["ok"] is False
    return cast(dict[str, object], envelope["error"])


def _items(envelope: dict[str, object]) -> list[dict[str, object]]:
    assert envelope["ok"] is True, envelope
    return cast(list[dict[str, object]], envelope["items"])


@pytest.fixture
def tools(tmp_path: Path) -> LocalTools:
    return LocalTools(root=tmp_path)


@pytest.fixture
def doc(tools: LocalTools) -> str:
    created = tools.new_document()
    assert created == {"ok": True, "document": "doc-1", "revision": 0}
    return "doc-1"


def _two_points_and_a_line(tools: LocalTools, doc: str) -> None:
    result = tools.apply_ops(doc, [_point(0), _point(1000), _line(1, 2)])
    assert result["ok"] is True, result


# --- catalog and documents -------------------------------------------------------------


def test_list_ops_needs_no_document() -> None:
    listed = LocalTools().list_ops()
    assert listed["ok"] is True and listed["schema"] == SCHEMA_ID
    assert "revision" not in listed
    names = [op["name"] for op in cast(list[dict[str, object]], listed["ops"])]
    assert "AddLine" in names
    one = LocalTools().list_ops("AddLine")
    assert [op["name"] for op in cast(list[dict[str, object]], one["ops"])] == ["AddLine"]
    assert _error(LocalTools().list_ops("Nope"))["code"] == "UNKNOWN_OP"


def test_new_documents_get_sequential_ids(tools: LocalTools) -> None:
    assert tools.new_document()["document"] == "doc-1"
    assert tools.new_document()["document"] == "doc-2"


def test_unknown_document_is_not_found_without_a_revision(tools: LocalTools) -> None:
    missing = tools.inspect("doc-9")
    assert _error(missing)["code"] == "NOT_FOUND"
    assert "revision" not in missing
    assert _error(tools.inspect(cast(str, 7)))["code"] == "INVALID_ARGUMENT"


def test_save_then_open_round_trips(tools: LocalTools, doc: str, tmp_path: Path) -> None:
    _two_points_and_a_line(tools, doc)
    saved = tools.save_document(doc, "out/sketch.ape.json")
    target = tmp_path / "out" / "sketch.ape.json"
    assert saved == {
        "ok": True,
        "revision": 1,
        "path": str(target.resolve()),
        "bytes": len(target.read_bytes()),
    }
    opened = tools.open_document("out/sketch.ape.json")
    assert opened == {"ok": True, "document": "doc-2", "revision": 0, "ops": 3}
    assert tools.get_document("doc-2")["document"] == tools.get_document(doc)["document"]


def test_save_outside_the_root_is_refused(tools: LocalTools, doc: str) -> None:
    assert _error(tools.save_document(doc, "../escape.json"))["code"] == "INVALID_ARGUMENT"


def test_open_reports_io_and_replay_errors(tools: LocalTools, tmp_path: Path) -> None:
    assert _error(tools.open_document("missing.json"))["code"] == "IO_ERROR"
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    assert _error(tools.open_document("bad.json"))["code"] == "REFUSED"
    wrong = {"schema": "other.v1", "units": "mm", "ops": []}
    (tmp_path / "wrong.json").write_text(json.dumps(wrong), encoding="utf-8")
    assert _error(tools.open_document("wrong.json"))["code"] == "REFUSED"
    broken = {"schema": SCHEMA_ID, "units": "mm", "ops": [{"op": "AddLine", "start_id": 1}]}
    (tmp_path / "broken.json").write_text(json.dumps(broken), encoding="utf-8")
    assert _error(tools.open_document("broken.json"))["code"] == "REFUSED"


# --- apply_op and revision -------------------------------------------------------------


def test_apply_op_returns_applied_and_bumps_revision(tools: LocalTools, doc: str) -> None:
    result = tools.apply_op(doc, "AddPoint", {"x_mm": 0, "y_mm": 0, "z_mm": 0, "label": "o"})
    assert result["ok"] is True
    assert result["revision"] == 1
    assert result["created_id"] == 1
    assert result["added"] == [1] and result["removed"] == []
    assert cast(dict[str, object], result["op"])["entity_id"] == 1


def test_refused_op_changes_nothing(tools: LocalTools, doc: str) -> None:
    _two_points_and_a_line(tools, doc)
    before = tools.get_document(doc)
    refused = tools.apply_op(doc, "AddLine", {"start_id": 1, "end_id": 1})
    assert _error(refused)["code"] == "REFUSED"
    assert refused["revision"] == 1
    assert tools.get_document(doc) == before


@pytest.mark.parametrize(
    ("op", "params", "code"),
    [
        ("Nope", {}, "UNKNOWN_OP"),
        ("AddPoint", {"x_mm": 0, "y_mm": 0}, "INVALID_ARGUMENT"),
        ("AddPoint", {"x_mm": 0, "y_mm": 0, "z_mm": 0, "entity_id": 4}, "INVALID_ARGUMENT"),
        ("AddPoint", [1, 2], "INVALID_ARGUMENT"),
        (5, {}, "INVALID_ARGUMENT"),
    ],
)
def test_bad_arguments_are_coded(
    tools: LocalTools, doc: str, op: object, params: object, code: str
) -> None:
    result = tools.apply_op(doc, op, params)
    assert _error(result)["code"] == code
    assert result["revision"] == 0


def test_lost_reply_resend_with_old_revision_is_stale(tools: LocalTools, doc: str) -> None:
    """Apply, drop the reply, resend with the old expect_revision: STALE, applied once."""
    before = tools.inspect(doc)
    revision = before["revision"]
    params = {"x_mm": 10, "y_mm": 20, "z_mm": 0}
    tools.apply_op(doc, "AddPoint", params, expect_revision=revision)  # reply lost
    resent = tools.apply_op(doc, "AddPoint", params, expect_revision=revision)
    assert _error(resent)["code"] == "STALE"
    assert resent["revision"] == cast(int, revision) + 1
    assert tools.inspect(doc)["ops"] == cast(int, before["ops"]) + 1


def test_expect_revision_must_be_an_integer(tools: LocalTools, doc: str) -> None:
    result = tools.apply_op(doc, "AddPoint", {"x_mm": 0, "y_mm": 0, "z_mm": 0}, "0")
    assert _error(result)["code"] == "INVALID_ARGUMENT"


# --- apply_ops ---------------------------------------------------------------------------


def test_batch_is_one_revision_and_undoes_op_by_op(tools: LocalTools, doc: str) -> None:
    result = tools.apply_ops(doc, [_point(0), _point(1000), _line(1, 2)], expect_revision=0)
    assert result["ok"] is True and result["revision"] == 1
    results = cast(list[dict[str, object]], result["results"])
    assert [r["created_id"] for r in results] == [1, 2, 3]
    assert all(r["revision"] == 1 for r in results)
    undone = tools.undo(doc)
    assert undone == {"ok": True, "revision": 2, "ops": 2}


def test_batch_failing_at_index_2_leaves_the_log_byte_identical(
    tools: LocalTools, doc: str
) -> None:
    _two_points_and_a_line(tools, doc)
    tools.undo(doc)  # leave something on the redo stack too
    session = tools.session(doc)
    log = session.document.to_json()
    failed = tools.apply_ops(doc, [_point(5000), _point(6000), _line(1, 1), _point(7000)])
    error = _error(failed)
    assert error["code"] == "REFUSED" and error["index"] == 2
    assert failed["revision"] == 2
    assert session.document.to_json() == log
    assert tools.inspect(doc)["can_redo"] is True
    assert tools.redo(doc)["ops"] == 3


def test_batch_item_errors_carry_their_index(tools: LocalTools, doc: str) -> None:
    bad_item = tools.apply_ops(doc, [_point(0), "AddPoint"])
    assert _error(bad_item)["code"] == "INVALID_ARGUMENT" and _error(bad_item)["index"] == 1
    unknown = tools.apply_ops(doc, [{"op": "Nope", "params": {}}])
    assert _error(unknown)["code"] == "UNKNOWN_OP" and _error(unknown)["index"] == 0
    assert tools.inspect(doc)["ops"] == 0


def test_batch_size_and_shape_limits(tools: LocalTools, doc: str) -> None:
    too_many = tools.apply_ops(doc, [_point(float(i)) for i in range(MAX_BATCH + 1)])
    assert _error(too_many)["code"] == "TOO_LARGE"
    assert _error(tools.apply_ops(doc, []))["code"] == "INVALID_ARGUMENT"
    assert _error(tools.apply_ops(doc, {"op": "AddPoint"}))["code"] == "INVALID_ARGUMENT"
    stale = tools.apply_ops(doc, [_point(0)], expect_revision=3)
    assert _error(stale)["code"] == "STALE"
    assert tools.inspect(doc)["ops"] == 0


def test_batch_of_max_size_lands(tools: LocalTools, doc: str) -> None:
    result = tools.apply_ops(doc, [_point(float(i)) for i in range(MAX_BATCH)])
    assert result["ok"] is True and result["revision"] == 1


# --- undo and redo -----------------------------------------------------------------------


def test_undo_redo_and_their_refusals(tools: LocalTools, doc: str) -> None:
    assert _error(tools.undo(doc))["code"] == "REFUSED"
    assert _error(tools.redo(doc))["code"] == "REFUSED"
    _two_points_and_a_line(tools, doc)
    assert tools.undo(doc, expect_revision=1) == {"ok": True, "revision": 2, "ops": 2}
    assert _error(tools.redo(doc, expect_revision=1))["code"] == "STALE"
    assert tools.inspect(doc)["can_redo"] is True
    assert tools.redo(doc) == {"ok": True, "revision": 3, "ops": 3}
    assert tools.inspect(doc)["can_redo"] is False


def test_a_new_op_clears_can_redo(tools: LocalTools, doc: str) -> None:
    _two_points_and_a_line(tools, doc)
    tools.undo(doc)
    tools.apply_op(doc, "AddPoint", {"x_mm": 0, "y_mm": 5, "z_mm": 0})
    assert tools.inspect(doc)["can_redo"] is False


# --- inspect -----------------------------------------------------------------------------


def test_inspect_an_empty_draft(tools: LocalTools, doc: str) -> None:
    result = tools.inspect(doc)
    assert result["ok"] is True and result["revision"] == 0
    assert result["units"] == "mm" and result["ops"] == 0
    assert result["extents_mm"] is None
    assert set(cast(dict[str, int], result["counts"]).values()) == {0}
    assert result["can_undo"] is False and result["can_redo"] is False


def test_inspect_counts_labels_tags_and_brep(tools: LocalTools, doc: str) -> None:
    box = {"origin_xyz_mm": [0, 0, 0], "size_xyz_mm": [6000, 400, 3000], "label": "wall-A"}
    added = tools.apply_op(doc, "AddBox", box)
    solid = cast(int, added["created_id"])
    tools.apply_ops(doc, [_point(0, 1000), _point(500, 1000)])
    tools.apply_ops(doc, [_line(*_last_two(tools, doc))])
    tools.apply_op(doc, "Tag", {"name": "walls", "entity_ids": [solid]})
    result = tools.inspect(doc)
    counts = cast(dict[str, int], result["counts"])
    assert counts["solid"] == 1 and counts["face"] == 6 and counts["line"] == 13
    assert counts["point"] == 10
    assert result["extents_mm"] == {"min": [0.0, 0.0, 0.0], "max": [6000.0, 1000.0, 3000.0]}
    assert result["labels"] == {"wall-A": solid}
    assert result["tags"] == {"walls": [solid]}
    assert result["brep"] == {
        "solids": 1,
        "faces": 6,
        "edges": 12,
        "vertices": 8,
        "free_lines": 1,
    }
    assert result["can_undo"] is True


def _last_two(tools: LocalTools, doc: str) -> tuple[int, int]:
    ids = sorted(tools.session(doc).document.entity_ids())
    return ids[-2], ids[-1]


# --- query_entities ----------------------------------------------------------------------


def _grid(tools: LocalTools, doc: str) -> None:
    """Points 1-3 on y=0, line 4 from 1 to 2, a circle (centre 5, circle 6) at (5000, 0)."""
    tools.apply_ops(
        doc,
        [
            _point(0),
            _point(1000),
            _point(3000, 0, 0),
            _line(1, 2),
            {"op": "AddCircle", "params": {"center_id": {"xyz": [5000, 0, 0]}, "radius_mm": 500}},
            {"op": "SetLabel", "params": {"entity_id": 4, "label": "beam"}},
            {"op": "Tag", "params": {"name": "frame", "entity_ids": [1, 4]}},
        ],
    )


def test_query_filters(tools: LocalTools, doc: str) -> None:
    _grid(tools, doc)

    def ids(**filters: object) -> list[object]:
        return [item["id"] for item in _items(tools.query_entities(doc, **filters))]

    assert ids() == [1, 2, 3, 4, 5, 6]
    assert ids(kind="point") == [1, 2, 3, 5]
    assert ids(kind=["line", "circle"]) == [4, 6]
    assert ids(tag="frame") == [1, 4]
    assert ids(tag="none") == []
    assert ids(label="beam") == [4]
    assert ids(ids=[3, 4, 99]) == [3, 4]
    assert ids(kind="point", tag="frame") == [1]
    inside = {"min": [-1, -1, -1], "max": [1500, 1, 1], "mode": "inside"}
    assert ids(window=inside) == [1, 2, 4]
    crossing = {"min": [4400, -10, -1], "max": [4600, 10, 1], "mode": "crossing"}
    assert ids(window=crossing) == [6]
    assert ids(window={**crossing, "mode": "inside"}) == []


def test_query_summary_and_full_items(tools: LocalTools, doc: str) -> None:
    _grid(tools, doc)
    summary = _items(tools.query_entities(doc, ids=[4]))[0]
    assert summary == {
        "id": 4,
        "kind": "line",
        "label": "beam",
        "tags": ["frame"],
        "bbox_mm": {"min": [0.0, 0.0, 0.0], "max": [1000.0, 0.0, 0.0]},
    }
    full = _items(tools.query_entities(doc, ids=[4, 6], detail="full"))
    assert full[0]["start_id"] == 1 and full[0]["end_id"] == 2
    assert full[0]["brep_children"] == [1, 2] and full[0]["brep_parents"] == []
    assert full[1]["radius_mm"] == 500.0 and full[1]["center_id"] == 5
    assert full[1]["bbox_mm"] == {"min": [4500.0, -500.0, 0.0], "max": [5500.0, 500.0, 0.0]}


@pytest.mark.parametrize(
    "filters",
    [
        {"kind": "blob"},
        {"limit": 0},
        {"limit": 501},
        {"detail": "everything"},
        {"window": {"min": [0, 0, 0]}},
        {"window": {"min": [1, 0, 0], "max": [0, 0, 0]}},
        {"window": {"min": [0, 0, 0], "max": [1, 1, 1], "mode": "near"}},
        {"cursor": "garbage"},
        {"ids": [1, "2"]},
        {"colour": "red"},
    ],
)
def test_query_bad_arguments(tools: LocalTools, doc: str, filters: dict[str, object]) -> None:
    assert _error(tools.query_entities(doc, **filters))["code"] == "INVALID_ARGUMENT"


def test_query_pages_through_every_match(tools: LocalTools, doc: str) -> None:
    _grid(tools, doc)
    seen: list[object] = []
    cursor: object = None
    while True:
        page = tools.query_entities(doc, limit=4, cursor=cursor)
        assert page["total"] == 6
        seen.extend(item["id"] for item in _items(page))
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == [1, 2, 3, 4, 5, 6]


def test_paging_across_a_mutation_is_stale(tools: LocalTools, doc: str) -> None:
    _grid(tools, doc)
    first = tools.query_entities(doc, limit=2)
    cursor = first["next_cursor"]
    assert isinstance(cursor, str)
    tools.apply_op(doc, "AddPoint", {"x_mm": 9, "y_mm": 9, "z_mm": 9})
    stale = tools.query_entities(doc, limit=2, cursor=cursor)
    assert _error(stale)["code"] == "STALE"
    assert stale["revision"] == 2


# --- get_document and render -------------------------------------------------------------


def test_get_document_is_to_dict(tools: LocalTools, doc: str) -> None:
    _two_points_and_a_line(tools, doc)
    result = tools.get_document(doc)
    assert result["ok"] is True and result["revision"] == 1
    assert result["document"] == tools.session(doc).document.to_dict()


def test_render_svg(tools: LocalTools, doc: str, tmp_path: Path) -> None:
    _two_points_and_a_line(tools, doc)
    result = tools.render(doc, view="top", width=400, height=300, show_ids=True)
    assert result["ok"] is True and result["revision"] == 1
    assert result["view"] == "top" and result["width"] == 400 and result["entities"] == 3
    assert cast(str, result["svg"]).startswith("<svg")
    assert "path" not in result
    saved = tools.render(doc, save_to="renders/top.svg")
    assert saved["path"] == str((tmp_path / "renders" / "top.svg").resolve())
    assert (tmp_path / "renders" / "top.svg").read_text(encoding="utf-8") == saved["svg"]


@pytest.mark.parametrize(
    ("params", "code"),
    [
        ({"format": "png"}, "UNAVAILABLE"),
        ({"format": "gif"}, "INVALID_ARGUMENT"),
        ({"view": "bottom"}, "INVALID_ARGUMENT"),
        ({"ids": [99]}, "INVALID_ARGUMENT"),
        ({"labels": "yes"}, "INVALID_ARGUMENT"),
        ({"save_to": "../out.svg"}, "INVALID_ARGUMENT"),
        ({"window": {"min": [0, 0, 0]}}, "INVALID_ARGUMENT"),
        ({"dpi": 300}, "INVALID_ARGUMENT"),
    ],
)
def test_render_errors(
    tools: LocalTools, doc: str, params: dict[str, object], code: str
) -> None:
    _two_points_and_a_line(tools, doc)
    result = tools.render(doc, **params)
    assert _error(result)["code"] == code
    assert result["revision"] == 1
