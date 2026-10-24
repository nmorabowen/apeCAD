"""`render_svg` and `render_png`: validate the spec §4 `render` parameters, fit the view, write."""

from __future__ import annotations

import importlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from apeCAD.document import Document
from apeCAD.entities import Box, EntityId, Solid
from apeCAD.render.annotate import plan_layout, section_notes
from apeCAD.render.scene import Drawable, closure, drawables, entity_map
from apeCAD.render.svg import TextOptions, Viewport, write_svg
from apeCAD.render.views import VIEW_NAMES, VIEWS, Vec2, Vec3, View, ViewName

MIN_SIZE_PX = 64
MAX_SIZE_PX = 2048
MAX_MARGIN = 0.4
ZERO_EXTENT_MM = 1000.0
CHORD_ERROR_PX = 0.5


class RenderArgumentError(ValueError):
    """A render parameter is malformed. Agents see it as `INVALID_ARGUMENT`."""

    code = "INVALID_ARGUMENT"


class PngUnavailableError(RenderArgumentError):
    """The `png` extra is not installed. Agents see it as `UNAVAILABLE` (never a fallback)."""

    code = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class RenderResult:
    svg: str
    view: ViewName
    width: int
    height: int
    scale_px_per_mm: float
    # The visible rectangle on the view plane, mm: {"min": [u, v], "max": [u, v]}.
    extents_mm: dict[str, list[float]]
    entities: int
    path: str | None = None


@dataclass(frozen=True, slots=True)
class PngResult:
    png: bytes
    view: ViewName
    width: int
    height: int
    scale_px_per_mm: float
    extents_mm: dict[str, list[float]]
    entities: int
    path: str | None = None


def render_svg(
    document: Document,
    *,
    view: str | None = None,
    width: int = 800,
    height: int = 600,
    margin: float = 0.05,
    ids: Sequence[EntityId] | None = None,
    highlight: Sequence[EntityId] | None = None,
    labels: bool = True,
    show_ids: bool = False,
    window: tuple[Sequence[float], Sequence[float]] | None = None,
    save_to: str | None = None,
    root: Path | None = None,
    annotate: bool = True,
) -> RenderResult:
    """Orthographic wireframe SVG of the draft (spec agent-surface-mcp §4 `render`).

    `width`/`height` clamp to 64–2048 px and `margin` to 0–0.4 of the larger extent.
    `ids` limits drawing (and the fit) to those entities and what they are built from.
    `save_to` is relative to `root` and must resolve under it.
    `annotate` draws a plan of a section at a standard scale with tags, overall dimensions
    and a scale note (spec ape-design §4 D4); they are drawn, never stored. Off, with a
    `window`, or when no standard scale leaves room, the bare drawing is fitted as before.
    """
    width_px = _clamp_size("width", width)
    height_px = _clamp_size("height", height)
    margin_frac = _clamp_margin(margin)
    entities = entity_map(document)
    children = document.brep().children
    draw_ids = (
        set(entities)
        if ids is None
        else closure(known_ids("ids", ids, entities), children)
    )
    marked: set[EntityId] = (
        set()
        if highlight is None
        else closure(known_ids("highlight", highlight, entities), children) & draw_ids
    )
    chosen = _choose_view(view, entities, draw_ids)
    coarse = drawables(entities, draw_ids, None)
    bounds = _window_bounds(chosen, window) if window is not None else _bounds(chosen, coarse)
    notes = (
        section_notes(chosen, entities, coarse, labels) if annotate and window is None else None
    )
    layout = (
        plan_layout(notes, bounds, width_px, height_px, margin_frac)
        if notes is not None and bounds is not None
        else None
    )
    if layout is None:  # bare drawing, fitted; also when no standard scale leaves room
        viewport = _fit(bounds, width_px, height_px, margin_frac)
    else:  # exactly the standard scale the layout chose
        viewport = Viewport(width_px, height_px, layout.scale_px_per_mm, layout.centre_mm)
    items = drawables(entities, draw_ids, CHORD_ERROR_PX / viewport.scale)
    svg = write_svg(chosen, viewport, items, marked, TextOptions(labels, show_ids), layout)
    path = None if save_to is None else save_text(svg, save_to, root)
    low, high = viewport.extents_mm()
    return RenderResult(
        svg=svg,
        view=chosen.name,
        width=width_px,
        height=height_px,
        scale_px_per_mm=viewport.scale,
        extents_mm={"min": [low[0], low[1]], "max": [high[0], high[1]]},
        entities=len(items),
        path=path,
    )


