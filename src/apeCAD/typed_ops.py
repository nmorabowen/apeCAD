"""Typed per-op convenience methods for `Document` (ADR 0023: the facade stays small).

Each method builds one op and hands it to `Document._apply`; none of them touches state.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from apeCAD.entities import (
    Arc,
    Bezier,
    Circle,
    Ellipse,
    Entity,
    EntityId,
    Face,
    Line,
    Point,
    Polyline,
    Solid,
)
from apeCAD.errors import DocumentError
from apeCAD.geometry import XYZ
from apeCAD.ops import (
    AddArc,
    AddBezier,
    AddBox,
    AddCircle,
    AddEllipse,
    AddFace,
    AddFaceFromLines,
    AddLine,
    AddLineChain,
    AddPoint,
    AddPolyline,
    ArrayLinear,
    ArrayPolar,
    BreakCrossing,
    ChamferCorner,
    Delete,
    Extrude,
    FilletCorner,
    InsertNode,
    JoinPolyline,
    Mirror,
    Op,
    Rotate,
    SetLabel,
    Sew,
    Simplify,
    Tag,
    Translate,
    TrimLine,
    VertexRef,
)

TEntity = TypeVar("TEntity", bound=Entity)


class TypedOps:
    """Mixin: one typed method per op. `Document` supplies `_apply`, `_ops` and `entity`."""

    _ops: list[Op]

    def _apply(self, op: Op) -> Entity | None:
        raise NotImplementedError

    def entity(self, entity_id: EntityId) -> Entity:
        raise NotImplementedError

    def add_point(
        self,
        x_mm: float,
        y_mm: float,
        z_mm: float,
        *,
        label: str | None = None,
    ) -> Point:
        return self._require_produced(
            self._apply(AddPoint(x_mm=x_mm, y_mm=y_mm, z_mm=z_mm, label=label)),
            Point,
        )

    def add_line(
        self,
        start_id: VertexRef,
        end_id: VertexRef,
        *,
        label: str | None = None,
    ) -> Line:
        return self._require_produced(
            self._apply(AddLine(start_id=start_id, end_id=end_id, label=label)),
            Line,
        )

    def add_line_chain(
        self, point_ids: Sequence[VertexRef], *, label: str | None = None
    ) -> tuple[Line, ...]:
        """One line-tool gesture: a Line per consecutive pair, one op (ADR 0030)."""
        self._apply(AddLineChain(point_ids=tuple(point_ids), label=label))
        committed = self._ops[-1]
        assert isinstance(committed, AddLineChain) and committed.line_ids is not None
        return tuple(self._require_produced(self.entity(i), Line) for i in committed.line_ids)

    def add_polyline(
        self,
        point_ids: Sequence[VertexRef],
        *,
        closed: bool = False,
        label: str | None = None,
    ) -> Polyline:
        return self._require_produced(
            self._apply(AddPolyline(point_ids=tuple(point_ids), closed=closed, label=label)),
            Polyline,
        )

    def add_box(
        self,
        origin_xyz_mm: tuple[float, float, float] | XYZ,
        size_xyz_mm: tuple[float, float, float] | XYZ,
        *,
        label: str | None = None,
    ) -> Solid:
        """AABB sugar: four points, a Face, and Extrude. One AddBox op in the log."""
        op = AddBox(
            origin_xyz_mm=XYZ.from_sequence(origin_xyz_mm),
            size_xyz_mm=XYZ.from_sequence(size_xyz_mm),
            label=label,
        )
        return self._require_produced(self._apply(op), Solid)

    def add_face(
        self,
        point_ids: Sequence[VertexRef],
        *,
        label: str | None = None,
    ) -> Face:
        return self._require_produced(
            self._apply(AddFace(point_ids=tuple(point_ids), label=label)),
            Face,
        )

    def extrude(
        self,
        face_id: EntityId | None,
        distance_mm: float,
        *,
        direction_xyz: tuple[float, float, float] | XYZ | None = None,
        label: str | None = None,
        ring: Sequence[VertexRef] | None = None,
    ) -> Solid:
        """Extrude a profile, or with `ring` (and face_id None) make the face too (ADR 0030)."""
        op = Extrude(
            face_id=face_id,
            distance_mm=distance_mm,
            direction_xyz=XYZ(0.0, 0.0, 1.0)
            if direction_xyz is None
            else XYZ.from_sequence(direction_xyz),
            label=label,
            ring=None if ring is None else tuple(ring),
        )
        return self._require_produced(self._apply(op), Solid)

    def add_circle(
        self,
        center_id: VertexRef,
        radius_mm: float,
        *,
        label: str | None = None,
    ) -> Circle:
        return self._require_produced(
            self._apply(AddCircle(center_id=center_id, radius_mm=radius_mm, label=label)),
            Circle,
        )

    def add_arc(
        self,
        start_id: VertexRef,
        mid_id: VertexRef,
        end_id: VertexRef,
        *,
        label: str | None = None,
    ) -> Arc:
        return self._require_produced(
            self._apply(
                AddArc(start_id=start_id, mid_id=mid_id, end_id=end_id, label=label)
            ),
            Arc,
        )

    def add_ellipse(
        self,
        center_id: VertexRef,
        radius_x_mm: float,
        radius_y_mm: float,
        *,
        label: str | None = None,
    ) -> Ellipse:
        return self._require_produced(
            self._apply(
                AddEllipse(
                    center_id=center_id,
                    radius_x_mm=radius_x_mm,
                    radius_y_mm=radius_y_mm,
                    label=label,
                )
            ),
            Ellipse,
        )

    def add_bezier(
        self,
        point_ids: Sequence[VertexRef],
        *,
        label: str | None = None,
    ) -> Bezier:
        return self._require_produced(
            self._apply(AddBezier(point_ids=tuple(point_ids), label=label)),
            Bezier,
        )

    def translate(
        self,
        entity_ids: tuple[EntityId, ...] | list[EntityId],
        dx_mm: float,
        dy_mm: float,
        dz_mm: float = 0.0,
    ) -> None:
        self._apply(
            Translate(
                entity_ids=tuple(entity_ids),
                dx_mm=dx_mm,
                dy_mm=dy_mm,
                dz_mm=dz_mm,
            )
        )

    def insert_node(
        self,
        target_id: EntityId,
        x_mm: float,
        y_mm: float,
        z_mm: float = 0.0,
    ) -> Point:
        return self._require_produced(
            self._apply(InsertNode(target_id=target_id, x_mm=x_mm, y_mm=y_mm, z_mm=z_mm)),
            Point,
        )

    def trim_line(
        self,
        line_id: EntityId,
        keep_id: EntityId,
        x_mm: float,
        y_mm: float,
        z_mm: float = 0.0,
    ) -> Point:
        return self._require_produced(
            self._apply(
                TrimLine(line_id=line_id, keep_id=keep_id, x_mm=x_mm, y_mm=y_mm, z_mm=z_mm)
            ),
            Point,
        )

    def break_crossing(
        self,
        line_a_id: EntityId,
        line_b_id: EntityId,
    ) -> Point:
        return self._require_produced(
            self._apply(BreakCrossing(line_a_id=line_a_id, line_b_id=line_b_id)),
            Point,
        )

    def add_face_from_lines(
        self,
        line_ids: tuple[EntityId, ...] | list[EntityId],
        *,
        label: str | None = None,
    ) -> Face:
        return self._require_produced(
            self._apply(AddFaceFromLines(line_ids=tuple(line_ids), label=label)),
            Face,
        )

    def join_polyline(
        self,
        entity_ids: tuple[EntityId, ...] | list[EntityId],
        *,
        label: str | None = None,
    ) -> Polyline:
        return self._require_produced(
            self._apply(JoinPolyline(entity_ids=tuple(entity_ids), label=label)),
            Polyline,
        )

    def rotate(
        self,
        entity_ids: tuple[EntityId, ...] | list[EntityId],
        origin_x_mm: float,
        origin_y_mm: float,
        angle_deg: float,
    ) -> None:
        self._apply(
            Rotate(
                entity_ids=tuple(entity_ids),
                origin_x_mm=origin_x_mm,
                origin_y_mm=origin_y_mm,
                angle_deg=angle_deg,
            )
        )

    def mirror(
        self,
        entity_ids: tuple[EntityId, ...] | list[EntityId],
        ax_mm: float,
        ay_mm: float,
        bx_mm: float,
        by_mm: float,
    ) -> None:
        self._apply(
            Mirror(
                entity_ids=tuple(entity_ids),
                ax_mm=ax_mm,
                ay_mm=ay_mm,
                bx_mm=bx_mm,
                by_mm=by_mm,
            )
        )

    def chamfer_corner(
        self,
        target_id: EntityId,
        vertex_id: EntityId,
        distance_mm: float,
    ) -> Line:
        return self._require_produced(
            self._apply(
                ChamferCorner(
                    target_id=target_id,
                    vertex_id=vertex_id,
                    distance_mm=distance_mm,
                )
            ),
            Line,
        )

    def fillet_corner(
        self,
        target_id: EntityId,
        vertex_id: EntityId,
        radius_mm: float,
    ) -> Arc:
        return self._require_produced(
            self._apply(
                FilletCorner(
                    target_id=target_id,
                    vertex_id=vertex_id,
                    radius_mm=radius_mm,
                )
            ),
            Arc,
        )

    def sew(
        self,
        entity_ids: tuple[EntityId, ...] | list[EntityId],
        *,
        tolerance_mm: float = 1.0,
    ) -> None:
        self._apply(Sew(entity_ids=tuple(entity_ids), tolerance_mm=tolerance_mm))

    def simplify(self, entity_ids: tuple[EntityId, ...] | list[EntityId]) -> None:
        self._apply(Simplify(entity_ids=tuple(entity_ids)))

    def array_linear(
        self,
        entity_ids: tuple[EntityId, ...] | list[EntityId],
        dx_mm: float,
        dy_mm: float,
        dz_mm: float = 0.0,
        *,
        copies: int = 1,
    ) -> None:
        self._apply(
            ArrayLinear(
                entity_ids=tuple(entity_ids),
                dx_mm=dx_mm,
                dy_mm=dy_mm,
                dz_mm=dz_mm,
                copies=copies,
            )
        )

    def array_polar(
        self,
        entity_ids: tuple[EntityId, ...] | list[EntityId],
        origin_x_mm: float,
        origin_y_mm: float,
        count: int,
        *,
        angle_deg: float = 360.0,
    ) -> None:
        self._apply(
            ArrayPolar(
                entity_ids=tuple(entity_ids),
                origin_x_mm=origin_x_mm,
                origin_y_mm=origin_y_mm,
                count=count,
                angle_deg=angle_deg,
            )
        )

    def delete(self, entity_ids: tuple[EntityId, ...] | list[EntityId]) -> None:
        self._apply(Delete(entity_ids=tuple(entity_ids)))

    def tag(self, name: str, entity_ids: tuple[EntityId, ...] | list[EntityId]) -> None:
        self._apply(Tag(name=name, entity_ids=tuple(entity_ids)))

    def set_label(self, entity_id: EntityId, label: str | None) -> None:
        self._apply(SetLabel(entity_id=entity_id, label=label))


    def _require_produced(self, entity: Entity | None, kind: type[TEntity]) -> TEntity:
        if not isinstance(entity, kind):
            raise DocumentError(f"internal error: expected {kind.__name__}")
        return entity
