"""DXF entities to an `apeCAD.section-seed` v2 and its report: the pure core of ADR 0042.

`dxf_import.py` reads the bytes with the `dxf` extra and hands each model-space entity here as
a `RawEntity`, in its OCS and its drawing units; this module imports no DXF library. It applies the
layer map (decision 2), reads faces, holes and bars (3, 6, 7), scales by the units (4), refuses
arcs and widths (5), checks each ring exactly (8), the caps (11) and the extent (12), and counts
every entity in the report (10). The self-replay of decision 9 needs a `Document`, which this
layer may not import, so `dxf_import.py` runs it.

Rings of one role are nested with `section/templates/hole_rules.py`'s exact region tests
(`clear_region` at gap 0, `interior`); no second interior test is written here. Every refusal
is a `DxfRefusedError` whose message starts `dxf <reason>:` (decision 14).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import cast

from apeCAD.section.designations import DESIGNATIONS
from apeCAD.section.draft import DRAFT_FRAME, DRAFT_UNITS, SEED_SCHEMA
from apeCAD.section.draft_v2 import SEED_SCHEMA_VERSION_V2
from apeCAD.section.dxf_options import (
    UNIT_FACTORS,
    DxfRefusedError,
    DxfTooLargeError,
    Json,
    LayerRole,
    choose_units,
    layer_map,
    require_chord,
    require_units,
)
from apeCAD.section.geometry import Point2, is_simple, signed_area
from apeCAD.section.layout import EXTENT_LIMIT_MM
from apeCAD.section.templates import hole_rules
from apeCAD.section.templates.plan import PlanCircle, PlanRing

BAR_TOLERANCE_MM = 0.01
"""A circle is designation D when |d - D| <= this (decision 7), never an argument. For d in
[D/2, 2D] the float subtraction is exact (Sterbenz): the test is exact on the scaled float."""
MAX_MAPPED_ENTITIES = 500
"""Most entities on mapped layers that are not skipped, counted before any geometry."""
MAX_VERTICES = 2000
"""Most polyline vertices on mapped layers, before any geometry and as bulges tessellate."""
MAX_RINGS = 100
"""Most polylines on mapped face layers (concrete, steel, void), counted by type before any is
read. Circles are not rings: they count under `MAX_MAPPED_ENTITIES` only."""

SKIPPED = ("DIMENSION", "HATCH", "LEADER", "MTEXT", "POINT", "TEXT", "WIPEOUT")
"""Entity types counted and never read on a mapped layer (decision 3). Nothing else is skipped."""

FACE_ROLES = ("concrete", "steel", "void")
_ZERO = Fraction(0)


@dataclass(frozen=True, slots=True)
class RawEntity:
    """One model-space entity as the reader found it: OCS coordinates, in drawing units.

    `points`, `bulges`, `closed`, `width` and `flat` describe a polyline (`flat` is False for
    a 3-D polyline or a mesh); `center` and `radius` a circle. Other types carry no geometry.
    """

    dxftype: str
    layer: str
    handle: str
    points: tuple[Point2, ...] = ()
    bulges: tuple[float, ...] = ()
    closed: bool = False
    width: bool = False
    flat: bool = True
    center: Point2 | None = None
    radius: float = 0.0
    extrusion: tuple[float, float, float] = (0.0, 0.0, 1.0)

    @property
    def name(self) -> str:
        return f"{self.dxftype} {self.handle} on layer {self.layer}"


@dataclass(frozen=True, slots=True)
class DxfSeed:
    """The seed, its report, and where each face boundary, hole and bar came from."""

    seed: Json
    report: Json
    faces: tuple[tuple[RawEntity, tuple[RawEntity, ...]], ...]
    bars: tuple[RawEntity, ...]


@dataclass(slots=True)
class _Shape:
    """A face ring or circle read from one entity, in scaled millimetres."""

    source: RawEntity
    role: LayerRole
    ring: tuple[Point2, ...] | None
    circle: tuple[Point2, float] | None
    twice_area: Fraction = _ZERO
    depth: int = 0
    parent: _Shape | None = None


# --- entities to shapes ----------------------------------------------------------------------


def _require_caps(mapped: Sequence[RawEntity], roles: dict[str, LayerRole]) -> None:
    if len(mapped) > MAX_MAPPED_ENTITIES:
        raise DxfTooLargeError(
            "too-large",
            f"{len(mapped)} entities on mapped layers; the import reads at most "
            f"{MAX_MAPPED_ENTITIES}",
        )
    rings = sum(
        1
        for e in mapped
        if e.dxftype in ("LWPOLYLINE", "POLYLINE") and roles[e.layer.casefold()].role in FACE_ROLES
    )
    if rings > MAX_RINGS:
        raise DxfTooLargeError(
            "too-large",
            f"{rings} polylines on face layers; the import reads at most {MAX_RINGS} rings",
        )
    _require_vertices(sum(len(e.points) for e in mapped))


def _require_vertices(count: int) -> None:
    if count > MAX_VERTICES:
        raise DxfTooLargeError(
            "too-large",
            f"{count} polyline vertices on mapped layers; the import reads at most {MAX_VERTICES}",
        )


def _xy(e: RawEntity, p: Point2, scale: float) -> Point2:
    """OCS to WCS for an extrusion of +Z or -Z (x negated: exact), scaled, z dropped."""
    x, y = p
    if e.extrusion[2] < 0:
        x = -x
    out = (x * scale + 0.0, y * scale + 0.0)  # + 0.0: no -0.0 in the seed
    if not (abs(out[0]) <= EXTENT_LIMIT_MM and abs(out[1]) <= EXTENT_LIMIT_MM):
        raise DxfRefusedError(
            "extent",
            f"{e.name} reaches ({out[0]!r}, {out[1]!r}) mm, outside ±{EXTENT_LIMIT_MM:g} mm; "
            "no origin is moved",
        )
    return out


def _require_disc_extent(e: RawEntity, centre: Point2, radius: float) -> None:
    """The whole circle, centre ± radius, lies within the extent, decided exactly (as
    `templates/holes.py` checks a circle hole)."""
    reach = [Fraction(abs(v)) + Fraction(radius) for v in centre]
    if not all(v <= EXTENT_LIMIT_MM for v in reach):
        raise DxfRefusedError(
            "extent",
            f"{e.name}, centre ({centre[0]!r}, {centre[1]!r}) mm and radius {radius!r} mm, "
            f"reaches outside ±{EXTENT_LIMIT_MM:g} mm; no origin is moved",
        )


@dataclass(slots=True)
class _Reading:
    """What the entity loop gathers, and the vertices counted so far against the cap."""

    shapes: list[_Shape]
    bars: list[tuple[RawEntity, LayerRole, Point2, float]]
    tessellated: list[Json]
    vertices: int


def _tessellate(e: RawEntity, chord: float, r: _Reading) -> tuple[list[Point2], int]:
    """The ring of a bulged polyline flattened to chords within `chord` (drawing units).

    Each arc's vertex count is counted against the cap before its vertices are made.
    """
    pts, n = e.points, len(e.points)
    out: list[Point2] = []
    segments = 0
    for i, (p, bulge) in enumerate(zip(pts, e.bulges, strict=True)):
        out.append(p)
        q = pts[(i + 1) % n]
        dx, dy = q[0] - p[0], q[1] - p[1]
        c = math.hypot(dx, dy)
        if bulge == 0.0 or c == 0.0:
            continue
        if not math.isfinite(bulge):
            raise DxfRefusedError("arc", f"{e.name} has a bulge of {bulge!r}")
        theta = 4.0 * math.atan(bulge)  # the included angle, CCW positive
        radius = c / (2.0 * math.sin(abs(theta) / 2.0))
        step = 2.0 * math.acos(max(-1.0, 1.0 - chord / radius))
        count = max(1, math.ceil(abs(theta) / step)) if step > 0.0 else MAX_VERTICES + 1
        r.vertices += count - 1
        _require_vertices(r.vertices)
        h = c * (1.0 - bulge * bulge) / (4.0 * bulge)  # centre offset along the left normal
        cx, cy = (p[0] + q[0]) / 2.0 - dy / c * h, (p[1] + q[1]) / 2.0 + dx / c * h
        a0 = math.atan2(p[1] - cy, p[0] - cx)
        for k in range(1, count):
            a = a0 + theta * k / count
            out.append((cx + radius * math.cos(a), cy + radius * math.sin(a)))
        segments += count
    return out, segments


def _read(e: RawEntity, role: LayerRole, scale: float, chord: float | None, r: _Reading) -> None:
    """Read one entity on a mapped layer, or refuse it by name (decisions 3, 5, 10, 12)."""
    if e.extrusion not in ((0.0, 0.0, 1.0), (0.0, 0.0, -1.0)):
        raise DxfRefusedError("tilted", f"{e.name} has extrusion {e.extrusion}, not ±Z")
    if e.dxftype == "CIRCLE" and e.center is not None:
        centre, radius = _xy(e, e.center, scale), e.radius * scale
        if not math.isfinite(radius):
            raise DxfRefusedError(
                "extent", f"{e.name} has radius {e.radius!r}, {radius!r} mm: not a finite length"
            )
        if not radius > 0.0:
            reason = "bar-size" if role.role == "bar" else "ring-not-simple"
            raise DxfRefusedError(reason, f"{e.name} has radius {e.radius!r}")
        _require_disc_extent(e, centre, radius)
        if role.role == "bar":
            r.bars.append((e, role, centre, radius * 2.0))
        else:
            r.shapes.append(_Shape(e, role, None, (centre, radius)))
        return
    if e.dxftype == "ARC":
        raise DxfRefusedError(
            "arc", f"{e.name}: an ARC never closes a ring, and LINE and ARC chaining is not read"
        )
    if e.dxftype not in ("LWPOLYLINE", "POLYLINE") or not e.flat:
        what = "a 3-D, mesh or fitted polyline" if not e.flat else "not read (decision 15)"
        raise DxfRefusedError("entity-unsupported", f"{e.name} is {what}")
    if e.width:  # before the bar layer's own refusal: a donut is the usual drawn bar
        raise DxfRefusedError("width", f"{e.name} has a width (a donut or a thick line)")
    if role.role == "bar":
        raise DxfRefusedError(
            "entity-unsupported", f"{e.name} is a polyline; a bar layer reads circles only"
        )
    if not e.closed:
        raise DxfRefusedError("open-outline", f"{e.name} is an open polyline")
    ring = list(e.points)
    if any(b != 0.0 for b in e.bulges):
        if chord is None:
            raise DxfRefusedError(
                "arc", f"{e.name} has a bulge; pass arc_chord_mm to tessellate it"
            )
        for p in ring:
            _xy(e, p, scale)  # the drawn vertices are finite and within the extent first
        ring, segments = _tessellate(e, chord / scale, r)
        r.tessellated.append({
            "handle": e.handle, "layer": e.layer, "vertices_in": len(e.points),
            "vertices_out": len(ring), "arc_segments": segments,
        })  # fmt: skip
    r.shapes.append(_Shape(e, role, tuple(_xy(e, p, scale) for p in ring), None))


# --- nesting (decision 6) and the exact ring checks (decision 8) --------------------------------


def _boundary(s: _Shape) -> PlanRing | PlanCircle:
    if s.ring is not None:
        return PlanRing(s.ring)
    centre, radius = cast(tuple[Point2, float], s.circle)
    return PlanCircle(centre, radius)


def relate(a: hole_rules.Region, b: hole_rules.Region) -> str:
    """How two closed regions lie, decided exactly: "disjoint" (gap > 0), "inside" (a in the
    interior of b), "contains" (b in the interior of a), or else "contact"."""
    if hole_rules.clear_region(a, b, _ZERO):
        return "disjoint"
    if hole_rules.interior(a, b):
        return "inside"
    if hole_rules.interior(b, a):
        return "contains"
    return "contact"


def _fbox(s: _Shape) -> tuple[float, float, float, float]:
    """A float box holding the shape: a ring's own floats; a circle's rounded outward."""
    if s.ring is not None:
        xs, ys = [p[0] for p in s.ring], [p[1] for p in s.ring]
        return (min(xs), min(ys), max(xs), max(ys))
    (x, y), r = cast(tuple[Point2, float], s.circle)
    lo, hi = -math.inf, math.inf
    return (
        math.nextafter(x - r, lo), math.nextafter(y - r, lo),
        math.nextafter(x + r, hi), math.nextafter(y + r, hi),
    )  # fmt: skip


def _check_ring(s: _Shape) -> None:
    """Exact simplicity and a non-zero exact area, before nesting (decision 8)."""
    if s.ring is None:
        return
    fault = hole_rules.exact_simplicity_fault(s.ring)
    if fault is not None:
        raise DxfRefusedError("ring-not-simple", f"{s.source.name}: {fault}")
    s.twice_area = hole_rules.exact_twice_area(s.ring)
    if s.twice_area == 0:
        raise DxfRefusedError("ring-not-simple", f"{s.source.name} has zero area")


def _nest(shapes: Sequence[_Shape]) -> None:
    """Set each shape's depth and parent among the shapes of one role (decision 6).

    Pairs whose float boxes are strictly apart are disjoint; every other pair is decided
    exactly. Containers of one shape are pairwise nested, so they form a chain and the parent
    is the one at depth - 1.
    """
    regions = [hole_rules.region(_boundary(s), s.source.name) for s in shapes]
    boxes = [_fbox(s) for s in shapes]
    order = sorted(range(len(shapes)), key=lambda k: boxes[k][0])
    containers: list[list[int]] = [[] for _ in shapes]
    for at, i in enumerate(order):
        for j in order[at + 1 :]:
            if boxes[j][0] > boxes[i][2]:
                break  # sorted by x_min: every later box starts right of this one
            if boxes[j][1] > boxes[i][3] or boxes[i][1] > boxes[j][3]:
                continue
            verdict = relate(regions[i], regions[j])
            if verdict == "contact":
                a, b = sorted((i, j))
                raise DxfRefusedError(
                    "ring-contact",
                    f"{shapes[a].source.name} and {shapes[b].source.name} touch or cross; "
                    "rings of one role are disjoint or strictly nested",
                )
            if verdict == "inside":
                containers[i].append(j)
            elif verdict == "contains":
                containers[j].append(i)
    for s, held in zip(shapes, containers, strict=True):
        s.depth = len(held)
        s.parent = next((shapes[k] for k in held if len(containers[k]) == s.depth - 1), None)


def _check_role(shapes: Sequence[_Shape]) -> None:
    """Nest one role's shapes, then refuse what nesting forbids (decision 6)."""
    for s in shapes:
        _check_ring(s)
    _nest(shapes)
    for s in shapes:
        parent = s.parent
        if parent is None:
            continue
        if s.role.role == "void":
            raise DxfRefusedError(
                "nested-void",
                f"{s.source.name} lies inside {parent.source.name}; a void holds no hole",
            )
        if s.depth % 2 == 1 and s.source.layer.casefold() != parent.source.layer.casefold():
            raise DxfRefusedError(
                "hole-layer",
                f"{s.source.name} is a hole of {parent.source.name}, which is on another "
                f"layer; a hole is read from its face's own layer",
            )