def _clamp_size(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RenderArgumentError(f"{name} must be an integer, got {value!r}")
    return max(MIN_SIZE_PX, min(MAX_SIZE_PX, value))


def _clamp_margin(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise RenderArgumentError(f"margin must be a finite number, got {value!r}")
    return max(0.0, min(MAX_MARGIN, float(value)))


def known_ids(
    name: str, ids: Sequence[object], entities: Mapping[EntityId, object]
) -> list[EntityId]:
    out: list[EntityId] = []
    for entity_id in ids:
        if isinstance(entity_id, bool) or not isinstance(entity_id, int):
            raise RenderArgumentError(f"{name} must be integers, got {entity_id!r}")
        if entity_id not in entities:
            raise RenderArgumentError(f"{name}: unknown entity id {entity_id}")
        out.append(entity_id)
    return out


def _choose_view(
    view: str | None, entities: Mapping[EntityId, object], draw_ids: set[EntityId]
) -> View:
    if view is None:
        solid = any(isinstance(entities[i], (Solid, Box)) for i in draw_ids)
        return VIEWS["iso" if solid else "top"]
    for name in VIEW_NAMES:
        if view == name:
            return VIEWS[name]
    raise RenderArgumentError(f"view must be one of {', '.join(VIEW_NAMES)}, got {view!r}")


Bounds = tuple[Vec2, Vec2] | None


def _bounds(view: View, items: list[Drawable]) -> Bounds:
    """Extents of everything drawn, a bar's whole disc included (not just its centre)."""
    us: list[float] = []
    vs: list[float] = []
    for d in items:
        for path, _closed in d.paths:
            for p in path:
                u, v = view.project(p)
                us += (u - d.radius_mm, u + d.radius_mm)
                vs += (v - d.radius_mm, v + d.radius_mm)
    if not us:
        return None
    return (min(us), min(vs)), (max(us), max(vs))


def _window_bounds(view: View, window: tuple[Sequence[float], Sequence[float]]) -> Bounds:
    low = _corner("window.min", window[0])
    high = _corner("window.max", window[1])
    if any(lo > hi for lo, hi in zip(low, high, strict=True)):
        raise RenderArgumentError("window.min must not exceed window.max on any axis")
    corners: list[Vec3] = [
        (x, y, z) for x in (low[0], high[0]) for y in (low[1], high[1]) for z in (low[2], high[2])
    ]
    projected = [view.project(c) for c in corners]
    us = [uv[0] for uv in projected]
    vs = [uv[1] for uv in projected]
    return (min(us), min(vs)), (max(us), max(vs))


def _corner(name: str, values: Sequence[object]) -> Vec3:
    coords = [
        float(v)
        for v in values
        if not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v)
    ]
    if len(values) != 3 or len(coords) != 3:
        raise RenderArgumentError(f"{name} must be three finite millimetre values")
    return (coords[0], coords[1], coords[2])


def _fit(bounds: Bounds, width: int, height: int, margin: float) -> Viewport:
    """Fit the bounds plus margin into the image, keeping the aspect ratio."""
    if bounds is None:
        (u0, v0), (u1, v1) = (0.0, 0.0), (0.0, 0.0)
    else:
        (u0, v0), (u1, v1) = bounds
    span_u, span_v = u1 - u0, v1 - v0
    if span_u <= 0.0 and span_v <= 0.0:
        span_u = span_v = ZERO_EXTENT_MM
    pad = margin * max(span_u, span_v)
    span_u += 2.0 * pad
    span_v += 2.0 * pad
    scale = min(
        width / span_u if span_u > 0.0 else math.inf,
        height / span_v if span_v > 0.0 else math.inf,
    )
    return Viewport(width, height, scale, ((u0 + u1) / 2.0, (v0 + v1) / 2.0))


def render_png(
    document: Document,
    *,
    view: str | None = None,
    width: int = 800,
    height: int = 600,
    margin: float = 0.05,
    ids: Sequence[EntityId] | None = None,
    highlight: Sequence[EntityId] | None = None,
    labels: bool = True,
    show_ids: bool = False,
    window: tuple[Sequence[float], Sequence[float]] | None = None,
    save_to: str | None = None,
    root: Path | None = None,
    annotate: bool = True,
) -> PngResult:
    """Orthographic wireframe PNG of the draft (spec agent-surface-mcp §4 `render`, stage S7).

    Rasterizes the `render_svg` output with `resvg_py` from the optional `apeCAD[png]` extra.
    Without the extra, raises `PngUnavailableError` (`UNAVAILABLE`), never falling back to SVG.
    """
    try:
        resvg_py: Any = importlib.import_module("resvg_py")
    except ImportError as exc:
        raise PngUnavailableError(
            "PNG output needs the png extra: pip install apeCAD[png]"
        ) from exc
    rendered = render_svg(
        document,
        view=view,
        width=width,
        height=height,
        margin=margin,
        ids=ids,
        highlight=highlight,
        labels=labels,
        show_ids=show_ids,
        window=window,
        save_to=None,
        root=root,
        annotate=annotate,
    )
    png = bytes(
        resvg_py.svg_to_bytes(
            svg_string=rendered.svg, width=rendered.width, height=rendered.height
        )
    )
    path = None if save_to is None else save_bytes(png, save_to, root)
    return PngResult(
        png=png,
        view=rendered.view,
        width=rendered.width,
        height=rendered.height,
        scale_px_per_mm=rendered.scale_px_per_mm,
        extents_mm=rendered.extents_mm,
        entities=rendered.entities,
        path=path,
    )


def _resolve_save_to(save_to: str, root: Path | None) -> Path:
    if root is None:
        raise RenderArgumentError("save_to needs a root folder")
    base = root.resolve()
    target = (base / save_to).resolve()
    if target == base or not target.is_relative_to(base):
        raise RenderArgumentError(f"save_to {save_to!r} must resolve to a file under the root")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def save_text(text: str, save_to: str, root: Path | None) -> str:
    """Write `text` to `save_to` under `root`: the SVG here, the DXF in `render/dxf.py`."""
    target = _resolve_save_to(save_to, root)
    target.write_text(text, encoding="utf-8", newline="\n")
    return str(target)


def save_bytes(data: bytes, save_to: str, root: Path | None) -> str:
    """Write `data` to `save_to` under `root` (PNG output, stage S7)."""
    target = _resolve_save_to(save_to, root)
    target.write_bytes(data)
    return str(target)

