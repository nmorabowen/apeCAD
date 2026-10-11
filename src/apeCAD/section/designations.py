"""The closed bar vocabulary of section mode (ADR 0024 P12, specs/section-draft.md).

Copied from apeConcrete `src/apeConcrete/rebar/bars.py` `METRIC_BARS`, in its canonical
spelling `f"Ø{d:g}"`. Every `Bar`, `Hoop`, `Crosstie` and leg-steel designation comes from
this list; anything else is a DocumentError. US bars (`#3` to `#18`) are not in v1.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from apeCAD.errors import DocumentError

_DIAMETERS_MM = (8, 10, 12, 14, 16, 18, 20, 22, 25, 28, 32)

DESIGNATIONS: Mapping[str, float] = MappingProxyType(
    {f"Ø{d:g}": float(d) for d in _DIAMETERS_MM}
)


def designation_for(diameter_mm: float) -> str:
    """The designation of a vocabulary diameter: 16.0 -> "Ø16"."""
    name = f"Ø{diameter_mm:g}"
    if DESIGNATIONS.get(name) != diameter_mm:
        raise DocumentError(
            f"no bar of diameter {diameter_mm!r} mm in the vocabulary; "
            f"known: {', '.join(DESIGNATIONS)}"
        )
    return name


def require_designation(name: str, diameter_mm: float) -> float:
    """Check a designation and its diameter; returns the diameter in mm."""
    known = DESIGNATIONS.get(name)
    if known is None:
        raise DocumentError(
            f"unknown bar designation {name!r}; known: {', '.join(DESIGNATIONS)}"
        )
    if diameter_mm != known:
        raise DocumentError(
            f"bar {name} has diameter {known:g} mm, not {diameter_mm!r} mm"
        )
    return known
