"""Graph surgery shared by edit and delete handlers: split, splice, retarget, absorb."""

from __future__ import annotations

import math
from dataclasses import replace

from apeCAD.draft.state import DraftState
from apeCAD.entities import (
    Arc,
    Bar,
    Bezier,
    Box,
    Circle,
    ConcreteFace,
    Crosstie,
    Ellipse,
    Entity,
    EntityId,
    Face,
    Hoop,
    Line,
    Point,
    Polyline,
    Solid,
)
from apeCAD.errors import DocumentError
from apeCAD.geometry import collinear_xy

EDGE_HIT_MM = 400.0


def require_on_edge(px: float, py: float, qx: float, qy: float) -> None:
    dx = qx - px
    dy = qy - py
    if dx * dx + dy * dy > EDGE_HIT_MM * EDGE_HIT_MM:
        raise DocumentError("click is not on an edge")


def referenced_ids(entity: Entity) -> frozenset[EntityId]:
    if isinstance(entity, Point):
        return frozenset()
    if isinstance(entity, Line):
        return frozenset({entity.start_id, entity.end_id})
    if isinstance(entity, (Polyline, Face, Bezier)):
        return frozenset(entity.point_ids)
    if isinstance(entity, Box):
        return frozenset()
    if isinstance(entity, Solid):
        refs = {entity.face_id}
        if entity.cap_id is not None:
            refs.add(entity.cap_id)
        refs.update(entity.wall_ids)
        return frozenset(refs)
    if isinstance(entity, (Circle, Ellipse)):
        return frozenset({entity.center_id})
    if isinstance(entity, ConcreteFace):
        return frozenset(entity.point_ids)
    if isinstance(entity, Bar):
        return frozenset({entity.point_id})
    if isinstance(entity, Hoop):
        return frozenset(entity.bar_ids)
    if isinstance(entity, Crosstie):
        return frozenset({entity.bar_a_id, entity.bar_b_id})
    return frozenset({entity.start_id, entity.mid_id, entity.end_id})


def split_line(
    state: DraftState, line: Line, node_id: EntityId, requested: EntityId | None
) -> EntityId:
    old_end = line.end_id
    state.entities[line.entity_id] = replace(line, end_id=node_id)
    new_line_id = state.allocate_id(requested)
    state.entities[new_line_id] = Line(
        entity_id=new_line_id,
        start_id=node_id,
        end_id=old_end,
        label=None,
    )
    return new_line_id


def split_line_between(
    state: DraftState,
    start_id: EntityId,
    end_id: EntityId,
    node_id: EntityId,
    requested: EntityId | None,
) -> EntityId | None:
    for entity in list(state.entities.values()):
        if not isinstance(entity, Line):
            continue
        if {entity.start_id, entity.end_id} != {start_id, end_id}:
            continue
        return split_line(state, entity, node_id, requested)
    return None


def splice_edge(
    state: DraftState, start_id: EntityId, end_id: EntityId, node_id: EntityId
) -> None:
    for entity in list(state.entities.values()):
        if isinstance(entity, Face):
            spliced = insert_on_ring(entity.point_ids, start_id, end_id, node_id, closed=True)
        elif isinstance(entity, Polyline):
            spliced = insert_on_ring(
                entity.point_ids, start_id, end_id, node_id, closed=entity.closed
            )
        else:
            continue
        if spliced is not None:
            state.entities[entity.entity_id] = replace(entity, point_ids=spliced)


def corner_of(
    state: DraftState, target_id: EntityId, vertex_id: EntityId
) -> tuple[EntityId, EntityId, EntityId]:
    target = state.entity(target_id)
    if isinstance(target, Face):
        ids = target.point_ids
        closed = True
    elif isinstance(target, Polyline):
        ids = target.point_ids
        closed = target.closed
    else:
        raise DocumentError(
            f"entity {target_id} cannot take a corner (need a face or polyline)"
        )
    try:
        index = ids.index(vertex_id)
    except ValueError as exc:
        raise DocumentError(f"vertex {vertex_id} is not on entity {target_id}") from exc
    if not closed and (index == 0 or index == len(ids) - 1):
        raise DocumentError("cannot chamfer or fillet an open polyline end")
    prev_id = ids[index - 1]
    next_id = ids[(index + 1) % len(ids)]
    return prev_id, vertex_id, next_id


