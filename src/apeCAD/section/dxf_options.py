"""The arguments of the DXF import and its refusals (ADR 0042 decisions 2, 4, 5, 11 and 14).

The layer map, the units and the arc chord, each checked by name before any byte is read, and
the three refusal types every message of the import comes in. `section/dxf_seed.py` builds the
seed with them; `dxf_import.py` checks the arguments first. Split from `dxf_seed.py` to keep
both under ADR 0023's 600 lines.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar, cast

from apeCAD.errors import INVALID_ARGUMENT, REFUSED, TOO_LARGE, DocumentError
from apeCAD.section.designations import DESIGNATIONS

Json = dict[str, object]

MAX_BYTES = 8 * 1024 * 1024
"""Most bytes read, counted before parsing (decision 11)."""

UNIT_FACTORS: Mapping[str, float] = {"in": 25.4, "ft": 304.8, "mm": 1.0, "cm": 10.0, "m": 1000.0}
"""Millimetres per drawing unit, exact factors (decision 4)."""
INSUNITS: Mapping[int, str] = {1: "in", 2: "ft", 4: "mm", 5: "cm", 6: "m"}
"""The `$INSUNITS` codes the import reads; any other names no unit."""

ROLES = ("concrete", "steel", "void", "bar")
_DEFAULT_MATERIAL: Mapping[str, str] = {"concrete": "concrete", "steel": "steel"}


class DxfRefusedError(DocumentError):
    """A file the import will not read, as `dxf <reason>: <detail>` (decision 14): `REFUSED`."""

    code: ClassVar[str] = REFUSED

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"dxf {reason}: {detail}")
        self.reason = reason


class DxfTooLargeError(DxfRefusedError):
    """A file over one of the caps (decision 11): `TOO_LARGE`, never truncated."""

    code: ClassVar[str] = TOO_LARGE


class DxfArgumentError(DxfRefusedError):
    """A bad `data`, `layers`, `units` or `arc_chord_mm` argument: `INVALID_ARGUMENT`."""

    code: ClassVar[str] = INVALID_ARGUMENT


@dataclass(frozen=True, slots=True)
class LayerRole:
    """What a mapped layer holds: its role, its material, and (bars only) a designation."""

    role: str
    material: str | None
    designation: str | None = None


DEFAULT_LAYERS: Mapping[str, LayerRole] = {
    "CONCRETE-CUT": LayerRole("concrete", "concrete"),
    "STEEL-CUT": LayerRole("steel", "steel"),
    "VOID": LayerRole("void", None),
    "BAR": LayerRole("bar", None),
}
"""The writer's own layers (`render/style.py::SECTION_STYLE`), so apeCAD's export round-trips."""


def layer_map(layers: object) -> dict[str, LayerRole]:
    """The layer map by case-folded name: `DEFAULT_LAYERS`, or `layers`, which replaces it.

    Each entry of `layers` is `name -> {role, material?, designation?}`. Two names that match
    each other, an unknown key or role, or a designation outside `DESIGNATIONS` (or on a layer
    that is not a bar layer) is `INVALID_ARGUMENT`.
    """
    if layers is None:
        return {name.casefold(): role for name, role in DEFAULT_LAYERS.items()}
    if not isinstance(layers, Mapping) or not layers:
        raise DxfArgumentError("layers", f"must map layer names to roles, got {layers!r}")
    out: dict[str, LayerRole] = {}
    spelled: dict[str, str] = {}
    for name, raw in cast(Mapping[object, object], layers).items():
        if not isinstance(name, str) or not name.strip():
            raise DxfArgumentError("layers", f"a layer name must be a non-empty string: {name!r}")
        key = name.casefold()
        if key in out:
            raise DxfArgumentError("layers", f"{spelled[key]!r} and {name!r} name one layer")
        out[key], spelled[key] = _layer_role(name, raw), name
    return out


def _layer_role(name: str, raw: object) -> LayerRole:
    where = f"layers[{name!r}]"
    if not isinstance(raw, Mapping):
        raise DxfArgumentError("layers", f"{where} must be an object, got {raw!r}")
    entry = cast(Mapping[object, object], raw)
    for key in entry:
        if key not in ("role", "material", "designation"):
            raise DxfArgumentError("layers", f"{where} has an unknown key {key!r}")
    role = entry.get("role")
    if not isinstance(role, str) or role not in ROLES:
        raise DxfArgumentError("layers", f"{where}.role must be one of {ROLES}, got {role!r}")
    material = entry.get("material", _DEFAULT_MATERIAL.get(role))
    if material is None and role in ("concrete", "steel"):
        raise DxfArgumentError("layers", f"{where} is a {role} layer and needs a material")
    if material is not None and (not isinstance(material, str) or not material.strip()):
        raise DxfArgumentError("layers", f"{where}.material must be a name, got {material!r}")
    designation = entry.get("designation")
    if designation is not None and (role != "bar" or designation not in DESIGNATIONS):
        raise DxfArgumentError(
            "layers",
            f"{where}.designation {designation!r} needs a bar layer and one of "
            f"{', '.join(DESIGNATIONS)}",
        )
    return LayerRole(role, material, cast(str | None, designation))


def require_chord(arc_chord_mm: object) -> float | None:
    """`arc_chord_mm`: None, or a positive finite sagitta in mm (decision 5)."""
    if arc_chord_mm is None:
        return None
    if (
        not isinstance(arc_chord_mm, (int, float))
        or isinstance(arc_chord_mm, bool)
        or not math.isfinite(arc_chord_mm)
        or arc_chord_mm <= 0
    ):
        raise DxfArgumentError("arc_chord_mm", f"must be a positive number, got {arc_chord_mm!r}")
    return float(arc_chord_mm)


def require_units(units: object) -> str | None:
    """`units`: None, or one of `UNIT_FACTORS`' names."""
    if units is None:
        return None
    if not isinstance(units, str) or units not in UNIT_FACTORS:
        raise DxfArgumentError("units", f"must be one of {', '.join(UNIT_FACTORS)}, got {units!r}")
    return units


def choose_units(units: str | None, insunits: object) -> tuple[Json, list[Json]]:
    """Decision 4: `units` wins, then `$INSUNITS`; with neither, `dxf no-units`. Never guessed.

    Returns the report's `units` object and its warnings: one when `units` and a set
    `$INSUNITS` disagree.
    """
    in_file = INSUNITS.get(insunits) if type(insunits) is int else None
    warnings: list[Json] = []
    if units is not None:
        name, source = units, "argument"
        if in_file != units and insunits not in (None, 0):
            warnings.append({
                "code": "dxf-units-mismatch",
                "message": f"$INSUNITS is {insunits!r} ({in_file or 'not read'}); "
                f"the units argument {units!r} wins",
            })  # fmt: skip
    elif in_file is not None:
        name, source = in_file, "$INSUNITS"
    else:
        raise DxfRefusedError(
            "no-units",
            f"$INSUNITS is {insunits!r}, which names no unit this import reads, and no units "
            f"argument was given; pass one of {', '.join(UNIT_FACTORS)}",
        )
    report: Json = {
        "name": name, "mm_per_unit": UNIT_FACTORS[name], "source": source, "insunits": insunits,
    }  # fmt: skip
    return report, warnings
