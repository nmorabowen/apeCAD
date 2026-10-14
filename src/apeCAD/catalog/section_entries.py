"""Catalog entries for the section-mode ops (ADR 0024). `entries.CATALOG` merges them."""

from __future__ import annotations

from apeCAD.catalog.spec import ENTITY_IDS, LABEL, OUTPUT_ID, VERTEX, VERTICES, OpSpec, entry
from apeCAD.ops import (
    AddBar,
    AddConcreteFace,
    AddCrosstie,
    AddHoop,
    AddSectionOutline,
    AddWallChain,
    AddWallLeg,
    SetBarSize,
    SetCover,
    SetLegReinforcement,
    SetMaterial,
    SetTransverse,
)
from apeCAD.section.designations import DESIGNATIONS

_DESIGNATION = (
    f"Bar designation from the closed vocabulary: {', '.join(DESIGNATIONS)}. The diameter "
    "follows from it."
)
_SPACING = "Spacing along the member, mm; positive."
_HORIZONTAL = (
    "The leg's horizontal web steel {designation, spacing_mm, curtains}, or null for none "
    "yet; curtains is a count of 1 or more. A leg without it is a lint warning (ADR 0024 P4)."
)
_STEEL_EXAMPLE = {"designation": "Ø10", "spacing_mm": 200, "curtains": 2}

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
    entry(
        AddSectionOutline,
        "Draw a section outline: one solid concrete face on z = 0, stored counter-clockwise.",
        "entity",
        {
            "point_ids": VERTICES + " At least 3, all at z = 0, forming a simple ring; a "
            "bow-tie is refused. Every outline is solid (no role, ADR 0024 P3).",
            "material": "Concrete material name, e.g. \"H30\"; a name, not a law.",
            "label": LABEL,
            "entity_id": OUTPUT_ID,
        },
        {
            "point_ids": [
                {"xyz": [0, 0, 0]},
                {"xyz": [2000, 0, 0]},
                {"xyz": [2000, 300, 0]},
                {"xyz": [0, 300, 0]},
            ],
            "material": "H30",
            "label": "pier-P1",
        },
        outputs=("entity_id",),
    ),
    entry(
        AddWallChain,
        "Draw a wall along its axis: one outline face plus one leg per axis segment.",
        "entity",
        {
            "point_ids": VERTICES + " The open wall axis, at least 2 points, all at z = 0.",
            "thickness_mm": "Wall thickness in mm: one value for every segment, or one per "
            "segment; positive.",
            "material": "Concrete material name, e.g. \"H30\".",
            "horizontal": _HORIZONTAL + " It goes on every leg.",
            "label": LABEL + " It names the face.",
            "entity_id": OUTPUT_ID + " The outline face.",
            "ring": "Output: the outline vertices the handler resolved. Do not send it.",
            "leg_ids": "Output: the legs, one per axis segment. Do not send it.",
        },
        {
            "point_ids": [{"xyz": [0, 0, 0]}, {"xyz": [3000, 0, 0]}, {"xyz": [3000, 2000, 0]}],
            "thickness_mm": [250],
            "material": "H30",
            "horizontal": _STEEL_EXAMPLE,
            "label": "wall-L1",
        },
        outputs=("entity_id", "ring", "leg_ids"),
    ),
    entry(
        AddWallLeg,
        "Add a wall leg on an existing concrete face, e.g. each of the three legs of a T.",
        "entity",
        {
            "start_id": VERTEX + " One end of the leg axis, at z = 0.",
            "end_id": VERTEX + " The other end; not the start.",
            "thickness_mm": "Leg thickness, mm; positive.",
            "face_id": "The concrete face the leg belongs to.",
            "horizontal": _HORIZONTAL,
            "label": LABEL,
            "entity_id": OUTPUT_ID,
        },
        {
            "start_id": {"xyz": [0, 150, 0]},
            "end_id": {"xyz": [2000, 150, 0]},
            "thickness_mm": 300,
            "face_id": 5,
            "horizontal": _STEEL_EXAMPLE,
        },
        outputs=("entity_id",),
    ),
    entry(
        SetLegReinforcement,
        "Set a wall leg's horizontal web steel.",
        "none",
        {
            "leg_id": "The wall leg.",
            "designation": _DESIGNATION,
            "spacing_mm": _SPACING,
            "curtains": "Number of curtains (layers) of horizontal steel; 1 or more.",
        },
        {"leg_id": 8, "designation": "Ø12", "spacing_mm": 150, "curtains": 2},
    ),
    entry(
        SetCover,
        "Set a concrete face's cover guide; it creates the guide or changes the face's one.",
        "entity",
        {
            "face_id": "The concrete face.",
            "cover_mm": "Clear cover to the outside of the transverse bar, mm; positive.",
            "tie_diameter_mm": "Transverse bar diameter, mm; 0 for a wall without hoops.",
            "bar_diameter_mm": "Longitudinal bar diameter, mm; positive. Bar centres sit "
            "cover + tie + bar / 2 inside the outline.",
            "entity_id": OUTPUT_ID + " The face's cover guide.",
        },
        {"face_id": 5, "cover_mm": 40, "tie_diameter_mm": 10, "bar_diameter_mm": 20},
        outputs=("entity_id",),
    ),
)
