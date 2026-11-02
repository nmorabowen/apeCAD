"""Catalog entries for the section-template ops (ADR 0040). `entries.CATALOG` merges them.

An agent lists the templates, fills in the params and sends one op; it never computes a
bar position (ADR 0040 decision 6). The field is `template_params`, because the request
envelope already uses `params` (ADR 0040 Errata 9). Its schema is an object: each template
checks its own params when it expands, and refuses a bad one by name with
`INVALID_ARGUMENT` (`TemplateParamError`). Stage C3-S3 lists each template's params.
"""

from __future__ import annotations

from apeCAD.catalog.spec import LABEL, OUTPUT_ID, OpSpec, entry
from apeCAD.ops import AddSectionTemplate, EditSectionTemplate, ExplodeSectionTemplate
from apeCAD.section.templates import TEMPLATES

_TEMPLATE = f"Template name: one of {', '.join(TEMPLATES)}."
_PARAMS = (
    "The template's parameters, an object: lengths in mm, bars as designations from the "
    "closed vocabulary, `material` (required) and `bar_material` (optional) as names. A "
    "missing, unknown or out-of-range one is refused by name (INVALID_ARGUMENT)."
)
_VERSION = (
    "The template version to expand, a whole number; null means the latest. The committed "
    "op records the version it ran, so an old log replays to the same drawing."
)
_CHILDREN = (
    "Output: the ids of every entity the template drew, in allocation order. Do not send it."
)
_TEMPLATE_ID = "Id of the section template entity."
_EXAMPLE_PARAMS: dict[str, object] = {
    "material": "C30", "b": 400, "h": 600, "center_mm": [200, 300], "cover": 40, "nx": 3,
    "ny": 3, "bar": "Ø20", "tie": "Ø10", "tie_spacing": 150, "crossties": "all",
}  # fmt: skip

TEMPLATE_ENTRIES: tuple[OpSpec, ...] = (
    entry(
        AddSectionTemplate,
        "Draw a parametric section template (a column, a box, a T beam) from its params; "
        "its children are locked until it is edited, deleted or exploded.",
        "entity",
        {
            "template": _TEMPLATE,
            "template_params": _PARAMS,
            "template_version": _VERSION,
            "label": LABEL,
            "entity_id": OUTPUT_ID,
            "child_ids": _CHILDREN,
        },
        {"template": "rect_column", "template_params": _EXAMPLE_PARAMS},
        outputs=("entity_id", "child_ids"),
    ),
    entry(
        EditSectionTemplate,
        "Replace a section template's params whole and draw it again with fresh child ids; "
        "edit center_mm to move it.",
        "entities",
        {
            "template_id": _TEMPLATE_ID,
            "template_params": _PARAMS + " They replace the old params whole.",
            "template_version": _VERSION.replace("the latest", "keep the template's version"),
            "child_ids": _CHILDREN,
        },
        {"template_id": 1, "template_params": {**_EXAMPLE_PARAMS, "b": 450}},
        outputs=("child_ids",),
    ),
    entry(
        ExplodeSectionTemplate,
        "Explode a section template: drop it and keep its children as a freehand drawing. "
        "There is no re-implode.",
        "none",
        {"template_id": _TEMPLATE_ID},
        {"template_id": 1},
    ),
)
