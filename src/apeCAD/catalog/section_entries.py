"""Catalog entries for the section-mode ops (ADR 0024). `entries.CATALOG` merges them."""

from __future__ import annotations

from apeCAD.catalog.spec import ENTITY_IDS, LABEL, OUTPUT_ID, VERTEX, VERTICES, OpSpec, entry
from apeCAD.ops import (
    AddBar,
    AddBarRow,
    AddBarsAlongEdge,
    AddBarsOnCircle,
    AddCircularTie,
    AddConcreteFace,
    AddCrosstie,
    AddFaceHole,
    AddHoop,
    AddSectionFace,
    AddSectionOutline,
    AddSteelShape,
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
_COUNT = "Number of bars, both ends included; 2 or more. Give this or spacing_mm, not both."
_PLACED = "Output: the ids of the bars placed, in order. Do not send it."
_PLACED_POINTS = "Output: the ids of the bars' own points, in order. Do not send it."
_BAR_MATERIAL = (
    "The bar steel's name, e.g. \"A630-420H\", or null for the consumer's default "
    "(ADR 0039 decision 6)."
)
_RING = (
    VERTICES + " A ring of at least 3, all at z = 0, simple. Give this or center_id and "
    "radius_mm, not both."
)
_CENTER = VERTEX + " A circle's centre, at z = 0; null for a ring."
_RADIUS = "A circle's radius, mm; positive. Null for a ring."
_W_RING = [
    {"xyz": [-150, -175, 0]},
    {"xyz": [150, -175, 0]},
    {"xyz": [150, -155, 0]},
    {"xyz": [6, -155, 0]},
    {"xyz": [6, 155, 0]},
    {"xyz": [150, 155, 0]},
    {"xyz": [150, 175, 0]},
    {"xyz": [-150, 175, 0]},
    {"xyz": [-150, 155, 0]},
    {"xyz": [-6, 155, 0]},
    {"xyz": [-6, -155, 0]},
    {"xyz": [-150, -155, 0]},
]

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
            "material": _BAR_MATERIAL,
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
        "Set the material name of faces: v1 concrete faces, v2 concrete and steel faces.",
        "none",
        {
            "entity_ids": "Ids of the faces; a void face is refused (it takes no material).",
            "material": "Material name, e.g. \"H30\" or \"A630-420H\"; a name, not a law.",
        },
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
    entry(
        AddBarRow,
        "Lay a row of bars between two points on z = 0, by count or by spacing (one op).",
        "entities",
        {
            "start_x_mm": "Row start x, mm.",
            "start_y_mm": "Row start y, mm.",
            "end_x_mm": "Row end x, mm.",
            "end_y_mm": "Row end y, mm.",
            "designation": _DESIGNATION,
            "count": _COUNT,
            "spacing_mm": "Bar spacing, mm; positive. As many whole spacings as fit, the "
            "remainder split evenly between the two ends. Give this or count, not both.",
            "bar_ids": _PLACED,
            "bar_point_ids": _PLACED_POINTS,
        },
        {
            "start_x_mm": 60,
            "start_y_mm": -740,
            "end_x_mm": 340,
            "end_y_mm": -740,
            "designation": "Ø16",
            "count": 3,
        },
        outputs=("bar_ids", "bar_point_ids"),
    ),
    entry(
        AddBarsAlongEdge,
        "Lay bars along one edge of a face's bar-centre ring; needs its cover guide.",
        "entities",
        {
            "face_id": "The concrete face; it must have a cover guide (SetCover).",
            "edge_index": "Edge i runs from face vertex i to i + 1 (vertices counter-clockwise, "
            "from 0), inset by cover + tie + bar / 2.",
            "designation": _DESIGNATION,
            "count": _COUNT,
            "spacing_mm": "Largest bar spacing, mm; positive. The edge takes the fewest equal "
            "intervals no longer than it. Give this or count, not both.",
            "bar_ids": _PLACED + " A position within 1 mm of a bar is skipped.",
            "bar_point_ids": _PLACED_POINTS,
        },
        {"face_id": 5, "edge_index": 0, "designation": "Ø16", "spacing_mm": 150},
        outputs=("bar_ids", "bar_point_ids"),
    ),
    entry(
        AddSectionFace,
        "Add a v2 section face: concrete, steel or void, as a ring (stored CCW) or a circle.",
        "entity",
        {
            "role": "\"concrete\", \"steel\" or \"void\". Where faces overlap, void > steel > "
            "concrete decides, never the drawing order (ADR 0039 decision 3).",
            "material": "Material name for a concrete or steel face, e.g. \"H30\"; required "
            "for those roles. Null for a void, which has no material.",
            "point_ids": _RING,
            "center_id": _CENTER,
            "radius_mm": _RADIUS,
            "label": LABEL,
            "entity_id": OUTPUT_ID,
        },
        {
            "role": "concrete",
            "material": "H30",
            "center_id": {"xyz": [0, 0, 0]},
            "radius_mm": 300,
            "label": "column-C1",
        },
        outputs=("entity_id",),
    ),
    entry(
        AddFaceHole,
        "Add a hole to a v2 section face: a ring (stored clockwise) or a circle.",
        "none",
        {
            "face_id": "The v2 section face; it loses material inside the hole, and no other "
            "face does. A v1 concrete face is refused.",
            "point_ids": _RING,
            "center_id": _CENTER,
            "radius_mm": _RADIUS,
            "hole_index": "Output: the hole's 0-based index on the face; a hole is "
            "(face_id, hole_index). Do not send it.",
        },
        {"face_id": 5, "center_id": {"xyz": [0, 0, 0]}, "radius_mm": 290},
        outputs=("hole_index",),
    ),
    entry(
        AddSteelShape,
        "Add a steel face from a catalog shape's ring the host resolved; apeCAD keeps the "
        "provenance only.",
        "entity",
        {
            "point_ids": VERTICES + " The resolved outline, at least 3 at z = 0, simple; "
            "stored CCW. apeCAD never resolves the designation itself.",
            "material": "Steel material name, e.g. \"A992\".",
            "catalog": "The catalog the host resolved the designation in, e.g. \"AISC 16\".",
            "designation": "The shape's designation in that catalog, e.g. \"W14X90\".",
            "anchor_mm": "Where the host placed the shape's origin, [x, y] in mm.",
            "rotation_deg": "The shape's turn about its anchor, degrees CCW. A rotate adds to "
            "it; a mirror of the face is refused.",
            "label": LABEL,
            "entity_id": OUTPUT_ID,
        },
        {
            "point_ids": _W_RING,
            "material": "A992",
            "catalog": "AISC 16",
            "designation": "W14X90",
            "anchor_mm": [0, 0],
        },
        outputs=("entity_id",),
    ),
    entry(
        AddCircularTie,
        "Add a spiral or a circular hoop around a centre on z = 0.",
        "entity",
        {
            "kind": "\"spiral\" or \"hoop\".",
            "center_id": VERTEX + " The tie's centre, at z = 0.",
            "centerline_radius_mm": "Radius of the tie's centreline, mm; positive.",
            "designation": _DESIGNATION,
            "pitch_mm": "A spiral's pitch, or a hoop's spacing along the member, mm; "
            "positive.",
            "label": LABEL,
            "entity_id": OUTPUT_ID,
        },
        {
            "kind": "spiral",
            "center_id": {"xyz": [0, 0, 0]},
            "centerline_radius_mm": 255,
            "designation": "Ø10",
            "pitch_mm": 75,
        },
        outputs=("entity_id",),
    ),
    entry(
        AddBarsOnCircle,
        "Lay bars evenly on a circle of bar centres on z = 0 (one op).",
        "entities",
        {
            "center_x_mm": "Circle centre x, mm.",
            "center_y_mm": "Circle centre y, mm.",
            "radius_mm": "Radius of the bar-centre circle, mm; positive.",
            "count": "Number of bars, 2 or more, spaced evenly round the circle.",
            "designation": _DESIGNATION,
            "start_angle_deg": "Angle of the first bar, degrees CCW from +x.",
            "material": _BAR_MATERIAL,
            "bar_ids": _PLACED,
            "bar_point_ids": _PLACED_POINTS,
        },
        {
            "center_x_mm": 0,
            "center_y_mm": 0,
            "radius_mm": 240,
            "count": 8,
            "designation": "Ø20",
        },
        outputs=("bar_ids", "bar_point_ids"),
    ),
)
