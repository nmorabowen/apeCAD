"""Kernel-free spatial draft. The ops log is the only writer."""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import replace
from typing import TypeVar, cast

from apeCAD.entities import (
    Arc,
    Bezier,
    Box,
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
from apeCAD.frame import FrameGraph, document_to_frame
from apeCAD.geometry import (
    XYZ,
    collinear_xy,
    line_intersect_xy,
    mirror_xy,
    project_on_segment,
    rotate_xy,
)
from apeCAD.ops import (
    SCHEMA_ID,
    UNITS,
    AddArc,
    AddBezier,
    AddBox,
    AddCircle,
    AddEllipse,
    AddFace,
    AddFaceFromLines,
    AddLine,
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
    Sew,
    Simplify,
    Tag,
    Translate,
    TrimLine,
    op_from_dict,
    op_to_dict,
)

TEntity = TypeVar("TEntity", bound=Entity)


class Document:
    """In-memory scratchpad. Mutate only through ops; JSON replays the log."""

    def __init__(self) -> None:
        self._ops: list[Op] = []
        self._redo: list[Op] = []
        self._next_id: EntityId = 1
        self._entities: dict[EntityId, Entity] = {}
        self._labels: dict[str, EntityId] = {}
        self._tags: dict[str, set[EntityId]] = {}

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
        start_id: EntityId,
        end_id: EntityId,
        *,
        label: str | None = None,
    ) -> Line:
        return self._require_produced(
            self._apply(AddLine(start_id=start_id, end_id=end_id, label=label)),
            Line,
        )

    def add_polyline(
        self,
        point_ids: tuple[EntityId, ...] | list[EntityId],
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
    ) -> Box:
        op = AddBox(
            origin_xyz_mm=XYZ.from_sequence(origin_xyz_mm),
            size_xyz_mm=XYZ.from_sequence(size_xyz_mm),
            label=label,
        )
        return self._require_produced(self._apply(op), Box)

    def add_face(
        self,
        point_ids: tuple[EntityId, ...] | list[EntityId],
        *,
        label: str | None = None,
    ) -> Face:
        return self._require_produced(
            self._apply(AddFace(point_ids=tuple(point_ids), label=label)),
            Face,
        )

    def extrude(
        self,
        face_id: EntityId,
        distance_mm: float,
        *,
        direction_xyz: tuple[float, float, float] | XYZ | None = None,
        label: str | None = None,
    ) -> Solid:
        op = Extrude(
            face_id=face_id,
            distance_mm=distance_mm,
            direction_xyz=XYZ(0.0, 0.0, 1.0)
            if direction_xyz is None
            else XYZ.from_sequence(direction_xyz),
            label=label,
        )
        return self._require_produced(self._apply(op), Solid)

    def add_circle(
        self,
        center_id: EntityId,
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
        start_id: EntityId,
        mid_id: EntityId,
        end_id: EntityId,
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
        center_id: EntityId,
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
        point_ids: tuple[EntityId, ...] | list[EntityId],
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

    def undo(self) -> None:
        if not self._ops:
            raise DocumentError("nothing to undo")
        self._redo.append(self._ops.pop())
        self._rebuild()

    def redo(self) -> None:
        if not self._redo:
            raise DocumentError("nothing to redo")
        self._apply(self._redo.pop(), from_redo=True)

    def entity(self, entity_id: EntityId) -> Entity:
        try:
            return self._entities[entity_id]
        except KeyError as exc:
            raise DocumentError(f"unknown entity id {entity_id}") from exc

    def entity_by_label(self, label: str) -> Entity:
        try:
            entity_id = self._labels[label]
        except KeyError as exc:
            raise DocumentError(f"unknown label {label!r}") from exc
        return self._entities[entity_id]

    def points(self) -> tuple[Point, ...]:
        return tuple(e for e in self._iter_entities() if isinstance(e, Point))

    def lines(self) -> tuple[Line, ...]:
        return tuple(e for e in self._iter_entities() if isinstance(e, Line))

    def polylines(self) -> tuple[Polyline, ...]:
        return tuple(e for e in self._iter_entities() if isinstance(e, Polyline))

    def boxes(self) -> tuple[Box, ...]:
        return tuple(e for e in self._iter_entities() if isinstance(e, Box))

    def faces(self) -> tuple[Face, ...]:
        return tuple(e for e in self._iter_entities() if isinstance(e, Face))

    def solids(self) -> tuple[Solid, ...]:
        return tuple(e for e in self._iter_entities() if isinstance(e, Solid))

    def circles(self) -> tuple[Circle, ...]:
        return tuple(e for e in self._iter_entities() if isinstance(e, Circle))

    def arcs(self) -> tuple[Arc, ...]:
        return tuple(e for e in self._iter_entities() if isinstance(e, Arc))

    def ellipses(self) -> tuple[Ellipse, ...]:
        return tuple(e for e in self._iter_entities() if isinstance(e, Ellipse))

    def beziers(self) -> tuple[Bezier, ...]:
        return tuple(e for e in self._iter_entities() if isinstance(e, Bezier))

    def tags(self) -> dict[str, frozenset[EntityId]]:
        return {name: frozenset(ids) for name, ids in sorted(self._tags.items())}

    def tagged(self, name: str) -> frozenset[EntityId]:
        return frozenset(self._tags.get(name, set()))

    def ops(self) -> tuple[Op, ...]:
        return tuple(self._ops)

    def to_frame(self) -> FrameGraph:
        """Project points/lines/polylines into a millimetre frame graph."""
        return document_to_frame(self)

    def apply(self, op: Op) -> Entity | None:
        """Apply one typed operation. The scratchpad client uses this."""
        return self._apply(op)

    def _require_produced(self, entity: Entity | None, kind: type[TEntity]) -> TEntity:
        if not isinstance(entity, kind):
            raise DocumentError(f"internal error: expected {kind.__name__}")
        return entity

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": SCHEMA_ID,
            "units": UNITS,
            "ops": [op_to_dict(op) for op in self._ops],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False) + "\n"

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> Document:
        schema = payload.get("schema")
        if schema != SCHEMA_ID:
            raise DocumentError(f"unsupported schema {schema!r}, expected {SCHEMA_ID!r}")
        units = payload.get("units")
        if units != UNITS:
            raise DocumentError(f"unsupported units {units!r}, expected {UNITS!r}")
        raw_ops = payload.get("ops")
        if not isinstance(raw_ops, list):
            raise DocumentError("ops must be a list")
        document = cls()
        for raw_op in cast(list[object], raw_ops):
            document._apply(op_from_dict(_as_string_dict(raw_op)))
        return document

    @classmethod
    def from_json(cls, text: str) -> Document:
        parsed: object = json.loads(text)
        return cls.from_dict(_as_string_dict(parsed))

    def _iter_entities(self) -> tuple[Entity, ...]:
        return tuple(self._entities[entity_id] for entity_id in sorted(self._entities))

    def _apply(self, op: Op, *, from_redo: bool = False) -> Entity | None:
        committed = self._dispatch(op)
        self._ops.append(committed)
        if not from_redo:
            self._redo.clear()
        if isinstance(committed, (
            Tag,
            Translate,
            Rotate,
            Mirror,
            Sew,
            Simplify,
            ArrayLinear,
            ArrayPolar,
            Delete,
        )):
            return None
        return self._entities[_entity_id_of(committed)]

    def _dispatch(self, op: Op) -> Op:
        if isinstance(op, AddPoint):
            return self._add_point(op)
        if isinstance(op, AddLine):
            return self._add_line(op)
        if isinstance(op, AddPolyline):
            return self._add_polyline(op)
        if isinstance(op, AddBox):
            return self._add_box(op)
        if isinstance(op, AddFace):
            return self._add_face(op)
        if isinstance(op, Extrude):
            return self._extrude(op)
        if isinstance(op, AddCircle):
            return self._add_circle(op)
        if isinstance(op, AddArc):
            return self._add_arc(op)
        if isinstance(op, AddEllipse):
            return self._add_ellipse(op)
        if isinstance(op, AddBezier):
            return self._add_bezier(op)
        if isinstance(op, Translate):
            return self._translate(op)
        if isinstance(op, InsertNode):
            return self._insert_node(op)
        if isinstance(op, TrimLine):
            return self._trim_line(op)
        if isinstance(op, BreakCrossing):
            return self._break_crossing(op)
        if isinstance(op, AddFaceFromLines):
            return self._add_face_from_lines(op)
        if isinstance(op, JoinPolyline):
            return self._join_polyline(op)
        if isinstance(op, Rotate):
            return self._rotate(op)
        if isinstance(op, Mirror):
            return self._mirror(op)
        if isinstance(op, ChamferCorner):
            return self._chamfer_corner(op)
        if isinstance(op, FilletCorner):
            return self._fillet_corner(op)
        if isinstance(op, Sew):
            return self._sew(op)
        if isinstance(op, Simplify):
            return self._simplify(op)
        if isinstance(op, ArrayLinear):
            return self._array_linear(op)
        if isinstance(op, ArrayPolar):
            return self._array_polar(op)
        if isinstance(op, Delete):
            return self._delete(op)
        return self._tag(op)

    def _add_point(self, op: AddPoint) -> AddPoint:
        self._reject_taken_label(op.label)
        entity_id = self._allocate_id(op.entity_id)
        self._register_label(entity_id, op.label)
        self._entities[entity_id] = Point(
            entity_id=entity_id,
            xyz_mm=XYZ(op.x_mm, op.y_mm, op.z_mm),
            label=op.label,
        )
        return replace(op, entity_id=entity_id)

    def _add_line(self, op: AddLine) -> AddLine:
        if op.start_id == op.end_id:
            raise DocumentError(f"line start and end cannot be the same point id {op.start_id}")
        self._require_point(op.start_id)
        self._require_point(op.end_id)
        self._reject_taken_label(op.label)
        entity_id = self._allocate_id(op.entity_id)
        self._register_label(entity_id, op.label)
        self._entities[entity_id] = Line(
            entity_id=entity_id,
            start_id=op.start_id,
            end_id=op.end_id,
            label=op.label,
        )
        return replace(op, entity_id=entity_id)

    def _add_polyline(self, op: AddPolyline) -> AddPolyline:
        for point_id in op.point_ids:
            self._require_point(point_id)
        self._reject_taken_label(op.label)
        entity_id = self._allocate_id(op.entity_id)
        self._register_label(entity_id, op.label)
        self._entities[entity_id] = Polyline(
            entity_id=entity_id,
            point_ids=op.point_ids,
            closed=op.closed,
            label=op.label,
        )
        return replace(op, entity_id=entity_id)

    def _add_box(self, op: AddBox) -> AddBox:
        self._reject_taken_label(op.label)
        entity_id = self._allocate_id(op.entity_id)
        self._register_label(entity_id, op.label)
        self._entities[entity_id] = Box(
            entity_id=entity_id,
            origin_xyz_mm=op.origin_xyz_mm,
            size_xyz_mm=op.size_xyz_mm,
            label=op.label,
        )
        return replace(op, entity_id=entity_id)

    def _add_face(self, op: AddFace) -> AddFace:
        for point_id in op.point_ids:
            self._require_point(point_id)
        self._reject_taken_label(op.label)
        entity_id = self._allocate_id(op.entity_id)
        self._register_label(entity_id, op.label)
        self._entities[entity_id] = Face(
            entity_id=entity_id,
            point_ids=op.point_ids,
            label=op.label,
        )
        return replace(op, entity_id=entity_id)

    def _extrude(self, op: Extrude) -> Extrude:
        face = self._entities.get(op.face_id)
        if not isinstance(face, (Face, Circle, Ellipse)):
            raise DocumentError(
                f"entity {op.face_id} is not a profile (need a face, circle, or ellipse)"
            )
        self._reject_taken_label(op.label)
        entity_id = self._allocate_id(op.entity_id)
        self._register_label(entity_id, op.label)
        self._entities[entity_id] = Solid(
            entity_id=entity_id,
            face_id=op.face_id,
            distance_mm=op.distance_mm,
            direction_xyz=op.direction_xyz,
            label=op.label,
        )
        return replace(op, entity_id=entity_id)

    def _add_circle(self, op: AddCircle) -> AddCircle:
        self._require_point(op.center_id)
        self._reject_taken_label(op.label)
        entity_id = self._allocate_id(op.entity_id)
        self._register_label(entity_id, op.label)
        self._entities[entity_id] = Circle(
            entity_id=entity_id,
            center_id=op.center_id,
            radius_mm=op.radius_mm,
            label=op.label,
        )
        return replace(op, entity_id=entity_id)

    def _add_arc(self, op: AddArc) -> AddArc:
        start = self._require_point(op.start_id)
        mid = self._require_point(op.mid_id)
        end = self._require_point(op.end_id)
        cross = (mid.xyz_mm.x_mm - start.xyz_mm.x_mm) * (
            end.xyz_mm.y_mm - start.xyz_mm.y_mm
        ) - (mid.xyz_mm.y_mm - start.xyz_mm.y_mm) * (
            end.xyz_mm.x_mm - start.xyz_mm.x_mm
        )
        if abs(cross) < 1e-6:
            raise DocumentError("arc points are collinear")
        self._reject_taken_label(op.label)
        entity_id = self._allocate_id(op.entity_id)
        self._register_label(entity_id, op.label)
        self._entities[entity_id] = Arc(
            entity_id=entity_id,
            start_id=op.start_id,
            mid_id=op.mid_id,
            end_id=op.end_id,
            label=op.label,
        )
        return replace(op, entity_id=entity_id)

    def _add_ellipse(self, op: AddEllipse) -> AddEllipse:
        self._require_point(op.center_id)
        self._reject_taken_label(op.label)
        entity_id = self._allocate_id(op.entity_id)
        self._register_label(entity_id, op.label)
        self._entities[entity_id] = Ellipse(
            entity_id=entity_id,
            center_id=op.center_id,
            radius_x_mm=op.radius_x_mm,
            radius_y_mm=op.radius_y_mm,
            label=op.label,
        )
        return replace(op, entity_id=entity_id)

    def _add_bezier(self, op: AddBezier) -> AddBezier:
        for point_id in op.point_ids:
            self._require_point(point_id)
        self._reject_taken_label(op.label)
        entity_id = self._allocate_id(op.entity_id)
        self._register_label(entity_id, op.label)
        self._entities[entity_id] = Bezier(
            entity_id=entity_id,
            point_ids=op.point_ids,
            label=op.label,
        )
        return replace(op, entity_id=entity_id)

    def _translate(self, op: Translate) -> Translate:
        moved = self._transform_points(
            op.entity_ids,
            lambda xyz: XYZ(
                xyz.x_mm + op.dx_mm,
                xyz.y_mm + op.dy_mm,
                xyz.z_mm + op.dz_mm,
            ),
        )
        if not moved:
            raise DocumentError("translate did not move any points")
        return op

    def _rotate(self, op: Rotate) -> Rotate:
        angle = math.radians(op.angle_deg)

        def mapper(xyz: XYZ) -> XYZ:
            x_mm, y_mm = rotate_xy(
                xyz.x_mm, xyz.y_mm, op.origin_x_mm, op.origin_y_mm, angle
            )
            return XYZ(x_mm, y_mm, xyz.z_mm)

        moved = self._transform_points(op.entity_ids, mapper)
        if not moved:
            raise DocumentError("rotate did not move any points")
        return op

    def _mirror(self, op: Mirror) -> Mirror:
        def mapper(xyz: XYZ) -> XYZ:
            x_mm, y_mm = mirror_xy(
                xyz.x_mm, xyz.y_mm, op.ax_mm, op.ay_mm, op.bx_mm, op.by_mm
            )
            return XYZ(x_mm, y_mm, xyz.z_mm)

        moved = self._transform_points(op.entity_ids, mapper)
        if not moved:
            raise DocumentError("mirror did not move any points")
        return op

    def _transform_points(
        self,
        entity_ids: tuple[EntityId, ...],
        mapper: Callable[[XYZ], XYZ],
    ) -> set[EntityId]:
        moved: set[EntityId] = set()
        box_moved = False
        for entity_id in entity_ids:
            entity = self.entity(entity_id)
            for point_id in self._point_ids_of(entity):
                if point_id in moved:
                    continue
                point = self._require_point(point_id)
                self._entities[point_id] = replace(point, xyz_mm=mapper(point.xyz_mm))
                moved.add(point_id)
            if isinstance(entity, Box):
                self._entities[entity_id] = replace(
                    entity, origin_xyz_mm=mapper(entity.origin_xyz_mm)
                )
                box_moved = True
        if not moved and not box_moved:
            return set()
        return moved if moved else {entity_ids[0]}

    def _chamfer_corner(self, op: ChamferCorner) -> ChamferCorner:
        prev_id, vertex_id, next_id = self._corner_of(op.target_id, op.vertex_id)
        t1, t2 = self._offset_on_edges(
            prev_id, vertex_id, next_id, op.distance_mm, op.distance_mm
        )
        start_id, _created = self._point_at(t1[0], t1[1], t1[2], requested=op.start_id)
        end_id, _unused = self._point_at(t2[0], t2[1], t2[2], requested=op.end_id)
        self._replace_corner(op.target_id, vertex_id, (start_id, end_id))
        self._retarget_segment(prev_id, vertex_id, prev_id, start_id)
        self._retarget_segment(vertex_id, next_id, end_id, next_id)
        line_op = self._add_line(
            AddLine(start_id=start_id, end_id=end_id, entity_id=op.entity_id)
        )
        return replace(
            op,
            entity_id=line_op.entity_id,
            start_id=start_id,
            end_id=end_id,
        )

    def _fillet_corner(self, op: FilletCorner) -> FilletCorner:
        prev_id, vertex_id, next_id = self._corner_of(op.target_id, op.vertex_id)
        prev = self._require_point(prev_id)
        vertex = self._require_point(vertex_id)
        nxt = self._require_point(next_id)
        d1x = prev.xyz_mm.x_mm - vertex.xyz_mm.x_mm
        d1y = prev.xyz_mm.y_mm - vertex.xyz_mm.y_mm
        d2x = nxt.xyz_mm.x_mm - vertex.xyz_mm.x_mm
        d2y = nxt.xyz_mm.y_mm - vertex.xyz_mm.y_mm
        len1 = math.hypot(d1x, d1y)
        len2 = math.hypot(d2x, d2y)
        if len1 < 1e-9 or len2 < 1e-9:
            raise DocumentError("fillet edges are too short")
        d1x /= len1
        d1y /= len1
        d2x /= len2
        d2y /= len2
        dot = max(-1.0, min(1.0, d1x * d2x + d1y * d2y))
        phi = math.acos(dot)
        if phi < 1e-3 or phi > math.pi - 1e-3:
            raise DocumentError("fillet needs a convex corner")
        tangent = op.radius_mm / math.tan(phi / 2.0)
        if tangent >= len1 or tangent >= len2:
            raise DocumentError("fillet radius is too large for the edges")
        t1, t2 = self._offset_on_edges(prev_id, vertex_id, next_id, tangent, tangent)
        bis_x = d1x + d2x
        bis_y = d1y + d2y
        bis_len = math.hypot(bis_x, bis_y)
        if bis_len < 1e-9:
            raise DocumentError("fillet needs a convex corner")
        bis_x /= bis_len
        bis_y /= bis_len
        dist_c = op.radius_mm / math.sin(phi / 2.0)
        cx = vertex.xyz_mm.x_mm + bis_x * dist_c
        cy = vertex.xyz_mm.y_mm + bis_y * dist_c
        vx = vertex.xyz_mm.x_mm - cx
        vy = vertex.xyz_mm.y_mm - cy
        vlen = math.hypot(vx, vy)
        if vlen < 1e-9:
            raise DocumentError("fillet centre collapsed")
        mx = cx + vx / vlen * op.radius_mm
        my = cy + vy / vlen * op.radius_mm
        z_mm = vertex.xyz_mm.z_mm
        start_id, _a = self._point_at(t1[0], t1[1], t1[2], requested=op.start_id)
        mid_id, _b = self._point_at(mx, my, z_mm, requested=op.mid_id)
        end_id, _c = self._point_at(t2[0], t2[1], t2[2], requested=op.end_id)
        self._replace_corner(op.target_id, vertex_id, (start_id, mid_id, end_id))
        self._retarget_segment(prev_id, vertex_id, prev_id, start_id)
        self._retarget_segment(vertex_id, next_id, end_id, next_id)
        arc_op = self._add_arc(
            AddArc(
                start_id=start_id,
                mid_id=mid_id,
                end_id=end_id,
                entity_id=op.entity_id,
            )
        )
        return replace(
            op,
            entity_id=arc_op.entity_id,
            start_id=start_id,
            mid_id=mid_id,
            end_id=end_id,
        )

    def _sew(self, op: Sew) -> Sew:
        point_ids: list[EntityId] = []
        seen: set[EntityId] = set()
        for entity_id in op.entity_ids:
            for point_id in self._point_ids_of(self.entity(entity_id)):
                if point_id not in seen:
                    seen.add(point_id)
                    point_ids.append(point_id)
        parent = {point_id: point_id for point_id in point_ids}

        def find(point_id: EntityId) -> EntityId:
            while parent[point_id] != point_id:
                parent[point_id] = parent[parent[point_id]]
                point_id = parent[point_id]
            return point_id

        tol2 = op.tolerance_mm * op.tolerance_mm
        for index, left_id in enumerate(point_ids):
            left = self._require_point(left_id)
            for right_id in point_ids[index + 1 :]:
                right = self._require_point(right_id)
                dx = left.xyz_mm.x_mm - right.xyz_mm.x_mm
                dy = left.xyz_mm.y_mm - right.xyz_mm.y_mm
                dz = left.xyz_mm.z_mm - right.xyz_mm.z_mm
                if dx * dx + dy * dy + dz * dz <= tol2:
                    a = find(left_id)
                    b = find(right_id)
                    if a != b:
                        parent[max(a, b)] = min(a, b)
        merged = False
        for point_id in point_ids:
            keeper = find(point_id)
            if keeper != point_id:
                self._absorb_point(point_id, keeper)
                merged = True
        if not merged:
            raise DocumentError("sew found no coincident points")
        return op

    def _simplify(self, op: Simplify) -> Simplify:
        changed = False
        for entity_id in op.entity_ids:
            entity = self.entity(entity_id)
            if isinstance(entity, Face):
                simplified = self._simplify_loop(entity.point_ids, closed=True)
                if simplified != entity.point_ids:
                    self._entities[entity_id] = replace(entity, point_ids=simplified)
                    changed = True
            elif isinstance(entity, Polyline):
                simplified = self._simplify_loop(
                    entity.point_ids, closed=entity.closed
                )
                if simplified != entity.point_ids:
                    self._entities[entity_id] = replace(entity, point_ids=simplified)
                    changed = True
        if not changed:
            raise DocumentError("simplify did not remove any vertices")
        return op

    def _array_linear(self, op: ArrayLinear) -> ArrayLinear:
        for index in range(1, op.copies + 1):
            dx = op.dx_mm * index
            dy = op.dy_mm * index
            dz = op.dz_mm * index
            self._clone_graph(
                op.entity_ids,
                lambda xyz, dx=dx, dy=dy, dz=dz: XYZ(
                    xyz.x_mm + dx, xyz.y_mm + dy, xyz.z_mm + dz
                ),
            )
        return op

    def _array_polar(self, op: ArrayPolar) -> ArrayPolar:
        full_turn = abs(abs(op.angle_deg) - 360.0) < 1e-9
        step = op.angle_deg / op.count if full_turn else op.angle_deg / (op.count - 1)
        for index in range(1, op.count):
            angle = math.radians(step * index)

            def mapper(
                xyz: XYZ,
                angle: float = angle,
            ) -> XYZ:
                x_mm, y_mm = rotate_xy(
                    xyz.x_mm, xyz.y_mm, op.origin_x_mm, op.origin_y_mm, angle
                )
                return XYZ(x_mm, y_mm, xyz.z_mm)

            self._clone_graph(op.entity_ids, mapper)
        return op

    def _insert_node(self, op: InsertNode) -> InsertNode:
        target = self.entity(op.target_id)
        if isinstance(target, Line):
            return self._insert_node_on_line(op, target)
        if isinstance(target, Face):
            return self._insert_node_on_loop(op, target.point_ids, closed=True)
        if isinstance(target, Polyline):
            return self._insert_node_on_loop(op, target.point_ids, closed=target.closed)
        raise DocumentError(
            f"entity {op.target_id} cannot take a node (need a line, face, or polyline)"
        )

    def _insert_node_on_line(self, op: InsertNode, line: Line) -> InsertNode:
        start = self._require_point(line.start_id)
        end = self._require_point(line.end_id)
        qx, qy, t = project_on_segment(
            op.x_mm,
            op.y_mm,
            start.xyz_mm.x_mm,
            start.xyz_mm.y_mm,
            end.xyz_mm.x_mm,
            end.xyz_mm.y_mm,
        )
        if t <= 1e-6 or t >= 1.0 - 1e-6:
            raise DocumentError("node cannot land on a line endpoint")
        z_mm = start.xyz_mm.z_mm + t * (end.xyz_mm.z_mm - start.xyz_mm.z_mm)
        self._require_on_edge(op.x_mm, op.y_mm, qx, qy)
        node_id, _created = self._point_at(qx, qy, z_mm, requested=op.entity_id)
        if node_id in (line.start_id, line.end_id):
            raise DocumentError("node cannot land on a line endpoint")
        old_end = line.end_id
        new_line_id = self._split_line(line, node_id, op.new_line_id)
        self._splice_edge(line.start_id, old_end, node_id)
        return replace(op, entity_id=node_id, new_line_id=new_line_id)

    def _insert_node_on_loop(
        self,
        op: InsertNode,
        point_ids: tuple[EntityId, ...],
        *,
        closed: bool,
    ) -> InsertNode:
        if len(point_ids) < 2:
            raise DocumentError("loop is too short to take a node")
        pairs = [(point_ids[i], point_ids[i + 1]) for i in range(len(point_ids) - 1)]
        if closed:
            pairs.append((point_ids[-1], point_ids[0]))
        best_i = -1
        best_dist = float("inf")
        best_q = (0.0, 0.0, 0.0)
        best_pair: tuple[EntityId, EntityId] | None = None
        for index, (start_id, end_id) in enumerate(pairs):
            start = self._require_point(start_id)
            end = self._require_point(end_id)
            qx, qy, t = project_on_segment(
                op.x_mm,
                op.y_mm,
                start.xyz_mm.x_mm,
                start.xyz_mm.y_mm,
                end.xyz_mm.x_mm,
                end.xyz_mm.y_mm,
            )
            if t <= 1e-6 or t >= 1.0 - 1e-6:
                continue
            dist = (qx - op.x_mm) ** 2 + (qy - op.y_mm) ** 2
            if dist < best_dist:
                best_dist = dist
                best_i = index
                z_mm = start.xyz_mm.z_mm + t * (end.xyz_mm.z_mm - start.xyz_mm.z_mm)
                best_q = (qx, qy, z_mm)
                best_pair = (start_id, end_id)
        if best_i < 0 or best_pair is None:
            raise DocumentError("click is not on an edge of the loop")
        self._require_on_edge(op.x_mm, op.y_mm, best_q[0], best_q[1])
        node_id, _created = self._point_at(
            best_q[0], best_q[1], best_q[2], requested=op.entity_id
        )
        if node_id in point_ids:
            raise DocumentError("node is already a vertex of the loop")
        ids = list(point_ids)
        ids.insert(best_i + 1, node_id)
        entity = self.entity(op.target_id)
        if isinstance(entity, Face):
            self._entities[entity.entity_id] = replace(entity, point_ids=tuple(ids))
        elif isinstance(entity, Polyline):
            self._entities[entity.entity_id] = replace(entity, point_ids=tuple(ids))
        new_line_id = self._split_line_between(
            best_pair[0], best_pair[1], node_id, op.new_line_id
        )
        self._splice_edge(best_pair[0], best_pair[1], node_id)
        return replace(op, entity_id=node_id, new_line_id=new_line_id)

    def _trim_line(self, op: TrimLine) -> TrimLine:
        line = self.entity(op.line_id)
        if not isinstance(line, Line):
            raise DocumentError(f"entity {op.line_id} is not a line")
        if op.keep_id not in (line.start_id, line.end_id):
            raise DocumentError("keep_id must be an endpoint of the trimmed line")
        cut_id, _created = self._point_at(op.x_mm, op.y_mm, op.z_mm, requested=op.entity_id)
        if op.keep_id == line.start_id:
            if cut_id == line.start_id:
                raise DocumentError("trim collapsed the line to a point")
            self._entities[line.entity_id] = replace(line, end_id=cut_id)
        else:
            if cut_id == line.end_id:
                raise DocumentError("trim collapsed the line to a point")
            self._entities[line.entity_id] = replace(line, start_id=cut_id)
        return replace(op, entity_id=cut_id)

    def _break_crossing(self, op: BreakCrossing) -> BreakCrossing:
        line_a = self.entity(op.line_a_id)
        line_b = self.entity(op.line_b_id)
        if not isinstance(line_a, Line) or not isinstance(line_b, Line):
            raise DocumentError("break needs two lines")
        a1 = self._require_point(line_a.start_id)
        a2 = self._require_point(line_a.end_id)
        b1 = self._require_point(line_b.start_id)
        b2 = self._require_point(line_b.end_id)
        hit = line_intersect_xy(a1.xyz_mm, a2.xyz_mm, b1.xyz_mm, b2.xyz_mm)
        if hit is None:
            raise DocumentError("those lines are parallel")
        point, t, u = hit
        if t <= 1e-6 or t >= 1.0 - 1e-6 or u <= 1e-6 or u >= 1.0 - 1e-6:
            raise DocumentError("lines do not cross")
        first = self._insert_node_on_line(
            InsertNode(
                target_id=op.line_a_id,
                x_mm=point.x_mm,
                y_mm=point.y_mm,
                z_mm=0.0,
                entity_id=op.entity_id,
                new_line_id=op.new_line_a_id,
            ),
            line_a,
        )
        line_b_now = self.entity(op.line_b_id)
        if not isinstance(line_b_now, Line):
            raise DocumentError("internal error: second line vanished")
        second = self._insert_node_on_line(
            InsertNode(
                target_id=op.line_b_id,
                x_mm=point.x_mm,
                y_mm=point.y_mm,
                z_mm=0.0,
                entity_id=first.entity_id,
                new_line_id=op.new_line_b_id,
            ),
            line_b_now,
        )
        return replace(
            op,
            entity_id=first.entity_id,
            new_line_a_id=first.new_line_id,
            new_line_b_id=second.new_line_id,
        )

    def _add_face_from_lines(self, op: AddFaceFromLines) -> AddFaceFromLines:
        lines: list[Line] = []
        for line_id in op.line_ids:
            entity = self.entity(line_id)
            if not isinstance(entity, Line):
                raise DocumentError(f"entity {line_id} is not a line")
            lines.append(entity)
        loop = _loop_from_lines(lines)
        face_op = self._add_face(AddFace(point_ids=loop, label=op.label, entity_id=op.entity_id))
        return replace(op, entity_id=face_op.entity_id)

    def _join_polyline(self, op: JoinPolyline) -> JoinPolyline:
        segments: list[tuple[EntityId, EntityId]] = []
        consumed: list[EntityId] = []
        for entity_id in op.entity_ids:
            entity = self.entity(entity_id)
            if isinstance(entity, Line):
                segments.append((entity.start_id, entity.end_id))
            elif isinstance(entity, Polyline):
                ids = entity.point_ids
                for index in range(len(ids) - 1):
                    segments.append((ids[index], ids[index + 1]))
                if entity.closed:
                    segments.append((ids[-1], ids[0]))
            else:
                raise DocumentError(
                    f"entity {entity_id} is not a line or polyline"
                )
            consumed.append(entity_id)
        point_ids, closed = _chain_from_segments(segments)
        inherited: list[str] = []
        for entity_id in consumed:
            source = self._entities[entity_id]
            if source.label is not None:
                inherited.append(source.label)
        label = op.label if op.label is not None else (
            inherited[0] if len(inherited) == 1 else None
        )
        owner = self._labels.get(label) if label is not None else None
        if owner is not None and owner not in consumed:
            raise DocumentError(f"label {label!r} already belongs to entity {owner}")
        for entity_id in consumed:
            self._drop_entity(entity_id)
        entity_id = self._allocate_id(op.entity_id)
        self._register_label(entity_id, label)
        self._entities[entity_id] = Polyline(
            entity_id=entity_id,
            point_ids=point_ids,
            closed=closed,
            label=label,
        )
        return replace(op, entity_id=entity_id, label=label)

    def _point_at(
        self,
        x_mm: float,
        y_mm: float,
        z_mm: float,
        *,
        requested: EntityId | None,
        tolerance_mm: float = 1.0,
    ) -> tuple[EntityId, bool]:
        for point in self.points():
            dx = point.xyz_mm.x_mm - x_mm
            dy = point.xyz_mm.y_mm - y_mm
            dz = point.xyz_mm.z_mm - z_mm
            if dx * dx + dy * dy + dz * dz <= tolerance_mm * tolerance_mm:
                return point.entity_id, False
        entity_id = self._allocate_id(requested)
        self._entities[entity_id] = Point(
            entity_id=entity_id,
            xyz_mm=XYZ(x_mm, y_mm, z_mm),
            label=None,
        )
        return entity_id, True

    def _point_ids_of(self, entity: Entity) -> tuple[EntityId, ...]:
        if isinstance(entity, Point):
            return (entity.entity_id,)
        if isinstance(entity, Line):
            return (entity.start_id, entity.end_id)
        if isinstance(entity, (Polyline, Face, Bezier)):
            return entity.point_ids
        if isinstance(entity, (Circle, Ellipse)):
            return (entity.center_id,)
        if isinstance(entity, Arc):
            return (entity.start_id, entity.mid_id, entity.end_id)
        if isinstance(entity, Solid):
            return self._point_ids_of(self.entity(entity.face_id))
        return ()

    def _require_on_edge(self, px: float, py: float, qx: float, qy: float) -> None:
        dx = qx - px
        dy = qy - py
        if dx * dx + dy * dy > _EDGE_HIT_MM * _EDGE_HIT_MM:
            raise DocumentError("click is not on an edge")

    def _split_line(
        self, line: Line, node_id: EntityId, requested: EntityId | None
    ) -> EntityId:
        old_end = line.end_id
        self._entities[line.entity_id] = replace(line, end_id=node_id)
        new_line_id = self._allocate_id(requested)
        self._entities[new_line_id] = Line(
            entity_id=new_line_id,
            start_id=node_id,
            end_id=old_end,
            label=None,
        )
        return new_line_id

    def _split_line_between(
        self,
        start_id: EntityId,
        end_id: EntityId,
        node_id: EntityId,
        requested: EntityId | None,
    ) -> EntityId | None:
        for entity in list(self._entities.values()):
            if not isinstance(entity, Line):
                continue
            if {entity.start_id, entity.end_id} != {start_id, end_id}:
                continue
            return self._split_line(entity, node_id, requested)
        return None

    def _splice_edge(self, start_id: EntityId, end_id: EntityId, node_id: EntityId) -> None:
        for entity in list(self._entities.values()):
            if isinstance(entity, Face):
                spliced = _insert_on_ring(
                    entity.point_ids, start_id, end_id, node_id, closed=True
                )
            elif isinstance(entity, Polyline):
                spliced = _insert_on_ring(
                    entity.point_ids, start_id, end_id, node_id, closed=entity.closed
                )
            else:
                continue
            if spliced is not None:
                self._entities[entity.entity_id] = replace(entity, point_ids=spliced)

    def _corner_of(
        self, target_id: EntityId, vertex_id: EntityId
    ) -> tuple[EntityId, EntityId, EntityId]:
        target = self.entity(target_id)
        if isinstance(target, Face):
            ids = target.point_ids
            closed = True
        elif isinstance(target, Polyline):
            ids = target.point_ids
            closed = target.closed
        else:
            raise DocumentError(
                f"entity {target_id} cannot take a corner (need a face or polyline)"
            )
        try:
            index = ids.index(vertex_id)
        except ValueError as exc:
            raise DocumentError(
                f"vertex {vertex_id} is not on entity {target_id}"
            ) from exc
        if not closed and (index == 0 or index == len(ids) - 1):
            raise DocumentError("cannot chamfer or fillet an open polyline end")
        prev_id = ids[index - 1]
        next_id = ids[(index + 1) % len(ids)]
        return prev_id, vertex_id, next_id

    def _offset_on_edges(
        self,
        prev_id: EntityId,
        vertex_id: EntityId,
        next_id: EntityId,
        distance_prev: float,
        distance_next: float,
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        prev = self._require_point(prev_id)
        vertex = self._require_point(vertex_id)
        nxt = self._require_point(next_id)
        d1x = prev.xyz_mm.x_mm - vertex.xyz_mm.x_mm
        d1y = prev.xyz_mm.y_mm - vertex.xyz_mm.y_mm
        d2x = nxt.xyz_mm.x_mm - vertex.xyz_mm.x_mm
        d2y = nxt.xyz_mm.y_mm - vertex.xyz_mm.y_mm
        len1 = math.hypot(d1x, d1y)
        len2 = math.hypot(d2x, d2y)
        if distance_prev >= len1 or distance_next >= len2:
            raise DocumentError("distance is too large for the corner edges")
        t1 = (
            vertex.xyz_mm.x_mm + d1x / len1 * distance_prev,
            vertex.xyz_mm.y_mm + d1y / len1 * distance_prev,
            vertex.xyz_mm.z_mm,
        )
        t2 = (
            vertex.xyz_mm.x_mm + d2x / len2 * distance_next,
            vertex.xyz_mm.y_mm + d2y / len2 * distance_next,
            vertex.xyz_mm.z_mm,
        )
        return t1, t2

    def _replace_corner(
        self,
        target_id: EntityId,
        vertex_id: EntityId,
        new_ids: tuple[EntityId, ...],
    ) -> None:
        entity = self.entity(target_id)
        if not isinstance(entity, (Face, Polyline)):
            raise DocumentError(f"entity {target_id} is not a face or polyline")
        ids = list(entity.point_ids)
        index = ids.index(vertex_id)
        ids[index : index + 1] = list(new_ids)
        if len(set(ids)) != len(ids):
            raise DocumentError("corner replacement produced duplicate vertices")
        self._entities[target_id] = replace(entity, point_ids=tuple(ids))

    def _retarget_segment(
        self,
        old_start: EntityId,
        old_end: EntityId,
        new_start: EntityId,
        new_end: EntityId,
    ) -> None:
        for entity in list(self._entities.values()):
            if not isinstance(entity, Line):
                continue
            if {entity.start_id, entity.end_id} != {old_start, old_end}:
                continue
            start_id = new_start if entity.start_id == old_start else new_end
            end_id = new_end if entity.end_id == old_end else new_start
            if entity.start_id == old_end and entity.end_id == old_start:
                start_id = new_end
                end_id = new_start
            if start_id == end_id:
                continue
            self._entities[entity.entity_id] = replace(
                entity, start_id=start_id, end_id=end_id
            )

    def _absorb_point(self, old_id: EntityId, new_id: EntityId) -> None:
        if old_id == new_id:
            return
        for entity in list(self._entities.values()):
            if isinstance(entity, Line):
                start_id = new_id if entity.start_id == old_id else entity.start_id
                end_id = new_id if entity.end_id == old_id else entity.end_id
                if start_id == end_id:
                    del self._entities[entity.entity_id]
                elif (start_id, end_id) != (entity.start_id, entity.end_id):
                    self._entities[entity.entity_id] = replace(
                        entity, start_id=start_id, end_id=end_id
                    )
            elif isinstance(entity, (Face, Polyline, Bezier)):
                ids = tuple(
                    new_id if point_id == old_id else point_id
                    for point_id in entity.point_ids
                )
                compacted = _compact_ids(
                    ids, closed=isinstance(entity, Face) or (
                        isinstance(entity, Polyline) and entity.closed
                    ),
                )
                if isinstance(entity, Face) and len(compacted) < 3:
                    raise DocumentError("sew would collapse a face")
                if isinstance(entity, Polyline) and len(compacted) < 2:
                    raise DocumentError("sew would collapse a polyline")
                if isinstance(entity, Bezier) and len(compacted) != 4:
                    raise DocumentError("sew would collapse a Bézier")
                if compacted != entity.point_ids:
                    self._entities[entity.entity_id] = replace(entity, point_ids=compacted)
            elif isinstance(entity, (Circle, Ellipse)) and entity.center_id == old_id:
                self._entities[entity.entity_id] = replace(entity, center_id=new_id)
            elif isinstance(entity, Arc):
                start_id = new_id if entity.start_id == old_id else entity.start_id
                mid_id = new_id if entity.mid_id == old_id else entity.mid_id
                end_id = new_id if entity.end_id == old_id else entity.end_id
                self._entities[entity.entity_id] = replace(
                    entity, start_id=start_id, mid_id=mid_id, end_id=end_id
                )
        old = self._entities.pop(old_id)
        if isinstance(old, Point) and old.label is not None:
            keeper = self.entity(new_id)
            if isinstance(keeper, Point) and keeper.label is None:
                self._entities[new_id] = replace(keeper, label=old.label)
                self._labels[old.label] = new_id
            elif old.label in self._labels:
                del self._labels[old.label]

    def _simplify_loop(
        self, point_ids: tuple[EntityId, ...], *, closed: bool
    ) -> tuple[EntityId, ...]:
        ids = list(point_ids)
        minimum = 3 if closed else 2
        changed = True
        while changed and len(ids) > minimum:
            changed = False
            count = len(ids)
            last = count if closed else count - 1
            start = 0 if closed else 1
            for index in range(start, last):
                prev_id = ids[index - 1]
                vertex_id = ids[index]
                next_id = ids[(index + 1) % count]
                if self._vertex_is_shared(vertex_id, point_ids):
                    continue
                prev = self._require_point(prev_id)
                vertex = self._require_point(vertex_id)
                nxt = self._require_point(next_id)
                if collinear_xy(
                    prev.xyz_mm.x_mm,
                    prev.xyz_mm.y_mm,
                    vertex.xyz_mm.x_mm,
                    vertex.xyz_mm.y_mm,
                    nxt.xyz_mm.x_mm,
                    nxt.xyz_mm.y_mm,
                ):
                    ids.pop(index)
                    changed = True
                    break
        if len(ids) < minimum:
            raise DocumentError("simplify would collapse the loop")
        return tuple(ids)

    def _vertex_is_shared(
        self, vertex_id: EntityId, owner_ids: tuple[EntityId, ...]
    ) -> bool:
        for entity in self._entities.values():
            if isinstance(entity, (Face, Polyline)) and entity.point_ids != owner_ids:
                if vertex_id in entity.point_ids:
                    return True
            if isinstance(entity, Line) and vertex_id in (entity.start_id, entity.end_id):
                other = entity.end_id if entity.start_id == vertex_id else entity.start_id
                if other not in owner_ids:
                    return True
        return False

    def _clone_graph(
        self,
        entity_ids: tuple[EntityId, ...],
        mapper: Callable[[XYZ], XYZ],
    ) -> None:
        extras: list[EntityId] = []
        for entity_id in entity_ids:
            entity = self.entity(entity_id)
            if isinstance(entity, Solid) and entity.face_id not in entity_ids:
                extras.append(entity.face_id)
        ordered = list(dict.fromkeys([*extras, *entity_ids]))
        non_solids = [
            entity_id
            for entity_id in ordered
            if not isinstance(self.entity(entity_id), Solid)
        ]
        solids = [
            entity_id
            for entity_id in ordered
            if isinstance(self.entity(entity_id), Solid)
        ]
        point_map: dict[EntityId, EntityId] = {}
        entity_map: dict[EntityId, EntityId] = {}

        def mapped_point(point_id: EntityId) -> EntityId:
            existing = point_map.get(point_id)
            if existing is not None:
                return existing
            point = self._require_point(point_id)
            new_id = self._allocate_id(None)
            self._entities[new_id] = Point(
                entity_id=new_id,
                xyz_mm=mapper(point.xyz_mm),
                label=None,
            )
            point_map[point_id] = new_id
            return new_id

        for entity_id in non_solids + solids:
            entity = self.entity(entity_id)
            if isinstance(entity, Point):
                mapped_point(entity.entity_id)
                continue
            new_id = self._allocate_id(None)
            entity_map[entity_id] = new_id
            if isinstance(entity, Line):
                self._entities[new_id] = Line(
                    entity_id=new_id,
                    start_id=mapped_point(entity.start_id),
                    end_id=mapped_point(entity.end_id),
                    label=None,
                )
            elif isinstance(entity, Polyline):
                self._entities[new_id] = Polyline(
                    entity_id=new_id,
                    point_ids=tuple(mapped_point(pid) for pid in entity.point_ids),
                    closed=entity.closed,
                    label=None,
                )
            elif isinstance(entity, Face):
                self._entities[new_id] = Face(
                    entity_id=new_id,
                    point_ids=tuple(mapped_point(pid) for pid in entity.point_ids),
                    label=None,
                )
            elif isinstance(entity, Box):
                self._entities[new_id] = Box(
                    entity_id=new_id,
                    origin_xyz_mm=mapper(entity.origin_xyz_mm),
                    size_xyz_mm=entity.size_xyz_mm,
                    label=None,
                )
            elif isinstance(entity, Circle):
                self._entities[new_id] = Circle(
                    entity_id=new_id,
                    center_id=mapped_point(entity.center_id),
                    radius_mm=entity.radius_mm,
                    label=None,
                )
            elif isinstance(entity, Ellipse):
                self._entities[new_id] = Ellipse(
                    entity_id=new_id,
                    center_id=mapped_point(entity.center_id),
                    radius_x_mm=entity.radius_x_mm,
                    radius_y_mm=entity.radius_y_mm,
                    label=None,
                )
            elif isinstance(entity, Arc):
                self._entities[new_id] = Arc(
                    entity_id=new_id,
                    start_id=mapped_point(entity.start_id),
                    mid_id=mapped_point(entity.mid_id),
                    end_id=mapped_point(entity.end_id),
                    label=None,
                )
            elif isinstance(entity, Bezier):
                self._entities[new_id] = Bezier(
                    entity_id=new_id,
                    point_ids=tuple(mapped_point(pid) for pid in entity.point_ids),
                    label=None,
                )
            else:
                assert isinstance(entity, Solid)
                profile_id = entity_map.get(entity.face_id)
                if profile_id is None:
                    raise DocumentError(
                        "polar/linear array could not clone the solid profile"
                    )
                self._entities[new_id] = Solid(
                    entity_id=new_id,
                    face_id=profile_id,
                    distance_mm=entity.distance_mm,
                    direction_xyz=entity.direction_xyz,
                    label=None,
                )

    def _delete(self, op: Delete) -> Delete:
        for entity_id in op.entity_ids:
            if entity_id not in self._entities:
                raise DocumentError(f"unknown entity id {entity_id}")
        doomed: set[EntityId] = set(op.entity_ids)
        changed = True
        while changed:
            changed = False
            for entity in self._entities.values():
                if entity.entity_id in doomed:
                    continue
                if doomed.intersection(_referenced_ids(entity)):
                    doomed.add(entity.entity_id)
                    changed = True
        attached: set[EntityId] = set()
        for entity_id in doomed:
            attached.update(_referenced_ids(self._entities[entity_id]))
        for entity_id in list(doomed):
            self._drop_entity(entity_id)
        still_used: set[EntityId] = set()
        for entity in self._entities.values():
            still_used.update(_referenced_ids(entity))
        for point_id in attached:
            leftover = self._entities.get(point_id)
            if isinstance(leftover, Point) and point_id not in still_used:
                self._drop_entity(point_id)
        return op

    def _drop_entity(self, entity_id: EntityId) -> None:
        entity = self._entities.pop(entity_id)
        if entity.label is not None:
            self._labels.pop(entity.label, None)
        empty_tags: list[str] = []
        for name, members in self._tags.items():
            members.discard(entity_id)
            if not members:
                empty_tags.append(name)
        for name in empty_tags:
            del self._tags[name]

    def _tag(self, op: Tag) -> Tag:
        for entity_id in op.entity_ids:
            if entity_id not in self._entities:
                raise DocumentError(f"cannot tag unknown entity id {entity_id}")
        members = self._tags.setdefault(op.name, set())
        members.update(op.entity_ids)
        return op

    def _allocate_id(self, requested: EntityId | None) -> EntityId:
        if requested is None:
            entity_id = self._next_id
            self._next_id += 1
            return entity_id
        if requested < 1:
            raise DocumentError(f"entity_id must be positive, got {requested}")
        if requested in self._entities:
            raise DocumentError(f"entity id {requested} already exists")
        if requested >= self._next_id:
            self._next_id = requested + 1
        return requested

    def _register_label(self, entity_id: EntityId, label: str | None) -> None:
        if label is None:
            return
        existing = self._labels.get(label)
        if existing is not None:
            raise DocumentError(f"label {label!r} already belongs to entity {existing}")
        self._labels[label] = entity_id

    def _reject_taken_label(self, label: str | None) -> None:
        if label is None:
            return
        existing = self._labels.get(label)
        if existing is not None:
            raise DocumentError(f"label {label!r} already belongs to entity {existing}")

    def _require_point(self, entity_id: EntityId) -> Point:
        entity = self._entities.get(entity_id)
        if not isinstance(entity, Point):
            raise DocumentError(f"entity {entity_id} is not a point")
        return entity

    def _rebuild(self) -> None:
        ops = list(self._ops)
        self._ops = []
        self._next_id = 1
        self._entities = {}
        self._labels = {}
        self._tags = {}
        for op in ops:
            self._dispatch(op)
            self._ops.append(op)


def _referenced_ids(entity: Entity) -> frozenset[EntityId]:
    if isinstance(entity, Point):
        return frozenset()
    if isinstance(entity, Line):
        return frozenset({entity.start_id, entity.end_id})
    if isinstance(entity, (Polyline, Face, Bezier)):
        return frozenset(entity.point_ids)
    if isinstance(entity, Box):
        return frozenset()
    if isinstance(entity, Solid):
        return frozenset({entity.face_id})
    if isinstance(entity, (Circle, Ellipse)):
        return frozenset({entity.center_id})
    return frozenset({entity.start_id, entity.mid_id, entity.end_id})


def _as_string_dict(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise DocumentError(f"each op must be an object, got {payload!r}")
    source = cast(dict[object, object], payload)
    typed: dict[str, object] = {}
    for raw_key, raw_value in source.items():
        if not isinstance(raw_key, str):
            raise DocumentError(f"op keys must be strings, got {raw_key!r}")
        typed[raw_key] = raw_value
    return typed


def _entity_id_of(
    op: AddPoint
    | AddLine
    | AddPolyline
    | AddBox
    | AddFace
    | Extrude
    | AddCircle
    | AddArc
    | AddEllipse
    | AddBezier
    | InsertNode
    | TrimLine
    | BreakCrossing
    | AddFaceFromLines
    | JoinPolyline
    | ChamferCorner
    | FilletCorner,
) -> EntityId:
    if op.entity_id is None:
        raise DocumentError("internal error: committed op is missing entity_id")
    return op.entity_id


_EDGE_HIT_MM = 400.0


def _insert_on_ring(
    point_ids: tuple[EntityId, ...],
    start_id: EntityId,
    end_id: EntityId,
    node_id: EntityId,
    *,
    closed: bool,
) -> tuple[EntityId, ...] | None:
    if node_id in point_ids:
        return None
    ids = list(point_ids)
    last = len(ids) if closed else len(ids) - 1
    for index in range(last):
        a = ids[index]
        b = ids[(index + 1) % len(ids)]
        if (a, b) == (start_id, end_id) or (a, b) == (end_id, start_id):
            ids.insert(index + 1, node_id)
            return tuple(ids)
    return None


def _loop_from_lines(lines: list[Line]) -> tuple[EntityId, ...]:
    if len(lines) < 3:
        raise DocumentError("face from lines needs at least three lines")
    adj: dict[EntityId, list[EntityId]] = {}
    for line in lines:
        adj.setdefault(line.start_id, []).append(line.end_id)
        adj.setdefault(line.end_id, []).append(line.start_id)
    for neighbors in adj.values():
        if len(neighbors) != 2:
            raise DocumentError("selected lines must form one closed loop")
    start = lines[0].start_id
    loop: list[EntityId] = [start]
    prev: EntityId | None = None
    current = start
    for _ in range(len(lines)):
        neighbors = adj[current]
        nxt = neighbors[0] if neighbors[0] != prev else neighbors[1]
        if nxt == start:
            break
        loop.append(nxt)
        prev = current
        current = nxt
    else:
        raise DocumentError("selected lines must form one closed loop")
    if len(loop) != len(lines):
        raise DocumentError("selected lines must form one closed loop")
    return tuple(loop)


def _chain_from_segments(
    segments: list[tuple[EntityId, EntityId]],
) -> tuple[tuple[EntityId, ...], bool]:
    if len(segments) < 2:
        raise DocumentError("join needs at least two segments")
    adj: dict[EntityId, list[EntityId]] = {}
    seen: set[frozenset[EntityId]] = set()
    for start_id, end_id in segments:
        if start_id == end_id:
            raise DocumentError("join cannot use a zero-length segment")
        edge = frozenset((start_id, end_id))
        if edge in seen:
            raise DocumentError("join found a duplicated segment")
        seen.add(edge)
        adj.setdefault(start_id, []).append(end_id)
        adj.setdefault(end_id, []).append(start_id)
    if any(len(neighbors) > 2 for neighbors in adj.values()):
        raise DocumentError("join needs a single chain (a branch was selected)")
    ends = [node for node, neighbors in adj.items() if len(neighbors) == 1]
    if len(ends) == 2:
        closed = False
        start = ends[0]
    elif len(ends) == 0:
        if any(len(neighbors) != 2 for neighbors in adj.values()):
            raise DocumentError("selected entities are not one connected chain")
        closed = True
        start = segments[0][0]
    else:
        raise DocumentError("selected entities are not one connected chain")
    chain: list[EntityId] = [start]
    prev: EntityId | None = None
    current = start
    for _ in range(len(segments)):
        nxt: EntityId | None = None
        for candidate in adj[current]:
            if candidate != prev:
                nxt = candidate
                break
        if nxt is None:
            break
        if closed and nxt == start:
            break
        chain.append(nxt)
        prev = current
        current = nxt
    if closed:
        if len(chain) != len(segments):
            raise DocumentError("selected entities are not one connected chain")
    elif len(chain) != len(segments) + 1:
        raise DocumentError("selected entities are not one connected chain")
    return tuple(chain), closed


def _compact_ids(
    point_ids: tuple[EntityId, ...], *, closed: bool
) -> tuple[EntityId, ...]:
    if not point_ids:
        return point_ids
    compacted: list[EntityId] = [point_ids[0]]
    for point_id in point_ids[1:]:
        if point_id != compacted[-1]:
            compacted.append(point_id)
    if closed and len(compacted) > 1 and compacted[0] == compacted[-1]:
        compacted.pop()
    return tuple(compacted)
