"""The `apeCAD.section-overlay` v1 contract: validate it, colour it, draw it (ADR 0041).

`parse_overlay` is the one reader (spec `AProjects/specs/section-overlay.md`). It refuses
anything the contract does not allow, with the exact `path` of the refused field, and never
truncates. `overlay_svg` draws a parsed overlay as one SVG group for `render_svg`. An overlay
is display data a host computed: apeCAD stores none of it and computes nothing from it
(ADR 0024 decision 2).
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from apeCAD.errors import INVALID_ARGUMENT, TOO_LARGE
from apeCAD.render.style import BLUE
from apeCAD.render.svg import FONT, Viewport, clean_text, num
from apeCAD.render.views import Vec2, View

OVERLAY_SCHEMA = "apeCAD.section-overlay"
OVERLAY_SCHEMA_VERSION = 1
MAX_OVERLAY_PRIMITIVES = 200_000
"""Most primitives one overlay carries, over all layers (ADR 0041 decision 2)."""

# The ADR 0031 colour roles an overlay may name, at their light-theme value in
# `static/css/app.css` (`tests/test_render_overlay.py` keeps the two in step). The SVG is
# drawn on white, so the render resolves a token to its light value.
COLOR_TOKENS: dict[str, str] = {
    "--text": "#1c2127",
    "--muted": "#4a525c",
    "--accent": "#2f74ad",
    "--signal": "#c64a1a",
    "--ink-edge": "#14181d",
    "--ink-rebar": "#000077",
    "--ink-concrete": "#000000",
    "--ink-section-guide": "#808080",
    "--fill-concrete": "#b4b4b4",
}
SCALE_KINDS = ("sequential", "diverging", "categorical")
PRIMITIVE_KINDS = ("polygon", "circle", "polyline", "point", "label")
VALUE_STROKE_PX = 1.5  # a valued polyline's stroke
OVERLAY_POINT_RADIUS_PX = 2.5

# Which paint keys a `style` may set, per kind (spec "Paint").
_PAINTS: dict[str, frozenset[str]] = {
    "polygon": frozenset({"fill", "stroke"}),
    "circle": frozenset({"fill", "stroke"}),
    "polyline": frozenset({"stroke"}),
    "point": frozenset({"fill"}),
    "label": frozenset({"fill"}),
}
_SHAPE_KEYS: dict[str, frozenset[str]] = {
    "polygon": frozenset({"ring", "holes"}),
    "circle": frozenset({"center", "radius"}),
    "polyline": frozenset({"points"}),
    "point": frozenset({"at"}),
    "label": frozenset({"at", "text"}),
}
_REQUIRED_SHAPE_KEYS: dict[str, frozenset[str]] = {**_SHAPE_KEYS, "polygon": frozenset({"ring"})}
_PRIMITIVE_KEYS = frozenset({"kind", "style", "value", "ids"})
_HEX = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})")

_Px = Callable[[Vec2], Vec2]


class OverlayError(ValueError):
    """An overlay the contract refuses. `code` is `INVALID_ARGUMENT`, or `TOO_LARGE` for
    the cap. `path` is the refused field exactly (`overlay.layers[0].scale.domain`), the
    missing or unknown key included; the message starts with it and is for people only.
    `render_svg` re-raises it as a render error."""

    def __init__(self, path: str, message: str, code: str = INVALID_ARGUMENT) -> None:
        super().__init__(message)
        self.path = path
        self.code = code


def _refuse(path: str, text: str, code: str = INVALID_ARGUMENT) -> OverlayError:
    return OverlayError(path, f"{path} {text}", code)


@dataclass(frozen=True, slots=True)
class Paint:
    """Resolved `#rrggbb` colours (None paints nothing) and the stroke width in px."""

    fill: str | None
    stroke: str | None
    width_px: float
    opacity: float


@dataclass(frozen=True, slots=True)
class Scale:
    kind: str
    domain: tuple[float, ...] | tuple[str, ...]
    colors: tuple[str, ...]  # resolved `#rrggbb`
    unit: str
    title: str


@dataclass(frozen=True, slots=True)
class Primitive:
    kind: str
    points: tuple[Vec2, ...]  # ring, polyline points, or the one centre / anchor
    holes: tuple[tuple[Vec2, ...], ...]
    radius: float  # circle only, mm
    text: str  # label only
    paint: Paint
    value: float | str | None
    ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class Layer:
    id: str
    label: str
    visible: bool
    scale: Scale | None
    primitives: tuple[Primitive, ...]


@dataclass(frozen=True, slots=True)
class Overlay:
    revision: int
    layers: tuple[Layer, ...]

    @property
    def primitive_count(self) -> int:
        return sum(len(layer.primitives) for layer in self.layers)


# --- reading -------------------------------------------------------------------------------


def parse_overlay(value: object) -> Overlay:
    """The overlay, validated, or `OverlayError` with the path of what it refuses."""
    top = _object("overlay", value, {"schema", "version", "units", "revision", "layers"})
    if top["schema"] != OVERLAY_SCHEMA:
        raise _refuse("overlay.schema", f"must be {OVERLAY_SCHEMA!r}, got {top['schema']!r}")
    version = top["version"]
    if _integral(version) != OVERLAY_SCHEMA_VERSION:
        raise _refuse("overlay.version", f"must be {OVERLAY_SCHEMA_VERSION}, got {version!r}")
    if top["units"] != "mm":
        raise _refuse("overlay.units", f"must be 'mm', got {top['units']!r}")
    revision = _int("overlay.revision", top["revision"])
    raw_layers = _list("overlay.layers", top["layers"])
    shells = [
        _object(f"overlay.layers[{i}]", item, {"id", "label", "visible", "scale", "primitives"})
        for i, item in enumerate(raw_layers)
    ]
    raw_primitives = [
        _list(f"overlay.layers[{i}].primitives", shell["primitives"])
        for i, shell in enumerate(shells)
    ]
    total = sum(len(items) for items in raw_primitives)
    if total > MAX_OVERLAY_PRIMITIVES:
        raise _refuse(
            "overlay.layers",
            f"hold {total} primitives, more than MAX_OVERLAY_PRIMITIVES "
            f"({MAX_OVERLAY_PRIMITIVES}); the overlay is refused, never truncated",
            TOO_LARGE,
        )
    layers: list[Layer] = []
    seen: set[str] = set()
    for i, (shell, items) in enumerate(zip(shells, raw_primitives, strict=True)):
        layers.append(_layer(f"overlay.layers[{i}]", shell, items, seen))
    return Overlay(revision=revision, layers=tuple(layers))


def _layer(path: str, shell: dict[str, object], items: list[object], seen: set[str]) -> Layer:
    layer_id = _str(f"{path}.id", shell["id"])
    if not layer_id:
        raise _refuse(f"{path}.id", "must not be empty")
    if layer_id in seen:
        raise _refuse(f"{path}.id", f"{layer_id!r} is used by another layer")
    seen.add(layer_id)
    label = _str(f"{path}.label", shell["label"])
    visible = shell["visible"]
    if not isinstance(visible, bool):
        raise _refuse(f"{path}.visible", f"must be true or false, got {visible!r}")
    raw_scale = shell["scale"]
    scale = None if raw_scale is None else _scale(f"{path}.scale", raw_scale)
    primitives = tuple(
        _primitive(f"{path}.primitives[{j}]", item, scale) for j, item in enumerate(items)
    )
    return Layer(layer_id, label, visible, scale, primitives)


def _scale(path: str, value: object) -> Scale:
    raw = _object(path, value, {"kind", "domain", "colors", "unit", "title"})
    kind = raw["kind"]
    if not isinstance(kind, str) or kind not in SCALE_KINDS:
        raise _refuse(f"{path}.kind", f"must be one of {', '.join(SCALE_KINDS)}, got {kind!r}")
    raw_colors = _list(f"{path}.colors", raw["colors"])
    colors = tuple(_color(f"{path}.colors[{i}]", c) for i, c in enumerate(raw_colors))
    if len(colors) < 2:
        raise _refuse(f"{path}.colors", f"needs at least 2 colours, got {len(colors)}")
    items = _list(f"{path}.domain", raw["domain"])
    domain: tuple[float, ...] | tuple[str, ...]
    if kind == "categorical":
        names = tuple(_str(f"{path}.domain[{i}]", c) for i, c in enumerate(items))
        for i, name in enumerate(names):
            if name in names[:i]:
                raise _refuse(f"{path}.domain[{i}]", f"repeats the category {name!r}")
        if len(names) != len(colors):
            raise _refuse(
                f"{path}.colors",
                f"needs one colour per category: {len(names)} categories, "
                f"{len(colors)} colours",
            )
        domain = names
    else:
        bounds = tuple(_number(f"{path}.domain[{i}]", c) for i, c in enumerate(items))
        want = 2 if kind == "sequential" else 3
        if len(bounds) != want:
            raise _refuse(f"{path}.domain", f"of a {kind} scale needs {want} numbers")
        if any(a >= b for a, b in zip(bounds, bounds[1:])):
            raise _refuse(f"{path}.domain", f"must increase strictly, got {list(bounds)}")
        if kind == "diverging" and len(colors) % 2 == 0:
            raise _refuse(
                f"{path}.colors",
                f"of a diverging scale must be an odd number, at least 3, got {len(colors)}",
            )
        domain = bounds
    unit = _str(f"{path}.unit", raw["unit"])
    return Scale(kind, domain, colors, unit, _str(f"{path}.title", raw["title"]))


def _primitive(path: str, value: object, scale: Scale | None) -> Primitive:
    if not isinstance(value, dict):
        raise _refuse(path, f"must be an object, got {type(value).__name__}")
    shell = cast(dict[object, object], value)
    kind = shell.get("kind")
    if not isinstance(kind, str) or kind not in PRIMITIVE_KINDS:
        raise _refuse(f"{path}.kind", f"must be one of {', '.join(PRIMITIVE_KINDS)}, got {kind!r}")
    allowed = set(_SHAPE_KEYS[kind] | _PRIMITIVE_KEYS)
    raw = _object(path, shell, allowed, set(_REQUIRED_SHAPE_KEYS[kind]) | {"kind"})
    has_style, has_value = "style" in raw, "value" in raw
    if has_style == has_value:
        raise _refuse(path, "must carry exactly one of style or value")
    holes: tuple[tuple[Vec2, ...], ...] = ()
    radius = 0.0
    text = ""
    if kind == "polygon":
        points = _points(f"{path}.ring", raw["ring"], 3)
        if "holes" in raw:
            raw_holes = _list(f"{path}.holes", raw["holes"])
            holes = tuple(_points(f"{path}.holes[{i}]", h, 3) for i, h in enumerate(raw_holes))
    elif kind == "circle":
        points = (_xy(f"{path}.center", raw["center"]),)
        radius = _number(f"{path}.radius", raw["radius"])
        if radius <= 0.0:
            raise _refuse(f"{path}.radius", f"must be positive, got {radius!r}")
    elif kind == "polyline":
        points = _points(f"{path}.points", raw["points"], 2)
    else:
        points = (_xy(f"{path}.at", raw["at"]),)
        if kind == "label":
            text = _str(f"{path}.text", raw["text"])
    ids: tuple[int, ...] = ()
    if "ids" in raw:
        raw_ids = _list(f"{path}.ids", raw["ids"])
        ids = tuple(_int(f"{path}.ids[{i}]", v) for i, v in enumerate(raw_ids))
    if has_style:
        paint = _style(f"{path}.style", raw["style"], kind)
        data_value: float | str | None = None
    else:
        data_value, paint = _valued(f"{path}.value", raw["value"], kind, scale)
    return Primitive(kind, points, holes, radius, text, paint, data_value, ids)


def _style(path: str, value: object, kind: str) -> Paint:
    raw = _object(path, value, {"stroke", "fill", "width_px", "opacity"}, required=set())
    for key in ("fill", "stroke"):
        if raw.get(key) is not None and key not in _PAINTS[kind]:
            raise _refuse(f"{path}.{key}", f"is not taken by a {kind}")
    fill = None if raw.get("fill") is None else _color(f"{path}.fill", raw["fill"])
    stroke = None if raw.get("stroke") is None else _color(f"{path}.stroke", raw["stroke"])
    if fill is None and stroke is None:
        raise _refuse(path, f"paints nothing: give a {' or '.join(sorted(_PAINTS[kind]))}")
    width = _number(f"{path}.width_px", raw["width_px"]) if "width_px" in raw else 1.0
    if width <= 0.0:
        raise _refuse(f"{path}.width_px", f"must be positive, got {width!r}")
    opacity = _number(f"{path}.opacity", raw["opacity"]) if "opacity" in raw else 1.0
    if not 0.0 <= opacity <= 1.0:
        raise _refuse(f"{path}.opacity", f"must be between 0 and 1, got {opacity!r}")
    return Paint(fill, stroke, width, opacity)


def _valued(
    path: str, value: object, kind: str, scale: Scale | None
) -> tuple[float | str, Paint]:
    if scale is None:
        raise _refuse(path, "needs a layer scale")
    data: float | str
    if scale.kind == "categorical":
        if not isinstance(value, str):
            raise _refuse(path, f"must be a category of a categorical scale, got {value!r}")
        data = value
    else:
        if isinstance(value, str):
            raise _refuse(path, f"must be a number on a {scale.kind} scale, got {value!r}")
        data = _number(path, value)
    color = scale_color(scale, data, path)
    if kind == "polyline":
        return data, Paint(None, color, VALUE_STROKE_PX, 1.0)
    return data, Paint(color, None, 1.0, 1.0)


# --- colour --------------------------------------------------------------------------------


def resolve_color(value: str) -> str | None:
    """Lower-case `#rrggbb` for a hex colour or a known token; None for anything else."""
    if value in COLOR_TOKENS:
        return COLOR_TOKENS[value]
    if _HEX.fullmatch(value) is None:
        return None
    digits = value[1:].lower()
    return "#" + ("".join(c * 2 for c in digits) if len(digits) == 3 else digits)


def _color(path: str, value: object) -> str:
    if not isinstance(value, str):
        raise _refuse(path, f"must be a colour string, got {value!r}")
    resolved = resolve_color(value)
    if resolved is None:
        raise _refuse(
            path,
            f"must be #rgb, #rrggbb or a design token ({', '.join(COLOR_TOKENS)}), "
            f"got {value!r}",
        )
    return resolved


def scale_stops(scale: Scale) -> list[float]:
    """Where each colour sits on a numeric scale's domain (spec "Scales")."""
    domain = cast(tuple[float, ...], scale.domain)
    n = len(scale.colors)
    if scale.kind == "sequential":
        lo, hi = domain
        return [lo + (hi - lo) * i / (n - 1) for i in range(n)]
    lo, mid, hi = domain
    k = (n - 1) // 2
    left = [lo + (mid - lo) * i / k for i in range(k)]
    return [*left, *(mid + (hi - mid) * j / k for j in range(k + 1))]


