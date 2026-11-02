"""Typed operations and their JSON codec (ADR 0006).

types.py holds one frozen dataclass per op (section.py the section-mode ones, templates.py
the section-template ones); codec.py, section_codec.py and template_codec.py map them to and
from JSON. `op_to_dict` and `op_from_dict` here ask the template codec first, then
`ops.codec`, which asks the section codec first.
Import from here: `from apeCAD.ops import AddPoint, op_from_dict`.
"""

from __future__ import annotations

from apeCAD.errors import DocumentError
from apeCAD.ops import codec as _codec
from apeCAD.ops.template_codec import parse_template_op, template_op_to_dict
from apeCAD.ops.templates import (
    TEMPLATE_OPS,
    AddSectionTemplate,
    EditSectionTemplate,
    ExplodeSectionTemplate,
    TemplateOp,
)
from apeCAD.ops.types import (
    SCHEMA_ID,
    SUPPORTED_SCHEMA_IDS,
    UNITS,
    AddArc,
    AddBar,
    AddBarRow,
    AddBarsAlongEdge,
    AddBarsOnCircle,
    AddBezier,
    AddBox,
    AddCircle,
    AddCircularTie,
    AddConcreteFace,
    AddCrosstie,
    AddEllipse,
    AddFace,
    AddFaceFromLines,
    AddFaceHole,
    AddHoop,
    AddLine,
    AddLineChain,
    AddPoint,
    AddPolyline,
    AddSectionFace,
    AddSectionOutline,
    AddSteelShape,
    AddWallChain,
    AddWallLeg,
    ArrayLinear,
    ArrayPolar,
    BreakCrossing,
    ChamferCorner,
    Delete,
    Extrude,
    FilletCorner,
    InsertNode,
    JoinPolyline,
    Mirror,
    PointAt,
    Rotate,
    SetBarSize,
    SetCover,
    SetLabel,
    SetLegReinforcement,
    SetMaterial,
    SetTransverse,
    Sew,
    Simplify,
    Tag,
    Translate,
    TrimLine,
    VertexRef,
)
from apeCAD.ops.types import Op as _CodecOp

Op = _CodecOp | TemplateOp
"""Every op: the ones `ops.codec` encodes, and the section-template ops (ADR 0040)."""


def op_to_dict(op: Op) -> dict[str, object]:
    """The JSON object of one op, keyed by "op"."""
    if isinstance(op, TEMPLATE_OPS):
        return template_op_to_dict(op)
    return _codec.op_to_dict(op)


def op_from_dict(payload: dict[str, object]) -> Op:
    """The op a JSON object names; a missing field is a `DocumentError` naming it."""
    try:
        template = parse_template_op(payload.get("op"), payload)
    except KeyError as exc:
        raise DocumentError(f"operation is missing field {exc.args[0]!r}") from exc
    if template is not None:
        return template
    return _codec.op_from_dict(payload)


__all__ = [
    "AddSectionTemplate",
    "EditSectionTemplate",
    "ExplodeSectionTemplate",
    "AddBarsOnCircle",
    "AddCircularTie",
    "AddFaceHole",
    "AddSectionFace",
    "AddSteelShape",
    "AddSectionOutline",
    "AddWallChain",
    "AddWallLeg",
    "SetLegReinforcement",
    "SetCover",
    "AddArc",
    "AddBar",
    "AddBarRow",
    "AddBarsAlongEdge",
    "AddBezier",
    "AddBox",
    "AddCircle",
    "AddConcreteFace",
    "AddCrosstie",
    "AddEllipse",
    "AddFace",
    "AddFaceFromLines",
    "AddHoop",
    "AddLine",
    "AddLineChain",
    "AddPoint",
    "AddPolyline",
    "ArrayLinear",
    "ArrayPolar",
    "BreakCrossing",
    "ChamferCorner",
    "Delete",
    "Extrude",
    "FilletCorner",
    "InsertNode",
    "JoinPolyline",
    "Mirror",
    "Op",
    "op_from_dict",
    "op_to_dict",
    "PointAt",
    "Rotate",
    "SCHEMA_ID",
    "SetBarSize",
    "SetLabel",
    "SetMaterial",
    "SetTransverse",
    "Sew",
    "Simplify",
    "SUPPORTED_SCHEMA_IDS",
    "Tag",
    "Translate",
    "TrimLine",
    "UNITS",
    "VertexRef",
]
