from __future__ import annotations

import pytest

from apeCAD import Arc, Bezier, Circle, Document, DocumentError, Ellipse


def test_sketch_curves_round_trip() -> None:
    document = Document()
    center = document.add_point(0.0, 0.0, 0.0)
    rim = document.add_point(2000.0, 0.0, 0.0)
    mid = document.add_point(0.0, 2000.0, 0.0)
    far = document.add_point(0.0, -2000.0, 0.0)
    c1 = document.add_point(500.0, 800.0, 0.0)
    c2 = document.add_point(1500.0, 800.0, 0.0)
    circle = document.add_circle(center.entity_id, 2000.0, label="drum")
    arc = document.add_arc(rim.entity_id, mid.entity_id, far.entity_id, label="arch")
    ellipse = document.add_ellipse(center.entity_id, 3000.0, 1500.0, label="oval")
    bezier = document.add_bezier(
        (center.entity_id, c1.entity_id, c2.entity_id, rim.entity_id),
        label="spline",
    )
    assert isinstance(circle, Circle)
    assert isinstance(arc, Arc)
    assert isinstance(ellipse, Ellipse)
    assert isinstance(bezier, Bezier)
    loaded = Document.from_json(document.to_json())
    drum = loaded.entity_by_label("drum")
    oval = loaded.entity_by_label("oval")
    spline = loaded.entity_by_label("spline")
    assert isinstance(drum, Circle)
    assert isinstance(oval, Ellipse)
    assert isinstance(spline, Bezier)
    assert drum.radius_mm == 2000.0
    assert oval.radius_y_mm == 1500.0
    assert spline.point_ids == bezier.point_ids


def test_zero_circle_radius_is_rejected() -> None:
    document = Document()
    center = document.add_point(0.0, 0.0, 0.0)
    with pytest.raises(DocumentError, match="positive"):
        document.add_circle(center.entity_id, 0.0)


def test_collinear_arc_is_rejected() -> None:
    document = Document()
    a = document.add_point(0.0, 0.0, 0.0)
    b = document.add_point(1000.0, 0.0, 0.0)
    c = document.add_point(2000.0, 0.0, 0.0)
    with pytest.raises(DocumentError, match="collinear"):
        document.add_arc(a.entity_id, b.entity_id, c.entity_id)
