"""apeCAD: spatial scratchpad and intent document for ape* workflows.

The public surface is a kernel-free Python document. Humans and agents
sketch spatial intent here; apeGmsh and apeSteel consume bridges.
The drawing window, when it exists, is a client of this package — not
the source of truth.

See ``AProjects/`` for ADRs, memory, specs, and guides.
"""

from __future__ import annotations

from apeCAD.document import Document
from apeCAD.entities import (
    Arc,
    Bar,
    Bezier,
    Box,
    Circle,
    ConcreteFace,
    CoverGuide,
    Crosstie,
    Ellipse,
    Face,
    Hoop,
    LegSteel,
    Line,
    Point,
    Polyline,
    Solid,
    WallLeg,
)
from apeCAD.errors import DocumentError, OpArgumentError
from apeCAD.frame import FrameGraph, FrameMember, FrameNode, FrameVolume
from apeCAD.geometry import XYZ

__version__ = "0.0.0"

__all__ = [
    "Arc",
    "Bar",
    "Bezier",
    "Box",
    "Circle",
    "ConcreteFace",
    "CoverGuide",
    "Crosstie",
    "Document",
    "DocumentError",
    "Ellipse",
    "Face",
    "FrameGraph",
    "FrameMember",
    "FrameNode",
    "FrameVolume",
    "Hoop",
    "LegSteel",
    "Line",
    "OpArgumentError",
    "Point",
    "Polyline",
    "Solid",
    "WallLeg",
    "XYZ",
    "__version__",
]
