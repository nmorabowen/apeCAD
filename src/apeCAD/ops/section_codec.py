"""JSON codec for the section-mode ops (ADR 0024). `ops.codec` delegates here first."""

from __future__ import annotations

from typing import cast

from apeCAD.entities import LegSteel
from apeCAD.errors import DocumentError
from apeCAD.ops.base import VertexRef
from apeCAD.ops.section import (
    AddBar,
    AddBarRow,
    AddBarsAlongEdge,
    AddConcreteFace,
    AddCrosstie,
    AddHoop,
    AddSectionOutline,
    AddWallChain,
    AddWallLeg,
    SectionOp,
    SetBarSize,
    SetCover,
    SetLegReinforcement,
    SetMaterial,
    SetTransverse,
)
from apeCAD.ops.section_faces import (
    SECTION_FACE_OPS,
    AddBarsOnCircle,
    AddCircularTie,
    AddFaceHole,
    AddSectionFace,
    AddSteelShape,
    SectionFaceOp,
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
    vertex_json,
    vertices_json,
)


def section_op_to_dict(op: SectionOp) -> dict[str, object]:
    if isinstance(op, SECTION_FACE_OPS):
        return _face_op_to_dict(op)
    if isinstance(op, AddConcreteFace):
        return {
            "op": "AddConcreteFace",
            "point_ids": vertices_json(op.point_ids),
            "material": op.material,
            "label": op.label,
            "entity_id": op.entity_id,
        }
    if isinstance(op, AddBar):
        return {
            "op": "AddBar",
            "x_mm": op.x_mm,
            "y_mm": op.y_mm,
            "designation": op.designation,
            "label": op.label,
            "entity_id": op.entity_id,
            "point_id": op.point_id,
            # Additive (ADR 0039 decision 6): absent when unset, so v1 logs stay as they were.
            **({} if op.material is None else {"material": op.material}),
        }
    if isinstance(op, AddHoop):
        return {
            "op": "AddHoop",
            "bar_ids": list(op.bar_ids),
            "designation": op.designation,
            "spacing_mm": op.spacing_mm,
            "hooks": op.hooks,
            "label": op.label,
            "entity_id": op.entity_id,
        }
    if isinstance(op, AddCrosstie):
        return {
            "op": "AddCrosstie",
            "bar_a_id": op.bar_a_id,
            "bar_b_id": op.bar_b_id,
            "designation": op.designation,
            "spacing_mm": op.spacing_mm,
            "hooks": op.hooks,
            "label": op.label,
            "entity_id": op.entity_id,
        }
    if isinstance(op, SetBarSize):
        return {
            "op": "SetBarSize",
            "entity_ids": list(op.entity_ids),
            "designation": op.designation,
        }
    if isinstance(op, SetMaterial):
        return {"op": "SetMaterial", "entity_ids": list(op.entity_ids), "material": op.material}
    if isinstance(op, (AddSectionOutline, AddWallChain, AddWallLeg, SetLegReinforcement, SetCover)):
        return _wall_op_to_dict(op)
    if isinstance(op, (AddBarRow, AddBarsAlongEdge)):
        return _layout_op_to_dict(op)
    return {
        "op": "SetTransverse",
        "entity_ids": list(op.entity_ids),
        "designation": op.designation,
        "spacing_mm": op.spacing_mm,
        "hooks": op.hooks,
    }