def scale_color(scale: Scale, value: float | str, path: str = "value") -> str:
    """The `#rrggbb` a value takes on its scale: clamped, 8-bit sRGB, no gamma."""
    if scale.kind == "categorical":
        names = cast(tuple[str, ...], scale.domain)
        if not isinstance(value, str) or value not in names:
            raise _refuse(path, f"{value!r} is not a category of the layer scale")
        return scale.colors[names.index(value)]
    x = float(value)
    stops = scale_stops(scale)
    if x <= stops[0]:
        return scale.colors[0]
    if x >= stops[-1]:
        return scale.colors[-1]
    i = max(j for j in range(len(stops) - 1) if stops[j] <= x)
    t = (x - stops[i]) / (stops[i + 1] - stops[i])
    return _mix(scale.colors[i], scale.colors[i + 1], t)


def _mix(c0: str, c1: str, t: float) -> str:
    a = [int(c0[k : k + 2], 16) for k in (1, 3, 5)]
    b = [int(c1[k : k + 2], 16) for k in (1, 3, 5)]
    return "#" + "".join(
        f"{math.floor(p + (q - p) * t + 0.5):02x}" for p, q in zip(a, b, strict=True)
    )


# --- field readers -------------------------------------------------------------------------


def _object(
    path: str, value: object, allowed: set[str], required: set[str] | None = None
) -> dict[str, object]:
    """A JSON object with string keys, none unknown, every required one present. An unknown
    key is refused before a missing one, each the first in sorted order, at `path.key`."""
    if not isinstance(value, dict):
        raise _refuse(path, f"must be an object, got {type(value).__name__}")
    raw = cast(dict[object, object], value)
    for key in raw:
        if not isinstance(key, str):
            raise _refuse(path, f"keys must be strings, got {key!r}")
    typed = cast(dict[str, object], raw)
    extra = sorted(set(typed) - allowed)
    if extra:
        raise _refuse(f"{path}.{extra[0]}", "is an unknown key")
    missing = sorted((allowed if required is None else required) - set(typed))
    if missing:
        raise _refuse(f"{path}.{missing[0]}", "is missing")
    return typed


