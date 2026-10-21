"""DXF export of the drawing (ADR 0034, stage D5 of ADR 0031).

AC1027 (R2013), model space at 1:1 in millimetres, plan (`top`) only: the file holds world
coordinates and any CAD program draws the other views. Layers are the style table's
`layer_name` values (`render/style.py`) with their ADR-005 pen and ink as ByLayer weight and
colour, so the file links into the office template unchanged. Section annotation follows
`annotate`, at the D4 layout's standard scale: native MTEXT tags and DIMENSION entities in
the ADR-007 / ADR-006 style names, placed where the SVG puts them.

ezdxf comes from the optional `apeCAD[dxf]` extra and is imported only inside
`export_dxf`, so `import apeCAD` never imports it. Without it, `DxfUnavailableError`.
ezdxf's signatures are only partly typed (its vector alias carries an Unknown), so its
objects cross this module as explicit `Any`; tests/test_dxf.py checks the file by reading it
back with ezdxf.
"""

from __future__ import annotations

import io
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from apeCAD.document import Document
from apeCAD.entities import Arc, Circle, Ellipse, Entity, EntityId
from apeCAD.render.annotate import (
    DIM_OFFSET_PX,
    Layout,
    dimension_text_boxes,
    leaders,
    plan_layout,
    scale_note,
    section_notes,
)
from apeCAD.render.api import RenderArgumentError, known_ids, save_text
from apeCAD.render.drawable import Drawable, Path3
from apeCAD.render.scene import closure, drawables, entity_map
from apeCAD.render.style import SECTION_STYLE, SKETCH_STYLE, LayerStyle
from apeCAD.render.svg import legend_geometry, view_title
from apeCAD.render.views import VIEWS, Vec2, Vec3

DXF_VERSION = "R2013"  # AC1027
CHORD_ERROR_MM = 0.5  # tessellation of what has no native DXF curve
FRAME_PX = (800, 600)  # the SVG's default frame: the DXF annotation matches that render
PX_PER_PAPER_MM = 5.0

# ADR-005 colours: ACI where the office pen is an ACI colour, true colour otherwise.
ACI = {"Black": 7, "Dark Grey": 8, "Grey": 9}
RGB = {"Blue": (0, 0, 119), "Grey210": (210, 210, 210)}
# ADR-005 pens in mm → DXF lineweight enum (1/100 mm); DXF has no 0.10, 0.09 is nearest.
LINEWEIGHT = {0.10: 9, 0.20: 20, 0.30: 30, 0.40: 40, 0.50: 50}

TEXT_STYLE = "Note - 2.0mm ArialNarrow Transparent"  # ADR-007
TITLE_STYLE = "Title - Bahnschrift SemiBold Condensed"  # ADR-009 display face
DIM_STYLE = "Arrow - 2.5mm ArialNarrow Transparent"  # ADR-006 default linear

# Layers the style table does not name: annotation and the concrete fill.
EXTRA_LAYERS: dict[str, tuple[str, str]] = {  # name: (ADR-005 line style, colour key)
    "CONCRETE-FILL": ("0.10mm S-Grey210", "Grey210"),
    "TAG": ("0.10mm S-Blue", "Blue"),
    "DIMENSION": ("0.10mm S-Blue", "Blue"),
    "VIEW-TITLE": ("0.30mm S-Blue", "Blue"),
}


class DxfUnavailableError(RenderArgumentError):
    """The `dxf` extra is not installed. Agents see it as `UNAVAILABLE` (never a fallback)."""

    code = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class DxfResult:
    dxf: str
    view: str
    entities: int  # drawables written
    layers: tuple[str, ...]  # layers that hold at least one entity
    scale: str | None  # "1:n" when annotated
    path: str | None = None


