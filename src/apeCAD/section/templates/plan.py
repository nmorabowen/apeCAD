"""The `Plan` a section template expands to, and the parameter readers templates share.

A template is a pure function from its parameters to a `Plan` (ADR 0040 decision 1, stage
C3-S1). A `Plan` names no entity and allocates no id: it is the list of faces, bars, hoops,
crossties, circular ties and cover guides a materialiser turns into ordinary section
entities (stage C3-S2). Bars are referred to by their index in `Plan.bars`, faces by their
index in `Plan.faces`.

All lengths are millimetres, in section coordinates (x right, y up, z = 0). Designations come
from the closed vocabulary (`section.designations`). A boundary ring is counter-clockwise and
a hole ring clockwise (specs/section-draft-v2.md "Ring orientation"). The `Plan` also carries
circles, holes, steel faces with `shape` provenance and circular ties (`circular_column` emits
a circle and a circular tie).

A bad parameter raises `TemplateParamError`, an `OpArgumentError` (`INVALID_ARGUMENT`) that
names the template and the parameter. A `Plan` that breaks its own invariants (an index out
of range, a ring the wrong way round) raises `DocumentError`: that is a template bug, not a
user error.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from apeCAD.errors import DocumentError, OpArgumentError
from apeCAD.section.designations import DESIGNATIONS
from apeCAD.section.geometry import Point2, convex_hull_ccw, is_simple, signed_area
from apeCAD.section.layout import (
    EXTENT_LIMIT_MM,
    MAX_LAYOUT_BARS,
    edge_positions,
    is_inclined,
    snap,
)

PlanRole = Literal["concrete", "steel", "void"]
"""A face's role, as `entities.SectionRole` (ADR 0039 decision 2)."""
PLAN_ROLES: tuple[PlanRole, ...] = ("concrete", "steel", "void")
CircularTieKind = Literal["spiral", "hoop"]
CrosstieHooks = Literal["135-135", "135-90"]

MAX_TEMPLATE_BARS = MAX_LAYOUT_BARS
"""Most bars one template places (C3 decision record §2)."""


class TemplateParamError(OpArgumentError):
    """A template parameter is missing, unknown, mistyped or out of range (`INVALID_ARGUMENT`).

    The message starts with `<template>: <param>:`, and the two names are attributes, so a
    host can point at the field.
    """

    def __init__(self, template: str, param: str, message: str) -> None:
        super().__init__(f"{template}: {param}: {message}")
        self.template = template
        self.param = param


def shown(value: object) -> str:
    """`repr(value)` for a refusal message, whatever `value` is.

    A value Python will not print is named by its type: an int past the 4300-digit limit
    (`sys.set_int_max_str_digits`) raises `ValueError`, and deep nesting `RecursionError`. A
    refusal must not crash on the value it refuses (apeSection#51).
    """
    try:
        return repr(value)
    except (ValueError, RecursionError):
        return f"an unprintable {type(value).__name__}"


# --- the Plan ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PlanRing:
    """A ring boundary: vertices given once, no repeated closing point."""

    points_mm: tuple[Point2, ...]


@dataclass(frozen=True, slots=True)
class PlanCircle:
    """An exact circle boundary (ADR 0039 decision 2); never tessellated in the contract."""

    center_mm: Point2
    radius_mm: float


PlanBoundary = PlanRing | PlanCircle


@dataclass(frozen=True, slots=True)
class PlanSteelShape:
    """Steel-shape provenance on a steel face (ADR 0039 decision 4); the ring is the outline."""

    catalog: str
    designation: str
    anchor_mm: Point2
    rotation_deg: float = 0.0


@dataclass(frozen=True, slots=True)
class PlanFace:
    """A v2 section face: role, material name (None only on a void), boundary and holes."""

    role: PlanRole
    material: str | None
    boundary: PlanBoundary
    holes: tuple[PlanBoundary, ...] = ()
    shape: PlanSteelShape | None = None


@dataclass(frozen=True, slots=True)
class PlanBar:
    """A longitudinal bar; `material` None means the draft's default bar steel."""

    x_mm: float
    y_mm: float
    designation: str
    diameter_mm: float
    material: str | None = None

    @property
    def xy(self) -> Point2:
        return (self.x_mm, self.y_mm)


