"""Kernel-free spatial draft. The ops log is the only writer."""

from __future__ import annotations

import json
from typing import cast

from apeCAD.brep import BrepIndex, build_brep
from apeCAD.draft.dispatch import apply_op
from apeCAD.draft.invariants import check_state
from apeCAD.draft.state import DraftState, produced_id
from apeCAD.entities import (
    Arc,
    Bar,
    Bezier,
    Box,
    Circle,
    ConcreteFace,
    Crosstie,
    Ellipse,
    Entity,
    EntityId,
    Face,
    Hoop,
    Line,
    Point,
    Polyline,
    Solid,
)
from apeCAD.errors import DocumentError
from apeCAD.frame import FrameGraph, document_to_frame
from apeCAD.ops import (
    SCHEMA_ID,
    SUPPORTED_SCHEMA_IDS,
    UNITS,
    AddLineChain,
    ArrayLinear,
    ArrayPolar,
    Delete,
    Mirror,
    Op,
    Rotate,
    SetBarSize,
    SetLabel,
    SetMaterial,
    SetTransverse,
    Sew,
    Simplify,
    Tag,
    Translate,
    op_from_dict,
    op_to_dict,
)
from apeCAD.typed_section_ops import SectionTypedOps


class Document(SectionTypedOps):
    """In-memory scratchpad. Mutate only through ops; JSON replays the log."""

    def __init__(self) -> None:
        self._ops: list[Op] = []
        self._redo: list[Op] = []
        self._state = DraftState()

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

    def entity_ids(self) -> frozenset[EntityId]:
        return frozenset(self._state.entities)

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

    def concrete_faces(self) -> tuple[ConcreteFace, ...]:
        return tuple(e for e in self._state.ordered() if isinstance(e, ConcreteFace))

    def bars(self) -> tuple[Bar, ...]:
        return tuple(e for e in self._state.ordered() if isinstance(e, Bar))

    def hoops(self) -> tuple[Hoop, ...]:
        return tuple(e for e in self._state.ordered() if isinstance(e, Hoop))

    def crossties(self) -> tuple[Crosstie, ...]:
        return tuple(e for e in self._state.ordered() if isinstance(e, Crosstie))

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
        if schema not in SUPPORTED_SCHEMA_IDS:
            raise DocumentError(
                f"unsupported schema {schema!r}, expected one of {SUPPORTED_SCHEMA_IDS!r}"
            )
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
    AddLineChain,
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
    SetBarSize,
    SetMaterial,
    SetTransverse,
)
"""Ops that change the draft without producing exactly one entity to return."""


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
