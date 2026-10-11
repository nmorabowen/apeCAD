"""Typed operations. The ops log is the document writer (ADR 0006)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from apeCAD.entities import EntityId
from apeCAD.errors import DocumentError
from apeCAD.geometry import XYZ, require_finite

SCHEMA_ID = "apeCAD.document.v0"
UNITS = "mm"


def _optional_label(label: str | None) -> str | None:
    if label is None:
        return None
    stripped = label.strip()
    if stripped == "":
        raise DocumentError("label must be None or a non-empty string")
    return stripped


def _require_name(name: str) -> str:
    stripped = name.strip()
    if stripped == "":
        raise DocumentError("tag name must be a non-empty string")
    return stripped


@dataclass(frozen=True, slots=True)
class PointAt:
    """A vertex given by coordinates (ADR 0030).

    Live, the handler reuses a point within 1 mm or creates one. The committed op records
    a reused point as its plain id and a created one as `PointAt` with `entity_id` set, so
    replay recreates that exact id without searching.
    """

    xyz_mm: XYZ
    entity_id: EntityId | None = None


VertexRef = EntityId | PointAt
"""A creation op's vertex: an existing point id, or coordinates (ADR 0030)."""


@dataclass(frozen=True, slots=True)
class AddPoint:
    x_mm: float
    y_mm: float
    z_mm: float
    label: str | None = None
    entity_id: EntityId | None = None

    def __post_init__(self) -> None:
        require_finite("x_mm", self.x_mm)
        require_finite("y_mm", self.y_mm)
        require_finite("z_mm", self.z_mm)
        object.__setattr__(self, "label", _optional_label(self.label))


@dataclass(frozen=True, slots=True)
class AddLine:
    start_id: VertexRef
    end_id: VertexRef
    label: str | None = None
    entity_id: EntityId | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _optional_label(self.label))


@dataclass(frozen=True, slots=True)
class AddPolyline:
    point_ids: tuple[VertexRef, ...]
    closed: bool = False
    label: str | None = None
    entity_id: EntityId | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _optional_label(self.label))
        if len(self.point_ids) < 2:
            raise DocumentError("polyline needs at least two point ids")


@dataclass(frozen=True, slots=True)
class AddBox:
    """AABB sugar: replay creates four points, a Face, and an Extrude Solid."""

    origin_xyz_mm: XYZ
    size_xyz_mm: XYZ
    label: str | None = None
    entity_id: EntityId | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _optional_label(self.label))
        dx = self.size_xyz_mm.x_mm
        dy = self.size_xyz_mm.y_mm
        dz = self.size_xyz_mm.z_mm
        if dx <= 0.0 or dy <= 0.0 or dz <= 0.0:
            raise DocumentError(
                "box size_xyz_mm components must be positive millimetres, "
                f"got {self.size_xyz_mm.to_tuple()!r}"
            )


@dataclass(frozen=True, slots=True)
class AddFace:
    point_ids: tuple[VertexRef, ...]
    label: str | None = None
    entity_id: EntityId | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _optional_label(self.label))
        if len(self.point_ids) < 3:
            raise DocumentError("face needs at least three point ids")
        if len(set(self.point_ids)) != len(self.point_ids):
            raise DocumentError("face point ids must be unique")


@dataclass(frozen=True, slots=True)
class Extrude:
    """Extrude a profile. Given a `ring` instead, it first makes the face (ADR 0030): one op
    for the box tool. The committed op then records the created face as `face_id`."""

    face_id: EntityId | None
    distance_mm: float
    direction_xyz: XYZ = XYZ(0.0, 0.0, 1.0)
    label: str | None = None
    entity_id: EntityId | None = None
    ring: tuple[VertexRef, ...] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _optional_label(self.label))
        if self.ring is None and self.face_id is None:
            raise DocumentError("extrude needs a face_id or a ring")
        if self.ring is not None and len(self.ring) < 3:
            raise DocumentError("extrude ring needs at least three vertices")
        require_finite("distance_mm", self.distance_mm)
        if self.distance_mm == 0.0:
            raise DocumentError("extrude distance_mm cannot be zero")
        if math.hypot(*self.direction_xyz.to_tuple()) == 0.0:
            raise DocumentError("extrude direction cannot be a zero vector")


@dataclass(frozen=True, slots=True)
class AddCircle:
    center_id: VertexRef
    radius_mm: float
    label: str | None = None
    entity_id: EntityId | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _optional_label(self.label))
        require_finite("radius_mm", self.radius_mm)
        if self.radius_mm <= 0.0:
            raise DocumentError("circle radius_mm must be positive")


@dataclass(frozen=True, slots=True)
class AddArc:
    start_id: VertexRef
    mid_id: VertexRef
    end_id: VertexRef
    label: str | None = None
    entity_id: EntityId | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _optional_label(self.label))
        ids = (self.start_id, self.mid_id, self.end_id)
        if len(set(ids)) != 3:
            raise DocumentError("arc start, mid, and end must be three distinct points")


