"""What every op module shares: labels, and vertex references (ADR 0030)."""

from __future__ import annotations

from dataclasses import dataclass

from apeCAD.entities import EntityId
from apeCAD.errors import DocumentError
from apeCAD.geometry import XYZ


def optional_label(label: str | None) -> str | None:
    if label is None:
        return None
    stripped = label.strip()
    if stripped == "":
        raise DocumentError("label must be None or a non-empty string")
    return stripped


def require_name(name: str) -> str:
    stripped = name.strip()
    if stripped == "":
        raise DocumentError("tag name must be a non-empty string")
    return stripped


@dataclass(frozen=True, slots=True)
class PointAt:
    """A vertex given by coordinates (ADR 0030).

    Live, the handler reuses a point within 1 mm or creates one. The committed op records
    a reused point as its plain id and a created one as `PointAt` with `entity_id` set, so
    replay recreates that exact id without searching.
    """

    xyz_mm: XYZ
    entity_id: EntityId | None = None


VertexRef = EntityId | PointAt
"""A creation op's vertex: an existing point id, or coordinates (ADR 0030)."""
