"""Template holes, version 2 (ADR 0040 Errata 13 to 18), on all seven templates: rect_column,
rect_hollow and polygon_column from C9-2b (apeSection#204); t_beam, circular_column, cft_round
and cft_rect from C9-2c (apeSection#205).

`section/templates/holes.py` is the step of Errata 13.2 around each v1 function. The oracles:

- *The reference step* (`reference`), written here apart from the product: it re-derives every
  refusal of 16.1 and 16.2 in the order of 13.2, places each hole itself, decides a ring's
  simplicity and area with `tests/_hole_rules_truth.py` (exact, built differently from
  `hole_rules.py`), runs the downstream float checks the general rule of 16.1 names, and judges
  R1 to R7 with the truth's `Truth`. It returns the refusal's parameter and its kind, or the
  plan the step must return: v1's plan with the stored holes appended.
- *One seeded, stratified generator* (`generated`) deals cases round strata: every shape fault,
  alone and several in one entry (extra keys beside a form, a bad centre with a bad radius, a
  short ring with bad vertices, a ring over the cap with an extra key), both caps either side
  of their limit, the malformed entries the caps must not count and the keyed ones they must, the
  extent either side of its limit, the float rings, v1 and unknown-key faults beside hole
  faults, and holes aimed at every limit R1 to R6 these templates draw (C9-2a's anchors) at
  contact, inside, outside, straddling, across, the float beside contact and +-1e-12 to +-1
  mm; each ring in a random start vertex and orientation, on every template, at `center_mm`
  offsets 0, 0.1, 1234.5 and 40000.3. On C9-2c's templates the holes are also aimed at the
  two faces of the circular tie (R7), at a CFT core's outline, and at t_beam's re-entrant
  corners and stirrup hull. Every outcome must equal the reference, through the expansion
  and, for every seventh case, through the op; a refusal must also carry its own template's
  name.
- *The break-once table* (`ROWS`): each mutant of the step (caps, order, refusal codes,
  placement, storage) and of each C9-2c template's wiring in `TEMPLATES` (its centring, its
  fields, its name, a v2 slot without the step) is a named row with a case that kills it,
  built in-process from the module's source; a row marked `fuzz` must also die under the
  generator.
- The hand cases of 18.3, the placement oracles of 18.4 and the op oracles of 18.5 for the
  templates, a v1 / v2 round trip, and the work-unit bound of 16.2.
"""

from __future__ import annotations

import json
import math
import random
import re
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from fractions import Fraction as Q
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest

import apeCAD.section.templates as templates_package
from _hole_rules_truth import (
    Core,
    Truth,
    all_closer,
    apart,
    jarvis,
    outline,
    point,
    qp,
    region,
    shape,
    strictly_inside,
    twice_area,
    within_hull,
)
from _hole_rules_truth import fault as ring_fault
from _section_fixtures_v2 import T_BEAM_PARAMS
from apeCAD import Document
from apeCAD.entities import SectionFace
from apeCAD.errors import OpArgumentError, TemplateLockedError
from apeCAD.geometry import XYZ
from apeCAD.ops import PointAt
from apeCAD.section.geometry import is_simple, signed_area
from apeCAD.section.lint import lint_section_v2
from apeCAD.section.templates import (
    TEMPLATES,
    cft_rect,
    cft_round,
    circular_column,
    expand,
    hole_rules,
    holes,
    polygon_column,
    rect_column,
    rect_hollow,
    t_beam,
)
from apeCAD.section.templates.plan import (
    Plan,
    PlanBoundary,
    PlanCircle,
    PlanRing,
    TemplateParamError,
)
from apeCAD.section_draft import section_draft
from test_section_template_hole_rules import BASES as RULE_BASES
from test_section_template_hole_rules import CLEAR, FAMILIES, MODES, has, has_corner, one_hole

Json = dict[str, object]
XY = tuple[float, float]

FIELDS = {
    rect_column.TEMPLATE: rect_column.FIELDS,
    rect_hollow.TEMPLATE: rect_hollow.FIELDS,
    polygon_column.TEMPLATE: polygon_column.FIELDS,
    t_beam.TEMPLATE: t_beam.FIELDS,  # C9-2c's four
    circular_column.TEMPLATE: circular_column.FIELDS,
    cft_round.TEMPLATE: cft_round.FIELDS,
    cft_rect.TEMPLATE: cft_rect.FIELDS,
}
CENTRED = {name: name != polygon_column.TEMPLATE for name in FIELDS}
C9_2C = (t_beam.TEMPLATE, circular_column.TEMPLATE, cft_round.TEMPLATE, cft_rect.TEMPLATE)
BASES = dict(RULE_BASES)  # rc, rc_all, rc_thin, pc, rh, and C9-2c's tb, cc, cr, ct
OFFSETS = (0.0, 0.1, 1234.5, 40000.3)
LIMIT = 2.0**20  # the ADR 0032 extent
SEED = 20261123
CASES = 3000

# The rings of Errata 18.4, given as section coordinates on polygon_column, and one more: a
# ring whose float signed_area is exactly 0.0 although it is exactly clockwise and float-simple,
# found by a seeded search (C9-2b), so that `draft/section.py::_boundary` would reverse it.
FLOAT_ORIENTATION_WRONG = (
    (39999.56872848823, 40000.99486747388), (40260.93513113888, 39758.30007034527),
    (40527.11796644146, 39511.13291895272),
)  # fmt: skip
WRONG_ONCE_REVERSED = (
    (-0.003034104320175181, -0.14196400488515), (-39578.90871125873, -28092.58529687345),
    (-0.00039359544240611885, -0.14008981597695389), (-0.000311942809276937, -0.14003186030764175),
)  # fmt: skip
FLOAT_SIMPLICITY_WRONG = (
    (0.005211328185895844, -0.061594004755554), (1329.183505433143, 219.15109444252522),
    (3091.0945986391544, 509.73157507462827),
)  # fmt: skip
FLOAT_AREA_ZERO = (
    (612195.0839090112, 329591.1600426609), (611341.6183843209, 329871.4882308378),
    (612283.487339991, 329562.1231654795),
)  # fmt: skip
FLOAT_RINGS = (
    FLOAT_ORIENTATION_WRONG,
    WRONG_ONCE_REVERSED,
    FLOAT_SIMPLICITY_WRONG,
    FLOAT_AREA_ZERO,
)


def params_at(base: str, off: float, **extra: object) -> tuple[str, Json]:
    """A base's template and params, moved to (off, -off), with `extra` keys."""
    template, params = BASES[base]
    moved: Json = dict(params)
    if template == "polygon_column":
        ring = cast(list[list[float]], params["ring"])
        moved["ring"] = [[x + off, y - off] for x, y in ring]
    else:
        moved["center_mm"] = [off, -off]
    return template, {**moved, **extra}


def centre_of(template: str, params: Mapping[str, object]) -> XY:
    if not CENTRED[template]:
        return (0.0, 0.0)
    cx, cy = cast(Sequence[float], params.get("center_mm", (0.0, 0.0)))
    return (float(cx), float(cy))


# --- the reference step ----------------------------------------------------------------------


def _is_list(v: object) -> bool:
    return isinstance(v, list | tuple)


def _finite(v: object) -> bool:
    if isinstance(v, bool) or not isinstance(v, int | float):
        return False
    try:
        return math.isfinite(float(v))
    except OverflowError:
        return False


def _xy(v: object) -> bool:
    return _is_list(v) and len(cast(Sequence[object], v)) == 2 and all(map(_finite, v))  # type: ignore[arg-type]


@dataclass(frozen=True)
class Refused:
    param: str
    kind: str
    detail: str = ""


Outcome = Refused | Plan


def reference(template: str, params: object) -> Outcome:
    """What version 2 of `template` must do with `params`: Errata 13.2, 16 and 17 re-derived."""
    if not isinstance(params, Mapping):
        return Refused("params", "params")
    data = cast(Mapping[str, object], params)
    known = (*FIELDS[template], "holes")
    unknown = sorted(str(k) for k in data if k not in known)
    if unknown:
        return Refused(unknown[0], "unknown")
    entries: Sequence[object] = ()
    if "holes" in data:
        if not _is_list(data["holes"]):
            return Refused("holes", "list")
        entries = cast(Sequence[object], data["holes"])
    if len(entries) > 32:
        return Refused("holes", "cap-holes")
    counted = [
        cast(Mapping[str, object], e)["ring_mm"] for e in entries
        if isinstance(e, Mapping) and _is_list(cast(Mapping[str, object], e).get("ring_mm"))
    ]  # fmt: skip
    if sum(len(cast(Sequence[object], r)) for r in counted) > 256:
        return Refused("holes", "cap-vertices")
    given: list[tuple[XY, float] | tuple[XY, ...]] = []
    for k, entry in enumerate(entries):
        w = f"holes[{k}]"
        if not isinstance(entry, Mapping):
            return Refused(w, "object")
        e = cast(Mapping[object, object], entry)
        extra = sorted(str(key) for key in e if key not in ("center_mm", "radius_mm", "ring_mm"))
        if extra:
            return Refused(f"{w}.{extra[0]}", "key")
        if set(e) == {"center_mm", "radius_mm"}:
            c, r = e["center_mm"], e["radius_mm"]
            if not _xy(c):
                return Refused(f"{w}.center_mm", "point")
            if not (_finite(r) and float(cast(float, r)) > 0):
                return Refused(f"{w}.radius_mm", "number")
            cx_, cy_ = cast(Sequence[float], c)
            given.append(((float(cx_), float(cy_)), float(cast(float, r))))
        elif set(e) == {"ring_mm"}:
            ring = e["ring_mm"]
            if not _is_list(ring):
                return Refused(f"{w}.ring_mm", "ring-list")
            vertices = cast(Sequence[object], ring)
            if len(vertices) < 3:
                return Refused(f"{w}.ring_mm", "ring-count")
            for i, v in enumerate(vertices):
                if not _xy(v):
                    return Refused(f"{w}.ring_mm[{i}]", "point")
            given.append(
                tuple((float(x), float(y)) for x, y in cast(Sequence[Sequence[float]], vertices))
            )
        else:
            return Refused(w, "form")
    try:
        v1 = expand(template, {k: v for k, v in data.items() if k != "holes"}, 1)
    except TemplateParamError as exc:
        return Refused(exc.param, "v1", str(exc))
    if not given:
        return v1
    cx, cy = centre_of(template, data)
    centred = CENTRED[template]
    stored: list[PlanBoundary] = []
    for k, g in enumerate(given):
        w = f"holes[{k}]"
        if len(g) == 2 and isinstance(g[1], float):  # a circle: (centre, radius)
            (x, y), r = cast(tuple[XY, float], g)
            if centred:
                x, y = cx + x, cy + y
            box = ((x - r, y - r), (x + r, y + r))
            if not all(abs(px) <= LIMIT and abs(py) <= LIMIT for px, py in box):
                return Refused(w, "extent")
            stored.append(PlanCircle((x, y), r))
            continue
        ring = tuple((cx + x, cy + y) if centred else (x, y) for x, y in cast(tuple[XY, ...], g))
        if not all(abs(px) <= LIMIT and abs(py) <= LIMIT for px, py in ring):
            return Refused(w, "extent")
        why = ring_fault(ring)
        if why is not None:
            return Refused(f"{w}.ring_mm", "simple", why)
        twice = twice_area(ring)
        if twice == 0:
            return Refused(f"{w}.ring_mm", "zero")
        kept = ring if twice < 0 else ring[::-1]
        # 16.1's general rule: the consumers' own float checks, on the order to be stored.
        # `require_simple` is `is_simple`'s predicate (geometry.py::_simplicity_fault), so the
        # third check can never fail alone.
        if not is_simple(kept):
            return Refused(f"{w}.ring_mm", "float-simple")
        if signed_area(kept) > 0.0:
            return Refused(f"{w}.ring_mm", "float-ccw")
        if not signed_area(kept) < 0.0:
            return Refused(f"{w}.ring_mm", "float-reverse")
        stored.append(PlanRing(kept))
    verdict = Truth(v1).verdict(stored)
    if verdict is not None:
        return Refused(f"holes[{verdict[0]}]", f"R{verdict[1]}")
    (i,) = (i for i, f in enumerate(v1.faces) if f.role == "concrete")
    faces = list(v1.faces)
    faces[i] = replace(faces[i], holes=(*faces[i].holes, *stored))
    return replace(v1, faces=tuple(faces))


