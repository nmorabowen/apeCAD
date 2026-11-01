"""Section-mode v2 ops (ADR 0039): general faces, holes, steel shapes and circular steel.

Split from `ops/section.py` so that file stays under the ADR 0023 line budget; it imports
these and lists them in `SectionOp` and `SECTION_OPS`. A boundary is given either as a ring
(`point_ids`, at least 3 vertices) or as a circle (`center_id` and `radius_mm`), never both.
"""

from __future__ import annotations

from dataclasses import dataclass

from apeCAD.entities import EntityId
from apeCAD.errors import DocumentError
from apeCAD.geometry import require_finite
from apeCAD.ops.base import VertexRef, optional_label
from apeCAD.section.designations import diameter_of

SECTION_ROLES = ("concrete", "steel", "void")
CIRCULAR_TIE_KINDS = ("spiral", "hoop")


def _name(field: str, value: str) -> str:
    stripped = value.strip()
    if stripped == "":
        raise DocumentError(f"{field} must be a non-empty name")
    return stripped


def _positive(field: str, value: float) -> float:
    if not require_finite(field, value) > 0.0:
        raise DocumentError(f"{field} must be positive, got {value!r}")
    return value


def require_role(role: str) -> str:
    if role not in SECTION_ROLES:
        raise DocumentError(f"role must be one of {SECTION_ROLES}, got {role!r}")
    return role


def require_face_material(role: str, material: str | None) -> str | None:
    """A void has no material (ADR 0039 Errata 6); a concrete or steel face names one."""
    if role == "void":
        if material is not None:
            raise DocumentError(f"a void face takes no material, got {material!r}")
        return None
    if material is None:
        raise DocumentError(f"a {role} face needs a material name")
    return _name("material", material)


def require_boundary(
    what: str,
    point_ids: tuple[VertexRef, ...],
    center_id: VertexRef | None,
    radius_mm: float | None,
) -> None:
    """Exactly one boundary: a ring of 3 or more vertices, or a centre and a radius."""
    ring = len(point_ids) > 0
    circle = center_id is not None or radius_mm is not None
    if ring == circle:
        raise DocumentError(
            f"{what} takes exactly one boundary: point_ids (a ring), or center_id and "
            "radius_mm (a circle)"
        )
    if ring and len(point_ids) < 3:
        raise DocumentError(f"{what} ring needs at least 3 vertices, got {len(point_ids)}")
    if circle:
        if center_id is None or radius_mm is None:
            raise DocumentError(f"{what} circle needs both center_id and radius_mm")
        _positive("radius_mm", radius_mm)


@dataclass(frozen=True, slots=True)
class AddSectionFace:
    """A v2 face (ADR 0039 decision 2): concrete, steel or void, ring or exact circle.

    A ring is stored counter-clockwise. Where faces overlap the role decides (void > steel >
    concrete), never the drawing order; holes are added with `AddFaceHole`.
    """

    role: str
    material: str | None = None
    point_ids: tuple[VertexRef, ...] = ()
    center_id: VertexRef | None = None
    radius_mm: float | None = None
    label: str | None = None
    entity_id: EntityId | None = None

    def __post_init__(self) -> None:
        require_role(self.role)
        object.__setattr__(self, "material", require_face_material(self.role, self.material))
        require_boundary("a section face", self.point_ids, self.center_id, self.radius_mm)
        object.__setattr__(self, "label", optional_label(self.label))


@dataclass(frozen=True, slots=True)
class AddFaceHole:
    """A hole in a v2 face: a ring (stored clockwise) or a circle. It cuts that face only.

    A hole outside its face is not refused; it is the `hole-outside-face` lint warning. A
    hole has no entity id: it is `(face_id, hole_index)`, and the committed op records the
    index (0-based, in the order the face's holes were added).
    """

    face_id: EntityId
    point_ids: tuple[VertexRef, ...] = ()
    center_id: VertexRef | None = None
    radius_mm: float | None = None
    hole_index: int | None = None

    def __post_init__(self) -> None:
        require_boundary("a hole", self.point_ids, self.center_id, self.radius_mm)
        if self.hole_index is not None and (
            isinstance(self.hole_index, bool) or self.hole_index < 0
        ):
            raise DocumentError(f"hole_index must be 0 or more, got {self.hole_index!r}")


