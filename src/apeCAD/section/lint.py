"""Section lint (ADR 0024, plan stage C3): drawing warnings, returned and never raised.

`lint_section(entities)` takes the document's entities (this package never imports
`draft/` or `document`) and returns `LintWarning`s in a fixed order: by code as listed in
`LINT_CODES`, then by the entity ids involved. They feed the `warnings[]` of the
section-draft (ADR 0025): advisory, and no consumer gates on them. apeConcrete's reader is
the gate for what it refuses (a face without a leg, an inclined leg).

`lint_section_v2(entities)` is the lint of a v2 draft (ADR 0039 decision 7, Errata 2 and 8.3):
the seven v1 codes that keep their meaning, read on many faces with holes and circles, then
the v2 codes, in `LINT_CODES_V2` order. Its region tests are exact for points; overlap and
cover are probed next to every boundary edge (`apeCAD.section.regions`), so a found overlap
is real and a sliver thinner than the probe offset can be missed.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from apeCAD.entities import (
    Bar,
    CircularTie,
    ConcreteFace,
    CoverGuide,
    Crosstie,
    Entity,
    EntityId,
    Hoop,
    Point,
    WallLeg,
)
from apeCAD.section.geometry import Point2
from apeCAD.section.regions import (
    Region,
    boundary_probes,
    circle_in_region,
    curve_strictly_inside,
    distance,
    edge_distance,
    locate,
    regions_of,
    segment_in_region,
    segment_inside,
)

LINT_CODES = (
    "bar-overlap",
    "bar-outside-concrete",
    "hoop-bar-not-in-face",
    "crosstie-crosses-outside",
    "face-without-cover-guide",
    "face-without-wall-leg",
    "inclined-wall-leg",
    "tie-mismatch-in-core",
    "more-than-one-solid-face",
)

LINT_CODES_V2 = (
    "bar-overlap",
    "bar-outside-concrete",
    "hoop-bar-not-in-face",
    "crosstie-crosses-outside",
    "face-without-cover-guide",
    "inclined-wall-leg",
    "tie-mismatch-in-core",
    "same-role-overlap",
    "hole-outside-face",
    "void-outside-solid",
    "bar-in-void",
    "bar-in-steel",
    "circular-tie-outside-face",
    "steel-shape-unresolved",
)
"""A v2 draft's codes, in order (specs/section-draft-v2.md "Lint codes"). The two v1-only codes
are absent (Errata 2); `steel-shape-unresolved` is reserved and never emitted (Errata 8.1)."""
RESERVED_LINT_CODES_V2 = ("steel-shape-unresolved",)


@dataclass(frozen=True, slots=True)
class LintWarning:
    """One warning: a code from `LINT_CODES`, the entities involved, and a sentence."""

    code: str
    ids: tuple[EntityId, ...]
    message: str

    def to_dict(self) -> dict[str, object]:
        """The section-draft form, `{code, ids, message}` (ADR 0025)."""
        return {"code": self.code, "ids": list(self.ids), "message": self.message}


def lint_section(entities: Mapping[EntityId, Entity]) -> tuple[LintWarning, ...]:
    """Every section warning for these entities; an empty tuple for a clean section."""
    view = _View(entities)
    return (
        *_bar_overlap(view),
        *_bar_outside_concrete(view),
        *_hoop_bar_not_in_face(view),
        *_crosstie_crosses_outside(view),
        *_face_without(view, CoverGuide, "face-without-cover-guide", "cover guide"),
        *_face_without(view, WallLeg, "face-without-wall-leg", "wall leg"),
        *_inclined_wall_leg(view),
        *_tie_mismatch_in_core(view),
        *_more_than_one_solid_face(view),
    )


class _View:
    """The section kinds, by id order, and point positions on the plane."""

    def __init__(self, entities: Mapping[EntityId, Entity]) -> None:
        ordered = [entities[i] for i in sorted(entities)]
        self.xy: dict[EntityId, Point2] = {
            e.entity_id: (e.xyz_mm.x_mm, e.xyz_mm.y_mm) for e in ordered if isinstance(e, Point)
        }
        self.faces = [e for e in ordered if isinstance(e, ConcreteFace) and e.role == "solid"]
        self.bars = [e for e in ordered if isinstance(e, Bar) and e.point_id in self.xy]
        self.hoops = [e for e in ordered if isinstance(e, Hoop)]
        self.ties = [e for e in ordered if isinstance(e, Crosstie)]
        self.legs = [e for e in ordered if isinstance(e, WallLeg)]
        self.guides = [e for e in ordered if isinstance(e, CoverGuide)]
        self.bar_xy = {bar.entity_id: self.xy[bar.point_id] for bar in self.bars}
        self.rings: dict[EntityId, list[Point2]] = {
            face.entity_id: [self.xy[i] for i in face.point_ids if i in self.xy]
            for face in self.faces
        }


def _bar_overlap(view: _View) -> list[LintWarning]:
    out: list[LintWarning] = []
    for k, a in enumerate(view.bars):
        for b in view.bars[k + 1 :]:
            gap = distance(view.bar_xy[a.entity_id], view.bar_xy[b.entity_id])
            if gap < (a.diameter_mm + b.diameter_mm) / 2.0:
                out.append(
                    LintWarning(
                        "bar-overlap",
                        (a.entity_id, b.entity_id),
                        f"bars {a.entity_id} ({a.designation}) and {b.entity_id} "
                        f"({b.designation}) overlap: centres {gap:g} mm apart",
                    )
                )
    return out


def _bar_outside_concrete(view: _View) -> list[LintWarning]:
    out: list[LintWarning] = []
    for bar in view.bars:
        p = view.bar_xy[bar.entity_id]
        radius = bar.diameter_mm / 2.0
        inside = any(
            locate(p, ring) > 0 and edge_distance(p, ring) >= radius
            for ring in view.rings.values()
        )
        if not inside:
            out.append(
                LintWarning(
                    "bar-outside-concrete",
                    (bar.entity_id,),
                    f"bar {bar.entity_id} ({bar.designation} at {_fmt(p)}) is not wholly "
                    "inside a concrete face",
                )
            )
    return out


def _hoop_bar_not_in_face(view: _View) -> list[LintWarning]:
    out: list[LintWarning] = []
    for hoop in view.hoops:
        members = [i for i in hoop.bar_ids if i in view.bar_xy]
        best: list[EntityId] = members
        for ring in view.rings.values():
            outside = [i for i in members if locate(view.bar_xy[i], ring) < 0]
            if len(outside) < len(best):
                best = outside
        if best:
            out.append(
                LintWarning(
                    "hoop-bar-not-in-face",
                    (hoop.entity_id, *best),
                    f"hoop {hoop.entity_id} has bars {list(best)} outside the concrete face "
                    "that holds the rest; a hoop lies in one face",
                )
            )
    return out


def _crosstie_crosses_outside(view: _View) -> list[LintWarning]:
    out: list[LintWarning] = []
    for tie in view.ties:
        a = view.bar_xy.get(tie.bar_a_id)
        b = view.bar_xy.get(tie.bar_b_id)
        if a is None or b is None:
            continue
        if not any(segment_inside(a, b, ring) for ring in view.rings.values()):
            out.append(
                LintWarning(
                    "crosstie-crosses-outside",
                    (tie.entity_id, tie.bar_a_id, tie.bar_b_id),
                    f"crosstie {tie.entity_id} from bar {tie.bar_a_id} to bar {tie.bar_b_id} "
                    "leaves the concrete",
                )
            )
    return out


def _face_without(
    view: _View, kind: type[CoverGuide] | type[WallLeg], code: str, what: str
) -> list[LintWarning]:
    owners = {e.face_id for e in (view.guides if kind is CoverGuide else view.legs)}
    return [
        LintWarning(code, (face.entity_id,), f"concrete face {face.entity_id} has no {what}")
        for face in view.faces
        if face.entity_id not in owners
    ]


def _inclined_wall_leg(view: _View) -> list[LintWarning]:
    out: list[LintWarning] = []
    for leg in view.legs:
        start = view.xy.get(leg.start_id)
        end = view.xy.get(leg.end_id)
        if start is None or end is None:
            continue
        dx, dy = end[0] - start[0], end[1] - start[1]
        if dx != 0.0 and dy != 0.0:
            angle = math.degrees(math.atan2(dy, dx))
            out.append(
                LintWarning(
                    "inclined-wall-leg",
                    (leg.entity_id,),
                    f"wall leg {leg.entity_id} runs at {angle:g}°; apeConcrete reads "
                    "horizontal and vertical legs only",
                )
            )
    return out


def _tie_mismatch_in_core(view: _View) -> list[LintWarning]:
    """A crosstie inside a hoop's core whose size or spacing differs from the hoop's."""
    out: list[LintWarning] = []
    for hoop in view.hoops:
        core = [view.bar_xy[i] for i in hoop.bar_ids if i in view.bar_xy]
        if len(core) < 3:
            continue
        for tie in view.ties:
            a = view.bar_xy.get(tie.bar_a_id)
            b = view.bar_xy.get(tie.bar_b_id)
            if a is None or b is None or locate(a, core) < 0 or locate(b, core) < 0:
                continue
            if tie.designation != hoop.designation or tie.spacing_mm != hoop.spacing_mm:
                out.append(
                    LintWarning(
                        "tie-mismatch-in-core",
                        (hoop.entity_id, tie.entity_id),
                        f"crosstie {tie.entity_id} ({tie.designation} at {tie.spacing_mm:g} "
                        f"mm) differs from hoop {hoop.entity_id} ({hoop.designation} at "
                        f"{hoop.spacing_mm:g} mm) in the same core",
                    )
                )
    return out


def _more_than_one_solid_face(view: _View) -> list[LintWarning]:
    if len(view.faces) < 2:
        return []
    ids = tuple(face.entity_id for face in view.faces)
    return [
        LintWarning(
            "more-than-one-solid-face",
            ids,
            f"{len(ids)} solid concrete faces {list(ids)}; a section in v1 has exactly one",
        )
    ]


def _fmt(p: Point2) -> str:
    return f"({p[0]:g}, {p[1]:g})"


# --- v2 (ADR 0039 decision 7) ---------------------------------------------------------------


def lint_section_v2(entities: Mapping[EntityId, Entity]) -> tuple[LintWarning, ...]:
    """Every v2 section warning, in `LINT_CODES_V2` order; empty for a clean section."""
    view = _View(entities)
    regions = regions_of(entities, view.xy)
    concrete = [r for r in regions if r.role == "concrete"]
    located = {b.entity_id: _bar_location(view.bar_xy[b.entity_id], regions) for b in view.bars}
    return (
        *_bar_overlap(view),
        *_bar_outside_concrete_v2(view, regions, located),
        *_hoop_bar_not_in_face_v2(view, concrete),
        *_crosstie_crosses_outside_v2(view, concrete),
        *_face_without_cover_guide_v2(view, concrete),
        *_inclined_wall_leg(view),
        *_tie_mismatch_in_core(view),
        *_same_role_overlap(regions),
        *_hole_outside_face(regions),
        *_void_outside_solid(regions),
        *_bar_in(view, located, "void"),
        *_bar_in(view, located, "steel"),
        *_circular_tie_outside_face(entities, view.xy, concrete),
    )


def _bar_location(p: Point2, regions: Sequence[Region]) -> str | None:
    """Where the precedence puts a bar centre: "void" > "steel" > None (concrete or nothing)."""
    for role in ("void", "steel"):
        if any(r.role == role and r.contains(p) for r in regions):
            return role
    return None


def _bar_outside_concrete_v2(
    view: _View, regions: Sequence[Region], located: Mapping[EntityId, str | None]
) -> list[LintWarning]:
    """v1's test on the concrete regions, for a bar not already in a void or steel face; the
    bar's disc must also stay clear of every void and steel face (precedence, Errata 8.3)."""
    out: list[LintWarning] = []
    for bar in view.bars:
        if located[bar.entity_id] is not None:
            continue
        p, radius = view.bar_xy[bar.entity_id], bar.diameter_mm / 2.0
        inside = any(
            r.role == "concrete" and r.contains(p) and r.clearance(p) >= radius for r in regions
        ) and all(r.clearance(p) >= radius for r in regions if r.role != "concrete")
        if not inside:
            out.append(
                LintWarning(
                    "bar-outside-concrete",
                    (bar.entity_id,),
                    f"bar {bar.entity_id} ({bar.designation} at {_fmt(p)}) is not wholly "
                    "inside a concrete face",
                )
            )
    return out


