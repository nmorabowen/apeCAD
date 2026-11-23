"""The lint parity of ADR 0040 Errata 17.6 (C9-3, apeSection#302): the hole step's verdicts
and `section/lint.py`'s agree on the drawn result.

17.6 gives each rule its freehand counterpart in the lint, which no code of C9 changes:

- R1 refuses what `hole-outside-face` warns about on a freehand hole;
- R4, R5 and R7 refuse what `bar-outside-concrete`, `crosstie-crosses-outside` and
  `circular-tie-outside-face` would warn about on the exploded drawing, and contact besides;
- R2, R3 and R6 have no lint;
- a template whose holes clear every rule by at least 0.01 mm draws no lint warning; closer
  than that, a float lint may still warn on a hole the exact rules accept.

`hoop-bar-not-in-face` is read as R4's too: a hoop's bar whose centre a hole covers is a bar
the hole meets, which R4 refuses (the PR body records this reading).

The cases are C9-2's seeded generator (`test_section_template_holes.generated`), each one
whose holes reach the rules: accepted, or refused by R1 to R7. Three judges read each:

- the step (S), the product: `expand(template, params, 2)`;
- the lint (L), `lint_section_v2`, on the drawn result: the template drawing of an accepted
  case, and for every case the exploded drawing, which is the template at version 1,
  exploded, with each hole added freehand by `AddFaceHole` at the test's own placed floats;
- the exact truth (T) of `tests/_hole_rules_truth.py`, apart from both, for clearances.

The parity, case by case (`disagreements`):

1. *Clean.* An accepted case whose holes clear every rule by at least 0.01 mm (T) draws no
   warning, neither as a template nor exploded.
2. *Counterparts.* Every warning is a counterpart, and the entity it names (its hole, bar,
   crosstie or circular tie) is met by some hole, or neared within 0.01 mm, by its rule (T).
   So the lint is never stricter than its rule beyond 17.6's 0.01 mm band.
3. *Verdicts.* A hole that meets a warned entity (T) is refused by the step: that hole or an
   earlier one, and that hole by the counterpart's rule or an earlier rule. This is "R4
   refuses what bar-outside-concrete would warn about", rule by rule.

Each counterpart fires, and each of R4, R5 and R7 also refuses holes the lint is silent on
(contact, "besides"); the counts are printed. Break-once mutants of the rules and of the
lint (`ROWS`) are each killed, by their own case and by the generator.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction as Q
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest

import apeCAD.section.lint as lint_module
from _hole_rules_truth import (
    ZERO,
    Core,
    Truth,
    all_closer,
    apart,
    outline,
    point,
    qp,
    segment,
    shape,
    strictly_inside,
)
from apeCAD import Document
from apeCAD.entities import Bar, CircularTie, Crosstie, Entity, EntityId, Point
from apeCAD.geometry import XYZ
from apeCAD.ops import PointAt
from apeCAD.section.lint import LintWarning, lint_section_v2
from apeCAD.section.templates import expand, hole_rules, holes
from apeCAD.section.templates.plan import Plan, PlanBoundary, PlanCircle, PlanRing
from test_section_template_holes import (
    CENTRED,
    Case,
    Refused,
    centre_of,
    circle,
    clear_by,
    fuzz,
    params_at,
    product,
    run,
)

Json = dict[str, object]
Lint = Callable[[Mapping[EntityId, Entity]], tuple[LintWarning, ...]]
GAP = Q(1, 100)  # 17.6's 0.01 mm
RULE_OF = {
    "hole-outside-face": 1,
    "bar-outside-concrete": 4,
    "hoop-bar-not-in-face": 4,  # a bar centre in a hole: a bar the hole meets
    "crosstie-crosses-outside": 5,
    "circular-tie-outside-face": 7,
}
RULE_KINDS = {f"R{r}" for r in range(1, 8)}


# --- the drawings -----------------------------------------------------------------------------


def bare(params: Mapping[str, object]) -> Json:
    return {k: v for k, v in params.items() if k != "holes"}


def placed(case: Case) -> list[PlanBoundary]:
    """The holes in section coordinates, placed here: (cx + x, cy + y), or as given on
    `polygon_column` (Errata 13.2 step 6)."""
    cx, cy = centre_of(case.template, case.params)
    centred = CENTRED[case.template]

    def at(x: object, y: object) -> tuple[float, float]:
        fx, fy = float(cast(float, x)), float(cast(float, y))
        return (cx + fx, cy + fy) if centred else (fx, fy)

    out: list[PlanBoundary] = []
    for entry in cast(list[Json], case.params["holes"]):
        if "radius_mm" in entry:
            x, y = cast(list[object], entry["center_mm"])
            out.append(PlanCircle(at(x, y), float(cast(float, entry["radius_mm"]))))
        else:
            ring = cast(list[list[object]], entry["ring_mm"])
            out.append(PlanRing(tuple(at(x, y) for x, y in ring)))
    return out


def entities(doc: Document) -> dict[EntityId, Entity]:
    return {i: doc.entity(i) for i in doc.entity_ids()}


def exploded(case: Case, hs: Sequence[PlanBoundary]) -> tuple[Document, int]:
    """The template at version 1, exploded, then each hole by `AddFaceHole` on its concrete
    face, its points created at exactly the placed floats (a `PointAt` with its id never snaps).
    Returns the document and the face's own hole count."""
    doc = Document()
    template = doc.add_section_template(case.template, bare(case.params), template_version=1)
    doc.explode_section_template(template.entity_id)
    (face,) = (f for f in doc.section_faces() if f.role == "concrete")
    own = len(face.holes)
    fresh = max(doc.entity_ids()) + 1

    def at(xy: tuple[float, float]) -> PointAt:
        nonlocal fresh
        fresh += 1
        return PointAt(XYZ(xy[0], xy[1], 0.0), fresh - 1)

    for h in hs:
        if isinstance(h, PlanCircle):
            doc.add_face_hole(face.entity_id, center_id=at(h.center_mm), radius_mm=h.radius_mm)
        else:
            doc.add_face_hole(face.entity_id, point_ids=[at(p) for p in h.points_mm])
    return doc, own


