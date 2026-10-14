"""Handlers for section mode (ADR 0024): faces, outlines, wall legs, cover, bars, hoops, ties.

Intent only: positions, rings of bar ids, designations and names. No mechanics. A section
lives on z = 0, x right and y up, in world millimetres (decision 6).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from apeCAD.draft.state import DraftState
from apeCAD.entities import (
    Bar,
    ConcreteFace,
    CoverGuide,
    Crosstie,
    EntityId,
    Hoop,
    LegSteel,
    Point,
    WallLeg,
)
from apeCAD.errors import DocumentError
from apeCAD.geometry import XYZ
from apeCAD.ops import (
    AddBar,
    AddConcreteFace,
    AddCrosstie,
    AddHoop,
    AddSectionOutline,
    AddWallChain,
    AddWallLeg,
    PointAt,
    SetBarSize,
    SetCover,
    SetLegReinforcement,
    SetMaterial,
    SetTransverse,
    VertexRef,
)
from apeCAD.ops.section import require_crosstie_hooks, require_hoop_hooks
from apeCAD.section.designations import diameter_of
from apeCAD.section.geometry import (
    Point2,
    chain_outline,
    convex_hull_ccw,
    require_simple,
    signed_area,
)


def add_concrete_face(state: DraftState, op: AddConcreteFace) -> AddConcreteFace:
    """A solid face; the ring is stored CCW whatever order the vertices came in.

    A second solid face is allowed: it is a lint warning, not a refusal (ADR 0024 P3).
    """
    point_ids, refs = state.resolve_all(op.point_ids)
    entity_id = _store_face(state, point_ids, op.material, op.label, op.entity_id)
    return replace(op, point_ids=refs, entity_id=entity_id)


def add_section_outline(state: DraftState, op: AddSectionOutline) -> AddSectionOutline:
    """The outline gesture: one solid face, one op, one undo (ADR 0024 decision 3)."""
    point_ids, refs = state.resolve_all(op.point_ids)
    entity_id = _store_face(state, point_ids, op.material, op.label, op.entity_id)
    return replace(op, point_ids=refs, entity_id=entity_id)


def add_wall_chain(state: DraftState, op: AddWallChain) -> AddWallChain:
    """An axis chain becomes one outline face (`chain_outline`) and one leg per segment.

    Live, the outline vertices reuse a point within 1 mm or create one; the committed op
    records them in `ring`, and the legs in `leg_ids`, so replay rebuilds the same ids.
    """
    axis_ids, axis_refs = state.resolve_all(op.point_ids)
    axis = [_xy_on_plane(state, point_id) for point_id in axis_ids]
    segments = len(axis) - 1
    thicknesses = op.thickness_mm * segments if len(op.thickness_mm) == 1 else op.thickness_mm
    outline = chain_outline(axis, list(thicknesses))
    ring_refs: tuple[VertexRef, ...]
    if op.ring is None:
        ring_refs = tuple(PointAt(XYZ(x, y, 0.0)) for x, y in outline)
    elif len(op.ring) != len(outline):
        raise DocumentError(
            f"ring records {len(op.ring)} vertices; this wall chain's outline has {len(outline)}"
        )
    else:
        ring_refs = op.ring
    ring_ids, ring_refs = state.resolve_all(ring_refs)
    face_id = _store_face(state, ring_ids, op.material, op.label, op.entity_id)
    leg_ids: list[EntityId] = []
    for k in range(segments):
        leg = _LegSpec(axis_ids[k], axis_ids[k + 1], thicknesses[k], face_id, op.horizontal)
        leg_ids.append(_store_leg(state, leg, None, op.leg_ids[k] if op.leg_ids else None))
    return replace(
        op,
        point_ids=axis_refs,
        entity_id=face_id,
        ring=ring_refs,
        leg_ids=tuple(leg_ids),
    )


def add_wall_leg(state: DraftState, op: AddWallLeg) -> AddWallLeg:
    """A leg on an existing face, e.g. the three legs of a T drawn as one polygon."""
    _require_face(state, op.face_id)
    start_id, start_ref = state.resolve(op.start_id)
    end_id, end_ref = state.resolve(op.end_id)
    state.reject_taken_label(op.label)
    leg = _LegSpec(start_id, end_id, op.thickness_mm, op.face_id, op.horizontal)
    entity_id = _store_leg(state, leg, op.label, op.entity_id)
    return replace(op, start_id=start_ref, end_id=end_ref, entity_id=entity_id)


def set_leg_reinforcement(state: DraftState, op: SetLegReinforcement) -> SetLegReinforcement:
    leg = state.entities.get(op.leg_id)
    if not isinstance(leg, WallLeg):
        raise DocumentError(f"entity {op.leg_id} is not a wall leg")
    steel = LegSteel(op.designation, op.spacing_mm, op.curtains)
    state.entities[op.leg_id] = replace(leg, horizontal=steel)
    return op


def set_cover(state: DraftState, op: SetCover) -> SetCover:
    """Create the face's cover guide, or change the one it has (one per face)."""
    _require_face(state, op.face_id)
    existing = next(
        (
            e
            for e in state.entities.values()
            if isinstance(e, CoverGuide) and e.face_id == op.face_id
        ),
        None,
    )
    if existing is not None:
        if op.entity_id is not None and op.entity_id != existing.entity_id:
            raise DocumentError(
                f"face {op.face_id} already has cover guide {existing.entity_id}, "
                f"not {op.entity_id}"
            )
        entity_id = existing.entity_id
    else:
        entity_id = state.allocate_id(op.entity_id)
    state.entities[entity_id] = CoverGuide(
        entity_id=entity_id,
        face_id=op.face_id,
        cover_mm=op.cover_mm,
        tie_diameter_mm=op.tie_diameter_mm,
        bar_diameter_mm=op.bar_diameter_mm,
        label=None if existing is None else existing.label,
    )
    return replace(op, entity_id=entity_id)


