"""Handlers for the bar-layout gestures (ADR 0024 decision 3, plan stage C3).

A row and an edge layout are each one op and one undo. Positions come from
`section.layout` (an inclined layout sits on an exact lattice, ADR 0032); every bar gets a
fresh point of its own, as `AddBar` does (decision 5).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import replace

from apeCAD.draft.state import DraftState
from apeCAD.entities import Bar, ConcreteFace, CoverGuide, EntityId, Point
from apeCAD.errors import DocumentError
from apeCAD.geometry import XYZ
from apeCAD.ops import AddBarRow, AddBarsAlongEdge
from apeCAD.section.cover import cover_rings
from apeCAD.section.designations import diameter_of
from apeCAD.section.geometry import Point2
from apeCAD.section.layout import DUPLICATE_BAR_MM, edge_positions, row_positions


def add_bar_row(state: DraftState, op: AddBarRow) -> AddBarRow:
    """Bars from start to end, by count or by spacing with the remainder centred."""
    positions = row_positions(
        (op.start_x_mm, op.start_y_mm), (op.end_x_mm, op.end_y_mm), op.count, op.spacing_mm
    )
    bar_ids, point_ids = _place_bars(state, positions, op.designation, op)
    return replace(op, bar_ids=bar_ids, bar_point_ids=point_ids)


def add_bars_along_edge(state: DraftState, op: AddBarsAlongEdge) -> AddBarsAlongEdge:
    """Bars on one edge of the face's bar-centre ring; positions near a bar are skipped."""
    face = state.entities.get(op.face_id)
    if not isinstance(face, ConcreteFace):
        raise DocumentError(f"entity {op.face_id} is not a concrete face")
    guide = next(
        (
            e
            for e in state.entities.values()
            if isinstance(e, CoverGuide) and e.face_id == op.face_id
        ),
        None,
    )
    if guide is None:
        raise DocumentError(
            f"face {op.face_id} has no cover guide; set one with SetCover before laying "
            "bars along its edges"
        )
    outline: list[Point2] = []
    for point_id in face.point_ids:
        xyz = state.require_point(point_id).xyz_mm
        if xyz.z_mm != 0.0:
            raise DocumentError(
                f"face {op.face_id} has point {point_id} at z = {xyz.z_mm:g} mm; "
                "a section lies on z = 0 (ADR 0024)"
            )
        outline.append((xyz.x_mm, xyz.y_mm))
    rings = cover_rings(outline, guide)
    if rings.bar_centre_ring_mm is None:
        raise DocumentError(f"face {op.face_id} has no bar-centre ring: {rings.reason}")
    positions = edge_positions(rings.bar_centre_ring_mm, op.edge_index, op.count, op.spacing_mm)
    taken = [_bar_xy(state, bar) for bar in state.entities.values() if isinstance(bar, Bar)]
    fresh: list[Point2] = []
    for p in positions:
        if all(math.hypot(p[0] - q[0], p[1] - q[1]) > DUPLICATE_BAR_MM for q in taken):
            fresh.append(p)
            taken.append(p)
    if not fresh:
        raise DocumentError(
            f"every position on edge {op.edge_index} of face {op.face_id} already has a bar "
            f"within {DUPLICATE_BAR_MM:g} mm"
        )
    bar_ids, point_ids = _place_bars(state, fresh, op.designation, op)
    return replace(op, bar_ids=bar_ids, bar_point_ids=point_ids)


def _place_bars(
    state: DraftState,
    positions: Sequence[Point2],
    designation: str,
    recorded: AddBarRow | AddBarsAlongEdge,
) -> tuple[tuple[EntityId, ...], tuple[EntityId, ...]]:
    """One point and one bar per position; replay reuses the ids the committed op recorded."""
    if recorded.bar_ids and len(recorded.bar_ids) != len(positions):
        raise DocumentError(
            f"the op records {len(recorded.bar_ids)} bars; this layout places {len(positions)}"
        )
    diameter = diameter_of(designation)
    bar_ids: list[EntityId] = []
    point_ids: list[EntityId] = []
    for k, (x_mm, y_mm) in enumerate(positions):
        point_id = state.allocate_id(recorded.bar_point_ids[k] if recorded.bar_point_ids else None)
        state.entities[point_id] = Point(
            entity_id=point_id, xyz_mm=XYZ(x_mm, y_mm, 0.0), label=None
        )
        bar_id = state.allocate_id(recorded.bar_ids[k] if recorded.bar_ids else None)
        state.entities[bar_id] = Bar(
            entity_id=bar_id, point_id=point_id, designation=designation, diameter_mm=diameter
        )
        bar_ids.append(bar_id)
        point_ids.append(point_id)
    return tuple(bar_ids), tuple(point_ids)


def _bar_xy(state: DraftState, bar: Bar) -> Point2:
    xyz = state.require_point(bar.point_id).xyz_mm
    return (xyz.x_mm, xyz.y_mm)
