import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const SNAP_APERTURE_MM = 400;
const GRID_MM = 100;

const canvas = document.getElementById("view");
const status = document.getElementById("status");
const labelInput = document.getElementById("label");
const consoleLog = document.getElementById("console-log");
const consolePrompt = document.getElementById("console-prompt");
const consoleInput = document.getElementById("console-input");
const projButton = document.getElementById("proj");
const snapButton = document.getElementById("snap");
const orthoButton = document.getElementById("ortho");
const gridButton = document.getElementById("grid");
const sidesInput = document.getElementById("sides");
const coordsEl = document.getElementById("coords");
const dimsEl = document.getElementById("dims");
const treeEl = document.getElementById("tree");
const propBody = document.getElementById("prop-body");
const marqueeEl = document.getElementById("marquee");

let tool = "select";
let pending = null;
let lastPointer = null;
let selectedIds = new Set();
let cutterIds = new Set();
let marqueeOrigin = null;
let sceneState = {
  points: [], lines: [], boxes: [], polylines: [], faces: [], solids: [],
  circles: [], arcs: [], ellipses: [], beziers: [],
};
let pointerDown = null;
let useOrtho = true;
let snapOn = true;
let gridOn = true;
let orthoOn = false;
let ghostDims = [];
let committedDims = [];

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x14171c);

const WORLD_UP = new THREE.Vector3(0, 0, 1);
const ISO_DIR = new THREE.Vector3(1, -1, 1);

const persp = new THREE.PerspectiveCamera(50, 1, 10, 2_000_000);
persp.up.copy(WORLD_UP);
persp.position.set(12000, 9000, 14000);
const orthoCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 10, 2_000_000);
orthoCam.up.copy(WORLD_UP);
orthoCam.position.copy(persp.position);

const controls = new OrbitControls(orthoCam, canvas);
controls.target.set(2000, 1500, 0);
controls.mouseButtons.LEFT = -1;
controls.mouseButtons.MIDDLE = THREE.MOUSE.ROTATE;
controls.mouseButtons.RIGHT = THREE.MOUSE.PAN;
// Keep orbit off the Z pole so lookAt(up=+Z) stays well-defined after Top/Bottom.
controls.minPolarAngle = 0.04;
controls.maxPolarAngle = Math.PI - 0.04;
controls.update();

scene.add(new THREE.AmbientLight(0xffffff, 0.7));
const key = new THREE.DirectionalLight(0xffffff, 0.6);
key.position.set(1, 0.6, 1.4);
scene.add(key);
const grid = new THREE.GridHelper(40000, 40, 0x3a4450, 0x24303a);
grid.rotation.x = Math.PI / 2;
scene.add(grid);
scene.add(new THREE.AxesHelper(3000));
const draft = new THREE.Group();
const ghosts = new THREE.Group();
scene.add(draft);
scene.add(ghosts);

function camera() {
  return useOrtho ? orthoCam : persp;
}

function applyCameraPose(position, target) {
  const src = camera();
  const dst = useOrtho ? persp : orthoCam;
  src.position.copy(position);
  src.up.copy(WORLD_UP);
  src.lookAt(target);
  dst.position.copy(src.position);
  dst.up.copy(WORLD_UP);
  dst.quaternion.copy(src.quaternion);
  controls.target.copy(target);
}

function syncCameras() {
  const src = camera();
  const dst = useOrtho ? persp : orthoCam;
  src.up.copy(WORLD_UP);
  dst.position.copy(src.position);
  dst.quaternion.copy(src.quaternion);
  dst.up.copy(WORLD_UP);
  const width = Math.max(canvas.clientWidth, 1);
  const height = Math.max(canvas.clientHeight, 1);
  const aspect = width / height;
  persp.aspect = aspect;
  persp.updateProjectionMatrix();
  const dist = src.position.distanceTo(controls.target);
  const half = Math.max(dist * Math.tan((persp.fov * Math.PI) / 360), 500);
  orthoCam.left = -half * aspect;
  orthoCam.right = half * aspect;
  orthoCam.top = half;
  orthoCam.bottom = -half;
  orthoCam.updateProjectionMatrix();
  renderer.setSize(width, height, false);
}

function setProjection(nextOrtho) {
  useOrtho = nextOrtho;
  const src = useOrtho ? persp : orthoCam;
  const dst = camera();
  dst.position.copy(src.position);
  dst.quaternion.copy(src.quaternion);
  dst.up.copy(WORLD_UP);
  controls.object = dst;
  projButton.querySelector("span").textContent = useOrtho ? "Parallel" : "Perspective";
  syncCameras();
  controls.update();
}

window.addEventListener("resize", syncCameras);
setProjection(true);
if (typeof ResizeObserver === "function") {
  new ResizeObserver(() => syncCameras()).observe(document.getElementById("stage"));
}

const cubeCanvas = document.getElementById("viewcube");
const cubeRenderer = new THREE.WebGLRenderer({
  canvas: cubeCanvas,
  antialias: true,
  alpha: true,
});
cubeRenderer.setPixelRatio(window.devicePixelRatio);
cubeRenderer.setClearColor(0x000000, 0);
const cubeScene = new THREE.Scene();
const cubeCam = new THREE.OrthographicCamera(-1.35, 1.35, 1.35, -1.35, 0.1, 20);
cubeCam.up.copy(WORLD_UP);
const cubeGroup = new THREE.Group();
cubeScene.add(cubeGroup);

function makeFaceTexture(label) {
  const canvasFace = document.createElement("canvas");
  canvasFace.width = 256;
  canvasFace.height = 256;
  const ctx = canvasFace.getContext("2d");
  ctx.fillStyle = "#1d2229";
  ctx.fillRect(0, 0, 256, 256);
  ctx.strokeStyle = "#2c333c";
  ctx.lineWidth = 10;
  ctx.strokeRect(6, 6, 244, 244);
  ctx.fillStyle = "#e8edf2";
  ctx.font = "bold 52px Segoe UI, system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(label, 128, 128);
  const texture = new THREE.CanvasTexture(canvasFace);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

const CUBE_FACE = 1.12;
function addCubeFace(nx, ny, nz, ux, uy, uz, label) {
  const mesh = new THREE.Mesh(
    new THREE.PlaneGeometry(CUBE_FACE, CUBE_FACE),
    new THREE.MeshBasicMaterial({ map: makeFaceTexture(label) }),
  );
  const normal = new THREE.Vector3(nx, ny, nz);
  mesh.position.copy(normal).multiplyScalar(CUBE_FACE / 2);
  mesh.up.set(ux, uy, uz);
  mesh.lookAt(mesh.position.clone().add(normal));
  cubeGroup.add(mesh);
}
addCubeFace(1, 0, 0, 0, 0, 1, "RIGHT");
addCubeFace(-1, 0, 0, 0, 0, 1, "LEFT");
addCubeFace(0, 1, 0, 0, 0, 1, "BACK");
addCubeFace(0, -1, 0, 0, 0, 1, "FRONT");
addCubeFace(0, 0, 1, 0, 1, 0, "TOP");
addCubeFace(0, 0, -1, 0, 1, 0, "BOTTOM");

const cubePick = new THREE.Mesh(
  new THREE.BoxGeometry(CUBE_FACE, CUBE_FACE, CUBE_FACE),
  new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false }),
);
cubeGroup.add(cubePick);
cubeGroup.add(new THREE.LineSegments(
  new THREE.EdgesGeometry(cubePick.geometry),
  new THREE.LineBasicMaterial({ color: 0x6cb3ff }),
));

let viewAnim = null;

function syncCube() {
  const cam = camera();
  cubeCam.up.copy(cam.up);
  cubeCam.position.set(0, 0, 0);
  cubeCam.quaternion.copy(cam.quaternion);
  cubeCam.translateZ(3.2);
  cubeCam.updateMatrixWorld();
  const size = Math.max(cubeCanvas.clientWidth, 1);
  cubeRenderer.setSize(size, size, false);
  cubeRenderer.render(cubeScene, cubeCam);
}

function pickCube(event) {
  const rect = cubeCanvas.getBoundingClientRect();
  if (rect.width < 2 || rect.height < 2) return null;
  const ndc = new THREE.Vector2(
    ((event.clientX - rect.left) / rect.width) * 2 - 1,
    -((event.clientY - rect.top) / rect.height) * 2 + 1,
  );
  const raycaster = new THREE.Raycaster();
  raycaster.setFromCamera(ndc, cubeCam);
  const hits = raycaster.intersectObject(cubePick, true);
  return hits[0] || null;
}