@dataclass(frozen=True, slots=True)
class AddEllipse:
    center_id: VertexRef
    radius_x_mm: float
    radius_y_mm: float
    label: str | None = None
    entity_id: EntityId | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _optional_label(self.label))
        require_finite("radius_x_mm", self.radius_x_mm)
        require_finite("radius_y_mm", self.radius_y_mm)
        if self.radius_x_mm <= 0.0 or self.radius_y_mm <= 0.0:
            raise DocumentError("ellipse radii must be positive millimetres")


@dataclass(frozen=True, slots=True)
class AddBezier:
    point_ids: tuple[VertexRef, ...]
    label: str | None = None
    entity_id: EntityId | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _optional_label(self.label))
        if len(self.point_ids) != 4:
            raise DocumentError("cubic Bézier needs exactly four control point ids")
        if len(set(self.point_ids)) != 4:
            raise DocumentError("Bézier control point ids must be unique")


@dataclass(frozen=True, slots=True)
class AddLineChain:
    """One line-tool gesture (ADR 0030): a Line per consecutive pair of vertices.

    `label` names the first line. The committed op records the lines it made in `line_ids`.
    """

    point_ids: tuple[VertexRef, ...]
    label: str | None = None
    line_ids: tuple[EntityId, ...] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _optional_label(self.label))
        if len(self.point_ids) < 2:
            raise DocumentError("line chain needs at least two vertices")


@dataclass(frozen=True, slots=True)
class Translate:
    entity_ids: tuple[EntityId, ...]
    dx_mm: float
    dy_mm: float
    dz_mm: float = 0.0

    def __post_init__(self) -> None:
        require_finite("dx_mm", self.dx_mm)
        require_finite("dy_mm", self.dy_mm)
        require_finite("dz_mm", self.dz_mm)
        if len(self.entity_ids) == 0:
            raise DocumentError("translate needs at least one entity id")


@dataclass(frozen=True, slots=True)
class InsertNode:
    target_id: EntityId
    x_mm: float
    y_mm: float
    z_mm: float = 0.0
    entity_id: EntityId | None = None
    new_line_id: EntityId | None = None

    def __post_init__(self) -> None:
        require_finite("x_mm", self.x_mm)
        require_finite("y_mm", self.y_mm)
        require_finite("z_mm", self.z_mm)


@dataclass(frozen=True, slots=True)
class TrimLine:
    line_id: EntityId
    keep_id: EntityId
    x_mm: float
    y_mm: float
    z_mm: float = 0.0
    entity_id: EntityId | None = None

    def __post_init__(self) -> None:
        require_finite("x_mm", self.x_mm)
        require_finite("y_mm", self.y_mm)
        require_finite("z_mm", self.z_mm)


@dataclass(frozen=True, slots=True)
class BreakCrossing:
    line_a_id: EntityId
    line_b_id: EntityId
    entity_id: EntityId | None = None
    new_line_a_id: EntityId | None = None
    new_line_b_id: EntityId | None = None

    def __post_init__(self) -> None:
        if self.line_a_id == self.line_b_id:
            raise DocumentError("break needs two different lines")


@dataclass(frozen=True, slots=True)
class AddFaceFromLines:
    line_ids: tuple[EntityId, ...]
    label: str | None = None
    entity_id: EntityId | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _optional_label(self.label))
        if len(self.line_ids) < 3:
            raise DocumentError("face from lines needs at least three lines")
        if len(set(self.line_ids)) != len(self.line_ids):
            raise DocumentError("face from lines cannot reuse a line")


@dataclass(frozen=True, slots=True)
class JoinPolyline:
    entity_ids: tuple[EntityId, ...]
    label: str | None = None
    entity_id: EntityId | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _optional_label(self.label))
        if len(self.entity_ids) < 2:
            raise DocumentError("join needs at least two lines or polylines")
        if len(set(self.entity_ids)) != len(self.entity_ids):
            raise DocumentError("join cannot reuse an entity")


@dataclass(frozen=True, slots=True)
class Rotate:
    entity_ids: tuple[EntityId, ...]
    origin_x_mm: float
    origin_y_mm: float
    angle_deg: float

    def __post_init__(self) -> None:
        require_finite("origin_x_mm", self.origin_x_mm)
        require_finite("origin_y_mm", self.origin_y_mm)
        require_finite("angle_deg", self.angle_deg)
        if len(self.entity_ids) == 0:
            raise DocumentError("rotate needs at least one entity id")


