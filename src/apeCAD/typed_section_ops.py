"""Typed `Document` methods for the section-mode ops (ADR 0024).

Kept apart from `typed_ops.py` so that C2 and C3 (legs, cover, bar rows) have room.
"""

from __future__ import annotations

from collections.abc import Sequence

from apeCAD.entities import (
    Bar,
    ConcreteFace,
    CoverGuide,
    Crosstie,
    EntityId,
    Hoop,
    LegSteel,
    WallLeg,
)
from apeCAD.ops import (
    AddBar,
    AddBarRow,
    AddBarsAlongEdge,
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

    def add_section_outline(
        self,
        point_ids: Sequence[VertexRef],
        material: str,
        *,
        label: str | None = None,
    ) -> ConcreteFace:
        """The outline gesture: one solid face on z = 0, stored CCW; a bow-tie is refused."""
        op = AddSectionOutline(point_ids=tuple(point_ids), material=material, label=label)
        return self._require_produced(self._apply(op), ConcreteFace)

    def add_wall_chain(
        self,
        point_ids: Sequence[VertexRef],
        thickness_mm: float | Sequence[float],
        material: str,
        *,
        horizontal: LegSteel | None = None,
        label: str | None = None,
    ) -> ConcreteFace:
        """One outline face around a wall axis, plus one leg per axis segment."""
        thicknesses = (
            (float(thickness_mm),)
            if isinstance(thickness_mm, (int, float))
            else tuple(thickness_mm)
        )
        op = AddWallChain(
            point_ids=tuple(point_ids),
            thickness_mm=thicknesses,
            material=material,
            horizontal=horizontal,
            label=label,
        )
        return self._require_produced(self._apply(op), ConcreteFace)

    def add_wall_leg(
        self,
        start_id: VertexRef,
        end_id: VertexRef,
        thickness_mm: float,
        face_id: EntityId,
        *,
        horizontal: LegSteel | None = None,
        label: str | None = None,
    ) -> WallLeg:
        """A leg on an existing concrete face (a T outline takes three)."""
        op = AddWallLeg(
            start_id=start_id,
            end_id=end_id,
            thickness_mm=thickness_mm,
            face_id=face_id,
            horizontal=horizontal,
            label=label,
        )
        return self._require_produced(self._apply(op), WallLeg)

    def set_leg_reinforcement(
        self, leg_id: EntityId, designation: str, spacing_mm: float, curtains: int
    ) -> None:
        self._apply(
            SetLegReinforcement(
                leg_id=leg_id, designation=designation, spacing_mm=spacing_mm, curtains=curtains
            )
        )

    def set_cover(
        self,
        face_id: EntityId,
        cover_mm: float,
        tie_diameter_mm: float,
        bar_diameter_mm: float,
    ) -> CoverGuide:
        """Create or change the face's cover guide (clear cover to the outside of the tie)."""
        op = SetCover(
            face_id=face_id,
            cover_mm=cover_mm,
            tie_diameter_mm=tie_diameter_mm,
            bar_diameter_mm=bar_diameter_mm,
        )
        return self._require_produced(self._apply(op), CoverGuide)

    def add_bar_row(
        self,
        start_xy_mm: tuple[float, float],
        end_xy_mm: tuple[float, float],
        designation: str,
        *,
        count: int | None = None,
        spacing_mm: float | None = None,
    ) -> tuple[Bar, ...]:
        """A row of bars, by count (ends included) or spacing (remainder centred); one op."""
        op = AddBarRow(
            start_x_mm=start_xy_mm[0],
            start_y_mm=start_xy_mm[1],
            end_x_mm=end_xy_mm[0],
            end_y_mm=end_xy_mm[1],
            designation=designation,
            count=count,
            spacing_mm=spacing_mm,
        )
        self._apply(op)
        return self._bars_placed()

    def add_bars_along_edge(
        self,
        face_id: EntityId,
        edge_index: int,
        designation: str,
        *,
        count: int | None = None,
        spacing_mm: float | None = None,
    ) -> tuple[Bar, ...]:
        """Bars on one edge of the face's bar-centre ring, skipping positions near a bar."""
        op = AddBarsAlongEdge(
            face_id=face_id,
            edge_index=edge_index,
            designation=designation,
            count=count,
            spacing_mm=spacing_mm,
        )
        self._apply(op)
        return self._bars_placed()

    def _bars_placed(self) -> tuple[Bar, ...]:
        committed = self._ops[-1]
        assert isinstance(committed, (AddBarRow, AddBarsAlongEdge))
        return tuple(self._require_produced(self.entity(i), Bar) for i in committed.bar_ids)
