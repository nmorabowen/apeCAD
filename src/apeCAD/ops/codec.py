"""JSON codec for ops: one dict per op, keyed by "op". Field names are the contract."""

from __future__ import annotations

from apeCAD.errors import DocumentError
from apeCAD.geometry import XYZ
from apeCAD.ops.section import SECTION_OPS
from apeCAD.ops.section_codec import parse_section_op, section_op_to_dict
from apeCAD.ops.types import (
    AddArc,
    AddBezier,
    AddBox,
    AddCircle,
    AddEllipse,
    AddFace,
    AddFaceFromLines,
    AddLine,
    AddLineChain,
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
from apeCAD.ops.values import (
    as_entity_id,
    as_float,
    as_id_tuple,
    as_int,
    as_optional_entity_id,
    as_optional_str,
    as_str,
    as_vertex,
    as_vertex_tuple,
    as_xyz,
    vertex_json,
    vertices_json,
)


def op_to_dict(op: Op) -> dict[str, object]:
    if isinstance(op, SECTION_OPS):
        return section_op_to_dict(op)
    if isinstance(op, AddPoint):
        return {
            "op": "AddPoint",
            "x_mm": op.x_mm,
            "y_mm": op.y_mm,
            "z_mm": op.z_mm,
            "label": op.label,
            "entity_id": op.entity_id,
        }
    if isinstance(op, AddLine):
        return {
            "op": "AddLine",
            "start_id": vertex_json(op.start_id),
            "end_id": vertex_json(op.end_id),
            "label": op.label,
            "entity_id": op.entity_id,
        }
    if isinstance(op, AddLineChain):
        return {
            "op": "AddLineChain",
            "point_ids": vertices_json(op.point_ids),
            "label": op.label,
            "line_ids": None if op.line_ids is None else list(op.line_ids),
        }
    if isinstance(op, AddPolyline):
        return {
            "op": "AddPolyline",
            "point_ids": vertices_json(op.point_ids),
            "closed": op.closed,
            "label": op.label,
            "entity_id": op.entity_id,
        }
    if isinstance(op, AddBox):
        return {
            "op": "AddBox",
            "origin_xyz_mm": list(op.origin_xyz_mm.to_tuple()),
            "size_xyz_mm": list(op.size_xyz_mm.to_tuple()),
            "label": op.label,
            "entity_id": op.entity_id,
        }
    if isinstance(op, AddFace):
        return {
            "op": "AddFace",
            "point_ids": vertices_json(op.point_ids),
            "label": op.label,
            "entity_id": op.entity_id,
        }
    if isinstance(op, Extrude):
        extruded: dict[str, object] = {
            "op": "Extrude",
            "face_id": op.face_id,
            "distance_mm": op.distance_mm,
            "direction_xyz": list(op.direction_xyz.to_tuple()),
            "label": op.label,
            "entity_id": op.entity_id,
        }
        if op.ring is not None:  # absent, not null, so a face-only Extrude reads as before
            extruded["ring"] = vertices_json(op.ring)
        return extruded
    if isinstance(op, AddCircle):
        return {
            "op": "AddCircle",
            "center_id": vertex_json(op.center_id),
            "radius_mm": op.radius_mm,
            "label": op.label,
            "entity_id": op.entity_id,
        }
    if isinstance(op, AddArc):
        return {
            "op": "AddArc",
            "start_id": vertex_json(op.start_id),
            "mid_id": vertex_json(op.mid_id),
            "end_id": vertex_json(op.end_id),
            "label": op.label,
            "entity_id": op.entity_id,
        }
    if isinstance(op, AddEllipse):
        return {
            "op": "AddEllipse",
            "center_id": vertex_json(op.center_id),
            "radius_x_mm": op.radius_x_mm,
            "radius_y_mm": op.radius_y_mm,
            "label": op.label,
            "entity_id": op.entity_id,
        }
    if isinstance(op, AddBezier):
        return {
            "op": "AddBezier",
            "point_ids": vertices_json(op.point_ids),
            "label": op.label,
            "entity_id": op.entity_id,
        }
    if isinstance(op, Translate):
        return {
            "op": "Translate",
            "entity_ids": list(op.entity_ids),
            "dx_mm": op.dx_mm,
            "dy_mm": op.dy_mm,
            "dz_mm": op.dz_mm,
        }
    if isinstance(op, InsertNode):
        return {
            "op": "InsertNode",
            "target_id": op.target_id,
            "x_mm": op.x_mm,
            "y_mm": op.y_mm,
            "z_mm": op.z_mm,
            "entity_id": op.entity_id,
            "new_line_id": op.new_line_id,
        }
    if isinstance(op, TrimLine):
        return {
            "op": "TrimLine",
            "line_id": op.line_id,
            "keep_id": op.keep_id,
            "x_mm": op.x_mm,
            "y_mm": op.y_mm,
            "z_mm": op.z_mm,
            "entity_id": op.entity_id,
        }
    if isinstance(op, BreakCrossing):
        return {
            "op": "BreakCrossing",
            "line_a_id": op.line_a_id,
            "line_b_id": op.line_b_id,
            "entity_id": op.entity_id,
            "new_line_a_id": op.new_line_a_id,
            "new_line_b_id": op.new_line_b_id,
        }
    if isinstance(op, AddFaceFromLines):
        return {
            "op": "AddFaceFromLines",
            "line_ids": list(op.line_ids),
            "label": op.label,
            "entity_id": op.entity_id,
        }
    if isinstance(op, JoinPolyline):
        return {
            "op": "JoinPolyline",
            "entity_ids": list(op.entity_ids),
            "label": op.label,
            "entity_id": op.entity_id,
        }
    if isinstance(op, Rotate):
        return {
            "op": "Rotate",
            "entity_ids": list(op.entity_ids),
            "origin_x_mm": op.origin_x_mm,
            "origin_y_mm": op.origin_y_mm,
            "angle_deg": op.angle_deg,
        }
    if isinstance(op, Mirror):
        return {
            "op": "Mirror",
            "entity_ids": list(op.entity_ids),
            "ax_mm": op.ax_mm,
            "ay_mm": op.ay_mm,
            "bx_mm": op.bx_mm,
            "by_mm": op.by_mm,
        }
    if isinstance(op, ChamferCorner):
        return {
            "op": "ChamferCorner",
            "target_id": op.target_id,
            "vertex_id": op.vertex_id,
            "distance_mm": op.distance_mm,
            "entity_id": op.entity_id,
            "start_id": op.start_id,
            "end_id": op.end_id,
        }
    if isinstance(op, FilletCorner):
        return {
            "op": "FilletCorner",
            "target_id": op.target_id,
            "vertex_id": op.vertex_id,
            "radius_mm": op.radius_mm,
            "entity_id": op.entity_id,
            "start_id": op.start_id,
            "mid_id": op.mid_id,
            "end_id": op.end_id,
        }
    if isinstance(op, Sew):
        return {
            "op": "Sew",
            "entity_ids": list(op.entity_ids),
            "tolerance_mm": op.tolerance_mm,
        }
    if isinstance(op, Simplify):
        return {
            "op": "Simplify",
            "entity_ids": list(op.entity_ids),
        }
    if isinstance(op, ArrayLinear):
        return {
            "op": "ArrayLinear",
            "entity_ids": list(op.entity_ids),
            "dx_mm": op.dx_mm,
            "dy_mm": op.dy_mm,
            "dz_mm": op.dz_mm,
            "copies": op.copies,
        }
    if isinstance(op, ArrayPolar):
        return {
            "op": "ArrayPolar",
            "entity_ids": list(op.entity_ids),
            "origin_x_mm": op.origin_x_mm,
            "origin_y_mm": op.origin_y_mm,
            "count": op.count,
            "angle_deg": op.angle_deg,
        }
    if isinstance(op, Delete):
        return {
            "op": "Delete",
            "entity_ids": list(op.entity_ids),
        }
    if isinstance(op, SetLabel):
        return {
            "op": "SetLabel",
            "entity_id": op.entity_id,
            "label": op.label,
        }
    return {
        "op": "Tag",
        "name": op.name,
        "entity_ids": list(op.entity_ids),
    }


def op_from_dict(payload: dict[str, object]) -> Op:
    try:
        return _parse_op(payload)
    except KeyError as exc:
        raise DocumentError(f"operation is missing field {exc.args[0]!r}") from exc


def _parse_op(payload: dict[str, object]) -> Op:
    kind = payload.get("op")
    section = parse_section_op(kind, payload)
    if section is not None:
        return section
    if kind == "AddPoint":
        return AddPoint(
            x_mm=as_float("x_mm", payload["x_mm"]),
            y_mm=as_float("y_mm", payload["y_mm"]),
            z_mm=as_float("z_mm", payload["z_mm"]),
            label=as_optional_str(payload.get("label")),
            entity_id=as_optional_entity_id(payload.get("entity_id")),
        )
    if kind == "AddLine":
        return AddLine(
            start_id=as_vertex("start_id", payload["start_id"]),
            end_id=as_vertex("end_id", payload["end_id"]),
            label=as_optional_str(payload.get("label")),
            entity_id=as_optional_entity_id(payload.get("entity_id")),
        )
    if kind == "AddLineChain":
        line_ids = payload.get("line_ids")
        return AddLineChain(
            point_ids=as_vertex_tuple("point_ids", payload["point_ids"]),
            label=as_optional_str(payload.get("label")),
            line_ids=None if line_ids is None else as_id_tuple("line_ids", line_ids),
        )
    if kind == "AddPolyline":
        return AddPolyline(
            point_ids=as_vertex_tuple("point_ids", payload["point_ids"]),
            closed=bool(payload.get("closed", False)),
            label=as_optional_str(payload.get("label")),
            entity_id=as_optional_entity_id(payload.get("entity_id")),
        )
    if kind == "AddBox":
        return AddBox(
            origin_xyz_mm=as_xyz("origin_xyz_mm", payload["origin_xyz_mm"]),
            size_xyz_mm=as_xyz("size_xyz_mm", payload["size_xyz_mm"]),
            label=as_optional_str(payload.get("label")),
            entity_id=as_optional_entity_id(payload.get("entity_id")),
        )
    if kind == "AddFace":
        return AddFace(
            point_ids=as_vertex_tuple("point_ids", payload["point_ids"]),
            label=as_optional_str(payload.get("label")),
            entity_id=as_optional_entity_id(payload.get("entity_id")),
        )
    if kind == "Extrude":
        direction = payload.get("direction_xyz")
        ring = payload.get("ring")
        return Extrude(
            face_id=as_optional_entity_id(payload.get("face_id")),
            distance_mm=as_float("distance_mm", payload["distance_mm"]),
            direction_xyz=as_xyz("direction_xyz", direction)
            if direction is not None
            else XYZ(0.0, 0.0, 1.0),
            label=as_optional_str(payload.get("label")),
            entity_id=as_optional_entity_id(payload.get("entity_id")),
            ring=None if ring is None else as_vertex_tuple("ring", ring),
        )
    if kind == "AddCircle":
        return AddCircle(
            center_id=as_vertex("center_id", payload["center_id"]),
            radius_mm=as_float("radius_mm", payload["radius_mm"]),
            label=as_optional_str(payload.get("label")),
            entity_id=as_optional_entity_id(payload.get("entity_id")),
        )
    if kind == "AddArc":
        return AddArc(
            start_id=as_vertex("start_id", payload["start_id"]),
            mid_id=as_vertex("mid_id", payload["mid_id"]),
            end_id=as_vertex("end_id", payload["end_id"]),
            label=as_optional_str(payload.get("label")),
            entity_id=as_optional_entity_id(payload.get("entity_id")),
        )
    if kind == "AddEllipse":
        return AddEllipse(
            center_id=as_vertex("center_id", payload["center_id"]),
            radius_x_mm=as_float("radius_x_mm", payload["radius_x_mm"]),
            radius_y_mm=as_float("radius_y_mm", payload["radius_y_mm"]),
            label=as_optional_str(payload.get("label")),
            entity_id=as_optional_entity_id(payload.get("entity_id")),
        )
    if kind == "AddBezier":
        return AddBezier(
            point_ids=as_vertex_tuple("point_ids", payload["point_ids"]),
            label=as_optional_str(payload.get("label")),
            entity_id=as_optional_entity_id(payload.get("entity_id")),
        )
    if kind == "Translate":
        return Translate(
            entity_ids=as_id_tuple("entity_ids", payload["entity_ids"]),
            dx_mm=as_float("dx_mm", payload["dx_mm"]),
            dy_mm=as_float("dy_mm", payload["dy_mm"]),
            dz_mm=as_float("dz_mm", payload.get("dz_mm", 0.0)),
        )
    if kind == "InsertNode":
        return InsertNode(
            target_id=as_entity_id("target_id", payload["target_id"]),
            x_mm=as_float("x_mm", payload["x_mm"]),
            y_mm=as_float("y_mm", payload["y_mm"]),
            z_mm=as_float("z_mm", payload.get("z_mm", 0.0)),
            entity_id=as_optional_entity_id(payload.get("entity_id")),
            new_line_id=as_optional_entity_id(payload.get("new_line_id")),
        )
    if kind == "TrimLine":
        return TrimLine(
            line_id=as_entity_id("line_id", payload["line_id"]),
            keep_id=as_entity_id("keep_id", payload["keep_id"]),
            x_mm=as_float("x_mm", payload["x_mm"]),
            y_mm=as_float("y_mm", payload["y_mm"]),
            z_mm=as_float("z_mm", payload.get("z_mm", 0.0)),
            entity_id=as_optional_entity_id(payload.get("entity_id")),
        )
    if kind == "BreakCrossing":
        return BreakCrossing(
            line_a_id=as_entity_id("line_a_id", payload["line_a_id"]),
            line_b_id=as_entity_id("line_b_id", payload["line_b_id"]),
            entity_id=as_optional_entity_id(payload.get("entity_id")),
            new_line_a_id=as_optional_entity_id(payload.get("new_line_a_id")),
            new_line_b_id=as_optional_entity_id(payload.get("new_line_b_id")),
        )
    if kind == "AddFaceFromLines":
        return AddFaceFromLines(
            line_ids=as_id_tuple("line_ids", payload["line_ids"]),
            label=as_optional_str(payload.get("label")),
            entity_id=as_optional_entity_id(payload.get("entity_id")),
        )
    if kind == "JoinPolyline":
        return JoinPolyline(
            entity_ids=as_id_tuple("entity_ids", payload["entity_ids"]),
            label=as_optional_str(payload.get("label")),
            entity_id=as_optional_entity_id(payload.get("entity_id")),
        )
    if kind == "Rotate":
        return Rotate(
            entity_ids=as_id_tuple("entity_ids", payload["entity_ids"]),
            origin_x_mm=as_float("origin_x_mm", payload["origin_x_mm"]),
            origin_y_mm=as_float("origin_y_mm", payload["origin_y_mm"]),
            angle_deg=as_float("angle_deg", payload["angle_deg"]),
        )
    if kind == "Mirror":
        return Mirror(
            entity_ids=as_id_tuple("entity_ids", payload["entity_ids"]),
            ax_mm=as_float("ax_mm", payload["ax_mm"]),
            ay_mm=as_float("ay_mm", payload["ay_mm"]),
            bx_mm=as_float("bx_mm", payload["bx_mm"]),
            by_mm=as_float("by_mm", payload["by_mm"]),
        )
    if kind == "ChamferCorner":
        return ChamferCorner(
            target_id=as_entity_id("target_id", payload["target_id"]),
            vertex_id=as_entity_id("vertex_id", payload["vertex_id"]),
            distance_mm=as_float("distance_mm", payload["distance_mm"]),
            entity_id=as_optional_entity_id(payload.get("entity_id")),
            start_id=as_optional_entity_id(payload.get("start_id")),
            end_id=as_optional_entity_id(payload.get("end_id")),
        )
    if kind == "FilletCorner":
        return FilletCorner(
            target_id=as_entity_id("target_id", payload["target_id"]),
            vertex_id=as_entity_id("vertex_id", payload["vertex_id"]),
            radius_mm=as_float("radius_mm", payload["radius_mm"]),
            entity_id=as_optional_entity_id(payload.get("entity_id")),
            start_id=as_optional_entity_id(payload.get("start_id")),
            mid_id=as_optional_entity_id(payload.get("mid_id")),
            end_id=as_optional_entity_id(payload.get("end_id")),
        )
    if kind == "Sew":
        return Sew(
            entity_ids=as_id_tuple("entity_ids", payload["entity_ids"]),
            tolerance_mm=as_float("tolerance_mm", payload.get("tolerance_mm", 1.0)),
        )
    if kind == "Simplify":
        return Simplify(entity_ids=as_id_tuple("entity_ids", payload["entity_ids"]))
    if kind == "ArrayLinear":
        return ArrayLinear(
            entity_ids=as_id_tuple("entity_ids", payload["entity_ids"]),
            dx_mm=as_float("dx_mm", payload["dx_mm"]),
            dy_mm=as_float("dy_mm", payload["dy_mm"]),
            dz_mm=as_float("dz_mm", payload.get("dz_mm", 0.0)),
            copies=as_int("copies", payload["copies"]),
        )
    if kind == "ArrayPolar":
        return ArrayPolar(
            entity_ids=as_id_tuple("entity_ids", payload["entity_ids"]),
            origin_x_mm=as_float("origin_x_mm", payload["origin_x_mm"]),
            origin_y_mm=as_float("origin_y_mm", payload["origin_y_mm"]),
            count=as_int("count", payload["count"]),
            angle_deg=as_float("angle_deg", payload.get("angle_deg", 360.0)),
        )
    if kind == "Delete":
        return Delete(entity_ids=as_id_tuple("entity_ids", payload["entity_ids"]))
    if kind == "SetLabel":
        return SetLabel(
            entity_id=as_entity_id("entity_id", payload["entity_id"]),
            label=as_optional_str(payload.get("label")),
        )
    if kind == "Tag":
        return Tag(
            name=as_str("name", payload["name"]),
            entity_ids=as_id_tuple("entity_ids", payload["entity_ids"]),
        )
    raise DocumentError(f"unknown operation {kind!r}")
