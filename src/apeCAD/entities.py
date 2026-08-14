"""Kernel-free draft entities. Identifiers are integers; labels are the handle."""

from __future__ import annotations

from dataclasses import dataclass

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
    """Axis-aligned box: origin is the minimum corner, size is extent in mm."""

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
    """Intent solid: a face pulled by a signed distance along a direction."""

    entity_id: EntityId
    face_id: EntityId
    distance_mm: float
    direction_xyz: XYZ
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


Entity = Point | Line | Polyline | Box | Face | Solid | Circle | Arc | Ellipse | Bezier