function viewDirFromCubePoint(point) {
  const local = cubePick.worldToLocal(point.clone());
  const snap = (value) => (Math.abs(value) < 0.42 ? 0 : Math.sign(value));
  let x = snap(local.x);
  let y = snap(local.y);
  let z = snap(local.z);
  if (x === 0 && y === 0 && z === 0) {
    const ax = Math.abs(local.x);
    const ay = Math.abs(local.y);
    const az = Math.abs(local.z);
    if (ax >= ay && ax >= az) x = Math.sign(local.x) || 1;
    else if (ay >= az) y = Math.sign(local.y) || 1;
    else z = Math.sign(local.z) || 1;
  }
  return new THREE.Vector3(x, y, z).normalize();
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

function goToView(dir, extras = {}) {
  const fromTarget = controls.target.clone();
  const toTarget = (extras.target || controls.target).clone();
  const fromOffset = camera().position.clone().sub(fromTarget);
  const dist = extras.dist != null ? extras.dist : Math.max(fromOffset.length(), 500);
  const toOffset = stableViewDir(dir).multiplyScalar(dist);
  viewAnim = {
    fromOffset,
    toOffset,
    fromTarget,
    toTarget,
    t0: performance.now(),
    ms: 220,
  };
}

function tickViewAnim() {
  if (!viewAnim) return;
  const u = Math.min(1, (performance.now() - viewAnim.t0) / viewAnim.ms);
  const s = u * u * (3 - 2 * u);
  const target = viewAnim.fromTarget.clone().lerp(viewAnim.toTarget, s);
  const offset = slerpOffset(viewAnim.fromOffset, viewAnim.toOffset, s);
  applyCameraPose(target.clone().add(offset), target);
  syncCameras();
  if (u >= 1) {
    controls.update();
    syncCameras();
    viewAnim = null;
  }
}

function fitView() {
  const box = new THREE.Box3();
  for (const point of sceneState.points || []) {
    box.expandByPoint(new THREE.Vector3(point.x_mm, point.y_mm, point.z_mm || 0));
  }
  if (box.isEmpty()) {
    goToView(ISO_DIR, { target: new THREE.Vector3(2000, 1500, 0), dist: 18000 });
    return;
  }
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const radius = Math.max(size.length() * 0.55, 800);
  let dir = camera().position.clone().sub(controls.target);
  if (dir.lengthSq() < 1e-8) dir.copy(ISO_DIR);
  const dist = radius / Math.max(Math.tan((persp.fov * Math.PI) / 360), 0.05);
  goToView(dir, { target: center, dist });
}

let cubePointer = null;
cubeCanvas.addEventListener("pointerdown", (event) => {
  event.preventDefault();
  event.stopPropagation();
  cubePointer = { x: event.clientX, y: event.clientY };
});
cubeCanvas.addEventListener("pointerup", (event) => {
  event.preventDefault();
  event.stopPropagation();
  const origin = cubePointer;
  cubePointer = null;
  if (!origin) return;
  if (Math.hypot(event.clientX - origin.x, event.clientY - origin.y) > 6) return;
  const hit = pickCube(event);
  if (!hit) return;
  goToView(viewDirFromCubePoint(hit.point));
});
cubeCanvas.addEventListener("pointermove", (event) => {
  cubeCanvas.style.cursor = pickCube(event) ? "pointer" : "default";
});
cubeCanvas.addEventListener("contextmenu", (event) => event.preventDefault());
document.getElementById("view-iso").addEventListener("click", () => {
  goToView(ISO_DIR);
});
document.getElementById("view-fit").addEventListener("click", () => fitView());

function setHint(text) {
  const next = text && text.trim() !== "" ? text : "Command:";
  const previous = consolePrompt.textContent;
  if (previous && previous !== next && previous !== "Command:") {
    appendLog(previous);
  }
  consolePrompt.textContent = next;
  consolePrompt.title = next;
}

function appendLog(text) {
  if (!text) return;
  const last = consoleLog.lastElementChild;
  if (last && last.textContent === text) {
    consoleLog.scrollTop = consoleLog.scrollHeight;
    return;
  }
  const line = document.createElement("div");
  line.textContent = text;
  consoleLog.appendChild(line);
  while (consoleLog.childElementCount > 80) consoleLog.removeChild(consoleLog.firstChild);
  consoleLog.scrollTop = consoleLog.scrollHeight;
}

function typedText() {
  return consoleInput.value.trim();
}

function clearTyped() {
  consoleInput.value = "";
}

function setTyped(value) {
  consoleInput.value = value;
}

function isTypingField(event) {
  if (event.target === consoleInput) return false;
  const tag = event.target && event.target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA";
}

function refreshToggles() {
  snapButton.classList.toggle("active", snapOn);
  orthoButton.classList.toggle("active", orthoOn);
  gridButton.classList.toggle("active", gridOn);
  const parts = [];
  if (snapOn) parts.push("SNAP");
  if (orthoOn) parts.push("ORTHO");
  if (snapOn && gridOn) parts.push("GRID");
  const typed = activeLength();
  if (typed !== null) parts.push(`${typed} mm`);
  status.textContent = parts.join(" · ") || "free";
}

function labelValue() {
  const value = labelInput.value.trim();
  return value === "" ? null : value;
}

function fieldLength() {
  const value = Number(typedText());
  return Number.isFinite(value) && value > 0 ? value : null;
}

function activeLength() {
  return fieldLength();
}

function bufferLength() {
  return fieldLength();
}

function sidesValue() {
  const value = Number(sidesInput.value);
  if (!Number.isInteger(value) || value < 3) return 6;
  return Math.min(value, 64);
}

function arrayCount() {
  const value = Number(sidesInput.value);
  if (!Number.isInteger(value) || value < 2) return 4;
  return Math.min(value, 64);
}

function formatMm(value) {
  if (!Number.isFinite(value)) return "—";
  const rounded = Math.abs(value - Math.round(value)) < 0.05 ? Math.round(value) : Math.round(value * 10) / 10;
  return `${rounded} mm`;
}

function formatDeg(rad) {
  let deg = rad * 180 / Math.PI;
  if (deg < 0) deg += 360;
  return `${Math.round(deg * 10) / 10}°`;
}

function dist3(a, b) {
  return Math.hypot(b.x_mm - a.x_mm, b.y_mm - a.y_mm, (b.z_mm || 0) - (a.z_mm || 0));
}

function midpoint(a, b) {
  return {
    x_mm: (a.x_mm + b.x_mm) / 2,
    y_mm: (a.y_mm + b.y_mm) / 2,
    z_mm: ((a.z_mm || 0) + (b.z_mm || 0)) / 2,
  };
}

function worldToScreen(x, y, z) {
  const vector = new THREE.Vector3(x, y, z).project(camera());
  if (vector.z > 1) return null;
  return {
    x: (vector.x * 0.5 + 0.5) * Math.max(canvas.clientWidth, 1),
    y: (-vector.y * 0.5 + 0.5) * Math.max(canvas.clientHeight, 1),
  };
}

function projectDims() {
  dimsEl.innerHTML = "";
  for (const item of committedDims.concat(ghostDims)) {
    const screen = worldToScreen(item.x_mm, item.y_mm, item.z_mm || 0);
    if (!screen) continue;
    const el = document.createElement("div");
    el.className = item.ghost ? "dim" : "dim committed";
    el.textContent = item.text;
    el.style.left = `${screen.x}px`;
    el.style.top = `${screen.y}px`;
    dimsEl.appendChild(el);
  }
}

function setCoords(hit, origin) {
  if (!hit) {
    coordsEl.textContent = "X 0   Y 0   Z 0";
    return;
  }
  const x = Math.round(hit.x_mm);
  const y = Math.round(hit.y_mm);
  const z = Math.round(hit.z_mm || 0);
  let text = `X ${x}   Y ${y}   Z ${z}`;
  if (origin) {
    const dx = hit.x_mm - origin.x_mm;
    const dy = hit.y_mm - origin.y_mm;
    const length = dist3(origin, hit);
    const ang = Math.atan2(dy, dx);
    text += `    ΔX ${Math.round(dx)}   ΔY ${Math.round(dy)}    L ${formatMm(length)}    ${formatDeg(ang)}`;
  }
  coordsEl.textContent = text;
}

function addCurve(group, pts, color = 0xe8edf2, entityId = null) {
  if (pts.length < 2) return;
  const line = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(
      pts.map((point) => new THREE.Vector3(point.x_mm, point.y_mm, point.z_mm || 0)),
    ),
    new THREE.LineBasicMaterial({ color }),
  );
  mark(line, entityId);
  group.add(line);
}

function sampleCircle(center, radius, count = 64) {
  const pts = [];
  for (let i = 0; i <= count; i += 1) {
    const a = (i / count) * Math.PI * 2;
    pts.push({
      x_mm: center.x_mm + radius * Math.cos(a),
      y_mm: center.y_mm + radius * Math.sin(a),
      z_mm: center.z_mm || 0,
    });
  }
  return pts;
}

function sampleEllipse(center, rx, ry, count = 64) {
  const pts = [];
  for (let i = 0; i <= count; i += 1) {
    const a = (i / count) * Math.PI * 2;
    pts.push({
      x_mm: center.x_mm + rx * Math.cos(a),
      y_mm: center.y_mm + ry * Math.sin(a),
      z_mm: center.z_mm || 0,
    });
  }
  return pts;
}

function circumcircle(a, b, c) {
  const d = 2 * (
    a.x_mm * (b.y_mm - c.y_mm)
    + b.x_mm * (c.y_mm - a.y_mm)
    + c.x_mm * (a.y_mm - b.y_mm)
  );
  if (Math.abs(d) < 1e-8) return null;
  const a2 = a.x_mm * a.x_mm + a.y_mm * a.y_mm;
  const b2 = b.x_mm * b.x_mm + b.y_mm * b.y_mm;
  const c2 = c.x_mm * c.x_mm + c.y_mm * c.y_mm;
  const ux = (a2 * (b.y_mm - c.y_mm) + b2 * (c.y_mm - a.y_mm) + c2 * (a.y_mm - b.y_mm)) / d;
  const uy = (a2 * (c.x_mm - b.x_mm) + b2 * (a.x_mm - c.x_mm) + c2 * (b.x_mm - a.x_mm)) / d;
  return { x_mm: ux, y_mm: uy, z_mm: 0, radius: Math.hypot(ux - a.x_mm, uy - a.y_mm) };
}

function ccwDelta(from, to) {
  let delta = to - from;
  while (delta <= 0) delta += Math.PI * 2;
  while (delta > Math.PI * 2) delta -= Math.PI * 2;
  return delta;
}

function sampleArc(start, mid, end, count = 48) {
  const circ = circumcircle(start, mid, end);
  if (!circ) return [start, mid, end];
  const a0 = Math.atan2(start.y_mm - circ.y_mm, start.x_mm - circ.x_mm);
  const a1 = Math.atan2(mid.y_mm - circ.y_mm, mid.x_mm - circ.x_mm);
  const a2 = Math.atan2(end.y_mm - circ.y_mm, end.x_mm - circ.x_mm);
  const total = ccwDelta(a0, a1) < ccwDelta(a0, a2)
    ? ccwDelta(a0, a2)
    : ccwDelta(a0, a2) - Math.PI * 2;
  const pts = [];
  for (let i = 0; i <= count; i += 1) {
    const angle = a0 + total * (i / count);
    pts.push({
      x_mm: circ.x_mm + circ.radius * Math.cos(angle),
      y_mm: circ.y_mm + circ.radius * Math.sin(angle),
      z_mm: 0,
    });
  }
  return pts;
}

function sampleBezier(pts, count = 32) {
  const [p0, p1, p2, p3] = pts;
  const out = [];
  for (let i = 0; i <= count; i += 1) {
    const t = i / count;
    const u = 1 - t;
    out.push({
      x_mm: u * u * u * p0.x_mm + 3 * u * u * t * p1.x_mm + 3 * u * t * t * p2.x_mm + t * t * t * p3.x_mm,
      y_mm: u * u * u * p0.y_mm + 3 * u * u * t * p1.y_mm + 3 * u * t * t * p2.y_mm + t * t * t * p3.y_mm,
      z_mm: 0,
    });
  }
  return out;
}

function regularPolygon(center, rim, sides) {
  const radius = dist3(center, rim);
  const a0 = Math.atan2(rim.y_mm - center.y_mm, rim.x_mm - center.x_mm);
  const pts = [];
  for (let i = 0; i < sides; i += 1) {
    const angle = a0 + (i * 2 * Math.PI) / sides;
    pts.push({
      x_mm: center.x_mm + radius * Math.cos(angle),
      y_mm: center.y_mm + radius * Math.sin(angle),
      z_mm: 0,
    });
  }
  return pts;
}

async function api(path, method = "GET", body = null) {
  const options = { method, headers: { "Content-Type": "application/json" } };
  if (body !== null) options.body = JSON.stringify(body);
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || response.statusText);
  return payload;
}

function createdId(payload, fallbackList) {
  if (payload.created_id != null) return payload.created_id;
  const items = payload[fallbackList] || [];
  if (!items.length) throw new Error("operation did not create an entity");
  return items[items.length - 1].entity_id;
}

function mark(object, entityId) {
  if (entityId == null) return;
  object.userData.entityId = entityId;
}

function accentFor(entityId, base) {
  if (entityId != null && selectedIds.has(entityId)) return 0x6cb3ff;
  if (entityId != null && cutterIds.has(entityId)) return 0xf0c674;
  return base;
}

function addVolume(group, origin, size, color, opacity, entityId = null) {
  const mesh = new THREE.Mesh(
    new THREE.BoxGeometry(size[0], size[1], size[2]),
    new THREE.MeshStandardMaterial({ color, transparent: true, opacity }),
  );
  mesh.position.set(origin[0] + size[0] / 2, origin[1] + size[1] / 2, origin[2] + size[2] / 2);
  mark(mesh, entityId);
  group.add(mesh);
  const edges = new THREE.LineSegments(
    new THREE.EdgesGeometry(mesh.geometry),
    new THREE.LineBasicMaterial({ color }),
  );
  edges.position.copy(mesh.position);
  mark(edges, entityId);
  group.add(edges);
}

function addCylinder(group, cx, cy, radius, originZ, height, color, opacity, entityId = null) {
  const mesh = new THREE.Mesh(
    new THREE.CylinderGeometry(radius, radius, Math.max(Math.abs(height), 1), 48),
    new THREE.MeshStandardMaterial({ color, transparent: true, opacity, side: THREE.DoubleSide }),
  );
  mesh.rotation.x = Math.PI / 2;
  mesh.position.set(cx, cy, originZ + height / 2);
  mark(mesh, entityId);
  group.add(mesh);
}

function addFaceGraphic(group, pts, { fill = true, opacity = 0.45, entityId = null, color = 0xf0c674 } = {}) {
  if (pts.length < 3) return;
  const z = (Number.isFinite(pts[0].z_mm) ? pts[0].z_mm : 0) + 20;
  if (fill) {
    const vertices = [];
    const origin = pts[0];
    for (let i = 1; i < pts.length - 1; i += 1) {
      vertices.push(
        origin.x_mm, origin.y_mm, z,
        pts[i].x_mm, pts[i].y_mm, z,
        pts[i + 1].x_mm, pts[i + 1].y_mm, z,
      );
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(vertices, 3));
    geometry.computeVertexNormals();
    const mesh = new THREE.Mesh(
      geometry,
      new THREE.MeshStandardMaterial({
        color,
        transparent: true,
        opacity,
        side: THREE.DoubleSide,
        depthWrite: false,
      }),
    );
    mesh.renderOrder = 2;
    mark(mesh, entityId);
    group.add(mesh);
  }
  const loop = pts.map((point) => new THREE.Vector3(point.x_mm, point.y_mm, z + 8));
  loop.push(loop[0].clone());
  const outline = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(loop),
    new THREE.LineBasicMaterial({ color: accentFor(entityId, 0xffe08a) }),
  );
  mark(outline, entityId);
  group.add(outline);
}

