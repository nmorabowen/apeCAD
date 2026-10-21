"""SVG text for projected drawables. Pure stdlib; same input, same bytes."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from xml.sax.saxutils import escape

from apeCAD.entities import EntityId
from apeCAD.render.annotate import Layout, notes_svg, scale_note
from apeCAD.render.drawable import SECTION_LAYERS, Drawable, Path3
from apeCAD.render.labels import CHAR_PX, TEXT_GAP_PX, LabelText, obstacles, place_labels
from apeCAD.render.style import (
    ANNOTATION_PEN_PX,
    BACKGROUND,
    BLUE,
    DISPLAY_FONT,
    EMPTY_TEXT,
    HIGHLIGHT,
    MIN_BAR_RADIUS_PX,
    POINT_RADIUS_PX,
    SECTION_STYLE,
    SECTION_TITLE,
    SKETCH_STYLE,
    TEXT_PX,
    TITLE_PX,
    TITLE_RULE_PX,
    VIEW_TITLES,
    WORKING_FONT,
)
from apeCAD.render.views import Vec2, View

ACCENT = HIGHLIGHT
FONT = f'font-family="{WORKING_FONT}" font-size="{TEXT_PX:g}"'
FONT_PX = TEXT_PX


@dataclass(frozen=True, slots=True)
class Viewport:
    """Pixel frame: `center` (view-plane mm) sits at the image centre, `scale` px per mm."""

    width: int
    height: int
    scale: float
    center: Vec2

    def to_px(self, uv: Vec2) -> Vec2:
        return (
            self.width / 2.0 + (uv[0] - self.center[0]) * self.scale,
            self.height / 2.0 - (uv[1] - self.center[1]) * self.scale,
        )

    def extents_mm(self) -> tuple[Vec2, Vec2]:
        half_u = self.width / 2.0 / self.scale
        half_v = self.height / 2.0 / self.scale
        cu, cv = self.center
        return (cu - half_u, cv - half_v), (cu + half_u, cv + half_v)


@dataclass(frozen=True, slots=True)
class TextOptions:
    labels: bool
    show_ids: bool


_BodyFn = Callable[[Drawable, View, Viewport], str]


def num(value: float) -> str:
    """Two decimals, trailing zeros dropped, never "-0"."""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def clean_text(text: str) -> str:
    """Escape for XML text content and drop characters XML 1.0 cannot carry."""
    kept = "".join(
        ch
        for ch in text
        if ch in "\t\n\r" or (0x20 <= ord(ch) < 0xD800) or (0xE000 <= ord(ch) <= 0xFFFD)
        or ord(ch) >= 0x10000
    )
    return escape(kept, {'"': "&quot;", "'": "&apos;"})


def write_svg(
    view: View,
    viewport: Viewport,
    items: list[Drawable],
    highlight: set[EntityId],
    text: TextOptions,
    layout: Layout | None = None,
) -> str:
    w, h = viewport.width, viewport.height
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" data-view="{view.name}">',
        f'<rect width="{w}" height="{h}" fill="{BACKGROUND}"/>',
    ]
    faces = [d for d in items if d.layer == "face"]
    solids = [d for d in items if d.layer == "solid"]
    edges = [d for d in items if d.layer == "edge"]
    points = [d for d in items if d.layer == "point"]
    out.append(f'<g class="faces" {SKETCH_STYLE["face"].attrs()}>')
    out.extend(_group(d, view, viewport, "data-id", _plain_body) for d in faces)
    out.append("</g>")
    out.extend(_section_layers(items, view, viewport))
    if solids:
        out.append(f'<g class="solids" {SKETCH_STYLE["solid"].attrs()}>')
        out.extend(_group(d, view, viewport, "data-id", _plain_body) for d in solids)
        out.append("</g>")
    out.append(f'<g class="edges" {SKETCH_STYLE["edge"].attrs()}>')
    out.extend(_group(d, view, viewport, "data-id", _plain_body) for d in edges)
    out.append("</g>")
    point_ink = SKETCH_STYLE["point"].fill
    out.append(f'<g class="points" fill="{point_ink}">')
    out.extend(
        _group(d, view, viewport, "data-id", _dot_body(POINT_RADIUS_PX, point_ink)) for d in points
    )
    out.append("</g>")
    if layout is not None:
        out.extend(notes_svg(layout, viewport.to_px, num, clean_text))
    marked = [d for d in items if d.entity_id in highlight]
    if marked:
        out.append(
            f'<g class="highlight" stroke="{ACCENT}" stroke-width="2.5" '
            'stroke-linecap="round" stroke-linejoin="round">'
        )
        for d in marked:
            body = _HIGHLIGHT_BODIES.get(d.layer, _dot_body(2.5, ACCENT))
            out.append(_group(d, view, viewport, "data-highlight", body))
        out.append("</g>")
    out.append(f'<g class="text" {FONT} fill="{BLUE}">')
    title = view_title(view, items)
    if layout is None:
        out.extend(_texts(items, view, viewport, text))
    else:
        out.extend(_placed_texts(items, view, viewport, text, layout, title))
    if not items:
        out.append(
            f'<text x="{num(w / 2.0)}" y="{num(h / 2.0)}" text-anchor="middle" '
            f'fill-opacity="0.5">{EMPTY_TEXT}</text>'
        )
    out.append("</g>")
    out.extend(_legend(view, viewport, title, layout))
    out.append("</svg>")
    return "\n".join(out) + "\n"


def _section_layers(items: list[Drawable], view: View, viewport: Viewport) -> list[str]:
    """One group per section layer that has anything in it, back to front."""
    out: list[str] = []
    for layer in SECTION_LAYERS:
        members = [d for d in items if d.layer == layer]
        if not members:
            continue
        body = _disc_body(None) if layer == "bar" else _plain_body
        out.append(f'<g class="{layer}" {SECTION_STYLE[layer].attrs()}>')
        out.extend(_group(d, view, viewport, "data-id", body) for d in members)
        out.append("</g>")
    return out


def _group(d: Drawable, view: View, viewport: Viewport, attr: str, body: _BodyFn) -> str:
    return f'<g {attr}="{d.entity_id}">{body(d, view, viewport)}</g>'


def _path_data(path: Path3, view: View, viewport: Viewport) -> str:
    points, closed = path
    coords = [viewport.to_px(view.project(p)) for p in points]
    parts = [f"{'M' if i == 0 else 'L'}{num(x)} {num(y)}" for i, (x, y) in enumerate(coords)]
    return " ".join(parts) + (" Z" if closed else "")


def _paths(d: Drawable, view: View, viewport: Viewport) -> Iterable[str]:
    return (_path_data(path, view, viewport) for path in d.paths if len(path[0]) > 1)


def _plain_body(d: Drawable, view: View, viewport: Viewport) -> str:
    return "".join(f'<path d="{data}"/>' for data in _paths(d, view, viewport))


def _accent_fill_body(d: Drawable, view: View, viewport: Viewport) -> str:
    return "".join(
        f'<path d="{data}" fill="{ACCENT}" fill-opacity="0.35"/>'
        for data in _paths(d, view, viewport)
    )


def _accent_stroke_body(d: Drawable, view: View, viewport: Viewport) -> str:
    return "".join(f'<path d="{data}" fill="none"/>' for data in _paths(d, view, viewport))


def _disc_body(color: str | None) -> _BodyFn:
    """A bar at its true diameter, never smaller than MIN_BAR_RADIUS_PX."""

    def body(d: Drawable, view: View, viewport: Viewport) -> str:
        radius = max(d.radius_mm * viewport.scale, MIN_BAR_RADIUS_PX)
        paint = "" if color is None else f' fill="{color}" stroke="none"'
        dots: list[str] = []
        for points, _closed in d.paths:
            for p in points:
                x, y = viewport.to_px(view.project(p))
                dots.append(f'<circle cx="{num(x)}" cy="{num(y)}" r="{num(radius)}"{paint}/>')
        return "".join(dots)

    return body


def _dot_body(radius: float, color: str) -> _BodyFn:
    def body(d: Drawable, view: View, viewport: Viewport) -> str:
        dots: list[str] = []
        for points, _closed in d.paths:
            for p in points:
                x, y = viewport.to_px(view.project(p))
                dots.append(
                    f'<circle cx="{num(x)}" cy="{num(y)}" r="{num(radius)}" '
                    f'fill="{color}" stroke="none"/>'
                )
        return "".join(dots)

    return body


_HIGHLIGHT_BODIES: dict[str, _BodyFn] = {
    "face": _accent_fill_body,
    "concrete": _accent_fill_body,
    "solid": _accent_stroke_body,
    "edge": _accent_stroke_body,
    "cover": _accent_stroke_body,
    "leg": _accent_stroke_body,
    "hoop": _accent_stroke_body,
    "crosstie": _accent_stroke_body,
    "bar": _disc_body(ACCENT),
}


def _texts(items: list[Drawable], view: View, viewport: Viewport, text: TextOptions) -> list[str]:
    out: list[str] = []
    for d in items:
        if d.anchor is None:
            continue
        parts: list[str] = []
        if text.labels and d.label:
            parts.append(d.label)
        if text.show_ids:
            parts.append(f"#{d.entity_id}")
        if not parts:
            continue
        x, y = viewport.to_px(view.project(d.anchor))
        words = " ".join(parts)
        out.append(
            f'<text {_text_place(x, y, len(words), viewport)} data-for="{d.entity_id}">'
            f"{clean_text(words)}</text>"
        )
    return out


def _placed_texts(
    items: list[Drawable], view: View, viewport: Viewport, text: TextOptions, layout: Layout,
    title: str,
) -> list[str]:
    """An annotated plan: labels the notes already print are left out, the rest placed
    clear of the annotation and the drawing (`render/labels.py`)."""
    wanted: list[LabelText] = []
    for d in items:
        if d.anchor is None:
            continue
        parts: list[str] = []
        if text.labels and d.label and d.entity_id not in layout.notes.named:
            parts.append(d.label)
        if text.show_ids:
            parts.append(f"#{d.entity_id}")
        if parts:
            anchor = viewport.to_px(view.project(d.anchor))
            wanted.append(LabelText(d.entity_id, " ".join(parts), anchor))
    if not wanted:
        return []
    blocked = obstacles(layout, view, viewport.to_px, items, legend_box(viewport, title))
    out: list[str] = []
    for p in place_labels(wanted, blocked, viewport.width, viewport.height):
        anchor = ' text-anchor="end"' if p.end else ""
        out.append(
            f'<text x="{num(p.x)}" y="{num(p.y)}"{anchor} data-for="{p.entity_id}">'
            f"{clean_text(p.words)}</text>"
        )
    return out


def _text_place(x: float, y: float, chars: int, viewport: Viewport) -> str:
    """Up and right of the anchor, flipped left or down where it would leave the frame."""
    ty = y - TEXT_GAP_PX if y - TEXT_GAP_PX >= FONT_PX else y + TEXT_GAP_PX + FONT_PX
    if x + TEXT_GAP_PX + chars * CHAR_PX <= viewport.width - TEXT_GAP_PX:
        return f'x="{num(x + TEXT_GAP_PX)}" y="{num(ty)}"'
    return f'x="{num(x - TEXT_GAP_PX)}" y="{num(ty)}" text-anchor="end"'


def scale_bar_mm(viewport: Viewport) -> float:
    """Largest 1-2-5 length that spans at most a quarter of the image width."""
    limit = viewport.width * 0.25 / viewport.scale
    power = 10.0 ** math.floor(math.log10(limit))
    for step in (5.0, 2.0, 1.0):
        if step * power <= limit:
            return step * power
    return power / 2.0


def view_title(view: View, items: list[Drawable]) -> str:
    """English view title (spec §3.3); a plan of a section is SECTION plus the face label."""
    concrete = [d for d in items if d.layer == "concrete"]
    if view.name == "top" and concrete:
        label = concrete[0].label
        return f"{SECTION_TITLE} {label}" if label else SECTION_TITLE
    return VIEW_TITLES.get(view.name, view.name.upper())


def legend_box(viewport: Viewport, title: str) -> tuple[float, float, float, float]:
    """What an annotated plan's legend covers, px: title, rule, scale note and scale bar."""
    x1 = 12.0 + scale_bar_mm(viewport) * viewport.scale
    right = max(12.0 + 0.55 * TITLE_PX * len(title), x1 + 6.0 + 8 * CHAR_PX)
    return 0.0, viewport.height - 40.0 - TITLE_PX, right, float(viewport.height)


