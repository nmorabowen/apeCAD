"""Section mode (ADRs 0024-0026): kernel-free geometry and the closed bar vocabulary.

    geometry       signed area, orientation, simplicity, strict hull, miter offset,
                   wall-chain outline; plain Python, millimetres, XY (ADR 0004)
    designations   DESIGNATIONS, the closed metric bar vocabulary (ADR 0024 P12)
    cover          cover and bar-centre rings of a face's cover guide
    layout         bar positions of a row or an edge layout, exact on inclines (ADR 0032)
    lint           section warnings, returned and never raised (LINT_CODES)
    draft          the section-draft's `section` block and the reopen comparison (ADR 0025)

This package holds no ops and no entities. It may import apeCAD.geometry, apeCAD.entities
and apeCAD.errors, never apeCAD.draft, apeCAD.document or apeCAD.scratchpad
(tests/test_architecture.py).
"""