@dataclass(frozen=True, slots=True)
class PlanHoop:
    """A polygon hoop: `bars` is the strict CCW hull of the bars it wraps (ADR 0024 P2)."""

    bars: tuple[int, ...]
    designation: str
    diameter_mm: float
    spacing_mm: float


@dataclass(frozen=True, slots=True)
class PlanCrosstie:
    """A crosstie between bars `bar_a` and `bar_b` (indices into `Plan.bars`)."""

    bar_a: int
    bar_b: int
    designation: str
    diameter_mm: float
    spacing_mm: float
    hooks: CrosstieHooks = "135-135"


@dataclass(frozen=True, slots=True)
class PlanCircularTie:
    """A spiral or circular hoop (ADR 0039 decision 5); `pitch_mm` is a hoop's spacing."""

    kind: CircularTieKind
    center_mm: Point2
    centerline_radius_mm: float
    designation: str
    diameter_mm: float
    pitch_mm: float


@dataclass(frozen=True, slots=True)
class PlanCoverGuide:
    """Cover intent on face `face` (an index into `Plan.faces`)."""

    face: int
    cover_mm: float
    tie_diameter_mm: float
    bar_diameter_mm: float


@dataclass(frozen=True, slots=True)
class Plan:
    """What one template expansion draws. Equal parameters give an equal `Plan`."""

    faces: tuple[PlanFace, ...]
    bars: tuple[PlanBar, ...] = ()
    hoops: tuple[PlanHoop, ...] = ()
    crossties: tuple[PlanCrosstie, ...] = ()
    circular_ties: tuple[PlanCircularTie, ...] = ()
    cover_guides: tuple[PlanCoverGuide, ...] = ()

    def __post_init__(self) -> None:
        _check_plan(self)


def _check_plan(plan: Plan) -> None:
    if not plan.faces:
        raise DocumentError("a template plan needs at least one face")
    for k, face in enumerate(plan.faces):
        if face.role not in PLAN_ROLES:
            raise DocumentError(f"plan face {k}: unknown role {face.role!r}")
        if (face.material is None) != (face.role == "void"):
            raise DocumentError(
                f"plan face {k}: a {face.role} face "
                + ("has no material" if face.role == "void" else "needs a material name")
            )
        if face.shape is not None and face.role != "steel":
            raise DocumentError(f"plan face {k}: only a steel face carries a shape")
        _check_boundary(face.boundary, f"plan face {k} boundary", ccw=True)
        for h, hole in enumerate(face.holes):
            _check_boundary(hole, f"plan face {k} hole {h}", ccw=False)
    n = len(plan.bars)
    for k, bar in enumerate(plan.bars):
        _check_designation(bar.designation, bar.diameter_mm, f"plan bar {k}")
    for k, hoop in enumerate(plan.hoops):
        _check_indices(hoop.bars, n, f"plan hoop {k}")
        if len(hoop.bars) < 3 or len(set(hoop.bars)) != len(hoop.bars):
            raise DocumentError(f"plan hoop {k} needs 3 or more distinct bars")
        _check_designation(hoop.designation, hoop.diameter_mm, f"plan hoop {k}")
    for k, tie in enumerate(plan.crossties):
        _check_indices((tie.bar_a, tie.bar_b), n, f"plan crosstie {k}")
        if tie.bar_a == tie.bar_b:
            raise DocumentError(f"plan crosstie {k} joins bar {tie.bar_a} to itself")
        _check_designation(tie.designation, tie.diameter_mm, f"plan crosstie {k}")
    for k, ctie in enumerate(plan.circular_ties):
        if not ctie.centerline_radius_mm > 0.0 or not ctie.pitch_mm > 0.0:
            raise DocumentError(f"plan circular tie {k} needs a positive radius and pitch")
        _check_designation(ctie.designation, ctie.diameter_mm, f"plan circular tie {k}")
    for k, guide in enumerate(plan.cover_guides):
        _check_indices((guide.face,), len(plan.faces), f"plan cover guide {k}")
        if plan.faces[guide.face].role != "concrete":
            raise DocumentError(f"plan cover guide {k} is on a face that is not concrete")


