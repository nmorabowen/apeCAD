"""`GET /api/render.svg` query string → `render_svg` (spec agent-surface-mcp §6, svg only)."""

from __future__ import annotations

from urllib.parse import parse_qs

from apeCAD.document import Document
from apeCAD.render.api import RenderArgumentError, RenderResult, render_svg

QUERY_KEYS = frozenset(
    {"view", "width", "height", "margin", "ids", "highlight", "labels", "show_ids", "window",
     "format"}
)
_TRUE = ("1", "true", "yes")
_FALSE = ("0", "false", "no")


def render_from_query(document: Document, query: str) -> RenderResult:
    """Parse e.g. `view=top&width=400&ids=1,2&window=0,0,0,1000,1000,0`. No `save_to` here."""
    params = parse_qs(query, keep_blank_values=True, strict_parsing=False)
    unknown = sorted(set(params) - QUERY_KEYS)
    if unknown:
        raise RenderArgumentError(f"unknown render parameter(s): {', '.join(unknown)}")
    single: dict[str, str] = {}
    for key, values in params.items():
        if len(values) != 1:
            raise RenderArgumentError(f"{key} given more than once")
        single[key] = values[0]
    if single.get("format", "svg") != "svg":
        raise RenderArgumentError("this route renders svg only")
    window = None
    if "window" in single:
        corners = _floats("window", single["window"])
        if len(corners) != 6:
            raise RenderArgumentError("window takes six numbers: x0,y0,z0,x1,y1,z1")
        window = (corners[:3], corners[3:])
    return render_svg(
        document,
        view=single.get("view"),
        width=_int("width", single.get("width", "800")),
        height=_int("height", single.get("height", "600")),
        margin=_float("margin", single.get("margin", "0.05")),
        ids=_ints("ids", single["ids"]) if "ids" in single else None,
        highlight=_ints("highlight", single["highlight"]) if "highlight" in single else None,
        labels=_bool("labels", single.get("labels", "true")),
        show_ids=_bool("show_ids", single.get("show_ids", "false")),
        window=window,
    )


def _int(name: str, raw: str) -> int:
    try:
        return int(raw)
    except ValueError as exc:
        raise RenderArgumentError(f"{name} must be an integer, got {raw!r}") from exc


def _float(name: str, raw: str) -> float:
    try:
        return float(raw)
    except ValueError as exc:
        raise RenderArgumentError(f"{name} must be a number, got {raw!r}") from exc


def _ints(name: str, raw: str) -> list[int]:
    return [_int(name, part) for part in raw.split(",") if part.strip()]


def _floats(name: str, raw: str) -> list[float]:
    return [_float(name, part) for part in raw.split(",")]


def _bool(name: str, raw: str) -> bool:
    lowered = raw.lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False
    raise RenderArgumentError(f"{name} must be true or false, got {raw!r}")