def _stored(s: _Shape) -> list[Point2] | None:
    """The ring in its stored order: a face CCW, a hole CW (ADR 0039 Errata 7), checked against
    the float `is_simple` and `signed_area` on that order (ADR 0040 Errata 16.1)."""
    if s.ring is None:
        return None
    ccw = s.depth % 2 == 0
    ring = list(s.ring) if (s.twice_area > 0) == ccw else list(s.ring[::-1])
    area = signed_area(ring)
    if not is_simple(ring) or area == 0.0 or (area > 0.0) != ccw:
        raise DxfRefusedError(
            "ring-not-simple",
            f"{s.source.name}: the float is_simple and signed_area disagree with the exact "
            f"tests on its stored order (float area {area!r} mm²)",
        )
    return ring


# --- bars (decision 7) ---------------------------------------------------------------------------


def bar_designation(diameter_mm: float) -> str | None:
    """The designation D with |d - D| <= BAR_TOLERANCE_MM, or None. At most one matches."""
    for name, size in DESIGNATIONS.items():
        if abs(diameter_mm - size) <= BAR_TOLERANCE_MM:
            return name
    return None


def _bar(e: RawEntity, role: LayerRole, xy: Point2, d: float, off: list[Json]) -> Json:
    designation = role.designation
    if designation is not None:
        if abs(d - DESIGNATIONS[designation]) > BAR_TOLERANCE_MM:
            off.append({
                "handle": e.handle, "layer": e.layer, "drawn_diameter_mm": d,
                "designation": designation,
            })  # fmt: skip
    else:
        designation = bar_designation(d)
        if designation is None:
            raise DxfRefusedError(
                "bar-size",
                f"{e.name} has diameter {d!r} mm, not within {BAR_TOLERANCE_MM:g} mm of a bar "
                f"size ({', '.join(DESIGNATIONS)}); name the layer's designation instead",
            )
    item: Json = {
        "label": None, "x_mm": xy[0], "y_mm": xy[1],
        "diameter_mm": DESIGNATIONS[designation], "designation": designation,
    }  # fmt: skip
    if role.material is not None:
        item["material"] = role.material
    return item