def templated(case: Case) -> Document:
    doc = Document()
    doc.add_section_template(case.template, case.params, template_version=2)
    return doc


# --- the truth, per warned entity -----------------------------------------------------------


def off_outline(t: Truth, h: Core, gap: Q) -> bool:
    """d(h, the face's outline) > gap with h inside it: R1 when gap is 0."""
    if t.circle is not None:
        return all_closer(h, qp(t.circle.center_mm), Q(t.circle.radius_mm) - gap)
    assert t.ring is not None
    return apart(h, outline(t.ring), gap) and strictly_inside(h.pts[0], t.ring)


def meeting(
    w: LintWarning, ents: Mapping[EntityId, Entity], cores: Sequence[Core], t: Truth, own: int
) -> dict[int, bool] | None:
    """For warning `w`: each hole k that meets the warned entity by its rule (True) or comes
    within 0.01 mm of meeting it (False); holes clear of it by 0.01 mm or more are left out.
    None for a code that has no counterpart."""

    def xy(point_id: EntityId) -> tuple[Q, Q]:
        p = ents[point_id]
        assert isinstance(p, Point)
        return qp((p.xyz_mm.x_mm, p.xyz_mm.y_mm))

    clears: Callable[[Core, Q], bool]
    if w.code == "hole-outside-face":
        (index,) = re.findall(r"^hole_index (\d+) of face ", w.message)
        k = int(index) - own
        if not 0 <= k < len(cores):
            return {}
        h = cores[k]
        return {k: not off_outline(t, h, ZERO)} if not off_outline(t, h, GAP) else {}
    if w.code in ("bar-outside-concrete", "hoop-bar-not-in-face"):
        bars = [b for b in (ents[i] for i in w.ids) if isinstance(b, Bar)]
        discs = [point(xy(b.point_id), Q(b.diameter_mm) / 2) for b in bars]

        def clears(h: Core, gap: Q) -> bool:
            return all(apart(h, d, gap) for d in discs)

    elif w.code == "crosstie-crosses-outside":
        (tie,) = (x for x in (ents[i] for i in w.ids) if isinstance(x, Crosstie))
        a, b = (cast(Bar, ents[i]) for i in (tie.bar_a_id, tie.bar_b_id))
        band = segment(xy(a.point_id), xy(b.point_id), Q(tie.diameter_mm) / 2)

        def clears(h: Core, gap: Q) -> bool:
            return apart(h, band, gap)

    elif w.code == "circular-tie-outside-face":
        (spiral,) = (x for x in (ents[i] for i in w.ids) if isinstance(x, CircularTie))
        c, rho, d = xy(spiral.center_id), Q(spiral.centerline_radius_mm), Q(spiral.diameter_mm)

        def clears(h: Core, gap: Q) -> bool:
            return all_closer(h, c, rho - d / 2 - gap) or apart(h, point(c), rho + d / 2 + gap)

    else:
        return None
    return {k: not clears(h, ZERO) for k, h in enumerate(cores) if not clears(h, GAP)}