def _check_boundary(boundary: PlanBoundary, what: str, *, ccw: bool) -> None:
    if isinstance(boundary, PlanCircle):
        if not (math.isfinite(boundary.radius_mm) and boundary.radius_mm > 0.0):
            raise DocumentError(f"{what}: a circle needs a positive radius")
        return
    ring = boundary.points_mm
    if len(ring) < 3 or not is_simple(ring):
        raise DocumentError(f"{what}: the ring is not simple")
    if (signed_area(ring) > 0.0) != ccw:
        raise DocumentError(f"{what}: the ring must be {'CCW' if ccw else 'CW'}")


def _check_indices(indices: Sequence[int], count: int, what: str) -> None:
    for i in indices:
        if not 0 <= i < count:
            raise DocumentError(f"{what}: index {i} is out of range (0..{count - 1})")


def _check_designation(name: str, diameter_mm: float, what: str) -> None:
    if DESIGNATIONS.get(name) != diameter_mm:
        raise DocumentError(f"{what}: {name!r} is not a vocabulary bar of {diameter_mm!r} mm")


# --- shared expansion helpers -----------------------------------------------------------


def hull_of(bars: Sequence[PlanBar], indices: Sequence[int]) -> tuple[int, ...]:
    """The strict CCW hull (exact predicates, ADR 0032) of `bars[i]` for i in `indices`."""
    return tuple(convex_hull_ccw({i: bars[i].xy for i in indices}))


def plan_points(plan: Plan) -> list[Point2]:
    """Every position a plan places: ring vertices, circle extremes, bars, circular ties."""
    out: list[Point2] = []

    def boundary(b: PlanBoundary) -> None:
        if isinstance(b, PlanRing):
            out.extend(b.points_mm)
        else:
            (cx, cy), r = b.center_mm, b.radius_mm
            out.extend(((cx - r, cy - r), (cx + r, cy + r)))

    for face in plan.faces:
        boundary(face.boundary)
        for hole in face.holes:
            boundary(hole)
    out.extend(bar.xy for bar in plan.bars)
    for t in plan.circular_ties:
        (cx, cy), r = t.center_mm, t.centerline_radius_mm
        out.extend(((cx - r, cy - r), (cx + r, cy + r)))
    return out


def overlapping_bars(bars: Sequence[PlanBar]) -> tuple[int, int] | None:
    """The first pair (i < j) of bars closer than (d_i + d_j) / 2, lint's `bar-overlap` rule.

    A sweep over the bars sorted by x, so a 1000-bar plan is checked quickly; the pair it
    returns depends only on the bars, so a refusal names the same parameter on every run.
    """
    order = sorted(range(len(bars)), key=lambda k: (bars[k].x_mm, bars[k].y_mm, k))
    widest = max((bar.diameter_mm for bar in bars), default=0.0)
    found: list[tuple[int, int]] = []
    for pos, i in enumerate(order):
        a = bars[i]
        for j in order[pos + 1 :]:
            b = bars[j]
            if b.x_mm - a.x_mm >= widest:
                break
            gap = math.hypot(b.x_mm - a.x_mm, b.y_mm - a.y_mm)
            if gap < (a.diameter_mm + b.diameter_mm) / 2.0:
                found.append((min(i, j), max(i, j)))
    return min(found) if found else None


def finish(
    template: str,
    plan: Plan,
    *,
    placement: str,
    count: str,
    overlap: Callable[[int, int], str],
) -> Plan:
    """Refuse a plan with too many bars, overlapping bars, or a point outside the extent.

    `placement` names the parameter that puts the section where it is (`center_mm`, `ring`),
    `count` the one that sets how many bars there are, and `overlap(i, j)` the one that set
    the spacing of two overlapping bars.
    """
    if len(plan.bars) > MAX_TEMPLATE_BARS:
        raise TemplateParamError(
            template,
            count,
            f"these parameters place {len(plan.bars)} bars; a template places at most "
            f"{MAX_TEMPLATE_BARS}",
        )
    require_extent(template, placement, plan_points(plan))
    pair = overlapping_bars(plan.bars)
    if pair is not None:
        i, j = pair
        a, b = plan.bars[i], plan.bars[j]
        raise TemplateParamError(
            template,
            overlap(i, j),
            f"bars {i} at ({a.x_mm:g}, {a.y_mm:g}) and {j} at ({b.x_mm:g}, {b.y_mm:g}) "
            f"overlap: centres {math.hypot(b.x_mm - a.x_mm, b.y_mm - a.y_mm):g} mm apart, "
            f"under {(a.diameter_mm + b.diameter_mm) / 2.0:g} mm",
        )
    return plan


