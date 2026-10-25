"""Section annotation tag extraction (ADR 0031 §3.5, spec ape-design §4 D4).

Extracts what a plan (`top`) view of a section should say from the document and its
projected drawables: tag groups for each hoop (its enclosed bars, its tie tag optionally
headed by the hoop's label, and its enclosed crossties), the web steel, and whole-section
notes (wall-leg curtains and cover). `render/annotate.py` plans where the tag stacks sit and
writes the SVG.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from apeCAD.entities import Bar, CoverGuide, Crosstie, Entity, EntityId, Hoop, WallLeg
from apeCAD.render.drawable import Drawable
from apeCAD.render.views import Vec2, View

TAG_CHAR_PX = 5.6  # a generous Arial Narrow average at 2.0 mm (10 px)


@dataclass(frozen=True, slots=True)
class Tag:
    text: str
    targets: tuple[Vec2, ...]  # view-plane mm; the leader goes to the one nearest its stack

    def width_px(self) -> float:
        return len(self.text) * TAG_CHAR_PX


@dataclass(frozen=True, slots=True)
class Group:
    tags: tuple[Tag, ...]
    anchor: Vec2  # view-plane mm: the stack sits beside this


@dataclass(frozen=True, slots=True)
class SectionNotes:
    """What to annotate: the concrete's view-plane box and the tag groups."""

    box_mm: tuple[Vec2, Vec2]
    groups: tuple[Group, ...]
    named: frozenset[EntityId] = frozenset()  # entities whose label the notes already print

    @property
    def tags(self) -> tuple[Tag, ...]:
        return tuple(tag for group in self.groups for tag in group.tags)


def phi(designation: str) -> str:
    """`Ø16` → `Φ16`: the office tag glyph (spec §3.4)."""
    return designation.replace("Ø", "Φ")


def _mm(value: float) -> str:
    return f"{value:.0f}" if abs(value - round(value)) < 1e-6 else f"{value:g}"


def section_notes(
    view: View, entities: Mapping[EntityId, Entity], items: list[Drawable], labels: bool = False
) -> SectionNotes | None:
    """Notes for a plan of a section, or None (another view, or no concrete drawn). With
    `labels`, a hoop's label heads its tie tag."""
    if view.name != "top":
        return None
    concrete = [d for d in items if d.layer == "concrete"]
    if not concrete:
        return None
    corners = [view.project(p) for d in concrete for path, _ in d.paths for p in path]
    u0, v0 = min(u for u, _ in corners), min(v for _, v in corners)
    u1, v1 = max(u for u, _ in corners), max(v for _, v in corners)
    bars = [(d, e) for d in items if isinstance(e := entities.get(d.entity_id), Bar)]
    ties = [(d, e) for d in items if isinstance(e := entities.get(d.entity_id), Crosstie)]
    used: set[EntityId] = set()
    named = {concrete[0].entity_id}  # the view title is SECTION plus this face's label
    groups: list[Group] = []
    for d in items:
        hoop = entities.get(d.entity_id)
        if not isinstance(hoop, Hoop):
            continue
        ring = [view.project(p) for p in d.paths[0][0]]  # the ring, not its hook ticks
        in_bars = [(bd, b) for bd, b in bars if b.entity_id not in used
                   and _inside(_centre(view, bd), ring)]
        in_ties = [(td, t) for td, t in ties if t.entity_id not in used
                   and _inside(_mid(view, td), ring)]
        used.update(b.entity_id for _, b in in_bars)
        used.update(t.entity_id for _, t in in_ties)
        tie_text = f"Tie {phi(hoop.designation)} @ {_mm(hoop.spacing_mm)} mm"
        if labels and hoop.label:
            tie_text = f"{hoop.label}: {tie_text}"
            named.add(hoop.entity_id)
        tags = [*_bar_tags(view, in_bars), Tag(tie_text, tuple(ring)), *_tie_tags(view, in_ties)]
        groups.append(Group(tuple(tags), _box_centre(ring)))
    web_bars = [(bd, b) for bd, b in bars if b.entity_id not in used]
    web_ties = [(td, t) for td, t in ties if t.entity_id not in used]
    if web_bars or web_ties:
        points = [_centre(view, bd) for bd, _ in web_bars]
        points += [_mid(view, td) for td, _ in web_ties]
        tags = [*_bar_tags(view, web_bars), *_tie_tags(view, web_ties)]
        groups.append(Group(tuple(tags), _box_centre(points)))
    whole = _section_tags(view, entities, items)
    if whole:
        groups.append(Group(tuple(whole), ((u0 + u1) / 2.0, (v0 + v1) / 2.0)))
    merged = tuple(_merged(g) for g in groups)
    return SectionNotes(((u0, v0), (u1, v1)), merged, frozenset(named))


