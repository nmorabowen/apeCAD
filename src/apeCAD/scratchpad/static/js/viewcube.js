// Zero-WebGL 26-zone SVG ViewCube + ground compass ring + drag-to-orbit + 90-degree roll
// buttons (ADR 0037). Ported from apeGmshViewer/src/renderer/viewcube.ts. Replaces the second
// WebGLRenderer so apeCAD uses a single WebGL context.
import * as THREE from "three";
import { S } from "./state.js";
import {
  bindProjectionCamera,
  camera,
  fitView,
  goNamedView,
  goToView,
  lookAtScene,
  namedViewFromDir,
  releaseNamedViewForOrbit,
  syncCameras,
  syncViewMenu,
} from "./camera.js";
import { setHint } from "./cmdline.js";
import { headingBasis, orbitAroundCursor, vDot } from "./navigation.js";
import { t } from "./strings.js";
import { ISO_DIR, WORLD_UP, controls, viewUp } from "./viewport.js";

const SVG_NS = "http://www.w3.org/2000/svg";
const HALF = 0.72;
const BEVEL = 0.56;
const CX = 60;
const CY = 60;
const SCALE = 38;

// 6 faces of the Z-up cube, each defined by its outward normal `n`, tangent `u`, bitangent `v`,
// and uppercase label. Subdividing (u, v) on [-1, -BEVEL, +BEVEL, +1]^2 produces 1 center
// face zone + 4 edge bevel strips + 4 corner bevel squares = 26 discrete orientation zones.
const FACES = [
  { id: "top", label: "TOP", n: [0, 0, 1], u: [1, 0, 0], v: [0, 1, 0] },
  { id: "bottom", label: "BOTTOM", n: [0, 0, -1], u: [1, 0, 0], v: [0, -1, 0] },
  { id: "front", label: "FRONT", n: [0, -1, 0], u: [1, 0, 0], v: [0, 0, 1] },
  { id: "back", label: "BACK", n: [0, 1, 0], u: [-1, 0, 0], v: [0, 0, 1] },
  { id: "right", label: "RIGHT", n: [1, 0, 0], u: [0, 1, 0], v: [0, 0, 1] },
  { id: "left", label: "LEFT", n: [-1, 0, 0], u: [0, -1, 0], v: [0, 0, 1] },
];

const COMPASS_CARDINALS = [
  { label: "N", angle: Math.PI / 2, dir: [0, 1, 0] },
  { label: "E", angle: 0, dir: [1, 0, 0] },
  { label: "S", angle: -Math.PI / 2, dir: [0, -1, 0] },
  { label: "W", angle: Math.PI, dir: [-1, 0, 0] },
];

const cubeHost = document.getElementById("viewcube");
const svgEl = document.createElementNS(SVG_NS, "svg");
svgEl.setAttribute("viewBox", "0 0 120 120");
svgEl.setAttribute("class", "vc-svg");
if (cubeHost) {
  cubeHost.replaceChildren(svgEl);
}

function facePoint3D(face, su, sv) {
  return {
    x: (face.n[0] + su * face.u[0] + sv * face.v[0]) * HALF,
    y: (face.n[1] + su * face.u[1] + sv * face.v[1]) * HALF,
    z: (face.n[2] + su * face.u[2] + sv * face.v[2]) * HALF,
  };
}

function zoneDirKey(face, iu, iv) {
  const su = iu === 0 ? -1 : iu === 2 ? 1 : 0;
  const sv = iv === 0 ? -1 : iv === 2 ? 1 : 0;
  const dx = Math.sign(face.n[0] + su * face.u[0] + sv * face.v[0]);
  const dy = Math.sign(face.n[1] + su * face.u[1] + sv * face.v[1]);
  const dz = Math.sign(face.n[2] + su * face.u[2] + sv * face.v[2]);
  return `${dx},${dy},${dz}`;
}

function projectPoint(pt, right, up, forward) {
  const sx = CX + vDot(pt, right) * SCALE;
  const sy = CY - vDot(pt, up) * SCALE;
  const depth = -vDot(pt, forward);
  return { x: sx, y: sy, depth };
}

function ptsAttr(pts) {
  return pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
}

function snapToDirKey(dirKey) {
  const parts = String(dirKey || "").split(",").map(Number);
  if (parts.length !== 3 || parts.some((n) => !Number.isFinite(n))) return;
  const dir = new THREE.Vector3(parts[0], parts[1], parts[2]);
  if (dir.lengthSq() < 1e-6) return;
  dir.normalize();
  const name = namedViewFromDir(dir);
  if (name) {
    goNamedView(name);
    return;
  }
  S.namedView = null;
  if (S.projection === "orthographic") {
    S.projection = "parallel";
    S.useOrtho = true;
    bindProjectionCamera();
  }
  viewUp.copy(WORLD_UP);
  goToView(dir, { up: WORLD_UP.clone() });
  syncViewMenu();
}

