"""Section lint (ADR 0024, plan stage C3): drawing warnings, returned and never raised.

`lint_section(entities)` takes the document's entities (this package never imports
`draft/` or `document`) and returns `LintWarning`s in a fixed order: by code as listed in
`LINT_CODES`, then by the entity ids involved. They feed the `warnings[]` of the
section-draft (ADR 0025): advisory, and no consumer gates on them. apeConcrete's reader is
the gate for what it refuses (a face without a leg, an inclined leg).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

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
from apeCAD.section.geometry import Point2

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
            gap = _distance(view.bar_xy[a.entity_id], view.bar_xy[b.entity_id])
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
            _locate(p, ring) > 0 and _edge_distance(p, ring) >= radius
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
            outside = [i for i in members if _locate(view.bar_xy[i], ring) < 0]
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
        if not any(_segment_inside(a, b, ring) for ring in view.rings.values()):
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
            if a is None or b is None or _locate(a, core) < 0 or _locate(b, core) < 0:
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


def _cross(o: Point2, a: Point2, b: Point2) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _distance(a: Point2, b: Point2) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _on_segment(p: Point2, a: Point2, b: Point2) -> bool:
    return (
        _cross(a, b, p) == 0.0
        and min(a[0], b[0]) <= p[0] <= max(a[0], b[0])
        and min(a[1], b[1]) <= p[1] <= max(a[1], b[1])
    )


def _locate(p: Point2, ring: Sequence[Point2]) -> int:
    """1 inside, 0 on the boundary, -1 outside (even-odd rule)."""
    n = len(ring)
    if n < 3:
        return -1
    inside = False
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        if _on_segment(p, a, b):
            return 0
        if (a[1] > p[1]) != (b[1] > p[1]):
            x = a[0] + (p[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if x > p[0]:
                inside = not inside
    return 1 if inside else -1


def _edge_distance(p: Point2, ring: Sequence[Point2]) -> float:
    """Shortest distance from p to the ring's edges."""
    best = math.inf
    n = len(ring)
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length2 = dx * dx + dy * dy
        t = 0.0 if length2 == 0.0 else ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2
        t = min(1.0, max(0.0, t))
        best = min(best, _distance(p, (a[0] + t * dx, a[1] + t * dy)))
    return best


def _segment_inside(a: Point2, b: Point2, ring: Sequence[Point2]) -> bool:
    """Segment ab stays inside the ring or on its boundary.

    Cut ab where it meets an edge or passes a vertex; it is inside when both ends and the
    midpoint of every piece between cuts are inside or on the boundary. The cut points
    themselves are not probed: they lie on an edge, where rounding may put them outside.
    """
    cuts = {0.0, 1.0}
    n = len(ring)
    rx, ry = b[0] - a[0], b[1] - a[1]
    for i in range(n):
        c, d = ring[i], ring[(i + 1) % n]
        sx, sy = d[0] - c[0], d[1] - c[1]
        denominator = rx * sy - ry * sx
        if denominator != 0.0:
            t = ((c[0] - a[0]) * sy - (c[1] - a[1]) * sx) / denominator
            u = ((c[0] - a[0]) * ry - (c[1] - a[1]) * rx) / denominator
            if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
                cuts.add(t)
        length2 = rx * rx + ry * ry
        if length2 > 0.0:
            t = ((c[0] - a[0]) * rx + (c[1] - a[1]) * ry) / length2
            if 0.0 <= t <= 1.0:
                cuts.add(t)  # a vertex the segment may graze
    ordered = sorted(cuts)
    probes = [0.0, 1.0, *((s + e) / 2.0 for s, e in zip(ordered, ordered[1:], strict=False))]
    return all(_locate((a[0] + t * rx, a[1] + t * ry), ring) >= 0 for t in probes)


def _fmt(p: Point2) -> str:
    return f"({p[0]:g}, {p[1]:g})"
