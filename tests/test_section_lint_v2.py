"""Stage C1-S3: the v2 section lint (ADR 0039 decision 7, Errata 2 and 8.3).

Each code is checked on the smallest section that raises it and on a near miss that must
not. The order of codes is read from the spec itself.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from _section_fixtures import BUILDERS
from apeCAD import Document
from apeCAD.geometry import XYZ
from apeCAD.ops import PointAt
from apeCAD.section.lint import (
    LINT_CODES,
    LINT_CODES_V2,
    RESERVED_LINT_CODES_V2,
    LintWarning,
    lint_section,
    lint_section_v2,
)

SPEC_V2 = Path(__file__).resolve().parents[1] / "AProjects" / "specs" / "section-draft-v2.md"


def _at(x: float, y: float) -> PointAt:
    return PointAt(XYZ(float(x), float(y), 0.0))


def _rect(x0: float, y0: float, x1: float, y1: float) -> list[PointAt]:
    return [_at(x0, y0), _at(x1, y0), _at(x1, y1), _at(x0, y1)]


def _lint(doc: Document) -> tuple[LintWarning, ...]:
    return lint_section_v2({i: doc.entity(i) for i in doc.entity_ids()})


def _codes(doc: Document) -> list[str]:
    return [w.code for w in _lint(doc)]


def _only(doc: Document, code: str) -> LintWarning:
    found = [w for w in _lint(doc) if w.code == code]
    assert len(found) == 1, _lint(doc)
    return found[0]


def _column(doc: Document, *, cover: bool = True) -> int:
    """A 400 x 400 concrete SectionFace with its cover guide; returns its id."""
    face = doc.add_section_face("concrete", "C30", point_ids=_rect(-200, -200, 200, 200))
    if cover:
        doc.set_cover(face.entity_id, 40.0, 10.0, 16.0)
    return face.entity_id


def test_codes_are_the_specs_in_the_specs_order() -> None:
    text = SPEC_V2.read_text(encoding="utf-8").split("## Lint codes", 1)[1].split("\n## ", 1)[0]
    kept = re.findall(r"`([a-z-]+)`", text.split("2. The v2 codes", 1)[0])
    table = re.findall(r"^\| `([a-z-]+)` \|", text, flags=re.M)
    assert list(LINT_CODES_V2) == [*kept, *table]
    assert set(kept) <= set(LINT_CODES)
    assert set(LINT_CODES) - set(LINT_CODES_V2) == {
        "more-than-one-solid-face",
        "face-without-wall-leg",
    }
    assert RESERVED_LINT_CODES_V2 == ("steel-shape-unresolved",)


@pytest.mark.parametrize("name", sorted(BUILDERS))
def test_on_v1_sections_v2_is_v1_without_its_two_v1_only_codes(name: str) -> None:
    doc = BUILDERS[name]()
    v1 = [w for w in doc.section_lint() if w.code in LINT_CODES_V2]
    assert list(_lint(doc)) == v1


def test_clean_v2_sections_lint_clean() -> None:
    doc = Document()
    face = doc.add_section_face("concrete", "C30", center_id=_at(0, 0), radius_mm=300.0)
    doc.set_cover(face.entity_id, 40.0, 10.0, 20.0)
    doc.add_bars_on_circle((0.0, 0.0), 240.0, 8, "Ø20")
    doc.add_circular_tie("spiral", _at(0, 0), 255.0, "Ø10", 75.0)
    assert _lint(doc) == ()
    assert lint_section_v2({}) == ()


# --- same-role-overlap ----------------------------------------------------------------------


def test_two_overlapping_concrete_faces_warn() -> None:
    doc = Document()
    a = _column(doc)
    b = doc.add_section_face("concrete", "C30", point_ids=_rect(100, 100, 500, 500))
    doc.set_cover(b.entity_id, 40.0, 10.0, 16.0)
    warning = _only(doc, "same-role-overlap")
    assert warning.ids == (a, b.entity_id)
    assert "concrete faces" in warning.message


def test_a_face_filling_another_faces_hole_does_not_overlap() -> None:
    doc = Document()
    outer = _column(doc)
    doc.add_face_hole(outer, point_ids=_rect(-50, -50, 50, 50))
    inner = doc.add_section_face("concrete", "C50", point_ids=_rect(-50, -50, 50, 50))
    doc.set_cover(inner.entity_id, 10.0, 10.0, 16.0)
    assert "same-role-overlap" not in _codes(doc)


def test_touching_faces_and_faces_of_two_roles_do_not_overlap() -> None:
    doc = Document()
    _column(doc)
    side = doc.add_section_face("concrete", "C30", point_ids=_rect(200, -200, 600, 200))
    doc.set_cover(side.entity_id, 40.0, 10.0, 16.0)
    doc.add_section_face("steel", "S355", point_ids=_rect(-50, -50, 50, 50))
    doc.add_section_face("void", None, center_id=_at(-120, 0), radius_mm=40.0)
    assert "same-role-overlap" not in _codes(doc)


def test_two_overlapping_circles_warn() -> None:
    doc = Document()
    doc.add_section_face("steel", "S355", center_id=_at(0, 0), radius_mm=100.0)
    doc.add_section_face("steel", "S355", center_id=_at(150, 0), radius_mm=100.0)
    assert _codes(doc) == ["same-role-overlap"]


# --- hole-outside-face ------------------------------------------------------------------------


def test_a_hole_crossing_its_face_warns_with_its_index() -> None:
    doc = Document()
    face = _column(doc)
    doc.add_face_hole(face, center_id=_at(0, 0), radius_mm=50.0)
    doc.add_face_hole(face, point_ids=_rect(150, -20, 250, 20))
    warning = _only(doc, "hole-outside-face")
    assert warning.ids == (face,)
    assert "hole_index 1 of face" in warning.message


@pytest.mark.parametrize("radius", [200.0, 250.0])
def test_a_circle_hole_touching_or_leaving_a_circle_face_warns(radius: float) -> None:
    doc = Document()
    tube = doc.add_section_face("steel", "S355", center_id=_at(0, 0), radius_mm=200.0)
    doc.add_face_hole(tube.entity_id, center_id=_at(0, 0), radius_mm=radius)
    assert "hole-outside-face" in _codes(doc)


# --- void-outside-solid -----------------------------------------------------------------------


def test_a_void_inside_concrete_or_steel_is_covered() -> None:
    doc = Document()
    _column(doc)
    doc.add_section_face("void", None, point_ids=_rect(-100, -100, 100, 100))
    doc.add_section_face("void", None, point_ids=_rect(-200, -200, -150, 200))  # on the edge
    assert "void-outside-solid" not in _codes(doc)


def test_a_void_reaching_out_of_the_solid_warns() -> None:
    doc = Document()
    _column(doc)
    void = doc.add_section_face("void", None, point_ids=_rect(100, -50, 300, 50))
    assert _only(doc, "void-outside-solid").ids == (void.entity_id,)


def test_a_void_in_a_faces_hole_is_not_covered() -> None:
    doc = Document()
    face = _column(doc)
    doc.add_face_hole(face, center_id=_at(0, 0), radius_mm=80.0)
    doc.add_section_face("void", None, center_id=_at(0, 0), radius_mm=50.0)
    assert "void-outside-solid" in _codes(doc)


# --- bar location: one code per bar, void > steel > concrete -----------------------------------


def test_a_bar_in_a_void_inside_concrete_is_bar_in_void_alone() -> None:
    doc = Document()
    _column(doc)
    doc.add_section_face("void", None, point_ids=_rect(-100, -100, 100, 100))
    doc.add_section_face("steel", "S355", point_ids=_rect(-100, -100, 100, 100))
    bar = doc.add_bar(0.0, 0.0, "Ø16")
    assert [(w.code, w.ids) for w in _lint(doc)] == [("bar-in-void", (bar.entity_id,))]


def test_a_bar_in_steel_is_bar_in_steel_alone() -> None:
    doc = Document()
    _column(doc)
    doc.add_section_face("steel", "S355", point_ids=_rect(-100, -100, 100, 100))
    bar = doc.add_bar(0.0, 0.0, "Ø16")
    assert [(w.code, w.ids) for w in _lint(doc)] == [("bar-in-steel", (bar.entity_id,))]


def test_a_bar_whose_disc_reaches_a_void_is_outside_concrete() -> None:
    doc = Document()
    _column(doc)
    doc.add_section_face("void", None, point_ids=_rect(-100, -100, 100, 100))
    bar = doc.add_bar(105.0, 0.0, "Ø16")  # centre in concrete, 5 mm from the void, r = 8
    assert [(w.code, w.ids) for w in _lint(doc)] == [("bar-outside-concrete", (bar.entity_id,))]


def test_a_bar_in_a_hole_is_outside_concrete() -> None:
    doc = Document()
    face = _column(doc)
    doc.add_face_hole(face, center_id=_at(0, 0), radius_mm=80.0)
    bar = doc.add_bar(0.0, 0.0, "Ø16")
    assert _only(doc, "bar-outside-concrete").ids == (bar.entity_id,)


def test_a_bar_in_a_filled_tube_core_is_clean() -> None:
    doc = Document()
    core = doc.add_section_face("concrete", "C50", center_id=_at(0, 0), radius_mm=190.0)
    tube = doc.add_section_face("steel", "S355", center_id=_at(0, 0), radius_mm=200.0)
    doc.add_face_hole(tube.entity_id, center_id=_at(0, 0), radius_mm=190.0)
    doc.set_cover(core.entity_id, 30.0, 0.0, 16.0)
    doc.add_bars_on_circle((0.0, 0.0), 150.0, 6, "Ø16")
    assert _lint(doc) == ()
    doc.add_bar(195.0, 0.0, "Ø16")  # in the tube wall
    assert _codes(doc) == ["bar-in-steel"]


# --- the kept codes on v2 faces ----------------------------------------------------------------


def test_cover_guide_warning_is_for_concrete_faces_only() -> None:
    doc = Document()
    face = _column(doc, cover=False)
    doc.add_section_face("steel", "S355", point_ids=_rect(-50, -50, 50, 50))
    doc.add_section_face("void", None, center_id=_at(-120, 0), radius_mm=40.0)
    assert [(w.code, w.ids) for w in _lint(doc)] == [("face-without-cover-guide", (face,))]


def test_a_crosstie_across_a_hole_leaves_the_concrete() -> None:
    doc = Document()
    face = _column(doc)
    a = doc.add_bar(-142.0, 0.0, "Ø16").entity_id
    b = doc.add_bar(142.0, 0.0, "Ø16").entity_id
    doc.add_crosstie(a, b, "Ø10", 100.0)
    assert "crosstie-crosses-outside" not in _codes(doc)
    doc.add_face_hole(face, center_id=_at(0, 0), radius_mm=50.0)
    assert _only(doc, "crosstie-crosses-outside").ids[1:] == (a, b)


def test_a_hoop_on_a_circle_face_and_one_outside_it() -> None:
    doc = Document()
    face = doc.add_section_face("concrete", "C30", center_id=_at(0, 0), radius_mm=300.0)
    doc.set_cover(face.entity_id, 40.0, 10.0, 16.0)
    bars = [doc.add_bar(x, y, "Ø16").entity_id for x, y in ((-150, -150), (150, -150), (0, 200))]
    doc.add_hoop(bars, "Ø10", 100.0)
    assert _lint(doc) == ()
    far = doc.add_bar(0.0, 400.0, "Ø16").entity_id
    hoop = doc.add_hoop([*bars[:2], far], "Ø10", 100.0).entity_id
    assert _only(doc, "hoop-bar-not-in-face").ids == (hoop, far)


# --- circular-tie-outside-face ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("radius", "warns"),
    [(255.0, False), (300.0, True), (320.0, True)],
)
def test_a_circular_tie_must_lie_inside_a_concrete_face(radius: float, warns: bool) -> None:
    doc = Document()
    face = doc.add_section_face("concrete", "C30", center_id=_at(0, 0), radius_mm=300.0)
    doc.set_cover(face.entity_id, 40.0, 10.0, 20.0)
    tie = doc.add_circular_tie("hoop", _at(0, 0), radius, "Ø10", 100.0)
    assert (_codes(doc) == ["circular-tie-outside-face"]) is warns
    if warns:
        assert _only(doc, "circular-tie-outside-face").ids == (tie.entity_id,)


def test_a_circular_tie_crossing_a_hole_warns_and_one_around_it_does_not() -> None:
    doc = Document()
    face = _column(doc)
    doc.add_face_hole(face, center_id=_at(0, 0), radius_mm=40.0)
    doc.add_circular_tie("spiral", _at(0, 0), 140.0, "Ø10", 75.0)
    assert "circular-tie-outside-face" not in _codes(doc)
    doc.add_circular_tie("hoop", _at(0, 0), 40.0, "Ø10", 75.0)
    assert _codes(doc).count("circular-tie-outside-face") == 1


def test_a_circular_tie_in_steel_only_warns() -> None:
    doc = Document()
    doc.add_section_face("steel", "S355", center_id=_at(0, 0), radius_mm=300.0)
    doc.add_circular_tie("hoop", _at(0, 0), 200.0, "Ø10", 100.0)
    assert _codes(doc) == ["circular-tie-outside-face"]


# --- the reserved code ---------------------------------------------------------------------------


def test_steel_shape_unresolved_is_never_emitted() -> None:
    doc = Document()
    doc.add_steel_shape(_rect(0, 0, 10, 100), "S355", "plates", "PL10x100", (5.0, 50.0))
    doc.add_section_face("steel", "S355", point_ids=_rect(0, 0, 10, 100))  # an overlap, too
    assert "steel-shape-unresolved" not in _codes(doc)
    assert _codes(doc) == ["same-role-overlap"]


def test_v1_lint_is_unchanged_for_v2_entities() -> None:
    """`Document.section_lint()` stays the v1 lint; it never reads v2 faces."""
    doc = Document()
    _column(doc)
    assert lint_section({i: doc.entity(i) for i in doc.entity_ids()}) == doc.section_lint()
