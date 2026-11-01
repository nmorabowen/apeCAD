"""Stage C1-S3 (ADR 0039): the `apeCAD.section-draft` v2 writer, reader and seed v2."""

from __future__ import annotations

import pytest

from apeCAD import Document, DocumentError
from apeCAD.entities import CoverGuide, WallLeg
from apeCAD.geometry import XYZ
from apeCAD.ops import PointAt

Json = dict[str, object]


def _at(x: float, y: float) -> PointAt:
    return PointAt(XYZ(x, y, 0.0))


# --- cover guides and wall legs on a v2 concrete face (comment 879) -----------------------


def test_cover_guide_and_wall_leg_on_a_v2_concrete_circle_face() -> None:
    """Regression: `_require_face` refused every v2 face, so the spec's seed could not replay."""
    doc = Document()
    face = doc.add_section_face("concrete", "concrete", center_id=_at(0, 0), radius_mm=300.0)
    guide = doc.set_cover(face.entity_id, 40.0, 10.0, 20.0)
    leg = doc.add_wall_leg(_at(-200, 0), _at(200, 0), 200.0, face_id=face.entity_id)
    assert isinstance(guide, CoverGuide) and guide.face_id == face.entity_id
    assert isinstance(leg, WallLeg) and leg.face_id == face.entity_id


@pytest.mark.parametrize("role", ["steel", "void"])
def test_cover_guide_refuses_a_steel_or_void_face_by_role(role: str) -> None:
    doc = Document()
    material = None if role == "void" else "S355"
    face = doc.add_section_face(role, material, center_id=_at(0, 0), radius_mm=300.0)
    with pytest.raises(DocumentError, match=f"is a {role} face, not a concrete face"):
        doc.set_cover(face.entity_id, 40.0, 10.0, 20.0)
    with pytest.raises(DocumentError, match=f"is a {role} face, not a concrete face"):
        doc.add_wall_leg(_at(-200, 0), _at(200, 0), 200.0, face_id=face.entity_id)