@dataclass(frozen=True, slots=True)
class AddSteelShape:
    """A steel face whose ring the host resolved (ADR 0039 decision 4).

    apeCAD never resolves `designation`: the host looked it up in `catalog`, placed it at
    `anchor_mm` turned by `rotation_deg` (CCW), and passes the ring here. The face keeps
    that provenance; a move carries it, a mirror is refused.
    """

    point_ids: tuple[VertexRef, ...]
    material: str
    catalog: str
    designation: str
    anchor_mm: tuple[float, float]
    rotation_deg: float = 0.0
    label: str | None = None
    entity_id: EntityId | None = None

    def __post_init__(self) -> None:
        if len(self.point_ids) < 3:
            raise DocumentError(
                f"a steel shape needs its resolved ring, at least 3 vertices, got "
                f"{len(self.point_ids)}"
            )
        object.__setattr__(self, "material", _name("material", self.material))
        object.__setattr__(self, "catalog", _name("catalog", self.catalog))
        object.__setattr__(self, "designation", _name("designation", self.designation))
        if len(self.anchor_mm) != 2:
            raise DocumentError(f"anchor_mm must be [x, y], got {list(self.anchor_mm)!r}")
        require_finite("anchor_mm[0]", self.anchor_mm[0])
        require_finite("anchor_mm[1]", self.anchor_mm[1])
        require_finite("rotation_deg", self.rotation_deg)
        object.__setattr__(self, "label", optional_label(self.label))


@dataclass(frozen=True, slots=True)
class AddCircularTie:
    """A spiral or a circular hoop (ADR 0039 decision 5) around a centre on z = 0.

    `pitch_mm` is a spiral's pitch, or a hoop's spacing. The enclosed bars are not named:
    the consumer derives them.
    """

    kind: str
    center_id: VertexRef
    centerline_radius_mm: float
    designation: str
    pitch_mm: float
    label: str | None = None
    entity_id: EntityId | None = None

    def __post_init__(self) -> None:
        if self.kind not in CIRCULAR_TIE_KINDS:
            raise DocumentError(
                f"a circular tie's kind must be one of {CIRCULAR_TIE_KINDS}, got {self.kind!r}"
            )
        _positive("centerline_radius_mm", self.centerline_radius_mm)
        diameter_of(self.designation)
        _positive("pitch_mm", self.pitch_mm)
        object.__setattr__(self, "label", optional_label(self.label))


@dataclass(frozen=True, slots=True)
class AddBarsOnCircle:
    """`count` bars evenly on a circle of bar centres, the first at `start_angle_deg`.

    One gesture, one op. Every bar gets a fresh point; the committed op records them in
    `bar_ids` and `bar_point_ids`. `material` is the bar steel's name, or None.
    """

    center_x_mm: float
    center_y_mm: float
    radius_mm: float
    count: int
    designation: str
    start_angle_deg: float = 0.0
    material: str | None = None
    bar_ids: tuple[EntityId, ...] = ()
    bar_point_ids: tuple[EntityId, ...] = ()

    def __post_init__(self) -> None:
        require_finite("center_x_mm", self.center_x_mm)
        require_finite("center_y_mm", self.center_y_mm)
        _positive("radius_mm", self.radius_mm)
        if isinstance(self.count, bool) or self.count < 2:
            raise DocumentError(f"count must be 2 or more, got {self.count!r}")
        diameter_of(self.designation)
        require_finite("start_angle_deg", self.start_angle_deg)
        if self.material is not None:
            object.__setattr__(self, "material", _name("material", self.material))
        if len(self.bar_ids) != len(self.bar_point_ids):
            raise DocumentError(
                f"bar_ids records {len(self.bar_ids)} bars but bar_point_ids "
                f"{len(self.bar_point_ids)} points"
            )


SectionFaceOp = AddSectionFace | AddFaceHole | AddSteelShape | AddCircularTie | AddBarsOnCircle
SECTION_FACE_OPS = (AddSectionFace, AddFaceHole, AddSteelShape, AddCircularTie, AddBarsOnCircle)
