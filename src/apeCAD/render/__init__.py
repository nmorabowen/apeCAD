"""SVG and PNG render of the draft for agents (ADR 0028, spec agent-surface-mcp §4 `render`)."""

from __future__ import annotations

from apeCAD.render.api import (
    PngResult,
    PngUnavailableError,
    RenderArgumentError,
    RenderResult,
    render_png,
    render_svg,
)
from apeCAD.render.views import VIEW_NAMES, ViewName

__all__ = [
    "VIEW_NAMES",
    "PngResult",
    "PngUnavailableError",
    "RenderArgumentError",
    "RenderResult",
    "ViewName",
    "render_png",
    "render_svg",
]