# --- the seed and the report -----------------------------------------------------------------


def _boundary_json(s: _Shape) -> Json:
    ring = _stored(s)
    if ring is not None:
        return {"kind": "ring", "ring_mm": [[x, y] for x, y in ring]}
    (x, y), r = cast(tuple[Point2, float], s.circle)
    return {"kind": "circle", "center_mm": [x, y], "radius_mm": r}


def _layers_report(
    entities: Sequence[RawEntity], layer_names: Sequence[str], roles: Mapping[str, LayerRole]
) -> list[Json]:
    """Every layer, by case-folded name: the table's spelling, else the first one drawn."""
    spelled: dict[str, str] = {}
    counts: dict[str, dict[str, int]] = {}
    for name in (*layer_names, *(e.layer for e in entities)):
        spelled.setdefault(name.casefold(), name)
        counts.setdefault(name.casefold(), {})
    for e in entities:
        per = counts[e.layer.casefold()]
        per[e.dxftype] = per.get(e.dxftype, 0) + 1
    out: list[Json] = []
    for key in sorted(spelled):
        role = roles.get(key)
        item: Json = {"name": spelled[key], "role": None if role is None else role.role}
        if role is not None:
            item["material"] = role.material
            if role.designation is not None:
                item["designation"] = role.designation
        item["counts"] = dict(sorted(counts[key].items()))
        out.append(item)
    return out


