"""The hole step of version 2 (ADR 0040 Errata 13.2): user holes, placed, checked and appended.

Version 2 of a template is version 1 composed with this step (Errata 15.2). It takes an
optional `holes`, a list of holes in one of two forms:

- `{"center_mm": [x, y], "radius_mm": r}`, a circle;
- `{"ring_mm": [[x, y], ...]}`, a simple ring of at least 3 vertices, given once and in
  either orientation.

On a template centred at `center_mm` = (cx, cy) the coordinates are offsets, so the hole at
(x, y) lands at (cx + x, cy + y) and moves with the template; `polygon_column` has no
`center_mm`, so its holes are in section coordinates, the frame of its `ring` (13.1).

`version_2` wraps a v1 function and runs these steps in order; the first that fails is the
refusal, a `TemplateParamError` whose message starts `<template>: <param>:` (16):

1. the params are an object, with no key outside the v1 `FIELDS` and `holes` (`Params`);
2. `holes` is a list (`holes`; `null` included);
3. the caps: at most `MAX_HOLES` holes and `MAX_HOLE_VERTICES` ring vertices, counting only
   the list-valued `ring_mm` of object entries (`holes`; 16.2);
4. each hole's shape, hole by hole: an object (`holes[k]`), no unknown key
   (`holes[k].<key>`), exactly one of the two forms (`holes[k]`), a `center_mm` of two finite
   numbers, a positive finite `radius_mm`, a `ring_mm` that is a list of 3 or more vertices
   (`holes[k].ring_mm`) each of two finite numbers (`holes[k].ring_mm[i]`);
5. the v1 function, on the params without `holes`: every v1 refusal and drawing is unchanged;
6. placement, hole by hole: the ADR 0032 extent (`holes[k]`); the ring's exact simplicity,
   zero area and orientation (`holes[k].ring_mm`); then, on the vertex order it will be
   stored in (clockwise, exactly), the downstream consumers' own float checks
   (`holes[k].ring_mm`): `plan.py::_check_boundary` (`is_simple`, and `signed_area > 0.0`
   must be false) and `draft/section.py::_boundary` (`require_simple`, and
   `signed_area < 0.0` must be true, so it keeps the stored order);
7. the rules R1 to R7 (`hole_rules.py`, Errata 17), decided exactly, contact refused;
8. the holes are appended, in index order and stored clockwise, after the own holes of the
   plan's one concrete face.

This module imports only `apeCAD.section` and `apeCAD.errors` (tests/test_architecture.py).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import cast

from apeCAD.errors import DocumentError
from apeCAD.section.geometry import Point2, is_simple, require_simple, signed_area
from apeCAD.section.templates.hole_rules import (
    exact_simplicity_fault,
    exact_twice_area,
    require_holes_clear,
)
from apeCAD.section.templates.plan import (
    Params,
    Plan,
    PlanBoundary,
    PlanCircle,
    PlanRing,
    TemplateParamError,
    number,
    point_value,
    positive,
    require_extent,
)

VERSION = 2
"""The template version that takes `holes` (Errata 15)."""

MAX_HOLES = 32
"""Most holes one template takes (Errata 16.2, owner ruling in comment 4844)."""

MAX_HOLE_VERTICES = 256
"""Most ring vertices one template's holes hold across all their rings (Errata 16.2)."""

CIRCLE_KEYS = ("center_mm", "radius_mm")
RING_KEYS = ("ring_mm",)
HOLE_KEYS = (*CIRCLE_KEYS, *RING_KEYS)


@dataclass(frozen=True, slots=True)
class CircleHole:
    """A circle hole: `center_mm` an offset (or a section point on `polygon_column`), mm."""

    center_mm: Point2
    radius_mm: float


@dataclass(frozen=True, slots=True)
class RingHole:
    """A ring hole: 3 or more vertices, given once, in either orientation."""

    ring_mm: tuple[Point2, ...]


Expansion = Callable[[Mapping[str, object]], Plan]


