"""SVG text for projected drawables. Pure stdlib; same input, same bytes."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from xml.sax.saxutils import escape

from apeCAD.entities import EntityId
from apeCAD.render.scene import Drawable, Path3
from apeCAD.render.views import Vec2, View

BACKGROUND = "#ffffff"
INK = "#1f2933"
FACE_FILL = "#3b6ea5"
ACCENT = "#e8590c"
FONT = 'font-family="sans-serif" font-size="11"'


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
) -> str:
    w, h = viewport.width, viewport.height
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" data-view="{view.name}">',
        f'<rect width="{w}" height="{h}" fill="{BACKGROUND}"/>',
    ]
    faces = [d for d in items if d.layer == "face"]
    edges = [d for d in items if d.layer == "edge"]
    points = [d for d in items if d.layer == "point"]
    out.append(
        f'<g class="faces" fill="{FACE_FILL}" fill-opacity="0.15" stroke="none">'
    )
    out.extend(_group(d, view, viewport, "data-id", _plain_body) for d in faces)
    out.append("</g>")
    out.append(
        f'<g class="edges" fill="none" stroke="{INK}" stroke-width="1.5" '
        'stroke-linecap="round" stroke-linejoin="round">'
    )
    out.extend(_group(d, view, viewport, "data-id", _plain_body) for d in edges)
    out.append("</g>")
    out.append(f'<g class="points" fill="{INK}">')
    out.extend(_group(d, view, viewport, "data-id", _dot_body(1.5, INK)) for d in points)
    out.append("</g>")
    marked = [d for d in items if d.entity_id in highlight]
    if marked:
        out.append(
            f'<g class="highlight" stroke="{ACCENT}" stroke-width="2.5" '
            'stroke-linecap="round" stroke-linejoin="round">'
        )
        for d in marked:
            body = {"face": _accent_fill_body, "edge": _accent_stroke_body}.get(
                d.layer, _dot_body(2.5, ACCENT)
            )
            out.append(_group(d, view, viewport, "data-highlight", body))
        out.append("</g>")
    out.append(f'<g class="text" {FONT} fill="{INK}">')
    out.extend(_texts(items, view, viewport, text))
    if not items:
        out.append(
            f'<text x="{num(w / 2.0)}" y="{num(h / 2.0)}" text-anchor="middle" '
            'fill-opacity="0.5">empty draft</text>'
        )
    out.append("</g>")
    out.extend(_legend(view, viewport))
    out.append("</svg>")
    return "\n".join(out) + "\n"


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
        out.append(
            f'<text x="{num(x + 5.0)}" y="{num(y - 5.0)}" data-for="{d.entity_id}">'
            f"{clean_text(' '.join(parts))}</text>"
        )
    return out


def scale_bar_mm(viewport: Viewport) -> float:
    """Largest 1-2-5 length that spans at most a quarter of the image width."""
    limit = viewport.width * 0.25 / viewport.scale
    power = 10.0 ** math.floor(math.log10(limit))
    for step in (5.0, 2.0, 1.0):
        if step * power <= limit:
            return step * power
    return power / 2.0


def _legend(view: View, viewport: Viewport) -> list[str]:
    length = scale_bar_mm(viewport)
    x0 = 12.0
    y0 = viewport.height - 12.0
    x1 = x0 + length * viewport.scale
    return [
        f'<g class="legend" {FONT} fill="{INK}" stroke="{INK}" stroke-width="1">',
        f'<path d="M{num(x0)} {num(y0 - 4.0)} L{num(x0)} {num(y0)} L{num(x1)} {num(y0)} '
        f'L{num(x1)} {num(y0 - 4.0)}" fill="none"/>',
        f'<text x="{num(x1 + 6.0)}" y="{num(y0)}" stroke="none">{length:.10g} mm</text>',
        f'<text x="{num(x0)}" y="{num(y0 - 10.0)}" stroke="none">{view.name}</text>',
        "</g>",
    ]
