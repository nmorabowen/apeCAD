"""One table from op type to handler. A new op adds one row here (ADR 0023)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from apeCAD.draft import create, edit, meta, transform
from apeCAD.draft.state import DraftState
from apeCAD.errors import DocumentError
from apeCAD.ops import (
    AddArc,
    AddBezier,
    AddBox,
    AddCircle,
    AddEllipse,
    AddFace,
    AddFaceFromLines,
    AddLine,
    AddPoint,
    AddPolyline,
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
    Op,
    Rotate,
    SetLabel,
    Sew,
    Simplify,
    Tag,
    Translate,
    TrimLine,
)

Handler = Callable[[DraftState, Any], Op]

HANDLERS: dict[type[object], Handler] = {
    AddPoint: create.add_point,
    AddLine: create.add_line,
    AddPolyline: create.add_polyline,
    AddBox: create.add_box,
    AddFace: create.add_face,
    Extrude: create.extrude,
    AddCircle: create.add_circle,
    AddArc: create.add_arc,
    AddEllipse: create.add_ellipse,
    AddBezier: create.add_bezier,
    AddFaceFromLines: create.add_face_from_lines,
    JoinPolyline: create.join_polyline,
    InsertNode: edit.insert_node,
    TrimLine: edit.trim_line,
    BreakCrossing: edit.break_crossing,
    ChamferCorner: edit.chamfer_corner,
    FilletCorner: edit.fillet_corner,
    Sew: edit.sew,
    Simplify: edit.simplify,
    Translate: transform.translate,
    Rotate: transform.rotate,
    Mirror: transform.mirror,
    ArrayLinear: transform.array_linear,
    ArrayPolar: transform.array_polar,
    Delete: meta.delete,
    Tag: meta.tag,
    SetLabel: meta.set_label,
}


def apply_op(state: DraftState, op: Op) -> Op:
    """Mutate state by one op; return it with every allocated id filled in."""
    handler = HANDLERS.get(type(op))
    if handler is None:
        raise DocumentError(f"internal error: no handler for {type(op).__name__}")
    return handler(state, op)
