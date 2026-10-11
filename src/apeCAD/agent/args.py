"""Checks for tool arguments, which arrive as untyped JSON. A bad one is `INVALID_ARGUMENT`."""

from __future__ import annotations

import math
from typing import cast

from apeCAD.agent.errors import ToolError
from apeCAD.errors import INVALID_ARGUMENT


def invalid(message: str) -> ToolError:
    return ToolError(INVALID_ARGUMENT, message)


def as_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise invalid(f"{name} must be an integer, got {value!r}")
    return value


def opt_int(name: str, value: object) -> int | None:
    return None if value is None else as_int(name, value)


def as_str(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise invalid(f"{name} must be a string, got {value!r}")
    return value


def opt_str(name: str, value: object) -> str | None:
    return None if value is None else as_str(name, value)


def as_bool(name: str, value: object) -> bool:
    if not isinstance(value, bool):
        raise invalid(f"{name} must be true or false, got {value!r}")
    return value


def as_number(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise invalid(f"{name} must be a finite number, got {value!r}")
    return float(value)


def as_list(name: str, value: object) -> list[object]:
    if not isinstance(value, list):
        raise invalid(f"{name} must be an array, got {value!r}")
    return list(cast(list[object], value))


def opt_int_list(name: str, value: object) -> list[int] | None:
    if value is None:
        return None
    return [as_int(f"{name}[{i}]", item) for i, item in enumerate(as_list(name, value))]


def as_object(name: str, value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise invalid(f"{name} must be an object, got {value!r}")
    typed: dict[str, object] = {}
    for key, item in cast(dict[object, object], value).items():
        if not isinstance(key, str):
            raise invalid(f"{name} keys must be strings, got {key!r}")
        typed[key] = item
    return typed


def as_xyz(name: str, value: object) -> tuple[float, float, float]:
    items = as_list(name, value)
    if len(items) != 3:
        raise invalid(f"{name} must be three millimetre values [x, y, z]")
    x, y, z = (as_number(f"{name}[{i}]", item) for i, item in enumerate(items))
    return (x, y, z)


def only_keys(name: str, value: dict[str, object], allowed: set[str]) -> None:
    extra = sorted(set(value) - allowed)
    if extra:
        raise invalid(f"{name} takes only {sorted(allowed)}, got extra {extra}")