def export_dxf(
    document: Document,
    *,
    view: str | None = "top",
    ids: Sequence[EntityId] | None = None,
    annotate: bool = True,
    save_to: str | None = None,
    root: Path | None = None,
) -> DxfResult:
    """DXF text of the draft (ADR 0034). `ids` limits it to those entities and what they are
    built from; `save_to` is relative to `root`, as for `render_svg`."""
    if view not in (None, "top"):
        raise RenderArgumentError(f"DXF exports the plan only: view must be top, got {view!r}")
    try:
        from ezdxf.filemanagement import new as new_drawing
    except ImportError as exc:  # pragma: no cover - exercised by the core CI job
        raise DxfUnavailableError(
            "DXF export needs the dxf extra: pip install apeCAD[dxf]"
        ) from exc
    entities = entity_map(document)
    children = document.brep().children
    draw_ids = (
        set(entities) if ids is None else closure(known_ids("ids", ids, entities), children)
    )
    items = drawables(entities, draw_ids, CHORD_ERROR_MM)
    doc: Any = new_drawing(DXF_VERSION, setup=True, units=4)  # 4 = millimetres
    doc.header["$MEASUREMENT"] = 1  # metric
    _styles(doc)
    msp: Any = doc.modelspace()
    used: set[str] = set()
    for d in items:
        used.add(_write(msp, d, entities.get(d.entity_id)))
        if d.layer == "concrete":
            used.add("CONCRETE-FILL")
    layout = _layout(entities, items) if annotate else None
    if layout is not None:
        used |= _annotation(doc, msp, layout, view_title(VIEWS["top"], items), _plane_z(items))
    _layers(doc)
    stream = io.StringIO()
    doc.write(stream)
    text = stream.getvalue()
    path = None if save_to is None else save_text(text, save_to, root)
    scale = None if layout is None else f"1:{layout.scale_n}"
    return DxfResult(text, "top", len(items), tuple(sorted(used)), scale, path)


# ---- tables -----------------------------------------------------------------------------


def _all_styles() -> dict[str, LayerStyle]:
    return {**SECTION_STYLE, **SKETCH_STYLE}


def _layers(doc: Any) -> None:
    """One layer per style-table layer name plus the annotation layers, ByLayer ADR-005."""
    specs: dict[str, tuple[str, str]] = {}
    for style in _all_styles().values():
        line = style.line_style or "0.10mm S-Black"
        specs.setdefault(style.layer_name, (line, line.split("-", 1)[1]))
    specs.update(EXTRA_LAYERS)
    for name, (line, colour) in sorted(specs.items()):
        mm = float(line.split("mm")[0])
        hidden = " H-" in f" {line.split(' ', 1)[1]}"
        layer = doc.layers.add(name)
        layer.dxf.lineweight = LINEWEIGHT[round(mm, 2)]
        layer.dxf.linetype = "HIDDEN" if hidden else "CONTINUOUS"
        if colour in RGB:
            layer.rgb = RGB[colour]
        else:
            layer.color = ACI[colour]
        layer.description = line


HIDDEN_PATTERN = [3.0, 2.0, -1.0]  # ADR-005 `H-`: total, 2.0 mm dash, 1.0 mm gap (paper)


def _styles(doc: Any) -> None:
    if "HIDDEN" not in doc.linetypes:  # setup=True does not define it for R2013
        doc.linetypes.add("HIDDEN", HIDDEN_PATTERN, description="Hidden __ __ __ (ADR-005 H-)")
    doc.styles.add(TEXT_STYLE, font="arialn.ttf")
    doc.styles.add(TITLE_STYLE, font="bahnschrift.ttf")
    dim = doc.dimstyles.add(DIM_STYLE)
    dim.dxf.dimtxsty = TEXT_STYLE
    dim.dxf.dimtxt = 2.5  # paper mm; dimscale makes it model mm
    dim.dxf.dimasz = ARROW_MM
    dim.dxf.dimexo = 0.6  # extension line gap at the object (3 px)
    dim.dxf.dimexe = 0.8  # past the dimension line (4 px)
    dim.dxf.dimgap = 0.6
    dim.dxf.dimtad = 1  # text above the line
    dim.dxf.dimdec = 0  # whole millimetres
    for key in ("dimclrd", "dimclre", "dimclrt"):
        setattr(dim.dxf, key, 256)  # ByLayer


ARROW_MM = 1.6  # ADR-006 "Arrow Filled 30", the default closed filled block


# ---- geometry ---------------------------------------------------------------------------


def _layer(d: Drawable) -> str:
    return _all_styles()[d.layer].layer_name


