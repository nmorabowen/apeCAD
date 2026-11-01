"""One table from op type to handler. A new op adds one row here (ADR 0023).

`apply_op` is also where the section-template lock runs (ADR 0040 decision 3): while the
draft holds a template, the entity map records what the op writes (`RecordingEntities`)
and `templates.check_template_lock` checks those writes, whatever the op. With no template
it costs one test and the map stays a plain dict.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from apeCAD.draft import create, edit, meta, rebar, section, templates, transform
from apeCAD.draft.state import DraftState, RecordingEntities
from apeCAD.errors import DocumentError
from apeCAD.ops import (
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
    AddSectionTemplate,
    AddSteelShape,
    AddWallChain,
    AddWallLeg,
    ArrayLinear,
    ArrayPolar,
    BreakCrossing,
    ChamferCorner,
    Delete,
    EditSectionTemplate,
    ExplodeSectionTemplate,
    Extrude,
    FilletCorner,
    InsertNode,
    JoinPolyline,
    Mirror,
    Op,
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
)

Handler = Callable[[DraftState, Any], Op]

HANDLERS: dict[type[object], Handler] = {
    AddPoint: create.add_point,
    AddLine: create.add_line,
    AddLineChain: create.add_line_chain,
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
    AddConcreteFace: section.add_concrete_face,
    AddBar: section.add_bar,
    AddHoop: section.add_hoop,
    AddCrosstie: section.add_crosstie,
    SetBarSize: section.set_bar_size,
    SetMaterial: section.set_material,
    SetTransverse: section.set_transverse,
    AddSectionOutline: section.add_section_outline,
    AddWallChain: section.add_wall_chain,
    AddWallLeg: section.add_wall_leg,
    SetLegReinforcement: section.set_leg_reinforcement,
    SetCover: section.set_cover,
    AddBarRow: rebar.add_bar_row,
    AddBarsAlongEdge: rebar.add_bars_along_edge,
    AddSectionFace: section.add_section_face,
    AddFaceHole: section.add_face_hole,
    AddSteelShape: section.add_steel_shape,
    AddCircularTie: rebar.add_circular_tie,
    AddBarsOnCircle: rebar.add_bars_on_circle,
    AddSectionTemplate: templates.add_section_template,
    EditSectionTemplate: templates.edit_section_template,
    ExplodeSectionTemplate: templates.explode_section_template,
}


def apply_op(state: DraftState, op: Op) -> Op:
    """Mutate state by one op; return it with every allocated id filled in."""
    handler = HANDLERS.get(type(op))
    if handler is None:
        raise DocumentError(f"internal error: no handler for {type(op).__name__}")
    if not state.template_ids:
        if isinstance(state.entities, RecordingEntities):  # the last template went
            state.entities = dict(state.entities)
        return handler(state, op)
    if not isinstance(state.entities, RecordingEntities):
        state.entities = RecordingEntities(state.entities)
    entities = state.entities
    entities.reset()
    before_templates = frozenset(state.template_ids)
    committed = handler(state, op)
    templates.check_template_lock(entities.written, before_templates, state)
    return committed
