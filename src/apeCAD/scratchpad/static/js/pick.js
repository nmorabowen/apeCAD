// Picking entities under the cursor: screen-space distance for points and curves, rays for
// faces and solids, per selection filter (ADR 0015-0018).
import * as THREE from "three";
import { S } from "./state.js";
import {
  FILTER_KINDS,
  catalog,
  curveWorldPoints,
  findRecord,
  gatherPoints,
  indexBrep,
  offsetPoints,
  owningSolidId,
  profileWorldPoints,
  rootId,
} from "./brep.js";
import { camera } from "./camera.js";
import { xyzMm } from "./draw.js";
import { rayInsidePlan, sectionShape } from "./section.js";
import { canvas, draft } from "./viewport.js";

const PICK_POINT_PX = 12;
const PICK_LINE_PX = 14;

function pickDrawnEntity(event) {
  const raycaster = new THREE.Raycaster();
  raycaster.params.Line = { threshold: 160 };
  raycaster.setFromCamera(ndcFromEvent(event), camera());
  const hits = raycaster.intersectObjects(draft.children, true);
  for (const hit of hits) {
    let object = hit.object;
    while (object) {
      if (object.userData && object.userData.entityId != null) {
        return { id: object.userData.entityId, distance: hit.distance };
      }
      object = object.parent;
    }
  }
  return null;
}

function projectedClient(point) {
  const p = xyzMm(point);
  const vector = new THREE.Vector3(p.x_mm, p.y_mm, p.z_mm).project(camera());
  if (!Number.isFinite(vector.x) || !Number.isFinite(vector.y) || !Number.isFinite(vector.z)) {
    return null;
  }
  if (vector.z < -1 || vector.z > 1) return null;
  const rect = canvas.getBoundingClientRect();
  return {
    x: rect.left + (vector.x * 0.5 + 0.5) * rect.width,
    y: rect.top + (-vector.y * 0.5 + 0.5) * rect.height,
  };
}

function pixelDist(event, point) {
  const projected = projectedClient(point);
  if (!projected) return Number.POSITIVE_INFINITY;
  return Math.hypot(projected.x - event.clientX, projected.y - event.clientY);
}

function pixelDistSegment(event, a, b) {
  const pa = projectedClient(a);
  const pb = projectedClient(b);
  if (!pa || !pb) return Number.POSITIVE_INFINITY;
  const dx = pb.x - pa.x;
  const dy = pb.y - pa.y;
  const len2 = dx * dx + dy * dy;
  if (len2 < 1e-6) return Math.hypot(event.clientX - pa.x, event.clientY - pa.y);
  let t = ((event.clientX - pa.x) * dx + (event.clientY - pa.y) * dy) / len2;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(event.clientX - (pa.x + t * dx), event.clientY - (pa.y + t * dy));
}

function pixelDistLoop(event, pts, closed) {
  if (!pts.length) return Number.POSITIVE_INFINITY;
  let best = Number.POSITIVE_INFINITY;
  const last = closed ? pts.length : Math.max(pts.length - 1, 0);
  for (let i = 0; i < last; i += 1) {
    best = Math.min(best, pixelDistSegment(event, pts[i], pts[(i + 1) % pts.length]));
  }
  return best;
}

function eventRay(event) {
  const raycaster = new THREE.Raycaster();
  raycaster.setFromCamera(ndcFromEvent(event), camera());
  return raycaster.ray;
}

function rayHitsPolygon(ray, pts) {
  if (!pts || pts.length < 3) return null;
  const a = new THREE.Vector3(pts[0].x_mm, pts[0].y_mm, pts[0].z_mm || 0);
  const target = new THREE.Vector3();
  let best = null;
  for (let i = 1; i < pts.length - 1; i += 1) {
    const b = new THREE.Vector3(pts[i].x_mm, pts[i].y_mm, pts[i].z_mm || 0);
    const c = new THREE.Vector3(pts[i + 1].x_mm, pts[i + 1].y_mm, pts[i + 1].z_mm || 0);
    if (ray.intersectTriangle(a, b, c, false, target)) {
      const dist = ray.origin.distanceTo(target);
      if (best == null || dist < best) best = dist;
    }
  }
  return best;
}

function pickClosestPoint(event) {
  let best = null;
  for (const point of S.sceneState.points || []) {
    if (S.hiddenIds.has(point.entity_id)) continue;
    const dist = pixelDist(event, point);
    if (dist <= PICK_POINT_PX && (!best || dist < best.dist)) {
      best = { id: point.entity_id, dist };
    }
  }
  return best ? best.id : null;
}

function pickClosestLine(event) {
  let best = null;
  for (const row of catalog()) {
    if (!FILTER_KINDS.line.has(row.kind) || S.hiddenIds.has(row.id)) continue;
    const shape = curveWorldPoints(row);
    if (!shape) continue;
    const dist = pixelDistLoop(event, shape.pts, shape.closed);
    if (dist <= PICK_LINE_PX && (!best || dist < best.dist)) {
      best = { id: row.id, dist };
    }
  }
  return best ? best.id : null;
}

