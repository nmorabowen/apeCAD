"""Section annotation for the SVG render (ADR 0031 §3.5, spec ape-design §4 D4).

Derived at render time from the document, never stored: no op, no log entry, no change to
the section-draft export. In a plan (top) view of a section it draws, at a standard
drafting scale, tags with leaders beside the group they label (each hoop with the bars and
crossties inside it; the web bars; the whole-section notes), the overall dimensions, and a
scale note under the view title. Text and arrowheads have a fixed paper size (ADR-007:
2.0 mm notes, ADR-006: 2.5 mm dimensions) at 5 px per paper mm. Tags keep the office
structure in English and millimetres: `18 Φ16`, `Tie Φ10 @ 100 mm`. The document spells
designations `Ø`; the drawing prints `Φ` (spec §3.4), here and nowhere else. A hoop's label
heads its tie tag (`BE1: Tie Φ10 @ 100 mm`) and the face's is in the title, so neither is
drawn again as an entity label (`SectionNotes.named`; `render/labels.py` places the rest).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from apeCAD.render.annotate_tags import (
    TAG_CHAR_PX,
    Group,
    SectionNotes,
    Tag,
    Vec2,
    _along,
    _bar_tags,
    _box_centre,
    _centre,
    _inside,
    _merged,
    _mid,
    _mm,
    _section_tags,
    _tie_tags,
    phi,
    section_notes,
)
from apeCAD.render.style import ANNOTATION_PEN_PX, BLUE, PX_PER_PAPER_MM, TEXT_PX, WORKING_FONT

Box = tuple[float, float, float, float]  # x0, y0, x1, y1 in px
Side = Literal["top", "bottom", "left", "right"]
ToPx = Callable[[Vec2], Vec2]
Num = Callable[[float], str]

# Office scale ladder (apeRevit library/graphics-tokens.json `scale_ladder`: details 1:5-15,
# member sections 1:15-25, armados 1:50, plans 1:75, elevations 1:100), continued with the
# ISO 5455 reductions for larger frames.
STANDARD_SCALES = (5, 10, 15, 20, 25, 50, 75, 100, 200, 250, 500, 1000, 2000, 5000)

DIM_TEXT_PX = PX_PER_PAPER_MM * 2.5  # ADR-006 default linear dimension, 2.5 mm
TAG_PITCH_PX = 14.0  # line pitch inside a stack
STACK_GAP_PX = 14.0  # between stacks on one side
LEADER_RUN_PX = 22.0  # from the concrete (or its dimension) to a stack
DIM_OFFSET_PX = 24.0  # dimension line off the concrete
DIM_BAND_PX = DIM_OFFSET_PX + DIM_TEXT_PX + 6.0
EXT_GAP_PX = 3.0
EXT_OVER_PX = 4.0
ARROW_PX = 8.0  # filled 30-degree arrowhead (ADR-006 "Arrow Filled 30"), 1.6 mm
FRAME_PAD_PX = 10.0
LEGEND_PX = 56.0  # title, rule, scale note and scale bar, bottom left
OPPOSITE: dict[Side, Side] = {"top": "bottom", "bottom": "top", "left": "right", "right": "left"}


def _dim(value: float) -> str:
    """Dimensions read in whole millimetres, like every APE drawing."""
    return f"{round(value):d}"


# ---- where to put it --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PlacedTag:
    tag: Tag
    x: float  # text anchor, px
    y: float  # baseline, px
    end: bool  # text-anchor end (stacks on the left)
    knee: Vec2  # px
    target: Vec2  # px
    via: Vec2 | None = None  # px: above/below stacks run down their edge first, clear of text

    def box(self) -> Box:
        width = self.tag.width_px()
        x0 = self.x - width if self.end else self.x
        return x0, self.y - TEXT_PX, x0 + width, self.y + 2.0


@dataclass(frozen=True, slots=True)
class Layout:
    """An annotated drawing: its standard scale, where the concrete sits, and the tags."""

    notes: SectionNotes
    scale_n: int  # drawing scale 1:n
    scale_px_per_mm: float
    centre_mm: Vec2  # view-plane point at the image centre
    placed: tuple[PlacedTag, ...]


def plan_layout(
    notes: SectionNotes, bounds: tuple[Vec2, Vec2], width: int, height: int, margin: float
) -> Layout | None:
    """The largest standard scale at which the drawing, its dimensions and every tag stack
    fit the frame without overlapping; None when none does."""
    (u0, v0), (u1, v1) = bounds
    pad_mm = margin * max(u1 - u0, v1 - v0)
    for n in STANDARD_SCALES:
        scale = PX_PER_PAPER_MM / n
        if (u1 - u0 + 2 * pad_mm) * scale > width or (v1 - v0 + 2 * pad_mm) * scale > height:
            continue
        layout = _layout_at(notes, (u0, v0, u1, v1), width, height, scale, pad_mm * scale, n)
        if layout is not None:
            return layout
    return None


def _layout_at(
    notes: SectionNotes, bounds: Box, width: int, height: int, scale: float, pad_px: float,
    n: int,
) -> Layout | None:
    (cu0, cv0), (cu1, cv1) = notes.box_mm
    horizontal = (cu1 - cu0) >= (cv1 - cv0)
    sides: dict[Side, list[Group]] = {"top": [], "bottom": [], "left": [], "right": []}
    for group in notes.groups:
        sides[_side(group.anchor, notes.box_mm, horizontal)].append(group)
    for _ in range(len(notes.groups) + 1):
        result = _try(notes, sides, bounds, width, height, scale, pad_px)
        if isinstance(result, tuple):
            return Layout(notes, n, scale, result[0], result[1])
        if result is None or not _move_one(sides, result, horizontal):
            return None
    return None


def _side(anchor: Vec2, box: tuple[Vec2, Vec2], horizontal: bool) -> Side:
    (u0, v0), (u1, v1) = box
    if horizontal:
        return "top" if anchor[1] >= (v0 + v1) / 2.0 else "bottom"
    return "right" if anchor[0] >= (u0 + u1) / 2.0 else "left"


def _move_one(sides: dict[Side, list[Group]], full: Side, horizontal: bool) -> bool:
    """Spill one stack from an overflowing side to the opposite one."""
    other = OPPOSITE[full]
    if not sides[full] or (len(sides[full]) == 1 and sides[other]):
        return False
    group = max(sides[full], key=lambda g: g.anchor[0] if horizontal else -g.anchor[1])
    sides[full].remove(group)
    sides[other].append(group)
    return True


def _stack_w(group: Group) -> float:
    return max(tag.width_px() for tag in group.tags) + 8.0


def _stack_h(group: Group) -> float:
    return len(group.tags) * TAG_PITCH_PX


def _try(
    notes: SectionNotes, sides: dict[Side, list[Group]], bounds: Box, width: int, height: int,
    scale: float, pad_px: float,
) -> tuple[Vec2, tuple[PlacedTag, ...]] | Side | None:
    """Place the drawing and every stack: (centre, tags), the Side that overflowed, or None
    when the frame is too small whatever the sides."""
    bu0, bv0, bu1, bv1 = bounds
    gw, gh = (bu1 - bu0) * scale, (bv1 - bv0) * scale
    extent = {s: max((_stack_h(g) if s in ("top", "bottom") else _stack_w(g)) for g in gs)
              if gs else 0.0 for s, gs in sides.items()}
    band = {s: extent[s] + LEADER_RUN_PX if extent[s] else 0.0 for s in extent}
    need_top = pad_px + band["top"]
    need_bottom = pad_px + DIM_BAND_PX + band["bottom"] + LEGEND_PX
    need_left = pad_px + DIM_BAND_PX + band["left"]
    need_right = pad_px + band["right"]
    room_w = width - 2 * FRAME_PAD_PX - need_left - need_right - gw
    room_h = height - 2 * FRAME_PAD_PX - need_top - need_bottom - gh
    if room_w < 0.0 or room_h < 0.0:
        culprits: list[tuple[float, Side]] = []
        if room_w < 0.0:
            culprits.append((-room_w, "left" if band["left"] >= band["right"] else "right"))
        if room_h < 0.0:
            culprits.append((-room_h, "top" if band["top"] >= band["bottom"] else "bottom"))
        side = max(culprits)[1]
        return side if band[side] else None
    x0 = FRAME_PAD_PX + need_left + room_w / 2.0
    y0 = FRAME_PAD_PX + need_top + room_h / 2.0
    centre = (bu0 + (width / 2.0 - x0) / scale, bv1 + (y0 - height / 2.0) / scale)

    def to_px(uv: Vec2) -> Vec2:
        return (width / 2.0 + (uv[0] - centre[0]) * scale,
                height / 2.0 - (uv[1] - centre[1]) * scale)

    (cu0, cv0), (cu1, cv1) = notes.box_mm
    box = (*to_px((cu0, cv1)), *to_px((cu1, cv0)))
    placed: list[PlacedTag] = []
    for side in ("top", "bottom", "left", "right"):
        stacks = _spread(side, sides[side], to_px, box, width, height)
        if stacks is None:
            return side
        placed.extend(stacks)
    return centre, tuple(placed)


def _spread(
    side: Side, groups: list[Group], to_px: ToPx, box: Box, width: int, height: int
) -> list[PlacedTag] | None:
    """Stacks along one side, each centred on its group and pushed apart; None if they do
    not fit the side."""
    if not groups:
        return []
    along_x = side in ("top", "bottom")
    axis = 0 if along_x else 1
    size = _stack_w if along_x else _stack_h
    order = sorted(groups, key=lambda g: to_px(g.anchor)[axis])
    lo = FRAME_PAD_PX
    hi = (width if along_x else height) - FRAME_PAD_PX - (LEGEND_PX if side == "left" else 0.0)
    starts: list[float] = []
    for g in order:
        start = max(lo, to_px(g.anchor)[axis] - size(g) / 2.0)
        if starts:
            start = max(start, starts[-1] + size(order[len(starts) - 1]) + STACK_GAP_PX)
        starts.append(start)
    overflow = starts[-1] + size(order[-1]) - hi
    if overflow > 0.0:
        starts = [s - overflow for s in starts]
        if starts[0] < lo:
            return None
    out: list[PlacedTag] = []
    for g, start in zip(order, starts, strict=True):
        out.extend(_stack(side, g, start, to_px, box))
    return out


def _stack(side: Side, group: Group, start: float, to_px: ToPx, box: Box) -> list[PlacedTag]:
    cx0, cy0, cx1, cy1 = box
    count = len(group.tags)
    out: list[PlacedTag] = []
    for i, tag in enumerate(group.tags):
        via: Vec2 | None = None
        if side in ("top", "bottom"):
            y = (cy0 - LEADER_RUN_PX - (count - 1 - i) * TAG_PITCH_PX if side == "top"
                 else cy1 + DIM_BAND_PX + LEADER_RUN_PX + TEXT_PX + i * TAG_PITCH_PX)
            x, end, knee = start + 8.0, False, (start + 2.0, y - 3.5)
            edge_y = (cy0 - LEADER_RUN_PX + 6.0 if side == "top"
                      else cy1 + DIM_BAND_PX + LEADER_RUN_PX - TEXT_PX + 2.0)
            via = (start + 2.0, edge_y)
        elif side == "right":
            y = start + TEXT_PX + i * TAG_PITCH_PX
            x, end, knee = cx1 + LEADER_RUN_PX + 6.0, False, (cx1 + LEADER_RUN_PX, y - 3.5)
        else:
            y = start + TEXT_PX + i * TAG_PITCH_PX
            edge = cx0 - DIM_BAND_PX - LEADER_RUN_PX
            x, end, knee = edge - 6.0, True, (edge, y - 3.5)
        targets = [to_px(t) for t in tag.targets]
        target = min(targets, key=lambda p: (p[0] - knee[0]) ** 2 + (p[1] - knee[1]) ** 2)
        out.append(PlacedTag(tag, x, y, end, knee, target, via))
    return out


# ---- SVG --------------------------------------------------------------------------------


def notes_svg(layout: Layout, to_px: ToPx, num: Num, clean: Callable[[str], str]) -> list[str]:
    """Tags with leaders, then the overall dimensions, all in annotation blue. `clean`
    escapes text content (a tie tag may carry a hoop's label)."""
    out = [
        f'<g class="annotation" font-family="{WORKING_FONT}" fill="{BLUE}" stroke="{BLUE}" '
        f'stroke-width="{ANNOTATION_PEN_PX:g}">'
    ]
    for p in layout.placed:
        tx, ty = p.target
        kx, ky = p.knee
        via = "" if p.via is None else f" L{num(p.via[0])} {num(p.via[1])}"
        anchor = ' text-anchor="end"' if p.end else ""
        out.append(
            f'<g class="tag"><path d="M{num(tx)} {num(ty)}{via} L{num(kx)} {num(ky)}" '
            'fill="none"/>'
            f'<circle cx="{num(tx)}" cy="{num(ty)}" r="1" stroke="none"/>'
            f'<text x="{num(p.x)}" y="{num(p.y)}" stroke="none" font-size="{TEXT_PX:g}"{anchor}>'
            f"{clean(p.tag.text)}</text></g>"
        )
    out.extend(_dimensions(layout.notes, to_px, num, leaders(layout)))
    out.append("</g>")
    return out


def leaders(layout: Layout) -> list[list[Vec2]]:
    """Each tag's leader as a px polyline: target, then its turn if any, then the knee."""
    return [[p.target, *([p.via] if p.via else []), p.knee] for p in layout.placed]


def dimension_text_boxes(
    notes: SectionNotes, to_px: ToPx, lines: list[list[Vec2]]
) -> list[Box]:
    """Where the two dimension texts go: the middle of their line, or the nearest quarter
    point no leader crosses."""
    (u0, v0), (u1, v1) = notes.box_mm
    x0, y1 = to_px((u0, v0))
    x1, y0 = to_px((u1, v1))
    dy, dx = y1 + DIM_OFFSET_PX, x0 - DIM_OFFSET_PX
    # Generous glyph width (0.62 em) and 3 px clearance, so a wider fallback face stays clear.
    w_text = len(_dim(u1 - u0)) * DIM_TEXT_PX * 0.62 + 6.0
    h_text = len(_dim(v1 - v0)) * DIM_TEXT_PX * 0.62 + 6.0
    width_box = _first_clear(
        [(x0 + (x1 - x0) * t - w_text / 2, dy - 6.0 - DIM_TEXT_PX,
          x0 + (x1 - x0) * t + w_text / 2, dy + 2.0) for t in _SLIDE], lines)
    depth_box = _first_clear(
        [(dx - 6.0 - DIM_TEXT_PX, y0 + (y1 - y0) * t - h_text / 2, dx + 2.0,
          y0 + (y1 - y0) * t + h_text / 2) for t in _SLIDE], lines)
    return [width_box, depth_box]


_SLIDE = (0.5, 0.25, 0.75, 0.15, 0.85)


def _first_clear(boxes: list[Box], lines: list[list[Vec2]]) -> Box:
    segments = [(a, b) for line in lines for a, b in zip(line, line[1:], strict=False)]
    for box in boxes:
        if not any(crosses(box, a, b) for a, b in segments):
            return box
    return boxes[0]


def crosses(box: Box, a: Vec2, b: Vec2) -> bool:
    """Does segment a-b touch the box? Clipped against it (Liang-Barsky)."""
    x0, y0, x1, y1 = box
    t0, t1 = 0.0, 1.0
    dx, dy = b[0] - a[0], b[1] - a[1]
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if p == 0.0:
            if q < 0.0:
                return False
            continue
        r = q / p
        if p < 0.0:
            t0 = max(t0, r)
        else:
            t1 = min(t1, r)
        if t0 > t1:
            return False
    return True


def dimension_lines(notes: SectionNotes, to_px: ToPx) -> list[list[Vec2]]:
    """The two dimension lines and their extension lines, as px polylines."""
    (u0, v0), (u1, v1) = notes.box_mm
    x0, y1 = to_px((u0, v0))
    x1, y0 = to_px((u1, v1))
    dy, dx = y1 + DIM_OFFSET_PX, x0 - DIM_OFFSET_PX
    return [
        [(x0, y1 + EXT_GAP_PX), (x0, dy + EXT_OVER_PX)],
        [(x1, y1 + EXT_GAP_PX), (x1, dy + EXT_OVER_PX)],
        [(x0, dy), (x1, dy)],
        [(x0 - EXT_GAP_PX, y0), (dx - EXT_OVER_PX, y0)],
        [(x0 - EXT_GAP_PX, y1), (dx - EXT_OVER_PX, y1)],
        [(dx, y0), (dx, y1)],
    ]


def _dimensions(
    notes: SectionNotes, to_px: ToPx, num: Num, lines: list[list[Vec2]]
) -> list[str]:
    (u0, v0), (u1, v1) = notes.box_mm
    x0, y1 = to_px((u0, v0))  # bottom left
    x1, y0 = to_px((u1, v1))  # top right
    dy = y1 + DIM_OFFSET_PX
    dx = x0 - DIM_OFFSET_PX
    width_box, depth_box = dimension_text_boxes(notes, to_px, lines)
    along = (width_box[0] + width_box[2]) / 2.0
    mid = (depth_box[1] + depth_box[3]) / 2.0
    return [
        f'<g class="dimension" data-dim="width"><path d="M{num(x0)} {num(y1 + EXT_GAP_PX)} '
        f'L{num(x0)} {num(dy + EXT_OVER_PX)} M{num(x1)} {num(y1 + EXT_GAP_PX)} '
        f'L{num(x1)} {num(dy + EXT_OVER_PX)} M{num(x0)} {num(dy)} L{num(x1)} {num(dy)}" '
        f'fill="none"/>{_arrow(x0, dy, 0.0, num)}{_arrow(x1, dy, 180.0, num)}'
        f'<text x="{num(along)}" y="{num(dy - 3.0)}" text-anchor="middle" '
        f'stroke="none" font-size="{DIM_TEXT_PX:g}">{_dim(u1 - u0)}</text></g>',
        f'<g class="dimension" data-dim="depth"><path d="M{num(x0 - EXT_GAP_PX)} {num(y0)} '
        f'L{num(dx - EXT_OVER_PX)} {num(y0)} M{num(x0 - EXT_GAP_PX)} {num(y1)} '
        f'L{num(dx - EXT_OVER_PX)} {num(y1)} M{num(dx)} {num(y0)} L{num(dx)} {num(y1)}" '
        f'fill="none"/>{_arrow(dx, y0, 90.0, num)}{_arrow(dx, y1, -90.0, num)}'
        f'<text transform="translate({num(dx - 3.0)} {num(mid)}) rotate(-90)" '
        f'text-anchor="middle" stroke="none" font-size="{DIM_TEXT_PX:g}">'
        f"{_dim(v1 - v0)}</text></g>",
    ]


def _arrow(x: float, y: float, angle_deg: float, num: Num) -> str:
    """A filled 30-degree arrowhead with its tip at (x, y), opening along `angle_deg`."""
    half = ARROW_PX * math.tan(math.radians(15.0))
    return (
        f'<path d="M0 0 L{num(ARROW_PX)} {num(-half)} L{num(ARROW_PX)} {num(half)} Z" '
        f'stroke="none" transform="translate({num(x)} {num(y)}) rotate({num(angle_deg)})"/>'
    )


def scale_note(n: int) -> str:
    return f"SCALE 1:{n}"


__all__ = [
    "ARROW_PX",
    "DIM_BAND_PX",
    "DIM_OFFSET_PX",
    "DIM_TEXT_PX",
    "EXT_GAP_PX",
    "EXT_OVER_PX",
    "FRAME_PAD_PX",
    "LEADER_RUN_PX",
    "LEGEND_PX",
    "OPPOSITE",
    "STACK_GAP_PX",
    "STANDARD_SCALES",
    "TAG_CHAR_PX",
    "TAG_PITCH_PX",
    "Box",
    "Group",
    "Layout",
    "Num",
    "PlacedTag",
    "SectionNotes",
    "Side",
    "Tag",
    "ToPx",
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
    "crosses",
    "dimension_lines",
    "dimension_text_boxes",
    "leaders",
    "notes_svg",
    "phi",
    "plan_layout",
    "scale_note",
    "section_notes",
]

