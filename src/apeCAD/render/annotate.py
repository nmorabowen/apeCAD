"""Section annotation for the SVG render (ADR 0031 §3.5, spec ape-design §3.2, stage D4).

Derived at render time from the document, never stored: no op, no log entry, no change to
the section-draft export. In a plan (top) view of a section it adds tags with leaders in a
column right of the concrete (bar groups, ties, crossties, web steel, cover), the overall
dimensions below and left of it, and a scale note under the view title. Tags keep the
office structure in English and millimetres: `10 Φ20`, `Tie Φ10 @ 100 mm`. The document
spells designations `Ø`; the drawing prints `Φ` (spec §3.4), here and nowhere else.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from xml.sax.saxutils import escape

from apeCAD.entities import Bar, CoverGuide, Crosstie, Entity, EntityId, Hoop, WallLeg
from apeCAD.render.drawable import Drawable
from apeCAD.render.style import (
    ANNOTATION_PEN_PX,
    BLUE,
    PX_PER_PAPER_MM,
    TEXT_PX,
    WORKING_FONT,
)
from apeCAD.render.views import View

Vec2 = tuple[float, float]
ToPx = Callable[[Vec2], Vec2]

DIM_TEXT_PX = PX_PER_PAPER_MM * 2.5  # ADR-006 default linear dimension, 2.5 mm
TAG_CHAR_PX = 5.6  # a generous Arial Narrow average at 10 px
TAG_LINE_PX = 16.0  # tag pitch in the column
LEADER_RUN_PX = 28.0  # from the concrete's right edge to the tag column
TEXT_INSET_PX = 4.0  # leader end to tag text
DIM_OFFSET_PX = 26.0  # dimension line off the concrete
EXT_GAP_PX = 3.0  # extension line gap at the object
EXT_OVER_PX = 4.0  # extension line past the dimension line
ARROW_PX = 8.0  # filled 30-degree arrowhead length (ADR-006 "Arrow Filled 30")
FRAME_PAD_PX = 10.0
LEGEND_PX = 54.0  # title, its rule, the scale note and the scale bar, bottom left
MIN_DRAWING_PX = 120.0  # below this much room for the section, no annotation


@dataclass(frozen=True, slots=True)
class Tag:
    text: str
    target: Vec2  # view-plane mm


@dataclass(frozen=True, slots=True)
class SectionNotes:
    """What to annotate: the concrete's view-plane box and the tags, top to bottom."""

    box_mm: tuple[Vec2, Vec2]
    tags: tuple[Tag, ...]

    def padding_px(self) -> tuple[float, float, float, float]:
        """Room around the concrete, left, top, right, bottom, in pixels."""
        widest = max((self.tag_width_px(t) for t in self.tags), default=0.0)
        left = DIM_OFFSET_PX + DIM_TEXT_PX + FRAME_PAD_PX
        right = LEADER_RUN_PX + TEXT_INSET_PX + widest + FRAME_PAD_PX
        bottom = DIM_OFFSET_PX + DIM_TEXT_PX + LEGEND_PX
        return left, FRAME_PAD_PX + TAG_LINE_PX, right, bottom

    @staticmethod
    def tag_width_px(tag: Tag) -> float:
        return len(tag.text) * TAG_CHAR_PX


def phi(designation: str) -> str:
    """`Ø16` → `Φ16`: the office tag glyph (spec §3.4)."""
    return designation.replace("Ø", "Φ")


def _dim(value: float) -> str:
    """Dimensions read in whole millimetres, like every APE drawing."""
    return f"{round(value):d}"


def _mm(value: float) -> str:
    return f"{value:.0f}" if abs(value - round(value)) < 1e-6 else f"{value:g}"


def section_notes(
    view: View, entities: Mapping[EntityId, Entity], items: list[Drawable]
) -> SectionNotes | None:
    """Notes for a plan of a section, or None (another view, or no concrete drawn)."""
    if view.name != "top":
        return None
    by_id = {d.entity_id: d for d in items}
    concrete = [d for d in items if d.layer == "concrete"]
    if not concrete:
        return None
    corners = [view.project(p) for d in concrete for path, _ in d.paths for p in path]
    box = (
        (min(u for u, _ in corners), min(v for _, v in corners)),
        (max(u for u, _ in corners), max(v for _, v in corners)),
    )
    tags: list[Tag] = []
    tags += _bar_tags(view, entities, by_id)
    tags += _grouped(view, entities, by_id, Hoop, "Tie")
    tags += _grouped(view, entities, by_id, Crosstie, "Crosstie")
    tags += _leg_tags(view, entities, by_id)
    tags += _cover_tags(view, entities, by_id)
    tags.sort(key=lambda tag: (-tag.target[1], tag.text))
    return SectionNotes(box, tuple(tags))


