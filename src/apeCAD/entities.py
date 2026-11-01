"""Kernel-free draft entities. Identifiers are integers; labels are the handle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from apeCAD.geometry import XYZ

EntityId = int


@dataclass(frozen=True, slots=True)
class Point:
    entity_id: EntityId
    xyz_mm: XYZ
    label: str | None = None


@dataclass(frozen=True, slots=True)
class Line:
    entity_id: EntityId
    start_id: EntityId
    end_id: EntityId
    label: str | None = None


@dataclass(frozen=True, slots=True)
class Polyline:
    entity_id: EntityId
    point_ids: tuple[EntityId, ...]
    closed: bool = False
    label: str | None = None


@dataclass(frozen=True, slots=True)
class Box:
    """Legacy AABB. New AddBox ops expand to Face + Extrude instead."""

    entity_id: EntityId
    origin_xyz_mm: XYZ
    size_xyz_mm: XYZ
    label: str | None = None


@dataclass(frozen=True, slots=True)
class Face:
    """Closed planar loop. The solid primitive starts here (ADR 0008)."""

    entity_id: EntityId
    point_ids: tuple[EntityId, ...]
    label: str | None = None


@dataclass(frozen=True, slots=True)
class Solid:
    """Intent solid: a profile pulled by a signed distance. Cap is the far end."""

    entity_id: EntityId
    face_id: EntityId
    distance_mm: float
    direction_xyz: XYZ
    cap_id: EntityId | None = None
    wall_ids: tuple[EntityId, ...] = ()
    label: str | None = None


@dataclass(frozen=True, slots=True)
class Circle:
    """Planar circle: centre point and radius in mm."""

    entity_id: EntityId
    center_id: EntityId
    radius_mm: float
    label: str | None = None


@dataclass(frozen=True, slots=True)
class Arc:
    """Circular arc through three points (start, a point on the arc, end)."""

    entity_id: EntityId
    start_id: EntityId
    mid_id: EntityId
    end_id: EntityId
    label: str | None = None


@dataclass(frozen=True, slots=True)
class Ellipse:
    """Axis-aligned ellipse on XY: centre point and two radii in mm."""

    entity_id: EntityId
    center_id: EntityId
    radius_x_mm: float
    radius_y_mm: float
    label: str | None = None


@dataclass(frozen=True, slots=True)
class Bezier:
    """Cubic Bézier: four control point ids."""

    entity_id: EntityId
    point_ids: tuple[EntityId, ...]
    label: str | None = None


FaceRole = Literal["solid"]
"""A concrete face's role. Only "solid" in v1; "void" is reserved (ADR 0024 P3)."""
HoopHooks = Literal["135"]
CrosstieHooks = Literal["135-135", "135-90"]
"""Crosstie hook pairs. "90-90" is refused (specs/section-draft.md)."""


@dataclass(frozen=True, slots=True)
class ConcreteFace:
    """Section mode: a concrete outline, a simple CCW ring on z = 0 (ADR 0024).

    `material` is a name, not a law; apeConcrete owns the mechanics.
    """

    entity_id: EntityId
    point_ids: tuple[EntityId, ...]
    material: str
    role: FaceRole = "solid"
    label: str | None = None


@dataclass(frozen=True, slots=True)
class Bar:
    """Section mode: a longitudinal bar at its own Point (ADR 0024 decision 5)."""

    entity_id: EntityId
    point_id: EntityId
    designation: str
    diameter_mm: float
    label: str | None = None
    material: str | None = None
    """The bar steel's name (ADR 0039 decision 6); None means the consumer's default."""


@dataclass(frozen=True, slots=True)
class Hoop:
    """Section mode: a closed hoop, the strict CCW convex hull of its bars (ADR 0024 P2)."""

    entity_id: EntityId
    bar_ids: tuple[EntityId, ...]
    designation: str
    diameter_mm: float
    spacing_mm: float
    hooks: HoopHooks = "135"
    label: str | None = None


@dataclass(frozen=True, slots=True)
class Crosstie:
    """Section mode: a crosstie between two distinct bars."""

    entity_id: EntityId
    bar_a_id: EntityId
    bar_b_id: EntityId
    designation: str
    diameter_mm: float
    spacing_mm: float
    hooks: CrosstieHooks = "135-135"
    label: str | None = None


@dataclass(frozen=True, slots=True)
class LegSteel:
    """A wall leg's horizontal web steel (ADR 0024 P4): a designation, not a diameter."""

    designation: str
    spacing_mm: float
    curtains: int


