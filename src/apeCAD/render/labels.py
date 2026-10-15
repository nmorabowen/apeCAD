"""Entity labels on an annotated plan of a section (spec ape-design §4 D4).

A bare drawing puts each label up and right of its entity's anchor (`svg._text_place`).
On an annotated plan that spot is often taken by the section's own lines or by a tag, so
here each label tries spots around its anchor, nearest first, and takes the first whose
text box stays in the frame and clear of the tags, the leaders, the dimensions, the
legend, the labels already placed, and every drawn line and bar. Labels the notes already
print (`SectionNotes.named`: the face in the title, hoops at the head of their tie tag)
are not drawn again; `svg.py` leaves them out before calling here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from apeCAD.entities import EntityId
from apeCAD.render.annotate import (
    Box,
    Layout,
    Vec2,
    crosses,
    dimension_lines,
    dimension_text_boxes,
    leaders,
)
from apeCAD.render.drawable import Drawable
from apeCAD.render.style import MIN_BAR_RADIUS_PX, TEXT_PX
from apeCAD.render.views import View

CHAR_PX = 6.6  # generous for Arial Narrow at 10 px, to keep labels inside the frame
TEXT_GAP_PX = 5.0
STEP_PX = 7.0  # each further ring of spots is this much farther from the anchor
RINGS = 8
CLEAR_PX = 2.0  # air between a label and what it clears; outline strokes are 1.5 px wide
ToPx = Callable[[Vec2], Vec2]


@dataclass(frozen=True, slots=True)
class LabelText:
    entity_id: EntityId
    words: str
    anchor: Vec2  # px


@dataclass(frozen=True, slots=True)
class PlacedLabel:
    entity_id: EntityId
    words: str
    x: float  # text anchor, px
    y: float  # baseline, px
    end: bool  # text-anchor end

    def box(self) -> Box:
        return text_box(self.x, self.y, self.end, len(self.words))


def text_box(x: float, y: float, end: bool, chars: int) -> Box:
    width = chars * CHAR_PX
    x0 = x - width if end else x
    return x0, y - TEXT_PX, x0 + width, y + 2.0


@dataclass(frozen=True, slots=True)
class Obstacles:
    """What a label must clear, in px. `geometry` (the reinforcement drawn inside the
    concrete) gives way first when a label has no other spot; `lines` never do."""

    boxes: list[Box]
    lines: list[tuple[Vec2, Vec2]]
    geometry_boxes: list[Box]
    geometry_lines: list[tuple[Vec2, Vec2]]


def obstacles(
    layout: Layout, view: View, to_px: ToPx, items: list[Drawable], legend: Box
) -> Obstacles:
    notes = layout.notes
    lines = leaders(layout)
    boxes = [p.box() for p in layout.placed]
    boxes += dimension_text_boxes(notes, to_px, lines)
    boxes.append(legend)
    segs = _segments([*lines, *dimension_lines(notes, to_px)])
    geometry_boxes: list[Box] = []
    geometry_lines: list[tuple[Vec2, Vec2]] = []
    for d in items:
        for path, closed in d.paths:
            pts = [to_px(view.project(p)) for p in path]
            if d.layer == "bar":
                r = max(d.radius_mm * layout.scale_px_per_mm, MIN_BAR_RADIUS_PX)
                geometry_boxes.extend((x - r, y - r, x + r, y + r) for x, y in pts)
                continue
            ring = _segments([pts + pts[:1] if closed else pts])
            (segs if d.layer == "concrete" else geometry_lines).extend(ring)
    return Obstacles(boxes, segs, geometry_boxes, geometry_lines)


def _segments(lines: list[list[Vec2]]) -> list[tuple[Vec2, Vec2]]:
    return [(a, b) for line in lines for a, b in zip(line, line[1:], strict=False)]


def place_labels(
    texts: list[LabelText], blocked: Obstacles, width: int, height: int
) -> list[PlacedLabel]:
    """Each label at its first clear spot: clear of everything, else clear of all but the
    reinforcement lines, else (nothing clears) the bare drawing's spot."""
    placed: list[PlacedLabel] = []
    for text in texts:
        spots = _spots(text, width, height)
        taken = [p.box() for p in placed]
        strict = (blocked.boxes + blocked.geometry_boxes + taken,
                  blocked.lines + blocked.geometry_lines)
        loose = (blocked.boxes + taken, blocked.lines)
        choice = next(
            (s for boxes, lines in (strict, loose) for s in spots
             if _clear(s.box(), boxes, lines)),
            spots[0],
        )
        placed.append(choice)
    return placed


def _spots(text: LabelText, width: int, height: int) -> list[PlacedLabel]:
    """Up-right, up-left, down-right, down-left of the anchor, ring by ring outward; the
    first is the bare drawing's spot. Spots that leave the frame are skipped."""
    ax, ay = text.anchor
    out: list[PlacedLabel] = []
    for ring in range(RINGS):
        d = TEXT_GAP_PX + ring * STEP_PX
        for dx, dy in ((1, -1), (-1, -1), (1, 1), (-1, 1)):
            y = ay - d if dy < 0 else ay + d + TEXT_PX
            out.append(PlacedLabel(text.entity_id, text.words, ax + dx * d, y, dx < 0))
    inside = [s for s in out if _in_frame(s.box(), width, height)]
    return inside or [out[0]]


def _in_frame(box: Box, width: int, height: int) -> bool:
    return box[0] >= TEXT_GAP_PX and box[1] >= 0.0 and box[2] <= width - TEXT_GAP_PX \
        and box[3] <= height


def _clear(box: Box, boxes: list[Box], lines: list[tuple[Vec2, Vec2]]) -> bool:
    box = (box[0] - CLEAR_PX, box[1] - CLEAR_PX, box[2] + CLEAR_PX, box[3] + CLEAR_PX)
    if any(box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3] for b in boxes):
        return False
    return not any(crosses(box, a, b) for a, b in lines)