def _wall_op_to_dict(
    op: AddSectionOutline | AddWallChain | AddWallLeg | SetLegReinforcement | SetCover,
) -> dict[str, object]:
    if isinstance(op, AddSectionOutline):
        return {
            "op": "AddSectionOutline",
            "point_ids": vertices_json(op.point_ids),
            "material": op.material,
            "label": op.label,
            "entity_id": op.entity_id,
        }
    if isinstance(op, AddWallChain):
        return {
            "op": "AddWallChain",
            "point_ids": vertices_json(op.point_ids),
            "thickness_mm": list(op.thickness_mm),
            "material": op.material,
            "horizontal": _steel_json(op.horizontal),
            "label": op.label,
            "entity_id": op.entity_id,
            "ring": None if op.ring is None else vertices_json(op.ring),
            "leg_ids": list(op.leg_ids),
        }
    if isinstance(op, AddWallLeg):
        return {
            "op": "AddWallLeg",
            "start_id": vertex_json(op.start_id),
            "end_id": vertex_json(op.end_id),
            "thickness_mm": op.thickness_mm,
            "face_id": op.face_id,
            "horizontal": _steel_json(op.horizontal),
            "label": op.label,
            "entity_id": op.entity_id,
        }
    if isinstance(op, SetLegReinforcement):
        return {
            "op": "SetLegReinforcement",
            "leg_id": op.leg_id,
            "designation": op.designation,
            "spacing_mm": op.spacing_mm,
            "curtains": op.curtains,
        }
    return {
        "op": "SetCover",
        "face_id": op.face_id,
        "cover_mm": op.cover_mm,
        "tie_diameter_mm": op.tie_diameter_mm,
        "bar_diameter_mm": op.bar_diameter_mm,
        "entity_id": op.entity_id,
    }


def _layout_op_to_dict(op: AddBarRow | AddBarsAlongEdge) -> dict[str, object]:
    placed = {"bar_ids": list(op.bar_ids), "bar_point_ids": list(op.bar_point_ids)}
    if isinstance(op, AddBarRow):
        where: dict[str, object] = {
            "op": "AddBarRow",
            "start_x_mm": op.start_x_mm,
            "start_y_mm": op.start_y_mm,
            "end_x_mm": op.end_x_mm,
            "end_y_mm": op.end_y_mm,
        }
    else:
        where = {"op": "AddBarsAlongEdge", "face_id": op.face_id, "edge_index": op.edge_index}
    return {
        **where,
        "designation": op.designation,
        "count": op.count,
        "spacing_mm": op.spacing_mm,
        **placed,
    }


def _parse_layout_op(kind: object, payload: dict[str, object]) -> SectionOp | None:
    if kind not in ("AddBarRow", "AddBarsAlongEdge"):
        return None
    designation = as_str("designation", payload["designation"])
    raw_count = payload.get("count")
    count = None if raw_count is None else as_int("count", raw_count)
    raw_spacing = payload.get("spacing_mm")
    spacing = None if raw_spacing is None else as_float("spacing_mm", raw_spacing)
    bar_ids = as_id_tuple("bar_ids", payload.get("bar_ids", []))
    bar_point_ids = as_id_tuple("bar_point_ids", payload.get("bar_point_ids", []))
    if kind == "AddBarRow":
        return AddBarRow(
            start_x_mm=as_float("start_x_mm", payload["start_x_mm"]),
            start_y_mm=as_float("start_y_mm", payload["start_y_mm"]),
            end_x_mm=as_float("end_x_mm", payload["end_x_mm"]),
            end_y_mm=as_float("end_y_mm", payload["end_y_mm"]),
            designation=designation,
            count=count,
            spacing_mm=spacing,
            bar_ids=bar_ids,
            bar_point_ids=bar_point_ids,
        )
    if kind == "AddBarsAlongEdge":
        return AddBarsAlongEdge(
            face_id=as_entity_id("face_id", payload["face_id"]),
            edge_index=as_int("edge_index", payload["edge_index"]),
            designation=designation,
            count=count,
            spacing_mm=spacing,
            bar_ids=bar_ids,
            bar_point_ids=bar_point_ids,
        )
    return None


def _steel_json(steel: LegSteel | None) -> dict[str, object] | None:
    if steel is None:
        return None
    return {
        "designation": steel.designation,
        "spacing_mm": steel.spacing_mm,
        "curtains": steel.curtains,
    }


def _as_steel(value: object) -> LegSteel | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise DocumentError(
            f"horizontal must be {{designation, spacing_mm, curtains}} or null, got {value!r}"
        )
    steel = cast(dict[str, object], value)
    unknown = set(steel) - {"designation", "spacing_mm", "curtains"}
    if unknown:
        raise DocumentError(f"horizontal has unknown fields {sorted(unknown)}")
    return LegSteel(
        designation=as_str("horizontal.designation", steel.get("designation")),
        spacing_mm=as_float("horizontal.spacing_mm", steel.get("spacing_mm")),
        curtains=as_int("horizontal.curtains", steel.get("curtains")),
    )