function rebuild() {
  draft.clear();
  committedDims = [];
  const byId = new Map((sceneState.points || []).map((point) => [point.entity_id, point]));
  for (const point of sceneState.points || []) {
    const mesh = new THREE.Mesh(
      new THREE.SphereGeometry(80, 12, 12),
      new THREE.MeshStandardMaterial({ color: accentFor(point.entity_id, 0x6cb3ff) }),
    );
    mesh.position.set(point.x_mm, point.y_mm, point.z_mm);
    mark(mesh, point.entity_id);
    draft.add(mesh);
  }
  for (const line of sceneState.lines || []) {
    const start = byId.get(line.start_id);
    const end = byId.get(line.end_id);
    if (!start || !end) continue;
    const drawn = new THREE.Line(new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(start.x_mm, start.y_mm, start.z_mm),
      new THREE.Vector3(end.x_mm, end.y_mm, end.z_mm),
    ]), new THREE.LineBasicMaterial({ color: accentFor(line.entity_id, 0xe8edf2) }));
    mark(drawn, line.entity_id);
    draft.add(drawn);
    const mid = midpoint(start, end);
    committedDims.push({ ...mid, z_mm: (mid.z_mm || 0) + 40, text: formatMm(dist3(start, end)) });
  }
  for (const polyline of sceneState.polylines || []) {
    const pts = polyline.point_ids.map((id) => byId.get(id)).filter(Boolean);
    if (pts.length < 2) continue;
    const vectors = pts.map((point) => new THREE.Vector3(point.x_mm, point.y_mm, point.z_mm));
    if (polyline.closed) vectors.push(vectors[0].clone());
    const drawn = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(vectors),
      new THREE.LineBasicMaterial({ color: accentFor(polyline.entity_id, 0xe8edf2) }),
    );
    mark(drawn, polyline.entity_id);
    draft.add(drawn);
  }
  const extruded = new Set((sceneState.solids || []).map((solid) => solid.face_id));
  for (const face of sceneState.faces || []) {
    const pts = face.point_ids.map((id) => byId.get(id)).filter(Boolean);
    addFaceGraphic(draft, pts, {
      fill: !extruded.has(face.entity_id),
      opacity: 0.38,
      entityId: face.entity_id,
      color: accentFor(face.entity_id, 0xf0c674),
    });
    if (pts.length >= 2 && !extruded.has(face.entity_id)) {
      const xs = pts.map((p) => p.x_mm);
      const ys = pts.map((p) => p.y_mm);
      committedDims.push({
        x_mm: (Math.min(...xs) + Math.max(...xs)) / 2,
        y_mm: (Math.min(...ys) + Math.max(...ys)) / 2,
        z_mm: 60,
        text: `${formatMm(Math.max(...xs) - Math.min(...xs))} × ${formatMm(Math.max(...ys) - Math.min(...ys))}`,
      });
    }
  }
  for (const circle of sceneState.circles || []) {
    const center = byId.get(circle.center_id);
    if (!center) continue;
    const loop = sampleCircle(center, circle.radius_mm);
    addFaceGraphic(draft, loop.slice(0, -1), {
      fill: !extruded.has(circle.entity_id),
      opacity: 0.38,
      entityId: circle.entity_id,
      color: accentFor(circle.entity_id, 0xf0c674),
    });
    committedDims.push({
      x_mm: center.x_mm + circle.radius_mm,
      y_mm: center.y_mm,
      z_mm: 40,
      text: `R ${formatMm(circle.radius_mm)}`,
    });
  }
  for (const arc of sceneState.arcs || []) {
    const start = byId.get(arc.start_id);
    const midPt = byId.get(arc.mid_id);
    const end = byId.get(arc.end_id);
    if (!start || !midPt || !end) continue;
    addCurve(draft, sampleArc(start, midPt, end), accentFor(arc.entity_id, 0xe8edf2), arc.entity_id);
    const circ = circumcircle(start, midPt, end);
    if (circ) {
      committedDims.push({
        x_mm: midPt.x_mm,
        y_mm: midPt.y_mm,
        z_mm: 40,
        text: `R ${formatMm(circ.radius)}`,
      });
    }
  }
  for (const ellipse of sceneState.ellipses || []) {
    const center = byId.get(ellipse.center_id);
    if (!center) continue;
    const loop = sampleEllipse(center, ellipse.radius_x_mm, ellipse.radius_y_mm);
    addFaceGraphic(draft, loop.slice(0, -1), {
      fill: !extruded.has(ellipse.entity_id),
      opacity: 0.38,
      entityId: ellipse.entity_id,
      color: accentFor(ellipse.entity_id, 0xf0c674),
    });
    committedDims.push({
      x_mm: center.x_mm,
      y_mm: center.y_mm + ellipse.radius_y_mm,
      z_mm: 40,
      text: `${formatMm(ellipse.radius_x_mm)} × ${formatMm(ellipse.radius_y_mm)}`,
    });
  }
  for (const bezier of sceneState.beziers || []) {
    const pts = bezier.point_ids.map((id) => byId.get(id)).filter(Boolean);
    if (pts.length !== 4) continue;
    addCurve(draft, sampleBezier(pts), accentFor(bezier.entity_id, 0xe8edf2), bezier.entity_id);
  }
  for (const box of sceneState.boxes || []) {
    addVolume(draft, box.origin_xyz_mm, box.size_xyz_mm, accentFor(box.entity_id, 0x7dcea0), 0.28, box.entity_id);
  }
  for (const solid of sceneState.solids || []) {
    const color = accentFor(solid.entity_id, 0x7dcea0);
    const face = (sceneState.faces || []).find((item) => item.entity_id === solid.face_id);
    const circle = (sceneState.circles || []).find((item) => item.entity_id === solid.face_id);
    const ellipse = (sceneState.ellipses || []).find((item) => item.entity_id === solid.face_id);
    const height = Math.abs(solid.distance_mm);
    if (circle) {
      const center = byId.get(circle.center_id);
      if (!center) continue;
      const originZ = solid.distance_mm >= 0 ? center.z_mm : center.z_mm - height;
      addCylinder(draft, center.x_mm, center.y_mm, circle.radius_mm, originZ, height, color, 0.28, solid.entity_id);
      continue;
    }
    if (ellipse) {
      const center = byId.get(ellipse.center_id);
      if (!center) continue;
      const originZ = solid.distance_mm >= 0 ? center.z_mm : center.z_mm - height;
      addVolume(
        draft,
        [center.x_mm - ellipse.radius_x_mm, center.y_mm - ellipse.radius_y_mm, originZ],
        [ellipse.radius_x_mm * 2, ellipse.radius_y_mm * 2, height],
        color,
        0.28,
        solid.entity_id,
      );
      continue;
    }
    if (!face) continue;
    const pts = face.point_ids.map((id) => byId.get(id)).filter(Boolean);
    if (!pts.length) continue;
    const xs = pts.map((p) => p.x_mm);
    const ys = pts.map((p) => p.y_mm);
    const zs = pts.map((p) => p.z_mm);
    const originZ = solid.distance_mm >= 0 ? Math.min(...zs) : Math.min(...zs) - height;
    addVolume(
      draft,
      [Math.min(...xs), Math.min(...ys), originZ],
      [
        Math.max(Math.max(...xs) - Math.min(...xs), 1),
        Math.max(Math.max(...ys) - Math.min(...ys), 1),
        Math.max(height, 1),
      ],
      color,
      0.28,
      solid.entity_id,
    );
  }
  refreshDocks();
}

async function refreshFrom(payload) {
  sceneState = payload;
  try {
    rebuild();
  } catch (error) {
    console.error(error);
    setHint(`draw error: ${error.message}`);
  }
}

function catalog() {
  const rows = [];
  const push = (kind, item) => {
    rows.push({
      id: item.entity_id,
      kind,
      name: item.label || `${kind} ${item.entity_id}`,
      item,
    });
  };
  for (const item of sceneState.points || []) push("Point", item);
  for (const item of sceneState.lines || []) push("Line", item);
  for (const item of sceneState.polylines || []) push("Polyline", item);
  for (const item of sceneState.faces || []) push("Face", item);
  for (const item of sceneState.circles || []) push("Circle", item);
  for (const item of sceneState.arcs || []) push("Arc", item);
  for (const item of sceneState.ellipses || []) push("Ellipse", item);
  for (const item of sceneState.beziers || []) push("Bezier", item);
  for (const item of sceneState.boxes || []) push("Box", item);
  for (const item of sceneState.solids || []) push("Solid", item);
  rows.sort((a, b) => a.id - b.id);
  return rows;
}

function findRecord(id) {
  return catalog().find((row) => row.id === id) || null;
}

function isProfile(id) {
  const row = findRecord(id);
  return row != null && (row.kind === "Face" || row.kind === "Circle" || row.kind === "Ellipse");
}

function setSelection(id, { shift = false } = {}) {
  if (id == null) {
    if (!shift) selectedIds.clear();
  } else if (shift) {
    if (selectedIds.has(id)) selectedIds.delete(id);
    else selectedIds.add(id);
  } else {
    selectedIds.clear();
    selectedIds.add(id);
  }
  rebuild();
}

function selectedProfileId() {
  const profiles = [...selectedIds].filter((id) => isProfile(id));
  return profiles.length === 1 ? profiles[0] : null;
}

function refreshDocks() {
  const rows = catalog();
  for (const id of [...selectedIds]) {
    if (!rows.some((row) => row.id === id)) selectedIds.delete(id);
  }
  treeEl.innerHTML = "";
  if (!rows.length) {
    treeEl.textContent = "No entities.";
  } else {
    for (const row of rows) {
      const div = document.createElement("div");
      div.className = `tree-item${selectedIds.has(row.id) ? " selected" : ""}`;
      div.innerHTML = `<span class="tree-kind">${row.kind}</span><span>${row.name}</span>`;
      div.addEventListener("click", (event) => setSelection(row.id, { shift: event.shiftKey }));
      treeEl.appendChild(div);
    }
  }
  if (selectedIds.size === 0) {
    propBody.textContent = "Nothing selected.";
    return;
  }
  if (selectedIds.size > 1) {
    propBody.textContent = `${selectedIds.size} entities selected.`;
    return;
  }
  const selected = rows.find((row) => selectedIds.has(row.id)) || null;
  if (!selected) {
    propBody.textContent = "Nothing selected.";
    return;
  }
  const fields = propertyFields(selected);
  propBody.innerHTML = fields.map(([key, value]) => (
    `<div class="prop"><dt>${key}</dt><dd>${value}</dd></div>`
  )).join("");
}

function propertyFields(row) {
  const item = row.item;
  const fields = [["Type", row.kind], ["Id", String(row.id)], ["Label", item.label || "—"]];
  if (row.kind === "Point") {
    fields.push(["X", formatMm(item.x_mm)], ["Y", formatMm(item.y_mm)], ["Z", formatMm(item.z_mm)]);
  }
  if (row.kind === "Line") fields.push(["Start", String(item.start_id)], ["End", String(item.end_id)]);
  if (row.kind === "Circle") fields.push(["Centre", String(item.center_id)], ["Radius", formatMm(item.radius_mm)]);
  if (row.kind === "Ellipse") {
    fields.push(["Centre", String(item.center_id)], ["Rx", formatMm(item.radius_x_mm)], ["Ry", formatMm(item.radius_y_mm)]);
  }
  if (row.kind === "Arc") {
    fields.push(["Start", String(item.start_id)], ["Mid", String(item.mid_id)], ["End", String(item.end_id)]);
  }
  if (row.kind === "Face") fields.push(["Points", String((item.point_ids || []).length)]);
  if (row.kind === "Solid") {
    fields.push(["Profile", String(item.face_id)], ["Height", formatMm(item.distance_mm)]);
  }
  if (row.kind === "Box" && item.size_xyz_mm) {
    fields.push(["Size", item.size_xyz_mm.map((value) => formatMm(value)).join(" × ")]);
  }
  if (row.kind === "Bezier") fields.push(["Controls", (item.point_ids || []).join(", ")]);
  return fields;
}

function pickEntity(event) {
  const raycaster = new THREE.Raycaster();
  raycaster.params.Line = { threshold: 160 };
  raycaster.setFromCamera(ndcFromEvent(event), camera());
  const hits = raycaster.intersectObjects(draft.children, true);
  for (const hit of hits) {
    let object = hit.object;
    while (object) {
      if (object.userData && object.userData.entityId != null) return object.userData.entityId;
      object = object.parent;
    }
  }
  return null;
}

function pointById(id) {
  return (sceneState.points || []).find((point) => point.entity_id === id) || null;
}

