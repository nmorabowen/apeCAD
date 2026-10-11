"""The op catalog: one entry per op, with its params schema, docs and an example (ADR 0028).

Spec `AProjects/specs/agent-surface-mcp.md` §1. `apply` is the one path every surface (the
scratchpad's `/api/op`, and later the agent tools, MCP and CLI) sends an op through. Replaying
a log (`Document.from_dict`, `/api/load`) does not go through it.
"""

from __future__ import annotations

from apeCAD.catalog.calls import Applied, apply, decode, list_ops, spec_for, split_request
from apeCAD.catalog.entries import CATALOG
from apeCAD.catalog.spec import OpSpec, Produces

__all__ = [
    "CATALOG",
    "Applied",
    "OpSpec",
    "Produces",
    "apply",
    "decode",
    "list_ops",
    "spec_for",
    "split_request",
]