def _as_thicknesses(value: object) -> tuple[float, ...]:
    """One thickness for every segment (a number or a 1-list), or one per segment."""
    if isinstance(value, list):
        items = cast(list[object], value)
        return tuple(as_float(f"thickness_mm[{k}]", item) for k, item in enumerate(items))
    return (as_float("thickness_mm", value),)


def _parse_wall_op(kind: object, payload: dict[str, object]) -> SectionOp | None:
    if kind == "AddSectionOutline":
        return AddSectionOutline(
            point_ids=as_vertex_tuple("point_ids", payload["point_ids"]),
            material=as_str("material", payload["material"]),
            label=as_optional_str(payload.get("label")),
            entity_id=as_optional_entity_id(payload.get("entity_id")),
        )
    if kind == "AddWallChain":
        ring = payload.get("ring")
        return AddWallChain(
            point_ids=as_vertex_tuple("point_ids", payload["point_ids"]),
            thickness_mm=_as_thicknesses(payload["thickness_mm"]),
            material=as_str("material", payload["material"]),
            horizontal=_as_steel(payload.get("horizontal")),
            label=as_optional_str(payload.get("label")),
            entity_id=as_optional_entity_id(payload.get("entity_id")),
            ring=None if ring is None else as_vertex_tuple("ring", ring),
            leg_ids=as_id_tuple("leg_ids", payload.get("leg_ids", [])),
        )
    if kind == "AddWallLeg":
        return AddWallLeg(
            start_id=as_vertex("start_id", payload["start_id"]),
            end_id=as_vertex("end_id", payload["end_id"]),
            thickness_mm=as_float("thickness_mm", payload["thickness_mm"]),
            face_id=as_entity_id("face_id", payload["face_id"]),
            horizontal=_as_steel(payload.get("horizontal")),
            label=as_optional_str(payload.get("label")),
            entity_id=as_optional_entity_id(payload.get("entity_id")),
        )
    if kind == "SetLegReinforcement":
        return SetLegReinforcement(
            leg_id=as_entity_id("leg_id", payload["leg_id"]),
            designation=as_str("designation", payload["designation"]),
            spacing_mm=as_float("spacing_mm", payload["spacing_mm"]),
            curtains=as_int("curtains", payload["curtains"]),
        )
    if kind == "SetCover":
        return SetCover(
            face_id=as_entity_id("face_id", payload["face_id"]),
            cover_mm=as_float("cover_mm", payload["cover_mm"]),
            tie_diameter_mm=as_float("tie_diameter_mm", payload["tie_diameter_mm"]),
            bar_diameter_mm=as_float("bar_diameter_mm", payload["bar_diameter_mm"]),
            entity_id=as_optional_entity_id(payload.get("entity_id")),
        )
    return None