function clientOf(xMm, yMm, zMm = 0) {
  const vector = new THREE.Vector3(xMm, yMm, zMm).project(camera());
  const rect = canvas.getBoundingClientRect();
  return {
    x: rect.left + (vector.x * 0.5 + 0.5) * rect.width,
    y: rect.top + (-vector.y * 0.5 + 0.5) * rect.height,
  };
}

function inRect(point, rect) {
  return point.x >= rect.left && point.x <= rect.right && point.y >= rect.top && point.y <= rect.bottom;
}

function segmentsCross2d(a1, a2, b1, b2) {
  const ax = a2.x - a1.x;
  const ay = a2.y - a1.y;
  const bx = b2.x - b1.x;
  const by = b2.y - b1.y;
  const denom = ax * by - ay * bx;
  if (Math.abs(denom) < 1e-9) return false;
  const t = ((b1.x - a1.x) * by - (b1.y - a1.y) * bx) / denom;
  const u = ((b1.x - a1.x) * ay - (b1.y - a1.y) * ax) / denom;
  return t >= 0 && t <= 1 && u >= 0 && u <= 1;
}

function segmentHitsRect(a, b, rect) {
  if (inRect(a, rect) || inRect(b, rect)) return true;
  const corners = [
    { x: rect.left, y: rect.top },
    { x: rect.right, y: rect.top },
    { x: rect.right, y: rect.bottom },
    { x: rect.left, y: rect.bottom },
  ];
  for (let i = 0; i < 4; i += 1) {
    if (segmentsCross2d(a, b, corners[i], corners[(i + 1) % 4])) return true;
  }
  return false;
}

function shapeQualifies(pts, closed, crossing, rect) {
  if (!pts.length) return false;
  if (!crossing) return pts.every((point) => inRect(point, rect));
  if (pts.some((point) => inRect(point, rect))) return true;
  const last = closed ? pts.length : pts.length - 1;
  for (let i = 0; i < last; i += 1) {
    if (segmentHitsRect(pts[i], pts[(i + 1) % pts.length], rect)) return true;
  }
  return false;
}

function entityScreenShape(row) {
  const toScreen = (point) => clientOf(point.x_mm, point.y_mm, point.z_mm || 0);
  if (row.kind === "Point") return { pts: [toScreen(row.item)], closed: false };
  if (row.kind === "Line") {
    const start = pointById(row.item.start_id);
    const end = pointById(row.item.end_id);
    if (!start || !end) return null;
    return { pts: [toScreen(start), toScreen(end)], closed: false };
  }
  if (row.kind === "Polyline" || row.kind === "Face" || row.kind === "Bezier") {
    const pts = (row.item.point_ids || []).map((id) => pointById(id)).filter(Boolean).map(toScreen);
    return { pts, closed: row.kind === "Face" || row.item.closed === true };
  }
  if (row.kind === "Arc") {
    const pts = [row.item.start_id, row.item.mid_id, row.item.end_id]
      .map((id) => pointById(id)).filter(Boolean).map(toScreen);
    return { pts, closed: false };
  }
  if (row.kind === "Circle") {
    const center = pointById(row.item.center_id);
    if (!center) return null;
    return {
      pts: sampleCircle(center, row.item.radius_mm).slice(0, -1).map(toScreen),
      closed: true,
    };
  }
  if (row.kind === "Ellipse") {
    const center = pointById(row.item.center_id);
    if (!center) return null;
    const loop = [
      { x_mm: center.x_mm - row.item.radius_x_mm, y_mm: center.y_mm, z_mm: 0 },
      { x_mm: center.x_mm, y_mm: center.y_mm - row.item.radius_y_mm, z_mm: 0 },
      { x_mm: center.x_mm + row.item.radius_x_mm, y_mm: center.y_mm, z_mm: 0 },
      { x_mm: center.x_mm, y_mm: center.y_mm + row.item.radius_y_mm, z_mm: 0 },
    ];
    return { pts: loop.map(toScreen), closed: true };
  }
  if (row.kind === "Box") {
    const [x, y, z] = row.item.origin_xyz_mm;
    const [dx, dy, dz] = row.item.size_xyz_mm;
    const corners = [];
    for (const xi of [x, x + dx]) {
      for (const yi of [y, y + dy]) {
        for (const zi of [z, z + dz]) corners.push(clientOf(xi, yi, zi));
      }
    }
    return { pts: corners, closed: false };
  }
  if (row.kind === "Solid") {
    const extents = profileExtents(row.item.face_id);
    if (!extents) return null;
    return {
      pts: [
        clientOf(extents.a.x_mm, extents.a.y_mm, 0),
        clientOf(extents.b.x_mm, extents.a.y_mm, 0),
        clientOf(extents.b.x_mm, extents.b.y_mm, 0),
        clientOf(extents.a.x_mm, extents.b.y_mm, 0),
      ],
      closed: true,
    };
  }
  return null;
}

function entitiesInWindow(rect, crossing) {
  const hits = [];
  for (const row of catalog()) {
    const shape = entityScreenShape(row);
    if (shape && shapeQualifies(shape.pts, shape.closed, crossing, rect)) hits.push(row.id);
  }
  return hits;
}

function hideMarquee() {
  marqueeOrigin = null;
  marqueeEl.hidden = true;
  marqueeEl.classList.remove("crossing");
}

function updateMarquee(event) {
  if (!marqueeOrigin) return;
  const stage = document.getElementById("stage").getBoundingClientRect();
  const x0 = marqueeOrigin.x;
  const y0 = marqueeOrigin.y;
  const x1 = event.clientX;
  const y1 = event.clientY;
  marqueeEl.hidden = false;
  marqueeEl.classList.toggle("crossing", x1 < x0);
  marqueeEl.style.left = `${Math.min(x0, x1) - stage.left}px`;
  marqueeEl.style.top = `${Math.min(y0, y1) - stage.top}px`;
  marqueeEl.style.width = `${Math.abs(x1 - x0)}px`;
  marqueeEl.style.height = `${Math.abs(y1 - y0)}px`;
}

function applyWindowSelect(origin, event) {
  const crossing = event.clientX < origin.x;
  const rect = {
    left: Math.min(origin.x, event.clientX),
    right: Math.max(origin.x, event.clientX),
    top: Math.min(origin.y, event.clientY),
    bottom: Math.max(origin.y, event.clientY),
  };
  hideMarquee();
  const hits = entitiesInWindow(rect, crossing);
  if (!event.shiftKey) selectedIds.clear();
  for (const id of hits) selectedIds.add(id);
  rebuild();
  setHint(hits.length
    ? `${crossing ? "Crossing" : "Window"}: ${selectedIds.size} selected.`
    : "Nothing in the window.");
}

function lineIntersectMm(a1, a2, b1, b2) {
  const ax = a1.x_mm;
  const ay = a1.y_mm;
  const bx = a2.x_mm - ax;
  const by = a2.y_mm - ay;
  const cx = b1.x_mm;
  const cy = b1.y_mm;
  const dx = b2.x_mm - cx;
  const dy = b2.y_mm - cy;
  const denom = bx * dy - by * dx;
  if (Math.abs(denom) < 1e-12) return null;
  const t = ((cx - ax) * dy - (cy - ay) * dx) / denom;
  const u = ((cx - ax) * by - (cy - ay) * bx) / denom;
  return { x_mm: ax + t * bx, y_mm: ay + t * by, z_mm: 0, t, u };
}

function segmentsIntersectMm(a1, a2, b1, b2) {
  const hit = lineIntersectMm(a1, a2, b1, b2);
  if (!hit) return null;
  if (hit.t <= 1e-9 || hit.t >= 1 - 1e-9 || hit.u <= 1e-9 || hit.u >= 1 - 1e-9) return null;
  return hit;
}

function projectT(point, start, end) {
  const vx = end.x_mm - start.x_mm;
  const vy = end.y_mm - start.y_mm;
  const length2 = vx * vx + vy * vy;
  if (length2 === 0) return 0;
  return ((point.x_mm - start.x_mm) * vx + (point.y_mm - start.y_mm) * vy) / length2;
}

function lineRows() {
  return catalog().filter((row) => row.kind === "Line");
}

function cutterCandidates(victimId) {
  const pinned = [...cutterIds].filter((id) => id !== victimId);
  const source = pinned.length
    ? pinned.map((id) => findRecord(id)).filter((row) => row && row.kind === "Line")
    : lineRows().filter((row) => row.id !== victimId);
  return source;
}

function seedCuttersFromSelection() {
  cutterIds = new Set([...selectedIds].filter((id) => {
    const row = findRecord(id);
    return row && row.kind === "Line";
  }));
}

function solveTrimOrExtend(victimId, click, mode) {
  const row = findRecord(victimId);
  if (!row || row.kind !== "Line" || !click) return null;
  const a1 = pointById(row.item.start_id);
  const a2 = pointById(row.item.end_id);
  if (!a1 || !a2) return null;
  const tClick = projectT(click, a1, a2);
  const hits = [];
  for (const cutter of cutterCandidates(victimId)) {
    const b1 = pointById(cutter.item.start_id);
    const b2 = pointById(cutter.item.end_id);
    if (!b1 || !b2) continue;
    const hit = lineIntersectMm(a1, a2, b1, b2);
    if (!hit) continue;
    const onCutter = hit.u > 1e-6 && hit.u < 1 - 1e-6;
    hits.push({ ...hit, cutterId: cutter.id, onCutter });
  }
  const prefer = (left, right) => {
    if (left.onCutter !== right.onCutter) return left.onCutter ? -1 : 1;
    return 0;
  };
  if (mode === "trim") {
    const onVictim = hits.filter((hit) => hit.t > 1e-4 && hit.t < 1 - 1e-4);
    if (!onVictim.length) return null;
    const tMin = Math.min(...onVictim.map((hit) => hit.t));
    const tMax = Math.max(...onVictim.map((hit) => hit.t));
    let chosen = null;
    let keepId = null;
    if (tClick <= tMin + 1e-9) {
      chosen = onVictim.filter((hit) => Math.abs(hit.t - tMin) < 1e-9).sort(prefer)[0];
      keepId = row.item.end_id;
    } else if (tClick >= tMax - 1e-9) {
      chosen = onVictim.filter((hit) => Math.abs(hit.t - tMax) < 1e-9).sort(prefer)[0];
      keepId = row.item.start_id;
    } else {
      return null;
    }
    const keepStart = keepId === row.item.start_id;
    return {
      mode: "trim",
      lineId: victimId,
      keepId,
      cutterId: chosen.cutterId,
      cut: { x_mm: chosen.x_mm, y_mm: chosen.y_mm, z_mm: 0 },
      keepA: keepStart ? a1 : a2,
      discardA: keepStart ? a2 : a1,
    };
  }
  const beyond = hits.filter((hit) => hit.t < -1e-4 || hit.t > 1 + 1e-4);
  if (!beyond.length) return null;
  const towardStart = tClick < 0.5;
  const candidates = beyond.filter((hit) => (towardStart ? hit.t < 0 : hit.t > 1));
  if (!candidates.length) return null;
  candidates.sort((left, right) => {
    const pin = prefer(left, right);
    if (pin !== 0) return pin;
    return towardStart ? right.t - left.t : left.t - right.t;
  });
  const chosen = candidates[0];
  const from = towardStart ? a1 : a2;
  const grow = Math.hypot(chosen.x_mm - from.x_mm, chosen.y_mm - from.y_mm);
  if (grow > 100000) return null;
  return {
    mode: "extend",
    lineId: victimId,
    keepId: towardStart ? row.item.end_id : row.item.start_id,
    cutterId: chosen.cutterId,
    cut: { x_mm: chosen.x_mm, y_mm: chosen.y_mm, z_mm: 0 },
    from,
    keepA: towardStart ? a2 : a1,
  };
}

function solveBreak(firstId, secondId) {
  if (firstId == null || secondId == null || firstId === secondId) return null;
  const a = findRecord(firstId);
  const b = findRecord(secondId);
  if (!a || !b || a.kind !== "Line" || b.kind !== "Line") return null;
  const a1 = pointById(a.item.start_id);
  const a2 = pointById(a.item.end_id);
  const b1 = pointById(b.item.start_id);
  const b2 = pointById(b.item.end_id);
  if (!a1 || !a2 || !b1 || !b2) return null;
  const hit = lineIntersectMm(a1, a2, b1, b2);
  if (!hit) return null;
  if (hit.t <= 1e-6 || hit.t >= 1 - 1e-6 || hit.u <= 1e-6 || hit.u >= 1 - 1e-6) return null;
  return { lineA: firstId, lineB: secondId, cut: { x_mm: hit.x_mm, y_mm: hit.y_mm, z_mm: 0 } };
}