@dataclass(frozen=True, slots=True)
class Mirror:
    entity_ids: tuple[EntityId, ...]
    ax_mm: float
    ay_mm: float
    bx_mm: float
    by_mm: float

    def __post_init__(self) -> None:
        require_finite("ax_mm", self.ax_mm)
        require_finite("ay_mm", self.ay_mm)
        require_finite("bx_mm", self.bx_mm)
        require_finite("by_mm", self.by_mm)
        if len(self.entity_ids) == 0:
            raise DocumentError("mirror needs at least one entity id")
        if self.ax_mm == self.bx_mm and self.ay_mm == self.by_mm:
            raise DocumentError("mirror axis needs two distinct points")


@dataclass(frozen=True, slots=True)
class ChamferCorner:
    target_id: EntityId
    vertex_id: EntityId
    distance_mm: float
    entity_id: EntityId | None = None
    start_id: EntityId | None = None
    end_id: EntityId | None = None

    def __post_init__(self) -> None:
        require_finite("distance_mm", self.distance_mm)
        if self.distance_mm <= 0.0:
            raise DocumentError("chamfer distance_mm must be positive")


@dataclass(frozen=True, slots=True)
class FilletCorner:
    target_id: EntityId
    vertex_id: EntityId
    radius_mm: float
    entity_id: EntityId | None = None
    start_id: EntityId | None = None
    mid_id: EntityId | None = None
    end_id: EntityId | None = None

    def __post_init__(self) -> None:
        require_finite("radius_mm", self.radius_mm)
        if self.radius_mm <= 0.0:
            raise DocumentError("fillet radius_mm must be positive")


@dataclass(frozen=True, slots=True)
class Sew:
    entity_ids: tuple[EntityId, ...]
    tolerance_mm: float = 1.0

    def __post_init__(self) -> None:
        require_finite("tolerance_mm", self.tolerance_mm)
        if self.tolerance_mm <= 0.0:
            raise DocumentError("sew tolerance_mm must be positive")
        if len(self.entity_ids) == 0:
            raise DocumentError("sew needs at least one entity id")


@dataclass(frozen=True, slots=True)
class Simplify:
    entity_ids: tuple[EntityId, ...]

    def __post_init__(self) -> None:
        if len(self.entity_ids) == 0:
            raise DocumentError("simplify needs at least one entity id")


@dataclass(frozen=True, slots=True)
class ArrayLinear:
    entity_ids: tuple[EntityId, ...]
    dx_mm: float
    dy_mm: float
    dz_mm: float = 0.0
    copies: int = 1

    def __post_init__(self) -> None:
        require_finite("dx_mm", self.dx_mm)
        require_finite("dy_mm", self.dy_mm)
        require_finite("dz_mm", self.dz_mm)
        if self.copies < 1:
            raise DocumentError("linear array needs at least one copy")
        if len(self.entity_ids) == 0:
            raise DocumentError("linear array needs at least one entity id")


@dataclass(frozen=True, slots=True)
class ArrayPolar:
    entity_ids: tuple[EntityId, ...]
    origin_x_mm: float
    origin_y_mm: float
    count: int
    angle_deg: float = 360.0

    def __post_init__(self) -> None:
        require_finite("origin_x_mm", self.origin_x_mm)
        require_finite("origin_y_mm", self.origin_y_mm)
        require_finite("angle_deg", self.angle_deg)
        if self.count < 2:
            raise DocumentError("polar array needs a count of at least 2")
        if len(self.entity_ids) == 0:
            raise DocumentError("polar array needs at least one entity id")


@dataclass(frozen=True, slots=True)
class Delete:
    entity_ids: tuple[EntityId, ...]

    def __post_init__(self) -> None:
        if len(self.entity_ids) == 0:
            raise DocumentError("delete needs at least one entity id")


@dataclass(frozen=True, slots=True)
class Tag:
    name: str
    entity_ids: tuple[EntityId, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _require_name(self.name))
        if len(self.entity_ids) == 0:
            raise DocumentError(f"tag {self.name!r} needs at least one entity id")


@dataclass(frozen=True, slots=True)
class SetLabel:
    """Rename (or clear) the unique label on one entity."""

    entity_id: EntityId
    label: str | None = None

    def __post_init__(self) -> None:
        raw = self.label
        if raw is None or raw.strip() == "":
            object.__setattr__(self, "label", None)
        else:
            object.__setattr__(self, "label", _optional_label(raw))


Op = (
    AddPoint
    | AddLine
    | AddLineChain
    | AddPolyline
    | AddBox
    | AddFace
    | Extrude
    | AddCircle
    | AddArc
    | AddEllipse
    | AddBezier
    | Translate
    | InsertNode
    | TrimLine
    | BreakCrossing
    | AddFaceFromLines
    | JoinPolyline
    | Rotate
    | Mirror
    | ChamferCorner
    | FilletCorner
    | Sew
    | Simplify
    | ArrayLinear
    | ArrayPolar
    | Delete
    | Tag
    | SetLabel
)
