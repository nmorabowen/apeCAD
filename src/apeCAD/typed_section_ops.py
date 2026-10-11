"""Typed `Document` methods for the section-mode ops (ADR 0024).

Kept apart from `typed_ops.py` so that C2 and C3 (legs, cover, bar rows) have room.
"""

from __future__ import annotations

from collections.abc import Sequence

from apeCAD.entities import Bar, ConcreteFace, Crosstie, EntityId, Hoop
from apeCAD.ops import (
    AddBar,
    AddConcreteFace,
    AddCrosstie,
    AddHoop,
    SetBarSize,
    SetMaterial,
    SetTransverse,
    VertexRef,
)
from apeCAD.typed_ops import TypedOps


class SectionTypedOps(TypedOps):
    """Mixin: one typed method per section op."""

    def add_concrete_face(
        self,
        point_ids: Sequence[VertexRef],
        material: str,
        *,
        label: str | None = None,
    ) -> ConcreteFace:
        """A solid concrete outline on z = 0, stored counter-clockwise."""
        op = AddConcreteFace(point_ids=tuple(point_ids), material=material, label=label)
        return self._require_produced(self._apply(op), ConcreteFace)

    def add_bar(
        self,
        x_mm: float,
        y_mm: float,
        designation: str,
        *,
        label: str | None = None,
    ) -> Bar:
        """A bar at (x, y, 0) with a fresh point of its own."""
        op = AddBar(x_mm=x_mm, y_mm=y_mm, designation=designation, label=label)
        return self._require_produced(self._apply(op), Bar)

    def add_hoop(
        self,
        bar_ids: Sequence[EntityId],
        designation: str,
        spacing_mm: float,
        *,
        hooks: str = "135",
        label: str | None = None,
    ) -> Hoop:
        """A hoop around the bars' strict CCW hull; selection order does not matter."""
        op = AddHoop(
            bar_ids=tuple(bar_ids),
            designation=designation,
            spacing_mm=spacing_mm,
            hooks=hooks,
            label=label,
        )
        return self._require_produced(self._apply(op), Hoop)

    def add_crosstie(
        self,
        bar_a_id: EntityId,
        bar_b_id: EntityId,
        designation: str,
        spacing_mm: float,
        *,
        hooks: str = "135-135",
        label: str | None = None,
    ) -> Crosstie:
        op = AddCrosstie(
            bar_a_id=bar_a_id,
            bar_b_id=bar_b_id,
            designation=designation,
            spacing_mm=spacing_mm,
            hooks=hooks,
            label=label,
        )
        return self._require_produced(self._apply(op), Crosstie)

    def set_bar_size(self, entity_ids: Sequence[EntityId], designation: str) -> None:
        self._apply(SetBarSize(entity_ids=tuple(entity_ids), designation=designation))

    def set_material(self, entity_ids: Sequence[EntityId], material: str) -> None:
        self._apply(SetMaterial(entity_ids=tuple(entity_ids), material=material))

    def set_transverse(
        self,
        entity_ids: Sequence[EntityId],
        *,
        designation: str | None = None,
        spacing_mm: float | None = None,
        hooks: str | None = None,
    ) -> None:
        """Size, spacing or hooks of hoops and crossties; None keeps a value."""
        self._apply(
            SetTransverse(
                entity_ids=tuple(entity_ids),
                designation=designation,
                spacing_mm=spacing_mm,
                hooks=hooks,
            )
        )
