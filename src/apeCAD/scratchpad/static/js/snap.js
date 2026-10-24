// Cursor-to-workplane hits with node snap, cover-ring snap, grid snap, ORTHO, and typed lengths.
import * as THREE from "three";
import { S } from "./state.js";
import { camera } from "./camera.js";
import { bufferLength } from "./cmdline.js";
import { gridMajorMm, gridMinorMm, nearestGridPoint, snapGrid } from "./grid.js";
import { ndcFromEvent } from "./pick.js";
import { WORLD_UP, controls, draft } from "./viewport.js";

export const SNAP_APERTURE_MM = 400;

export function nearestPoint(xyz, tolerance = SNAP_APERTURE_MM) {
  let best = null;
  let bestDist = tolerance;
  for (const point of S.sceneState.points || []) {
    const dist = Math.hypot(point.x_mm - xyz.x_mm, point.y_mm - xyz.y_mm, point.z_mm - xyz.z_mm);
    if (dist <= bestDist) {
      best = point;
      bestDist = dist;
    }
  }
  return best;
}

export function nearestCoverSnap(xyz, tolerance = SNAP_APERTURE_MM) {
  let best = null;
  let bestDist = tolerance;
  for (const guide of S.sceneState.cover_guides || []) {
    for (const ring of [guide.bar_centre_ring_mm, guide.cover_ring_mm]) {
      if (!ring) continue;
      for (const [x, y] of ring) {
        const dist = Math.hypot(x - xyz.x_mm, y - xyz.y_mm);
        if (dist <= bestDist) {
          best = { x_mm: x, y_mm: y, z_mm: 0, dist };
          bestDist = dist;
        }
      }
    }
  }
  if (best) return best;
  let segDist = tolerance * 0.5;
  for (const guide of S.sceneState.cover_guides || []) {
    const ring = guide.bar_centre_ring_mm;
    if (!ring || ring.length < 2) continue;
    for (let i = 0; i < ring.length; i += 1) {
      const [ax, ay] = ring[i];
      const [bx, by] = ring[(i + 1) % ring.length];
      const dx = bx - ax;
      const dy = by - ay;
      const len2 = dx * dx + dy * dy;
      if (len2 < 1e-6) continue;
      const u = Math.max(0, Math.min(1, ((xyz.x_mm - ax) * dx + (xyz.y_mm - ay) * dy) / len2));
      const px = ax + u * dx;
      const py = ay + u * dy;
      const dist = Math.hypot(px - xyz.x_mm, py - xyz.y_mm);
      if (dist <= segDist) {
        best = { x_mm: px, y_mm: py, z_mm: 0, dist };
        segDist = dist;
      }
    }
  }
  return best;
}

export function rawHit(event) {
  const raycaster = new THREE.Raycaster();
  raycaster.setFromCamera(ndcFromEvent(event), camera());
  const hit = new THREE.Vector3();
  if (!raycaster.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 0, 1), 0), hit)) {
    return null;
  }
  return { x_mm: hit.x, y_mm: hit.y, z_mm: 0 };
}

export function applySnaps(raw) {
  if (!raw) return null;
  if (S.snapOn) {
    const node = nearestPoint(raw);
    const coverPt = nearestCoverSnap(raw);
    const nodeDist = node ? Math.hypot(node.x_mm - raw.x_mm, node.y_mm - raw.y_mm, node.z_mm - raw.z_mm) : Infinity;
    if (coverPt && coverPt.dist <= nodeDist) {
      return { x_mm: coverPt.x_mm, y_mm: coverPt.y_mm, z_mm: 0, snap: "node" };
    }
    if (node) {
      return {
        x_mm: node.x_mm,
        y_mm: node.y_mm,
        z_mm: node.z_mm,
        entity_id: node.entity_id,
        snap: "node",
      };
    }
  }
  if (S.gridSnapOn) {
    const snapped = nearestGridPoint(raw);
    if (!snapped) return { ...raw, snap: null };
    const minor = gridMinorMm();
    const major = gridMajorMm();
    const reach = Math.max(
      SNAP_APERTURE_MM,
      minor * Math.SQRT2 / 2,
      major * Math.SQRT2 / 2,
    );
    if (snapped.dist <= reach) {
      return { x_mm: snapped.x_mm, y_mm: snapped.y_mm, z_mm: 0, snap: snapped.snap };
    }
  }
  return { ...raw, snap: null };
}