# --- the product, and its refusal read back as a kind -----------------------------------------

_HOLE_KINDS: tuple[tuple[str, str], ...] = (
    ("must be a list of holes", "list"),
    ("ring vertices across the holes; a template takes at most", "cap-vertices"),
    ("holes; a template takes at most", "cap-holes"),
    ("must be an object, {center_mm, radius_mm} or {ring_mm}", "object"),
    ("unknown key; known: center_mm, radius_mm, ring_mm", "key"),
    ("must hold exactly one form", "form"),
    ("must be a list of [x_mm, y_mm] vertices", "ring-list"),
    ("needs 3 or more vertices", "ring-count"),
    ("sections stay within", "extent"),
    ("has zero area", "zero"),
    ("the float is_simple (plan.py", "float-simple"),
    ("the float signed_area (plan.py", "float-ccw"),
    ("the float require_simple (draft/section.py", "float-require"),
    ("the float signed_area (draft/section.py::_boundary) would reverse it", "float-reverse"),
)
_NUMBER = ("must be a number in mm", "must be finite")


def kind_of(exc: TemplateParamError) -> Refused:
    """The refusal as (param, kind): the kind read from the message's own words."""
    body = str(exc)[len(f"{exc.template}: {exc.param}: ") :]
    param = exc.param
    if not param.startswith("holes"):
        if body.startswith("unknown parameter; known: "):
            return Refused(param, "unknown")
        return Refused(param, "params" if param == "params" else "v1", str(exc))
    if len(body) > 3 and body[0] == "R" and body[1] in "1234567" and body[2] == ":":
        return Refused(param, body[:2])
    if body.startswith("is not simple: "):
        return Refused(param, "simple", body[len("is not simple: ") :])
    for words, kind in _HOLE_KINDS:
        if words in body:
            return Refused(param, kind)
    if param.endswith(("center_mm", "]")) and body.startswith(("must be [x_mm, y_mm]", *_NUMBER)):
        return Refused(param, "point")
    if param.endswith("radius_mm") and body.startswith((*_NUMBER, "must be positive")):
        return Refused(param, "number")
    return Refused(param, "?", body)


Step = Callable[[str, object], Plan]


def product(template: str, params: object) -> Plan:
    return expand(template, cast(Mapping[str, object], params), 2)


def run(step: Step, template: str, params: object) -> Outcome | tuple[str, str]:
    try:
        return step(template, params)
    except TemplateParamError as exc:
        if exc.template != template or not str(exc).startswith(f"{template}: {exc.param}: "):
            return ("misnamed", str(exc))  # 16: the message starts `<template>: <param>:`
        return kind_of(exc)
    except Exception as exc:  # an unnamed refusal or a crash: never what the reference says
        return ("unnamed", f"{type(exc).__name__}: {exc}")


# --- the generator ----------------------------------------------------------------------------


def circle(c: XY, r: float) -> Json:
    return {"center_mm": [c[0], c[1]], "radius_mm": r}


def ring_entry(points: Sequence[XY]) -> Json:
    return {"ring_mm": [[x, y] for x, y in points]}


def entry_of(hole: PlanBoundary, centre: XY, centred: bool) -> Json:
    """A hole placed in section floats, as a params entry: offsets on a centred template."""
    cx, cy = centre if centred else (0.0, 0.0)
    if isinstance(hole, PlanCircle):
        (x, y), r = hole.center_mm, hole.radius_mm
        return circle((x - cx, y - cy) if centred else (x, y), r)
    return ring_entry([(x - cx, y - cy) if centred else (x, y) for x, y in hole.points_mm])


def turned(points: Sequence[XY], rng: random.Random) -> list[XY]:
    """A random start vertex and a random orientation."""
    k = rng.randrange(len(points))
    pts = list(points[k:]) + list(points[:k])
    return pts[::-1] if rng.random() < 0.5 else pts


def regular(n: int, centre: XY, radius: float) -> list[XY]:
    cx, cy = centre
    return [
        (cx + radius * math.cos(2 * math.pi * i / n), cy + radius * math.sin(2 * math.pi * i / n))
        for i in range(n)
    ]


def box_of(boundary: PlanBoundary) -> list[XY]:
    """A ring's vertices, or the two far corners of a circle's box."""
    if isinstance(boundary, PlanCircle):
        (x, y), r = boundary.center_mm, boundary.radius_mm
        return [(x - r, y - r), (x + r, y + r)]
    return list(boundary.points_mm)


@cache
def safe_spots(base: str, off: float) -> tuple[XY, ...]:
    """Offsets (on pc: section points) where a 1 mm circle clears every rule, by the truth."""
    template, params = params_at(base, off)
    plan = expand(template, params, 1)
    centre = centre_of(template, params)
    truth = Truth(plan)
    corners = [p for f in plan.faces for p in box_of(f.boundary)]
    xs, ys = [p[0] for p in corners], [p[1] for p in corners]
    out: list[XY] = []
    for i in range(1, 40):
        for j in range(1, 40):
            x = min(xs) + (max(xs) - min(xs)) * i / 40
            y = min(ys) + (max(ys) - min(ys)) * j / 40
            if truth.verdict([PlanCircle((x, y), 1.0)]) is None:
                out.append((x - centre[0], y - centre[1]) if CENTRED[template] else (x, y))
    return tuple(out)


def valid_holes(base: str, off: float, n: int, rng: random.Random) -> list[Json]:
    """n circles of 1 mm at distinct safe spots (each clears the others: spots are apart)."""
    return [circle(p, 1.0) for p in rng.sample(safe_spots(base, off), n)]


NAN, INF = math.nan, math.inf
BAD_POINTS: tuple[object, ...] = (
    None, 5, "00", [0], [0, 0, 0], [NAN, 0], [0, INF], [True, 0], ["0", 0], [10**400, 0],
    {"x": 0, "y": 0},
)  # fmt: skip
BAD_RADII: tuple[object, ...] = (0, -1, -0.0, NAN, INF, True, "1", None, 10**400, [1])
TRI = [[0, 0], [1, 0], [0, 1]]
BAD_ENTRIES: tuple[object, ...] = (
    None, 5, "ring", TRI, True, 1.5,  # not an object
    {"center_mm": [0, 0], "radius_mm": 1, "zz": 1}, {"ring_mm": TRI, "Ring_mm": 1},
    {"a": 1}, {"center_mm": [0, 0], "radius_mm": 1, "ring_mm": TRI, "q": 0},  # unknown keys
    {}, {"center_mm": [0, 0]}, {"radius_mm": 1}, {"center_mm": [0, 0], "ring_mm": TRI},
    {"center_mm": [0, 0], "radius_mm": 1, "ring_mm": TRI}, {"radius_mm": 1, "ring_mm": TRI},
    *({"center_mm": p, "radius_mm": 1} for p in BAD_POINTS),
    *({"center_mm": [0, 0], "radius_mm": r} for r in BAD_RADII),
    {"ring_mm": "x" * 300}, {"ring_mm": 7}, {"ring_mm": None}, {"ring_mm": {"0": [0, 0]}},
    {"ring_mm": []}, {"ring_mm": [[0, 0]]}, {"ring_mm": [[0, 0], [1, 1]]},
    *({"ring_mm": [[0, 0], [1, 0], p]} for p in BAD_POINTS),
    {"ring_mm": [[0, 0], [NAN, 0], [1, 1], "x"]},
    # Three refusal orders of 16.1 and 16.2 (round 2 of apeCAD #75): a ring over the vertex cap
    # with an unknown key is counted (`holes`, not `holes[0].zz`); a circle names its centre
    # before its radius; a ring names its count before its vertices.
    {"ring_mm": [[0, 0]] * 300, "zz": 1}, {"center_mm": None, "radius_mm": 0},
    {"ring_mm": [[0, 0], "x"]},
)  # fmt: skip
BAD_LISTS: tuple[object, ...] = (None, "abc", 5, {"center_mm": [0, 0], "radius_mm": 1}, True)
BAD_V1 = (
    ("b", -1), ("nx", 1), ("bar", "Ø99"), ("cover", 0), ("material", ""), ("bw", -1),
    ("hf", 900), ("diameter", 0), ("n_bars", 2), ("tie_kind", "coil"), ("t", 300),
    ("steel_material", ""),
)  # fmt: skip


@dataclass(frozen=True)
class Case:
    stratum: str
    template: str
    params: Json
    rule: int = 0  # an aimed case: the rule its last hole was aimed at
    family: str = ""  # and the family of C9-2a's anchors it was aimed by


EXTRA_KEYS = ("zz", "a", "Ring_mm", "radius", "q")
GOOD_VERTICES: tuple[object, ...] = ([0, 0], [1, 0], [0, 1], [2.5, 3.0])


def compound(rng: random.Random) -> Json:
    """An entry whose fields are drawn apart, so several may be bad at once: a circle with its
    centre and radius each good or bad, or a ring of 0 to 300 vertices each good or bad (short
    rings with bad vertices, rings over the vertex cap); and, beside either form, sometimes one
    or two unknown keys. The first fault 13.2 and 16.1 name is the refusal."""
    entry: Json
    if rng.random() < 0.5:
        entry = {
            "center_mm": rng.choice(([0.5, 0.5], *BAD_POINTS)),
            "radius_mm": rng.choice((1.0, *BAD_RADII)),
        }
    else:
        n = rng.choice((0, 1, 2, 2, 3, 4, 57, 300))
        bad = rng.random() < 0.6
        entry = {"ring_mm": [
            rng.choice(BAD_POINTS) if bad and rng.random() < 0.5 else rng.choice(GOOD_VERTICES)
            for _ in range(n)
        ]}  # fmt: skip
    if rng.random() < 0.4:
        for key in rng.sample(EXTRA_KEYS, rng.choice((1, 2))):
            entry[key] = rng.choice((1, None, [0, 0]))
    return entry


