"""Section-mode ops (ADR 0024): concrete faces, bars, hoops, crossties and their settings.

Ops carry designations only; the handler looks the diameter up in the closed vocabulary
(`section.designations`, P12), so a designation and its diameter can never disagree.
"""

from __future__ import annotations

from dataclasses import dataclass

from apeCAD.entities import EntityId
from apeCAD.errors import DocumentError
from apeCAD.geometry import require_finite
from apeCAD.ops.base import VertexRef, optional_label
from apeCAD.section.designations import diameter_of

HOOP_HOOKS = ("135",)
CROSSTIE_HOOKS = ("135-135", "135-90")


def require_designation_name(designation: str) -> str:
    diameter_of(designation)
    return designation


def require_material(material: str) -> str:
    stripped = material.strip()
    if stripped == "":
        raise DocumentError("material must be a non-empty name")
    return stripped


def require_spacing(spacing_mm: float) -> float:
    if not require_finite("spacing_mm", spacing_mm) > 0.0:
        raise DocumentError(f"spacing_mm must be positive, got {spacing_mm!r}")
    return spacing_mm


def require_hoop_hooks(hooks: str) -> str:
    if hooks not in HOOP_HOOKS:
        raise DocumentError(f"hoop hooks must be one of {HOOP_HOOKS}, got {hooks!r}")
    return hooks


def require_crosstie_hooks(hooks: str) -> str:
    if hooks == "90-90":
        raise DocumentError('a crosstie with "90-90" hooks is refused; use "135-135" or "135-90"')
    if hooks not in CROSSTIE_HOOKS:
        raise DocumentError(f"crosstie hooks must be one of {CROSSTIE_HOOKS}, got {hooks!r}")
    return hooks


def _require_targets(entity_ids: tuple[EntityId, ...], what: str) -> None:
    if not entity_ids:
        raise DocumentError(f"{what} needs at least one entity id")


@dataclass(frozen=True, slots=True)
class AddConcreteFace:
    """A concrete outline on z = 0. The handler stores the ring counter-clockwise."""

    point_ids: tuple[VertexRef, ...]
    material: str
    label: str | None = None
    entity_id: EntityId | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "material", require_material(self.material))
        object.__setattr__(self, "label", optional_label(self.label))


@dataclass(frozen=True, slots=True)
class AddBar:
    """A bar at (x, y) on z = 0. Always a fresh Point, never a reused one (ADR 0024)."""

    x_mm: float
    y_mm: float
    designation: str
    label: str | None = None
    entity_id: EntityId | None = None
    point_id: EntityId | None = None

    def __post_init__(self) -> None:
        require_finite("x_mm", self.x_mm)
        require_finite("y_mm", self.y_mm)
        require_designation_name(self.designation)
        object.__setattr__(self, "label", optional_label(self.label))


@dataclass(frozen=True, slots=True)
class AddHoop:
    """A hoop around the selected bars; stored as their strict CCW hull (P2)."""

    bar_ids: tuple[EntityId, ...]
    designation: str
    spacing_mm: float
    hooks: str = "135"
    label: str | None = None
    entity_id: EntityId | None = None

    def __post_init__(self) -> None:
        require_designation_name(self.designation)
        require_spacing(self.spacing_mm)
        require_hoop_hooks(self.hooks)
        object.__setattr__(self, "label", optional_label(self.label))


@dataclass(frozen=True, slots=True)
class AddCrosstie:
    bar_a_id: EntityId
    bar_b_id: EntityId
    designation: str
    spacing_mm: float
    hooks: str = "135-135"
    label: str | None = None
    entity_id: EntityId | None = None

    def __post_init__(self) -> None:
        if self.bar_a_id == self.bar_b_id:
            raise DocumentError(f"a crosstie needs two distinct bars, got {self.bar_a_id} twice")
        require_designation_name(self.designation)
        require_spacing(self.spacing_mm)
        require_crosstie_hooks(self.hooks)
        object.__setattr__(self, "label", optional_label(self.label))


@dataclass(frozen=True, slots=True)
class SetBarSize:
    entity_ids: tuple[EntityId, ...]
    designation: str

    def __post_init__(self) -> None:
        _require_targets(self.entity_ids, "SetBarSize")
        require_designation_name(self.designation)


@dataclass(frozen=True, slots=True)
class SetMaterial:
    entity_ids: tuple[EntityId, ...]
    material: str

    def __post_init__(self) -> None:
        _require_targets(self.entity_ids, "SetMaterial")
        object.__setattr__(self, "material", require_material(self.material))


@dataclass(frozen=True, slots=True)
class SetTransverse:
    """Change the size, spacing or hooks of hoops and crossties; None keeps a value."""

    entity_ids: tuple[EntityId, ...]
    designation: str | None = None
    spacing_mm: float | None = None
    hooks: str | None = None

    def __post_init__(self) -> None:
        _require_targets(self.entity_ids, "SetTransverse")
        if self.designation is None and self.spacing_mm is None and self.hooks is None:
            raise DocumentError("SetTransverse needs a designation, a spacing_mm or hooks")
        if self.designation is not None:
            require_designation_name(self.designation)
        if self.spacing_mm is not None:
            require_spacing(self.spacing_mm)
        if self.hooks is not None and not (
            self.hooks in HOOP_HOOKS or self.hooks in CROSSTIE_HOOKS
        ):
            require_crosstie_hooks(self.hooks)  # raises, naming "90-90" when that was sent


SectionOp = (
    AddConcreteFace | AddBar | AddHoop | AddCrosstie | SetBarSize | SetMaterial | SetTransverse
)
SECTION_OPS = (
    AddConcreteFace,
    AddBar,
    AddHoop,
    AddCrosstie,
    SetBarSize,
    SetMaterial,
    SetTransverse,
)
