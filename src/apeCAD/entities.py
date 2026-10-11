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


SectionEntity = ConcreteFace | Bar | Hoop | Crosstie
"""Section-mode kinds (ADR 0024). C2 adds WallLeg and CoverGuide."""

Entity = (
    Point | Line | Polyline | Box | Face | Solid | Circle | Arc | Ellipse | Bezier | SectionEntity
)