def parse_section_op(kind: object, payload: dict[str, object]) -> SectionOp | None:
    """The section op `payload` names, or None when `kind` is not a section op."""
    wall = (
        _parse_wall_op(kind, payload)
        or _parse_layout_op(kind, payload)
        or _parse_face_op(kind, payload)
    )
    if wall is not None:
        return wall
    if kind == "AddConcreteFace":
        return AddConcreteFace(
            point_ids=as_vertex_tuple("point_ids", payload["point_ids"]),
            material=as_str("material", payload["material"]),
            label=as_optional_str(payload.get("label")),
            entity_id=as_optional_entity_id(payload.get("entity_id")),
        )
    if kind == "AddBar":
        point_id = payload.get("point_id")
        return AddBar(
            x_mm=as_float("x_mm", payload["x_mm"]),
            y_mm=as_float("y_mm", payload["y_mm"]),
            designation=as_str("designation", payload["designation"]),
            label=as_optional_str(payload.get("label")),
            entity_id=as_optional_entity_id(payload.get("entity_id")),
            point_id=None if point_id is None else as_entity_id("point_id", point_id),
            material=_as_optional_name("material", payload.get("material")),
        )
    if kind == "AddHoop":
        return AddHoop(
            bar_ids=as_id_tuple("bar_ids", payload["bar_ids"]),
            designation=as_str("designation", payload["designation"]),
            spacing_mm=as_float("spacing_mm", payload["spacing_mm"]),
            hooks=as_str("hooks", payload.get("hooks", "135")),
            label=as_optional_str(payload.get("label")),
            entity_id=as_optional_entity_id(payload.get("entity_id")),
        )
    if kind == "AddCrosstie":
        return AddCrosstie(
            bar_a_id=as_entity_id("bar_a_id", payload["bar_a_id"]),
            bar_b_id=as_entity_id("bar_b_id", payload["bar_b_id"]),
            designation=as_str("designation", payload["designation"]),
            spacing_mm=as_float("spacing_mm", payload["spacing_mm"]),
            hooks=as_str("hooks", payload.get("hooks", "135-135")),
            label=as_optional_str(payload.get("label")),
            entity_id=as_optional_entity_id(payload.get("entity_id")),
        )
    if kind == "SetBarSize":
        return SetBarSize(
            entity_ids=as_id_tuple("entity_ids", payload["entity_ids"]),
            designation=as_str("designation", payload["designation"]),
        )
    if kind == "SetMaterial":
        return SetMaterial(
            entity_ids=as_id_tuple("entity_ids", payload["entity_ids"]),
            material=as_str("material", payload["material"]),
        )
    if kind == "SetTransverse":
        designation = payload.get("designation")
        spacing = payload.get("spacing_mm")
        hooks = payload.get("hooks")
        return SetTransverse(
            entity_ids=as_id_tuple("entity_ids", payload["entity_ids"]),
            designation=None if designation is None else as_str("designation", designation),
            spacing_mm=None if spacing is None else as_float("spacing_mm", spacing),
            hooks=None if hooks is None else as_str("hooks", hooks),
        )
    return None


def _boundary_json(
    point_ids: tuple[VertexRef, ...], center_id: VertexRef | None, radius_mm: float | None
) -> dict[str, object]:
    return {
        "point_ids": vertices_json(point_ids),
        "center_id": None if center_id is None else vertex_json(center_id),
        "radius_mm": radius_mm,
    }


def _face_op_to_dict(op: SectionFaceOp) -> dict[str, object]:
    """The v2 ops (ADR 0039); `section_op_to_dict` delegates here first."""
    if isinstance(op, AddSectionFace):
        return {
            "op": "AddSectionFace",
            "role": op.role,
            "material": op.material,
            **_boundary_json(op.point_ids, op.center_id, op.radius_mm),
            "label": op.label,
            "entity_id": op.entity_id,
        }
    if isinstance(op, AddFaceHole):
        return {
            "op": "AddFaceHole",
            "face_id": op.face_id,
            **_boundary_json(op.point_ids, op.center_id, op.radius_mm),
            "hole_index": op.hole_index,
        }
    if isinstance(op, AddSteelShape):
        return {
            "op": "AddSteelShape",
            "point_ids": vertices_json(op.point_ids),
            "material": op.material,
            "catalog": op.catalog,
            "designation": op.designation,
            "anchor_mm": list(op.anchor_mm),
            "rotation_deg": op.rotation_deg,
            "label": op.label,
            "entity_id": op.entity_id,
        }
    if isinstance(op, AddCircularTie):
        return {
            "op": "AddCircularTie",
            "kind": op.kind,
            "center_id": vertex_json(op.center_id),
            "centerline_radius_mm": op.centerline_radius_mm,
            "designation": op.designation,
            "pitch_mm": op.pitch_mm,
            "label": op.label,
            "entity_id": op.entity_id,
        }
    return {
        "op": "AddBarsOnCircle",
        "center_x_mm": op.center_x_mm,
        "center_y_mm": op.center_y_mm,
        "radius_mm": op.radius_mm,
        "count": op.count,
        "designation": op.designation,
        "start_angle_deg": op.start_angle_deg,
        "material": op.material,
        "bar_ids": list(op.bar_ids),
        "bar_point_ids": list(op.bar_point_ids),
    }


