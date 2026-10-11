"""Agent tool bodies (ADR 0028, spec `agent-surface-mcp.md` stage S2): no MCP SDK here.

`Session` holds one document and its revision counter; `apeCAD.agent.tools` has one function
per tool over a session, returning the §2 envelope; `LocalTools` keeps local-mode documents
by id. The scratchpad's HTTP routes and the later MCP adapter (S3) both call these.
"""

from __future__ import annotations

from apeCAD.agent.errors import Envelope, ToolError
from apeCAD.agent.local import LocalTools
from apeCAD.agent.session import MAX_BATCH, Session

__all__ = ["MAX_BATCH", "Envelope", "LocalTools", "Session", "ToolError"]
