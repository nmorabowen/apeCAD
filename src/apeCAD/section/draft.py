"""The `section` block of an `apeCAD.section-draft` v1, and the reopen comparison (ADR 0025).

`project_section(entities)` is a pure function of the document's entities: it projects the
section kinds onto the block that `specs/section-draft.md` fixes, in entity-id order. The
rings are the stored ones, which the ops keep CCW (faces) and strict-hull CCW (hoops).

`compare_sections(stored, fresh)` is the P9 rule for a reopened draft: a numeric
difference (rel_tol 1e-9) is a warning, any other difference is a `DocumentError`.

This module takes entities, not the `Document` (this package never imports `document`,
`draft/` or `scratchpad`); `apeCAD.section_draft` wraps it for a `Document`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import cast

from apeCAD.entities import (
    Bar,
    ConcreteFace,
    CoverGuide,
    Crosstie,
    Entity,
    EntityId,
    Hoop,
    Point,
    WallLeg,
)
from apeCAD.errors import DocumentError

DRAFT_SCHEMA = "apeCAD.section-draft"
DRAFT_SCHEMA_VERSION = 1
DRAFT_UNITS = "mm"
DRAFT_FRAME: Mapping[str, str] = {"x": "right", "y": "up", "origin": "world"}

REL_TOL = 1e-9
"""Reopen tolerance (ADR 0025 decision 3): a number further off than this is a warning."""

SECTION_LISTS = (
    "concrete_faces",
    "wall_legs",
    "bars",
    "hoops",
    "crossties",
    "cover_guides",
)
"""The block's lists, in the contract's order; every item carries an `id`."""

REOPEN_NUMERIC = "reopen-numeric-difference"
"""The warning code of a stored number that differs from the replayed one."""

_NUMERIC_KEYS = frozenset(
    {
        "ring_mm",
        "start_mm",
        "end_mm",
        "thickness_mm",
        "x_mm",
        "y_mm",
        "diameter_mm",
        "spacing_mm",
        "cover_mm",
        "tie_diameter_mm",
        "bar_diameter_mm",
    }
)
"""Fields whose numbers are lengths: compared with `REL_TOL`. Every other value (ids,
designations, labels, hooks, curtains) must be equal."""

Json = dict[str, object]


def project_section(entities: Mapping[EntityId, Entity]) -> Json:
    """The `section` block of these entities (specs/section-draft.md)."""
    ordered = [entities[i] for i in sorted(entities)]
    xy = {
        e.entity_id: [float(e.xyz_mm.x_mm), float(e.xyz_mm.y_mm)]
        for e in ordered
        if isinstance(e, Point)
    }
    bar_xy = {e.entity_id: xy[e.point_id] for e in ordered if isinstance(e, Bar)}
    return {
        "concrete_faces": [
            {
                "id": e.entity_id,
                "label": e.label,
                "material": e.material,
                "role": e.role,
                "ring_mm": [list(xy[pid]) for pid in e.point_ids],
            }
            for e in ordered
            if isinstance(e, ConcreteFace)
        ],
        "wall_legs": [_wall_leg(e, xy) for e in ordered if isinstance(e, WallLeg)],
        "bars": [
            {
                "id": e.entity_id,
                "label": e.label,
                "x_mm": bar_xy[e.entity_id][0],
                "y_mm": bar_xy[e.entity_id][1],
                "diameter_mm": float(e.diameter_mm),
                "designation": e.designation,
            }
            for e in ordered
            if isinstance(e, Bar)
        ],
        "hoops": [
            {
                "id": e.entity_id,
                "label": e.label,
                "bar_ids": list(e.bar_ids),
                "diameter_mm": float(e.diameter_mm),
                "designation": e.designation,
                "spacing_mm": float(e.spacing_mm),
                "hooks": e.hooks,
            }
            for e in ordered
            if isinstance(e, Hoop)
        ],
        "crossties": [
            {
                "id": e.entity_id,
                "label": e.label,
                "bar_a_id": e.bar_a_id,
                "bar_b_id": e.bar_b_id,
                "diameter_mm": float(e.diameter_mm),
                "designation": e.designation,
                "spacing_mm": float(e.spacing_mm),
                "hooks": e.hooks,
            }
            for e in ordered
            if isinstance(e, Crosstie)
        ],
        "cover_guides": [
            {
                "id": e.entity_id,
                "face_id": e.face_id,
                "cover_mm": float(e.cover_mm),
                "tie_diameter_mm": float(e.tie_diameter_mm),
                "bar_diameter_mm": float(e.bar_diameter_mm),
            }
            for e in ordered
            if isinstance(e, CoverGuide)
        ],
    }


def _wall_leg(leg: WallLeg, xy: Mapping[EntityId, list[float]]) -> Json:
    steel = leg.horizontal
    return {
        "id": leg.entity_id,
        "label": leg.label,
        "start_mm": list(xy[leg.start_id]),
        "end_mm": list(xy[leg.end_id]),
        "thickness_mm": float(leg.thickness_mm),
        "concrete_face_id": leg.face_id,
        "horizontal": None
        if steel is None
        else {
            "designation": steel.designation,
            "spacing_mm": float(steel.spacing_mm),
            "curtains": steel.curtains,
        },
    }


def require_header(draft: Mapping[str, object]) -> None:
    """Refuse a draft whose schema, version or units this reader does not know."""
    schema = draft.get("schema")
    version = draft.get("version")
    if schema != DRAFT_SCHEMA:
        raise DocumentError(f"unsupported draft schema {schema!r}, expected {DRAFT_SCHEMA!r}")
    if type(version) is not int or version != DRAFT_SCHEMA_VERSION:
        raise DocumentError(
            f"unsupported {DRAFT_SCHEMA} version {version!r}, expected {DRAFT_SCHEMA_VERSION}"
        )
    units = draft.get("units")
    if units != DRAFT_UNITS:
        raise DocumentError(f"unsupported draft units {units!r}, expected {DRAFT_UNITS!r}")


def compare_sections(stored: object, fresh: Json) -> list[Json]:
    """Compare a stored `section` block with the one recomputed from the replayed document.

    Returns one `{code, ids, message}` warning per item whose numbers moved by more than
    `REL_TOL`. Raises `DocumentError` on a structural difference: an id missing or extra in
    a list (which also catches an id of another kind), or any non-numeric field that
    differs (hoop membership, designations, labels, hooks). A stored key this reader does
    not write is ignored, so an additive field (ADR 0025 rule 6) still reopens.
    """
    block = _object(stored, "section")
    warnings: list[Json] = []
    for name in SECTION_LISTS:
        stored_items = _by_id(block.get(name), f"section.{name}")
        fresh_items = _by_id(fresh[name], f"section.{name}")
        missing = sorted(set(fresh_items) - set(stored_items))
        extra = sorted(set(stored_items) - set(fresh_items))
        if missing or extra:
            raise DocumentError(
                f"section.{name} differs from the replayed document: "
                f"ids missing from the draft {missing}, ids not in the document {extra}"
            )
        for entity_id, item in fresh_items.items():
            where = f"section.{name}[id={entity_id}]"
            moved: list[str] = []
            _compare(stored_items[entity_id], item, where, numeric=False, moved=moved)
            if moved:
                warnings.append(
                    {
                        "code": REOPEN_NUMERIC,
                        "ids": [entity_id],
                        "message": f"{where}: the stored value differs from the replayed one "
                        f"beyond rel {REL_TOL:g} at {', '.join(moved)}; the replay wins",
                    }
                )
    return warnings


def _compare(stored: object, fresh: object, where: str, *, numeric: bool, moved: list[str]) -> None:
    if isinstance(fresh, dict):
        fresh_obj = cast(Json, fresh)
        stored_obj = _object(stored, where)
        for key, value in fresh_obj.items():
            if key not in stored_obj:
                raise DocumentError(f"{where} has no {key!r}")
            _compare(
                stored_obj[key],
                value,
                f"{where}.{key}",
                numeric=numeric or key in _NUMERIC_KEYS,
                moved=moved,
            )
        return
    if isinstance(fresh, list):
        fresh_list = cast(list[object], fresh)
        stored_list = _list(stored, where)
        if len(stored_list) != len(fresh_list):
            raise DocumentError(
                f"{where} has {len(stored_list)} items; the replayed document has {len(fresh_list)}"
            )
        for index, (old, new) in enumerate(zip(stored_list, fresh_list, strict=True)):
            _compare(old, new, f"{where}[{index}]", numeric=numeric, moved=moved)
        return
    if numeric and _is_number(fresh):
        if not _is_number(stored):
            raise DocumentError(f"{where} must be a number, got {stored!r}")
        old = float(cast(float, stored))
        new = float(cast(float, fresh))
        if not math.isclose(old, new, rel_tol=REL_TOL, abs_tol=0.0):
            moved.append(f"{where} ({old!r} stored, {new!r} replayed)")
        return
    if stored != fresh or type(stored) is not type(fresh):
        raise DocumentError(
            f"{where} is {stored!r} in the draft; the replayed document has {fresh!r}"
        )


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _object(value: object, where: str) -> Json:
    if not isinstance(value, dict):
        raise DocumentError(f"{where} must be an object, got {type(value).__name__}")
    return cast(Json, value)


def _list(value: object, where: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise DocumentError(f"{where} must be a list, got {type(value).__name__}")
    return cast(list[object], value)


def _by_id(value: object, where: str) -> dict[EntityId, Json]:
    items: dict[EntityId, Json] = {}
    for index, raw in enumerate(_list(value, where)):
        item = _object(raw, f"{where}[{index}]")
        entity_id = item.get("id")
        if type(entity_id) is not int:
            raise DocumentError(f"{where}[{index}].id must be an integer, got {entity_id!r}")
        if entity_id in items:
            raise DocumentError(f"{where} repeats id {entity_id}")
        items[entity_id] = item
    return items
