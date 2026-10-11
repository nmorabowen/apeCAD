"""The op catalog (spec agent-surface-mcp §1, ADR 0028): schemas, `apply`, error codes."""

from __future__ import annotations

import json

import pytest

from apeCAD.catalog import CATALOG, apply, list_ops, split_request
from apeCAD.document import Document
from apeCAD.errors import (
    ERROR_CODES,
    INVALID_ARGUMENT,
    REFUSED,
    UNKNOWN_OP,
    DocumentError,
    OpArgumentError,
    UnknownOpError,
)
from apeCAD.ops import SCHEMA_ID, SUPPORTED_SCHEMA_IDS


def _square(document: Document) -> None:
    for x_mm, y_mm in ((0, 0), (4000, 0), (4000, 3000), (0, 3000)):
        apply(document, "AddPoint", {"x_mm": x_mm, "y_mm": y_mm, "z_mm": 0})


def test_error_codes_are_the_spec_table() -> None:
    assert ERROR_CODES == (
        "UNKNOWN_OP",
        "INVALID_ARGUMENT",
        "REFUSED",
        "STALE",
        "NOT_FOUND",
        "TOO_LARGE",
        "DETACHED",
        "UNAVAILABLE",
        "IO_ERROR",
    )
    assert DocumentError.code == REFUSED
    assert OpArgumentError.code == INVALID_ARGUMENT
    assert UnknownOpError.code == UNKNOWN_OP
    assert issubclass(UnknownOpError, OpArgumentError)
    assert issubclass(OpArgumentError, DocumentError)


def test_list_ops_is_json_and_has_the_spec_shape() -> None:
    ops = list_ops()
    assert [item["name"] for item in ops] == list(CATALOG)
    for item in ops:
        assert set(item) == {"name", "summary", "produces", "params", "example"}
        params = item["params"]
        assert isinstance(params, dict)
        assert params["type"] == "object"
        assert params["additionalProperties"] is False
    json.dumps(ops)
    assert list_ops("AddLine")[0]["name"] == "AddLine"
    with pytest.raises(UnknownOpError):
        list_ops("AddTeapot")


def test_schema_derivation_follows_the_type_hints() -> None:
    point = CATALOG["AddPoint"].params
    props = point["properties"]
    assert isinstance(props, dict)
    assert props["x_mm"]["type"] == "number"
    assert props["label"]["type"] == ["string", "null"]
    assert props["label"]["default"] is None
    assert "entity_id" not in props  # output-only
    assert point["required"] == ["x_mm", "y_mm", "z_mm"]
    linear = CATALOG["ArrayLinear"].params["properties"]
    assert isinstance(linear, dict)
    assert linear["copies"] == {
        "type": "integer",
        "description": CATALOG["ArrayLinear"].fields["copies"],
        "default": 1,
    }
    assert linear["entity_ids"]["items"] == {"type": "integer", "minimum": 1}
    box = CATALOG["AddBox"].params["properties"]
    assert isinstance(box, dict)
    assert box["size_xyz_mm"]["minItems"] == box["size_xyz_mm"]["maxItems"] == 3
    # SetLabel's entity_id names the target, so it is an input there.
    required = CATALOG["SetLabel"].params["required"]
    assert isinstance(required, list) and "entity_id" in required


def test_apply_returns_the_committed_op_and_the_id_diff() -> None:
    document = Document()
    applied = apply(
        document, "AddLine", {"start_id": {"xyz": [0, 0, 0]}, "end_id": {"xyz": [6000, 0, 0]}}
    )
    assert applied.created_id == 3
    assert applied.added == (1, 2, 3)
    assert applied.removed == ()
    assert applied.op["entity_id"] == 3
    assert applied.op["start_id"] == {"xyz": [0.0, 0.0, 0.0], "id": 1}
    deleted = apply(document, "Delete", {"entity_ids": [3]})
    assert deleted.created_id is None
    assert deleted.added == ()
    assert deleted.removed == (1, 2, 3)


