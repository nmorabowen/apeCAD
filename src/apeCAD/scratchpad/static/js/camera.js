// Camera behaviour: perspective/parallel lens, named axis views, animated view changes,
// framing the model, and keeping both cameras and the renderer in sync (ADR 0013).
import * as THREE from "three";
import { S } from "./state.js";
import { requestRender } from "./store.js";
import { t } from "./strings.js";
import { setHint } from "./cmdline.js";
import { gridMajorMm, gridMinorMm, syncGridLineResolution } from "./grid.js";
import {
  ISO_DIR,
  VIEW_PRESETS,
  WORLD_UP,
  canvas,
  controls,
  orthoCam,
  persp,
  renderer,
  syncAllLineResolutions,
  viewUp,
} from "./viewport.js";

export const projButton = document.getElementById("proj");
let viewSize = { w: 0, h: 0 };
let viewAnim = null;
let _cachedBoundsScene = null;
let _cachedBounds3 = null;

export function invalidateSceneBounds() {
  _cachedBoundsScene = null;
  _cachedBounds3 = null;
}

function sceneBounds3() {
  if (_cachedBoundsScene === S.sceneState) return _cachedBounds3;
  _cachedBoundsScene = S.sceneState;
  const box = new THREE.Box3();
  for (const point of S.sceneState.points || []) {
    box.expandByPoint(new THREE.Vector3(point.x_mm, point.y_mm, point.z_mm || 0));
  }
  _cachedBounds3 = box.isEmpty() ? null : box;
  return _cachedBounds3;
}

function sceneFrame() {
  const box = sceneBounds3();
  const minor = gridMinorMm();
  const major = gridMajorMm();
  if (!box) {
    return {
      center: new THREE.Vector3(0, 0, 0),
      radius: Math.max(major * 4, minor * 20, 500),
    };
  }
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const radius = Math.max(size.length() * 0.55, minor * 2, 1);
  return { center, radius };
}

export function frameDistance(radius) {
  const aspect = Math.max(canvas.clientWidth, 1) / Math.max(canvas.clientHeight, 1);
  const vFov = (persp.fov * Math.PI) / 360;
  const hFov = Math.atan(Math.tan(vFov) * aspect);
  const fov = Math.min(vFov, hFov);
  return radius / Math.max(Math.tan(fov), 0.05);
}

export function resetViewZoom() {
  orthoCam.zoom = 1;
  persp.zoom = 1;
}

export function lookAtScene(dir, extras = {}) {
  const { center, radius } = sceneFrame();
  resetViewZoom();
  const nextDir = dir && dir.lengthSq() > 1e-8 ? dir.clone() : ISO_DIR.clone();
  goToView(nextDir, {
    target: extras.target || center,
    dist: extras.dist != null ? extras.dist : frameDistance(radius),
    up: extras.up || viewUp.clone(),
    axis: Boolean(extras.axis),
  });
}

export function camera() {
  return S.useOrtho ? orthoCam : persp;
}

function applyCameraPose(position, target, up) {
  if (up) viewUp.copy(up);
  const src = camera();
  const dst = S.useOrtho ? persp : orthoCam;
  src.position.copy(position);
  src.up.copy(viewUp);
  src.lookAt(target);
  dst.position.copy(src.position);
  dst.up.copy(viewUp);
  dst.quaternion.copy(src.quaternion);
  controls.target.copy(target);
}

function updateClipPlanes(dist) {
  const radius = sceneFrame().radius;
  const span = Math.max(radius * 8, dist * 8, 10);
  persp.near = Math.max(0.1, Math.min(dist * 0.02, radius));
  persp.far = dist + span;
  orthoCam.near = -span;
  orthoCam.far = span;
  controls.minDistance = Math.max(radius * 0.02, 0.5);
  controls.maxDistance = Math.max(radius * 400, dist * 20, 1000);
}


export function updateCameraMatrices() {
  const src = camera();
  const dst = S.useOrtho ? persp : orthoCam;
  src.up.copy(viewUp);
  dst.position.copy(src.position);
  dst.quaternion.copy(src.quaternion);
  dst.up.copy(viewUp);
  const width = Math.max(canvas.clientWidth, 1);
  const height = Math.max(canvas.clientHeight, 1);
  const aspect = width / height;
  persp.aspect = aspect;
  const dist = Math.max(src.position.distanceTo(controls.target), 1);
  updateClipPlanes(dist);
  persp.updateProjectionMatrix();
  const half = Math.max(dist * Math.tan((persp.fov * Math.PI) / 360), 1);
  orthoCam.left = -half * aspect;
  orthoCam.right = half * aspect;
  orthoCam.top = half;
  orthoCam.bottom = -half;
  orthoCam.updateProjectionMatrix();
  if (width !== viewSize.w || height !== viewSize.h) {
    viewSize = { w: width, h: height };
    renderer.setSize(width, height, false);
    syncGridLineResolution();
    syncAllLineResolutions(width, height);
  }
}

