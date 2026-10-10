"""Handlers that edit existing topology: nodes, trim, break, corners, sew (ADRs 0011, 0012)."""

from __future__ import annotations

import math
from dataclasses import replace

from apeCAD.draft.create import add_arc, add_line
from apeCAD.draft.state import DraftState
from apeCAD.draft.topology import (
    absorb_point,
    corner_of,
    offset_on_edges,
    replace_corner,
    require_on_edge,
    retarget_segment,
    simplify_loop,
    splice_edge,
    split_line,
    split_line_between,
)
from apeCAD.entities import EntityId, Face, Line, Polyline
from apeCAD.errors import DocumentError
from apeCAD.geometry import line_intersect_xy, project_on_segment
from apeCAD.ops import (
    AddArc,
    AddLine,
    BreakCrossing,
    ChamferCorner,
    FilletCorner,
    InsertNode,
    Sew,
    Simplify,
    TrimLine,
)


def insert_node(state: DraftState, op: InsertNode) -> InsertNode:
    target = state.entity(op.target_id)
    if isinstance(target, Line):
        return _insert_node_on_line(state, op, target)
    if isinstance(target, Face):
        return _insert_node_on_loop(state, op, target.point_ids, closed=True)
    if isinstance(target, Polyline):
        return _insert_node_on_loop(state, op, target.point_ids, closed=target.closed)
    raise DocumentError(
        f"entity {op.target_id} cannot take a node (need a line, face, or polyline)"
    )


def _insert_node_on_line(state: DraftState, op: InsertNode, line: Line) -> InsertNode:
    start = state.require_point(line.start_id)
    end = state.require_point(line.end_id)
    qx, qy, t = project_on_segment(
        op.x_mm,
        op.y_mm,
        start.xyz_mm.x_mm,
        start.xyz_mm.y_mm,
        end.xyz_mm.x_mm,
        end.xyz_mm.y_mm,
    )
    if t <= 1e-6 or t >= 1.0 - 1e-6:
        raise DocumentError("node cannot land on a line endpoint")
    z_mm = start.xyz_mm.z_mm + t * (end.xyz_mm.z_mm - start.xyz_mm.z_mm)
    require_on_edge(op.x_mm, op.y_mm, qx, qy)
    node_id, _created = state.point_at(qx, qy, z_mm, requested=op.entity_id)
    if node_id in (line.start_id, line.end_id):
        raise DocumentError("node cannot land on a line endpoint")
    old_end = line.end_id
    new_line_id = split_line(state, line, node_id, op.new_line_id)
    splice_edge(state, line.start_id, old_end, node_id)
    return replace(op, entity_id=node_id, new_line_id=new_line_id)


def _insert_node_on_loop(
    state: DraftState,
    op: InsertNode,
    point_ids: tuple[EntityId, ...],
    *,
    closed: bool,
) -> InsertNode:
    if len(point_ids) < 2:
        raise DocumentError("loop is too short to take a node")
    pairs = [(point_ids[i], point_ids[i + 1]) for i in range(len(point_ids) - 1)]
    if closed:
        pairs.append((point_ids[-1], point_ids[0]))
    best_i = -1
    best_dist = float("inf")
    best_q = (0.0, 0.0, 0.0)
    best_pair: tuple[EntityId, EntityId] | None = None
    for index, (start_id, end_id) in enumerate(pairs):
        start = state.require_point(start_id)
        end = state.require_point(end_id)
        qx, qy, t = project_on_segment(
            op.x_mm,
            op.y_mm,
            start.xyz_mm.x_mm,
            start.xyz_mm.y_mm,
            end.xyz_mm.x_mm,
            end.xyz_mm.y_mm,
        )
        if t <= 1e-6 or t >= 1.0 - 1e-6:
            continue
        dist = (qx - op.x_mm) ** 2 + (qy - op.y_mm) ** 2
        if dist < best_dist:
            best_dist = dist
            best_i = index
            z_mm = start.xyz_mm.z_mm + t * (end.xyz_mm.z_mm - start.xyz_mm.z_mm)
            best_q = (qx, qy, z_mm)
            best_pair = (start_id, end_id)
    if best_i < 0 or best_pair is None:
        raise DocumentError("click is not on an edge of the loop")
    require_on_edge(op.x_mm, op.y_mm, best_q[0], best_q[1])
    node_id, _created = state.point_at(best_q[0], best_q[1], best_q[2], requested=op.entity_id)
    if node_id in point_ids:
        raise DocumentError("node is already a vertex of the loop")
    ids = list(point_ids)
    ids.insert(best_i + 1, node_id)
    entity = state.entity(op.target_id)
    if isinstance(entity, Face):
        state.entities[entity.entity_id] = replace(entity, point_ids=tuple(ids))
    elif isinstance(entity, Polyline):
        state.entities[entity.entity_id] = replace(entity, point_ids=tuple(ids))
    new_line_id = split_line_between(state, best_pair[0], best_pair[1], node_id, op.new_line_id)
    splice_edge(state, best_pair[0], best_pair[1], node_id)
    return replace(op, entity_id=node_id, new_line_id=new_line_id)


