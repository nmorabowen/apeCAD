"""JSON codec for the section-mode ops (ADR 0024). `ops.codec` delegates here first."""

from __future__ import annotations

from apeCAD.ops.section import (
    AddBar,
    AddConcreteFace,
    AddCrosstie,
    AddHoop,
    SectionOp,
    SetBarSize,
    SetMaterial,
    SetTransverse,
)
from apeCAD.ops.values import (
    as_entity_id,
    as_float,
    as_id_tuple,
    as_optional_entity_id,
    as_optional_str,
    as_str,
    as_vertex_tuple,
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
    return {
        "op": "SetTransverse",
        "entity_ids": list(op.entity_ids),
        "designation": op.designation,
        "spacing_mm": op.spacing_mm,
        "hooks": op.hooks,
    }


def parse_section_op(kind: object, payload: dict[str, object]) -> SectionOp | None:
    """The section op `payload` names, or None when `kind` is not a section op."""
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