def version_2(template: str, fields: Sequence[str], v1: Expansion, *, centred: bool) -> Expansion:
    """Version 2 of `template`: `v1` composed with the hole step.

    `fields` are v1's parameter names; `centred` says the template is placed by `center_mm`
    (default (0, 0)), so a hole's coordinates are offsets from it.
    """

    def expand_v2(data: Mapping[str, object]) -> Plan:
        return expand_with_holes(template, fields, v1, data, centred=centred)

    expand_v2.__name__ = f"{template}_expand_v2"
    expand_v2.__qualname__ = expand_v2.__name__
    return expand_v2


def expand_with_holes(
    template: str,
    fields: Sequence[str],
    v1: Expansion,
    data: Mapping[str, object],
    *,
    centred: bool,
) -> Plan:
    """The version 2 plan of `data`: steps 1 to 8 of Errata 13.2, in order."""
    Params(template, data, (*fields, "holes"))  # step 1: an object, and no unknown key
    entries = _hole_list(template, data)  # step 2
    _require_caps(template, entries)  # step 3
    shapes = [_shape(template, k, entry) for k, entry in enumerate(entries)]  # step 4
    v1_params = {key: value for key, value in data.items() if key != "holes"}
    plan = v1(v1_params)  # step 5
    if not shapes:
        return plan
    cx, cy = 0.0, 0.0
    if centred:  # the same floats v1 read: it accepted them in step 5
        cx, cy = Params(template, v1_params, fields).point("center_mm", (0.0, 0.0))
    stored = [
        _placed(template, k, shape, cx, cy, centred=centred) for k, shape in enumerate(shapes)
    ]  # step 6
    require_holes_clear(template, plan, stored)  # step 7
    return _appended(plan, stored)  # step 8


# --- steps 2 to 4: the shape, before anything is placed -----------------------------------


def _hole_list(template: str, data: Mapping[str, object]) -> Sequence[object]:
    if "holes" not in data:
        return ()
    value = data["holes"]
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        kind = "null" if value is None else type(value).__name__
        raise TemplateParamError(template, "holes", f"must be a list of holes, got {kind}")
    return cast(Sequence[object], value)


def _ring_values(entry: object) -> Sequence[object] | None:
    """The list-valued `ring_mm` of an object entry; None for anything else (16.2)."""
    if not isinstance(entry, Mapping):
        return None
    ring = cast(Mapping[object, object], entry).get("ring_mm")
    if isinstance(ring, str | bytes) or not isinstance(ring, Sequence):
        return None
    return cast(Sequence[object], ring)


def _require_caps(template: str, entries: Sequence[object]) -> None:
    if len(entries) > MAX_HOLES:
        raise TemplateParamError(
            template, "holes", f"{len(entries)} holes; a template takes at most {MAX_HOLES}"
        )
    vertices = sum(len(ring) for e in entries if (ring := _ring_values(e)) is not None)
    if vertices > MAX_HOLE_VERTICES:
        raise TemplateParamError(
            template,
            "holes",
            f"{vertices} ring vertices across the holes; a template takes at most "
            f"{MAX_HOLE_VERTICES}",
        )