def _store_face(
    state: DraftState,
    point_ids: tuple[EntityId, ...],
    material: str,
    label: str | None,
    requested: EntityId | None,
) -> EntityId:
    ring = [_xy_on_plane(state, point_id) for point_id in point_ids]
    require_simple(ring, "a concrete face")
    if signed_area(ring) < 0.0:
        point_ids = point_ids[::-1]
    state.reject_taken_label(label)
    entity_id = state.allocate_id(requested)
    state.register_label(entity_id, label)
    state.entities[entity_id] = ConcreteFace(
        entity_id=entity_id,
        point_ids=point_ids,
        material=material,
        role="solid",
        label=label,
    )
    return entity_id


@dataclass(frozen=True, slots=True)
class _LegSpec:
    start_id: EntityId
    end_id: EntityId
    thickness_mm: float
    face_id: EntityId
    horizontal: LegSteel | None


def _store_leg(
    state: DraftState, leg: _LegSpec, label: str | None, requested: EntityId | None
) -> EntityId:
    start = _xy_on_plane(state, leg.start_id)
    end = _xy_on_plane(state, leg.end_id)
    if start == end:
        raise DocumentError(
            f"a wall leg needs two distinct axis points; {leg.start_id} and {leg.end_id} "
            f"are both at {start}"
        )
    entity_id = state.allocate_id(requested)
    state.register_label(entity_id, label)
    state.entities[entity_id] = WallLeg(
        entity_id=entity_id,
        start_id=leg.start_id,
        end_id=leg.end_id,
        thickness_mm=leg.thickness_mm,
        face_id=leg.face_id,
        horizontal=leg.horizontal,
        label=label,
    )
    return entity_id


def _require_face(state: DraftState, face_id: EntityId) -> ConcreteFace:
    face = state.entities.get(face_id)
    if not isinstance(face, ConcreteFace):
        raise DocumentError(f"entity {face_id} is not a concrete face")
    return face


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
        face = _require_face(state, entity_id)
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
