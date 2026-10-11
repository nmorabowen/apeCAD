"""Catalog entries for the section-mode ops (ADR 0024). `entries.CATALOG` merges them."""

from __future__ import annotations

from apeCAD.catalog.spec import ENTITY_IDS, LABEL, OUTPUT_ID, VERTICES, OpSpec, entry
from apeCAD.ops import (
    AddBar,
    AddConcreteFace,
    AddCrosstie,
    AddHoop,
    SetBarSize,
    SetMaterial,
    SetTransverse,
)
from apeCAD.section.designations import DESIGNATIONS

_DESIGNATION = (
    f"Bar designation from the closed vocabulary: {', '.join(DESIGNATIONS)}. The diameter "
    "follows from it."
)
_SPACING = "Spacing along the member, mm; positive."

SECTION_ENTRIES: tuple[OpSpec, ...] = (
    entry(
        AddConcreteFace,
        "Add a solid concrete outline on z = 0; the ring is stored counter-clockwise.",
        "entity",
        {
            "point_ids": VERTICES + " At least 3, all at z = 0, forming a simple ring.",
            "material": "Concrete material name, e.g. \"H30\"; a name, not a law.",
            "label": LABEL,
            "entity_id": OUTPUT_ID,
        },
        {
            "point_ids": [
                {"xyz": [0, 0, 0]},
                {"xyz": [3000, 0, 0]},
                {"xyz": [3000, 300, 0]},
                {"xyz": [0, 300, 0]},
            ],
            "material": "H30",
            "label": "wall-W1",
        },
        outputs=("entity_id",),
    ),
    entry(
        AddBar,
        "Add a longitudinal bar at (x, y) on z = 0, with a fresh point of its own.",
        "entity",
        {
            "x_mm": "Bar centre x, mm.",
            "y_mm": "Bar centre y, mm.",
            "designation": _DESIGNATION,
            "label": LABEL,
            "entity_id": OUTPUT_ID,
            "point_id": "Output: the id of the bar's own point. Do not send it.",
        },
        {"x_mm": 60, "y_mm": 60, "designation": "Ø16"},
        outputs=("entity_id", "point_id"),
    ),
    entry(
        AddHoop,
        "Add a hoop around bars; it keeps their strict CCW convex hull, in any order.",
        "entity",
        {
            "bar_ids": "Ids of the bars to enclose; the hull needs 3 non-collinear bars.",
            "designation": _DESIGNATION,
            "spacing_mm": _SPACING,
            "hooks": "Hook intent; only \"135\".",
            "label": LABEL,
            "entity_id": OUTPUT_ID,
        },
        {"bar_ids": [2, 4, 6, 8], "designation": "Ø10", "spacing_mm": 100},
        outputs=("entity_id",),
    ),
    entry(
        AddCrosstie,
        "Add a crosstie between two distinct bars.",
        "entity",
        {
            "bar_a_id": "The first bar.",
            "bar_b_id": "The second bar; not the first.",
            "designation": _DESIGNATION,
            "spacing_mm": _SPACING,
            "hooks": "\"135-135\" or \"135-90\"; \"90-90\" is refused.",
            "label": LABEL,
            "entity_id": OUTPUT_ID,
        },
        {"bar_a_id": 2, "bar_b_id": 4, "designation": "Ø10", "spacing_mm": 100},
        outputs=("entity_id",),
    ),
    entry(
        SetBarSize,
        "Change the designation (and so the diameter) of bars.",
        "none",
        {"entity_ids": "Ids of the bars to resize.", "designation": _DESIGNATION},
        {"entity_ids": [2, 4], "designation": "Ø20"},
    ),
    entry(
        SetMaterial,
        "Set the material name of concrete faces.",
        "none",
        {"entity_ids": "Ids of the concrete faces.", "material": "Concrete material name."},
        {"entity_ids": [5], "material": "H35"},
    ),
    entry(
        SetTransverse,
        "Change the size, spacing or hooks of hoops and crossties; null keeps a value.",
        "none",
        {
            "entity_ids": ENTITY_IDS + " Hoops and crossties only.",
            "designation": _DESIGNATION + " Null keeps it.",
            "spacing_mm": _SPACING + " Null keeps it.",
            "hooks": "\"135\" for hoops; \"135-135\" or \"135-90\" for crossties. Null keeps it.",
        },
        {"entity_ids": [9], "spacing_mm": 150},
    ),
)