def _merged(group: Group) -> Group:
    """One tag per text in a group (two legs with the same web steel read once)."""
    by_text: dict[str, list[Vec2]] = {}
    for tag in group.tags:
        by_text.setdefault(tag.text, []).extend(tag.targets)
    return Group(tuple(Tag(text, tuple(pts)) for text, pts in by_text.items()), group.anchor)


def _centre(view: View, d: Drawable) -> Vec2:
    return view.project(d.paths[0][0][0])


def _mid(view: View, d: Drawable) -> Vec2:
    a, b = (view.project(p) for p in (d.paths[0][0][0], d.paths[0][0][-1]))
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


def _box_centre(points: list[Vec2]) -> Vec2:
    us, vs = [p[0] for p in points], [p[1] for p in points]
    return ((min(us) + max(us)) / 2.0, (min(vs) + max(vs)) / 2.0)


def _inside(point: Vec2, ring: list[Vec2]) -> bool:
    """Even-odd ray cast; the hoop ring is the bar hull grown outward, so its bars are in."""
    x, y = point
    inside = False
    for i, (ax, ay) in enumerate(ring):
        bx, by = ring[i - 1]
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            inside = not inside
    return inside


def _along(points: list[Vec2], closed: bool, per_edge: int = 8) -> list[Vec2]:
    """Leader targets along a line or ring, not only its corners."""
    ends = points + points[:1] if closed else points
    out: list[Vec2] = []
    for (ax, ay), (bx, by) in zip(ends, ends[1:], strict=False):
        out.extend((ax + (bx - ax) * k / per_edge, ay + (by - ay) * k / per_edge)
                   for k in range(per_edge))
    return out + ends[-1:]


def _bar_tags(view: View, members: list[tuple[Drawable, Bar]]) -> list[Tag]:
    by_designation: dict[str, list[Vec2]] = {}
    for d, bar in members:
        by_designation.setdefault(bar.designation, []).append(_centre(view, d))
    return [
        Tag(f"{len(points)} {phi(designation)}", tuple(points))
        for designation, points in by_designation.items()
    ]


def _tie_tags(view: View, members: list[tuple[Drawable, Crosstie]]) -> list[Tag]:
    by_kind: dict[tuple[str, float], list[Vec2]] = {}
    for d, tie in members:
        by_kind.setdefault((tie.designation, tie.spacing_mm), []).append(_mid(view, d))
    out: list[Tag] = []
    for (designation, spacing), points in by_kind.items():
        count = f" ×{len(points)}" if len(points) > 1 else ""
        text = f"Crosstie {phi(designation)} @ {_mm(spacing)} mm{count}"
        out.append(Tag(text, tuple(points)))
    return out


def _section_tags(
    view: View, entities: Mapping[EntityId, Entity], items: list[Drawable]
) -> list[Tag]:
    out: list[Tag] = []
    for d in items:
        entity = entities.get(d.entity_id)
        points = tuple(
            q for path, closed in d.paths for q in _along([view.project(p) for p in path], closed)
        )
        if isinstance(entity, WallLeg) and entity.horizontal is not None:
            steel = entity.horizontal
            text = f"{phi(steel.designation)} @ {_mm(steel.spacing_mm)} mm"
            out.append(Tag(f"{text}, {steel.curtains} curtains", points))
        elif isinstance(entity, CoverGuide):
            out.append(Tag(f"Cover {_mm(entity.cover_mm)} mm", points))
    return out


__all__ = [
    "TAG_CHAR_PX",
    "Group",
    "SectionNotes",
    "Tag",
    "Vec2",
    "_along",
    "_bar_tags",
    "_box_centre",
    "_centre",
    "_inside",
    "_merged",
    "_mid",
    "_mm",
    "_section_tags",
    "_tie_tags",
    "phi",
    "section_notes",
]