def _hoop_bar_not_in_face_v2(view: _View, concrete: Sequence[Region]) -> list[LintWarning]:
    out: list[LintWarning] = []
    for hoop in view.hoops:
        members = [i for i in hoop.bar_ids if i in view.bar_xy]
        best: list[EntityId] = members
        for region in concrete:
            outside = [i for i in members if not region.covers(view.bar_xy[i])]
            if len(outside) < len(best):
                best = outside
        if best:
            out.append(
                LintWarning(
                    "hoop-bar-not-in-face",
                    (hoop.entity_id, *best),
                    f"hoop {hoop.entity_id} has bars {list(best)} outside the concrete face "
                    "that holds the rest; a hoop lies in one face",
                )
            )
    return out


def _crosstie_crosses_outside_v2(view: _View, concrete: Sequence[Region]) -> list[LintWarning]:
    out: list[LintWarning] = []
    for tie in view.ties:
        a = view.bar_xy.get(tie.bar_a_id)
        b = view.bar_xy.get(tie.bar_b_id)
        if a is None or b is None:
            continue
        if not any(segment_in_region(a, b, region) for region in concrete):
            out.append(
                LintWarning(
                    "crosstie-crosses-outside",
                    (tie.entity_id, tie.bar_a_id, tie.bar_b_id),
                    f"crosstie {tie.entity_id} from bar {tie.bar_a_id} to bar {tie.bar_b_id} "
                    "leaves the concrete",
                )
            )
    return out