export function syncCameras() {
  updateCameraMatrices();
  requestRender();
}

export function syncViewMenu() {
  const markOn = (cmd, on) => {
    const el = document.querySelector(`[data-cmd="${cmd}"]`);
    if (el) el.classList.toggle("is-on", on);
  };
  markOn("perspective", S.projection === "perspective");
  markOn("parallel", S.projection === "parallel");
  for (const name of Object.keys(VIEW_PRESETS)) {
    markOn(`view-${name}`, S.namedView === name);
  }
}

function setOrbitPoleLimit(axisView) {
  if (axisView) {
    controls.minPolarAngle = 0;
    controls.maxPolarAngle = Math.PI;
  } else {
    controls.minPolarAngle = 0.04;
    controls.maxPolarAngle = Math.PI - 0.04;
  }
}

export function bindProjectionCamera(opts = {}) {
  const dst = camera();
  dst.up.copy(viewUp);
  controls.object = dst;
  const named = S.namedView && VIEW_PRESETS[S.namedView];
  projButton.classList.toggle("active", S.useOrtho);
  projButton.title = named
    ? t("title.proj.named", { view: named.label })
    : t(S.useOrtho ? "title.proj.parallel" : "title.proj.perspective");
  setOrbitPoleLimit(Boolean(S.namedView));
  syncCameras();
  if (!opts.deferUpdate) controls.update();
  syncViewMenu();
}

export function setProjectionMode(mode, extras = {}) {
  if (mode === "orthographic") {
    goNamedView(S.namedView || "top");
    return;
  }
  const leavingNamed = S.namedView;
  S.namedView = null;
  S.projection = mode;
  S.useOrtho = mode !== "perspective";
  const hint = t(mode === "perspective" ? "view.perspective" : "view.parallel");
  if (leavingNamed) {
    viewUp.copy(WORLD_UP);
    const dir = camera().position.clone().sub(controls.target);
    bindProjectionCamera();
    goToView(dir, { up: WORLD_UP.clone() });
    if (!extras.silent) setHint(hint);
    return;
  }
  viewUp.copy(WORLD_UP);
  const src = S.useOrtho ? persp : orthoCam;
  const dst = camera();
  dst.position.copy(src.position);
  dst.quaternion.copy(src.quaternion);
  dst.up.copy(viewUp);
  bindProjectionCamera();
  if (!extras.silent) setHint(hint);
}

function setProjection(nextOrtho) {
  setProjectionMode(nextOrtho ? "parallel" : "perspective", { silent: true });
}

export function releaseNamedViewForOrbit() {
  if (!S.namedView) return;
  const leaving = S.namedView;
  S.namedView = null;
  viewAnim = null;
  if (S.projection === "orthographic") {
    S.projection = "parallel";
    S.useOrtho = true;
  }
  const target = controls.target.clone();
  const offset = camera().position.clone().sub(target);
  const dist = Math.max(offset.length(), 1);
  const dir = (leaving === "top" || leaving === "bottom")
    ? stableViewDir(offset)
    : offset.clone().normalize();
  viewUp.copy(WORLD_UP);
  applyCameraPose(target.clone().addScaledVector(dir, dist), target, WORLD_UP);
  bindProjectionCamera();
}

export function goNamedView(name) {
  const preset = VIEW_PRESETS[name];
  if (!preset) return;
  S.namedView = name;
  S.projection = "orthographic";
  S.useOrtho = true;
  viewUp.copy(preset.up);
  bindProjectionCamera({ deferUpdate: true });
  goToView(preset.dir.clone(), { up: preset.up.clone(), axis: true });
  setHint(t("view.named", { view: preset.label }));
}