@dataclass(frozen=True, slots=True)
class WallLeg:
    """Section mode: a rectangular wall leg on its axis, inside a concrete face (P4).

    `start_id` and `end_id` are axis points. `horizontal` is the leg's web steel, or None
    when not yet given; apeConcrete's reader refuses a leg without it, apeCAD only warns.
    """

    entity_id: EntityId
    start_id: EntityId
    end_id: EntityId
    thickness_mm: float
    face_id: EntityId
    horizontal: LegSteel | None = None
    label: str | None = None


@dataclass(frozen=True, slots=True)
class CoverGuide:
    """Section mode: a face's cover intent, one per face (ADR 0024).

    Clear cover is measured to the outside of the transverse bar (ADR 0024 open q6, the
    proposed default); bar centres sit `cover + tie + bar / 2` inside the outline.
    """

    entity_id: EntityId
    face_id: EntityId
    cover_mm: float
    tie_diameter_mm: float
    bar_diameter_mm: float
    label: str | None = None


SectionRole = Literal["concrete", "steel", "void"]
"""A v2 section face's role (ADR 0039 decision 2). Where faces overlap, void > steel >
concrete decides (decision 3), never the drawing order."""
CircularTieKind = Literal["spiral", "hoop"]


@dataclass(frozen=True, slots=True)
class RingBoundary:
    """A face boundary that is a simple ring of points on z = 0.

    Stored counter-clockwise as a face's outer boundary and clockwise as a hole
    (specs/section-draft-v2.md "Ring orientation"); the op that adds it normalises it.
    """

    point_ids: tuple[EntityId, ...]


@dataclass(frozen=True, slots=True)
class CircleBoundary:
    """An exact circle on z = 0: a centre point and a radius. Never tessellated here."""

    center_id: EntityId
    radius_mm: float


FaceBoundary = RingBoundary | CircleBoundary


@dataclass(frozen=True, slots=True)
class SteelShape:
    """Where a steel face's ring came from (ADR 0039 decision 4). apeCAD never resolves it.

    The host resolved `designation` in `catalog`, placed it at `anchor_mm` turned by
    `rotation_deg` (CCW), and passed the ring. A translate or rotate carries the anchor and
    the turn with the ring; a mirror is refused (ADR 0039 Errata 7).
    """

    catalog: str
    designation: str
    anchor_mm: tuple[float, float]
    rotation_deg: float


@dataclass(frozen=True, slots=True)
class SectionFace:
    """Section mode v2 (ADR 0039 decision 2): a concrete, steel or void face with holes.

    `material` is a name, None only on a void (Errata 6). A hole removes material from this
    face only; it is identified by `(entity_id, index in holes)`. `shape` is set only on a
    steel face drawn by `AddSteelShape`.
    """

    entity_id: EntityId
    role: SectionRole
    boundary: FaceBoundary
    material: str | None
    holes: tuple[FaceBoundary, ...] = ()
    shape: SteelShape | None = None
    label: str | None = None


@dataclass(frozen=True, slots=True)
class CircularTie:
    """Section mode v2 (ADR 0039 decision 5): a spiral or a circular hoop.

    `center_id` is a point on z = 0 and `centerline_radius_mm` the radius of the tie's
    centreline. `pitch_mm` is a spiral's pitch, or a hoop's spacing. Which bars it encloses
    is geometry; the consumer derives it.
    """

    entity_id: EntityId
    kind: CircularTieKind
    center_id: EntityId
    centerline_radius_mm: float
    designation: str
    diameter_mm: float
    pitch_mm: float
    label: str | None = None


def boundary_point_ids(boundary: FaceBoundary) -> tuple[EntityId, ...]:
    if isinstance(boundary, RingBoundary):
        return boundary.point_ids
    return (boundary.center_id,)


def section_face_point_ids(face: SectionFace) -> tuple[EntityId, ...]:
    """Every point a v2 face stands on: its boundary's, then each hole's, without repeats."""
    ids = [*boundary_point_ids(face.boundary)]
    for hole in face.holes:
        ids.extend(boundary_point_ids(hole))
    return tuple(dict.fromkeys(ids))


SectionEntity = (
    ConcreteFace | Bar | Hoop | Crosstie | WallLeg | CoverGuide | SectionFace | CircularTie
)
"""Section-mode kinds (ADR 0024, and ADR 0039's v2 faces and circular ties)."""

Entity = (
    Point | Line | Polyline | Box | Face | Solid | Circle | Arc | Ellipse | Bezier | SectionEntity
)