def require_extent(template: str, param: str, points: Iterable[Point2]) -> None:
    """Refuse, naming `param`, a point outside the ADR 0032 extent (±EXTENT_LIMIT_MM)."""
    for x, y in points:
        if not (abs(x) <= EXTENT_LIMIT_MM and abs(y) <= EXTENT_LIMIT_MM):
            raise TemplateParamError(
                template,
                param,
                f"the section reaches ({x:g}, {y:g}); sections stay within "
                f"±{EXTENT_LIMIT_MM:g} mm (ADR 0032)",
            )


def layout_ring(ring: Sequence[Point2]) -> list[Point2]:
    """`ring` as `layout.edge_positions` places bars on it, computed once.

    `edge_positions` snaps every vertex to `SNAP_GRID_MM` when any edge of its ring is
    inclined (ADR 0032), and does so again for every edge it is asked about: O(n²) on a ring
    of n vertices. Snapping is idempotent, so snapping here once and handing it one edge at a
    time (`ring_positions`) places the same bars.
    """
    points = list(ring)
    if any(is_inclined(points[i - 1], points[i]) for i in range(len(points))):
        points = [(snap(x), snap(y)) for x, y in points]
    return points


def ring_intervals(ring: Sequence[Point2], spacing_mm: float) -> list[int]:
    """Per edge of a `layout_ring`, the intervals `edge_positions` takes at `spacing_mm`.

    The same formula as `layout.edge_positions` (the fewest equal intervals no longer than
    the spacing), so a template can count its bars before placing any.
    """
    n = len(ring)
    out: list[int] = []
    for i in range(n):
        (ax, ay), (bx, by) = ring[i], ring[(i + 1) % n]
        out.append(max(1, math.ceil(math.hypot(bx - ax, by - ay) / spacing_mm - 1e-9)))
    return out


def ring_positions(ring: Sequence[Point2], spacing_mm: float) -> list[list[Point2]]:
    """Bars along every edge of a `layout_ring`, each edge without its end corner.

    Each edge goes to `edge_positions` as a two-vertex ring of already snapped points, so
    nothing is snapped twice and the work is linear in the bars placed.
    """
    n = len(ring)
    return [
        edge_positions((ring[i], ring[(i + 1) % n]), 0, None, spacing_mm)[:-1]
        for i in range(n)
    ]


def require_bar_count(p: Params, counts: Mapping[str, int]) -> None:
    """Refuse, before anything is built, a bar count over the cap (C3 review finding 1).

    `counts` maps each count parameter to the bars it places; the largest is named.
    """
    total = sum(counts.values())
    if total > MAX_TEMPLATE_BARS:
        name = max(counts, key=lambda k: counts[k])
        raise p.error(
            name,
            f"these parameters place {shown(total)} bars; a template places at most "
            f"{MAX_TEMPLATE_BARS}",
        )


# --- parameter readers ------------------------------------------------------------------


