"""Scene payload for the scratchpad client. Derived from the document."""

from __future__ import annotations

from apeCAD.document import Document


def scene_payload(document: Document) -> dict[str, object]:
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
        # Section mode (ADR 0024): intent lists; the 3-D client draws bars as dots.
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
        "tags": {name: sorted(ids) for name, ids in document.tags().items()},
        "brep": document.brep().to_payload(),
    }
