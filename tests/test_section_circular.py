"""Circular steel (ADR 0039 decisions 5-6): AddCircularTie, AddBarsOnCircle, bars[].material.

Oracles: bar k of n sits at angle start + 360 k / n on the circle, so 4 bars from 0 deg are
exactly on the axes and the 45 deg bar of 8 is at r / sqrt(2); a tie's diameter is its
designation's (ADR 0024 P12); every op round-trips through `to_json` / `from_json` and undo
/ redo; delete follows ADR 0029.
"""

from __future__ import annotations

import math

import pytest

from apeCAD import XYZ, Bar, CircularTie, Document, DocumentError
from apeCAD.catalog import apply
from apeCAD.ops import AddBar, PointAt, op_to_dict


def _xy(document: Document, bar: Bar) -> tuple[float, float]:
    point = document.entity(bar.point_id)
    return (point.xyz_mm.x_mm, point.xyz_mm.y_mm)  # type: ignore[union-attr]


def _reopened(document: Document) -> Document:
    copy = Document.from_json(document.to_json())
    assert copy.to_json() == document.to_json()
    assert copy.circular_ties() == document.circular_ties()
    assert copy.bars() == document.bars()
    return copy


def test_four_bars_from_zero_sit_exactly_on_the_axes() -> None:
    doc = Document()
    bars = doc.add_bars_on_circle((1000.0, 500.0), 240.0, 4, "Ø20")
    assert [_xy(doc, b) for b in bars] == [
        (1240.0, 500.0),
        (1000.0, 740.0),
        (760.0, 500.0),
        (1000.0, 260.0),
    ]
    assert {b.diameter_mm for b in bars} == {20.0}
    assert all(b.material is None for b in bars)
    _reopened(doc)


def test_eight_bars_follow_the_angle_formula() -> None:
    doc = Document()
    bars = doc.add_bars_on_circle((0.0, 0.0), 240.0, 8, "Ø16", start_angle_deg=22.5)
    for k, bar in enumerate(bars):
        angle = math.radians(22.5 + 45.0 * k)
        x, y = _xy(doc, bar)
        assert math.isclose(x, 240.0 * math.cos(angle), rel_tol=1e-14, abs_tol=1e-12)
        assert math.isclose(y, 240.0 * math.sin(angle), rel_tol=1e-14, abs_tol=1e-12)
        assert math.isclose(math.hypot(x, y), 240.0, rel_tol=1e-14)
    second = doc.add_bars_on_circle((0.0, 0.0), 240.0, 8, "Ø16")
    x, y = _xy(doc, second[1])
    assert math.isclose(x, 240.0 / math.sqrt(2.0), rel_tol=1e-14)
    assert math.isclose(y, 240.0 / math.sqrt(2.0), rel_tol=1e-14)


def test_bars_on_circle_carry_their_material_and_replay_their_ids() -> None:
    doc = Document()
    bars = doc.add_bars_on_circle((0.0, 0.0), 240.0, 6, "Ø20", material="A630-420H")
    assert {b.material for b in bars} == {"A630-420H"}
    reopened = _reopened(doc)
    assert tuple(b.entity_id for b in reopened.bars()) == tuple(b.entity_id for b in bars)


@pytest.mark.parametrize(
    ("kwargs", "fragment"),
    [
        ({"count": 1}, "count must be 2 or more"),
        ({"radius_mm": 0.0}, "radius_mm must be positive"),
        ({"designation": "#5"}, "#5"),
        ({"material": "  "}, "non-empty name"),
    ],
)
def test_bad_circle_layouts_are_refused(kwargs: dict[str, object], fragment: str) -> None:
    args: dict[str, object] = {"radius_mm": 240.0, "count": 6, "designation": "Ø20"}
    args.update(kwargs)
    doc = Document()
    with pytest.raises(DocumentError, match=fragment):
        doc.add_bars_on_circle((0.0, 0.0), **args)  # type: ignore[arg-type]
    assert doc.ops() == ()


def test_a_bar_material_is_additive_in_the_ops_log() -> None:
    """An unnamed bar's op JSON has no `material` key, so v1 logs and fixtures are unchanged."""
    assert "material" not in op_to_dict(AddBar(x_mm=0.0, y_mm=0.0, designation="Ø16"))
    named = AddBar(x_mm=0.0, y_mm=0.0, designation="Ø16", material="A630-420H")
    assert op_to_dict(named)["material"] == "A630-420H"
    doc = Document()
    bar = doc.add_bar(60.0, 60.0, "Ø16", material="A630-420H")
    assert bar.material == "A630-420H"
    assert _reopened(doc).entity(bar.entity_id) == bar


def test_a_spiral_shares_a_circle_face_centre() -> None:
    doc = Document()
    face = doc.add_section_face(
        "concrete", "H30", center_id=PointAt(XYZ(0.0, 0.0, 0.0)), radius_mm=300.0
    )
    spiral = doc.add_circular_tie("spiral", PointAt(XYZ(0.0, 0.0, 0.0)), 255.0, "Ø10", 75.0)
    assert spiral == CircularTie(
        entity_id=spiral.entity_id,
        kind="spiral",
        center_id=face.boundary.center_id,  # type: ignore[union-attr]
        centerline_radius_mm=255.0,
        designation="Ø10",
        diameter_mm=10.0,
        pitch_mm=75.0,
    )
    hoop = doc.add_circular_tie("hoop", 1, 255.0, "Ø12", 100.0, label="H1")
    assert hoop.kind == "hoop" and hoop.diameter_mm == 12.0
    assert doc.brep().children[spiral.entity_id] == (1,)
    assert _reopened(doc).entity_by_label("H1") == hoop


