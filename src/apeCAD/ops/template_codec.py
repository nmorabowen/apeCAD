"""JSON codec for the section-template ops (ADR 0040). `apeCAD.ops` asks it first.

`op_to_dict` and `op_from_dict` in `apeCAD.ops` try this codec before `ops.codec`, as
`ops.codec` tries the section codec before its own branches; every caller imports the pair
from `apeCAD.ops`. `params` is written as plain JSON (`thaw_params`). `template_version`
and `child_ids` are written only once the op has committed.
"""

from __future__ import annotations

from apeCAD.errors import DocumentError
from apeCAD.ops.templates import (
    AddSectionTemplate,
    EditSectionTemplate,
    ExplodeSectionTemplate,
    TemplateOp,
    thaw_params,
)
from apeCAD.ops.values import as_entity_id, as_id_tuple, as_optional_entity_id, as_optional_str


def template_op_to_dict(op: TemplateOp) -> dict[str, object]:
    if isinstance(op, AddSectionTemplate):
        return {
            "op": "AddSectionTemplate",
            "template": op.template,
            "template_version": op.template_version,
            "params": thaw_params(op.params),
            "label": op.label,
            "entity_id": op.entity_id,
            "child_ids": list(op.child_ids),
        }
    if isinstance(op, EditSectionTemplate):
        return {
            "op": "EditSectionTemplate",
            "template_id": op.template_id,
            "template_version": op.template_version,
            "params": thaw_params(op.params),
            "child_ids": list(op.child_ids),
        }
    return {"op": "ExplodeSectionTemplate", "template_id": op.template_id}


def parse_template_op(kind: object, payload: dict[str, object]) -> TemplateOp | None:
    """The template op `payload` names, or None when `kind` is not a template op."""
    if kind == "AddSectionTemplate":
        return AddSectionTemplate(
            template=_as_template(payload["template"]),
            params=_as_params(payload["params"]),
            template_version=_as_version(payload.get("template_version")),
            label=as_optional_str(payload.get("label")),
            entity_id=as_optional_entity_id(payload.get("entity_id")),
            child_ids=as_id_tuple("child_ids", payload.get("child_ids", [])),
        )
    if kind == "EditSectionTemplate":
        return EditSectionTemplate(
            template_id=as_entity_id("template_id", payload["template_id"]),
            params=_as_params(payload["params"]),
            template_version=_as_version(payload.get("template_version")),
            child_ids=as_id_tuple("child_ids", payload.get("child_ids", [])),
        )
    if kind == "ExplodeSectionTemplate":
        return ExplodeSectionTemplate(
            template_id=as_entity_id("template_id", payload["template_id"]),
        )
    return None


def _as_template(value: object) -> str:
    if not isinstance(value, str):
        raise DocumentError(f"template must be a template name, got {value!r}")
    return value


def _as_params(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise DocumentError(f"params must be an object, got {value!r}")
    return value  # pyright: ignore[reportUnknownVariableType]


def _as_version(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise DocumentError(f"template_version must be a whole number, got {value!r}")
    return value