async function commitTrimPreview(preview) {
  await refreshFrom(await api("/api/op", "POST", {
    op: "TrimLine",
    line_id: preview.lineId,
    keep_id: preview.keepId,
    x_mm: preview.cut.x_mm,
    y_mm: preview.cut.y_mm,
    z_mm: 0,
  }));
  setHint(preview.mode === "extend"
    ? "Extended. Click another end, or Esc."
    : "Trimmed. Click another part, or Esc.");
  if (lastPointer) updateGhost(lastPointer);
}

async function commitBreak(preview) {
  const after = await api("/api/op", "POST", {
    op: "BreakCrossing",
    line_a_id: preview.lineA,
    line_b_id: preview.lineB,
  });
  await refreshFrom(after);
  pending = null;
  if (after.created_id != null) setSelection(after.created_id);
  setHint("Broke at the crossing. Click two more lines, or Esc.");
}

async function finishMove(end) {
  const dx = end.x_mm - pending.a.x_mm;
  const dy = end.y_mm - pending.a.y_mm;
  const dz = (end.z_mm || 0) - (pending.a.z_mm || 0);
  if (Math.hypot(dx, dy, dz) < 1) {
    pending = null;
    ghosts.clear();
    setHint("Move cancelled (zero displacement).");
    return;
  }
  await refreshFrom(await api("/api/op", "POST", {
    op: "Translate",
    entity_ids: [...selectedIds],
    dx_mm: dx,
    dy_mm: dy,
    dz_mm: dz,
  }));
  pending = null;
  clearTyped();
  ghosts.clear();
  ghostDims = [];
  setHint(`Moved ${selectedIds.size} entities.`);
}

async function finishInsertNode(targetId, xyz) {
  const after = await api("/api/op", "POST", {
    op: "InsertNode",
    target_id: targetId,
    x_mm: xyz.x_mm,
    y_mm: xyz.y_mm,
    z_mm: xyz.z_mm || 0,
  });
  await refreshFrom(after);
  if (after.created_id != null) setSelection(after.created_id);
  setHint("Node inserted.");
}

async function commitFaceFromLines() {
  const lineIds = [...selectedIds].filter((id) => {
    const row = findRecord(id);
    return row && row.kind === "Line";
  });
  if (lineIds.length < 3) {
    setHint("Select at least three lines that form a closed loop, then Face.");
    return;
  }
  const after = await api("/api/op", "POST", {
    op: "AddFaceFromLines",
    line_ids: lineIds,
    label: labelValue(),
  });
  await refreshFrom(after);
  if (after.created_id != null) setSelection(after.created_id);
  setHint("Face from lines.");
}

async function commitJoin() {
  const ids = [...selectedIds].filter((id) => {
    const row = findRecord(id);
    return row && (row.kind === "Line" || row.kind === "Polyline");
  });
  if (ids.length < 2) {
    setHint("Select two or more connected lines (or polylines), then Join. Sew first if ends only coincide.");
    return;
  }
  const after = await api("/api/op", "POST", {
    op: "JoinPolyline",
    entity_ids: ids,
    label: labelValue(),
  });
  await refreshFrom(after);
  if (after.created_id != null) setSelection(after.created_id);
  setHint("Joined into a polyline.");
}

async function commitSew() {
  if (selectedIds.size === 0) {
    setHint("Select entities, then Sew to merge coincident points.");
    return;
  }
  await refreshFrom(await api("/api/op", "POST", {
    op: "Sew",
    entity_ids: [...selectedIds],
    tolerance_mm: 1,
  }));
  setHint("Sewed coincident points.");
}

async function commitSimplify() {
  const ids = [...selectedIds].filter((id) => {
    const row = findRecord(id);
    return row && (row.kind === "Face" || row.kind === "Polyline");
  });
  if (!ids.length) {
    setHint("Select a face or polyline, then Simplify.");
    return;
  }
  await refreshFrom(await api("/api/op", "POST", {
    op: "Simplify",
    entity_ids: ids,
  }));
  setHint("Simplified collinear vertices.");
}

async function commitDelete() {
  if (pending) {
    setHint("Finish or Esc the current command before deleting.");
    return;
  }
  if (selectedIds.size === 0) {
    setHint("Select entities, then Delete.");
    return;
  }
  const count = selectedIds.size;
  await refreshFrom(await api("/api/op", "POST", {
    op: "Delete",
    entity_ids: [...selectedIds],
  }));
  setHint(count === 1 ? "Deleted 1 entity." : `Deleted ${count} entities.`);
}

function nearestVertexId(row, xyz) {
  const ids = row.item.point_ids || [];
  let best = null;
  let bestDist = Infinity;
  for (const id of ids) {
    const point = pointById(id);
    if (!point) continue;
    const dist = Math.hypot(point.x_mm - xyz.x_mm, point.y_mm - xyz.y_mm);
    if (dist < bestDist) {
      bestDist = dist;
      best = id;
    }
  }
  return bestDist < 800 ? best : null;
}

function cornerTarget(event) {
  const xyz = hitWorkplane(event);
  if (!xyz) return null;
  const picked = pickEntity(event);
  const row = findRecord(picked);
  if (row && (row.kind === "Face" || row.kind === "Polyline")) {
    const vertexId = nearestVertexId(row, xyz);
    if (vertexId != null) return { targetId: row.id, vertexId };
  }
  if (row && row.kind === "Point") {
    for (const candidate of catalog()) {
      if (candidate.kind !== "Face" && candidate.kind !== "Polyline") continue;
      if ((candidate.item.point_ids || []).includes(row.id)) {
        return { targetId: candidate.id, vertexId: row.id };
      }
    }
  }
  return null;
}

async function finishRotate(pivot, angleDeg) {
  await refreshFrom(await api("/api/op", "POST", {
    op: "Rotate",
    entity_ids: [...selectedIds],
    origin_x_mm: pivot.x_mm,
    origin_y_mm: pivot.y_mm,
    angle_deg: angleDeg,
  }));
  pending = null;
  clearTyped();
  ghosts.clear();
  ghostDims = [];
  setHint(`Rotated ${selectedIds.size} entities.`);
}

async function finishMirror(axisA, axisB) {
  await refreshFrom(await api("/api/op", "POST", {
    op: "Mirror",
    entity_ids: [...selectedIds],
    ax_mm: axisA.x_mm,
    ay_mm: axisA.y_mm,
    bx_mm: axisB.x_mm,
    by_mm: axisB.y_mm,
  }));
  pending = null;
  clearTyped();
  ghosts.clear();
  ghostDims = [];
  setHint(`Mirrored ${selectedIds.size} entities.`);
}

async function finishArray(end) {
  const copies = arrayCount() - 1;
  if (copies < 1) throw new Error("n must be at least 2 for an array");
  await refreshFrom(await api("/api/op", "POST", {
    op: "ArrayLinear",
    entity_ids: [...selectedIds],
    dx_mm: end.x_mm - pending.a.x_mm,
    dy_mm: end.y_mm - pending.a.y_mm,
    dz_mm: 0,
    copies,
  }));
  pending = null;
  clearTyped();
  ghosts.clear();
  ghostDims = [];
  setHint(`Linear array: ${arrayCount()} items.`);
}

async function finishPolar(center) {
  const typed = activeLength();
  await refreshFrom(await api("/api/op", "POST", {
    op: "ArrayPolar",
    entity_ids: [...selectedIds],
    origin_x_mm: center.x_mm,
    origin_y_mm: center.y_mm,
    count: arrayCount(),
    angle_deg: typed != null ? typed : 360,
  }));
  pending = null;
  clearTyped();
  ghosts.clear();
  ghostDims = [];
  setHint(`Polar array: ${arrayCount()} items.`);
}

async function finishCorner(kind, event) {
  const dist = activeLength();
  if (dist == null) {
    setHint(kind === "chamfer"
      ? "Chamfer: type a distance (mm), then click a corner."
      : "Fillet: type a radius (mm), then click a corner.");
    return;
  }
  const corner = cornerTarget(event);
  if (!corner) {
    setHint("Click a face or polyline corner.");
    return;
  }
  const body = kind === "chamfer"
    ? {
      op: "ChamferCorner",
      target_id: corner.targetId,
      vertex_id: corner.vertexId,
      distance_mm: dist,
    }
    : {
      op: "FilletCorner",
      target_id: corner.targetId,
      vertex_id: corner.vertexId,
      radius_mm: dist,
    };
  const after = await api("/api/op", "POST", body);
  await refreshFrom(after);
  clearTyped();
  setHint(kind === "chamfer" ? "Corner chamfered." : "Corner filleted.");
}

function profileExtents(id) {
  const row = findRecord(id);
  const byId = new Map((sceneState.points || []).map((point) => [point.entity_id, point]));
  if (!row) return null;
  if (row.kind === "Circle") {
    const center = byId.get(row.item.center_id);
    if (!center) return null;
    const radius = row.item.radius_mm;
    return {
      a: { x_mm: center.x_mm - radius, y_mm: center.y_mm - radius, z_mm: 0 },
      b: { x_mm: center.x_mm + radius, y_mm: center.y_mm + radius, z_mm: 0 },
    };
  }
  if (row.kind === "Ellipse") {
    const center = byId.get(row.item.center_id);
    if (!center) return null;
    return {
      a: { x_mm: center.x_mm - row.item.radius_x_mm, y_mm: center.y_mm - row.item.radius_y_mm, z_mm: 0 },
      b: { x_mm: center.x_mm + row.item.radius_x_mm, y_mm: center.y_mm + row.item.radius_y_mm, z_mm: 0 },
    };
  }
  if (row.kind === "Face") {
    const pts = (row.item.point_ids || []).map((pid) => byId.get(pid)).filter(Boolean);
    if (!pts.length) return null;
    return {
      a: { x_mm: Math.min(...pts.map((p) => p.x_mm)), y_mm: Math.min(...pts.map((p) => p.y_mm)), z_mm: 0 },
      b: { x_mm: Math.max(...pts.map((p) => p.x_mm)), y_mm: Math.max(...pts.map((p) => p.y_mm)), z_mm: 0 },
    };
  }
  return null;
}

function setTool(next) {
  if (next === "face-lines") {
    commitFaceFromLines().catch((error) => setHint(error.message));
    return;
  }
  if (next === "join") {
    commitJoin().catch((error) => setHint(error.message));
    return;
  }
  if (next === "sew") {
    commitSew().catch((error) => setHint(error.message));
    return;
  }
  if (next === "simplify") {
    commitSimplify().catch((error) => setHint(error.message));
    return;
  }
  if (next === "delete") {
    commitDelete().catch((error) => setHint(error.message));
    return;
  }
  const previous = tool;
  tool = next;
  pending = null;
  clearTyped();
  ghosts.clear();
  ghostDims = [];
  if (next === "trim" || next === "extend") {
    seedCuttersFromSelection();
  } else {
    cutterIds.clear();
  }
  for (const button of document.querySelectorAll("button[data-tool]")) {
    button.classList.toggle("active", button.dataset.tool === tool);
  }
  refreshToggles();
  if (next === "trim") {
    setHint(cutterIds.size
      ? `Trim (T): click the part to remove. ${cutterIds.size} cutter(s) pinned. Shift pins more.`
      : "Trim (T): click the part to remove. Shift pins a cutter. All lines cut if none pinned.");
  } else if (next === "extend") {
    setHint(cutterIds.size
      ? `Extend (E): click the end to grow. ${cutterIds.size} boundary line(s) pinned.`
      : "Extend (E): click the end to grow. Shift pins a boundary. All lines if none pinned.");
  } else {
    setHint(toolHints[tool] || "");
  }
  if (next === "trim" || next === "extend" || previous === "trim" || previous === "extend") rebuild();
}

async function reload() {
  await refreshFrom(await api("/api/scene"));
}

function snapGrid(value) {
  return Math.round(value / GRID_MM) * GRID_MM;
}