@pytest.mark.parametrize(
    ("args", "fragment"),
    [
        (("helix", PointAt(XYZ(0, 0, 0)), 255.0, "Ø10", 75.0), "kind must be one of"),
        (("spiral", PointAt(XYZ(0, 0, 0)), -1.0, "Ø10", 75.0), "centerline_radius_mm"),
        (("spiral", PointAt(XYZ(0, 0, 0)), 255.0, "Ø10", 0.0), "pitch_mm"),
        (("spiral", PointAt(XYZ(0, 0, 0)), 255.0, "Ø11", 75.0), "Ø11"),
        (("spiral", PointAt(XYZ(0, 0, 500)), 255.0, "Ø10", 75.0), "z = 0"),
    ],
)
def test_bad_circular_ties_are_refused(args: tuple[object, ...], fragment: str) -> None:
    doc = Document()
    with pytest.raises(DocumentError, match=fragment):
        doc.add_circular_tie(*args)  # type: ignore[arg-type]
    assert doc.ops() == ()


def test_a_tie_centre_cannot_be_a_bar_point() -> None:
    doc = Document()
    bar = doc.add_bar(0.0, 0.0, "Ø16")
    with pytest.raises(DocumentError, match="belongs to bar"):
        doc.add_circular_tie("spiral", bar.point_id, 255.0, "Ø10", 75.0)


def test_delete_cascade_keeps_a_shared_centre() -> None:
    doc = Document()
    face = doc.add_section_face(
        "concrete", "H30", center_id=PointAt(XYZ(0.0, 0.0, 0.0)), radius_mm=300.0
    )
    spiral = doc.add_circular_tie("spiral", 1, 255.0, "Ø10", 75.0)
    doc.delete([face.entity_id])
    assert doc.circular_ties() == (spiral,) and len(doc.points()) == 1
    doc.delete([spiral.entity_id])
    assert doc.points() == ()
    doc.undo()
    doc.undo()
    assert len(doc.section_faces()) == 1 and len(doc.circular_ties()) == 1


def test_deleting_the_centre_takes_the_tie() -> None:
    doc = Document()
    doc.add_circular_tie("spiral", PointAt(XYZ(0.0, 0.0, 0.0)), 255.0, "Ø10", 75.0)
    doc.delete([1])
    assert doc.circular_ties() == () and doc.points() == ()


def test_moves_and_arrays_carry_ties_and_bars() -> None:
    doc = Document()
    spiral = doc.add_circular_tie("spiral", PointAt(XYZ(0.0, 0.0, 0.0)), 255.0, "Ø10", 75.0)
    doc.translate([spiral.entity_id], 1000.0, 0.0)
    assert doc.entity(spiral.center_id).xyz_mm == XYZ(1000.0, 0.0, 0.0)  # type: ignore[union-attr]
    doc.array_linear([spiral.entity_id], 2000.0, 0.0, copies=2)
    centres = sorted(doc.entity(t.center_id).xyz_mm.x_mm for t in doc.circular_ties())  # type: ignore[union-attr]
    assert centres == [1000.0, 3000.0, 5000.0]
    _reopened(doc)


def test_each_circular_op_undoes_and_redoes() -> None:
    doc = Document()
    steps = [
        lambda: doc.add_circular_tie("spiral", PointAt(XYZ(0, 0, 0)), 255.0, "Ø10", 75.0),
        lambda: doc.add_bars_on_circle((0.0, 0.0), 240.0, 6, "Ø20", material="A630-420H"),
        lambda: doc.add_bar(0.0, 0.0, "Ø16", material="A630-420H"),
    ]
    for step in steps:
        before = doc.to_json()
        step()
        after = doc.to_json()
        doc.undo()
        assert doc.to_json() == before
        doc.redo()
        assert doc.to_json() == after


def test_catalog_apply_draws_a_spiral_column() -> None:
    """The `circular_column_spiral` case (spec "Fixtures"), drawn through `catalog.apply`."""
    doc = Document()
    apply(
        doc,
        "AddSectionFace",
        {"role": "concrete", "material": "H30", "center_id": {"xyz": [0, 0, 0]}, "radius_mm": 300},
    )
    bars = apply(
        doc,
        "AddBarsOnCircle",
        {"center_x_mm": 0, "center_y_mm": 0, "radius_mm": 240, "count": 8, "designation": "Ø20"},
    )
    assert bars.created_id is None and len(bars.added) == 16
    spiral = apply(
        doc,
        "AddCircularTie",
        {"kind": "spiral", "center_id": 1, "centerline_radius_mm": 255, "designation": "Ø10",
         "pitch_mm": 75},
    )  # fmt: skip
    assert spiral.added == (spiral.created_id,)
    assert len(doc.bars()) == 8 and len(doc.circular_ties()) == 1
    _reopened(doc)
