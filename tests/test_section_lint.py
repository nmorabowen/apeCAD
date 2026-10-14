"""Section lint (plan stage C3): one case per code, plus a clean section.

Warnings are returned, never raised, and every drawing that triggers one is accepted.
"""

from __future__ import annotations

from apeCAD import Document
from apeCAD.entities import Bar, ConcreteFace, LegSteel
from apeCAD.geometry import XYZ
from apeCAD.ops import PointAt
from apeCAD.section.lint import LINT_CODES, LintWarning, lint_section

STEEL = LegSteel("Ø10", 200.0, 2)


def _at(*xy: tuple[float, float]) -> list[PointAt]:
    return [PointAt(XYZ(x, y, 0.0)) for x, y in xy]


def _clean() -> tuple[Document, ConcreteFace, list[Bar]]:
    """A 2000 x 300 wall: one leg, a cover guide, 12 boundary bars, a hoop and a crosstie."""
    doc = Document()
    face = doc.add_wall_chain(_at((0.0, 150.0), (2000.0, 150.0)), 300.0, "H30", horizontal=STEEL)
    doc.set_cover(face.entity_id, 40.0, 10.0, 20.0)
    bars: list[Bar] = []
    for edge, count in ((0, 5), (1, 3), (2, 5), (3, 3)):
        bars.extend(doc.add_bars_along_edge(face.entity_id, edge, "Ø20", count=count))
    doc.add_hoop([bar.entity_id for bar in bars], "Ø10", 100.0)
    doc.add_crosstie(bars[2].entity_id, bars[8].entity_id, "Ø10", 100.0)  # (1000, 60)-(1000, 240)
    return doc, face, bars


def _codes(doc: Document) -> set[str]:
    return {warning.code for warning in doc.section_lint()}


def _only(doc: Document, code: str) -> LintWarning:
    found = [w for w in doc.section_lint() if w.code == code]
    assert len(found) == 1, doc.section_lint()
    return found[0]


def test_the_codes_are_the_plan_list() -> None:
    assert LINT_CODES == (
        "bar-overlap",
        "bar-outside-concrete",
        "hoop-bar-not-in-face",
        "crosstie-crosses-outside",
        "face-without-cover-guide",
        "face-without-wall-leg",
        "inclined-wall-leg",
        "tie-mismatch-in-core",
        "more-than-one-solid-face",
    )


def test_a_clean_section_has_no_warnings() -> None:
    doc, _, bars = _clean()
    assert len(bars) == 12
    assert doc.section_lint() == ()
    assert Document().section_lint() == ()


def test_bar_overlap() -> None:
    doc, _, bars = _clean()
    twin = doc.add_bar(1000.5, 60.0, "Ø20")  # accepted: bars own their points (ADR 0024)
    warning = _only(doc, "bar-overlap")
    assert warning.ids == (bars[2].entity_id, twin.entity_id)
    assert _codes(doc) == {"bar-overlap"}


def test_bar_outside_concrete() -> None:
    doc, _, _ = _clean()
    stray = doc.add_bar(1000.0, 295.0, "Ø20")  # centre inside, but it pokes out of the top
    assert _only(doc, "bar-outside-concrete").ids == (stray.entity_id,)
    far = doc.add_bar(5000.0, 5000.0, "Ø20")
    ids = [w.ids for w in doc.section_lint() if w.code == "bar-outside-concrete"]
    assert ids == [(stray.entity_id,), (far.entity_id,)]


def test_hoop_bar_not_in_face() -> None:
    doc, _, bars = _clean()
    outside = doc.add_bar(1000.0, 600.0, "Ø20")
    hoop = doc.add_hoop([bars[0].entity_id, bars[4].entity_id, outside.entity_id], "Ø10", 100.0)
    warning = _only(doc, "hoop-bar-not-in-face")
    assert warning.ids == (hoop.entity_id, outside.entity_id)