export function hitWorkplane(event) {
  return applySnaps(rawHit(event));
}

export function cursorPivot(event) {
  const cam = camera();
  const raycaster = new THREE.Raycaster();
  raycaster.setFromCamera(ndcFromEvent(event), cam);
  if (draft.children.length) {
    const hits = raycaster.intersectObjects(draft.children, true);
    for (const hit of hits) {
      if (hit.point) return { x_mm: hit.point.x, y_mm: hit.point.y, z_mm: hit.point.z };
    }
  }
  const hit = new THREE.Vector3();
  const camDist = Math.max(cam.position.distanceTo(controls.target), 1);
  if (
    Math.abs(raycaster.ray.direction.z) >= 0.15 &&
    raycaster.ray.intersectPlane(new THREE.Plane(WORLD_UP, 0), hit) &&
    hit.distanceTo(controls.target) <= camDist * 2.5
  ) {
    return { x_mm: hit.x, y_mm: hit.y, z_mm: 0 };
  }
  const look = new THREE.Vector3();
  cam.getWorldDirection(look);
  const viewPlane = new THREE.Plane().setFromNormalAndCoplanarPoint(look, controls.target);
  if (raycaster.ray.intersectPlane(viewPlane, hit)) {
    return { x_mm: hit.x, y_mm: hit.y, z_mm: hit.z };
  }
  return null;
}

function wantOrtho(event) {
  return Boolean(S.orthoOn) !== Boolean(event && event.shiftKey);
}

export function orthogonalize(from, to, event) {
  if (to && to.snap === "node") return to;
  if (!wantOrtho(event)) return to;
  const dx = to.x_mm - from.x_mm;
  const dy = to.y_mm - from.y_mm;
  if (Math.abs(dx) >= Math.abs(dy)) return { x_mm: to.x_mm, y_mm: from.y_mm, z_mm: from.z_mm };
  return { x_mm: from.x_mm, y_mm: to.y_mm, z_mm: from.z_mm };
}

export function applyLength(from, to, length) {
  if (length === null) return to;
  const dx = to.x_mm - from.x_mm;
  const dy = to.y_mm - from.y_mm;
  const dz = to.z_mm - from.z_mm;
  const dist = Math.hypot(dx, dy, dz);
  if (dist === 0) {
    return { x_mm: from.x_mm + length, y_mm: from.y_mm, z_mm: from.z_mm };
  }
  const scale = length / dist;
  return {
    x_mm: from.x_mm + dx * scale,
    y_mm: from.y_mm + dy * scale,
    z_mm: from.z_mm + dz * scale,
  };
}

export function hitHeight(event, cornerA, cornerB) {
  const typed = bufferLength();
  if (typed !== null) return typed;
  const mid = new THREE.Vector3(
    (cornerA.x_mm + cornerB.x_mm) / 2,
    (cornerA.y_mm + cornerB.y_mm) / 2,
    0,
  );
  const look = new THREE.Vector3();
  camera().getWorldDirection(look);
  look.z = 0;
  if (look.lengthSq() < 1e-8) look.set(1, 0, 0);
  look.normalize();
  const raycaster = new THREE.Raycaster();
  raycaster.setFromCamera(ndcFromEvent(event), camera());
  const hit = new THREE.Vector3();
  if (!raycaster.ray.intersectPlane(new THREE.Plane(look, -look.dot(mid)), hit)) return 3000;
  return S.gridSnapOn ? snapGrid(hit.z) : hit.z;
}