def _list(path: str, value: object) -> list[object]:
    if not isinstance(value, list):
        raise _refuse(path, f"must be a list, got {type(value).__name__}")
    return cast(list[object], value)


def _str(path: str, value: object) -> str:
    if not isinstance(value, str):
        raise _refuse(path, f"must be a string, got {value!r}")
    return value


def _integral(value: object) -> int | None:
    """An integer by value (spec "Integers"): a finite number with no fractional part, so
    `1.0` is 1, as JSON.parse reads it. None for anything else, a bool included."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    return None


def _int(path: str, value: object) -> int:
    whole = _integral(value)
    if whole is None or whole < 0:
        raise _refuse(path, f"must be a non-negative integer, got {value!r}")
    return whole


def _number(path: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _refuse(path, f"must be a number, got {value!r}")
    if not math.isfinite(value):
        raise _refuse(path, f"must be finite, got {value!r}")
    return float(value)


def _xy(path: str, value: object) -> Vec2:
    items = _list(path, value)
    if len(items) != 2:
        raise _refuse(path, f"must be [x, y] in mm, got {len(items)} values")
    return _number(f"{path}[0]", items[0]), _number(f"{path}[1]", items[1])


def _points(path: str, value: object, least: int) -> tuple[Vec2, ...]:
    points = tuple(_xy(f"{path}[{i}]", p) for i, p in enumerate(_list(path, value)))
    if len(points) < least:
        raise _refuse(path, f"needs at least {least} points, got {len(points)}")
    return points


def as_overlay(value: Overlay | Mapping[str, object] | object) -> Overlay:
    """A parsed overlay as is, or its JSON object parsed (anything else is refused)."""
    return value if isinstance(value, Overlay) else parse_overlay(value)


# --- drawing -------------------------------------------------------------------------------

LEGEND_W_PX = 150.0
LEGEND_BAR_PX = 10.0
LEGEND_ROW_PX = 14.0
LEGEND_GAP_PX = 10.0
LEGEND_EDGE_PX = 12.0


def overlay_svg(overlay: Overlay, view: View, viewport: Viewport) -> list[str]:
    """One `<g class="overlay">`: the visible layers in order, then their legends."""

    def px(p: Vec2) -> Vec2:
        return viewport.to_px(view.project((p[0], p[1], 0.0)))

    out = [f'<g class="overlay" data-revision="{overlay.revision}">']
    for layer in overlay.layers:
        if not layer.visible:
            continue
        out.append(
            f'<g class="overlay-layer" data-layer="{clean_text(layer.id)}" '
            f'data-label="{clean_text(layer.label)}">'
        )
        out.extend(_primitive_svg(p, px, viewport.scale) for p in layer.primitives)
        out.append("</g>")
    top = LEGEND_EDGE_PX
    right = viewport.width - LEGEND_EDGE_PX
    for index, layer in enumerate(overlay.layers):
        if layer.visible and layer.scale is not None:
            lines, height = _legend_svg(index, layer.id, layer.scale, right, top)
            out.extend(lines)
            top += height + LEGEND_GAP_PX
    out.append("</g>")
    return out


def _paint_attrs(paint: Paint) -> str:
    parts = [f'fill="{paint.fill or "none"}"', f'stroke="{paint.stroke or "none"}"']
    if paint.stroke is not None:
        parts.append(f'stroke-width="{paint.width_px:g}"')
    if paint.opacity < 1.0:
        parts.append(f'opacity="{paint.opacity:g}"')
    return " ".join(parts)


def _data_attrs(p: Primitive) -> str:
    out = ""
    if p.value is not None:
        shown = p.value if isinstance(p.value, str) else f"{p.value:.10g}"
        out += f' data-value="{clean_text(shown)}"'
    if p.ids:
        out += f' data-ids="{" ".join(str(i) for i in p.ids)}"'
    return out


def _path_data(points: Sequence[Vec2], px: _Px, closed: bool) -> str:
    coords = [px(p) for p in points]
    parts = [f"{'M' if i == 0 else 'L'}{num(x)} {num(y)}" for i, (x, y) in enumerate(coords)]
    return " ".join(parts) + (" Z" if closed else "")


def _primitive_svg(p: Primitive, px: _Px, scale: float) -> str:
    paint = _paint_attrs(p.paint)
    data = _data_attrs(p)
    if p.kind == "polygon":
        d = " ".join(_path_data(ring, px, True) for ring in (p.points, *p.holes))
        return f'<path d="{d}" fill-rule="evenodd" {paint}{data}/>'
    if p.kind == "polyline":
        d = _path_data(p.points, px, False)
        return f'<path d="{d}" {paint} stroke-linecap="round" stroke-linejoin="round"{data}/>'
    x, y = px(p.points[0])
    if p.kind == "circle":
        r = p.radius * scale
        return f'<circle cx="{num(x)}" cy="{num(y)}" r="{num(r)}" {paint}{data}/>'
    if p.kind == "point":
        r = OVERLAY_POINT_RADIUS_PX
        return f'<circle cx="{num(x)}" cy="{num(y)}" r="{num(r)}" {paint}{data}/>'
    return f'<text x="{num(x)}" y="{num(y)}" {FONT} {paint}{data}>{clean_text(p.text)}</text>'


def _legend_svg(
    index: int, layer_id: str, scale: Scale, right: float, top: float
) -> tuple[list[str], float]:
    """A legend block whose top-right corner is (right, top); returns it and its height."""
    x0 = right - LEGEND_W_PX
    heading = f"{scale.title} ({scale.unit})" if scale.unit else scale.title
    out = [
        f'<g class="overlay-legend" data-layer="{clean_text(layer_id)}" {FONT} '
        f'fill="{BLUE}">',
        f'<text x="{num(x0)}" y="{num(top + 10.0)}">{clean_text(heading)}</text>',
    ]
    bar_top = top + 14.0
    if scale.kind == "categorical":
        names = cast(tuple[str, ...], scale.domain)
        for i, (name, color) in enumerate(zip(names, scale.colors, strict=True)):
            y = bar_top + i * LEGEND_ROW_PX
            out.append(
                f'<rect x="{num(x0)}" y="{num(y)}" width="{num(LEGEND_BAR_PX)}" '
                f'height="{num(LEGEND_BAR_PX)}" fill="{color}" stroke="{BLUE}" '
                'stroke-width="0.5"/>'
            )
            out.append(
                f'<text x="{num(x0 + LEGEND_BAR_PX + 4.0)}" y="{num(y + 9.0)}">'
                f"{clean_text(name)}</text>"
            )
        out.append("</g>")
        return out, 14.0 + len(names) * LEGEND_ROW_PX
    stops = scale_stops(scale)
    lo, hi = stops[0], stops[-1]
    gradient = f"overlay-scale-{index}"
    out.append(f'<defs><linearGradient id="{gradient}" x1="0" y1="0" x2="1" y2="0">')
    out.extend(
        f'<stop offset="{(s - lo) / (hi - lo):.6g}" stop-color="{c}"/>'
        for s, c in zip(stops, scale.colors, strict=True)
    )
    out.append("</linearGradient></defs>")
    out.append(
        f'<rect x="{num(x0)}" y="{num(bar_top)}" width="{num(LEGEND_W_PX)}" '
        f'height="{num(LEGEND_BAR_PX)}" fill="url(#{gradient})" stroke="{BLUE}" '
        'stroke-width="0.5"/>'
    )
    label_y = bar_top + LEGEND_BAR_PX + 11.0
    ticks = [(lo, x0, "start"), (hi, right, "end")]
    if scale.kind == "diverging":
        mid = cast(tuple[float, ...], scale.domain)[1]
        ticks.insert(1, (mid, x0 + LEGEND_W_PX * (mid - lo) / (hi - lo), "middle"))
    out.extend(
        f'<text x="{num(x)}" y="{num(label_y)}" text-anchor="{anchor}">{v:.4g}</text>'
        for v, x, anchor in ticks
    )
    out.append("</g>")
    return out, 14.0 + LEGEND_BAR_PX + 13.0
