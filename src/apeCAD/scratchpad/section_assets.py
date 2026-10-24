"""Embedding kit for the 2-D section client (`static/section/`, ADR 0026 stages C6 and C9).

A host application (such as ape-web-tools HA-04) either copies the files returned by
`client_files()` at a pinned apeCAD sha or mounts `SECTION_DIR` as a static directory, and
asserts `CLIENT_API_VERSION == 1` at startup. Importing this module does not load the HTTP
server (`scratchpad.server`).
"""

from __future__ import annotations

from pathlib import Path

CLIENT_API_VERSION = 1
"""Version of the `APECADSection` browser contract (`APECADSection.API_VERSION`)."""

SECTION_DIR = Path(__file__).resolve().parent / "static" / "section"
"""Directory containing `apecad-section.js` and its sibling ES modules and stylesheet."""

_ASSET_SUFFIXES = frozenset({".js", ".css", ".html"})


def client_files() -> dict[str, Path]:
    """Map each file name in `static/section/` to its `Path` on disk."""
    if not SECTION_DIR.is_dir():
        return {}
    return {
        path.name: path
        for path in sorted(SECTION_DIR.iterdir())
        if path.is_file() and path.suffix in _ASSET_SUFFIXES
    }