def _write(msp: Any, d: Drawable, entity: Entity | None) -> str:
    """Write one drawable on its layer; return the layer."""
    layer = _layer(d)
    attribs: dict[str, object] = {"layer": layer}
    if d.layer == "bar":
        for points, _closed in d.paths:
            for p in points:
                msp.add_circle(p, d.radius_mm, dxfattribs=attribs)
                hatch = msp.add_hatch(dxfattribs={**attribs, "elevation": (0.0, 0.0, p[2])})
                hatch.set_solid_fill(color=256)  # ByLayer: the BAR layer's blue
                hatch.paths.add_edge_path().add_arc((p[0], p[1]), d.radius_mm, 0.0, 360.0)
        return layer
    if d.layer == "point":
        for points, _closed in d.paths:
            for p in points:
                msp.add_point(p, dxfattribs=attribs)
        return layer
    if _native_curve(msp, entity, d, attribs):
        return layer
    for path in d.paths:
        _polyline(msp, path, attribs)
    if d.layer == "concrete":
        for points, _closed in d.paths:
            fill = msp.add_hatch(
                dxfattribs={"layer": "CONCRETE-FILL", "elevation": (0.0, 0.0, points[0][2])}
            )
            fill.set_solid_fill(color=256)  # ByLayer: Grey210
            fill.paths.add_polyline_path([(p[0], p[1]) for p in points], is_closed=True)
    return layer


def _polyline(msp: Any, path: Path3, attribs: dict[str, object]) -> None:
    points, closed = path
    if len(points) < 2:
        return
    z = points[0][2]
    if all(abs(p[2] - z) < 1e-9 for p in points):
        msp.add_lwpolyline(
            [(p[0], p[1]) for p in points],
            close=closed,
            dxfattribs={**attribs, "elevation": z},
        )
    else:
        msp.add_polyline3d(list(points), close=closed, dxfattribs=attribs)


def _native_curve(
    msp: Any, entity: Entity | None, d: Drawable, attribs: dict[str, object]
) -> bool:
    """Circles, arcs and ellipses in a horizontal plane stay native DXF curves (ADR 0034
    decision 3); anything else is written as its tessellation."""
    if not isinstance(entity, (Circle, Arc, Ellipse)) or d.anchor is None:
        return False
    points = [p for path, _ in d.paths for p in path]
    z = points[0][2]
    if any(abs(p[2] - z) > 1e-6 for p in points):
        return False
    if isinstance(entity, Circle):
        msp.add_circle(d.anchor, entity.radius_mm, dxfattribs=attribs)
        return True
    if isinstance(entity, Ellipse):
        rx, ry = entity.radius_x_mm, entity.radius_y_mm
        major = (rx, 0.0, 0.0) if rx >= ry else (0.0, ry, 0.0)
        msp.add_ellipse(d.anchor, major_axis=major, ratio=min(rx, ry) / max(rx, ry),
                        dxfattribs=attribs)
        return True
    start, end = points[0], points[-1]
    circle = _circumcircle(start, d.anchor, end)
    if circle is None:
        return False
    (cx, cy), radius = circle
    a0 = math.degrees(math.atan2(start[1] - cy, start[0] - cx))
    a1 = math.degrees(math.atan2(end[1] - cy, end[0] - cx))
    am = math.degrees(math.atan2(d.anchor[1] - cy, d.anchor[0] - cx))
    if (am - a0) % 360.0 > (a1 - a0) % 360.0:  # the mid point is on the clockwise way round
        a0, a1 = a1, a0
    msp.add_arc((cx, cy, z), radius, a0, a1, dxfattribs=attribs)
    return True


def _circumcircle(a: Vec3, b: Vec3, c: Vec3) -> tuple[Vec2, float] | None:
    d = 2.0 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
    if abs(d) < 1e-12:
        return None
    sa, sb, sc = (a[0] ** 2 + a[1] ** 2), (b[0] ** 2 + b[1] ** 2), (c[0] ** 2 + c[1] ** 2)
    ux = (sa * (b[1] - c[1]) + sb * (c[1] - a[1]) + sc * (a[1] - b[1])) / d
    uy = (sa * (c[0] - b[0]) + sb * (a[0] - c[0]) + sc * (b[0] - a[0])) / d
    return (ux, uy), math.hypot(a[0] - ux, a[1] - uy)


def _plane_z(items: list[Drawable]) -> float:
    concrete = [d for d in items if d.layer == "concrete"]
    return concrete[0].paths[0][0][0][2] if concrete else 0.0


# ---- annotation -------------------------------------------------------------------------