def offset_on_edges(
    state: DraftState,
    prev_id: EntityId,
    vertex_id: EntityId,
    next_id: EntityId,
    distance_prev: float,
    distance_next: float,
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    prev = state.require_point(prev_id)
    vertex = state.require_point(vertex_id)
    nxt = state.require_point(next_id)
    d1x = prev.xyz_mm.x_mm - vertex.xyz_mm.x_mm
    d1y = prev.xyz_mm.y_mm - vertex.xyz_mm.y_mm
    d2x = nxt.xyz_mm.x_mm - vertex.xyz_mm.x_mm
    d2y = nxt.xyz_mm.y_mm - vertex.xyz_mm.y_mm
    len1 = math.hypot(d1x, d1y)
    len2 = math.hypot(d2x, d2y)
    if distance_prev >= len1 or distance_next >= len2:
        raise DocumentError("distance is too large for the corner edges")
    t1 = (
        vertex.xyz_mm.x_mm + d1x / len1 * distance_prev,
        vertex.xyz_mm.y_mm + d1y / len1 * distance_prev,
        vertex.xyz_mm.z_mm,
    )
    t2 = (
        vertex.xyz_mm.x_mm + d2x / len2 * distance_next,
        vertex.xyz_mm.y_mm + d2y / len2 * distance_next,
        vertex.xyz_mm.z_mm,
    )
    return t1, t2


def replace_corner(
    state: DraftState,
    target_id: EntityId,
    vertex_id: EntityId,
    new_ids: tuple[EntityId, ...],
) -> None:
    entity = state.entity(target_id)
    if not isinstance(entity, (Face, Polyline)):
        raise DocumentError(f"entity {target_id} is not a face or polyline")
    ids = list(entity.point_ids)
    index = ids.index(vertex_id)
    ids[index : index + 1] = list(new_ids)
    if len(set(ids)) != len(ids):
        raise DocumentError("corner replacement produced duplicate vertices")
    state.entities[target_id] = replace(entity, point_ids=tuple(ids))


def retarget_segment(
    state: DraftState,
    old_start: EntityId,
    old_end: EntityId,
    new_start: EntityId,
    new_end: EntityId,
) -> None:
    for entity in list(state.entities.values()):
        if not isinstance(entity, Line):
            continue
        if {entity.start_id, entity.end_id} != {old_start, old_end}:
            continue
        start_id = new_start if entity.start_id == old_start else new_end
        end_id = new_end if entity.end_id == old_end else new_start
        if entity.start_id == old_end and entity.end_id == old_start:
            start_id = new_end
            end_id = new_start
        if start_id == end_id:
            continue
        state.entities[entity.entity_id] = replace(entity, start_id=start_id, end_id=end_id)


def absorb_point(state: DraftState, old_id: EntityId, new_id: EntityId) -> None:
    """Rewire every reference from old_id to new_id, then drop old_id."""
    if old_id == new_id:
        return
    owned = state.bar_points()
    for point_id in (old_id, new_id):
        if point_id in owned:
            raise DocumentError(
                f"point {point_id} belongs to bar {owned[point_id]}; a bar owns its point"
            )
    for entity in list(state.entities.values()):
        if isinstance(entity, Line):
            start_id = new_id if entity.start_id == old_id else entity.start_id
            end_id = new_id if entity.end_id == old_id else entity.end_id
            if start_id == end_id:
                del state.entities[entity.entity_id]
            elif (start_id, end_id) != (entity.start_id, entity.end_id):
                state.entities[entity.entity_id] = replace(
                    entity, start_id=start_id, end_id=end_id
                )
        elif isinstance(entity, (Face, Polyline, Bezier)):
            ids = tuple(
                new_id if point_id == old_id else point_id for point_id in entity.point_ids
            )
            compacted = compact_ids(
                ids,
                closed=isinstance(entity, Face)
                or (isinstance(entity, Polyline) and entity.closed),
            )
            if isinstance(entity, Face) and len(compacted) < 3:
                raise DocumentError("sew would collapse a face")
            if isinstance(entity, Polyline) and len(compacted) < 2:
                raise DocumentError("sew would collapse a polyline")
            if isinstance(entity, Bezier) and len(compacted) != 4:
                raise DocumentError("sew would collapse a Bézier")
            if compacted != entity.point_ids:
                state.entities[entity.entity_id] = replace(entity, point_ids=compacted)
        elif isinstance(entity, (Circle, Ellipse)) and entity.center_id == old_id:
            state.entities[entity.entity_id] = replace(entity, center_id=new_id)
        elif isinstance(entity, Arc):
            start_id = new_id if entity.start_id == old_id else entity.start_id
            mid_id = new_id if entity.mid_id == old_id else entity.mid_id
            end_id = new_id if entity.end_id == old_id else entity.end_id
            state.entities[entity.entity_id] = replace(
                entity, start_id=start_id, mid_id=mid_id, end_id=end_id
            )
    old = state.entities.pop(old_id)
    if isinstance(old, Point) and old.label is not None:
        keeper = state.entity(new_id)
        if isinstance(keeper, Point) and keeper.label is None:
            state.entities[new_id] = replace(keeper, label=old.label)
            state.labels[old.label] = new_id
        elif old.label in state.labels:
            del state.labels[old.label]


def simplify_loop(
    state: DraftState, point_ids: tuple[EntityId, ...], *, closed: bool
) -> tuple[EntityId, ...]:
    ids = list(point_ids)
    minimum = 3 if closed else 2
    changed = True
    while changed and len(ids) > minimum:
        changed = False
        count = len(ids)
        last = count if closed else count - 1
        start = 0 if closed else 1
        for index in range(start, last):
            prev_id = ids[index - 1]
            vertex_id = ids[index]
            next_id = ids[(index + 1) % count]
            if vertex_is_shared(state, vertex_id, point_ids):
                continue
            prev = state.require_point(prev_id)
            vertex = state.require_point(vertex_id)
            nxt = state.require_point(next_id)
            if collinear_xy(
                prev.xyz_mm.x_mm,
                prev.xyz_mm.y_mm,
                vertex.xyz_mm.x_mm,
                vertex.xyz_mm.y_mm,
                nxt.xyz_mm.x_mm,
                nxt.xyz_mm.y_mm,
            ):
                ids.pop(index)
                changed = True
                break
    if len(ids) < minimum:
        raise DocumentError("simplify would collapse the loop")
    return tuple(ids)


def vertex_is_shared(
    state: DraftState, vertex_id: EntityId, owner_ids: tuple[EntityId, ...]
) -> bool:
    for entity in state.entities.values():
        if isinstance(entity, (Face, Polyline)) and entity.point_ids != owner_ids:
            if vertex_id in entity.point_ids:
                return True
        if isinstance(entity, Line) and vertex_id in (entity.start_id, entity.end_id):
            other = entity.end_id if entity.start_id == vertex_id else entity.start_id
            if other not in owner_ids:
                return True
    return False


def insert_on_ring(
    point_ids: tuple[EntityId, ...],
    start_id: EntityId,
    end_id: EntityId,
    node_id: EntityId,
    *,
    closed: bool,
) -> tuple[EntityId, ...] | None:
    if node_id in point_ids:
        return None
    ids = list(point_ids)
    last = len(ids) if closed else len(ids) - 1
    for index in range(last):
        a = ids[index]
        b = ids[(index + 1) % len(ids)]
        if (a, b) == (start_id, end_id) or (a, b) == (end_id, start_id):
            ids.insert(index + 1, node_id)
            return tuple(ids)
    return None


def loop_from_lines(lines: list[Line]) -> tuple[EntityId, ...]:
    if len(lines) < 3:
        raise DocumentError("face from lines needs at least three lines")
    adj: dict[EntityId, list[EntityId]] = {}
    for line in lines:
        adj.setdefault(line.start_id, []).append(line.end_id)
        adj.setdefault(line.end_id, []).append(line.start_id)
    for neighbors in adj.values():
        if len(neighbors) != 2:
            raise DocumentError("selected lines must form one closed loop")
    start = lines[0].start_id
    loop: list[EntityId] = [start]
    prev: EntityId | None = None
    current = start
    for _ in range(len(lines)):
        neighbors = adj[current]
        nxt = neighbors[0] if neighbors[0] != prev else neighbors[1]
        if nxt == start:
            break
        loop.append(nxt)
        prev = current
        current = nxt
    else:
        raise DocumentError("selected lines must form one closed loop")
    if len(loop) != len(lines):
        raise DocumentError("selected lines must form one closed loop")
    return tuple(loop)


def chain_from_segments(
    segments: list[tuple[EntityId, EntityId]],
) -> tuple[tuple[EntityId, ...], bool]:
    if len(segments) < 2:
        raise DocumentError("join needs at least two segments")
    adj: dict[EntityId, list[EntityId]] = {}
    seen: set[frozenset[EntityId]] = set()
    for start_id, end_id in segments:
        if start_id == end_id:
            raise DocumentError("join cannot use a zero-length segment")
        edge = frozenset((start_id, end_id))
        if edge in seen:
            raise DocumentError("join found a duplicated segment")
        seen.add(edge)
        adj.setdefault(start_id, []).append(end_id)
        adj.setdefault(end_id, []).append(start_id)
    if any(len(neighbors) > 2 for neighbors in adj.values()):
        raise DocumentError("join needs a single chain (a branch was selected)")
    ends = [node for node, neighbors in adj.items() if len(neighbors) == 1]
    if len(ends) == 2:
        closed = False
        start = ends[0]
    elif len(ends) == 0:
        if any(len(neighbors) != 2 for neighbors in adj.values()):
            raise DocumentError("selected entities are not one connected chain")
        closed = True
        start = segments[0][0]
    else:
        raise DocumentError("selected entities are not one connected chain")
    chain: list[EntityId] = [start]
    prev: EntityId | None = None
    current = start
    for _ in range(len(segments)):
        nxt: EntityId | None = None
        for candidate in adj[current]:
            if candidate != prev:
                nxt = candidate
                break
        if nxt is None:
            break
        if closed and nxt == start:
            break
        chain.append(nxt)
        prev = current
        current = nxt
    if closed:
        if len(chain) != len(segments):
            raise DocumentError("selected entities are not one connected chain")
    elif len(chain) != len(segments) + 1:
        raise DocumentError("selected entities are not one connected chain")
    return tuple(chain), closed


def compact_ids(point_ids: tuple[EntityId, ...], *, closed: bool) -> tuple[EntityId, ...]:
    if not point_ids:
        return point_ids
    compacted: list[EntityId] = [point_ids[0]]
    for point_id in point_ids[1:]:
        if point_id != compacted[-1]:
            compacted.append(point_id)
    if closed and len(compacted) > 1 and compacted[0] == compacted[-1]:
        compacted.pop()
    return tuple(compacted)