def trim_line(state: DraftState, op: TrimLine) -> TrimLine:
    line = state.entity(op.line_id)
    if not isinstance(line, Line):
        raise DocumentError(f"entity {op.line_id} is not a line")
    if op.keep_id not in (line.start_id, line.end_id):
        raise DocumentError("keep_id must be an endpoint of the trimmed line")
    cut_id, _created = state.point_at(op.x_mm, op.y_mm, op.z_mm, requested=op.entity_id)
    if op.keep_id == line.start_id:
        if cut_id == line.start_id:
            raise DocumentError("trim collapsed the line to a point")
        state.entities[line.entity_id] = replace(line, end_id=cut_id)
    else:
        if cut_id == line.end_id:
            raise DocumentError("trim collapsed the line to a point")
        state.entities[line.entity_id] = replace(line, start_id=cut_id)
    return replace(op, entity_id=cut_id)


def break_crossing(state: DraftState, op: BreakCrossing) -> BreakCrossing:
    line_a = state.entity(op.line_a_id)
    line_b = state.entity(op.line_b_id)
    if not isinstance(line_a, Line) or not isinstance(line_b, Line):
        raise DocumentError("break needs two lines")
    a1 = state.require_point(line_a.start_id)
    a2 = state.require_point(line_a.end_id)
    b1 = state.require_point(line_b.start_id)
    b2 = state.require_point(line_b.end_id)
    hit = line_intersect_xy(a1.xyz_mm, a2.xyz_mm, b1.xyz_mm, b2.xyz_mm)
    if hit is None:
        raise DocumentError("those lines are parallel")
    point, t, u = hit
    if t <= 1e-6 or t >= 1.0 - 1e-6 or u <= 1e-6 or u >= 1.0 - 1e-6:
        raise DocumentError("lines do not cross")
    first = _insert_node_on_line(
        state,
        InsertNode(
            target_id=op.line_a_id,
            x_mm=point.x_mm,
            y_mm=point.y_mm,
            z_mm=0.0,
            entity_id=op.entity_id,
            new_line_id=op.new_line_a_id,
        ),
        line_a,
    )
    line_b_now = state.entity(op.line_b_id)
    if not isinstance(line_b_now, Line):
        raise DocumentError("internal error: second line vanished")
    second = _insert_node_on_line(
        state,
        InsertNode(
            target_id=op.line_b_id,
            x_mm=point.x_mm,
            y_mm=point.y_mm,
            z_mm=0.0,
            entity_id=first.entity_id,
            new_line_id=op.new_line_b_id,
        ),
        line_b_now,
    )
    return replace(
        op,
        entity_id=first.entity_id,
        new_line_a_id=first.new_line_id,
        new_line_b_id=second.new_line_id,
    )


def chamfer_corner(state: DraftState, op: ChamferCorner) -> ChamferCorner:
    prev_id, vertex_id, next_id = corner_of(state, op.target_id, op.vertex_id)
    t1, t2 = offset_on_edges(state, prev_id, vertex_id, next_id, op.distance_mm, op.distance_mm)
    start_id, _created = state.point_at(t1[0], t1[1], t1[2], requested=op.start_id)
    end_id, _unused = state.point_at(t2[0], t2[1], t2[2], requested=op.end_id)
    replace_corner(state, op.target_id, vertex_id, (start_id, end_id))
    retarget_segment(state, prev_id, vertex_id, prev_id, start_id)
    retarget_segment(state, vertex_id, next_id, end_id, next_id)
    line_op = add_line(state, AddLine(start_id=start_id, end_id=end_id, entity_id=op.entity_id))
    return replace(op, entity_id=line_op.entity_id, start_id=start_id, end_id=end_id)


