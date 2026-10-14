"""JSON codec for the section-mode ops (ADR 0024). `ops.codec` delegates here first."""

from __future__ import annotations

from typing import cast

from apeCAD.entities import LegSteel
from apeCAD.errors import DocumentError
from apeCAD.ops.section import (
    AddBar,
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
    wall = _parse_wall_op(kind, payload)
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