def _face_without_cover_guide_v2(view: _View, concrete: Sequence[Region]) -> list[LintWarning]:
    """Concrete faces only: a steel or void face never raises it (Errata 8.3)."""
    owners = {guide.face_id for guide in view.guides}
    return [
        LintWarning(
            "face-without-cover-guide",
            (r.face_id,),
            f"concrete face {r.face_id} has no cover guide",
        )
        for r in concrete
        if r.face_id not in owners
    ]


def _same_role_overlap(regions: Sequence[Region]) -> list[LintWarning]:
    out: list[LintWarning] = []
    for k, a in enumerate(regions):
        for b in regions[k + 1 :]:
            if a.role != b.role:
                continue
            if any(a.contains(q) and b.contains(q) for q in boundary_probes((a, b))):
                out.append(
                    LintWarning(
                        "same-role-overlap",
                        (a.face_id, b.face_id),
                        f"{a.role} faces {a.face_id} and {b.face_id} overlap; the consumer "
                        "decides whether to merge them or refuse",
                    )
                )
    return out


def _hole_outside_face(regions: Sequence[Region]) -> list[LintWarning]:
    """A hole is named `(face_id, hole_index)`: the face's id in `ids`, the index in the text."""
    return [
        LintWarning(
            "hole-outside-face",
            (r.face_id,),
            f"hole_index {k} of face {r.face_id} is not strictly inside the face's boundary",
        )
        for r in regions
        for k, hole in enumerate(r.holes)
        if not curve_strictly_inside(hole, r.boundary)
    ]


