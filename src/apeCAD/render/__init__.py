"""SVG render of the draft for agents (ADR 0028, spec agent-surface-mcp §4 `render`)."""

from __future__ import annotations

from apeCAD.render.api import RenderArgumentError, RenderResult, render_svg
from apeCAD.render.views import VIEW_NAMES, ViewName

__all__ = ["VIEW_NAMES", "RenderArgumentError", "RenderResult", "ViewName", "render_svg"]