def _rightmost(view: View, d: Drawable) -> Vec2:
    """The drawable's point nearest the tag column (largest u, then largest v)."""
    pts = [view.project(p) for path, _ in d.paths for p in path]
    u, v = max(pts, key=lambda uv: (uv[0], uv[1]))
    return (u + d.radius_mm, v)


def _bar_tags(
    view: View, entities: Mapping[EntityId, Entity], by_id: Mapping[EntityId, Drawable]
) -> list[Tag]:
    groups: dict[str, list[Drawable]] = {}
    for d in by_id.values():
        entity = entities.get(d.entity_id)
        if isinstance(entity, Bar):
            groups.setdefault(entity.designation, []).append(d)
    out: list[Tag] = []
    for designation, members in groups.items():
        target = max((_rightmost(view, d) for d in members), key=lambda uv: (uv[0], uv[1]))
        out.append(Tag(f"{len(members)} {phi(designation)}", target))
    return out


def _grouped(
    view: View,
    entities: Mapping[EntityId, Entity],
    by_id: Mapping[EntityId, Drawable],
    kind: type[Hoop] | type[Crosstie],
    noun: str,
) -> list[Tag]:
    """One tag per designation and spacing, `×n` when it stands for several."""
    groups: dict[tuple[str, float], list[Drawable]] = {}
    for d in by_id.values():
        entity = entities.get(d.entity_id)
        if isinstance(entity, kind):
            groups.setdefault((entity.designation, entity.spacing_mm), []).append(d)
    out: list[Tag] = []
    for (designation, spacing), members in groups.items():
        target = max((_rightmost(view, d) for d in members), key=lambda uv: (uv[0], uv[1]))
        count = f" ×{len(members)}" if len(members) > 1 else ""
        out.append(Tag(f"{noun} {phi(designation)} @ {_mm(spacing)} mm{count}", target))
    return out


def _leg_tags(
    view: View, entities: Mapping[EntityId, Entity], by_id: Mapping[EntityId, Drawable]
) -> list[Tag]:
    out: list[Tag] = []
    for d in by_id.values():
        leg = entities.get(d.entity_id)
        if isinstance(leg, WallLeg) and leg.horizontal is not None:
            steel = leg.horizontal
            text = (
                f"{phi(steel.designation)} @ {_mm(steel.spacing_mm)} mm, "
                f"{steel.curtains} curtains"
            )
            out.append(Tag(text, _rightmost(view, d)))
    return out


def _cover_tags(
    view: View, entities: Mapping[EntityId, Entity], by_id: Mapping[EntityId, Drawable]
) -> list[Tag]:
    out: list[Tag] = []
    for d in by_id.values():
        guide = entities.get(d.entity_id)
        if isinstance(guide, CoverGuide):
            pts = [view.project(p) for path, _ in d.paths for p in path]
            target = min(pts, key=lambda uv: (-uv[0], uv[1]))  # right side, lowest point
            out.append(Tag(f"Cover {_mm(guide.cover_mm)} mm", target))
    return out


# ---- layout and SVG -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PlacedTag:
    tag: Tag
    x: float  # text start, px
    y: float  # baseline, px
    knee: Vec2  # where the leader turns into the column, px
    target: Vec2  # px


def place_tags(notes: SectionNotes, to_px: ToPx, height: int) -> list[PlacedTag]:
    """Stack the tags in one column right of the concrete, in target order, a pitch apart,
    centred on their targets and kept inside the frame."""
    (_, _), (u1, _) = notes.box_mm
    right_px = to_px((u1, notes.box_mm[0][1]))[0]
    column = right_px + LEADER_RUN_PX
    targets = [to_px(tag.target) for tag in notes.tags]
    count = len(targets)
    if not count:
        return []
    ys = [t[1] + 3.5 for t in targets]
    for i in range(1, count):  # push down so baselines are a pitch apart
        ys[i] = max(ys[i], ys[i - 1] + TAG_LINE_PX)
    centre_shift = (sum(t[1] for t in targets) / count + 3.5) - (ys[0] + ys[-1]) / 2.0
    ys = [y + centre_shift for y in ys]
    top, bottom = FRAME_PAD_PX + TEXT_PX, height - FRAME_PAD_PX
    if ys[0] < top:
        ys = [y + top - ys[0] for y in ys]
    if ys[-1] > bottom:
        ys = [y - (ys[-1] - bottom) for y in ys]
    return [
        PlacedTag(tag, column + TEXT_INSET_PX, y, (column, y - 3.5), target)
        for tag, y, target in zip(notes.tags, ys, targets, strict=True)
    ]