def test_crosstie_crosses_outside() -> None:
    doc = Document()
    face = doc.add_wall_chain(
        _at((0.0, 0.0), (2000.0, 0.0), (2000.0, 2000.0)), 300.0, "H30", horizontal=STEEL
    )
    doc.set_cover(face.entity_id, 40.0, 10.0, 20.0)
    a = doc.add_bar(100.0, 0.0, "Ø20")
    b = doc.add_bar(2000.0, 1900.0, "Ø20")
    inside = doc.add_bar(1900.0, 0.0, "Ø20")
    tie = doc.add_crosstie(a.entity_id, b.entity_id, "Ø10", 100.0)  # across the L's notch
    doc.add_crosstie(a.entity_id, inside.entity_id, "Ø10", 100.0)  # along the flange: fine
    warning = _only(doc, "crosstie-crosses-outside")
    assert warning.ids == (tie.entity_id, a.entity_id, b.entity_id)


def test_face_without_cover_guide() -> None:
    doc = Document()
    face = doc.add_wall_chain(_at((0.0, 0.0), (1000.0, 0.0)), 250.0, "H30", horizontal=STEEL)
    assert _only(doc, "face-without-cover-guide").ids == (face.entity_id,)
    assert _codes(doc) == {"face-without-cover-guide"}


def test_face_without_wall_leg() -> None:
    doc = Document()
    face = doc.add_section_outline(
        _at((0.0, 0.0), (1000.0, 0.0), (1000.0, 250.0), (0.0, 250.0)), "H30"
    )
    doc.set_cover(face.entity_id, 40.0, 10.0, 20.0)
    assert _only(doc, "face-without-wall-leg").ids == (face.entity_id,)
    assert _codes(doc) == {"face-without-wall-leg"}


def test_inclined_wall_leg() -> None:
    doc = Document()
    face = doc.add_wall_chain(_at((0.0, 0.0), (1000.0, 600.0)), 250.0, "H30", horizontal=STEEL)
    doc.set_cover(face.entity_id, 40.0, 10.0, 20.0)
    leg = doc.wall_legs()[0]
    warning = _only(doc, "inclined-wall-leg")
    assert warning.ids == (leg.entity_id,)
    assert "30.9638°" in warning.message
    assert _codes(doc) == {"inclined-wall-leg"}


def test_tie_mismatch_in_core() -> None:
    doc, _, bars = _clean()
    hoop = doc.hoops()[0]
    tie = doc.add_crosstie(bars[1].entity_id, bars[9].entity_id, "Ø8", 100.0)
    slack = doc.add_crosstie(bars[3].entity_id, bars[7].entity_id, "Ø10", 150.0)
    ids = [w.ids for w in doc.section_lint() if w.code == "tie-mismatch-in-core"]
    assert ids == [(hoop.entity_id, tie.entity_id), (hoop.entity_id, slack.entity_id)]
    assert _codes(doc) == {"tie-mismatch-in-core"}


def test_more_than_one_solid_face() -> None:
    doc, face, _ = _clean()
    other = doc.add_wall_chain(
        _at((0.0, 1000.0), (1000.0, 1000.0)), 250.0, "H30", horizontal=STEEL
    )
    doc.set_cover(other.entity_id, 40.0, 10.0, 20.0)
    warning = _only(doc, "more-than-one-solid-face")
    assert warning.ids == (face.entity_id, other.entity_id)
    assert _codes(doc) == {"more-than-one-solid-face"}


def test_warnings_have_the_section_draft_shape() -> None:
    doc = Document()
    face = doc.add_section_outline(_at((0.0, 0.0), (500.0, 0.0), (500.0, 500.0)), "H30")
    rows = [w.to_dict() for w in doc.section_lint()]
    assert rows == [
        {
            "code": "face-without-cover-guide",
            "ids": [face.entity_id],
            "message": f"concrete face {face.entity_id} has no cover guide",
        },
        {
            "code": "face-without-wall-leg",
            "ids": [face.entity_id],
            "message": f"concrete face {face.entity_id} has no wall leg",
        },
    ]


def test_lint_takes_entities_not_a_document() -> None:
    doc, _, _ = _clean()
    assert lint_section({}) == ()
    assert lint_section(dict((e.entity_id, e) for e in doc.points())) == ()
