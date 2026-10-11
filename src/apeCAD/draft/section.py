"""Handlers for section mode (ADR 0024): concrete faces, bars, hoops, crossties, settings.

Intent only: positions, rings of bar ids, designations and names. No mechanics. A section
lives on z = 0, x right and y up, in world millimetres (decision 6).
"""

from __future__ import annotations

from dataclasses import replace

from apeCAD.draft.state import DraftState
from apeCAD.entities import Bar, ConcreteFace, Crosstie, EntityId, Hoop, Point
from apeCAD.errors import DocumentError
from apeCAD.geometry import XYZ
from apeCAD.ops import (
    AddBar,
    AddConcreteFace,
    AddCrosstie,
    AddHoop,
    SetBarSize,
    SetMaterial,
    SetTransverse,
)
from apeCAD.ops.section import require_crosstie_hooks, require_hoop_hooks
from apeCAD.section.designations import diameter_of
from apeCAD.section.geometry import Point2, convex_hull_ccw, require_simple, signed_area


def add_concrete_face(state: DraftState, op: AddConcreteFace) -> AddConcreteFace:
    """A solid face; the ring is stored CCW whatever order the vertices came in.

    A second solid face is allowed: it is a lint warning, not a refusal (ADR 0024 P3).
    """
    point_ids, refs = state.resolve_all(op.point_ids)
    ring = [_xy_on_plane(state, point_id) for point_id in point_ids]
    require_simple(ring, "a concrete face")
    if signed_area(ring) < 0.0:
        point_ids = point_ids[::-1]
    state.reject_taken_label(op.label)
    entity_id = state.allocate_id(op.entity_id)
    state.register_label(entity_id, op.label)
    state.entities[entity_id] = ConcreteFace(
        entity_id=entity_id,
        point_ids=point_ids,
        material=op.material,
        role="solid",
        label=op.label,
    )
    return replace(op, point_ids=refs, entity_id=entity_id)


def add_bar(state: DraftState, op: AddBar) -> AddBar:
    """A bar with a fresh Point of its own, never one found by `point_at` (decision 5)."""
    state.reject_taken_label(op.label)
    point_id = state.allocate_id(op.point_id)
    state.entities[point_id] = Point(
        entity_id=point_id, xyz_mm=XYZ(op.x_mm, op.y_mm, 0.0), label=None
    )
    entity_id = state.allocate_id(op.entity_id)
    state.register_label(entity_id, op.label)
    state.entities[entity_id] = Bar(
        entity_id=entity_id,
        point_id=point_id,
        designation=op.designation,
        diameter_mm=diameter_of(op.designation),
        label=op.label,
    )
    return replace(op, entity_id=entity_id, point_id=point_id)


def add_hoop(state: DraftState, op: AddHoop) -> AddHoop:
    """Store the strict CCW hull of the selected bars, so selection order does not matter."""
    if len(set(op.bar_ids)) != len(op.bar_ids):
        raise DocumentError(f"a hoop names a bar twice: {list(op.bar_ids)}")
    positions = {bar_id: _bar_xy(state, bar_id) for bar_id in op.bar_ids}
    ring = tuple(convex_hull_ccw(positions))
    state.reject_taken_label(op.label)
    entity_id = state.allocate_id(op.entity_id)
    state.register_label(entity_id, op.label)
    state.entities[entity_id] = Hoop(
        entity_id=entity_id,
        bar_ids=ring,
        designation=op.designation,
        diameter_mm=diameter_of(op.designation),
        spacing_mm=op.spacing_mm,
        hooks="135",
        label=op.label,
    )
    return replace(op, entity_id=entity_id)


def add_crosstie(state: DraftState, op: AddCrosstie) -> AddCrosstie:
    state.require_bar(op.bar_a_id)
    state.require_bar(op.bar_b_id)
    state.reject_taken_label(op.label)
    entity_id = state.allocate_id(op.entity_id)
    state.register_label(entity_id, op.label)
    state.entities[entity_id] = Crosstie(
        entity_id=entity_id,
        bar_a_id=op.bar_a_id,
        bar_b_id=op.bar_b_id,
        designation=op.designation,
        diameter_mm=diameter_of(op.designation),
        spacing_mm=op.spacing_mm,
        hooks="135-90" if op.hooks == "135-90" else "135-135",
        label=op.label,
    )
    return replace(op, entity_id=entity_id)


def set_bar_size(state: DraftState, op: SetBarSize) -> SetBarSize:
    diameter = diameter_of(op.designation)
    for entity_id in op.entity_ids:
        bar = state.require_bar(entity_id)
        state.entities[entity_id] = replace(
            bar, designation=op.designation, diameter_mm=diameter
        )
    return op


def set_material(state: DraftState, op: SetMaterial) -> SetMaterial:
    for entity_id in op.entity_ids:
        face = state.entities.get(entity_id)
        if not isinstance(face, ConcreteFace):
            raise DocumentError(f"entity {entity_id} is not a concrete face")
        state.entities[entity_id] = replace(face, material=op.material)
    return op


def set_transverse(state: DraftState, op: SetTransverse) -> SetTransverse:
    """Size, spacing or hooks of hoops and crossties; a None field keeps its value."""
    for entity_id in op.entity_ids:
        tie = state.entities.get(entity_id)
        if not isinstance(tie, (Hoop, Crosstie)):
            raise DocumentError(f"entity {entity_id} is not a hoop or a crosstie")
        designation = tie.designation if op.designation is None else op.designation
        spacing = tie.spacing_mm if op.spacing_mm is None else op.spacing_mm
        common = {
            "designation": designation,
            "diameter_mm": diameter_of(designation),
            "spacing_mm": spacing,
        }
        if isinstance(tie, Hoop):
            if op.hooks is not None:
                require_hoop_hooks(op.hooks)
            state.entities[entity_id] = replace(tie, **common)
        else:
            hooks = tie.hooks
            if op.hooks is not None:
                hooks = "135-90" if require_crosstie_hooks(op.hooks) == "135-90" else "135-135"
            state.entities[entity_id] = replace(tie, hooks=hooks, **common)
    return op


def _bar_xy(state: DraftState, bar_id: EntityId) -> Point2:
    bar = state.require_bar(bar_id)
    xyz = state.require_point(bar.point_id).xyz_mm
    return (xyz.x_mm, xyz.y_mm)


def _xy_on_plane(state: DraftState, point_id: EntityId) -> Point2:
    xyz = state.require_point(point_id).xyz_mm
    if xyz.z_mm != 0.0:
        raise DocumentError(
            f"point {point_id} is at z = {xyz.z_mm:g} mm; a section lies on z = 0 (ADR 0024)"
        )
    return (xyz.x_mm, xyz.y_mm)