def _layout(entities: dict[EntityId, Entity], items: list[Drawable]) -> Layout | None:
    """The D4 layout at the SVG's default frame and labels, so the DXF matches that render
    (a tie tag carries its hoop's label, as there)."""
    notes = section_notes(VIEWS["top"], entities, items, True)
    if notes is None:
        return None
    us = [p[0] for d in items for path, _ in d.paths for p in path]
    vs = [p[1] for d in items for path, _ in d.paths for p in path]
    bounds = ((min(us), min(vs)), (max(us), max(vs)))
    return plan_layout(notes, bounds, FRAME_PX[0], FRAME_PX[1], 0.05)


def _annotation(
    doc: Any, msp: Any, layout: Layout, title: str, z: float
) -> set[str]:
    """Tags, overall dimensions, title and scale note, in model mm at the layout's scale."""
    n = layout.scale_n
    doc.dimstyles.get(DIM_STYLE).dxf.dimscale = float(n)
    doc.header["$LTSCALE"] = float(n)  # the hidden dashes print at their paper size
    to_mm = _px_to_mm(layout)

    def at(px: Vec2) -> Vec3:
        u, v = to_mm(px)
        return (u, v, z)

    text_h = 2.0 * n  # ADR-007 body note, printed at 2.0 mm
    for placed, line in zip(layout.placed, leaders(layout), strict=True):
        msp.add_lwpolyline([at(p)[:2] for p in line], dxfattribs={"layer": "TAG", "elevation": z})
        mtext = msp.add_mtext(placed.tag.text, dxfattribs={
            "layer": "TAG", "style": TEXT_STYLE, "char_height": text_h,
        })
        attach = 9 if placed.end else 7  # bottom right / bottom left, as the SVG baseline
        mtext.set_location(at((placed.x, placed.y)), attachment_point=attach)
    _dimensions(msp, layout, at)
    x0, _y0, title_y, rule_y, rule_x1, note_y = legend_geometry(FRAME_PX[1], title, True)
    heading = msp.add_mtext(title, dxfattribs={
        "layer": "VIEW-TITLE", "style": TITLE_STYLE, "char_height": 3.5 * n,
    })
    heading.set_location(at((x0, title_y)), attachment_point=7)
    msp.add_lwpolyline([at((x0, rule_y))[:2], at((rule_x1, rule_y))[:2]],
                       dxfattribs={"layer": "VIEW-TITLE", "elevation": z})
    note = msp.add_mtext(scale_note(n), dxfattribs={
        "layer": "VIEW-TITLE", "style": TEXT_STYLE, "char_height": text_h,
    })
    note.set_location(at((x0, note_y)), attachment_point=7)
    return {"TAG", "DIMENSION", "VIEW-TITLE"}


def _px_to_mm(layout: Layout) -> Callable[[Vec2], Vec2]:
    width, height = FRAME_PX
    (cu, cv), s = layout.centre_mm, layout.scale_px_per_mm

    def to_mm(px: Vec2) -> Vec2:
        return cu + (px[0] - width / 2.0) / s, cv - (px[1] - height / 2.0) / s

    return to_mm


def _dimensions(msp: Any, layout: Layout, at: Callable[[Vec2], Vec3]) -> None:
    """The two overall dimensions as native, associative-style DIMENSION entities, their
    text where the SVG slid it clear of the leaders."""
    width, height = FRAME_PX
    s = layout.scale_px_per_mm
    (cu, cv) = layout.centre_mm

    def to_px(uv: Vec2) -> Vec2:
        return width / 2.0 + (uv[0] - cu) * s, height / 2.0 - (uv[1] - cv) * s

    (u0, v0), (u1, v1) = layout.notes.box_mm
    width_box, depth_box = dimension_text_boxes(layout.notes, to_px, leaders(layout))
    offset = DIM_OFFSET_PX / s
    z = at((0.0, 0.0))[2]
    attribs = {"layer": "DIMENSION"}
    across = msp.add_linear_dim(
        base=(u0, v0 - offset, z), p1=(u0, v0, z), p2=(u1, v0, z),
        location=at(((width_box[0] + width_box[2]) / 2.0, (width_box[1] + width_box[3]) / 2.0)),
        dimstyle=DIM_STYLE, dxfattribs=attribs,
    )
    across.render()
    deep = msp.add_linear_dim(
        base=(u0 - offset, v0, z), p1=(u0, v0, z), p2=(u0, v1, z), angle=90.0,
        location=at(((depth_box[0] + depth_box[2]) / 2.0, (depth_box[1] + depth_box[3]) / 2.0)),
        dimstyle=DIM_STYLE, dxfattribs=attribs,
    )
    deep.render()