def tag_box_px(placed: PlacedTag) -> tuple[float, float, float, float]:
    """Text box as x0, y0, x1, y1 (px), with the same width estimate the layout uses."""
    width = SectionNotes.tag_width_px(placed.tag)
    return placed.x, placed.y - TEXT_PX, placed.x + width, placed.y + 2.0


def notes_svg(
    notes: SectionNotes, to_px: ToPx, height: int, num: Callable[[float], str]
) -> list[str]:
    """Tags with leaders, then the overall dimensions, all in annotation blue."""
    out = [
        f'<g class="annotation" font-family="{WORKING_FONT}" fill="{BLUE}" stroke="{BLUE}" '
        f'stroke-width="{ANNOTATION_PEN_PX:g}">'
    ]
    for placed in place_tags(notes, to_px, height):
        tx, ty = placed.target
        kx, ky = placed.knee
        out.append(
            f'<g class="tag"><path d="M{num(tx)} {num(ty)} L{num(kx - 6.0)} {num(ky)} '
            f'L{num(kx)} {num(ky)}" fill="none"/><circle cx="{num(tx)}" cy="{num(ty)}" r="1" '
            f'stroke="none"/><text x="{num(placed.x)}" y="{num(placed.y)}" stroke="none" '
            f'font-size="{TEXT_PX:g}">{escape(placed.tag.text)}</text></g>'
        )
    out.extend(_dimensions(notes, to_px, num))
    out.append("</g>")
    return out


def _dimensions(notes: SectionNotes, to_px: ToPx, num: Callable[[float], str]) -> list[str]:
    (u0, v0), (u1, v1) = notes.box_mm
    x0, y1 = to_px((u0, v0))  # bottom left
    x1, y0 = to_px((u1, v1))  # top right
    out: list[str] = []
    # Horizontal: overall width, below the concrete.
    dy = y1 + DIM_OFFSET_PX
    out.append(
        f'<g class="dimension" data-dim="width"><path d="M{num(x0)} {num(y1 + EXT_GAP_PX)} '
        f'L{num(x0)} {num(dy + EXT_OVER_PX)} M{num(x1)} {num(y1 + EXT_GAP_PX)} '
        f'L{num(x1)} {num(dy + EXT_OVER_PX)} M{num(x0)} {num(dy)} L{num(x1)} {num(dy)}" '
        f'fill="none"/>{_arrow(x0, dy, 0.0, num)}{_arrow(x1, dy, 180.0, num)}'
        f'<text x="{num((x0 + x1) / 2.0)}" y="{num(dy - 3.0)}" text-anchor="middle" '
        f'stroke="none" font-size="{DIM_TEXT_PX:g}">{_dim(u1 - u0)}</text></g>'
    )
    # Vertical: overall depth, left of the concrete.
    dx = x0 - DIM_OFFSET_PX
    mid = (y0 + y1) / 2.0
    out.append(
        f'<g class="dimension" data-dim="depth"><path d="M{num(x0 - EXT_GAP_PX)} {num(y0)} '
        f'L{num(dx - EXT_OVER_PX)} {num(y0)} M{num(x0 - EXT_GAP_PX)} {num(y1)} '
        f'L{num(dx - EXT_OVER_PX)} {num(y1)} M{num(dx)} {num(y0)} L{num(dx)} {num(y1)}" '
        f'fill="none"/>{_arrow(dx, y0, 90.0, num)}{_arrow(dx, y1, -90.0, num)}'
        f'<text transform="translate({num(dx - 3.0)} {num(mid)}) rotate(-90)" '
        f'text-anchor="middle" stroke="none" font-size="{DIM_TEXT_PX:g}">'
        f'{_dim(v1 - v0)}</text></g>'
    )
    return out


def _arrow(x: float, y: float, angle_deg: float, num: Callable[[float], str]) -> str:
    """A filled 30-degree arrowhead with its tip at (x, y), pointing along `angle_deg`
    reversed: the head sits inside the dimension line."""
    half = ARROW_PX * math.tan(math.radians(15.0))
    return (
        f'<path d="M0 0 L{num(ARROW_PX)} {num(-half)} L{num(ARROW_PX)} {num(half)} Z" '
        f'stroke="none" transform="translate({num(x)} {num(y)}) rotate({num(angle_deg)})"/>'
    )


def scale_note(scale_px_per_mm: float) -> str:
    """`SCALE 1:n`: the drawing scale the pen and type mapping implies (5 px per paper mm)."""
    return f"SCALE 1:{PX_PER_PAPER_MM / scale_px_per_mm:.0f}"