def _as_optional_name(name: str, value: object) -> str | None:
    return None if value is None else as_str(name, value)


def _as_optional_float(name: str, value: object) -> float | None:
    return None if value is None else as_float(name, value)


def _as_pair(name: str, value: object) -> tuple[float, float]:
    if not isinstance(value, list):
        raise DocumentError(f"{name} must be a list of two millimetre components, got {value!r}")
    items = cast(list[object], value)
    if len(items) != 2:
        raise DocumentError(f"{name} must be a list of two millimetre components, got {value!r}")
    return (as_float(f"{name}[0]", items[0]), as_float(f"{name}[1]", items[1]))


def _boundary_args(
    payload: dict[str, object],
) -> tuple[tuple[VertexRef, ...], VertexRef | None, float | None]:
    center = payload.get("center_id")
    ring = payload.get("point_ids", [])
    if ring == ():  # the catalog fills an omitted ring with its schema default, ()
        ring = []
    return (
        as_vertex_tuple("point_ids", ring),
        None if center is None else as_vertex("center_id", center),
        _as_optional_float("radius_mm", payload.get("radius_mm")),
    )


def _parse_face_op(kind: object, payload: dict[str, object]) -> SectionOp | None:
    if kind == "AddSectionFace":
        point_ids, center_id, radius_mm = _boundary_args(payload)
        return AddSectionFace(
            role=as_str("role", payload["role"]),
            material=_as_optional_name("material", payload.get("material")),
            point_ids=point_ids,
            center_id=center_id,
            radius_mm=radius_mm,
            label=as_optional_str(payload.get("label")),
            entity_id=as_optional_entity_id(payload.get("entity_id")),
        )
    if kind == "AddFaceHole":
        point_ids, center_id, radius_mm = _boundary_args(payload)
        raw_index = payload.get("hole_index")
        return AddFaceHole(
            face_id=as_entity_id("face_id", payload["face_id"]),
            point_ids=point_ids,
            center_id=center_id,
            radius_mm=radius_mm,
            hole_index=None if raw_index is None else as_int("hole_index", raw_index),
        )
    if kind == "AddSteelShape":
        return AddSteelShape(
            point_ids=as_vertex_tuple("point_ids", payload["point_ids"]),
            material=as_str("material", payload["material"]),
            catalog=as_str("catalog", payload["catalog"]),
            designation=as_str("designation", payload["designation"]),
            anchor_mm=_as_pair("anchor_mm", payload["anchor_mm"]),
            rotation_deg=as_float("rotation_deg", payload.get("rotation_deg", 0.0)),
            label=as_optional_str(payload.get("label")),
            entity_id=as_optional_entity_id(payload.get("entity_id")),
        )
    if kind == "AddCircularTie":
        return AddCircularTie(
            kind=as_str("kind", payload["kind"]),
            center_id=as_vertex("center_id", payload["center_id"]),
            centerline_radius_mm=as_float(
                "centerline_radius_mm", payload["centerline_radius_mm"]
            ),
            designation=as_str("designation", payload["designation"]),
            pitch_mm=as_float("pitch_mm", payload["pitch_mm"]),
            label=as_optional_str(payload.get("label")),
            entity_id=as_optional_entity_id(payload.get("entity_id")),
        )
    if kind == "AddBarsOnCircle":
        return AddBarsOnCircle(
            center_x_mm=as_float("center_x_mm", payload["center_x_mm"]),
            center_y_mm=as_float("center_y_mm", payload["center_y_mm"]),
            radius_mm=as_float("radius_mm", payload["radius_mm"]),
            count=as_int("count", payload["count"]),
            designation=as_str("designation", payload["designation"]),
            start_angle_deg=as_float("start_angle_deg", payload.get("start_angle_deg", 0.0)),
            material=_as_optional_name("material", payload.get("material")),
            bar_ids=as_id_tuple("bar_ids", payload.get("bar_ids", [])),
            bar_point_ids=as_id_tuple("bar_point_ids", payload.get("bar_point_ids", [])),
        )
    return None
