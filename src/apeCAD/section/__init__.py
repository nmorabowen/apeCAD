"""Section mode (ADRs 0024-0026): kernel-free geometry and the closed bar vocabulary.

    geometry       signed area, orientation, simplicity, strict hull, miter offset,
                   wall-chain outline; plain Python, millimetres, XY (ADR 0004)
    designations   DESIGNATIONS, the closed metric bar vocabulary (ADR 0024 P12)

This package holds no ops and no entities. It may import apeCAD.geometry, apeCAD.entities
and apeCAD.errors, never apeCAD.draft, apeCAD.document or apeCAD.scratchpad
(tests/test_architecture.py).
"""