def bad_entry(rng: random.Random) -> object:
    return rng.choice(BAD_ENTRIES) if rng.random() < 0.5 else compound(rng)


def _shape(rng: random.Random, base: str, off: float) -> Json:
    good = valid_holes(base, off, rng.choice((0, 1, 2, 3)), rng)
    k = rng.randrange(len(good) + 1)
    bad = [*good[:k], bad_entry(rng), *good[k:]]
    if rng.random() < 0.3:  # a later fault too: the earlier one is named
        bad.append(bad_entry(rng))
    return {"holes": bad}


def _caps(rng: random.Random, base: str, off: float) -> Json:
    spots = safe_spots(base, off)
    pick = rng.choice(("holes", "vertices", "uncounted", "not-objects", "both"))
    if pick == "holes":
        n = rng.choice((31, 32, 33, 40))
        out: list[object] = [circle(p, 1.0) for p in rng.sample(spots, n)]
        if rng.random() < 0.3:
            out[rng.randrange(n)] = rng.choice(BAD_ENTRIES)  # the cap comes first
        return {"holes": out}
    if pick == "vertices":
        total = rng.choice((255, 256, 257, 300))
        sizes = rng.choice(([total], [total - 3, 3], [100, total - 100]))
        out = [ring_entry(turned(regular(n, spots[i * 7 % len(spots)], 0.6), rng))
               for i, n in enumerate(sizes)]  # fmt: skip
        out += [circle(p, 1.0) for p in rng.sample(spots[1::7], rng.choice((0, 5)))]
        return {"holes": out}
    if pick == "uncounted":  # only list-valued ring_mm of object entries count, whatever else
        junk = rng.choice((  # they hold: the last four are counted (or hold no ring)
            {"ring_mm": "x" * 300}, {"ring_mm": {"k": [[0, 0]] * 300}},
            [["ring_mm", [[0, 0]] * 300]], {"center_mm": [0, 0], "radius_mm": 1},
            {"ring_mm": [[0, 0]] * 300, "zz": 1}, {"ring_mm": [[0, 0]] * 57, "zz": 1},
            {"center_mm": None, "radius_mm": 0}, {"ring_mm": [[0, 0], "x"]},
        ))  # fmt: skip
        n = rng.choice((200, 256))
        return {"holes": [ring_entry(regular(n, spots[0], 0.6)), junk]}
    if pick == "not-objects":
        return {"holes": [rng.choice((None, 1, "x", [0, 0]))] * rng.choice((32, 33))}
    return {"holes": [{"ring_mm": [None] * 300}]}  # counted although malformed


def _extent(rng: random.Random, template: str, params: Json) -> Json:
    cx, cy = centre_of(template, params)
    edge = rng.choice((LIMIT, -LIMIT)) + rng.choice((-1.0, 0.0, 1.0, 1e-9, -1e-9, 1e300))
    edge = math.nextafter(edge, rng.choice((INF, -INF))) if rng.random() < 0.3 else edge
    if rng.random() < 0.5:
        r = rng.choice((5.0, 0.5))
        x = edge - math.copysign(r, edge) if rng.random() < 0.5 else edge
        return {"holes": [circle((x - cx, 0.0 - cy) if CENTRED[template] else (x, 0.0), r)]}
    pts = [(edge, 0.0), (edge - math.copysign(10.0, edge), 0.0), (edge, 10.0)]
    pts = [(x - cx, y - cy) for x, y in pts] if CENTRED[template] else pts
    return {"holes": [ring_entry(turned(pts, rng))]}


def _float_ring(rng: random.Random) -> list[XY]:
    if rng.random() < 0.4:
        return list(rng.choice(FLOAT_RINGS))
    # A thin triangle far out: its float shoelace may disagree with the exact one.
    c = (
        rng.choice((1.0, -1.0)) * rng.uniform(1e5, 1e6),
        rng.choice((1.0, -1.0)) * rng.uniform(1e5, 1e6),
    )
    length, angle = rng.uniform(1.0, 2000.0), rng.uniform(0.0, 2 * math.pi)
    u = (math.cos(angle), math.sin(angle))
    h, t = rng.uniform(-1.0, 1.0) * 10 ** rng.uniform(-12, -4), rng.random()
    return [c, (c[0] + length * u[0], c[1] + length * u[1]),
            (c[0] + t * length * u[0] - h * u[1], c[1] + t * length * u[1] + h * u[0])]  # fmt: skip


NOT_SIMPLE: tuple[tuple[XY, ...], ...] = (
    ((0, 0), (4, 4), (4, 0), (0, 4)),  # a bow-tie
    ((0, 0), (4, 0), (4, 4), (2, 0), (0, 4)),  # the T-touch ring of C9-2a
    ((0, 0), (4, 0), (4, 4), (4, 0)),  # a repeated vertex
    ((0, 0), (4, 0), (2, 0), (2, 3)),  # a spike back along an edge
    ((0, 0), (2, 0), (4, 0)),  # straight
    ((0, 0), (4, 0), (4, 4), (0, 4), (2, 2), (2, -1)),  # an edge crossing back
)


def _not_simple(rng: random.Random, base: str, off: float) -> Json:
    """A ring that is not simple once placed: as given, or only because placement at a large
    `center_mm` rounds two distinct offsets to one float."""
    template, params = params_at(base, off)
    sx, sy = rng.choice(safe_spots(base, off))
    if rng.random() < 0.7:
        scale = rng.choice((0.25, 1.0, 1e-3))
        pts = [(sx + scale * x, sy + scale * y) for x, y in rng.choice(NOT_SIMPLE)]
    else:  # offsets 1e-12 apart: distinct as given, one float apart or none once placed
        tiny = rng.choice((1e-12, 1e-13, 4e-12))
        pts = [(sx, sy), (sx + tiny, sy), (sx + 3.0, sy + 3.0), (sx, sy + 3.0)]
    return {
        "holes": [*valid_holes(base, off, rng.choice((0, 1)), rng), ring_entry(turned(pts, rng))]
    }


def _aimed(
    rng: random.Random, base: str, off: float, mode: str, only: Sequence[str] = ()
) -> tuple[Json, int, str] | None:
    """Holes aimed at one limit of one rule (C9-2a's anchors), earlier holes that pass first;
    the last hole's family drawn from `only` when it is given."""
    template, params = params_at(base, off)
    plan = expand(template, params, 1)
    centre = centre_of(template, params)
    truth = Truth(plan)
    families = [
        f for f, (_, needs) in FAMILIES.items()
        if all(has(plan, n) for n in needs)
        and not (f.endswith(("@corner", "@line")) and not has_corner(plan, f))
    ]  # fmt: skip
    priors: list[PlanBoundary] = []
    for _ in range(rng.choice((0, 0, 0, 1, 2))):
        for _try in range(4):
            pick = rng.choice([f for f in families if priors or not f.startswith("prior")])
            hole = one_hole(plan, pick, rng.choice(CLEAR), rng, priors)
            if hole is not None and truth.verdict([*priors, hole]) is None:
                priors.append(hole)
                break
    pool = [f for f in families if priors or not f.startswith("prior")]
    family = rng.choice([f for f in pool if f in only] if only else pool)
    last = one_hole(plan, family, mode, rng, priors)
    if last is None:
        return None
    entries = [entry_of(h, centre, CENTRED[template]) for h in (*priors, last)]
    return {"holes": entries}, FAMILIES[family][0], family


# C9-2c: t_beam's two re-entrant corners, where the flange meets the web. The outline's
# "@corner" and "@line" families seen from the concrete aim at its reflex corners (`spot`).
RE_ENTRANT = ("outline-in@corner", "outline-cover@corner", "outline-in@line", "outline-cover@line")
STRATA = (
    "aimed", "aimed", "aimed", "aimed", "shape", "shape", "list", "caps", "caps", "extent",
    "float", "float", "v1", "unknown", "far", "simple", "corner",
)  # fmt: skip