let hoveredZoneKey = null;

export function restyleCube() {
  syncCube();
}

export function syncCube() {
  if (!svgEl) return;
  const cam = camera();
  const eye = cam.position;
  const tgt = controls.target;
  const forwardVec = {
    x: tgt.x - eye.x,
    y: tgt.y - eye.y,
    z: tgt.z - eye.z,
  };
  const { right, up, forward } = headingBasis(forwardVec, {
    x: cam.up.x,
    y: cam.up.y,
    z: cam.up.z,
  });

  const nodes = [];

  // Ground compass ring in z = -HALF * 1.05 plane.
  const ringZ = -HALF * 1.05;
  const ringR = 1.18;
  const ringPts = [];
  for (let i = 0; i <= 36; i += 1) {
    const a = (i / 36) * Math.PI * 2;
    ringPts.push(
      projectPoint({ x: Math.cos(a) * ringR, y: Math.sin(a) * ringR, z: ringZ }, right, up, forward),
    );
  }
  const polyRing = document.createElementNS(SVG_NS, "polyline");
  polyRing.setAttribute("class", "vc-ring");
  polyRing.setAttribute("points", ptsAttr(ringPts));
  nodes.push(polyRing);

  for (const card of COMPASS_CARDINALS) {
    const pos = projectPoint(
      { x: Math.cos(card.angle) * (ringR + 0.22), y: Math.sin(card.angle) * (ringR + 0.22), z: ringZ },
      right,
      up,
      forward,
    );
    const txt = document.createElementNS(SVG_NS, "text");
    txt.setAttribute("class", "vc-compass-label");
    txt.setAttribute("x", pos.x.toFixed(1));
    txt.setAttribute("y", pos.y.toFixed(1));
    txt.textContent = card.label;
    nodes.push(txt);
  }

  // Sort visible cube faces back-to-front by camera-facing dot product.
  const visibleFaces = [];
  for (const face of FACES) {
    const nVec = { x: face.n[0], y: face.n[1], z: face.n[2] };
    // Face is visible when its outward normal points toward the camera (dot(n, -forward) > 0).
    const facing = -vDot(nVec, forward);
    if (facing <= 0.02) continue;
    const center = projectPoint(facePoint3D(face, 0, 0), right, up, forward);
    visibleFaces.push({ face, depth: center.depth, center });
  }
  visibleFaces.sort((a, b) => a.depth - b.depth);

  const gridStops = [-1, -BEVEL, BEVEL, 1];
  for (const { face, center } of visibleFaces) {
    // Full face background polygon.
    const corners = [
      projectPoint(facePoint3D(face, -1, -1), right, up, forward),
      projectPoint(facePoint3D(face, 1, -1), right, up, forward),
      projectPoint(facePoint3D(face, 1, 1), right, up, forward),
      projectPoint(facePoint3D(face, -1, 1), right, up, forward),
    ];
    const bg = document.createElementNS(SVG_NS, "polygon");
    bg.setAttribute("class", "vc-face-bg");
    bg.setAttribute("points", ptsAttr(corners));
    nodes.push(bg);

    // 9 interactive bevel zones (center face + 4 edge strips + 4 corner squares).
    for (let iu = 0; iu < 3; iu += 1) {
      for (let iv = 0; iv < 3; iv += 1) {
        const u0 = gridStops[iu];
        const u1 = gridStops[iu + 1];
        const v0 = gridStops[iv];
        const v1 = gridStops[iv + 1];
        const zCorners = [
          projectPoint(facePoint3D(face, u0, v0), right, up, forward),
          projectPoint(facePoint3D(face, u1, v0), right, up, forward),
          projectPoint(facePoint3D(face, u1, v1), right, up, forward),
          projectPoint(facePoint3D(face, u0, v1), right, up, forward),
        ];
        const key = zoneDirKey(face, iu, iv);
        const zone = document.createElementNS(SVG_NS, "polygon");
        zone.setAttribute("class", key === hoveredZoneKey ? "vc-zone is-hovered" : "vc-zone");
        zone.setAttribute("points", ptsAttr(zCorners));
        zone.dataset.dirKey = key;
        nodes.push(zone);
      }
    }

    const labelEl = document.createElementNS(SVG_NS, "text");
    labelEl.setAttribute("class", "vc-face-label");
    labelEl.setAttribute("x", center.x.toFixed(1));
    labelEl.setAttribute("y", center.y.toFixed(1));
    labelEl.textContent = face.label;
    nodes.push(labelEl);
  }

  svgEl.replaceChildren(...nodes);
}

