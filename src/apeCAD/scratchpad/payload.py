"""Scene payload for the scratchpad client. Derived from the document.

The v2 keys (C5 record §3 "Client data", option A) are `section_faces`, `circular_ties` and
`templates`: each item is `section/draft_v2.py`'s projector output with `entity_id` in place
of `id` (no second projector), so a `section_faces` or `circular_ties` item equals the v2
draft's, less `id` and `template_id`. A template lists its `child_ids`; its children are drawn
from their own lists (ADR 0040 D7). `concrete_faces` keeps the v1 faces only.

`warnings` is the v1 lint while v1 can say the document, else the v2 lint (C5 record §3).
"""

from __future__ import annotations

from collections.abc import Mapping

from apeCAD.document import Document
from apeCAD.entities import (
    Bar,
    CircleBoundary,
    CircularTie,
    ConcreteFace,
    CoverGuide,
    Entity,
    EntityId,
    Hoop,
    LegSteel,
    Point,
    SectionFace,
    SectionTemplate,
)
from apeCAD.errors import DocumentError
from apeCAD.render.section import rounded_ring
from apeCAD.section.cover import CoverRings, bar_centre_inset_mm, circle_cover_rings, cover_rings
from apeCAD.section.draft_v2 import (
    circular_tie_item,
    face_item,
    points_xy,
    require_v1_expressible,
    template_item,
)
from apeCAD.section.lint import lint_section_v2


def scene_payload(document: Document) -> dict[str, object]:
    entities = {i: document.entity(i) for i in sorted(document.entity_ids())}
    return {
        "document": document.to_dict(),
        "points": [
            {
                "entity_id": point.entity_id,
                "x_mm": point.xyz_mm.x_mm,
                "y_mm": point.xyz_mm.y_mm,
                "z_mm": point.xyz_mm.z_mm,
                "label": point.label,
            }
            for point in document.points()
        ],
        "lines": [
            {
                "entity_id": line.entity_id,
                "start_id": line.start_id,
                "end_id": line.end_id,
                "label": line.label,
            }
            for line in document.lines()
        ],
        "polylines": [
            {
                "entity_id": polyline.entity_id,
                "point_ids": list(polyline.point_ids),
                "closed": polyline.closed,
                "label": polyline.label,
            }
            for polyline in document.polylines()
        ],
        "boxes": [
            {
                "entity_id": box.entity_id,
                "origin_xyz_mm": list(box.origin_xyz_mm.to_tuple()),
                "size_xyz_mm": list(box.size_xyz_mm.to_tuple()),
                "label": box.label,
            }
            for box in document.boxes()
        ],
        "faces": [
            {
                "entity_id": face.entity_id,
                "point_ids": list(face.point_ids),
                "label": face.label,
            }
            for face in document.faces()
        ],
        "solids": [
            {
                "entity_id": solid.entity_id,
                "face_id": solid.face_id,
                "distance_mm": solid.distance_mm,
                "direction_xyz": list(solid.direction_xyz.to_tuple()),
                "cap_id": solid.cap_id,
                "wall_ids": list(solid.wall_ids),
                "label": solid.label,
            }
            for solid in document.solids()
        ],
        "circles": [
            {
                "entity_id": circle.entity_id,
                "center_id": circle.center_id,
                "radius_mm": circle.radius_mm,
                "label": circle.label,
            }
            for circle in document.circles()
        ],
        "arcs": [
            {
                "entity_id": arc.entity_id,
                "start_id": arc.start_id,
                "mid_id": arc.mid_id,
                "end_id": arc.end_id,
                "label": arc.label,
            }
            for arc in document.arcs()
        ],
        "ellipses": [
            {
                "entity_id": ellipse.entity_id,
                "center_id": ellipse.center_id,
                "radius_x_mm": ellipse.radius_x_mm,
                "radius_y_mm": ellipse.radius_y_mm,
                "label": ellipse.label,
            }
            for ellipse in document.ellipses()
        ],
        "beziers": [
            {
                "entity_id": bezier.entity_id,
                "point_ids": list(bezier.point_ids),
                "label": bezier.label,
            }
            for bezier in document.beziers()
        ],
        # Section mode (ADR 0024): intent lists; the 3-D client draws them (js/section.js).
        "concrete_faces": [
            {
                "entity_id": face.entity_id,
                "point_ids": list(face.point_ids),
                "material": face.material,
                "role": face.role,
                "label": face.label,
            }
            for face in document.concrete_faces()
        ],
        "bars": [
            {
                "entity_id": bar.entity_id,
                "point_id": bar.point_id,
                "designation": bar.designation,
                "diameter_mm": bar.diameter_mm,
                "material": bar.material,  # v2 (ADR 0039 D6); None is the consumer's default
                "label": bar.label,
            }
            for bar in document.bars()
        ],
        "hoops": [
            {
                "entity_id": hoop.entity_id,
                "bar_ids": list(hoop.bar_ids),
                "designation": hoop.designation,
                "diameter_mm": hoop.diameter_mm,
                "spacing_mm": hoop.spacing_mm,
                "hooks": hoop.hooks,
                "display_ring_mm": _hoop_display_ring(document, hoop),
                "label": hoop.label,
            }
            for hoop in document.hoops()
        ],
        "crossties": [
            {
                "entity_id": tie.entity_id,
                "bar_a_id": tie.bar_a_id,
                "bar_b_id": tie.bar_b_id,
                "designation": tie.designation,
                "diameter_mm": tie.diameter_mm,
                "spacing_mm": tie.spacing_mm,
                "hooks": tie.hooks,
                "label": tie.label,
            }
            for tie in document.crossties()
        ],
        "wall_legs": [
            {
                "entity_id": leg.entity_id,
                "start_id": leg.start_id,
                "end_id": leg.end_id,
                "thickness_mm": leg.thickness_mm,
                "face_id": leg.face_id,
                "horizontal": _steel(leg.horizontal),
                "label": leg.label,
            }
            for leg in document.wall_legs()
        ],
        "cover_guides": [_cover_guide(document, guide) for guide in document.cover_guides()],
        **_v2_lists(entities),
        "warnings": _warnings(document, entities),
        "tags": {name: sorted(ids) for name, ids in document.tags().items()},
        "brep": document.brep().to_payload(),
    }