def seed_from_entities(
    entities: Sequence[RawEntity],
    *,
    layer_names: Sequence[str] = (),
    insunits: object = None,
    layers: object = None,
    units: object = None,
    arc_chord_mm: object = None,
) -> DxfSeed:
    """The seed v2 and report of a file's model-space `entities`, in file order.

    `layer_names` are the file's layer table, `insunits` its `$INSUNITS`. Refuses by name,
    as `DxfRefusedError` (and its `TOO_LARGE` and `INVALID_ARGUMENT` kinds), what the import
    does not read. The caller proves the replay (decision 9).
    """
    roles = layer_map(layers)
    chord, chosen = require_chord(arc_chord_mm), require_units(units)
    units_report, warnings = choose_units(chosen, insunits)
    scale = UNIT_FACTORS[cast(str, units_report["name"])]
    mapped = [e for e in entities if e.layer.casefold() in roles and e.dxftype not in SKIPPED]
    _require_caps(mapped, roles)
    reading = _Reading([], [], [], sum(len(e.points) for e in mapped))
    for e in mapped:
        _read(e, roles[e.layer.casefold()], scale, chord, reading)
    for role in FACE_ROLES:
        _check_role([s for s in reading.shapes if s.role.role == role])
    off: list[Json] = []
    bars = [_bar(e, role, xy, d, off) for e, role, xy, d in reading.bars]
    faces = [s for s in reading.shapes if s.depth % 2 == 0]
    if not faces and not bars:
        mapped_names = ", ".join(sorted(roles))
        raise DxfRefusedError(
            "no-geometry", f"no face or bar was read; the mapped layers are {mapped_names}"
        )
    holes = [[h for h in reading.shapes if h.parent is f and h.depth % 2 == 1] for f in faces]
    face_items = [
        {
            "label": None,
            "role": f.role.role,
            "material": f.role.material,
            "boundary": _boundary_json(f),
            "holes": [_boundary_json(h) for h in own],
        }
        for f, own in zip(faces, holes, strict=True)
    ]
    seed: Json = {
        "schema": SEED_SCHEMA,
        "version": SEED_SCHEMA_VERSION_V2,
        "units": DRAFT_UNITS,
        "frame": dict(DRAFT_FRAME),
        "section": {
            "faces": face_items,
            "wall_legs": [],
            "bars": bars,
            "hoops": [],
            "crossties": [],
            "circular_ties": [],
            "cover_guides": [],
        },
    }
    skipped: dict[str, int] = {}
    for e in entities:
        if e.layer.casefold() in roles and e.dxftype in SKIPPED:
            skipped[e.dxftype] = skipped.get(e.dxftype, 0) + 1
    report: Json = {
        "units": units_report,
        "entities": len(entities),
        "read": {
            "faces": len(faces),
            "holes": sum(len(own) for own in holes),
            "bars": len(bars),
        },
        "skipped": dict(sorted(skipped.items())),
        "unmapped": sum(1 for e in entities if e.layer.casefold() not in roles),
        "layers": _layers_report(entities, layer_names, roles),
        "tessellated": reading.tessellated,
        "bar_size_overrides": off,
        "warnings": warnings,
    }
    sources = tuple((f.source, tuple(h.source for h in own)) for f, own in zip(faces, holes))
    return DxfSeed(seed, report, sources, tuple(e for e, *_ in reading.bars))
