"""The `templates` key of `list_ops` and `GET /api/ops` (ADR 0040 decision 6, stage C3-S3).

One row per section template: its summary, its versions, the JSON Schema of its latest
version's params (derived from the template's parameter dataclass, as an op's schema is from
its op dataclass) and an example that expands. An agent reads a row, fills in the params and
sends `AddSectionTemplate`; it never computes a bar position.

The schema is a guide for the caller. The expansion stays the check: it refuses a bad param
by name with `INVALID_ARGUMENT` (`TemplateParamError`). `tests/test_section_template_projection.py`
holds each row to its expansion, param by param.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from apeCAD.catalog.schema import params_schema
from apeCAD.section.designations import DESIGNATIONS
from apeCAD.section.templates import (
    TEMPLATES,
    circular_column,
    latest_version,
    polygon_column,
    rect_column,
    rect_hollow,
    t_beam,
)

Json = dict[str, object]

_BARS = f"one of {', '.join(DESIGNATIONS)}"
_MATERIAL = "Name of the concrete face's material. A name only: the host binds it."
_BAR_MATERIAL = "Name of the bar steel; null leaves the bars without one (the consumer's default)."
_CENTER = "Centre of the gross bounding box, [x, y] in mm."
_COVER = "Clear cover to the tie in mm; a bar centre sits cover + tie + bar / 2 from the face."
_ROW = "A row of bars: n, at least 2, and bar, "
_TIE = f"Tie bar, {_BARS}."
_TIE_SPACING = "Spacing of the ties along the member, in mm."
_SPACING_MAX = "Largest spacing of the bars along an edge, in mm."


@dataclass(frozen=True)
class _Row:
    template: str
    summary: str
    params: type
    fields: Mapping[str, str]
    example: Mapping[str, object]


_ROWS = (
    _Row(
        rect_column.TEMPLATE,
        "A rectangular tied column: the ring, its cover guide, bars along each face, one "
        "corner hoop and 135-135 crossties.",
        rect_column.RectColumnParams,
        {
            "material": _MATERIAL,
            "bar_material": _BAR_MATERIAL,
            "center_mm": _CENTER,
            "b": "Width along x, in mm.",
            "h": "Depth along y, in mm.",
            "cover": _COVER,
            "nx": "Bars along each horizontal face, corners included; at least 2.",
            "ny": "Bars along each vertical face, corners included; at least 2.",
            "bar": f"Face bar, {_BARS}.",
            "corner_bar": f"Corner bar, {_BARS}; null uses bar.",
            "tie": _TIE,
            "tie_spacing": _TIE_SPACING,
            "crossties": "Crossties between facing interior bars: none, all or alternate "
            "(the even indices, counted from the corner).",
        },
        {
            "material": "C30", "b": 400, "h": 600, "center_mm": [200, 300], "cover": 40,
            "nx": 3, "ny": 3, "bar": "Ø20", "tie": "Ø10", "tie_spacing": 150,
            "crossties": "all",
        },
    ),
    _Row(
        polygon_column.TEMPLATE,
        "A strictly convex polygonal tied column: the ring, its cover guide, bars along every "
        "edge of the inset ring and one hull hoop.",
        polygon_column.PolygonColumnParams,
        {
            "material": _MATERIAL,
            "bar_material": _BAR_MATERIAL,
            "ring": "The outline, 3 or more [x, y] vertices in mm; a straight or reflex vertex "
            "is refused. The ring is the placement: edit it to move the column.",
            "cover": _COVER,
            "bar": f"Bar, {_BARS}.",
            "spacing_max": _SPACING_MAX,
            "tie": _TIE,
            "tie_spacing": _TIE_SPACING,
        },
        {
            "material": "C30", "ring": [[0, 0], [600, 0], [600, 300], [0, 500]], "cover": 40,
            "bar": "Ø20", "spacing_max": 150, "tie": "Ø10", "tie_spacing": 150,
        },
    ),
    _Row(
        rect_hollow.TEMPLATE,
        "A rectangular hollow section: the ring with one hole, its cover guide, an outer and "
        "an inner bar ring and two hoops. Version 1 places no crossties.",
        rect_hollow.RectHollowParams,
        {
            "material": _MATERIAL,
            "bar_material": _BAR_MATERIAL,
            "center_mm": _CENTER,
            "b": "Outer width along x, in mm.",
            "h": "Outer depth along y, in mm.",
            "t_x": "Thickness of the walls that bound the width, in mm.",
            "t_y": "Thickness of the walls that bound the depth, in mm.",
            "cover": _COVER,
            "bar": f"Bar, {_BARS}.",
            "spacing_max": _SPACING_MAX,
            "tie": _TIE,
            "tie_spacing": _TIE_SPACING,
        },
        {
            "material": "C30", "b": 600, "h": 800, "t_x": 150, "t_y": 200, "cover": 40,
            "bar": "Ø16", "spacing_max": 200, "tie": "Ø10", "tie_spacing": 150,
        },
    ),
    _Row(
        t_beam.TEMPLATE,
        "A symmetric T beam: the ring, its cover guide, bottom and top rows in the web, one "
        "stirrup on their hull and optional slab bars. Version 1 is symmetric only.",
        t_beam.TBeamParams,
        {
            "material": _MATERIAL,
            "bar_material": _BAR_MATERIAL,
            "center_mm": _CENTER,
            "bw": "Web width, in mm.",
            "h": "Overall depth, in mm.",
            "bf": "Flange width, in mm; wider than bw.",
            "hf": "Flange depth, in mm; shallower than h.",
            "cover": "Clear cover in mm; a web bar centre sits cover + stirrup + bar / 2 from "
            "the face, a slab bar cover + bar / 2 below the top.",
            "bottom": f"{_ROW}{_BARS}.",
            "top": f"{_ROW}{_BARS}.",
            "slab_bars": f"Bars per overhang, or null: n, at least 1, and bar, {_BARS}.",
            "stirrup": f"Stirrup bar, {_BARS}.",
            "stirrup_spacing": "Spacing of the stirrups along the member, in mm.",
        },
        {
            "material": "C30", "bw": 300, "h": 600, "bf": 800, "hf": 150, "center_mm": [0, 300],
            "cover": 30, "bottom": {"n": 3, "bar": "Ø20"}, "top": {"n": 2, "bar": "Ø16"},
            "slab_bars": {"n": 2, "bar": "Ø12"}, "stirrup": "Ø10", "stirrup_spacing": 150,
        },
    ),
    _Row(
        circular_column.TEMPLATE,
        "A circular column: the exact circle, equal bars evenly on a circle from angle 0 "
        "counter-clockwise, one spiral or circular hoop and its cover guide.",
        circular_column.CircularColumnParams,
        {
            "material": _MATERIAL,
            "bar_material": _BAR_MATERIAL,
            "center_mm": "Centre of the circle, [x, y] in mm.",
            "diameter": "Outer diameter, in mm.",
            "cover": _COVER,
            "n_bars": "Bars on the circle; at least 3.",
            "bar": f"Bar, {_BARS}.",
            "tie_kind": "spiral or hoop; required. Both are circular ties, and differ in kind "
            "alone.",
            "tie": _TIE,
            "pitch": "Pitch of a spiral or spacing of the hoops along the member, in mm; at "
            "least the tie's diameter.",
        },
        {
            "material": "C30", "diameter": 600, "cover": 40, "n_bars": 8, "bar": "Ø20",
            "tie_kind": "spiral", "tie": "Ø10", "pitch": 75,
        },
    ),
)  # fmt: skip


def _schema(row: _Row) -> Json:
    schema = params_schema(row.params, row.fields)
    properties = cast(dict[str, Json], schema["properties"])
    for prop in properties.values():  # a default in the dataclass may be a tuple; JSON has lists
        default = prop.get("default")
        if isinstance(default, tuple):
            prop["default"] = list(cast(tuple[object, ...], default))
    return schema


def list_templates() -> list[Json]:
    """Every template as JSON: `{name, summary, version, versions, params, example}`.

    `version` is the latest, the one an op that names none records; `params` is its schema.
    """
    return [
        {
            "name": row.template,
            "summary": row.summary,
            "version": latest_version(row.template),
            "versions": sorted(TEMPLATES[row.template]),
            "params": _schema(row),
            "example": dict(row.example),
        }
        for row in _ROWS
    ]