def fillet_corner(state: DraftState, op: FilletCorner) -> FilletCorner:
    prev_id, vertex_id, next_id = corner_of(state, op.target_id, op.vertex_id)
    prev = state.require_point(prev_id)
    vertex = state.require_point(vertex_id)
    nxt = state.require_point(next_id)
    d1x = prev.xyz_mm.x_mm - vertex.xyz_mm.x_mm
    d1y = prev.xyz_mm.y_mm - vertex.xyz_mm.y_mm
    d2x = nxt.xyz_mm.x_mm - vertex.xyz_mm.x_mm
    d2y = nxt.xyz_mm.y_mm - vertex.xyz_mm.y_mm
    len1 = math.hypot(d1x, d1y)
    len2 = math.hypot(d2x, d2y)
    if len1 < 1e-9 or len2 < 1e-9:
        raise DocumentError("fillet edges are too short")
    d1x /= len1
    d1y /= len1
    d2x /= len2
    d2y /= len2
    dot = max(-1.0, min(1.0, d1x * d2x + d1y * d2y))
    phi = math.acos(dot)
    if phi < 1e-3 or phi > math.pi - 1e-3:
        raise DocumentError("fillet needs a convex corner")
    tangent = op.radius_mm / math.tan(phi / 2.0)
    if tangent >= len1 or tangent >= len2:
        raise DocumentError("fillet radius is too large for the edges")
    t1, t2 = offset_on_edges(state, prev_id, vertex_id, next_id, tangent, tangent)
    bis_x = d1x + d2x
    bis_y = d1y + d2y
    bis_len = math.hypot(bis_x, bis_y)
    if bis_len < 1e-9:
        raise DocumentError("fillet needs a convex corner")
    bis_x /= bis_len
    bis_y /= bis_len
    dist_c = op.radius_mm / math.sin(phi / 2.0)
    cx = vertex.xyz_mm.x_mm + bis_x * dist_c
    cy = vertex.xyz_mm.y_mm + bis_y * dist_c
    vx = vertex.xyz_mm.x_mm - cx
    vy = vertex.xyz_mm.y_mm - cy
    vlen = math.hypot(vx, vy)
    if vlen < 1e-9:
        raise DocumentError("fillet centre collapsed")
    mx = cx + vx / vlen * op.radius_mm
    my = cy + vy / vlen * op.radius_mm
    z_mm = vertex.xyz_mm.z_mm
    start_id, _a = state.point_at(t1[0], t1[1], t1[2], requested=op.start_id)
    mid_id, _b = state.point_at(mx, my, z_mm, requested=op.mid_id)
    end_id, _c = state.point_at(t2[0], t2[1], t2[2], requested=op.end_id)
    replace_corner(state, op.target_id, vertex_id, (start_id, mid_id, end_id))
    retarget_segment(state, prev_id, vertex_id, prev_id, start_id)
    retarget_segment(state, vertex_id, next_id, end_id, next_id)
    arc_op = add_arc(
        state,
        AddArc(start_id=start_id, mid_id=mid_id, end_id=end_id, entity_id=op.entity_id),
    )
    return replace(
        op,
        entity_id=arc_op.entity_id,
        start_id=start_id,
        mid_id=mid_id,
        end_id=end_id,
    )


def sew(state: DraftState, op: Sew) -> Sew:
    point_ids: list[EntityId] = []
    seen: set[EntityId] = set()
    for entity_id in op.entity_ids:
        for point_id in state.point_ids_of(state.entity(entity_id)):
            if point_id not in seen:
                seen.add(point_id)
                point_ids.append(point_id)
    parent = {point_id: point_id for point_id in point_ids}

    def find(point_id: EntityId) -> EntityId:
        while parent[point_id] != point_id:
            parent[point_id] = parent[parent[point_id]]
            point_id = parent[point_id]
        return point_id

    tol2 = op.tolerance_mm * op.tolerance_mm
    for index, left_id in enumerate(point_ids):
        left = state.require_point(left_id)
        for right_id in point_ids[index + 1 :]:
            right = state.require_point(right_id)
            dx = left.xyz_mm.x_mm - right.xyz_mm.x_mm
            dy = left.xyz_mm.y_mm - right.xyz_mm.y_mm
            dz = left.xyz_mm.z_mm - right.xyz_mm.z_mm
            if dx * dx + dy * dy + dz * dz <= tol2:
                a = find(left_id)
                b = find(right_id)
                if a != b:
                    parent[max(a, b)] = min(a, b)
    merged = False
    for point_id in point_ids:
        keeper = find(point_id)
        if keeper != point_id:
            absorb_point(state, point_id, keeper)
            merged = True
    if not merged:
        raise DocumentError("sew found no coincident points")
    return op


def simplify(state: DraftState, op: Simplify) -> Simplify:
    changed = False
    for entity_id in op.entity_ids:
        entity = state.entity(entity_id)
        if isinstance(entity, Face):
            simplified = simplify_loop(state, entity.point_ids, closed=True)
            if simplified != entity.point_ids:
                state.entities[entity_id] = replace(entity, point_ids=simplified)
                changed = True
        elif isinstance(entity, Polyline):
            simplified = simplify_loop(state, entity.point_ids, closed=entity.closed)
            if simplified != entity.point_ids:
                state.entities[entity_id] = replace(entity, point_ids=simplified)
                changed = True
    if not changed:
        raise DocumentError("simplify did not remove any vertices")
    return op
