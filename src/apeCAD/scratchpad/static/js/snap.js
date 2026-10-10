// Cursor-to-workplane hits with node snap, grid snap, ORTHO, and typed lengths.
import * as THREE from "three";
import { S } from "./state.js";
import { camera } from "./camera.js";
import { bufferLength } from "./cmdline.js";
import { gridMajorMm, gridMinorMm, nearestGridPoint, snapGrid } from "./grid.js";
import { ndcFromEvent } from "./pick.js";

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