def generated(n: int, seed: int) -> list[Case]:
    rng = random.Random(seed)
    out: list[Case] = []
    i = 0
    while len(out) < n:
        stratum = STRATA[i % len(STRATA)]
        mode = MODES[(i // len(STRATA)) % len(MODES)]
        base = {"float": "pc", "corner": "tb"}.get(stratum, sorted(BASES)[(i // 3) % len(BASES)])
        i += 1
        off = rng.choice(OFFSETS)
        template, params = params_at(base, off)
        extra: Json | None
        rule, family = 0, ""
        if stratum in ("aimed", "corner"):
            only = RE_ENTRANT if stratum == "corner" else ()
            aimed = _aimed(rng, base, off, mode, only)
            extra, rule, family = (None, 0, "") if aimed is None else aimed
        elif stratum == "shape":
            extra = _shape(rng, base, off)
        elif stratum == "list":
            extra = {"holes": rng.choice(BAD_LISTS)}
        elif stratum == "caps":
            extra = _caps(rng, base, off)
        elif stratum == "extent":
            extra = _extent(rng, template, params)
        elif stratum == "float":
            holes_ = [ring_entry(turned(_float_ring(rng), rng))]
            extra = {"holes": [*valid_holes(base, off, rng.choice((0, 1)), rng), *holes_]}
        elif stratum == "v1":
            name, value = rng.choice([b for b in BAD_V1 if b[0] in FIELDS[template]])
            hole = rng.choice((*valid_holes(base, off, 1, rng), rng.choice(BAD_ENTRIES)))
            extra = {name: value, "holes": [hole]}
        elif stratum == "simple":
            extra = _not_simple(rng, base, off)
        elif stratum == "unknown":
            # A CFT places no bars, so its v2 refuses `bar_material` at step 1, an unknown key,
            # before any hole or v1 check (13.2; v1 names it "places no bars", Errata 11.3).
            cft = "bar_material" not in FIELDS[template]
            key = "bar_material" if cft and rng.random() < 0.5 else "zz"
            some = ([rng.choice(BAD_ENTRIES)], None, [], valid_holes(base, off, 1, rng))
            extra = {key: rng.choice((1, "A630")), "holes": rng.choice(some)}
        else:  # far: valid holes only, accepted
            extra = {"holes": valid_holes(base, off, rng.choice((1, 2, 4)), rng)}
        if extra is not None:
            out.append(Case(stratum, template, {**params, **extra}, rule, family))
    return out


def at_re_entrant_corner(case: Case, within: float) -> bool:
    """The case's last hole, placed, comes within `within` mm of a reflex vertex of the outline
    (a classification for the report, in floats)."""
    plan = expand(case.template, {k: v for k, v in case.params.items() if k != "holes"}, 1)
    ring = cast(PlanRing, plan.faces[0].boundary).points_mm  # counter-clockwise
    n = len(ring)
    reflex = [
        b for a, b, c in ((ring[i - 1], ring[i], ring[(i + 1) % n]) for i in range(n))
        if (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) < 0
    ]  # fmt: skip
    cx, cy = centre_of(case.template, case.params)
    last = cast(list[Json], case.params["holes"])[-1]
    if "radius_mm" in last:
        x, y = cast(list[float], last["center_mm"])
        r = float(cast(float, last["radius_mm"]))
        return any(math.dist((cx + x, cy + y), v) - r <= within for v in reflex)
    pts = [(cx + x, cy + y) for x, y in cast(list[list[float]], last["ring_mm"])]
    return any(
        _seg_dist(v, pts[i - 1], pts[i]) <= within for v in reflex for i in range(len(pts))
    )


def _seg_dist(p: XY, a: XY, b: XY) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = 0.0 if dx == dy == 0 else ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)
    t = min(1.0, max(0.0, t))
    return math.dist(p, (a[0] + t * dx, a[1] + t * dy))


@cache
def fuzz() -> tuple[tuple[Case, Outcome], ...]:
    return tuple((case, reference(case.template, case.params)) for case in generated(CASES, SEED))


def mismatches(step: Step, judged: Sequence[tuple[Case, Outcome]]) -> list[str]:
    bad: list[str] = []
    for case, expected in judged:
        got = run(step, case.template, case.params)
        if got != expected:
            bad.append(f"{case.stratum} {case.template}: got {got}, want {expected}")
    return bad


def test_the_fuzz_agrees_with_the_reference_and_reaches_every_kind() -> None:
    judged = fuzz()
    bad = mismatches(product, judged)
    assert not bad, f"{len(bad)} of {len(judged)} differ:\n" + "\n".join(bad[:15])
    kinds = Counter(o.kind if isinstance(o, Refused) else "accepted" for _, o in judged)
    per_stratum = Counter((c.stratum, o.kind if isinstance(o, Refused) else "accepted")
                          for c, o in judged)  # fmt: skip
    print(f"\n{len(judged)} cases: {dict(sorted(kinds.items()))}")
    print("\n".join(f"  {s}: {k} {n}" for (s, k), n in sorted(per_stratum.items())))
    # Every refusal of 16 is reached, R1 to R7, and acceptance. "zero" (an exactly simple ring
    # has a non-zero area) and "float-require" (`require_simple` is `is_simple`'s predicate)
    # cannot be reached; the PR body of C9-2b argues both.
    wanted = {
        "list", "cap-holes", "cap-vertices", "object", "key", "form", "point", "number",
        "ring-list", "ring-count", "extent", "simple", "float-simple", "float-ccw",
        "float-reverse", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "v1", "unknown", "accepted",
    }  # fmt: skip
    assert wanted <= set(kinds), wanted - set(kinds)
    # C9-2c: each of its templates is reached by every stratum, and refuses what it draws.
    per_template = Counter((c.template, o.kind if isinstance(o, Refused) else "accepted")
                           for c, o in judged)  # fmt: skip
    drawn = {
        "t_beam": {"R1", "R2", "R3", "R4", "R6"}, "circular_column": {"R1", "R2", "R3", "R4", "R7"},
        "cft_round": {"R1", "R2"}, "cft_rect": {"R1", "R2"},
    }  # fmt: skip
    for name, rules in drawn.items():
        got = {k for (t, k), _ in per_template.items() if t == name}
        need = rules | {"accepted", "v1", "unknown", "list", "cap-holes", "cap-vertices", "key",
                        "point", "extent", "simple"}  # fmt: skip
        assert need <= got, (name, need - got)
        strata = {c.stratum for c, _ in judged if c.template == name}
        assert strata >= set(STRATA) - {"float", "corner"}, (name, set(STRATA) - strata)
    # bar_material on a CFT is an unknown key at step 1 (13.2), named before anything else.
    assert any(c.template.startswith("cft") and "bar_material" in c.params
               and o == Refused("bar_material", "unknown") for c, o in judged)  # fmt: skip
    # t_beam's re-entrant corners (the "corner" stratum): at the outline (R1) and at the cover
    # (R3), the rule refuses some holes there and lets others past it, to a later rule or in.
    # Counted only where the hole comes within 10 mm of the limit at a re-entrant corner: of the
    # corner itself for R1, of the 30 mm cover round it for R3.
    for family, r, within in (("outline-in@corner", 1, 10.0), ("outline-cover@corner", 3, 40.0)):
        corner = Counter((o.kind if isinstance(o, Refused) else "accepted") for c, o in judged
                         if c.stratum == "corner" and c.family == family
                         and at_re_entrant_corner(c, within))  # fmt: skip
        print(f"  t_beam's re-entrant corners, {family}: {dict(sorted(corner.items()))}")
        past = corner["accepted"] + sum(corner[f"R{x}"] for x in range(r + 1, 8))
        assert corner[f"R{r}"] and past, (family, corner)
    # Each rule both refuses holes aimed at it and lets some through (18.2's two sides). On a
    # whole template a hole that clears the outline near it meets the cover (R3) next, so "let
    # through" is: accepted, or refused by a later rule.
    for r in range(1, 8):
        refused = passed = 0
        for c, o in judged:
            if c.stratum != "aimed" or c.rule != r:
                continue
            last = f"holes[{len(cast(list[object], c.params['holes'])) - 1}]"
            if not isinstance(o, Refused):
                passed += 1
            elif o.param == last and o.kind == f"R{r}":
                refused += 1
            elif o.param == last and o.kind[0] == "R" and int(o.kind[1]) > r:
                passed += 1
        accepted = sum(1 for c, o in judged if c.rule == r and not isinstance(o, Refused))
        print(f"  aimed at R{r}: refused by it {refused}, past it {passed} ({accepted} accepted)")
        assert refused and passed, f"R{r} does not show both verdicts"


def test_the_op_path_agrees_with_the_expansion() -> None:
    """Every seventh case through `AddSectionTemplate`: frozen params (tuples and read-only
    mappings), the same refusal by name, or the same holes in the draft."""
    for case, expected in fuzz()[::7]:
        doc = Document()
        try:
            doc.add_section_template(case.template, case.params, template_version=2)
        except TemplateParamError as exc:
            assert isinstance(expected, Refused), (case, exc)
            assert kind_of(exc) == expected, (case, exc)
            continue
        except OpArgumentError as exc:  # freeze_params refuses what JSON cannot carry
            assert "JSON cannot carry" in str(exc) or "holds more than" in str(exc), exc
            continue
        assert isinstance(expected, Plan), (case, expected)
        (face,) = (f for f in doc.section_faces() if f.role == "concrete")
        assert len(face.holes) == len(next(f for f in expected.faces if f.role == "concrete").holes)


# --- the break-once table ----------------------------------------------------------------------


@cache
def mutant(edits: tuple[tuple[str, str], ...], wiring: bool = False) -> ModuleType:
    """`holes` (or, for a wiring row, the `templates` package that registers each version)
    with `edits` applied to its source, as a fresh module."""
    target = templates_package if wiring else holes
    path = cast(str, target.__file__)
    source = Path(path).read_text(encoding="utf-8")
    for old, new in edits:
        assert source.count(old) == 1, f"the edit no longer applies; re-pin the row: {old!r}"
        source = source.replace(old, new)
    name = f"{target.__name__}_mutant_{len(MUTANTS)}"
    module = ModuleType(name)
    module.__file__ = path
    sys.modules[name] = module  # dataclasses look their module up while the source runs
    exec(compile(source, path, "exec"), module.__dict__)
    MUTANTS.append(name)
    return module


MUTANTS: list[str] = []


def step_of(module: ModuleType, wiring: bool = False) -> Step:
    """The v2 step of a mutant: the mutant's own `TEMPLATES[t][2]` for a wiring row, else the
    mutant `expand_with_holes` wired as the registry wires the real one."""

    def step(template: str, params: object) -> Plan:
        if wiring:
            versions = cast(Mapping[str, Mapping[int, Callable[[object], Plan]]], module.TEMPLATES)
            return versions[template][2](params)
        v1 = TEMPLATES[template][1]
        return cast(Plan, module.expand_with_holes(
            template, FIELDS[template], v1, params, centred=CENTRED[template]
        ))  # fmt: skip

    return step


RC = params_at("rc", 1234.5)[1]
PC = params_at("pc", 0.0)[1]
RH = params_at("rh", 0.1)[1]
SPOT = (37.5, -82.5)  # a safe spot of rc, as an offset (`safe_spots`)
BOX = [(-20.0, 40.0), (20.0, 40.0), (20.0, 80.0), (-20.0, 80.0)]  # counter-clockwise; clear in rc
DUCT = [(-20.0, 293.0), (20.0, 293.0), (20.0, 333.0), (-20.0, 333.0)]  # rh's top wall: clear


@dataclass(frozen=True)
class Row:
    name: str
    what: str
    edits: tuple[tuple[str, str], ...]
    template: str
    params: Json
    fuzz: bool = True
    wiring: bool = False  # the edits apply to `templates/__init__.py`, not to `holes.py`


# Lines of the step, as the source spells them, for the rows that move or change one.
STEP_3 = "    _require_caps(template, entries)  # step 3\n"
STEP_4 = "    shapes = [_shape(template, k, entry) for k, entry in enumerate(entries)]  # step 4\n"
STEP_5 = (
    '    v1_params = {key: value for key, value in data.items() if key != "holes"}\n'
    "    plan = v1(v1_params)  # step 5\n"
)
RING_LIST = "\n        return None\n    return cast(Sequence[object], ring)"
UNKNOWN_KEY = '\n        raise TemplateParamError(\n            template, f"{where}.{unknown[0]}"'
RADIUS = 'number(p, "radius_mm", hole["radius_mm"])'
GIVEN_SIGN = "None if is_simple(ring) and (signed_area(ring) < 0) == (twice < 0) else 'x'"
RING_VALUES = "    if not isinstance(entry, Mapping):\n        return None"
CENTRE_CHECK = '        center = point_value(p, "center_mm", hole["center_mm"])\n'
RADIUS_CHECK = f'        radius = positive(p, "radius_mm", {RADIUS})\n'
COUNT_CHECK = (
    "    if len(ring) < 3:\n"
    '        raise p.error("ring_mm", f"needs 3 or more vertices, got {len(ring)}")\n'
)
VERTICES = 'tuple(point_value(p, f"ring_mm[{i}]", v) for i, v in enumerate(ring))'
ROW_OF_33 = [circle((x * 4.0, 0.5), 1.0) for x in range(-16, 17)]
CONCRETE_FACE = '    (k,) = (i for i, face in enumerate(plan.faces) if face.role == "concrete")\n'
CR = params_at("cr", 0.1)[1]

# --- C9-2c: the wiring rows. Each template's v2 slot is one call to `holes.version_2`; a row
# breaks one argument of it, the way a copied line goes wrong: the centring, the v1 function,
# the fields, the name, or no step at all. On a CFT, `bar_material` among the fields would let
# v1 name it ("places no bars") where 13.2 step 1 names it an unknown key.
SIBLING = {"t_beam": "rect_column", "circular_column": "cft_round", "cft_round": "cft_rect",
           "cft_rect": "cft_round"}  # fmt: skip
BASE_OF = {"t_beam": "tb", "circular_column": "cc", "cft_round": "cr", "cft_rect": "ct"}


def v2_call(template: str) -> str:
    """How `templates/__init__.py` spells `template`'s v2 slot: its call to `holes.version_2`."""
    source = Path(cast(str, templates_package.__file__)).read_text(encoding="utf-8")
    t = re.escape(template)
    found = re.findall(
        rf"holes\.version_2\(\s*{t}\.TEMPLATE, {t}\.FIELDS, {t}\.expand_v1,\s*centred=True,?\s*\)",
        source,
    )
    assert len(found) == 1, (template, found)
    return cast(str, found[0])


def wiring_rows() -> tuple[Row, ...]:
    rows: list[Row] = []
    for t in C9_2C:
        call, s = v2_call(t), SIBLING[t]
        params = params_at(BASE_OF[t], 1234.5)[1]  # centred on (1234.5, -1234.5)
        held = {**params, "holes": [circle((0.0, 0.0), 20.0)]}  # clear at its centre
        rows += [
            Row(f"{t}_uncentred", f"{t} v2 wired centred=False: holes not moved by center_mm",
                ((call, call.replace("centred=True", "centred=False")),), t, held, wiring=True),
            Row(f"{t}_no_step", f"{t} v2 is v1 itself: holes refused as unknown",
                ((call, f"{t}.expand_v1"),), t, held, wiring=True),
            Row(f"{t}_other_v1", f"{t} v2 wraps {s}'s v1",
                ((call, call.replace(f"{t}.expand_v1", f"{s}.expand_v1")),), t, held,
                wiring=True),
            Row(f"{t}_other_fields", f"{t} v2 checks its keys against {s}'s fields",
                ((call, call.replace(f"{t}.FIELDS", f"{s}.FIELDS")),), t, held, wiring=True),
            Row(f"{t}_other_name", f"{t} v2's hole refusals named {s}",
                ((call, call.replace(f"{t}.TEMPLATE", f"{s}.TEMPLATE")),), t,
                {**params, "holes": [None]}, wiring=True),
        ]  # fmt: skip
        if t.startswith("cft"):
            rows.append(Row(
                f"{t}_bar_material_known", f"{t} v2 takes bar_material past step 1",
                ((call, call.replace(f"{t}.FIELDS", f'(*{t}.FIELDS, "bar_material")')),), t,
                {**held, "bar_material": "A630"}, wiring=True,
            ))  # fmt: skip
    return tuple(rows)

ROWS: tuple[Row, ...] = (
    # --- the caps, and what they count (16.2, 13.2 step 3) -------------------------------------
    Row("cap_holes_33", "33 holes taken",
        (("if len(entries) > MAX_HOLES:", "if len(entries) > 33:"),),
        "rect_column", {**RC, "holes": ROW_OF_33}),
    Row("cap_holes_ge", "32 holes refused",
        (("if len(entries) > MAX_HOLES:", "if len(entries) >= MAX_HOLES:"),),
        "rect_column", {**RC, "holes": ROW_OF_33[:32]}),
    Row("cap_vertices_257", "257 ring vertices taken",
        (("if vertices > MAX_HOLE_VERTICES:", "if vertices > 257:"),),
        "rect_column", {**RC, "holes": [ring_entry(regular(257, (30.0, 30.0), 10.0))]}),
    Row("cap_vertices_ge", "256 ring vertices refused",
        (("if vertices > MAX_HOLE_VERTICES:", "if vertices >= MAX_HOLE_VERTICES:"),),
        "rect_column", {**RC, "holes": [ring_entry(regular(256, (30.0, 30.0), 10.0))]}),
    Row("cap_counts_strings", "a string ring_mm counted as vertices (Errata's 'x' * 300)",
        (("if isinstance(ring, str | bytes) or not isinstance(ring, Sequence):" + RING_LIST,
          "if not isinstance(ring, Sequence):" + RING_LIST),),
        "rect_column", {**RC, "holes": [{"ring_mm": "x" * 300}]}),
    Row("cap_drop_vertices", "no vertex cap",
        (("    if vertices > MAX_HOLE_VERTICES:\n", "    if False:\n"),),
        "rect_column", {**RC, "holes": [{"ring_mm": [None] * 300}]}),
    Row("cap_after_shape", "the caps after the shapes: a malformed entry among 33 is named",
        ((STEP_3 + STEP_4, STEP_4 + STEP_3),),
        "rect_column", {**RC, "holes": [None] * 33}),
    Row("cap_sole_ring_key", "ring_mm counted only where it is the sole key (16.2 carry-over 1)",
        ((RING_VALUES, RING_VALUES.replace("):", ") or len(entry) != 1:", 1)),),
        "rect_column", {**RC, "holes": [{"ring_mm": [[0, 0]] * 300, "zz": 1}]}),
    # --- the order of the steps (13.2) -------------------------------------------------------
    Row("v1_before_shape", "v1 before the shapes: a bad b named before a bad hole",
        ((STEP_4 + STEP_5, STEP_5 + STEP_4),),
        "rect_column", {**RC, "b": -1, "holes": [None]}),
    Row("keys_unchecked", "no step 1: an unknown key reaches v1, which names it without holes",
        (("    Params(template, data, (*fields, \"holes\"))  # step 1", "    pass  # step 1"),),
        "rect_column", {**RC, "zz": 1, "holes": [None]}),
    Row("holes_to_v1", "v1 given holes: it refuses them as unknown",
        (("    plan = v1(v1_params)  # step 5", "    plan = v1(data)  # step 5"),),
        "rect_column", {**RC, "holes": [circle(SPOT, 1.0)]}),
    Row("rules_dropped", "no step 7: a hole on a bar accepted",
        (("    require_holes_clear(template, plan, stored)  # step 7\n", ""),),
        "rect_column", {**RC, "holes": [circle((0.0, -240.0), 5.0)]}),
    Row("key_dropped", "no unknown-key check: the form check names the entry instead",
        (("    if unknown:" + UNKNOWN_KEY, "    if False:" + UNKNOWN_KEY),),
        "rect_column", {**RC, "holes": [{"center_mm": [0, 0], "radius_mm": 1, "zz": 1}]}),
    # --- refusal codes (16.1) ----------------------------------------------------------------
    Row("null_is_absent", "holes: null taken as no holes",
        (('    if "holes" not in data:\n', '    if data.get("holes") is None:\n'),),
        "rect_column", {**RC, "holes": None}),
    Row("string_is_a_list", "holes: a string taken as a list of characters",
        (("    if isinstance(value, str | bytes) or not isinstance(value, Sequence):\n        kind",
          "    if not isinstance(value, Sequence):\n        kind"),),
        "rect_column", {**RC, "holes": "abc"}),
    Row("both_forms", "a circle with a ring_mm too",
        (("if keys != set(CIRCLE_KEYS) and keys != set(RING_KEYS):",
          "if not keys >= set(CIRCLE_KEYS) and keys != set(RING_KEYS):"),),
        "rect_column", {**RC, "holes": [{"center_mm": [0, 0], "radius_mm": 1, "ring_mm": TRI}]}),
    Row("radius_unsigned", "a zero radius taken",
        ((f'radius = positive(p, "radius_mm", {RADIUS})', f"radius = {RADIUS}"),),
        "rect_column", {**RC, "holes": [circle(SPOT, 0)]}),
    Row("ring_two", "a two-vertex ring reaches placement",
        (("    if len(ring) < 3:\n", "    if len(ring) < 2:\n"),),
        "rect_column", {**RC, "holes": [{"ring_mm": [[0, 0], [1, 1]]}]}),
    Row("radius_before_centre", "a circle's radius checked before its centre (16.1's row order)",
        ((CENTRE_CHECK + RADIUS_CHECK, RADIUS_CHECK + CENTRE_CHECK),),
        "rect_column", {**RC, "holes": [{"center_mm": None, "radius_mm": 0}]}),
    Row("vertices_before_count", "a ring's vertices checked before its count (16.1's ring row)",
        ((COUNT_CHECK + f"    return RingHole({VERTICES})",
          f"    points = {VERTICES}\n" + COUNT_CHECK + "    return RingHole(points)"),),
        "rect_column", {**RC, "holes": [{"ring_mm": [[0, 0], "x"]}]}),
    Row("vertex_name", "a bad vertex named as the whole ring",
        (("point_value(p, f\"ring_mm[{i}]\", v)", "point_value(p, \"ring_mm\", v)"),),
        "rect_column", {**RC, "holes": [{"ring_mm": [[0, 0], [1, 0], "x"]}]}),
    Row("extent_dropped", "no extent check: the rules name the hole instead",
        (("    require_extent(template, where, ring)\n", ""),),
        "polygon_column",
        {**PC, "holes": [ring_entry([(LIMIT + 1, 0.0), (LIMIT - 9, 0.0), (LIMIT, 10.0)])]}),
    Row("extent_centre_only", "a circle's extent from its centre only",
        (("require_extent(template, where, ((x - r, y - r), (x + r, y + r)))",
          "require_extent(template, where, ((x, y),))"),),
        "polygon_column", {**PC, "holes": [circle((LIMIT - 2.0, 100.0), 5.0)]}),
    # --- placement (13.2 step 6, 18.4) -------------------------------------------------------
    Row("unplaced", "holes not moved by center_mm",
        (("return (cx + point[0], cy + point[1]) if centred else point", "return point"),),
        "rect_column", {**RC, "holes": [circle(SPOT, 1.0)]}),
    Row("axes_swapped", "center_mm's x and y swapped",
        (("return (cx + point[0], cy + point[1]) if centred else point",
          "return (cy + point[0], cx + point[1]) if centred else point"),),
        "rect_column", {**RC, "holes": [ring_entry(BOX)]}),
    # --- the exact verdict and storage (16.1) ------------------------------------------------
    Row("stored_as_given", "a counter-clockwise ring stored as given",
        (("    stored = ring if twice < 0 else ring[::-1]", "    stored = ring"),),
        "rect_column", {**RC, "holes": [ring_entry(BOX)]}),
    Row("float_orientation", "orientation by the float shoelace (18.4 ring 1)",
        (("    twice = exact_twice_area(ring)", "    twice = signed_area(ring)"),),
        "polygon_column", {**PC, "holes": [ring_entry(FLOAT_ORIENTATION_WRONG)]}),
    Row("float_simplicity", "simplicity by the float is_simple (18.4 ring 3)",
        (("    fault = exact_simplicity_fault(ring)",
          "    fault = None if is_simple(ring) else 'edges cross'"),),
        "polygon_column", {**PC, "holes": [ring_entry(FLOAT_SIMPLICITY_WRONG)]}),
    Row("float_checks_dropped", "no general float rule: an unnamed DocumentError (ring 1)",
        (("    disagreement = _float_disagreement(stored)", "    disagreement = None"),),
        "polygon_column", {**PC, "holes": [ring_entry(FLOAT_ORIENTATION_WRONG)]}),
    Row("float_on_given", "the float checks run on the order given: a CCW ring refused",
        (("_float_disagreement(stored)", "_float_disagreement(ring)"),),
        "rect_column", {**RC, "holes": [ring_entry(BOX)]}),
    Row("float_given_sign", "the given order's float sign taken for the stored one's (ring 2)",
        (("_float_disagreement(stored)", GIVEN_SIGN),),
        "polygon_column", {**PC, "holes": [ring_entry(WRONG_ONCE_REVERSED)]}),
    Row("float_no_reverse_check", "draft/section.py's orientation check dropped (the zero ring)",
        (("    if not signed_area(stored) < 0.0:\n", "    if False:\n"),),
        "polygon_column", {**PC, "holes": [ring_entry(FLOAT_AREA_ZERO)]}),
    Row("float_ccw_ge", "plan.py's check read as >= 0: the zero ring named by the wrong consumer",
        (("    if signed_area(stored) > 0.0:", "    if signed_area(stored) >= 0.0:"),),
        "polygon_column", {**PC, "holes": [ring_entry(FLOAT_AREA_ZERO)]}),
    Row("float_simple_dropped", "plan.py's is_simple dropped: draft/section.py's names it (ring 3)",
        (("    if not is_simple(stored):\n", "    if False:\n"),),
        "polygon_column", {**PC, "holes": [ring_entry(FLOAT_SIMPLICITY_WRONG)]}),
    # --- step 8 ------------------------------------------------------------------------------
    Row("before_own_holes", "user holes before the void (13.5: the void stays index 0)",
        (("holes=(*face.holes, *holes)", "holes=(*holes, *face.holes)"),),
        "rect_hollow", {**RH, "holes": [ring_entry(DUCT)]}),
    # --- C9-2c: a CFT's plan has a steel face too; holes cut the core only (Errata 19) --------
    Row("holes_in_steel", "user holes appended to the steel tube, the plan's last face",
        ((CONCRETE_FACE, "    k = len(plan.faces) - 1\n"),),
        "cft_round", {**CR, "holes": [circle((0.0, 0.0), 50.0)]}),
    # --- C9-2c: each template's wiring in TEMPLATES (`wiring_rows`) ----------------------------
    *wiring_rows(),
)  # fmt: skip


@pytest.mark.parametrize("row", ROWS, ids=[r.name for r in ROWS])
def test_each_row_kills_its_mutant(row: Row) -> None:
    expected = reference(row.template, row.params)
    assert run(product, row.template, row.params) == expected, f"{row.name}: product != reference"
    got = run(step_of(mutant(row.edits, row.wiring), row.wiring), row.template, row.params)
    assert got != expected, f"{row.name} ({row.what}) survives its case: {got}"


def kills(step: Step, judged: Sequence[tuple[Case, Outcome]]) -> bool:
    return any(run(step, c.template, c.params) != expected for c, expected in judged)


def test_the_generator_kills_every_fuzz_row() -> None:
    judged = fuzz()
    alive = [
        r.name for r in ROWS
        if r.fuzz and not kills(step_of(mutant(r.edits, r.wiring), r.wiring), judged)
    ]  # fmt: skip
    assert not alive, f"the generator lets these through: {alive}"


def test_the_rows_are_distinct() -> None:
    names = [r.name for r in ROWS]
    assert len(set(names)) == len(names) and len({r.edits for r in ROWS}) == len(ROWS)


# --- 18.3, the hand cases, read back from the draft ---------------------------------------------

RECT: Json = {
    "material": "C30", "b": 400, "h": 600, "center_mm": [200, 300], "cover": 40, "nx": 3,
    "ny": 3, "bar": "Ø20", "tie": "Ø10", "tie_spacing": 150,
}  # fmt: skip
HOLLOW: Json = dict(BASES["rh"][1])
VOID = [[-150.0, -200.0], [-150.0, 200.0], [150.0, 200.0], [150.0, -200.0]]  # rh's void, CW
POLYGON: Json = dict(BASES["pc"][1])


def drafted(template: str, params: Json, version: int = 2) -> tuple[Document, list[Json]]:
    """The document and its concrete face's `holes` in the section-draft v2."""
    doc = Document()
    doc.add_section_template(template, params, template_version=version)
    return doc, face_holes(doc)


def face_holes(doc: Document) -> list[Json]:
    section = cast(Json, section_draft(doc, version=2, commit=None)["section"])
    (face,) = (f for f in cast(list[Json], section["faces"]) if f["role"] == "concrete")
    return cast(list[Json], face["holes"])


def refusal(template: str, params: Json) -> TemplateParamError:
    with pytest.raises(TemplateParamError) as caught:
        expand(template, params)
    return caught.value


def test_rect_column_centred_duct_by_hand() -> None:
    # b 400, h 600 at (200, 300); bar centres 40 + 10 + 10 = 60 in: the nearest, (60, 300) and
    # (340, 300), are 140 from the duct's centre, 80 clear of the Ø20 bars; the outline is 150
    # from the duct, past the 40 cover; the hoop's hull is 280 x 480, round the duct.
    duct = {"holes": [{"center_mm": [0, 0], "radius_mm": 50}]}
    doc, got = drafted("rect_column", {**RECT, **duct})
    assert got == [{"kind": "circle", "center_mm": [200.0, 300.0], "radius_mm": 50.0}]
    assert round(400 * 600 - math.pi * 50**2, 1) == 232146.0  # the worked example's net area
    assert lint_section_v2({i: doc.entity(i) for i in doc.entity_ids()}) == ()
    tied = refusal("rect_column", {**RECT, **duct, "crossties": "all"})
    assert tied.param == "holes[0]" and str(tied).startswith("rect_column: holes[0]: R5: ")


def test_rect_hollow_wall_duct_by_hand() -> None:
    # d = 40 + 10 + 8 = 58: the outer bars' top row at y 342, the inner at y 258 (void top 200
    # + 58). A Ø60 duct at (0, 313) runs from y 283 to 343: 1 past the outer hull (within
    # r_min 8), 25 off the inner hull (beyond r_max + t = 18), 57 from the top (cover 40), 83
    # off the void, and 61 from the nearest bar centre. User hole 0 is the face's hole 1.
    _, got = drafted("rect_hollow", {**HOLLOW, "holes": [{"center_mm": [0, 313], "radius_mm": 30}]})
    assert got == [
        {"kind": "ring", "ring_mm": VOID},
        {"kind": "circle", "center_mm": [0.0, 313.0], "radius_mm": 30.0},
    ]  # fmt: skip
    for y in (270, 250):  # 40 and 20 clear of the void: no more than the cover
        low = refusal("rect_hollow", {**HOLLOW, "holes": [{"center_mm": [0, y], "radius_mm": 30}]})
        assert (
            str(low)
            == "rect_hollow: holes[0]: R3: it is not more than the 40 mm cover from own hole 0"
        )


def test_polygon_column_ring_by_hand() -> None:
    # Section coordinates: the triangle is stored as given, reversed to clockwise. Bars sit 60
    # in, at y 60 under it (40 clear); the outline's bottom is 100 below it, the left edge 150.
    tri = [[150, 100], [230, 100], [190, 160]]
    _, got = drafted("polygon_column", {**POLYGON, "holes": [{"ring_mm": tri}]})
    assert got == [{"kind": "ring", "ring_mm": [[190.0, 160.0], [230.0, 100.0], [150.0, 100.0]]}]


T_BEAM: Json = {**T_BEAM_PARAMS, "hf": 200}  # centred on (0, 300): y 0 to 600, flange from 400


def test_t_beam_duct_by_hand() -> None:
    # Errata 18.3 on the flange placement. The stirrup's hull runs from the bottom bar (100, 50)
    # to the top bar (102, 552); a Ø50 duct centred on the right leg's centreline, 15 mm
    # (r_max + t / 2) outside that edge and 110 mm below the top, at about (116.75, 490), sits
    # in the flange: about 70.9 mm from the outline (cover 30) and 30.7 mm clear of the top bar
    # (102, 552), but its distance from the hull runs from 0 to about 40 mm, neither within
    # r_min = 8 nor beyond r_max + t = 20 mm: R6. The offset is from center_mm (0, 300).
    duct = refusal("t_beam", {**T_BEAM, "holes": [circle((116.75, 190.0), 25.0)]})
    assert duct.param == "holes[0]" and str(duct).startswith("t_beam: holes[0]: R6: "), duct
    # A re-entrant corner of the T is (150, 400). A Ø10 hole on its bisector, 35 mm along both
    # faces, is exactly the 30 mm cover from the underside of the flange and the web's face:
    # contact, R3. One millimetre further it clears every rule (the hull is 84 mm off, the
    # nearest slab bar, (212.5, 564), about 130 mm) and lands at the corner plus its offsets.
    at = refusal("t_beam", {**T_BEAM, "holes": [circle((185.0, 135.0), 5.0)]})
    assert str(at).startswith("t_beam: holes[0]: R3: "), at
    doc, got = drafted("t_beam", {**T_BEAM, "holes": [circle((186.0, 136.0), 5.0)]})
    assert got == [{"kind": "circle", "center_mm": [186.0, 436.0], "radius_mm": 5.0}]
    assert lint_section_v2({i: doc.entity(i) for i in doc.entity_ids()}) == ()
    # The web, inside the cage, and an overhang, outside it, between the slab bars.
    _, got = drafted("t_beam", {**T_BEAM, "holes": [circle((0, 0), 50), circle((275, 200), 20)]})
    assert [h["center_mm"] for h in got] == [[0.0, 300.0], [275.0, 500.0]]


def test_circular_column_spiral_inner_face_by_hand() -> None:
    # Errata 18.3: diameter 600, cover 40, a Ø10 spiral: rho = 255, its inner face 250 from the
    # centre. A Ø50 hole whose far side reaches 250 touches it (R7); 0.01 mm in, it is clear:
    # 6 Ø20 bars at r 240, the nearest (120, 207.8) about 121 from it, and 50 from the outline.
    base = dict(BASES["cc"][1])
    touch = refusal("circular_column", {**base, "holes": [circle((0.0, 225.0), 25.0)]})
    assert str(touch).startswith("circular_column: holes[0]: R7: "), touch
    doc, got = drafted("circular_column", {**base, "holes": [circle((0.0, 224.99), 25.0)]})
    assert got == [{"kind": "circle", "center_mm": [0.0, 224.99], "radius_mm": 25.0}]
    assert lint_section_v2({i: doc.entity(i) for i in doc.entity_ids()}) == ()
    # Beyond the tie's outer face (260) the hole would be in the cover: R3 refuses it there.
    out = refusal("circular_column", {**base, "holes": [circle((0.0, 270.0), 5.0)]})
    assert str(out).startswith("circular_column: holes[0]: R3: "), out


@pytest.mark.parametrize("base", ["cr", "ct"])
def test_cft_core_holes_by_hand(base: str) -> None:
    # Errata 18.3 and 19: the core is the concrete face; the tube keeps its one hole, the core.
    template, params = BASES[base]
    if template == "cft_round":  # core radius 400 / 2 - 10 = 190
        tangent, clear = circle((165.0, 0.0), 25.0), circle((164.99, 0.0), 25.0)
        a, b, b_clear = circle((-50, 0), 25), circle((0, 0), 25), circle((0.01, 0), 25)
    else:  # core 300 - 2 x 12 by 500 - 2 x 12: x from -138 to 138
        tangent = ring_entry([(88, -25), (138, -25), (138, 25), (88, 25)])
        clear = ring_entry([(88, -25), (137.99, -25), (137.99, 25), (88, 25)])
        a = ring_entry([(-60, -20), (-20, -20), (-20, 20), (-60, 20)])
        b = ring_entry([(-20, -20), (20, -20), (20, 20), (-20, 20)])
        b_clear = ring_entry([(-19.99, -20), (20, -20), (20, 20), (-19.99, 20)])
    core = expand(template, params, 1).faces[0].boundary
    as_hole = entry_of(core, (0.0, 0.0), True)  # a hole equal to the core: it touches R1
    for refused, rule, k in ((tangent, 1, 0), (as_hole, 1, 0), ([a, b], 2, 1)):
        given = refused if isinstance(refused, list) else [refused]
        err = refusal(template, {**params, "holes": given})
        assert str(err).startswith(f"{template}: holes[{k}]: R{rule}: "), err
    doc, got = drafted(template, {**params, "holes": [clear, a, b_clear]})
    assert len(got) == 3
    section = cast(Json, section_draft(doc, version=2, commit=None)["section"])
    (tube,) = (f for f in cast(list[Json], section["faces"]) if f["role"] == "steel")
    assert tube["holes"] == [tube_hole(template, params)]  # the steel face is untouched
    assert lint_section_v2({i: doc.entity(i) for i in doc.entity_ids()}) == ()


V1_FAULT = {"t_beam": ("bw", -1), "circular_column": ("diameter", 0), "cft_round": ("t", 300),
            "cft_rect": ("t", 300)}  # fmt: skip
OUTSIDE = circle((1e5, 0.0), 1.0)  # within the extent, outside every face: R1
BOW_TIE = ring_entry([(0, 0), (4, 4), (4, 0), (0, 4)])
FAR_OUT = circle((LIMIT * 2, 0.0), 1.0)  # outside the ADR 0032 extent once placed


@pytest.mark.parametrize("name", C9_2C)
def test_each_refusal_order_of_13_2_on_c9_2c_templates(name: str) -> None:
    """Every pair of steps 13.2 orders, pinned by params bad in two ways at once: the earlier
    step names its fault. The reference agrees with each."""
    params = dict(BASES[BASE_OF[name]][1])
    key, value = V1_FAULT[name]
    cases: list[tuple[Json, str]] = [
        ({"zz": 1, "holes": None}, "zz"),  # step 1 before step 2
        ({key: value, "holes": "abc"}, "holes"),  # 2 before 5
        ({key: value, "holes": [None] * 33}, "holes"),  # 3 (the cap) before 4 and 5
        ({key: value, "holes": [{"center_mm": [0, 0]}]}, "holes[0]"),  # 4 before 5
        ({key: value, "holes": [OUTSIDE]}, key),  # 5 before 7
        ({"holes": [FAR_OUT, {"radius_mm": 1}]}, "holes[1]"),  # 4 (every hole) before 6
        ({"holes": [OUTSIDE, BOW_TIE]}, "holes[1].ring_mm"),  # 6 (every hole) before 7
        ({"holes": [OUTSIDE, FAR_OUT]}, "holes[1]"),  # the extent (6) before R1 of hole 0 (7)
    ]
    if name.startswith("cft"):  # 1 before 5: v1 would say "places no bars"
        cases.append(({"bar_material": None, "holes": [None]}, "bar_material"))
    for extra, param in cases:
        given = {**params, **extra}
        err = refusal(name, given)
        assert err.param == param and str(err).startswith(f"{name}: {param}: "), (extra, err)
        want = reference(name, given)
        assert isinstance(want, Refused) and want.param == param, (extra, want)


def tube_hole(template: str, params: Json) -> Json:
    """The steel tube's one hole, the core, in the draft's words (v1's drawing)."""
    doc = Document()
    doc.add_section_template(template, params, template_version=1)
    section = cast(Json, section_draft(doc, version=2, commit=None)["section"])
    (tube,) = (f for f in cast(list[Json], section["faces"]) if f["role"] == "steel")
    (hole,) = cast(list[Json], tube["holes"])
    return hole


# --- 18.4, placement -----------------------------------------------------------------------------

FAR = [1234.5, -40000.3]  # non-zero and not dyadic


def _placed(entry: Json, centre: Sequence[float]) -> Json:
    """The test's own placement: (cx + x, cy + y), a ring stored clockwise by its exact area."""
    cx, cy = centre
    if "radius_mm" in entry:
        x, y = cast(list[float], entry["center_mm"])
        return {
            "kind": "circle",
            "center_mm": [cx + x, cy + y],
            "radius_mm": float(cast(float, entry["radius_mm"])),
        }
    ring = [(cx + x, cy + y) for x, y in cast(list[list[float]], entry["ring_mm"])]
    exact = sum(
        (
            Q(a[0]) * Q(b[1]) - Q(b[0]) * Q(a[1])
            for a, b in zip(ring, ring[1:] + ring[:1], strict=True)
        ),
        Q(0),
    )
    kept = ring if exact < 0 else ring[::-1]
    return {"kind": "ring", "ring_mm": [[x, y] for x, y in kept]}


def _exact_cw(ring: Sequence[Sequence[float]]) -> bool:
    pts = [(Q(x), Q(y)) for x, y in ring]
    return (
        sum((a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1], strict=True)), Q(0))
        < 0
    )


PLACED_HOLES: list[Json] = [
    {"center_mm": [0.1, -0.2], "radius_mm": 30},
    {"ring_mm": [[-40.7, 120.3], [40.1, 120.3], [40.1, 160.9], [-40.7, 160.9]]},  # CCW
    {"ring_mm": [[-40.7, -160.9], [-40.7, -120.3], [40.1, -120.3]]},  # CW
]


# Each centred template, and the edit of its size that leaves the holes at their offsets. The
# holes of `PLACED_HOLES` clear every rule on each: they lie within 166 mm of the centre, inside
# the stirrup's hull of the T's web, the bars' circle (r 240) and the CFT cores.
SIZED: dict[str, tuple[Json, Json]] = {
    "rect_column": (RECT, {"b": 500}),
    "t_beam": (dict(T_BEAM_PARAMS), {"bw": 320}),
    "circular_column": (dict(BASES["cc"][1]), {"diameter": 700}),
    "cft_round": (dict(BASES["cr"][1]), {"diameter": 500}),
    "cft_rect": (dict(BASES["ct"][1]), {"b": 340}),
}


@pytest.mark.parametrize("template", sorted(SIZED))
def test_holes_land_at_the_centre_plus_their_offsets_and_move_with_it(template: str) -> None:
    base, size = SIZED[template]
    doc, got = drafted(template, {**base, "center_mm": FAR, "holes": PLACED_HOLES})
    assert got == [_placed(h, FAR) for h in PLACED_HOLES]
    (entity,) = doc.section_templates()
    moved = [-777.7, 333.3]
    doc.edit_section_template(entity.entity_id, {**base, "center_mm": moved, "holes": PLACED_HOLES})
    assert face_holes(doc) == [_placed(h, moved) for h in PLACED_HOLES]
    doc.edit_section_template(
        entity.entity_id, {**base, **size, "center_mm": moved, "holes": PLACED_HOLES}
    )
    assert face_holes(doc) == [_placed(h, moved) for h in PLACED_HOLES]  # size leaves offsets
    assert all(
        _exact_cw(cast(list[list[float]], h["ring_mm"]))
        for h in face_holes(doc)
        if h["kind"] == "ring"
    )


def test_polygon_column_holes_stay_in_section_coordinates() -> None:
    given = [
        {"center_mm": [300.25, 200.1], "radius_mm": 40},
        {"ring_mm": [[150.3, 100.7], [190.1, 160.9], [230.3, 100.7]]},  # CW: stored as given
        {"ring_mm": [[400.1, 100.3], [480.7, 100.3], [440.9, 150.1]]},  # CCW: reversed
    ]
    _, got = drafted("polygon_column", {**POLYGON, "holes": given})
    assert got == [_placed(h, (0.0, 0.0)) for h in given]
    assert got[1]["ring_mm"] == given[1]["ring_mm"]


def test_rect_hollow_user_holes_follow_the_void() -> None:
    doc, got = drafted(
        "rect_hollow", {**HOLLOW, "holes": [ring_entry(DUCT), circle((0, -313), 30)]}
    )
    assert [h["kind"] for h in got] == ["ring", "ring", "circle"]
    assert got[0]["ring_mm"] == VOID
    assert got[1] == _placed(ring_entry(DUCT), (0.0, 0.0))  # hole_index 1 (13.5)
    doc.explode_section_template(doc.section_templates()[0].entity_id)
    assert face_holes(doc) == got  # explode keeps (face_id, n_own + k)


@pytest.mark.parametrize(
    "ring",
    FLOAT_RINGS[:3] + FLOAT_RINGS[3:],
    ids=["orientation", "once-reversed", "simplicity", "area-zero"],
)
def test_rings_the_float_checks_decide_otherwise_are_refused_by_name(ring: tuple[XY, ...]) -> None:
    for points in (ring, ring[::-1], ring[1:] + ring[:1]):
        doc = Document()
        with pytest.raises(TemplateParamError) as caught:
            doc.add_section_template("polygon_column", {**POLYGON, "holes": [ring_entry(points)]})
        assert caught.value.param == "holes[0].ring_mm", caught.value
        assert doc.ops() == () and doc.entity_ids() == frozenset()  # never stored


def test_every_accepted_ring_passes_both_consumers_unchanged() -> None:
    """The guarantee of 16.1, over every ring the fuzz accepted."""
    rings = 0
    for _, outcome in fuzz():
        if isinstance(outcome, Plan):
            for h in outcome.faces[0].holes:
                if isinstance(h, PlanRing):
                    ring = h.points_mm
                    assert is_simple(ring) and signed_area(ring) < 0.0 and _exact_cw(ring)
                    rings += 1
    assert rings > 100


# --- 18.5, the op oracles ------------------------------------------------------------------------


# A size each template takes with a centred Ø100 hole, and one that brings the hole to a rule:
# the bars of a 180 wide rect_column (R4), the cover of a 150 wide web (R3), the bars on a
# 200 circle (r 40, R4), a CFT core narrower than the hole (R1).
RESIZED: dict[str, tuple[Json, Json, Json]] = {
    "rect_column": (RECT, {"b": 450}, {"b": 180}),
    "t_beam": (dict(T_BEAM_PARAMS), {"bw": 320}, {"bw": 150}),
    "circular_column": (dict(BASES["cc"][1]), {"diameter": 700}, {"diameter": 200}),
    "cft_round": (dict(BASES["cr"][1]), {"diameter": 500}, {"diameter": 100}),
    "cft_rect": (dict(BASES["ct"][1]), {"b": 340}, {"b": 100}),
}


@pytest.mark.parametrize("name", sorted(RESIZED))
def test_an_edit_keeps_or_drops_holes_and_a_bad_one_changes_nothing(name: str) -> None:
    base, ok, bad = RESIZED[name]
    with_holes = {**base, "holes": [{"center_mm": [0, 0], "radius_mm": 50}]}
    doc, before = drafted(name, with_holes)
    assert len(before) == 1
    template = doc.section_templates()[0].entity_id
    doc.edit_section_template(template, {**with_holes, **ok})
    assert face_holes(doc) == before  # a size moves no hole: it is centred on center_mm
    saved = doc.to_json()
    with pytest.raises(TemplateParamError, match=rf"{name}: holes\[0\]: R"):
        doc.edit_section_template(template, {**with_holes, **bad})  # the hole meets a rule
    assert doc.to_json() == saved  # refused before anything changed
    doc.edit_section_template(template, base)  # params replaced whole: no holes
    assert face_holes(doc) == []
    doc.undo()
    assert face_holes(doc) == before
    doc.undo()
    doc.undo()
    assert doc.ops() == ()  # one undo per op


def section_of(doc: Document) -> Json:
    return cast(Json, section_draft(doc, version=2, commit=None)["section"])


def without_ids(value: object) -> object:
    """`value` with every entity id dropped (`id`, `*_id`, `*_ids`): an edit draws fresh ids."""
    if isinstance(value, dict):
        return {
            k: without_ids(v)
            for k, v in cast(dict[str, object], value).items()
            if k != "id" and not k.endswith(("_id", "_ids"))
        }
    if isinstance(value, list):
        return [without_ids(v) for v in cast(list[object], value)]
    return value


@pytest.mark.parametrize("name", sorted(RESIZED))
def test_a_v1_template_takes_holes_by_an_edit_to_version_2_and_drops_them_back(name: str) -> None:
    """13.4, and the round trip: v1, then v2 with a hole, then v1 again draws v1's section."""
    base = RESIZED[name][0]
    doc = Document()
    template = doc.add_section_template(name, base, template_version=1)
    plain = section_of(doc)
    holed = {**base, "holes": [{"center_mm": [0, 0], "radius_mm": 50}]}
    with pytest.raises(TemplateParamError, match=f"{name}: holes: unknown parameter; known: "):
        doc.edit_section_template(template.entity_id, holed)
    edited = doc.edit_section_template(template.entity_id, holed, template_version=2)
    assert edited.template_version == 2 and len(face_holes(doc)) == 1
    log = doc.to_dict()
    assert Document.from_dict(log).to_dict() == log  # the log replays across the versions
    back = doc.edit_section_template(template.entity_id, base, template_version=1)
    assert back.template_version == 1 and face_holes(doc) == []
    assert without_ids(section_of(doc)) == without_ids(plain)
    assert Document.from_dict(doc.to_dict()).to_dict() == doc.to_dict()
    with pytest.raises(TemplateParamError, match=f"{name}: holes: unknown parameter; known: "):
        doc.edit_section_template(template.entity_id, holed)  # v1 again: holes unknown


@pytest.mark.parametrize("name", sorted(RESIZED))
def test_add_face_hole_on_a_template_face_stays_locked(name: str) -> None:
    base = RESIZED[name][0]
    doc, _ = drafted(name, {**base, "center_mm": [200, 300], "holes": [circle((0, 0), 50)]})
    faces = [e for e in doc.section_faces() if isinstance(e, SectionFace)]
    assert faces and len(faces) == (2 if name.startswith("cft") else 1)
    at = [PointAt(XYZ(x, y, 0.0)) for x, y in ((150, 450), (250, 450), (200, 500))]
    for face in faces:  # the core, and a CFT's steel tube
        with pytest.raises(TemplateLockedError):
            doc.add_face_hole(face.entity_id, point_ids=at)
    assert len(face_holes(doc)) == 1


@pytest.mark.parametrize("base", sorted(BASES))
def test_without_holes_version_2_is_version_1(base: str) -> None:
    for off in OFFSETS:
        template, params = params_at(base, off)
        v1 = expand(template, params, 1)
        assert expand(template, params, 2) == v1 == expand(template, {**params, "holes": []}, 2)
        one, two = Document(), Document()
        a = one.add_section_template(template, params, template_version=1)
        b = two.add_section_template(template, params, template_version=2)
        assert a.child_ids == b.child_ids
        first = cast(Json, section_draft(one, version=2, commit=None)["section"])
        second = cast(Json, section_draft(two, version=2, commit=None)["section"])
        cast(list[Json], second["templates"])[0]["template_version"] = 1
        assert first == second


LOGS = Path(__file__).resolve().parent / "fixtures" / "section_templates"


@pytest.mark.parametrize("name", sorted(FIELDS))
def test_each_v1_log_replays_under_version_2_apart_from_the_version(name: str) -> None:
    """15.4: v1's params, expanded under version 2, give the same section."""
    log = cast(Json, json.loads((LOGS / f"{name}@v1.json").read_text(encoding="utf-8")))
    v1 = cast(Json, section_draft(Document.from_dict(log), version=2, commit=None)["section"])
    (op,) = cast(list[Json], log["ops"])
    as_v2 = Document.from_dict({**log, "ops": [{**op, "template_version": 2}]})  # same child ids
    v2 = cast(Json, section_draft(as_v2, version=2, commit=None)["section"])
    cast(list[Json], v2["templates"])[0]["template_version"] = 1
    assert v1 == v2


def clear_by(plan: Plan, holes: Sequence[PlanBoundary], gap: Q) -> bool:
    """Every hole clears every rule by `gap`, by the truth's primitives (Errata 15.3)."""
    t = Truth(plan)
    cores = [shape(h) for h in holes]

    def off_outline(h: Core, by: Q) -> bool:  # d(h, the outline) > by, h inside the face
        if t.circle is not None:
            return all_closer(h, qp(t.circle.center_mm), Q(t.circle.radius_mm) - by)
        assert t.ring is not None
        return apart(h, outline(t.ring), by) and strictly_inside(h.pts[0], t.ring)

    for k, h in enumerate(cores):
        if not off_outline(h, gap):
            return False
        others = [*t.own, *cores[:k]]
        if not all(apart(h, o, gap) for o in others):
            return False
        if not all(
            off_outline(h, c + gap) and all(apart(h, v, c + gap) for v in t.own) for c in t.covers
        ):
            return False
        if not all(apart(h, s, gap) for s in (*t.bars, *t.ties)):
            return False
        for hull, r_min, r_max, d in t.hoops:
            if not (within_hull(h, hull, r_min - gap) or apart(h, region(hull), r_max + d + gap)):
                return False
        for c, rho, d in t.spirals:  # R7: inside the tie's inner face, or beyond its outer one
            if not (all_closer(h, c, rho - d / 2 - gap) or apart(h, point(c), rho + d / 2 + gap)):
                return False
    return True


@pytest.mark.parametrize("name", sorted(FIELDS))
def test_each_v2_log_holds_a_circle_and_a_ring_clear_by_1_mm(name: str) -> None:
    log = cast(Json, json.loads((LOGS / f"{name}@v2.json").read_text(encoding="utf-8")))
    (op,) = cast(list[Json], log["ops"])
    params = cast(Json, op["template_params"])
    assert op["template_version"] == 2
    assert sorted("radius_mm" in h for h in cast(list[Json], params["holes"])) == [False, True]
    bare = expand(name, params | {"holes": []}, 2)  # the plan the holes must clear
    added = expand(name, params, 2).faces[0].holes[len(bare.faces[0].holes) :]
    assert len(added) == 2 and clear_by(bare, added, Q(1))
    assert not clear_by(bare, added, Q(100))  # the measure can fail


# --- 16.2, the caps and the work they bound -----------------------------------------------------


def worst_case() -> Json:
    """`polygon_column` at the caps: a 1000-vertex ring (1000 bars, the cap), one 256-vertex
    ring hole and 31 circle holes, with every optional key: the largest params v2 accepts."""
    ring = [[round(20000 * math.cos(2 * math.pi * i / 1000), 3),
             round(20000 * math.sin(2 * math.pi * i / 1000), 3)] for i in range(1000)]  # fmt: skip
    holes_: list[Json] = [ring_entry(regular(256, (0.0, 0.0), 1000.0))]
    holes_ += [circle(regular(31, (0.0, 0.0), 3000.0)[i], 10.0)
               for i in range(31)]  # fmt: skip
    return {"material": "C30", "bar_material": "A630", "ring": ring, "cover": 40, "bar": "Ø10",
            "spacing_max": 200, "tie": "Ø8", "tie_spacing": 150, "holes": holes_}  # fmt: skip


def count_values(value: object) -> int:
    """Objects, lists and scalars, as `ops/templates.py::freeze_params` counts them."""
    if isinstance(value, dict):
        return 1 + sum(count_values(v) for v in cast(dict[str, object], value).values())
    if isinstance(value, list):
        return 1 + sum(count_values(v) for v in cast(list[object], value))
    return 1


def test_the_caps_bound_the_params_and_the_work(monkeypatch: pytest.MonkeyPatch) -> None:
    params = worst_case()
    assert count_values(params) == 3935  # Errata 16.2: within MAX_PARAMS_VALUES (4000)
    plan = expand("polygon_column", params, 2)
    assert len(plan.bars) == 1000 and len(plan.faces[0].holes) == 32
    Document().add_section_template("polygon_column", params)  # the op takes it too
    # (sum n_k)(E + B + X + K + T) + sum_{j<k} n_j n_k, with n = 256 and 31 x 1.
    n = [256] + [1] * 31
    hull = len(jarvis([qp(b.xy) for b in plan.bars]))
    units = sum(n) * (1000 + 1000 + 0 + hull + 0) + sum(
        n[j] * n[k] for k in range(len(n)) for j in range(k)
    )
    assert hull == 1000 and units == 869_401
    calls = Counter[str]()
    for name in ("_cross", "_d2", "_seg_d2", "_overlap", "_touch"):
        real = getattr(hole_rules, name)

        def counted(
            *args: object, _real: Callable[..., object] = real, _name: str = name
        ) -> object:
            calls[_name] += 1
            return _real(*args)

        monkeypatch.setattr(hole_rules, name, counted)
    expand("polygon_column", params, 2)
    print(f"\nwork units {units}; primitive calls {dict(calls)} = {sum(calls.values())}")
    assert sum(calls.values()) <= units  # operations, not seconds (apeSection lesson #158)


def test_the_catalog_rows_take_holes_with_the_form_keywords() -> None:
    from apeCAD.catalog import list_templates
    from apeCAD.catalog.schema import validate

    allowed = {"type", "items", "anyOf", "properties", "required", "additionalProperties",
               "prefixItems", "minItems", "maxItems"}  # fmt: skip

    def keywords(schema: object) -> set[str]:
        if isinstance(schema, dict):
            d = cast(dict[str, object], schema)
            inner = d.get("properties", {})
            found = set(d) - {"description", "default"}
            subs = [
                *cast(dict[str, object], inner).values(), d.get("items"),
                *cast(list[object], d.get("anyOf", [])),
                *cast(list[object], d.get("prefixItems", [])),
            ]  # fmt: skip
            return found.union(*(keywords(s) for s in subs if s is not None))
        return set()

    rows = {cast(str, r["name"]): r for r in list_templates()}
    for name in FIELDS:
        row = rows[name]
        assert row["version"] == 2 and row["versions"] == [1, 2]
        schema = cast(Json, row["params"])
        prop = cast(Json, cast(Json, schema["properties"])["holes"])
        assert prop["default"] == [] and "holes" not in cast(list[str], schema["required"])
        assert keywords(prop) <= allowed, keywords(prop) - allowed
        holed = {**cast(Json, row["example"]), "holes": [circle((0, 0), 1), ring_entry(TRI)]}
        validate(schema, holed, name)
        with pytest.raises(OpArgumentError):
            validate(schema, {**holed, "holes": [{"center_mm": [0, 0]}]}, name)