function stepRollAroundZ(deltaRad) {
  const cam = camera();
  const dx = cam.position.x - controls.target.x;
  const dy = cam.position.y - controls.target.y;
  if (S.namedView === "top" || S.namedView === "bottom" || Math.hypot(dx, dy) < 1e-3) {
    const sign = cam.position.z >= controls.target.z ? 1 : -1;
    viewUp.applyAxisAngle(WORLD_UP, deltaRad * sign).normalize();
    cam.up.copy(viewUp);
    cam.lookAt(controls.target);
    syncCameras();
    return;
  }
  releaseNamedViewForOrbit();
  const res = orbitAroundCursor({
    eye: cam.position,
    target: controls.target,
    pivot: controls.target,
    yawDeltaRad: deltaRad,
    pitchDeltaRad: 0,
  });
  cam.position.set(res.eye.x, res.eye.y, res.eye.z);
  controls.target.set(res.target.x, res.target.y, res.target.z);
  viewUp.copy(WORLD_UP);
  cam.up.copy(viewUp);
  cam.lookAt(controls.target);
  syncCameras();
}

export function bindViewCube() {
  if (!cubeHost) return;
  let dragState = null;

  svgEl.addEventListener("pointermove", (event) => {
    if (dragState) {
      const dx = event.clientX - dragState.lastX;
      const dy = event.clientY - dragState.lastY;
      dragState.moved += Math.hypot(dx, dy);
      dragState.lastX = event.clientX;
      dragState.lastY = event.clientY;
      if (dragState.moved > 4) {
        releaseNamedViewForOrbit();
        const cam = camera();
        const res = orbitAroundCursor({
          eye: cam.position,
          target: controls.target,
          pivot: controls.target,
          yawDeltaRad: -dx * 0.012,
          pitchDeltaRad: -dy * 0.012,
        });
        cam.position.set(res.eye.x, res.eye.y, res.eye.z);
        controls.target.set(res.target.x, res.target.y, res.target.z);
        viewUp.copy(WORLD_UP);
        cam.up.copy(viewUp);
        cam.lookAt(controls.target);
        syncCameras();
      }
      return;
    }
    const zone = event.target && event.target.closest ? event.target.closest("[data-dir-key]") : null;
    const nextKey = zone ? zone.dataset.dirKey : null;
    if (nextKey !== hoveredZoneKey) {
      hoveredZoneKey = nextKey;
      for (const poly of svgEl.querySelectorAll(".vc-zone")) {
        poly.classList.toggle("is-hovered", poly.dataset.dirKey === hoveredZoneKey);
      }
    }
  });

  svgEl.addEventListener("pointerleave", () => {
    hoveredZoneKey = null;
    for (const poly of svgEl.querySelectorAll(".vc-zone.is-hovered")) {
      poly.classList.remove("is-hovered");
    }
  });

  svgEl.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    event.stopPropagation();
    const zone = event.target && event.target.closest ? event.target.closest("[data-dir-key]") : null;
    dragState = {
      pointerId: event.pointerId,
      lastX: event.clientX,
      lastY: event.clientY,
      moved: 0,
      dirKey: zone ? zone.dataset.dirKey : null,
    };
    if (svgEl.setPointerCapture) {
      try { svgEl.setPointerCapture(event.pointerId); } catch (_e) { /* synthetic event */ }
    }
  });

  const endDrag = (event, cancelled = false) => {
    if (!dragState) return;
    const st = dragState;
    dragState = null;
    if (svgEl.releasePointerCapture) {
      try { svgEl.releasePointerCapture(st.pointerId); } catch (_e) { /* ignore */ }
    }
    if (!cancelled && st.moved <= 4 && st.dirKey) {
      event.preventDefault();
      event.stopPropagation();
      snapToDirKey(st.dirKey);
    }
  };

  svgEl.addEventListener("pointerup", (ev) => endDrag(ev, false));
  svgEl.addEventListener("pointercancel", (ev) => endDrag(ev, true));
  svgEl.addEventListener("lostpointercapture", (ev) => endDrag(ev, true));
  svgEl.addEventListener("contextmenu", (event) => event.preventDefault());

  const ccwBtn = document.getElementById("view-roll-ccw");
  if (ccwBtn) ccwBtn.addEventListener("click", () => stepRollAroundZ(Math.PI / 2));
  const cwBtn = document.getElementById("view-roll-cw");
  if (cwBtn) cwBtn.addEventListener("click", () => stepRollAroundZ(-Math.PI / 2));

  document.getElementById("view-iso").addEventListener("click", () => {
    S.namedView = null;
    if (S.projection === "orthographic") {
      S.projection = "parallel";
      S.useOrtho = true;
    }
    viewUp.copy(WORLD_UP);
    bindProjectionCamera();
    lookAtScene(ISO_DIR, { up: WORLD_UP.clone() });
    setHint(t("view.iso"));
  });
  document.getElementById("view-fit").addEventListener("click", () => fitView());
}