class Params:
    """Reads one template's parameter mapping, refusing every fault by name."""

    def __init__(
        self,
        template: str,
        data: Mapping[str, object],
        allowed: Sequence[str],
        *,
        prefix: str = "",
    ) -> None:
        self.template = template
        self.prefix = prefix
        if not isinstance(data, Mapping):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise self.error("params", f"params must be an object, got {type(data).__name__}")
        self._data = data
        unknown = sorted(str(k) for k in data if k not in allowed)
        if unknown:
            raise self.error(unknown[0], f"unknown parameter; known: {', '.join(allowed)}")

    def error(self, param: str, message: str) -> TemplateParamError:
        """The refusal of `param`, named `<prefix><param>` (`bottom.n` in a nested row)."""
        return TemplateParamError(self.template, f"{self.prefix}{param}", message)

    def _get(self, name: str) -> object:
        if name not in self._data:
            raise self.error(name, "required")
        return self._data[name]

    def has(self, name: str) -> bool:
        return self._data.get(name) is not None

    def length(self, name: str, default: float | None = None) -> float:
        """A positive, finite length in mm."""
        if default is not None and name not in self._data:
            return default
        return positive(self, name, number(self, name, self._get(name)))

    def count(self, name: str, minimum: int) -> int:
        return count_value(self, name, self._get(name), minimum)

    def designation(self, name: str, default: str | None = None) -> tuple[str, float]:
        """A vocabulary bar designation and its diameter."""
        if default is not None and self._data.get(name) is None:
            return default, DESIGNATIONS[default]
        return designation_value(self, name, self._get(name))

    def material(self, name: str) -> str:
        return name_value(self, name, self._get(name))

    def optional_material(self, name: str) -> str | None:
        value = self._data.get(name)
        return None if value is None else name_value(self, name, value)

    def point(self, name: str, default: Point2 | None = None) -> Point2:
        if default is not None and name not in self._data:
            return default
        return point_value(self, name, self._get(name))

    def choice(self, name: str, options: Sequence[str], default: str | None = None) -> str:
        """One of `options`; without a `default` the parameter is required."""
        value = self._get(name) if default is None else self._data.get(name, default)
        if not isinstance(value, str) or value not in options:
            raise self.error(name, f"must be one of {', '.join(options)}, got {shown(value)}")
        return value

    def mapping(self, name: str, *, required: bool) -> Mapping[str, object] | None:
        value = self._data.get(name)
        if value is None:
            if required:
                raise self.error(name, "required")
            return None
        if not isinstance(value, Mapping):
            raise self.error(name, f"must be an object, got {type(value).__name__}")
        return _str_keys(self, name, value)  # pyright: ignore[reportUnknownArgumentType]

    def sequence(self, name: str) -> Sequence[object]:
        value = self._get(name)
        if isinstance(value, str | bytes) or not isinstance(value, Sequence):
            raise self.error(name, f"must be a list, got {type(value).__name__}")
        return list(value)  # pyright: ignore[reportUnknownArgumentType]


def _str_keys(p: Params, name: str, value: Mapping[object, object]) -> Mapping[str, object]:
    out: dict[str, object] = {}
    for k, v in value.items():
        if not isinstance(k, str):
            raise p.error(name, f"keys must be strings, got {shown(k)}")
        out[k] = v
    return out


def number(p: Params, name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise p.error(name, f"must be a number in mm, got {shown(value)}")
    try:
        result = float(value)
    except OverflowError:
        raise p.error(name, "must be finite, got an int too large for a float") from None
    if not math.isfinite(result):
        raise p.error(name, f"must be finite, got {value!r}")  # a float always prints
    return result


def positive(p: Params, name: str, value: float) -> float:
    if not value > 0.0:
        raise p.error(name, f"must be positive, got {value:g}")
    return value


def count_value(p: Params, name: str, value: object, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise p.error(name, f"must be a whole number, got {shown(value)}")
    if value < minimum:
        raise p.error(name, f"must be {minimum} or more, got {shown(value)}")
    return value


def designation_value(p: Params, name: str, value: object) -> tuple[str, float]:
    if not isinstance(value, str) or value not in DESIGNATIONS:
        raise p.error(
            name, f"unknown bar designation {shown(value)}; known: {', '.join(DESIGNATIONS)}"
        )
    return value, DESIGNATIONS[value]


def name_value(p: Params, name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise p.error(name, f"must be a non-empty material name, got {shown(value)}")
    return value


def point_value(p: Params, name: str, value: object) -> Point2:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise p.error(name, f"must be [x_mm, y_mm], got {shown(value)}")
    items: list[object] = list(value)  # pyright: ignore[reportUnknownArgumentType]
    if len(items) != 2:
        raise p.error(name, f"must be [x_mm, y_mm], got {len(items)} values")
    return (number(p, name, items[0]), number(p, name, items[1]))
