"""apeCAD: spatial scratchpad and intent document for ape* workflows.

The public surface is a kernel-free Python document. Humans and agents
sketch spatial intent here; apeGmsh and apeSteel consume bridges.
The drawing window, when it exists, is a client of this package — not
the source of truth.

See ``AProjects/`` for ADRs, memory, specs, and guides.
"""

from __future__ import annotations

from apeCAD.document import Document
from apeCAD.entities import Arc, Bezier, Box, Circle, Ellipse, Face, Line, Point, Polyline, Solid
from apeCAD.errors import DocumentError
from apeCAD.frame import FrameGraph, FrameMember, FrameNode, FrameVolume
from apeCAD.geometry import XYZ

__version__ = "0.0.0"

__all__ = [
    "Arc",
    "Bezier",
    "Box",
    "Circle",
    "Document",
    "DocumentError",
    "Ellipse",
    "Face",
    "FrameGraph",
    "FrameMember",
    "FrameNode",
    "FrameVolume",
    "Line",
    "Point",
    "Polyline",
    "Solid",
    "XYZ",
    "__version__",
]
