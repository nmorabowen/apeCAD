"""The `apeCAD.section-seed` v1 constants and projection (ADR 0025 decision 7 & 8, stage C10).

Re-exports `SEED_SCHEMA`, `SEED_SCHEMA_VERSION`, `project_seed_section` and
`require_seed_header` from `apeCAD.section.draft` so callers importing either module path find
the contract constants in one place.
"""

from __future__ import annotations

from apeCAD.section.draft import (
    SEED_SCHEMA,
    SEED_SCHEMA_VERSION,
    project_seed_section,
    require_seed_header,
)

__all__ = [
    "SEED_SCHEMA",
    "SEED_SCHEMA_VERSION",
    "project_seed_section",
    "require_seed_header",
]