function facePickPolygons() {
  const polygons = [];
  for (const row of catalog()) {
    if (!FILTER_KINDS.face.has(row.kind) || S.hiddenIds.has(row.id)) continue;
    const pts = profileWorldPoints(row);
    if (pts.length >= 3) polygons.push({ id: row.id, pts });
  }
  for (const solid of S.sceneState.solids || []) {
    if (S.hiddenIds.has(solid.entity_id)) continue;
    const cap = findRecord(solid.cap_id);
    if (cap && FILTER_KINDS.face.has(cap.kind)) continue;
    const profile = findRecord(solid.face_id);
    if (!profile || (profile.kind !== "Circle" && profile.kind !== "Ellipse")) continue;
    if (S.hiddenIds.has(profile.id)) continue;
    const pts = profileWorldPoints(profile);
    if (pts.length < 3) continue;
    const dir = solid.direction_xyz || [0, 0, 1];
    const length = Math.hypot(dir[0] || 0, dir[1] || 0, dir[2] || 0) || 1;
    const scale = solid.distance_mm / length;
    polygons.push({
      id: profile.id,
      pts: offsetPoints(pts, (dir[0] || 0) * scale, (dir[1] || 0) * scale, (dir[2] || 0) * scale),
    });
  }
  return polygons;
}

function pickClosestFace(event) {
  const ray = eventRay(event);
  let best = null;
  for (const poly of facePickPolygons()) {
    const rayDist = rayHitsPolygon(ray, poly.pts);
    const edgeDist = pixelDistLoop(event, poly.pts, true);
    let score = null;
    if (rayDist != null) score = { ray: rayDist, px: 0 };
    else if (edgeDist <= PICK_LINE_PX) score = { ray: Number.POSITIVE_INFINITY, px: edgeDist };
    if (!score) continue;
    if (
      !best
      || score.ray < best.ray - 1e-6
      || (Math.abs(score.ray - best.ray) < 1e-6 && score.px < best.px)
    ) {
      best = { id: poly.id, ray: score.ray, px: score.px };
    }
  }
  return best ? best.id : null;
}

function rayHitsSolid(ray, row) {
  const pts = gatherPoints(row);
  if (!pts.length) return null;
  const box = new THREE.Box3();
  for (const point of pts) {
    box.expandByPoint(new THREE.Vector3(point.x_mm, point.y_mm, point.z_mm || 0));
  }
  if (box.isEmpty()) return null;
  const target = new THREE.Vector3();
  if (!ray.intersectBox(box, target)) return null;
  return ray.origin.distanceTo(target);
}

function pickClosestSolid(event) {
  const drawn = pickDrawnEntity(event);
  if (drawn) {
    const row = findRecord(drawn.id);
    if (row && FILTER_KINDS.solid.has(row.kind)) return drawn.id;
    const owner = owningSolidId(drawn.id);
    if (owner != null) return owner;
  }
  const ray = eventRay(event);
  let best = null;
  for (const row of catalog()) {
    if (!FILTER_KINDS.solid.has(row.kind) || S.hiddenIds.has(row.id)) continue;
    const dist = rayHitsSolid(ray, row);
    if (dist != null && (!best || dist < best.dist)) best = { id: row.id, dist };
  }
  return best ? best.id : null;
}

// Section entities pick as themselves (ADR 0024): a bar under the cursor first, then the
// nearest line (tie, leg axis, cover ring or concrete outline), then the concrete inside.
function pickClosestSection(event) {
  const ray = eventRay(event);
  let best = null;
  const consider = (id, tier, dist) => {
    if (!best || tier < best.tier || (tier === best.tier && dist < best.dist)) {
      best = { id, tier, dist };
    }
  };
  for (const row of catalog()) {
    if (!FILTER_KINDS.section.has(row.kind) || S.hiddenIds.has(row.id)) continue;
    const shape = sectionShape(row.kind, row.item);
    if (!shape) continue;
    const dist = pixelDistLoop(event, shape.pts, shape.closed);
    const inside = shape.closed && rayInsidePlan(ray, shape.pts) != null;
    if (row.kind === "Bar") {
      if (inside || dist <= PICK_POINT_PX) consider(row.id, 0, inside ? 0 : dist);
      continue;
    }
    if (dist <= PICK_LINE_PX) consider(row.id, 1, dist);
    else if (row.kind === "ConcreteFace" && inside) consider(row.id, 2, 0);
  }
  return best ? best.id : null;
}

function pickClosestElement(event) {
  const line = pickClosestLine(event);
  if (line != null) return rootId(line);
  const section = pickClosestSection(event);
  if (section != null) return rootId(section);
  const point = pickClosestPoint(event);
  if (point != null) return rootId(point);
  const face = pickClosestFace(event);
  if (face != null) return rootId(face);
  const solid = pickClosestSolid(event);
  if (solid != null) return rootId(solid);
  return null;
}

export function pickByFilter(event, filter) {
  indexBrep();
  if (filter === "point") return pickClosestPoint(event);
  if (filter === "line") return pickClosestLine(event);
  if (filter === "face") return pickClosestFace(event);
  if (filter === "solid") return pickClosestSolid(event);
  if (filter === "section") return pickClosestSection(event);
  return pickClosestElement(event);
}

export function pickEntity(event) {
  if (S.tool === "select") return pickByFilter(event, S.selectFilter);
  if (S.tool === "trim" || S.tool === "extend" || S.tool === "break") {
    return pickClosestLine(event);
  }
  if (S.tool === "node") {
    return pickClosestLine(event) || pickClosestFace(event);
  }
  const drawn = pickDrawnEntity(event);
  return drawn ? drawn.id : null;
}

export function ndcFromEvent(event) {
  const rect = canvas.getBoundingClientRect();
  return new THREE.Vector2(
    ((event.clientX - rect.left) / rect.width) * 2 - 1,
    -((event.clientY - rect.top) / rect.height) * 2 + 1,
  );
}