# --- the parity -------------------------------------------------------------------------------


@dataclass
class Tally:
    accepted: int = 0
    clean: int = 0  # accepted, clear by 0.01 mm: no warning
    near: int = 0  # accepted within 0.01 mm of a rule, and the lint warns (17.6 allows it)
    fired: Counter[str] = field(default_factory=Counter[str])  # warnings, by code
    silent: Counter[str] = field(default_factory=Counter[str])  # refused by R1/4/5/7, no warning


def disagreements(
    case: Case, lint: Lint = lint_section_v2, tally: Tally | None = None
) -> list[str]:
    """Where the step, the lint and the truth disagree on `case` (the module docstring's 1 to 3)."""
    tally = tally if tally is not None else Tally()
    where = f"{case.stratum} {case.template} {case.params.get('holes')}"
    verdict = run(product, case.template, case.params)
    if isinstance(verdict, tuple) or (
        isinstance(verdict, Refused) and verdict.kind not in RULE_KINDS
    ):
        return [f"{where}: the step answers {verdict}, not a rule's verdict"]
    accepted = isinstance(verdict, Plan)
    tally.accepted += accepted
    hs = placed(case)
    plan = expand(case.template, bare(case.params), 1)
    truth, cores = Truth(plan), [shape(h) for h in hs]
    bad: list[str] = []
    doc, own = exploded(case, hs)
    ents = entities(doc)
    warnings = lint(ents)
    clean = accepted and clear_by(plan, hs, GAP)
    if clean:
        tally.clean += 1
        for name, got in (("template", lint(entities(templated(case)))), ("exploded", warnings)):
            if got:
                bad.append(f"{where}: clear by 0.01 mm, yet the {name} drawing warns {got}")
    for w in warnings:
        tally.fired[w.code] += 1
        met = meeting(w, ents, cores, truth, own)
        if met is None:
            bad.append(f"{where}: {w.code} {w.ids} has no counterpart rule in 17.6")
            continue
        if not met:
            bad.append(f"{where}: {w.code} {w.ids}: no hole meets it or comes within 0.01 mm")
            continue
        rule = RULE_OF[w.code]
        for k in (k for k, hard in sorted(met.items()) if hard):
            if accepted:
                bad.append(f"{where}: accepted, yet holes[{k}] meets {w.code} {w.ids} by R{rule}")
                continue
            refused = cast(Refused, verdict)
            j, r = int(refused.param[len("holes[") : -1]), int(refused.kind[1:])
            if j > k or (j == k and r > rule):
                bad.append(f"{where}: holes[{k}] meets {w.code} {w.ids}, yet R{rule} is "
                           f"passed: the step refuses holes[{j}] by R{r}")  # fmt: skip
    if accepted and warnings and not clean:
        tally.near += 1
    if isinstance(verdict, Refused) and int(verdict.kind[1:]) in (1, 4, 5, 7) and not warnings:
        tally.silent[verdict.kind] += 1
    return bad