def _void_outside_solid(regions: Sequence[Region]) -> list[LintWarning]:
    solids = [r for r in regions if r.role != "void"]
    out: list[LintWarning] = []
    for void in (r for r in regions if r.role == "void"):
        probes = boundary_probes((void, *solids))
        if any(void.contains(q) and not any(s.covers(q) for s in solids) for q in probes):
            out.append(
                LintWarning(
                    "void-outside-solid",
                    (void.face_id,),
                    f"void face {void.face_id} is not covered by a concrete or steel face",
                )
            )
    return out


def _bar_in(view: _View, located: Mapping[EntityId, str | None], role: str) -> list[LintWarning]:
    return [
        LintWarning(
            f"bar-in-{role}",
            (bar.entity_id,),
            f"bar {bar.entity_id} ({bar.designation} at {_fmt(view.bar_xy[bar.entity_id])}) "
            f"lies where a {role} face wins",
        )
        for bar in view.bars
        if located[bar.entity_id] == role
    ]


def _circular_tie_outside_face(
    entities: Mapping[EntityId, Entity],
    xy: Mapping[EntityId, Point2],
    concrete: Sequence[Region],
) -> list[LintWarning]:
    out: list[LintWarning] = []
    for e in (entities[i] for i in sorted(entities)):
        if not isinstance(e, CircularTie) or e.center_id not in xy:
            continue
        center = xy[e.center_id]
        if not any(circle_in_region(center, e.centerline_radius_mm, r) for r in concrete):
            out.append(
                LintWarning(
                    "circular-tie-outside-face",
                    (e.entity_id,),
                    f"circular tie {e.entity_id} ({e.kind}, centreline radius "
                    f"{e.centerline_radius_mm:g} mm at {_fmt(center)}) is not inside a "
                    "concrete face",
                )
            )
    return out


