// Z-up zero-roll CAD turntable math, cursor-pivot orbit, zoom-to-cursor, pan-keep-point,
// frustum dock offset, and pointer-capture cleanup (ADR 0037). Ported from
// apeGmshViewer/src/renderer/navigation.ts. Pure math functions have zero external imports
// so they run in both the browser and Node unit tests.

import { S } from "./state.js";
import { requestRender } from "./store.js";

const DEFAULT_WORLD_UP = { x: 0, y: 0, z: 1 };
const FALLBACK_RIGHT = { x: 1, y: 0, z: 0 };

function toVec3(v, fallback = DEFAULT_WORLD_UP) {
  if (!v) return { ...fallback };
  if (Array.isArray(v)) return { x: Number(v[0]) || 0, y: Number(v[1]) || 0, z: Number(v[2]) || 0 };
  if (typeof v.x_mm === "number") return { x: v.x_mm, y: v.y_mm, z: v.z_mm || 0 };
  return { x: Number(v.x) || 0, y: Number(v.y) || 0, z: Number(v.z) || 0 };
}

function vLen(a) {
  return Math.hypot(a.x, a.y, a.z);
}

function vNorm(a, fallback = DEFAULT_WORLD_UP) {
  const len = vLen(a);
  if (len < 1e-12) return { ...fallback };
  return { x: a.x / len, y: a.y / len, z: a.z / len };
}

function vSub(a, b) {
  return { x: a.x - b.x, y: a.y - b.y, z: a.z - b.z };
}

function vAdd(a, b) {
  return { x: a.x + b.x, y: a.y + b.y, z: a.z + b.z };
}

function vScale(a, s) {
  return { x: a.x * s, y: a.y * s, z: a.z * s };
}

export function vDot(a, b) {
  return a.x * b.x + a.y * b.y + a.z * b.z;
}

export function vCross(a, b) {
  return {
    x: a.y * b.z - a.z * b.y,
    y: a.z * b.x - a.x * b.z,
    z: a.x * b.y - a.y * b.x,
  };
}

// Rodrigues rotation of vector `v` around unit `axis` by `angleRad`.
export function rotateAroundAxis(v, axis, angleRad) {
  if (Math.abs(angleRad) < 1e-12) return { ...v };
  const k = vNorm(axis);
  const cos = Math.cos(angleRad);
  const sin = Math.sin(angleRad);
  const cross = vCross(k, v);
  const dot = vDot(k, v);
  return {
    x: v.x * cos + cross.x * sin + k.x * dot * (1 - cos),
    y: v.y * cos + cross.y * sin + k.y * dot * (1 - cos),
    z: v.z * cos + cross.z * sin + k.z * dot * (1 - cos),
  };
}

// Orthonormal Z-up camera basis { right, up, forward } with strictly zero roll (right.z === 0
// whenever forward is not collinear with worldUp).
export function headingBasis(forwardInput, worldUpInput = DEFAULT_WORLD_UP) {
  const worldUp = vNorm(toVec3(worldUpInput), DEFAULT_WORLD_UP);
  let forward = toVec3(forwardInput, { x: -1, y: 1, z: -1 });
  if (vLen(forward) < 1e-12) forward = { x: -1, y: 1, z: -1 };
  forward = vNorm(forward);

  const rawRight = vCross(forward, worldUp);
  const right = vLen(rawRight) < 1e-4 ? { ...FALLBACK_RIGHT } : vNorm(rawRight);
  const up = vNorm(vCross(right, forward), DEFAULT_WORLD_UP);
  return { right, up, forward };
}

// Orbit `eye` and `target` around an arbitrary 3-D world `pivot` point using Z-up turntable
// yaw (around +Z) and camera-right pitch (clamped off the +-Z poles by `poleMarginRad`),
// keeping `pivot` stationary on screen (ADR 0037).
export function orbitAroundCursor({
  eye,
  target,
  up = DEFAULT_WORLD_UP,
  pivot = target,
  yawDeltaRad = 0,
  pitchDeltaRad = 0,
  poleMarginRad = 0.04,
}) {
  const eyeV = toVec3(eye);
  const targetV = toVec3(target);
  const pivotV = toVec3(pivot ?? targetV);
  const worldUp = vNorm(toVec3(up), DEFAULT_WORLD_UP);

  const offset = vSub(eyeV, targetV);
  const dist = Math.max(vLen(offset), 1e-3);
  const dirFromTarget = vScale(offset, 1 / dist);

  // Current polar angle phi in [0, PI] from +Z worldUp.
  const cosPhi = Math.max(-1, Math.min(1, vDot(dirFromTarget, worldUp)));
  const phi = Math.acos(cosPhi);
  const clampedPhi = Math.max(
    poleMarginRad,
    Math.min(Math.PI - poleMarginRad, phi + pitchDeltaRad),
  );
  const actualPitch = clampedPhi - phi;

  const { right } = headingBasis(vSub(targetV, eyeV), worldUp);
  const eyePitched = rotateAroundAxis(vSub(eyeV, pivotV), right, actualPitch);
  const targetPitched = rotateAroundAxis(vSub(targetV, pivotV), right, actualPitch);
  const eyeYawed = rotateAroundAxis(eyePitched, worldUp, yawDeltaRad);
  const targetYawed = rotateAroundAxis(targetPitched, worldUp, yawDeltaRad);

  const nextEye = vAdd(pivotV, eyeYawed);
  const nextTarget = vAdd(pivotV, targetYawed);
  const basis = headingBasis(vSub(nextTarget, nextEye), worldUp);

  return {
    eye: nextEye,
    target: nextTarget,
    up: worldUp,
    right: basis.right,
    cameraUp: basis.up,
  };
}