def _shape(template: str, k: int, entry: object) -> CircleHole | RingHole:
    """Hole k as given, or its first shape fault by name (16.1, the rows before placement)."""
    where = f"holes[{k}]"
    if not isinstance(entry, Mapping):
        raise TemplateParamError(
            template,
            where,
            "must be an object, {center_mm, radius_mm} or {ring_mm}, got "
            + ("null" if entry is None else type(entry).__name__),
        )
    hole = cast(Mapping[object, object], entry)
    unknown = sorted(str(key) for key in hole if key not in HOLE_KEYS)
    if unknown:
        raise TemplateParamError(
            template, f"{where}.{unknown[0]}", f"unknown key; known: {', '.join(HOLE_KEYS)}"
        )
    keys = set(hole)
    if keys != set(CIRCLE_KEYS) and keys != set(RING_KEYS):
        given = ", ".join(sorted(str(key) for key in keys)) or "none"
        raise TemplateParamError(
            template,
            where,
            "must hold exactly one form, a circle {center_mm, radius_mm} or a ring {ring_mm}; "
            f"its keys are {given}",
        )
    p = Params(template, {}, (), prefix=f"{where}.")
    if keys == set(CIRCLE_KEYS):
        center = point_value(p, "center_mm", hole["center_mm"])
        radius = positive(p, "radius_mm", number(p, "radius_mm", hole["radius_mm"]))
        return CircleHole(center, radius)
    ring = _ring_values(hole)
    if ring is None:
        raise p.error(
            "ring_mm",
            f"must be a list of [x_mm, y_mm] vertices, got {type(hole['ring_mm']).__name__}",
        )
    if len(ring) < 3:
        raise p.error("ring_mm", f"needs 3 or more vertices, got {len(ring)}")
    return RingHole(tuple(point_value(p, f"ring_mm[{i}]", v) for i, v in enumerate(ring)))


# --- step 6: placement, then the checks on the placed floats ------------------------------


def _placed(
    template: str, k: int, shape: CircleHole | RingHole, cx: float, cy: float, *, centred: bool
) -> PlanBoundary:
    """Hole k placed in section floats and checked (16.1, the "after placement" rows).

    A ring comes back in the vertex order it is stored in: as given when its exact area is
    negative (clockwise), reversed otherwise.
    """

    def at(point: Point2) -> Point2:
        return (cx + point[0], cy + point[1]) if centred else point

    where = f"holes[{k}]"
    if isinstance(shape, CircleHole):
        (x, y), r = at(shape.center_mm), shape.radius_mm
        require_extent(template, where, ((x - r, y - r), (x + r, y + r)))  # as plan_points
        return PlanCircle((x, y), r)
    ring = tuple(at(point) for point in shape.ring_mm)
    require_extent(template, where, ring)
    fault = exact_simplicity_fault(ring)
    if fault is not None:
        raise TemplateParamError(template, f"{where}.ring_mm", f"is not simple: {fault}")
    twice = exact_twice_area(ring)
    if twice == 0:
        raise TemplateParamError(template, f"{where}.ring_mm", "has zero area")
    stored = ring if twice < 0 else ring[::-1]
    disagreement = _float_disagreement(stored)
    if disagreement is not None:
        raise TemplateParamError(
            template,
            f"{where}.ring_mm",
            f"it is exactly simple and clockwise as stored, but {disagreement}; a ring the "
            "float checks downstream do not decide the same way is refused (Errata 16.1)",
        )
    return PlanRing(stored)


def _float_disagreement(stored: tuple[Point2, ...]) -> str | None:
    """The first downstream float check, run as its consumer runs it, that fails `stored`.

    `plan.py::_check_boundary` takes a hole that `is_simple` and whose `signed_area > 0.0`
    is false; `draft/section.py::_boundary` takes one that passes `require_simple`, and
    keeps its order only when `signed_area < 0.0`.
    """
    if not is_simple(stored):
        return "the float is_simple (plan.py::_check_boundary) finds it not simple"
    if signed_area(stored) > 0.0:
        return "the float signed_area (plan.py::_check_boundary) finds it counter-clockwise"
    try:
        require_simple(stored, "a hole")
    except DocumentError as exc:
        return f"the float require_simple (draft/section.py::_boundary) says {exc}"
    if not signed_area(stored) < 0.0:
        return "the float signed_area (draft/section.py::_boundary) would reverse it"
    return None


# --- step 8 ---------------------------------------------------------------------------------


def _appended(plan: Plan, holes: Sequence[PlanBoundary]) -> Plan:
    """`plan` with `holes` after the own holes of its one concrete face, in index order."""
    (k,) = (i for i, face in enumerate(plan.faces) if face.role == "concrete")
    face = plan.faces[k]
    faces = list(plan.faces)
    faces[k] = replace(face, holes=(*face.holes, *holes))
    return replace(plan, faces=tuple(faces))