@cache
def pool() -> tuple[Case, ...]:
    """The generator's cases whose holes reach the rules: accepted with holes, or refused by a
    rule (the reference's verdict, which C9-2's fuzz proves the product's)."""
    return tuple(
        case for case, outcome in fuzz()
        if (isinstance(outcome, Plan) and cast(list[object], case.params.get("holes") or []))
        or (isinstance(outcome, Refused) and outcome.kind in RULE_KINDS)
    )  # fmt: skip


def test_the_step_and_the_lint_agree_on_the_generators_cases() -> None:
    tally = Tally()
    bad = [d for case in pool() for d in disagreements(case, tally=tally)]
    assert not bad, f"{len(bad)} disagreements:\n" + "\n".join(bad[:15])
    print(f"\n{len(pool())} cases, {tally.accepted} accepted; clean by 0.01 mm: {tally.clean}; "
          f"accepted closer and warned: {tally.near}")  # fmt: skip
    print(f"  warnings: {dict(sorted(tally.fired.items()))}")
    print(f"  refused with no warning (contact besides): {dict(sorted(tally.silent.items()))}")
    # Not vacuous: 1 and 3 hold on many cases, every counterpart fires, and R4, R5 and R7 also
    # refuse holes the lint lets by ("and contact besides"). 17.6 claims no such slack for R1:
    # `hole-outside-face` warns at contact too, so R1 is reported but not required here.
    assert tally.clean >= 100, tally.clean
    assert set(RULE_OF) <= set(tally.fired), set(RULE_OF) - set(tally.fired)
    assert {"R4", "R5", "R7"} <= set(tally.silent), tally.silent


# --- the break-once table -------------------------------------------------------------------


def mutant(target: ModuleType, edits: tuple[tuple[str, str], ...]) -> ModuleType:
    path = cast(str, target.__file__)
    source = Path(path).read_text(encoding="utf-8")
    for old, new in edits:
        assert source.count(old) == 1, f"the edit no longer applies; re-pin the row: {old!r}"
        source = source.replace(old, new)
    name = f"{target.__name__}_parity_mutant_{abs(hash(edits))}"
    module = ModuleType(name)
    module.__file__ = path
    sys.modules[name] = module  # dataclasses look their module up while the source runs
    exec(compile(source, path, "exec"), module.__dict__)
    return module


@dataclass(frozen=True)
class Row:
    name: str
    what: str
    target: str  # "rules" (`hole_rules.py`, wired into the step) or "lint" (`section/lint.py`)
    edits: tuple[tuple[str, str], ...]
    case: Case


def _case(base: str, off: float, *hole: Json) -> Case:
    template, params = params_at(base, off)
    return Case("hand", template, {**params, "holes": list(hole)})


ON_BAR = circle((0.0, -240.0), 5.0)  # rc: on the bottom middle bar's centre, inside the hoop
NEAR_BAR = circle((0.0, -224.5), 5.0)  # rc: 0.5 mm clear of that bar's Ø20, every rule clear
CENTRED_DUCT = circle((0.0, 0.0), 50.0)  # Errata 18.3: across rc_all's two crossties
FAR_OUT = circle((1e5, 0.0), 1.0)  # outside the face, within the extent
ON_SPIRAL = circle((220.0, 127.0), 2.0)  # cc: across the spiral's centreline, between bars
SAFE = circle((37.5, -82.5), 1.0)  # rc and rc_all: a safe spot (`safe_spots`)
CORE = circle((0.0, 0.0), 10.0)  # cc: at the centre, inside the spiral
CONCRETE_RULE = "r.role == \"concrete\" and r.contains(p) and r.clearance(p) >= radius for r"
SPIRAL_IN = "circle_in_region(center, e.centerline_radius_mm, r) for r in concrete"

