"""Kernel-free spatial draft. The ops log is the only writer."""

from __future__ import annotations

import json
from typing import TypeVar, cast

from apeCAD.brep import BrepIndex, build_brep
from apeCAD.draft.dispatch import apply_op
from apeCAD.draft.invariants import check_state
from apeCAD.draft.state import DraftState, produced_id
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
from apeCAD.geometry import XYZ
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
    SetLabel,
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
        self._state = DraftState()

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

    def set_label(self, entity_id: EntityId, label: str | None) -> None:
        self._apply(SetLabel(entity_id=entity_id, label=label))

    def undo(self) -> None:
        if not self._ops:
            raise DocumentError("nothing to undo")
        self._redo.append(self._ops.pop())
        self._rebuild()

    def redo(self) -> None:
        if not self._redo:
            raise DocumentError("nothing to redo")
        self._apply(self._redo[-1], from_redo=True)

    def entity(self, entity_id: EntityId) -> Entity:
        return self._state.entity(entity_id)

    def entity_by_label(self, label: str) -> Entity:
        try:
            entity_id = self._state.labels[label]
        except KeyError as exc:
            raise DocumentError(f"unknown label {label!r}") from exc
        return self._state.entities[entity_id]

    def points(self) -> tuple[Point, ...]:
        return tuple(e for e in self._state.ordered() if isinstance(e, Point))

    def lines(self) -> tuple[Line, ...]:
        return tuple(e for e in self._state.ordered() if isinstance(e, Line))

    def polylines(self) -> tuple[Polyline, ...]:
        return tuple(e for e in self._state.ordered() if isinstance(e, Polyline))

    def boxes(self) -> tuple[Box, ...]:
        return tuple(e for e in self._state.ordered() if isinstance(e, Box))

    def faces(self) -> tuple[Face, ...]:
        return tuple(e for e in self._state.ordered() if isinstance(e, Face))

    def solids(self) -> tuple[Solid, ...]:
        return tuple(e for e in self._state.ordered() if isinstance(e, Solid))

    def circles(self) -> tuple[Circle, ...]:
        return tuple(e for e in self._state.ordered() if isinstance(e, Circle))

    def arcs(self) -> tuple[Arc, ...]:
        return tuple(e for e in self._state.ordered() if isinstance(e, Arc))

    def ellipses(self) -> tuple[Ellipse, ...]:
        return tuple(e for e in self._state.ordered() if isinstance(e, Ellipse))

    def beziers(self) -> tuple[Bezier, ...]:
        return tuple(e for e in self._state.ordered() if isinstance(e, Bezier))

    def brep(self) -> BrepIndex:
        """Evaluated vertex/edge/face/solid graph (ADR 0018)."""
        return build_brep(self._state.entities)

    def tags(self) -> dict[str, frozenset[EntityId]]:
        return {name: frozenset(ids) for name, ids in sorted(self._state.tags.items())}

    def tagged(self, name: str) -> frozenset[EntityId]:
        return frozenset(self._state.tags.get(name, set()))

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
        ops = [op_from_dict(_as_string_dict(raw)) for raw in cast(list[object], raw_ops)]
        document._replay(ops)
        return document

    @classmethod
    def from_json(cls, text: str) -> Document:
        parsed: object = json.loads(text)
        return cls.from_dict(_as_string_dict(parsed))


    def _apply(self, op: Op, *, from_redo: bool = False) -> Entity | None:
        """Run the op on a trial copy; commit only if it succeeds and passes the guard."""
        trial = self._state.copy()
        committed = _run(trial, op)
        check_state(self._state, trial)
        self._state = trial
        self._ops.append(committed)
        if from_redo:
            self._redo.pop()
        else:
            self._redo.clear()
        if isinstance(committed, _NO_PRODUCT):
            return None
        return self._state.entities[produced_id(committed)]

    def _rebuild(self) -> None:
        self._replay(list(self._ops))

    def _replay(self, ops: list[Op]) -> None:
        """Rebuild from a whole log into a fresh state; one guard at the end keeps it linear."""
        fresh = DraftState()
        committed = [_run(fresh, op) for op in ops]
        check_state(DraftState(), fresh)
        self._state = fresh
        self._ops = committed


def _run(state: DraftState, op: Op) -> Op:
    try:
        return apply_op(state, op)
    except ArithmeticError as exc:  # float overflow is a refusal, not a crash
        raise DocumentError(f"{type(op).__name__} is out of range: {exc}") from exc


_NO_PRODUCT = (
    Tag,
    Translate,
    Rotate,
    Mirror,
    Sew,
    Simplify,
    ArrayLinear,
    ArrayPolar,
    Delete,
    SetLabel,
)
"""Ops that change the draft without producing one entity to return."""


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