export function namedViewFromDir(dir) {
  const x = Math.abs(dir.x) > 0.85 ? Math.sign(dir.x) : 0;
  const y = Math.abs(dir.y) > 0.85 ? Math.sign(dir.y) : 0;
  const z = Math.abs(dir.z) > 0.85 ? Math.sign(dir.z) : 0;
  if (Math.abs(x) + Math.abs(y) + Math.abs(z) !== 1) return null;
  if (z === 1) return "top";
  if (z === -1) return "bottom";
  if (y === -1) return "front";
  if (y === 1) return "back";
  if (x === 1) return "right";
  if (x === -1) return "left";
  return null;
}


function stableViewDir(dir) {
  const next = dir.clone().normalize();
  if (Math.hypot(next.x, next.y) < 0.04 && Math.abs(next.z) > 0.98) {
    // Nudge Top/Bottom off the orbit pole; approach from Front so +Y is screen-up.
    next.set(0, next.z > 0 ? -0.045 : 0.045, Math.sign(next.z) || 1).normalize();
  }
  return next;
}

function slerpOffset(fromOffset, toOffset, t) {
  const fromLen = fromOffset.length();
  const toLen = toOffset.length();
  const len = fromLen + (toLen - fromLen) * t;
  const fromN = fromOffset.clone().normalize();
  const toN = toOffset.clone().normalize();
  if (fromN.dot(toN) < -0.999) {
    const axis = new THREE.Vector3().crossVectors(fromN, WORLD_UP);
    if (axis.lengthSq() < 1e-8) axis.set(1, 0, 0);
    axis.normalize();
    return fromN.clone().applyAxisAngle(axis, Math.PI * t).multiplyScalar(len);
  }
  const q = new THREE.Quaternion().setFromUnitVectors(fromN, toN);
  const qT = new THREE.Quaternion().slerpQuaternions(new THREE.Quaternion(), q, t);
  return fromN.clone().applyQuaternion(qT).multiplyScalar(len);
}

export function goToView(dir, extras = {}) {
  const fromTarget = controls.target.clone();
  const toTarget = (extras.target || controls.target).clone();
  const fromOffset = camera().position.clone().sub(fromTarget);
  const dist = extras.dist != null ? extras.dist : Math.max(fromOffset.length(), 1);
  const toDir = extras.axis ? dir.clone().normalize() : stableViewDir(dir);
  const toOffset = toDir.multiplyScalar(dist);
  viewAnim = {
    fromOffset,
    toOffset,
    fromTarget,
    toTarget,
    up: (extras.up || viewUp).clone(),
    axis: Boolean(extras.axis),
    t0: performance.now(),
    ms: 220,
  };
  requestRender();
}

export function tickViewAnim() {
  if (!viewAnim) return false;
  const u = Math.min(1, (performance.now() - viewAnim.t0) / viewAnim.ms);
  const s = u * u * (3 - 2 * u);
  const target = viewAnim.fromTarget.clone().lerp(viewAnim.toTarget, s);
  const offset = slerpOffset(viewAnim.fromOffset, viewAnim.toOffset, s);
  applyCameraPose(target.clone().add(offset), target, viewAnim.up);
  updateCameraMatrices();
  if (u >= 1) {
    const endTarget = viewAnim.toTarget;
    const endPos = endTarget.clone().add(viewAnim.toOffset);
    applyCameraPose(endPos, endTarget, viewAnim.up);
    setOrbitPoleLimit(viewAnim.axis);
    updateCameraMatrices();
    controls.update();
    applyCameraPose(endPos, endTarget, viewAnim.up);
    updateCameraMatrices();
    viewAnim = null;
    return false;
  }
  return true;
}

export function fitView() {
  let dir = S.namedView ? VIEW_PRESETS[S.namedView].dir.clone() : camera().position.clone().sub(controls.target);
  if (dir.lengthSq() < 1e-8) dir.copy(ISO_DIR);
  lookAtScene(dir, { up: viewUp.clone(), axis: Boolean(S.namedView) });
}

function worldToScreen(x, y, z) {
  const vector = new THREE.Vector3(x, y, z).project(camera());
  if (vector.z > 1) return null;
  return {
    x: (vector.x * 0.5 + 0.5) * Math.max(canvas.clientWidth, 1),
    y: (-vector.y * 0.5 + 0.5) * Math.max(canvas.clientHeight, 1),
  };
}

export function initCamera() {
  window.addEventListener("resize", syncCameras);
  controls.addEventListener("change", syncCameras);
  setProjection(true);
  if (typeof ResizeObserver === "function") {
    new ResizeObserver(() => syncCameras()).observe(document.getElementById("stage"));
  }
}