function ndcFromEvent(event) {
  const rect = canvas.getBoundingClientRect();
  return new THREE.Vector2(
    ((event.clientX - rect.left) / rect.width) * 2 - 1,
    -((event.clientY - rect.top) / rect.height) * 2 + 1,
  );
}

function nearestPoint(xyz, tolerance = SNAP_APERTURE_MM) {
  let best = null;
  let bestDist = tolerance;
  for (const point of sceneState.points || []) {
    const dist = Math.hypot(point.x_mm - xyz.x_mm, point.y_mm - xyz.y_mm, point.z_mm - xyz.z_mm);
    if (dist <= bestDist) {
      best = point;
      bestDist = dist;
    }
  }
  return best;
}

function rawHit(event) {
  const raycaster = new THREE.Raycaster();
  raycaster.setFromCamera(ndcFromEvent(event), camera());
  const hit = new THREE.Vector3();
  if (!raycaster.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 0, 1), 0), hit)) {
    return null;
  }
  return { x_mm: hit.x, y_mm: hit.y, z_mm: 0 };
}

function applySnaps(raw) {
  if (!raw) return null;
  if (snapOn) {
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
    if (gridOn) {
      const snapped = { x_mm: snapGrid(raw.x_mm), y_mm: snapGrid(raw.y_mm), z_mm: 0 };
      const dist = Math.hypot(snapped.x_mm - raw.x_mm, snapped.y_mm - raw.y_mm);
      if (dist <= SNAP_APERTURE_MM) {
        return { ...snapped, snap: "grid" };
      }
    }
  }
  return { ...raw, snap: null };
}

function hitWorkplane(event) {
  return applySnaps(rawHit(event));
}

function wantOrtho(event) {
  return Boolean(orthoOn) !== Boolean(event && event.shiftKey);
}

function orthogonalize(from, to, event) {
  if (to && to.snap === "node") return to;
  if (!wantOrtho(event)) return to;
  const dx = to.x_mm - from.x_mm;
  const dy = to.y_mm - from.y_mm;
  if (Math.abs(dx) >= Math.abs(dy)) return { x_mm: to.x_mm, y_mm: from.y_mm, z_mm: from.z_mm };
  return { x_mm: from.x_mm, y_mm: to.y_mm, z_mm: from.z_mm };
}

function applyLength(from, to, length) {
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

function hitHeight(event, cornerA, cornerB) {
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
  return snapOn && gridOn ? snapGrid(hit.z) : hit.z;
}

async function addFaceFromCorners(a, b, label) {
  const x0 = Math.min(a.x_mm, b.x_mm);
  const y0 = Math.min(a.y_mm, b.y_mm);
  const x1 = Math.max(a.x_mm, b.x_mm);
  const y1 = Math.max(a.y_mm, b.y_mm);
  if (x1 - x0 < 1 || y1 - y0 < 1) {
    throw new Error("face needs a non-zero width and height");
  }
  const corners = [
    { x_mm: x0, y_mm: y0, z_mm: 0 },
    { x_mm: x1, y_mm: y0, z_mm: 0 },
    { x_mm: x1, y_mm: y1, z_mm: 0 },
    { x_mm: x0, y_mm: y1, z_mm: 0 },
  ];
  const ids = [];
  for (const corner of corners) ids.push(await ensurePoint(corner));
  if (new Set(ids).size !== 4) {
    throw new Error("face corners collapsed onto the same points; draw a larger rectangle");
  }
  const afterFace = await api("/api/op", "POST", {
    op: "AddFace", point_ids: ids, label,
  });
  await refreshFrom(afterFace);
  return createdId(afterFace, "faces");
}

async function ensurePoint(xyz) {
  if (xyz.entity_id) return xyz.entity_id;
  const existing = nearestPoint(xyz, 1);
  if (existing) return existing.entity_id;
  const sceneAfter = await api("/api/op", "POST", {
    op: "AddPoint",
    x_mm: xyz.x_mm,
    y_mm: xyz.y_mm,
    z_mm: xyz.z_mm,
    label: null,
  });
  await refreshFrom(sceneAfter);
  return createdId(sceneAfter, "points");
}

function ghostLine(a, b) {
  ghostStroke(a, b, 0x6cb3ff, true);
}

function ghostStroke(a, b, color, dashed) {
  const material = dashed
    ? new THREE.LineDashedMaterial({ color, dashSize: 120, gapSize: 80 })
    : new THREE.LineBasicMaterial({ color });
  const line = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(a.x_mm, a.y_mm, a.z_mm || 0),
      new THREE.Vector3(b.x_mm, b.y_mm, b.z_mm || 0),
    ]),
    material,
  );
  if (dashed) line.computeLineDistances();
  ghosts.add(line);
}

function drawTrimPreview(preview) {
  if (preview.mode === "extend") {
    ghostStroke(preview.from, preview.cut, 0x7dce7d, true);
    ghostStroke(preview.keepA, preview.from, 0x6cb3ff, false);
  } else {
    ghostStroke(preview.discardA, preview.cut, 0xff6b6b, true);
    ghostStroke(preview.keepA, preview.cut, 0x6cb3ff, false);
  }
  drawSnapMarker(preview.cut, "node");
}

function ghostRect(a, b, height = 0) {
  const x0 = Math.min(a.x_mm, b.x_mm);
  const y0 = Math.min(a.y_mm, b.y_mm);
  const x1 = Math.max(a.x_mm, b.x_mm);
  const y1 = Math.max(a.y_mm, b.y_mm);
  addFaceGraphic(ghosts, [
    { x_mm: x0, y_mm: y0, z_mm: 0 },
    { x_mm: x1, y_mm: y0, z_mm: 0 },
    { x_mm: x1, y_mm: y1, z_mm: 0 },
    { x_mm: x0, y_mm: y1, z_mm: 0 },
  ], { fill: true, opacity: 0.18 });
  if (Math.abs(height) > 1) {
    addVolume(
      ghosts,
      [x0, y0, Math.min(0, height)],
      [Math.max(x1 - x0, 100), Math.max(y1 - y0, 100), Math.abs(height)],
      0x6cb3ff,
      0.18,
    );
  }
}

function drawSnapMarker(xyz, kind) {
  const size = kind === "node" ? 180 : 130;
  const z = xyz.z_mm + 40;
  const loop = [
    [xyz.x_mm - size, xyz.y_mm - size, z],
    [xyz.x_mm + size, xyz.y_mm - size, z],
    [xyz.x_mm + size, xyz.y_mm + size, z],
    [xyz.x_mm - size, xyz.y_mm + size, z],
    [xyz.x_mm - size, xyz.y_mm - size, z],
  ].map((corner) => new THREE.Vector3(...corner));
  ghosts.add(new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(loop),
    new THREE.LineBasicMaterial({ color: kind === "node" ? 0xffdd55 : 0x6cb3ff }),
  ));
}

function currentEnd(event) {
  const raw = hitWorkplane(event);
  if (!raw || !pending) return null;
  if (raw.snap === "node") return raw;
  if (pending.kind === "line" || pending.kind === "move" || pending.kind === "array" || pending.kind === "mirror" || (pending.kind === "radial" && tool !== "ellipse")) {
    return applyLength(pending.a, orthogonalize(pending.a, raw, event), activeLength());
  }
  if (pending.kind === "rect") {
    return orthogonalize(pending.a, raw, event);
  }
  return raw;
}

function updateGhost(event) {
  ghosts.clear();
  ghostDims = [];
  if (!event) {
    setCoords(null);
    return;
  }
  const hit = hitWorkplane(event);
  if (hit && hit.snap) drawSnapMarker(hit, hit.snap);
  if ((tool === "trim" || tool === "extend") && !pending) {
    const picked = pickEntity(event);
    const preview = picked ? solveTrimOrExtend(picked, hit, tool) : null;
    if (preview) drawTrimPreview(preview);
    setCoords(hit);
    return;
  }
  if (tool === "break" && pending && pending.kind === "break") {
    const picked = pickEntity(event);
    const preview = solveBreak(pending.lineId, picked);
    if (preview) drawSnapMarker(preview.cut, "node");
    setCoords(hit);
    return;
  }
  if (!pending) {
    setCoords(hit);
    return;
  }
  if (pending.kind === "line" || pending.kind === "move" || pending.kind === "array" || pending.kind === "mirror") {
    const end = currentEnd(event);
    if (end) {
      ghostLine(pending.a, end);
      const mid = midpoint(pending.a, end);
      const text = pending.kind === "mirror"
        ? "axis"
        : formatMm(dist3(pending.a, end));
      ghostDims.push({ ...mid, z_mm: 50, text, ghost: true });
      setCoords(end, pending.a);
    }
    return;
  }
  if (pending.kind === "rotate") {
    const end = hitWorkplane(event);
    if (end) {
      ghostLine(pending.a, end);
      const typed = activeLength();
      const deg = typed != null ? typed : Math.atan2(end.y_mm - pending.a.y_mm, end.x_mm - pending.a.x_mm) * 180 / Math.PI;
      ghostDims.push({
        ...end,
        z_mm: 50,
        text: `${Math.round(deg * 10) / 10}°`,
        ghost: true,
      });
      setCoords(end, pending.a);
    }
    return;
  }
  if (pending.kind === "rect") {
    const end = currentEnd(event);
    if (end) {
      ghostRect(pending.a, end);
      const w = Math.abs(end.x_mm - pending.a.x_mm);
      const h = Math.abs(end.y_mm - pending.a.y_mm);
      ghostDims.push({
        x_mm: (pending.a.x_mm + end.x_mm) / 2,
        y_mm: (pending.a.y_mm + end.y_mm) / 2,
        z_mm: 50,
        text: `${formatMm(w)} × ${formatMm(h)}`,
        ghost: true,
      });
      setCoords(end, pending.a);
    }
    return;
  }
  if (pending.kind === "height" || pending.kind === "extrude") {
    const height = hitHeight(event, pending.a, pending.b);
    ghostRect(pending.a, pending.b, height);
    ghostDims.push({
      x_mm: (pending.a.x_mm + pending.b.x_mm) / 2,
      y_mm: (pending.a.y_mm + pending.b.y_mm) / 2,
      z_mm: Math.abs(height) / 2,
      text: formatMm(Math.abs(height)),
      ghost: true,
    });
    setCoords(hit);
    return;
  }
  if (pending.kind === "radial") {
    const rim = currentEnd(event);
    if (!rim) return;
    const radius = dist3(pending.a, rim);
    if (tool === "circle") {
      addFaceGraphic(ghosts, sampleCircle(pending.a, radius).slice(0, -1), { fill: true, opacity: 0.22 });
      ghostDims.push({
        x_mm: pending.a.x_mm + radius,
        y_mm: pending.a.y_mm,
        z_mm: 50,
        text: `R ${formatMm(radius)}`,
        ghost: true,
      });
    } else if (tool === "polygon") {
      addFaceGraphic(ghosts, regularPolygon(pending.a, rim, sidesValue()), { fill: true, opacity: 0.18 });
      ghostDims.push({
        x_mm: pending.a.x_mm,
        y_mm: pending.a.y_mm,
        z_mm: 50,
        text: `${sidesValue()} × R ${formatMm(radius)}`,
        ghost: true,
      });
    } else if (tool === "ellipse") {
      const rx = Math.max(Math.abs(rim.x_mm - pending.a.x_mm), 1);
      const ry = Math.max(Math.abs(rim.y_mm - pending.a.y_mm), 1);
      addFaceGraphic(ghosts, sampleEllipse(pending.a, rx, ry).slice(0, -1), { fill: true, opacity: 0.22 });
      ghostDims.push({
        x_mm: pending.a.x_mm,
        y_mm: pending.a.y_mm,
        z_mm: 50,
        text: `${formatMm(rx)} × ${formatMm(ry)}`,
        ghost: true,
      });
    }
    setCoords(rim, pending.a);
    return;
  }
  if (pending.kind === "arc") {
    const cur = currentEnd(event) || hit;
    if (!cur) return;
    if (pending.pts.length === 1) {
      ghostLine(pending.pts[0], cur);
      ghostDims.push({ ...midpoint(pending.pts[0], cur), z_mm: 50, text: formatMm(dist3(pending.pts[0], cur)), ghost: true });
    } else {
      addCurve(ghosts, sampleArc(pending.pts[0], pending.pts[1], cur), 0x6cb3ff);
      const circ = circumcircle(pending.pts[0], pending.pts[1], cur);
      if (circ) {
        ghostDims.push({ x_mm: pending.pts[1].x_mm, y_mm: pending.pts[1].y_mm, z_mm: 50, text: `R ${formatMm(circ.radius)}`, ghost: true });
      }
    }
    setCoords(cur, pending.pts[0]);
    return;
  }
  if (pending.kind === "bezier") {
    const cur = currentEnd(event) || hit;
    if (!cur) return;
    const pts = pending.pts.concat([cur]);
    if (pts.length === 2) ghostLine(pts[0], pts[1]);
    else if (pts.length === 3) addCurve(ghosts, sampleBezier([pts[0], pts[1], pts[2], pts[2]]), 0x6cb3ff);
    else addCurve(ghosts, sampleBezier(pts.slice(0, 4)), 0x6cb3ff);
    setCoords(cur, pending.pts[0]);
  }
}

