"""Localhost scratchpad: web canvas in front of a Python Document.

`main` loads lazily, so `from apeCAD.scratchpad.transport import handle` does not import the
HTTP server (ADR 0026: a host imports `handle` and nothing else).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apeCAD.scratchpad.server import main

__all__ = ["main"]


def __getattr__(name: str) -> object:
    if name == "main":
        from apeCAD.scratchpad.server import main

        return main
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