// Translate `eye` and `target` identically in the camera plane so a dragged world point stays
// under the cursor.
export function panKeepPoint({
  eye,
  target,
  right,
  up,
  worldPerPixelX = 1,
  worldPerPixelY = 1,
  dxPx = 0,
  dyPx = 0,
}) {
  const eyeV = toVec3(eye);
  const targetV = toVec3(target);
  const rightV = vNorm(toVec3(right), FALLBACK_RIGHT);
  const upV = vNorm(toVec3(up), DEFAULT_WORLD_UP);
  const shift = vAdd(
    vScale(rightV, -dxPx * worldPerPixelX),
    vScale(upV, dyPx * worldPerPixelY),
  );
  return {
    eye: vAdd(eyeV, shift),
    target: vAdd(targetV, shift),
  };
}

// Zoom toward/away from a 3-D cursor `pivot` point so `pivot` remains at the same screen
// coordinates before and after the wheel step (ADR 0037).
export function zoomAtCursor({
  eye,
  target,
  pivot = target,
  zoomFactor = 1,
  minDistance = 0.5,
  maxDistance = 2_000_000,
}) {
  const eyeV = toVec3(eye);
  const targetV = toVec3(target);
  const pivotV = toVec3(pivot ?? targetV);
  const viewVec = vSub(eyeV, targetV);
  const dist = Math.max(vLen(viewVec), 1e-6);
  const clampedFactor = Math.max(0.05, Math.min(20, Number(zoomFactor) || 1));
  const nextDist = Math.max(minDistance, Math.min(maxDistance, dist * clampedFactor));
  const scale = nextDist / dist;

  // Homothety centered at `pivotV` with ratio `scale` keeps `pivotV` at the same NDC ray.
  const nextEye = vAdd(pivotV, vScale(vSub(eyeV, pivotV), scale));
  const nextTarget = vAdd(pivotV, vScale(vSub(targetV, pivotV), scale));
  return {
    eye: nextEye,
    target: nextTarget,
    distance: nextDist,
    scale,
  };
}

// Compute camera.setViewOffset parameters when a side dock overlaps the stage so [0, 0] NDC
// coincides with the visual center of the unoccluded viewport (ADR 0037).
export function viewOffsetForStage(stageRect, dockRect = null) {
  const fullWidth = Math.max(1, Number(stageRect?.width) || 1);
  const fullHeight = Math.max(1, Number(stageRect?.height) || 1);
  if (!dockRect || !(dockRect.width > 0) || !(dockRect.height > 0)) {
    return { fullWidth, fullHeight, offsetX: 0, offsetY: 0, width: fullWidth, height: fullHeight };
  }
  const sLeft = Number(stageRect.left) || 0;
  const sRight = sLeft + fullWidth;
  const dLeft = Math.max(sLeft, Number(dockRect.left) || sRight);
  const dRight = Math.min(sRight, (Number(dockRect.left) || 0) + (Number(dockRect.width) || 0));
  const overlapRight = Math.max(0, dRight - dLeft);
  if (overlapRight <= 0 || overlapRight >= fullWidth * 0.8) {
    return { fullWidth, fullHeight, offsetX: 0, offsetY: 0, width: fullWidth, height: fullHeight };
  }
  return {
    fullWidth,
    fullHeight,
    offsetX: overlapRight * 0.5,
    offsetY: 0,
    width: fullWidth,
    height: fullHeight,
  };
}

// Attach wheel zoom-to-cursor and pointercancel / lostpointercapture cleanup to the viewport.
export function bindCadNavigation({
  canvas,
  camera,
  controls,
  syncCameras,
  hitWorkplane,
  hideMarquee,
}) {
  if (!canvas) return;

  const cancelActiveGesture = () => {
    if (S.marqueeOrigin && typeof hideMarquee === "function") {
      hideMarquee();
    }
    requestRender();
  };
  canvas.addEventListener("pointercancel", cancelActiveGesture);
  canvas.addEventListener("lostpointercapture", cancelActiveGesture);
  window.addEventListener("blur", cancelActiveGesture);

  canvas.addEventListener(
    "wheel",
    (event) => {
      if (event.ctrlKey || !hitWorkplane || !controls || !camera) return;
      const wp = hitWorkplane(event);
      if (!wp) return;
      const cam = camera();
      const factor = event.deltaY < 0 ? 0.92 : 1.08;
      const dist = Math.hypot(
        cam.position.x - controls.target.x,
        cam.position.y - controls.target.y,
        cam.position.z - controls.target.z,
      );
      if (dist <= (controls.minDistance || 0.5) * 1.05 && factor < 1) return;
      if (dist >= (controls.maxDistance || 2_000_000) * 0.95 && factor > 1) return;
      const blend = event.deltaY < 0 ? 0.08 : -0.08;
      const dx = (wp.x_mm - controls.target.x) * blend;
      const dy = (wp.y_mm - controls.target.y) * blend;
      if (Math.hypot(dx, dy) > 1e-2 && Math.hypot(dx, dy) < dist * 2) {
        cam.position.x += dx;
        cam.position.y += dy;
        controls.target.x += dx;
        controls.target.y += dy;
        syncCameras();
      }
    },
    { passive: true },
  );
}