async function finishLine(end) {
  const startId = await ensurePoint(pending.a);
  const endId = await ensurePoint(end);
  await refreshFrom(await api("/api/op", "POST", {
    op: "AddLine", start_id: startId, end_id: endId, label: labelValue(),
  }));
  pending = null;
  clearTyped();
  ghosts.clear();
  ghostDims = [];
  refreshToggles();
  setHint("Line placed. LMB draws another.");
}

async function finishFace(end) {
  await addFaceFromCorners(pending.a, end, labelValue());
  pending = null;
  clearTyped();
  ghosts.clear();
  ghostDims = [];
  refreshToggles();
  setHint("Rect placed.");
}

async function finishBox(event) {
  const height = hitHeight(event, pending.a, pending.b);
  const faceId = await addFaceFromCorners(pending.a, pending.b, labelValue());
  const distance = height === 0 ? 100 : height;
  await refreshFrom(await api("/api/op", "POST", {
    op: "Extrude",
    face_id: faceId,
    distance_mm: distance,
    label: labelValue() ? `${labelValue()}_solid` : null,
  }));
  pending = null;
  clearTyped();
  ghosts.clear();
  ghostDims = [];
  refreshToggles();
  setHint("Solid placed (face + extrude).");
}

async function finishExtrude(event) {
  const height = hitHeight(event, pending.a, pending.b);
  const distance = height === 0 ? 100 : height;
  await refreshFrom(await api("/api/op", "POST", {
    op: "Extrude",
    face_id: pending.profileId,
    distance_mm: distance,
    label: labelValue() ? `${labelValue()}_solid` : null,
  }));
  pending = null;
  clearTyped();
  ghosts.clear();
  ghostDims = [];
  refreshToggles();
  setHint("Solid placed.");
}

async function finishCircle(rim) {
  const radius = dist3(pending.a, rim);
  if (radius < 1) throw new Error("circle radius must be positive");
  const centerId = await ensurePoint(pending.a);
  await refreshFrom(await api("/api/op", "POST", {
    op: "AddCircle", center_id: centerId, radius_mm: radius, label: labelValue(),
  }));
  pending = null;
  clearTyped();
  ghosts.clear();
  ghostDims = [];
  refreshToggles();
  setHint("Circle placed. Select it, then Extrude.");
}

async function finishEllipse(rim) {
  const rx = Math.abs(rim.x_mm - pending.a.x_mm);
  const ry = Math.abs(rim.y_mm - pending.a.y_mm);
  if (rx < 1 || ry < 1) throw new Error("ellipse needs two positive radii");
  const centerId = await ensurePoint(pending.a);
  await refreshFrom(await api("/api/op", "POST", {
    op: "AddEllipse",
    center_id: centerId,
    radius_x_mm: rx,
    radius_y_mm: ry,
    label: labelValue(),
  }));
  pending = null;
  clearTyped();
  ghosts.clear();
  ghostDims = [];
  refreshToggles();
  setHint("Ellipse placed.");
}

async function finishPolygon(rim) {
  const pts = regularPolygon(pending.a, rim, sidesValue());
  const ids = [];
  for (const point of pts) ids.push(await ensurePoint(point));
  if (new Set(ids).size !== pts.length) {
    throw new Error("polygon vertices collapsed; draw a larger radius");
  }
  await refreshFrom(await api("/api/op", "POST", {
    op: "AddFace", point_ids: ids, label: labelValue(),
  }));
  pending = null;
  clearTyped();
  ghosts.clear();
  ghostDims = [];
  refreshToggles();
  setHint("Polygon placed.");
}

async function finishArc(end) {
  const ids = [];
  for (const point of pending.pts.concat([end])) ids.push(await ensurePoint(point));
  await refreshFrom(await api("/api/op", "POST", {
    op: "AddArc",
    start_id: ids[0],
    mid_id: ids[1],
    end_id: ids[2],
    label: labelValue(),
  }));
  pending = null;
  clearTyped();
  ghosts.clear();
  ghostDims = [];
  refreshToggles();
  setHint("Arc placed.");
}

async function finishBezier(end) {
  const ids = [];
  for (const point of pending.pts.concat([end])) ids.push(await ensurePoint(point));
  await refreshFrom(await api("/api/op", "POST", {
    op: "AddBezier", point_ids: ids, label: labelValue(),
  }));
  pending = null;
  clearTyped();
  ghosts.clear();
  ghostDims = [];
  refreshToggles();
  setHint("Bézier placed.");
}

async function onClick(event) {
  try {
    if (tool === "select") {
      setSelection(pickEntity(event), { shift: event.shiftKey });
      return;
    }
    if (tool === "move") {
      if (selectedIds.size === 0) {
        setHint("Select entities first, then Move.");
        return;
      }
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      if (!pending) {
        pending = { kind: "move", a: xyz };
        setHint("Move: click the destination, or type a length and Enter.");
        return;
      }
      const end = currentEnd(event);
      if (!end) return;
      await finishMove(end);
      return;
    }
    if (tool === "rotate") {
      if (selectedIds.size === 0) {
        setHint("Select entities first, then Rotate.");
        return;
      }
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      if (!pending) {
        pending = { kind: "rotate", a: xyz };
        setHint("Rotate: type degrees and Enter, or click a second point for the angle.");
        return;
      }
      const typed = activeLength();
      const end = hitWorkplane(event);
      if (typed == null && !end) return;
      const angle = typed != null
        ? typed
        : Math.atan2(end.y_mm - pending.a.y_mm, end.x_mm - pending.a.x_mm) * 180 / Math.PI;
      await finishRotate(pending.a, angle);
      return;
    }
    if (tool === "mirror") {
      if (selectedIds.size === 0) {
        setHint("Select entities first, then Mirror.");
        return;
      }
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      if (!pending) {
        pending = { kind: "mirror", a: xyz };
        setHint("Mirror: click the second point of the axis.");
        return;
      }
      const end = currentEnd(event);
      if (!end) return;
      await finishMirror(pending.a, end);
      return;
    }
    if (tool === "array") {
      if (selectedIds.size === 0) {
        setHint("Select entities first, then Array. n is the count.");
        return;
      }
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      if (!pending) {
        pending = { kind: "array", a: xyz };
        setHint("Array: click the spacing to the next copy. n is the total count.");
        return;
      }
      const end = currentEnd(event);
      if (!end) return;
      await finishArray(end);
      return;
    }
    if (tool === "polar") {
      if (selectedIds.size === 0) {
        setHint("Select entities first, then Polar. n is the count.");
        return;
      }
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      await finishPolar(xyz);
      return;
    }
    if (tool === "chamfer") {
      await finishCorner("chamfer", event);
      return;
    }
    if (tool === "fillet") {
      await finishCorner("fillet", event);
      return;
    }
    if (tool === "trim" || tool === "extend") {
      const picked = pickEntity(event);
      const row = findRecord(picked);
      if (event.shiftKey && row && row.kind === "Line") {
        if (cutterIds.has(picked)) cutterIds.delete(picked);
        else cutterIds.add(picked);
        rebuild();
        const noun = tool === "extend" ? "boundary" : "cutter";
        setHint(cutterIds.size
          ? `${tool === "extend" ? "Extend" : "Trim"}: ${cutterIds.size} ${noun}(s). Click a part.`
          : `${tool === "extend" ? "Extend" : "Trim"}: all lines. Click a part.`);
        return;
      }
      if (!row || row.kind !== "Line") {
        setHint(tool === "extend"
          ? "Extend: click the end to grow, or Shift-click a boundary."
          : "Trim: click the part to remove, or Shift-click a cutter.");
        return;
      }
      const click = hitWorkplane(event);
      const preview = solveTrimOrExtend(picked, click, tool);
      if (!preview) {
        setHint(tool === "extend"
          ? "Extend: click the short end toward a boundary (implied intersection is OK)."
          : "Trim: click a free end — the stub past the nearest cutter.");
        return;
      }
      await commitTrimPreview(preview);
      return;
    }
    if (tool === "break") {
      const picked = pickEntity(event);
      const row = findRecord(picked);
      if (!row || row.kind !== "Line") {
        setHint("Break: click the first line.");
        return;
      }
      if (!pending) {
        pending = { kind: "break", lineId: picked };
        setHint("Break: click the crossing line.");
        return;
      }
      const preview = solveBreak(pending.lineId, picked);
      if (!preview) {
        setHint("Break: those lines do not cross. Click another line.");
        return;
      }
      await commitBreak(preview);
      return;
    }
    if (tool === "node") {
      const picked = pickEntity(event);
      const row = findRecord(picked);
      if (!row || (row.kind !== "Line" && row.kind !== "Face" && row.kind !== "Polyline")) {
        setHint("Node: click a line, face, or polyline.");
        return;
      }
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      await finishInsertNode(picked, xyz);
      return;
    }
    if (tool === "extrude") {
      const profileId = selectedProfileId();
      if (profileId == null) {
        setHint("Select a face, circle, or ellipse first.");
        return;
      }
      if (!pending) {
        const extents = profileExtents(profileId);
        if (!extents) return;
        pending = { kind: "extrude", a: extents.a, b: extents.b, profileId };
        setHint("Extrude: move for height, then click or Enter.");
        return;
      }
      await finishExtrude(event);
      return;
    }
    if (tool === "line") {
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      if (!pending) {
        pending = { kind: "line", a: xyz };
        setHint("Line: click the second point, or type a length and Enter.");
        return;
      }
      const end = currentEnd(event);
      if (!end) return;
      await finishLine(end);
      return;
    }
    if (tool === "rect") {
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      if (!pending) {
        pending = { kind: "rect", a: xyz };
        setHint("Rect: click the opposite corner.");
        return;
      }
      const end = currentEnd(event);
      if (!end) return;
      await finishFace(end);
      return;
    }
    if (tool === "circle" || tool === "polygon" || tool === "ellipse") {
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      if (!pending) {
        pending = { kind: "radial", a: xyz };
        setHint(tool === "circle"
          ? "Circle: click the radius, or type it and Enter."
          : tool === "polygon"
            ? "Polygon: click the radius."
            : "Ellipse: click a corner of the bounding box.");
        return;
      }
      const rim = currentEnd(event);
      if (!rim) return;
      if (tool === "circle") await finishCircle(rim);
      else if (tool === "polygon") await finishPolygon(rim);
      else await finishEllipse(rim);
      return;
    }
    if (tool === "arc") {
      const xyz = currentEnd(event) || hitWorkplane(event);
      if (!xyz) return;
      if (!pending) {
        pending = { kind: "arc", pts: [xyz] };
        setHint("Arc: click a second point on the arc.");
        return;
      }
      if (pending.pts.length === 1) {
        pending.pts.push(xyz);
        setHint("Arc: click the end point.");
        return;
      }
      await finishArc(xyz);
      return;
    }
    if (tool === "bezier") {
      const xyz = currentEnd(event) || hitWorkplane(event);
      if (!xyz) return;
      if (!pending) {
        pending = { kind: "bezier", pts: [xyz] };
        setHint("Bézier: click control point 2.");
        return;
      }
      if (pending.pts.length < 3) {
        pending.pts.push(xyz);
        setHint(`Bézier: click control point ${pending.pts.length + 1}.`);
        return;
      }
      await finishBezier(xyz);
      return;
    }
    if (tool === "box") {
      if (!pending) {
        const xyz = hitWorkplane(event);
        if (!xyz) return;
        pending = { kind: "rect", a: xyz };
        setHint("Box: click the opposite corner of the face.");
        return;
      }
      if (pending.kind === "rect") {
        const end = currentEnd(event);
        if (!end) return;
        pending = { kind: "height", a: pending.a, b: end };
        setHint("Box: move for height, type a length, then click or Enter.");
        return;
      }
      await finishBox(event);
    }
  } catch (error) {
    setHint(error.message);
    pending = null;
    ghosts.clear();
    ghostDims = [];
  }
}

