"""SVG and PNG render of the draft for agents (ADR 0028, spec agent-surface-mcp §4 `render`)."""

from __future__ import annotations

from apeCAD.render.api import (
    OverlayTooLargeError,
    PngResult,
    PngUnavailableError,
    RenderArgumentError,
    RenderResult,
    render_png,
    render_svg,
)
from apeCAD.render.overlay import (
    MAX_OVERLAY_PRIMITIVES,
    OVERLAY_SCHEMA,
    OVERLAY_SCHEMA_VERSION,
    Overlay,
    OverlayError,
    parse_overlay,
)
from apeCAD.render.views import VIEW_NAMES, ViewName

__all__ = [
    "MAX_OVERLAY_PRIMITIVES",
    "OVERLAY_SCHEMA",
    "OVERLAY_SCHEMA_VERSION",
    "VIEW_NAMES",
    "Overlay",
    "OverlayError",
    "OverlayTooLargeError",
    "PngResult",
    "PngUnavailableError",
    "RenderArgumentError",
    "RenderResult",
    "ViewName",
    "parse_overlay",
    "render_png",
    "render_svg",
]