def legend_geometry(
    height: float, title: str, annotated: bool
) -> tuple[float, float, float, float, float, float]:
    """The legend's px positions, bottom left: x0, the scale bar's y, the title baseline,
    its rule's y and right end, and the scale note's baseline. The DXF writer reuses it."""
    x0 = 12.0
    y0 = height - 12.0
    # Annotated sections add a scale note between the title's rule and the scale bar.
    title_y = y0 - (28.0 if annotated else 14.0)  # clear of the scale bar's ticks and label
    rule_y = title_y + 3.0
    rule_x1 = x0 + 0.55 * TITLE_PX * len(title)  # under the title only
    return x0, y0, title_y, rule_y, rule_x1, rule_y + 12.0


def _legend(view: View, viewport: Viewport, title: str, layout: Layout | None) -> list[str]:
    """Scale bar (0.10 mm pen, working font) under the view title (display font, 3.5 mm,
    0.30 mm rule), bottom left, all in annotation blue (ADR-004, ADR-007, ADR-009)."""
    length = scale_bar_mm(viewport)
    x0, y0, title_y, rule_y, rule_x1, note_y = legend_geometry(
        viewport.height, title, layout is not None
    )
    x1 = x0 + length * viewport.scale
    note = (
        [f'<text class="scale-note" x="{num(x0)}" y="{num(note_y)}" stroke="none">'
         f"{scale_note(layout.scale_n)}</text>"]
        if layout
        else []
    )
    return [
        f'<g class="legend" {FONT} fill="{BLUE}" stroke="{BLUE}" '
        f'stroke-width="{ANNOTATION_PEN_PX:g}">',
        f'<path d="M{num(x0)} {num(y0 - 4.0)} L{num(x0)} {num(y0)} L{num(x1)} {num(y0)} '
        f'L{num(x1)} {num(y0 - 4.0)}" fill="none"/>',
        f'<text x="{num(x1 + 6.0)}" y="{num(y0)}" stroke="none">{length:.10g} mm</text>',
        f'<text class="view-title" x="{num(x0)}" y="{num(title_y)}" stroke="none" '
        f'font-family="{DISPLAY_FONT}" font-size="{TITLE_PX:g}" font-weight="600" '
        f'data-view="{view.name}">{clean_text(title)}</text>',
        f'<path class="view-title-rule" d="M{num(x0)} {num(rule_y)} L{num(rule_x1)} {num(rule_y)}" '
        f'fill="none" stroke-width="{TITLE_RULE_PX:g}"/>',
        *note,
        "</g>",
    ]