ROWS: tuple[Row, ...] = (
    Row("r1_dropped", "R1 not checked: a hole outside the face accepted", "rules",
        (("(1, _r1_face), ", ""),), _case("rc", 0.0, FAR_OUT)),
    Row("r4_dropped", "R4 not checked: a hole on a bar accepted", "rules",
        (("(4, _r4_bars),", ""),), _case("rc", 1234.5, ON_BAR)),
    Row("r5_dropped", "R5 not checked: the centred duct across two crossties accepted", "rules",
        (("(5, _r5_crossties), ", ""),), _case("rc_all", 0.1, CENTRED_DUCT)),
    Row("r7_dropped", "R7 not checked: a hole across the spiral accepted", "rules",
        ((", (7, _r7_circular_ties),", ","),), _case("cc", 40000.3, ON_SPIRAL)),
    Row("r4_after_r6", "R4 checked after R6: a hole on a hoop's bar named by R6", "rules",
        (("(4, _r4_bars),\n    (5, _r5_crossties), (6, _r6_hoops),",
          "(5, _r5_crossties), (6, _r6_hoops),\n    (4, _r4_bars),"),),
        _case("rc", 0.0, circle((140.0, 240.0), 12.0))),
    Row("lint_bar_reach", "bar-outside-concrete warns on a bar within 1 mm of a hole", "lint",
        ((CONCRETE_RULE, CONCRETE_RULE.replace(">= radius", ">= radius + 1.0")),),
        _case("rc", 0.0, NEAR_BAR)),
    Row("lint_hole_index", "hole-outside-face names the next hole", "lint",
        (("for k, hole in enumerate(r.holes)", "for k, hole in enumerate(r.holes, 1)"),),
        _case("rc", 0.1, FAR_OUT)),
    Row("lint_tie_any_hole", "crosstie-crosses-outside warns on any face with holes", "lint",
        (("segment_in_region(a, b, region) for region in concrete",
          "segment_in_region(a, b, region) and not region.holes for region in concrete"),),
        _case("rc_all", 1234.5, SAFE)),
    Row("lint_spiral_any_hole", "circular-tie-outside-face warns on any face with holes", "lint",
        ((SPIRAL_IN, SPIRAL_IN.replace(", r) for", ", r) and not r.holes for")),),
        _case("cc", 0.0, CORE)),
)  # fmt: skip


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch) -> Callable[[Row], Lint]:
    """Wire a row's mutant in: rules through the step's `require_holes_clear`, which
    `holes.expand_with_holes` looks up when it runs; a lint returned as the lint to use."""

    def wire(row: Row) -> Lint:
        if row.target == "rules":
            rules = mutant(hole_rules, row.edits)
            monkeypatch.setattr(holes, "require_holes_clear", rules.require_holes_clear)
            return lint_section_v2
        return cast(Lint, mutant(lint_module, row.edits).lint_section_v2)

    return wire


@pytest.mark.parametrize("row", ROWS, ids=[r.name for r in ROWS])
def test_each_row_kills_its_mutant(row: Row, wired: Callable[[Row], Lint]) -> None:
    assert disagreements(row.case) == [], f"{row.name}: the product fails its own case"
    lint = wired(row)
    assert disagreements(row.case, lint), f"{row.name} ({row.what}) survives its case"


def _first_kill(cases: Iterable[Case], lint: Lint) -> Case | None:
    return next((c for c in cases if disagreements(c, lint)), None)


@pytest.mark.parametrize("row", ROWS, ids=[r.name for r in ROWS])
def test_the_generator_kills_each_row(row: Row, wired: Callable[[Row], Lint]) -> None:
    lint = wired(row)
    assert _first_kill(pool(), lint) is not None, f"the generator lets {row.name} through"


def test_the_rows_are_distinct() -> None:
    names = [r.name for r in ROWS]
    assert len(set(names)) == len(names) and len({(r.target, r.edits) for r in ROWS}) == len(ROWS)
