"""Typed readers and writers for op field values, shared by the op codecs."""

from __future__ import annotations

from typing import cast

from apeCAD.entities import EntityId
from apeCAD.errors import DocumentError
from apeCAD.geometry import XYZ, require_finite
from apeCAD.ops.base import PointAt, VertexRef


def as_int(name: str, value: object) -> int:
    if isinstance(value, bool):
        raise DocumentError(f"{name} must be an integer, got {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    raise DocumentError(f"{name} must be an integer, got {value!r}")


def as_float(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DocumentError(f"{name} must be a number, got {value!r}")
    return require_finite(name, float(value))


def as_str(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise DocumentError(f"{name} must be a string, got {value!r}")
    return value


def as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise DocumentError(f"label must be a string or null, got {value!r}")
    return value


def as_entity_id(name: str, value: object) -> EntityId:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DocumentError(f"{name} must be an integer entity id, got {value!r}")
    if value < 1:
        raise DocumentError(f"{name} must be a positive entity id, got {value!r}")
    return value


def as_optional_entity_id(value: object) -> EntityId | None:
    if value is None:
        return None
    return as_entity_id("entity_id", value)


def as_id_tuple(name: str, value: object) -> tuple[EntityId, ...]:
    if not isinstance(value, list):
        raise DocumentError(f"{name} must be a list of entity ids, got {value!r}")
    items = cast(list[object], value)
    return tuple(as_entity_id(name, item) for item in items)


def as_xyz(name: str, value: object) -> XYZ:
    if not isinstance(value, list):
        raise DocumentError(f"{name} must be a list of three millimetre components, got {value!r}")
    coords = cast(list[object], value)
    if len(coords) != 3:
        raise DocumentError(f"{name} must be a list of three millimetre components, got {value!r}")
    return XYZ(
        as_float(f"{name}[0]", coords[0]),
        as_float(f"{name}[1]", coords[1]),
        as_float(f"{name}[2]", coords[2]),
    )


def vertex_json(ref: VertexRef) -> object:
    """A point id stays a plain int, as in v0; coordinates become {"xyz": [...], "id": n}."""
    if not isinstance(ref, PointAt):
        return ref
    out: dict[str, object] = {"xyz": list(ref.xyz_mm.to_tuple())}
    if ref.entity_id is not None:
        out["id"] = ref.entity_id
    return out


def vertices_json(refs: tuple[VertexRef, ...]) -> list[object]:
    return [vertex_json(ref) for ref in refs]


def as_vertex(name: str, value: object) -> VertexRef:
    """An int or {"id": n} names a point; {"xyz": [...]} gives coordinates (ADR 0030)."""
    if not isinstance(value, dict):
        return as_entity_id(name, value)
    ref = cast(dict[object, object], value)
    if not ref or set(ref) - {"id", "xyz"}:
        raise DocumentError(f"{name} must be an id, {{id: n}}, or {{xyz: [x, y, z]}}")
    raw_id = ref.get("id")
    entity_id = None if raw_id is None else as_entity_id(name, raw_id)
    if "xyz" not in ref:
        if entity_id is None:
            raise DocumentError(f"{name} needs an id or xyz")
        return entity_id
    return PointAt(xyz_mm=as_xyz(f"{name}.xyz", ref["xyz"]), entity_id=entity_id)


def as_vertex_tuple(name: str, value: object) -> tuple[VertexRef, ...]:
    if not isinstance(value, list):
        raise DocumentError(f"{name} must be a list of vertices, got {value!r}")
    items = cast(list[object], value)
    return tuple(as_vertex(name, item) for item in items)