def test_apply_fills_schema_defaults_the_codec_requires() -> None:
    document = Document()
    _square(document)
    face = apply(document, "AddFace", {"point_ids": [1, 2, 3, 4]})
    # ArrayLinear's codec reads `copies` unconditionally; the schema default fills it.
    copied = apply(
        document, "ArrayLinear", {"entity_ids": [face.created_id], "dx_mm": 5000, "dy_mm": 0}
    )
    assert copied.op["copies"] == 1
    assert copied.added  # the copy's points, lines and face
    # Extrude's face_id has always been optional in the codec; a ring alone is enough.
    solid = apply(
        document,
        "Extrude",
        {"ring": [{"xyz": [0, 5000, 0]}, {"xyz": [400, 5000, 0]}, {"xyz": [400, 5400, 0]}],
         "distance_mm": 3000},
    )
    assert solid.created_id is not None


@pytest.mark.parametrize(
    ("params", "fragment"),
    [
        ({"x_mm": 0, "y_mm": 0}, "z_mm is required"),
        ({"x_mm": 0, "y_mm": 0, "z_mm": 0, "colour": "red"}, "colour is not a field"),
        ({"x_mm": "0", "y_mm": 0, "z_mm": 0}, "x_mm must be number"),
        ({"x_mm": True, "y_mm": 0, "z_mm": 0}, "x_mm must be number"),
        ({"x_mm": 0, "y_mm": 0, "z_mm": 0, "entity_id": 7}, "entity_id is not a field"),
    ],
)
def test_bad_arguments_are_invalid_argument(params: dict[str, object], fragment: str) -> None:
    document = Document()
    with pytest.raises(OpArgumentError, match=fragment) as caught:
        apply(document, "AddPoint", params)
    assert caught.value.code == INVALID_ARGUMENT
    assert document.ops() == ()


def test_committed_vertex_with_an_id_is_output_only() -> None:
    document = Document()
    with pytest.raises(OpArgumentError):
        apply(document, "AddLine", {"start_id": {"xyz": [0, 0, 0], "id": 5}, "end_id": 1})


def test_decode_failure_is_invalid_argument() -> None:
    with pytest.raises(OpArgumentError, match="radius_mm must be positive") as caught:
        apply(Document(), "AddCircle", {"center_id": {"xyz": [0, 0, 0]}, "radius_mm": -1})
    assert caught.value.code == INVALID_ARGUMENT


def test_unknown_op_is_unknown_op() -> None:
    with pytest.raises(UnknownOpError) as caught:
        apply(Document(), "AddTeapot", {})
    assert caught.value.code == UNKNOWN_OP


def test_refusal_is_refused_and_changes_nothing() -> None:
    document = Document()
    _square(document)
    before = document.to_json()
    with pytest.raises(DocumentError) as caught:
        apply(document, "AddLine", {"start_id": 1, "end_id": 99})
    assert not isinstance(caught.value, OpArgumentError)
    assert caught.value.code == REFUSED
    assert document.to_json() == before


def test_split_request_takes_flat_and_nested_forms() -> None:
    flat = split_request({"op": "AddPoint", "x_mm": 1, "y_mm": 2, "z_mm": 3})
    nested = split_request({"op": "AddPoint", "params": {"x_mm": 1, "y_mm": 2, "z_mm": 3}})
    assert flat == nested == ("AddPoint", {"x_mm": 1, "y_mm": 2, "z_mm": 3})
    with pytest.raises(OpArgumentError):
        split_request({"x_mm": 1})
    with pytest.raises(OpArgumentError):
        split_request({"op": "AddPoint", "params": {}, "x_mm": 1})
    with pytest.raises(OpArgumentError):
        split_request({"op": "AddPoint", "params": [1]})


def test_schema_id_is_v1_and_v0_still_reads() -> None:
    """ADR 0024 decision 9: section ops move the writer to v1; v0 logs stay readable."""
    assert SCHEMA_ID == "apeCAD.document.v1"
    assert SUPPORTED_SCHEMA_IDS == ("apeCAD.document.v0", "apeCAD.document.v1")
