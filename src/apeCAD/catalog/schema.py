"""JSON Schema for op params, derived from the op dataclasses, and a validator for it.

Derivation follows spec `agent-surface-mcp.md` §1: the JSON type comes from each field's type
hint, a field with a dataclass default is optional and carries that default, and
`additionalProperties` is false. The validator understands exactly the keywords derived here.
"""

from __future__ import annotations

import dataclasses
import math
import types
from collections.abc import Iterable, Mapping
from typing import Union, cast, get_args, get_origin, get_type_hints

from apeCAD.errors import OpArgumentError
from apeCAD.geometry import XYZ
from apeCAD.ops import Op, PointAt

Schema = dict[str, object]

_XYZ: Schema = {
    "type": "array",
    "items": {"type": "number"},
    "minItems": 3,
    "maxItems": 3,
}
_ID: Schema = {"type": "integer", "minimum": 1}
# ADR 0030 vertex reference, as an agent sends it. The committed form {"xyz", "id"} carries an
# allocated id, so it is output-only: replay accepts it, `apply` does not.
_VERTEX: Schema = {
    "anyOf": [
        _ID,
        {
            "type": "object",
            "properties": {"id": _ID},
            "required": ["id"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {"xyz": _XYZ},
            "required": ["xyz"],
            "additionalProperties": False,
        },
    ]
}
_SCALARS: dict[object, Schema] = {
    bool: {"type": "boolean"},
    int: {"type": "integer"},
    float: {"type": "number"},
    str: {"type": "string"},
}


def params_schema(
    op_type: type[Op],
    descriptions: Mapping[str, str],
    *,
    outputs: Iterable[str] = (),
    defaults: Mapping[str, object] | None = None,
) -> Schema:
    """The params schema of one op: every field except `outputs`, each with its description.

    `defaults` makes a field without a dataclass default optional, for fields the codec has
    always treated as optional (Extrude's `face_id`).
    """
    hints = get_type_hints(op_type)
    skipped = set(outputs)
    extra = dict(defaults or {})
    properties: dict[str, object] = {}
    required: list[str] = []
    for field in dataclasses.fields(op_type):
        if field.name in skipped:
            continue
        prop = dict(_field_schema(field.name, hints[field.name]))
        prop["description"] = descriptions[field.name]
        if field.default is not dataclasses.MISSING:
            prop["default"] = _json_default(field.default)
        elif field.name in extra:
            prop["default"] = extra[field.name]
        else:
            required.append(field.name)
        properties[field.name] = prop
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _field_schema(name: str, hint: object) -> Schema:
    is_id = name.endswith("_id") or name.endswith("_ids")
    origin = get_origin(hint)
    if origin is Union or origin is types.UnionType:
        members = get_args(hint)
        concrete = tuple(member for member in members if member is not type(None))
        nullable = len(concrete) != len(members)
        if set(concrete) == {int, PointAt}:
            inner = _VERTEX
        elif len(concrete) == 1:
            inner = _field_schema(name, concrete[0])
        else:
            raise TypeError(f"{name}: no JSON schema for union {hint!r}")
        return _nullable(inner) if nullable else inner
    if origin is tuple:
        args = get_args(hint)
        if len(args) == 2 and args[1] is Ellipsis:
            return {"type": "array", "items": _field_schema(name, args[0])}
        return {
            "type": "array",
            "prefixItems": [_field_schema(name, arg) for arg in args],
            "minItems": len(args),
            "maxItems": len(args),
        }
    if hint is XYZ:
        return _XYZ
    if isinstance(hint, type) and dataclasses.is_dataclass(hint):
        return _record_schema(hint)
    if hint is int and is_id:
        return _ID
    if hint in _SCALARS:
        return _SCALARS[hint]
    raise TypeError(f"{name}: no JSON schema for {hint!r}")


def _record_schema(record: type) -> Schema:
    """A nested value object (a wall leg's `LegSteel`): every field required, no others."""
    hints = get_type_hints(record)
    names = [field.name for field in dataclasses.fields(record)]
    return {
        "type": "object",
        "properties": {name: _field_schema(name, hints[name]) for name in names},
        "required": names,
        "additionalProperties": False,
    }


def _nullable(inner: Schema) -> Schema:
    kind = inner.get("type")
    if isinstance(kind, str):
        return {**inner, "type": [kind, "null"]}
    return {"anyOf": [inner, {"type": "null"}]}


def _json_default(value: object) -> object:
    if isinstance(value, XYZ):
        return list(value.to_tuple())
    return value


def validate(schema: Mapping[str, object], value: object, path: str) -> None:
    """Raise `OpArgumentError` naming the first place `value` breaks `schema`."""
    choices = schema.get("anyOf")
    if isinstance(choices, list):
        for choice in cast(list[Mapping[str, object]], choices):
            try:
                validate(choice, value, path)
            except OpArgumentError:
                continue
            return
        raise OpArgumentError(f"{path}: {value!r} matches none of the allowed forms")
    kind = schema.get("type")
    kinds = [kind] if isinstance(kind, str) else cast(list[str], kind or [])
    if kinds and not any(_is_type(value, k) for k in kinds):
        raise OpArgumentError(f"{path} must be {' or '.join(kinds)}, got {value!r}")
    minimum = schema.get("minimum")
    if isinstance(minimum, int) and isinstance(value, int) and value < minimum:
        raise OpArgumentError(f"{path} must be at least {minimum}, got {value!r}")
    if isinstance(value, list):
        _validate_array(schema, cast(list[object], value), path)
    elif isinstance(value, dict):
        _validate_object(schema, cast(dict[str, object], value), path)


def _validate_array(schema: Mapping[str, object], items: list[object], path: str) -> None:
    low = schema.get("minItems")
    high = schema.get("maxItems")
    if isinstance(low, int) and len(items) < low:
        raise OpArgumentError(f"{path} needs at least {low} items, got {len(items)}")
    if isinstance(high, int) and len(items) > high:
        raise OpArgumentError(f"{path} takes at most {high} items, got {len(items)}")
    prefix = schema.get("prefixItems")
    item_schema = schema.get("items")
    for index, item in enumerate(items):
        if isinstance(prefix, list):
            validate(cast(list[Mapping[str, object]], prefix)[index], item, f"{path}[{index}]")
        elif isinstance(item_schema, Mapping):
            validate(cast(Mapping[str, object], item_schema), item, f"{path}[{index}]")


def _validate_object(schema: Mapping[str, object], value: dict[str, object], path: str) -> None:
    properties = cast(Mapping[str, Mapping[str, object]], schema.get("properties", {}))
    for name in cast(list[str], schema.get("required", [])):
        if name not in value:
            raise OpArgumentError(f"{path}.{name} is required")
    for name, item in value.items():
        if name not in properties:
            if schema.get("additionalProperties") is False:
                allowed = ", ".join(properties) or "none"
                raise OpArgumentError(f"{path}.{name} is not a field (allowed: {allowed})")
            continue
        validate(properties[name], item, f"{path}.{name}")


def _is_type(value: object, kind: str) -> bool:
    if kind == "null":
        return value is None
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
        )
    if kind == "string":
        return isinstance(value, str)
    if kind == "array":
        return isinstance(value, list)
    if kind == "object":
        return isinstance(value, dict)
    raise TypeError(f"unknown JSON type {kind!r}")