async function commitWithEnter() {
  if (!pending) return;
  const echoed = typedText();
  if (echoed) appendLog(`${consolePrompt.textContent} ${echoed}`);
  try {
    if (pending.kind === "rotate") {
      const typed = activeLength();
      if (typed != null) {
        await finishRotate(pending.a, typed);
        return;
      }
      if (!lastPointer) return;
      const end = hitWorkplane(lastPointer);
      if (end) {
        await finishRotate(
          pending.a,
          Math.atan2(end.y_mm - pending.a.y_mm, end.x_mm - pending.a.x_mm) * 180 / Math.PI,
        );
      }
      return;
    }
    if (!lastPointer) return;
    if (pending.kind === "line" || pending.kind === "move" || pending.kind === "array" || pending.kind === "mirror") {
      const end = currentEnd(lastPointer);
      if (end) {
        if (pending.kind === "move") await finishMove(end);
        else if (pending.kind === "array") await finishArray(end);
        else if (pending.kind === "mirror") await finishMirror(pending.a, end);
        else await finishLine(end);
      }
      return;
    }
    if (pending.kind === "rect" && tool === "rect") {
      const end = currentEnd(lastPointer);
      if (end) await finishFace(end);
      return;
    }
    if (pending.kind === "radial") {
      const rim = currentEnd(lastPointer);
      if (!rim) return;
      if (tool === "circle") await finishCircle(rim);
      else if (tool === "polygon") await finishPolygon(rim);
      else if (tool === "ellipse") await finishEllipse(rim);
      return;
    }
    if (pending.kind === "arc" && pending.pts.length === 2) {
      const end = currentEnd(lastPointer);
      if (end) await finishArc(end);
      return;
    }
    if (pending.kind === "bezier" && pending.pts.length === 3) {
      const end = currentEnd(lastPointer);
      if (end) await finishBezier(end);
      return;
    }
    if (pending.kind === "rect" && tool === "box") {
      const end = currentEnd(lastPointer);
      if (!end) return;
      pending = { kind: "height", a: pending.a, b: end };
      setHint("Box: move for height, type a length, then click or Enter.");
      updateGhost(lastPointer);
      return;
    }
    if (pending.kind === "height") await finishBox(lastPointer);
    if (pending.kind === "extrude") await finishExtrude(lastPointer);
  } catch (error) {
    setHint(error.message);
    pending = null;
    ghosts.clear();
  }
}

const toolHints = {
  select: "Select: click, or drag L→R window / R→L crossing. Shift adds. Delete removes.",
  line: "Line: two clicks. Type a length, Enter to commit.",
  rect: "Rect: two clicks for a rectangle on XY.",
  circle: "Circle: centre, then radius. Then Select + Extrude.",
  arc: "Arc: three clicks (start, on-arc, end).",
  ellipse: "Ellipse: centre, then a corner of the bounding box.",
  polygon: "Polygon: centre, then radius. n sets the side count.",
  bezier: "Bézier: four control points.",
  box: "Box: rectangle, then pull height. Type height and Enter.",
  extrude: "Extrude: select a face/circle/ellipse, then pull height.",
  move: "Move: select entities, click a base point, then the destination.",
  rotate: "Rotate: select, click the pivot, type degrees or click an angle.",
  mirror: "Mirror: select, then two clicks for the mirror axis.",
  array: "Array: select, click spacing to the next copy. n = total count.",
  polar: "Polar: select, click the centre. n = count. Length = sweep ° (default 360).",
  trim: "Trim (T): click the part to remove. Shift pins a cutter. Implied intersection is OK.",
  extend: "Extend (E): click the short end to grow to a boundary. Shift pins a boundary.",
  break: "Break: click two crossing lines to insert a shared node.",
  node: "Node: click a line, face, or polyline to insert a shared point.",
  chamfer: "Chamfer: type a distance, then click a face or polyline corner.",
  fillet: "Fillet: type a radius, then click a face or polyline corner.",
};

for (const button of document.querySelectorAll("button[data-tool]")) {
  button.addEventListener("click", () => setTool(button.dataset.tool));
}

projButton.addEventListener("click", () => setProjection(!useOrtho));
snapButton.addEventListener("click", () => {
  snapOn = !snapOn;
  refreshToggles();
  if (lastPointer) updateGhost(lastPointer);
});
orthoButton.addEventListener("click", () => {
  orthoOn = !orthoOn;
  refreshToggles();
  if (lastPointer) updateGhost(lastPointer);
});
gridButton.addEventListener("click", () => {
  gridOn = !gridOn;
  refreshToggles();
  if (lastPointer) updateGhost(lastPointer);
});
consoleInput.addEventListener("input", () => {
  refreshToggles();
  if (lastPointer) updateGhost(lastPointer);
});

document.getElementById("undo").addEventListener("click", async () => {
  try { pending = null; ghosts.clear(); await refreshFrom(await api("/api/undo", "POST", {})); }
  catch (error) { setHint(error.message); }
});
document.getElementById("redo").addEventListener("click", async () => {
  try { await refreshFrom(await api("/api/redo", "POST", {})); }
  catch (error) { setHint(error.message); }
});
document.getElementById("clear").addEventListener("click", async () => {
  pending = null;
  ghosts.clear();
  await refreshFrom(await api("/api/reset", "POST", {}));
  setHint("Cleared.");
});
document.getElementById("save").addEventListener("click", () => {
  const blob = new Blob([JSON.stringify(sceneState.document, null, 2)], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "apecad.json";
  link.click();
});

canvas.addEventListener("pointerdown", (event) => {
  canvas.focus();
  if (event.button === 0 && event.altKey) {
    controls.mouseButtons.LEFT = THREE.MOUSE.ROTATE;
  } else {
    controls.mouseButtons.LEFT = -1;
  }
  if (event.button !== 0) return;
  pointerDown = { x: event.clientX, y: event.clientY };
  if (tool === "select" && !event.altKey) {
    marqueeOrigin = { x: event.clientX, y: event.clientY };
    canvas.setPointerCapture(event.pointerId);
  }
}, true);
canvas.addEventListener("pointermove", (event) => {
  lastPointer = event;
  if (marqueeOrigin) updateMarquee(event);
  updateGhost(event);
});
canvas.addEventListener("pointerup", (event) => {
  controls.mouseButtons.LEFT = -1;
  if (event.button !== 0 || !pointerDown) return;
  const origin = marqueeOrigin;
  const moved = Math.hypot(event.clientX - pointerDown.x, event.clientY - pointerDown.y);
  pointerDown = null;
  if (origin && moved > 5) {
    applyWindowSelect(origin, event);
    return;
  }
  hideMarquee();
  if (event.altKey || moved > 5) return;
  onClick(event);
});
canvas.addEventListener("contextmenu", (event) => event.preventDefault());

window.addEventListener("keydown", (event) => {
  if (event.key === "F3") {
    event.preventDefault();
    snapOn = !snapOn;
    refreshToggles();
    if (lastPointer) updateGhost(lastPointer);
    return;
  }
  if (event.key === "F8") {
    event.preventDefault();
    orthoOn = !orthoOn;
    refreshToggles();
    if (lastPointer) updateGhost(lastPointer);
    return;
  }
  if (event.key === "F9") {
    event.preventDefault();
    gridOn = !gridOn;
    refreshToggles();
    if (lastPointer) updateGhost(lastPointer);
    return;
  }
  if (event.key === "Escape") {
    if (pending) {
      pending = null;
      clearTyped();
      ghosts.clear();
      ghostDims = [];
      hideMarquee();
      refreshToggles();
      setHint("Cancelled.");
      return;
    }
    if (tool !== "select") {
      setTool("select");
      return;
    }
    setSelection(null);
    setHint("Selection cleared.");
    return;
  }
  if (event.target === consoleInput) {
    if (event.key === "Enter") {
      event.preventDefault();
      commitWithEnter();
      return;
    }
    if (event.key === "Delete" && consoleInput.value === "") {
      event.preventDefault();
      commitDelete().catch((error) => setHint(error.message));
      return;
    }
    if (consoleInput.value === "" && !event.ctrlKey && !event.metaKey && !event.altKey) {
      if (event.key === "t" || event.key === "T") {
        event.preventDefault();
        setTool("trim");
        return;
      }
      if (event.key === "e" || event.key === "E") {
        event.preventDefault();
        setTool("extend");
        return;
      }
      if (event.key === "j" || event.key === "J") {
        event.preventDefault();
        setTool("join");
        return;
      }
    }
    return;
  }
  if (isTypingField(event)) return;
  if (!event.ctrlKey && !event.metaKey && !event.altKey) {
    if (event.key === "t" || event.key === "T") {
      event.preventDefault();
      setTool("trim");
      return;
    }
    if (event.key === "e" || event.key === "E") {
      event.preventDefault();
      setTool("extend");
      return;
    }
    if (event.key === "j" || event.key === "J") {
      event.preventDefault();
      setTool("join");
      return;
    }
  }
  if (event.key === "Delete") {
    event.preventDefault();
    commitDelete().catch((error) => setHint(error.message));
    return;
  }
  if (event.key === "o" || event.key === "O") {
    setProjection(!useOrtho);
    return;
  }
  if (event.key === "Enter") {
    event.preventDefault();
    commitWithEnter();
    return;
  }
  if (event.key === "Backspace" && consoleInput.value !== "") {
    event.preventDefault();
    setTyped(consoleInput.value.slice(0, -1));
    refreshToggles();
    if (lastPointer) updateGhost(lastPointer);
    return;
  }
  if (event.key.length === 1 && /[0-9.]/.test(event.key)) {
    if (event.key === "." && consoleInput.value.includes(".")) return;
    setTyped(consoleInput.value + event.key);
    refreshToggles();
    if (lastPointer) updateGhost(lastPointer);
  }
});

function bindSplit(handle, onMove) {
  handle.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    event.preventDefault();
    handle.setPointerCapture(event.pointerId);
    handle.classList.add("dragging");
    const onPointerMove = (moveEvent) => onMove(moveEvent);
    const onPointerUp = () => {
      handle.classList.remove("dragging");
      try { handle.releasePointerCapture(event.pointerId); } catch (_error) { /* already released */ }
      handle.removeEventListener("pointermove", onPointerMove);
      handle.removeEventListener("pointerup", onPointerUp);
      syncCameras();
    };
    handle.addEventListener("pointermove", onPointerMove);
    handle.addEventListener("pointerup", onPointerUp);
  });
}

const workspaceEl = document.getElementById("workspace");
const dockEl = document.getElementById("dock");
const propsEl = document.getElementById("props");
bindSplit(document.getElementById("split-x"), (event) => {
  const rect = workspaceEl.getBoundingClientRect();
  const maxWidth = Math.max(rect.width * 0.5, 180);
  const width = Math.min(Math.max(event.clientX - rect.left, 180), maxWidth);
  dockEl.style.width = `${width}px`;
  syncCameras();
});
bindSplit(document.getElementById("split-y"), (event) => {
  const rect = dockEl.getBoundingClientRect();
  const height = Math.min(Math.max(rect.bottom - event.clientY, 88), rect.height - 140);
  propsEl.style.height = `${height}px`;
});
const consoleEl = document.getElementById("console");
bindSplit(document.getElementById("split-console"), (event) => {
  const body = document.body.getBoundingClientRect();
  const height = Math.min(Math.max(body.bottom - event.clientY, 56), body.height * 0.4);
  consoleEl.style.height = `${height}px`;
  syncCameras();
});

function setDockCollapsed(collapsed) {
  workspaceEl.classList.toggle("dock-collapsed", collapsed);
  document.getElementById("dock-toggle").title = collapsed ? "Show model panel" : "Collapse panel";
  syncCameras();
}

document.getElementById("dock-toggle").addEventListener("click", () => {
  setDockCollapsed(true);
});
document.getElementById("dock-expand").addEventListener("click", () => {
  setDockCollapsed(false);
});

function tick() {
  tickViewAnim();
  renderer.render(scene, camera());
  syncCube();
  projectDims();
  requestAnimationFrame(tick);
}
refreshToggles();
tick();
reload().catch((error) => setHint(error.message));