def _v2_lists(entities: Mapping[EntityId, Entity]) -> dict[str, object]:
    """The v2 scene keys, from the v2 draft's item projectors, in entity-id order."""
    ordered = list(entities.values())
    xy = points_xy(ordered)
    return {
        "section_faces": [
            {"entity_id": e.entity_id, **face_item(e, xy)}
            for e in ordered
            if isinstance(e, SectionFace)
        ],
        "circular_ties": [
            {"entity_id": e.entity_id, **circular_tie_item(e, xy)}
            for e in ordered
            if isinstance(e, CircularTie)
        ],
        "templates": [
            {
                "entity_id": e.entity_id,
                **{k: v for k, v in template_item(e).items() if k != "id"},
                "child_ids": list(e.child_ids),
                "label": e.label,
            }
            for e in ordered
            if isinstance(e, SectionTemplate)
        ],
    }


def _warnings(document: Document, entities: Mapping[EntityId, Entity]) -> list[dict[str, object]]:
    """v1's lint while v1 can say the document, so a v1 scene is unchanged; else v2's."""
    try:
        require_v1_expressible(entities, "the scene")
    except DocumentError:
        return [warning.to_dict() for warning in lint_section_v2(entities)]
    return [warning.to_dict() for warning in document.section_lint()]


def _hoop_display_ring(document: Document, hoop: Hoop) -> list[list[float]]:
    centres: list[tuple[float, float, float]] = []
    offsets: list[float] = []
    for bar_id in hoop.bar_ids:
        bar = document.entity(bar_id)
        assert isinstance(bar, Bar)
        point = document.entity(bar.point_id)
        assert isinstance(point, Point)
        centres.append(point.xyz_mm.to_tuple())
        offsets.append(bar.diameter_mm / 2.0 + hoop.diameter_mm / 2.0)
    if len(centres) < 2:
        return []
    return [[p[0], p[1]] for p in rounded_ring(centres, offsets, None)]


def _steel(steel: LegSteel | None) -> dict[str, object] | None:
    if steel is None:
        return None
    return {
        "designation": steel.designation,
        "spacing_mm": steel.spacing_mm,
        "curtains": steel.curtains,
    }


def _cover_guide(document: Document, guide: CoverGuide) -> dict[str, object]:
    """The guide with its rings, computed here in Python (plan C2: never in the client)."""
    rings = _guide_rings(document, guide)
    return {
        "entity_id": guide.entity_id,
        "face_id": guide.face_id,
        "cover_mm": guide.cover_mm,
        "tie_diameter_mm": guide.tie_diameter_mm,
        "bar_diameter_mm": guide.bar_diameter_mm,
        "bar_centre_inset_mm": bar_centre_inset_mm(guide),
        "cover_ring_mm": _ring(rings.cover_ring_mm),
        "bar_centre_ring_mm": _ring(rings.bar_centre_ring_mm),
        "reason": rings.reason,
        "label": guide.label,
    }


def _xy(document: Document, point_id: int) -> tuple[float, float]:
    point = document.entity(point_id)
    assert isinstance(point, Point)
    return (point.xyz_mm.x_mm, point.xyz_mm.y_mm)


def _guide_rings(document: Document, guide: CoverGuide) -> CoverRings:
    """A v1 face or a v2 concrete ring insets by mitred offset; a v2 circle by radius."""
    face = document.entity(guide.face_id)
    if isinstance(face, SectionFace):
        boundary = face.boundary
        if isinstance(boundary, CircleBoundary):
            center = _xy(document, boundary.center_id)
            return circle_cover_rings(center, boundary.radius_mm, guide)
        point_ids = boundary.point_ids
    else:
        assert isinstance(face, ConcreteFace)
        point_ids = face.point_ids
    return cover_rings([_xy(document, point_id) for point_id in point_ids], guide)


def _ring(ring: list[tuple[float, float]] | None) -> list[list[float]] | None:
    return None if ring is None else [[x, y] for x, y in ring]
