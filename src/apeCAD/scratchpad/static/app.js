import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { LineSegments2 } from "three/addons/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/addons/lines/LineSegmentsGeometry.js";
import { LineMaterial } from "three/addons/lines/LineMaterial.js";

const SNAP_APERTURE_MM = 400;
const PICK_POINT_PX = 12;
const PICK_LINE_PX = 14;
const SELECT_FILTERS = ["point", "line", "face", "solid", "element"];
const FILTER_KINDS = {
  point: new Set(["Point"]),
  line: new Set(["Line", "Polyline", "Arc", "Bezier"]),
  face: new Set(["Face", "Circle", "Ellipse"]),
  solid: new Set(["Solid", "Box"]),
};
const GRID_DEFAULT_MINOR_MM = 100;
const GRID_DEFAULT_MAJOR_MM = 1000;
const GRID_EXTENT_MM = 40000;
const GRID_MAX_DIVISIONS = 800;
const GRID_MIN_MM = 1;
const GRID_MAX_MM = 10000;
const GRID_HIDDEN_SCALE_DEFAULT = 0.25;
const GRID_HIDDEN_SCALE_MIN = 0.25;
const GRID_HIDDEN_SCALE_MAX = 4;
const GRID_MINOR_STYLE_DEFAULT = "dots";
const GRID_DOT_SIZE_DEFAULT = 1.5;
const GRID_DOT_SIZE_MIN = 0.5;
const GRID_DOT_SIZE_MAX = 8;
const GRID_LINE_WIDTH_DEFAULT = 1;
const GRID_LINE_WIDTH_MIN = 0.5;
const GRID_LINE_WIDTH_MAX = 8;
const UNIT_MM = { mm: 1, cm: 10, m: 1000, in: 25.4 };
const UNIT_STEP = { mm: 1, cm: 0.1, m: 0.01, in: 0.01 };
const UNIT_DECIMALS = { mm: 0, cm: 1, m: 3, in: 2 };

const canvas = document.getElementById("view");
const status = document.getElementById("status");
const labelInput = document.getElementById("label");
const consoleLog = document.getElementById("console-log");
const consolePrompt = document.getElementById("console-prompt");
const consoleInput = document.getElementById("console-input");
const projButton = document.getElementById("proj");
const snapButton = document.getElementById("snap");
const gridSnapButton = document.getElementById("grid-snap");
const orthoButton = document.getElementById("ortho");
const gridButton = document.getElementById("grid");
const coordsEl = document.getElementById("coords");
const dimsEl = document.getElementById("dims");
const treeEl = document.getElementById("tree");
const propBody = document.getElementById("prop-body");
const marqueeEl = document.getElementById("marquee");

let tool = "select";
let pending = null;
let lastPointer = null;
let selectedIds = new Set();
let selectFilter = "element";
let brepParent = new Map();
let hiddenIds = new Set();
let cutterIds = new Set();
let marqueeOrigin = null;
let sceneState = {
  points: [], lines: [], boxes: [], polylines: [], faces: [], solids: [],
  circles: [], arcs: [], ellipses: [], beziers: [],
};
let pointerDown = null;
let useOrtho = true;
let projection = "parallel";
let namedView = null;
let snapOn = true;
let gridSnapOn = true;
let gridOn = true;
let gridMinorOn = true;
let orthoOn = false;
let ghostDims = [];
let committedDims = [];
let saveName = "apecad.json";
let viewCubeOn = true;

const PREFS_KEY = "apeCAD.prefs.v2";
const LAYOUT_KEY = "apeCAD.layout.v2";
const PREF_DEFAULTS = {
  background: "g5",
  clay: 176,
  curve: "#111111",
  keyLight: true,
  ao: true,
  showEdges: true,
  showCurves: true,
  showFaces: true,
  grid: true,
  gridSnap: true,
  gridMinorOn: true,
  gridMinor: GRID_DEFAULT_MINOR_MM,
  gridMajor: GRID_DEFAULT_MAJOR_MM,
  gridAuto: true,
  gridHiddenScale: GRID_HIDDEN_SCALE_DEFAULT,
  gridMinorStyle: GRID_MINOR_STYLE_DEFAULT,
  gridDotSize: GRID_DOT_SIZE_DEFAULT,
  gridLineWidth: GRID_LINE_WIDTH_DEFAULT,
  displayUnit: "mm",
};
const BACKGROUNDS = {
  g2: { bg: 0x1c1c1c, major: 0x3c3c3c, minor: 0x2a2a2a },
  g5: { bg: 0xe4e9ee, major: 0xc0c0c0, minor: 0xd2d2d2 },
  g6: { bg: 0xa3a6aa, major: 0x8a8e92, minor: 0x96999d },
};
const EDGE_COLOR = 0x111111;
const CURVE_PICK = 0x4a90d9;
const CURVE_HOVER = 0x6aa8e8;
const SNAP_COLOR = 0xd55e00;

function clampGridSpacing(value, fallback = GRID_DEFAULT_MINOR_MM) {
  const raw = Number(value);
  if (!Number.isFinite(raw) || raw <= 0) return fallback;
  return Math.min(Math.max(raw, GRID_MIN_MM), GRID_MAX_MM);
}

function loadPrefs() {
  try {
    const raw = JSON.parse(localStorage.getItem(PREFS_KEY) || "null");
    const merged = { ...PREF_DEFAULTS, ...(raw && typeof raw === "object" ? raw : {}) };
    if (raw && typeof raw === "object" && raw.gridMinor == null && raw.gridSpacing != null) {
      merged.gridMinor = clampGridSpacing(raw.gridSpacing);
    }
    if (raw && typeof raw === "object" && raw.gridMajor == null) {
      merged.gridMajor = clampGridSpacing(merged.gridMinor * 10, GRID_DEFAULT_MAJOR_MM);
    }
    if (merged.gridMajor < merged.gridMinor) merged.gridMajor = merged.gridMinor;
    return merged;
  } catch (_error) {
    return { ...PREF_DEFAULTS };
  }
}

let prefs = loadPrefs();
if (prefs.grid === false) gridOn = false;
if (prefs.gridSnap === false) gridSnapOn = false;
if (prefs.gridMinorOn === false) gridMinorOn = false;
prefs.gridHiddenScale = clampHiddenScale(prefs.gridHiddenScale);
prefs.gridMinorStyle = gridMinorStyle();
prefs.gridDotSize = clampDotSize(prefs.gridDotSize);
prefs.gridLineWidth = clampLineWidth(prefs.gridLineWidth);
prefs.displayUnit = displayUnit();

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
const scene = new THREE.Scene();
scene.background = new THREE.Color(0xe4e9ee);

const WORLD_UP = new THREE.Vector3(0, 0, 1);
const ISO_DIR = new THREE.Vector3(1, -1, 1);
const viewUp = new THREE.Vector3(0, 0, 1);
const VIEW_PRESETS = {
  top: { dir: new THREE.Vector3(0, 0, 1), up: new THREE.Vector3(0, 1, 0), label: "Top" },
  bottom: { dir: new THREE.Vector3(0, 0, -1), up: new THREE.Vector3(0, 1, 0), label: "Bottom" },
  front: { dir: new THREE.Vector3(0, -1, 0), up: WORLD_UP, label: "Front" },
  back: { dir: new THREE.Vector3(0, 1, 0), up: WORLD_UP, label: "Back" },
  right: { dir: new THREE.Vector3(1, 0, 0), up: WORLD_UP, label: "Right" },
  left: { dir: new THREE.Vector3(-1, 0, 0), up: WORLD_UP, label: "Left" },
};

const persp = new THREE.PerspectiveCamera(50, 1, 10, 2_000_000);
persp.up.copy(WORLD_UP);
persp.position.copy(ISO_DIR.clone().normalize().multiplyScalar(10000));
const orthoCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 10, 2_000_000);
orthoCam.up.copy(WORLD_UP);
orthoCam.position.copy(persp.position);

const controls = new OrbitControls(orthoCam, canvas);
controls.target.set(0, 0, 0);
controls.mouseButtons.LEFT = -1;
controls.mouseButtons.MIDDLE = THREE.MOUSE.ROTATE;
controls.mouseButtons.RIGHT = THREE.MOUSE.PAN;
// Keep orbit off the Z pole so lookAt(up=+Z) stays well-defined after Top/Bottom.
controls.minPolarAngle = 0.04;
controls.maxPolarAngle = Math.PI - 0.04;
controls.minDistance = 10;
controls.maxDistance = 2_000_000;
controls.update();

const hemi = new THREE.HemisphereLight(0xf4f7fb, 0x6e757c, 0.55);
scene.add(hemi);
const key = new THREE.DirectionalLight(0xffffff, 0.45);
key.position.set(-1.1, 0.85, 1.35);
scene.add(key);
function clampHiddenScale(value) {
  const raw = Number(value);
  if (!Number.isFinite(raw) || raw <= 0) return GRID_HIDDEN_SCALE_DEFAULT;
  const clamped = Math.min(Math.max(raw, GRID_HIDDEN_SCALE_MIN), GRID_HIDDEN_SCALE_MAX);
  return Math.round(clamped * 100) / 100;
}

function hiddenLineScale() {
  return clampHiddenScale(prefs.gridHiddenScale);
}

function clampDotSize(value) {
  const raw = Number(value);
  if (!Number.isFinite(raw) || raw <= 0) return GRID_DOT_SIZE_DEFAULT;
  const clamped = Math.min(Math.max(raw, GRID_DOT_SIZE_MIN), GRID_DOT_SIZE_MAX);
  return Math.round(clamped * 2) / 2;
}

function gridDotSize() {
  return clampDotSize(prefs.gridDotSize);
}

function clampLineWidth(value) {
  const raw = Number(value);
  if (!Number.isFinite(raw) || raw <= 0) return GRID_LINE_WIDTH_DEFAULT;
  const clamped = Math.min(Math.max(raw, GRID_LINE_WIDTH_MIN), GRID_LINE_WIDTH_MAX);
  return Math.round(clamped * 2) / 2;
}

function gridLineWidth() {
  return clampLineWidth(prefs.gridLineWidth);
}

function gridMinorStyle() {
  return prefs.gridMinorStyle === "lines" ? "lines" : "dots";
}

function displayUnit() {
  return UNIT_MM[prefs.displayUnit] ? prefs.displayUnit : "mm";
}

function mmToUnit(mm, unit = displayUnit()) {
  return mm / UNIT_MM[unit];
}

function fromDisplay(value, unit = displayUnit()) {
  const raw = Number(value);
  if (!Number.isFinite(raw)) return NaN;
  return raw * UNIT_MM[unit];
}

function formatGridInput(mm) {
  const unit = displayUnit();
  const value = mmToUnit(mm, unit);
  const decimals = UNIT_DECIMALS[unit];
  const rounded = Number(value.toFixed(decimals));
  return String(rounded);
}

function formatNumber(mm) {
  return formatGridInput(mm);
}

function prefMinorMm() {
  return clampGridSpacing(prefs.gridMinor, GRID_DEFAULT_MINOR_MM);
}

function prefMajorMm() {
  const minor = prefMinorMm();
  return Math.max(clampGridSpacing(prefs.gridMajor, GRID_DEFAULT_MAJOR_MM), minor);
}

function gridAutoOn() {
  return prefs.gridAuto !== false;
}

function niceLength(mm) {
  if (!Number.isFinite(mm) || mm <= 0) return GRID_DEFAULT_MINOR_MM;
  const exp = Math.floor(Math.log10(mm));
  const base = 10 ** exp;
  const n = mm / base;
  const nice = n <= 1.5 ? 1 : n <= 3.5 ? 2 : n <= 7.5 ? 5 : 10;
  return clampGridSpacing(nice * base);
}

function scenePlanBox() {
  const box = new THREE.Box3();
  for (const point of sceneState.points || []) {
    box.expandByPoint(new THREE.Vector3(point.x_mm, point.y_mm, 0));
  }
  return box.isEmpty() ? null : box;
}

function sceneBounds3() {
  const box = new THREE.Box3();
  for (const point of sceneState.points || []) {
    box.expandByPoint(new THREE.Vector3(point.x_mm, point.y_mm, point.z_mm || 0));
  }
  return box.isEmpty() ? null : box;
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

function frameDistance(radius) {
  const aspect = Math.max(canvas.clientWidth, 1) / Math.max(canvas.clientHeight, 1);
  const vFov = (persp.fov * Math.PI) / 360;
  const hFov = Math.atan(Math.tan(vFov) * aspect);
  const fov = Math.min(vFov, hFov);
  return radius / Math.max(Math.tan(fov), 0.05);
}

function resetViewZoom() {
  orthoCam.zoom = 1;
  persp.zoom = 1;
}

function lookAtScene(dir, extras = {}) {
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

function effectiveGrid() {
  const minor0 = prefMinorMm();
  const major0 = prefMajorMm();
  if (!gridAutoOn()) return { minor: minor0, major: major0 };
  const box = scenePlanBox();
  if (!box) return { minor: minor0, major: major0 };
  const size = box.getSize(new THREE.Vector3());
  const span = Math.max(size.x, size.y);
  if (span < minor0 * 2) return { minor: minor0, major: major0 };
  const ratio = Math.max(Math.round(major0 / minor0) || 10, 2);
  const major = niceLength(span / 10);
  const minor = clampGridSpacing(major / ratio, minor0);
  return { minor, major: Math.max(major, minor) };
}

function gridMinorMm() {
  return effectiveGrid().minor;
}

function gridMajorMm() {
  return effectiveGrid().major;
}

function gridReachMm() {
  const major = gridMajorMm();
  const box = scenePlanBox();
  if (!box) return GRID_EXTENT_MM / 2;
  const reach = Math.max(
    Math.abs(box.min.x), Math.abs(box.max.x),
    Math.abs(box.min.y), Math.abs(box.max.y),
  );
  const span = Math.max(box.getSize(new THREE.Vector3()).x, box.getSize(new THREE.Vector3()).y);
  return Math.min(
    Math.max(reach * 1.35, span * 0.7, major * 6, GRID_DEFAULT_MAJOR_MM * 2),
    GRID_EXTENT_MM * 2,
  );
}

function gridLayout(spacing) {
  const reach = gridReachMm();
  let divisions = Math.round((reach * 2) / spacing);
  divisions = Math.max(2, Math.min(divisions, GRID_MAX_DIVISIONS));
  if (divisions % 2 !== 0) divisions += 1;
  return { divisions, size: divisions * spacing };
}

function appendHiddenSpan(from, to, dash, gap, emitSeg, maxSeg) {
  if (dash <= 0) {
    const piece = Math.max(maxSeg || 1000, 100);
    for (let a = from; a < to - 1e-6; a += piece) {
      emitSeg(a, Math.min(a + piece, to));
    }
    return;
  }
  const period = dash + gap;
  const start = Math.floor(from / period) * period;
  for (let s = start; s < to; s += period) {
    const a = Math.max(s, from);
    const b = Math.min(s + dash, to);
    if (b - a > 1e-6) emitSeg(a, b);
  }
}

function onGridStep(value, step) {
  return Math.abs(value - snapToStep(value, step)) < 1e-4;
}

function makeMinorDots(spacing, color, skipStep) {
  const { divisions, size } = gridLayout(spacing);
  const step = size / divisions;
  const half = size / 2;
  const positions = [];
  for (let i = 0, x = -half; i <= divisions; i++, x += step) {
    if (skipStep && onGridStep(x, skipStep)) continue;
    for (let j = 0, y = -half; j <= divisions; j++, y += step) {
      if (skipStep && onGridStep(y, skipStep)) continue;
      positions.push(x, y, 0);
    }
  }
  if (!positions.length) return null;
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  const helper = new THREE.Points(
    geometry,
    new THREE.PointsMaterial({
      color,
      size: gridDotSize(),
      sizeAttenuation: false,
      toneMapped: false,
    }),
  );
  sendBehind(helper, -1);
  return helper;
}

function makeGridHelper(spacing, color, hidden, skipStep) {
  const { divisions, size } = gridLayout(spacing);
  const step = size / divisions;
  const half = size / 2;
  const scale = hidden ? hiddenLineScale() : 0;
  const period = hidden ? spacing * scale : 0;
  const dash = hidden ? period * (2 / 3) : 0;
  const gap = hidden ? period - dash : 0;
  const positions = [];
  for (let i = 0, k = -half; i <= divisions; i++, k += step) {
    if (skipStep && onGridStep(k, skipStep)) continue;
    appendHiddenSpan(-half, half, dash, gap, (a, b) => {
      positions.push(a, 0, k, b, 0, k);
    }, step);
    appendHiddenSpan(-half, half, dash, gap, (a, b) => {
      positions.push(k, 0, a, k, 0, b);
    }, step);
  }
  if (!positions.length) return null;
  const geometry = new LineSegmentsGeometry();
  geometry.setPositions(positions);
  const helper = new LineSegments2(
    geometry,
    new LineMaterial({
      color,
      linewidth: gridLineWidth(),
      worldUnits: false,
      toneMapped: false,
    }),
  );
  helper.rotation.x = Math.PI / 2;
  sendBehind(helper, -1);
  syncGridLineResolution(helper);
  return helper;
}

function makeGrid() {
  const pal = BACKGROUNDS[prefs.background] || BACKGROUNDS.g5;
  const group = new THREE.Group();
  const minor = gridMinorMm();
  const major = gridMajorMm();
  if (gridMinorOn && major > minor + 1e-6) {
    const minorGrid = gridMinorStyle() === "dots"
      ? makeMinorDots(minor, pal.minor, major)
      : makeGridHelper(minor, pal.minor, true, major);
    if (minorGrid) group.add(minorGrid);
  }
  const majorGrid = makeGridHelper(major, pal.major, false);
  if (majorGrid) group.add(majorGrid);
  group.visible = gridOn;
  return group;
}

function disposeObject(object) {
  if (!object) return;
  object.traverse((node) => {
    if (node.geometry) node.geometry.dispose();
    for (const mat of [].concat(node.material || [])) {
      if (mat) mat.dispose();
    }
  });
}

function rebuildGrid() {
  const next = makeGrid();
  if (grid) {
    scene.remove(grid);
    disposeObject(grid);
  }
  grid = next;
  scene.add(grid);
  syncGridLineResolution(grid);
}

function syncGridLineResolution(root = grid) {
  if (!root) return;
  const width = Math.max(canvas.clientWidth, 1);
  const height = Math.max(canvas.clientHeight, 1);
  root.traverse((node) => {
    if (node.material && node.material.resolution) {
      node.material.resolution.set(width, height);
    }
  });
}

function setGridSpacing(minor, major) {
  prefs.gridAuto = false;
  prefs.gridMinor = clampGridSpacing(minor, GRID_DEFAULT_MINOR_MM);
  if (major != null) prefs.gridMajor = clampGridSpacing(major, GRID_DEFAULT_MAJOR_MM);
  if (prefs.gridMajor < prefs.gridMinor) prefs.gridMajor = prefs.gridMinor;
  savePrefs();
  rebuildGrid();
  refreshToggles();
  if (lastPointer) updateGhost(lastPointer);
  setHint(`Grid ${formatLength(gridMinorMm())} / ${formatLength(gridMajorMm())}.`);
}

function setGridAuto(next) {
  prefs.gridAuto = Boolean(next);
  savePrefs();
  rebuildGrid();
  refreshToggles();
  setHint(prefs.gridAuto
    ? `Grid auto ${formatLength(gridMinorMm())} / ${formatLength(gridMajorMm())}.`
    : "Grid spacing is manual.");
}

function setGridMinorOn(next) {
  gridMinorOn = next;
  prefs.gridMinorOn = next;
  savePrefs();
  rebuildGrid();
  refreshToggles();
  setHint(gridMinorOn ? "Minor grid on." : "Minor grid off.");
}

function setGridHiddenScale(next, opts = {}) {
  prefs.gridHiddenScale = clampHiddenScale(next);
  savePrefs();
  rebuildGrid();
  syncGridPrefsForm();
  if (!opts.silent) setHint(`Hidden line scale ${hiddenLineScale()}.`);
}

function setGridMinorStyle(next) {
  prefs.gridMinorStyle = next === "lines" ? "lines" : "dots";
  savePrefs();
  rebuildGrid();
  syncGridPrefsForm();
  setHint(prefs.gridMinorStyle === "dots" ? "Minor grid: dots." : "Minor grid: lines.");
}

function setGridDotSize(next, opts = {}) {
  prefs.gridDotSize = clampDotSize(next);
  savePrefs();
  const size = gridDotSize();
  let updated = false;
  if (grid) {
    grid.traverse((node) => {
      if (node.isPoints && node.material) {
        node.material.size = size;
        updated = true;
      }
    });
  }
  if (!updated && gridMinorStyle() === "dots") rebuildGrid();
  syncGridPrefsForm();
  if (!opts.silent) setHint(`Dot size ${size} px.`);
}

function setGridLineWidth(next, opts = {}) {
  prefs.gridLineWidth = clampLineWidth(next);
  savePrefs();
  const width = gridLineWidth();
  let updated = false;
  if (grid) {
    grid.traverse((node) => {
      if (node.material && node.material.linewidth != null) {
        node.material.linewidth = width;
        updated = true;
      }
    });
  }
  if (!updated) rebuildGrid();
  syncGridPrefsForm();
  if (!opts.silent) setHint(`Line thickness ${width} px.`);
}

function setDisplayUnit(next) {
  prefs.displayUnit = UNIT_MM[next] ? next : "mm";
  savePrefs();
  refreshToggles();
  if (lastPointer) updateGhost(lastPointer);
  setHint(`Units ${displayUnit()}.`);
}

function syncGridMenu() {
  const minorOnEl = document.getElementById("grid-minor-on");
  if (minorOnEl) minorOnEl.checked = gridMinorOn;
}

function syncGridPrefsForm() {
  const showEl = document.getElementById("gpref-show");
  if (!showEl) return;
  showEl.checked = gridOn;
  document.getElementById("gpref-minor-on").checked = gridMinorOn;
  document.getElementById("gpref-snap").checked = gridSnapOn;
  const autoEl = document.getElementById("gpref-auto");
  if (autoEl) autoEl.checked = gridAutoOn();
  const styleEl = document.getElementById("gpref-minor-style");
  if (styleEl && document.activeElement !== styleEl) styleEl.value = gridMinorStyle();
  const unitEl = document.getElementById("gpref-unit");
  if (unitEl && document.activeElement !== unitEl) unitEl.value = displayUnit();
  const dots = gridMinorStyle() === "dots";
  const dotOpts = document.getElementById("gpref-dot-opts");
  const lineOpts = document.getElementById("gpref-line-opts");
  if (dotOpts) dotOpts.hidden = !dots;
  if (lineOpts) lineOpts.hidden = dots;
  const unit = displayUnit();
  const step = UNIT_STEP[unit];
  const min = mmToUnit(GRID_MIN_MM);
  const max = mmToUnit(GRID_MAX_MM);
  const minorEl = document.getElementById("gpref-minor");
  const majorEl = document.getElementById("gpref-major");
  for (const el of [minorEl, majorEl]) {
    el.min = String(min);
    el.max = String(max);
    el.step = String(step);
    el.disabled = gridAutoOn();
  }
  if (document.activeElement !== minorEl) minorEl.value = formatGridInput(gridMinorMm());
  if (document.activeElement !== majorEl) majorEl.value = formatGridInput(gridMajorMm());
  const scaleEl = document.getElementById("gpref-hidden-scale");
  const scaleNum = document.getElementById("gpref-hidden-scale-num");
  const scale = hiddenLineScale();
  if (document.activeElement !== scaleEl) scaleEl.value = String(scale);
  if (document.activeElement !== scaleNum) scaleNum.value = String(scale);
  const dotEl = document.getElementById("gpref-dot-size");
  const dotNum = document.getElementById("gpref-dot-size-num");
  const size = gridDotSize();
  if (dotEl && document.activeElement !== dotEl) dotEl.value = String(size);
  if (dotNum && document.activeElement !== dotNum) dotNum.value = String(size);
  const widthEl = document.getElementById("gpref-line-width");
  const widthNum = document.getElementById("gpref-line-width-num");
  const width = gridLineWidth();
  if (widthEl && document.activeElement !== widthEl) widthEl.value = String(width);
  if (widthNum && document.activeElement !== widthNum) widthNum.value = String(width);
  for (const button of document.querySelectorAll("[data-grid-minor]")) {
    button.textContent = `${formatGridInput(Number(button.dataset.gridMinor))} / ${formatGridInput(Number(button.dataset.gridMajor))}`;
  }
  const placeholder = document.getElementById("console-input");
  if (placeholder) placeholder.placeholder = `length ${unit} · angle ° · Enter`;
}

let grid = null;
const contact = new THREE.Mesh(
  new THREE.PlaneGeometry(40000, 40000),
  new THREE.MeshBasicMaterial({
    color: 0x000000,
    transparent: true,
    opacity: 0.06,
    depthWrite: false,
  }),
);
contact.position.z = -2;
contact.renderOrder = -2;
scene.add(contact);
scene.add(new THREE.AxesHelper(3000));
const draft = new THREE.Group();
const ghosts = new THREE.Group();
scene.add(draft);
scene.add(ghosts);

function sendBehind(object, order) {
  object.renderOrder = order;
  const materials = [].concat(object.material || []);
  for (const mat of materials) {
    if (!mat) continue;
    mat.depthTest = false;
    mat.depthWrite = false;
  }
}

rebuildGrid();
draft.renderOrder = 1;
ghosts.renderOrder = 2;

function camera() {
  return useOrtho ? orthoCam : persp;
}

function applyCameraPose(position, target, up) {
  if (up) viewUp.copy(up);
  const src = camera();
  const dst = useOrtho ? persp : orthoCam;
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

let viewSize = { w: 0, h: 0 };

function syncCameras() {
  const src = camera();
  const dst = useOrtho ? persp : orthoCam;
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
  }
  syncGridLineResolution();
}

function syncViewMenu() {
  const mark = (cmd, on) => {
    const el = document.querySelector(`[data-cmd="${cmd}"]`);
    if (el) el.classList.toggle("is-on", on);
  };
  mark("perspective", projection === "perspective");
  mark("parallel", projection === "parallel");
  for (const name of Object.keys(VIEW_PRESETS)) {
    mark(`view-${name}`, namedView === name);
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

function bindProjectionCamera(opts = {}) {
  const dst = camera();
  dst.up.copy(viewUp);
  controls.object = dst;
  const named = namedView && VIEW_PRESETS[namedView];
  projButton.classList.toggle("active", useOrtho);
  projButton.title = named
    ? `${named.label} (O perspective / parallel)`
    : useOrtho ? "Parallel (O)" : "Perspective (O)";
  setOrbitPoleLimit(Boolean(namedView));
  syncCameras();
  if (!opts.deferUpdate) controls.update();
  syncViewMenu();
}

function setProjectionMode(mode, extras = {}) {
  if (mode === "orthographic") {
    goNamedView(namedView || "top");
    return;
  }
  const leavingNamed = namedView;
  namedView = null;
  projection = mode;
  useOrtho = mode !== "perspective";
  const hint = mode === "perspective" ? "Perspective." : "Parallel.";
  if (leavingNamed) {
    viewUp.copy(WORLD_UP);
    const dir = camera().position.clone().sub(controls.target);
    bindProjectionCamera();
    goToView(dir, { up: WORLD_UP.clone() });
    if (!extras.silent) setHint(hint);
    return;
  }
  viewUp.copy(WORLD_UP);
  const src = useOrtho ? persp : orthoCam;
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

function releaseNamedViewForOrbit() {
  if (!namedView) return;
  const leaving = namedView;
  namedView = null;
  viewAnim = null;
  if (projection === "orthographic") {
    projection = "parallel";
    useOrtho = true;
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

function goNamedView(name) {
  const preset = VIEW_PRESETS[name];
  if (!preset) return;
  namedView = name;
  projection = "orthographic";
  useOrtho = true;
  viewUp.copy(preset.up);
  bindProjectionCamera({ deferUpdate: true });
  goToView(preset.dir.clone(), { up: preset.up.clone(), axis: true });
  setHint(`${preset.label} view.`);
}

function namedViewFromDir(dir) {
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
}

function tickViewAnim() {
  if (!viewAnim) return;
  const u = Math.min(1, (performance.now() - viewAnim.t0) / viewAnim.ms);
  const s = u * u * (3 - 2 * u);
  const target = viewAnim.fromTarget.clone().lerp(viewAnim.toTarget, s);
  const offset = slerpOffset(viewAnim.fromOffset, viewAnim.toOffset, s);
  applyCameraPose(target.clone().add(offset), target, viewAnim.up);
  syncCameras();
  if (u >= 1) {
    const endTarget = viewAnim.toTarget;
    const endPos = endTarget.clone().add(viewAnim.toOffset);
    applyCameraPose(endPos, endTarget, viewAnim.up);
    setOrbitPoleLimit(viewAnim.axis);
    syncCameras();
    controls.update();
    applyCameraPose(endPos, endTarget, viewAnim.up);
    syncCameras();
    viewAnim = null;
  }
}

function fitView() {
  let dir = namedView ? VIEW_PRESETS[namedView].dir.clone() : camera().position.clone().sub(controls.target);
  if (dir.lengthSq() < 1e-8) dir.copy(ISO_DIR);
  lookAtScene(dir, { up: viewUp.clone(), axis: Boolean(namedView) });
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
  const dir = viewDirFromCubePoint(hit.point);
  const name = namedViewFromDir(dir);
  if (name) goNamedView(name);
  else {
    namedView = null;
    if (projection === "orthographic") {
      projection = "parallel";
      useOrtho = true;
      bindProjectionCamera();
    }
    viewUp.copy(WORLD_UP);
    goToView(dir, { up: WORLD_UP.clone() });
    syncViewMenu();
  }
});
cubeCanvas.addEventListener("pointermove", (event) => {
  cubeCanvas.style.cursor = pickCube(event) ? "pointer" : "default";
});
cubeCanvas.addEventListener("contextmenu", (event) => event.preventDefault());
document.getElementById("view-iso").addEventListener("click", () => {
  namedView = null;
  if (projection === "orthographic") {
    projection = "parallel";
    useOrtho = true;
  }
  viewUp.copy(WORLD_UP);
  bindProjectionCamera();
  lookAtScene(ISO_DIR, { up: WORLD_UP.clone() });
  setHint("ISO (Front–Right).");
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
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  return Boolean(event.target && event.target.closest && event.target.closest("dialog"));
}

function refreshToggles() {
  snapButton.classList.toggle("active", snapOn);
  gridSnapButton.classList.toggle("active", gridSnapOn);
  orthoButton.classList.toggle("active", orthoOn);
  gridButton.classList.toggle("active", gridOn);
  const parts = [];
  if (snapOn) parts.push("SNAP");
  if (gridSnapOn) parts.push(`GRIDSNAP ${formatNumber(gridMinorMm())}/${formatNumber(gridMajorMm())}`);
  if (orthoOn) parts.push("ORTHO");
  if (gridOn) parts.push("GRID");
  if (tool === "select") {
    const names = {
      point: "POINT", line: "LINE", face: "FACE", solid: "SOLID", element: "ELEMENT",
    };
    parts.push(names[selectFilter] || "ELEMENT");
  }
  const typed = activeLength();
  if (typed !== null) parts.push(formatLength(typed));
  status.textContent = parts.join(" · ") || "free";
  grid.visible = gridOn;
  syncGridMenu();
  syncGridPrefsForm();
}

function labelValue() {
  const value = labelInput.value.trim();
  return value === "" ? null : value;
}

function fieldLength() {
  return parseLength(typedText());
}

function activeLength() {
  return fieldLength();
}

function bufferLength() {
  return fieldLength();
}

function sidesValue() {
  return 6;
}

function arrayCount() {
  return 4;
}

function parseLength(text) {
  const match = String(text || "").trim().match(/^([+-]?\d+(?:\.\d+)?)\s*(mm|cm|m|in|")?$/i);
  if (!match) return null;
  const n = Number(match[1]);
  if (!Number.isFinite(n) || n <= 0) return null;
  const suffix = match[2] ? match[2].toLowerCase() : displayUnit();
  const key = suffix === '"' ? "in" : suffix;
  const factor = UNIT_MM[key];
  if (!factor) return null;
  return n * factor;
}

function formatLength(mm) {
  if (!Number.isFinite(mm)) return "—";
  return `${formatNumber(mm)} ${displayUnit()}`;
}

function formatMm(value) {
  return formatLength(value);
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
}

function setCoords(hit, origin) {
  if (!hit) {
    coordsEl.textContent = `X 0   Y 0   Z 0   ${displayUnit()}`;
    return;
  }
  const x = formatNumber(hit.x_mm);
  const y = formatNumber(hit.y_mm);
  const z = formatNumber(hit.z_mm || 0);
  let text = `X ${x}   Y ${y}   Z ${z}   ${displayUnit()}`;
  if (origin) {
    const dx = hit.x_mm - origin.x_mm;
    const dy = hit.y_mm - origin.y_mm;
    const length = dist3(origin, hit);
    const ang = Math.atan2(dy, dx);
    text += `    ΔX ${formatNumber(dx)}   ΔY ${formatNumber(dy)}    L ${formatLength(length)}    ${formatDeg(ang)}`;
  }
  coordsEl.textContent = text;
}

function parseCssHex(value, fallback) {
  const raw = String(value || "").replace("#", "").trim();
  const hex = raw.length === 3
    ? raw.split("").map((ch) => ch + ch).join("")
    : raw;
  const parsed = Number.parseInt(hex, 16);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function clayHex() {
  const value = Math.max(80, Math.min(230, Number(prefs.clay) || 176));
  return (value << 16) | (value << 8) | value;
}

function curveIdle() {
  return parseCssHex(prefs.curve, EDGE_COLOR);
}

function isPicked(entityId) {
  return entityId != null && selectedIds.has(entityId);
}

function selectionTints(entityId) {
  if (entityId == null) return false;
  if (isPicked(entityId)) return true;
  const owner = owningSolidId(entityId);
  return owner != null && isPicked(owner);
}

function curveFor(entityId) {
  if (selectionTints(entityId)) return CURVE_PICK;
  if (entityId != null && cutterIds.has(entityId)) return CURVE_HOVER;
  return curveIdle();
}

function lineOverlay(entityId) {
  return selectFilter === "line" || isPicked(entityId);
}

function clayMat(preview, opacity, entityId = null) {
  return new THREE.MeshLambertMaterial({
    color: preview || selectionTints(entityId) ? CURVE_PICK : clayHex(),
    transparent: preview || opacity < 0.99,
    opacity,
    side: THREE.DoubleSide,
  });
}

function addEdgeOverlay(group, mesh, entityId, preview) {
  if (preview || !prefs.showEdges) return;
  const edges = new THREE.LineSegments(
    new THREE.EdgesGeometry(mesh.geometry),
    new THREE.LineBasicMaterial({ color: EDGE_COLOR }),
  );
  edges.position.copy(mesh.position);
  edges.quaternion.copy(mesh.quaternion);
  mark(edges, entityId);
  group.add(edges);
}

function addCurve(group, pts, color = curveIdle(), entityId = null) {
  if (pts.length < 2) return;
  if (group !== ghosts && !prefs.showCurves) return;
  const overlay = group !== ghosts && lineOverlay(entityId);
  const line = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(
      pts.map((point) => {
        const p = xyzMm(point);
        return new THREE.Vector3(p.x_mm, p.y_mm, p.z_mm);
      }),
    ),
    new THREE.LineBasicMaterial({ color, depthTest: !overlay }),
  );
  line.renderOrder = overlay ? 12 : 0;
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

function addVolume(group, origin, size, color, opacity, entityId = null) {
  const preview = group === ghosts;
  const mesh = new THREE.Mesh(
    new THREE.BoxGeometry(size[0], size[1], size[2]),
    clayMat(preview, opacity, entityId),
  );
  mesh.position.set(origin[0] + size[0] / 2, origin[1] + size[1] / 2, origin[2] + size[2] / 2);
  mark(mesh, entityId);
  if (!preview && !prefs.showFaces) mesh.visible = false;
  group.add(mesh);
  addEdgeOverlay(group, mesh, entityId, preview);
}

function addCylinder(group, cx, cy, radius, originZ, height, color, opacity, entityId = null) {
  const preview = group === ghosts;
  const mesh = new THREE.Mesh(
    new THREE.CylinderGeometry(radius, radius, Math.max(Math.abs(height), 1), 48),
    clayMat(preview, opacity, entityId),
  );
  mesh.rotation.x = Math.PI / 2;
  mesh.position.set(cx, cy, originZ + height / 2);
  mark(mesh, entityId);
  if (!preview && !prefs.showFaces) mesh.visible = false;
  group.add(mesh);
  addEdgeOverlay(group, mesh, entityId, preview);
}

function addFaceGraphic(group, pts, { fill = true, opacity = 0.92, entityId = null, color = null } = {}) {
  if (pts.length < 3) return;
  const preview = group === ghosts;
  const z = (Number.isFinite(pts[0].z_mm) ? pts[0].z_mm : 0) + 20;
  if (fill && (preview || prefs.showFaces)) {
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
      clayMat(preview, preview ? opacity : 0.92, entityId),
    );
    if (preview && color != null) mesh.material.color.setHex(color);
    mesh.renderOrder = 2;
    mark(mesh, entityId);
    group.add(mesh);
  }
  if (!preview && !prefs.showEdges && !prefs.showCurves) return;
  const loop = pts.map((point) => new THREE.Vector3(point.x_mm, point.y_mm, z + 8));
  loop.push(loop[0].clone());
  const outline = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(loop),
    new THREE.LineBasicMaterial({
      color: preview ? (color ?? curveIdle()) : EDGE_COLOR,
    }),
  );
  mark(outline, entityId);
  group.add(outline);
}

function xyzMm(point) {
  const x = Number(point.x_mm);
  const y = Number(point.y_mm);
  const z = Number(point.z_mm);
  return {
    x_mm: Number.isFinite(x) ? x : 0,
    y_mm: Number.isFinite(y) ? y : 0,
    z_mm: Number.isFinite(z) ? z : 0,
  };
}

function addPlanarFace(group, pts, entityId) {
  if (pts.length < 3) return;
  const preview = group === ghosts;
  const world = pts.map(xyzMm);
  if (preview || prefs.showFaces) {
    const vertices = [];
    const origin = world[0];
    for (let i = 1; i < world.length - 1; i += 1) {
      vertices.push(
        origin.x_mm, origin.y_mm, origin.z_mm,
        world[i].x_mm, world[i].y_mm, world[i].z_mm,
        world[i + 1].x_mm, world[i + 1].y_mm, world[i + 1].z_mm,
      );
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(vertices, 3));
    geometry.computeVertexNormals();
    const mesh = new THREE.Mesh(geometry, clayMat(preview, preview ? 0.22 : 1, entityId));
    mesh.renderOrder = 1;
    mark(mesh, entityId);
    group.add(mesh);
  }
  if ((preview || prefs.showEdges || prefs.showCurves) && (preview || selectFilter !== "line")) {
    const loop = world.map((point) => new THREE.Vector3(point.x_mm, point.y_mm, point.z_mm));
    loop.push(loop[0].clone());
    const outline = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(loop),
      new THREE.LineBasicMaterial({
        color: preview ? CURVE_PICK : (selectionTints(entityId) ? CURVE_PICK : EDGE_COLOR),
      }),
    );
    mark(outline, entityId);
    group.add(outline);
  }
}

function addSolidPrism(group, solid, byId) {
  const face = (sceneState.faces || []).find((item) => item.entity_id === solid.face_id);
  if (!face) return false;
  const base = face.point_ids.map((id) => byId.get(id)).filter(Boolean);
  const cap = (sceneState.faces || []).find((item) => item.entity_id === solid.cap_id);
  const lid = cap
    ? cap.point_ids.map((id) => byId.get(id)).filter(Boolean)
    : [];
  if (base.length < 3 || lid.length !== base.length) return false;
  addPlanarFace(group, base, face.entity_id);
  addPlanarFace(group, lid, cap.entity_id);
  const walls = solid.wall_ids || [];
  for (let i = 0; i < base.length; i += 1) {
    const j = (i + 1) % base.length;
    addPlanarFace(group, [base[i], base[j], lid[j], lid[i]], walls[i] ?? solid.entity_id);
  }
  return true;
}

function addSolidVolumeFallback(group, solid, byId) {
  const face = (sceneState.faces || []).find((item) => item.entity_id === solid.face_id);
  if (!face) return;
  const pts = face.point_ids.map((id) => byId.get(id)).filter(Boolean).map(xyzMm);
  if (!pts.length) return;
  const height = Math.abs(solid.distance_mm) || 1;
  const xs = pts.map((p) => p.x_mm);
  const ys = pts.map((p) => p.y_mm);
  const zs = pts.map((p) => p.z_mm);
  const originZ = solid.distance_mm >= 0 ? Math.min(...zs) : Math.min(...zs) - height;
  addVolume(
    group,
    [Math.min(...xs), Math.min(...ys), originZ],
    [
      Math.max(Math.max(...xs) - Math.min(...xs), 1),
      Math.max(Math.max(...ys) - Math.min(...ys), 1),
      Math.max(height, 1),
    ],
    clayHex(),
    1,
    solid.entity_id,
  );
}

function addVertexDot(group, point) {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute(
    "position",
    new THREE.Float32BufferAttribute([point.x_mm, point.y_mm, point.z_mm], 3),
  );
  const picked = isPicked(point.entity_id);
  const material = new THREE.PointsMaterial({
    color: picked ? CURVE_PICK : EDGE_COLOR,
    size: selectFilter === "point" || picked ? 11 : 8,
    sizeAttenuation: false,
    depthTest: false,
    depthWrite: false,
  });
  const dot = new THREE.Points(geometry, material);
  dot.renderOrder = 20;
  dot.raycast = () => {};
  mark(dot, point.entity_id);
  group.add(dot);
}

function rebuild() {
  draft.clear();
  committedDims = [];
  indexBrepParents();
  const byId = new Map((sceneState.points || []).map((point) => [point.entity_id, point]));
  for (const line of sceneState.lines || []) {
    if (hiddenIds.has(line.entity_id)) continue;
    const start = byId.get(line.start_id);
    const end = byId.get(line.end_id);
    if (!start || !end) continue;
    if (prefs.showCurves) {
      const overlay = lineOverlay(line.entity_id);
      const a = xyzMm(start);
      const b = xyzMm(end);
      const drawn = new THREE.Line(new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(a.x_mm, a.y_mm, a.z_mm),
        new THREE.Vector3(b.x_mm, b.y_mm, b.z_mm),
      ]), new THREE.LineBasicMaterial({
        color: curveFor(line.entity_id),
        depthTest: !overlay,
      }));
      drawn.renderOrder = overlay ? 12 : 0;
      mark(drawn, line.entity_id);
      draft.add(drawn);
    }
  }
  for (const polyline of sceneState.polylines || []) {
    if (hiddenIds.has(polyline.entity_id)) continue;
    const pts = polyline.point_ids.map((id) => byId.get(id)).filter(Boolean);
    if (pts.length < 2) continue;
    if (!prefs.showCurves) continue;
    const overlay = lineOverlay(polyline.entity_id);
    const vectors = pts.map((point) => {
      const p = xyzMm(point);
      return new THREE.Vector3(p.x_mm, p.y_mm, p.z_mm);
    });
    if (polyline.closed) vectors.push(vectors[0].clone());
    const drawn = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(vectors),
      new THREE.LineBasicMaterial({
        color: curveFor(polyline.entity_id),
        depthTest: !overlay,
      }),
    );
    drawn.renderOrder = overlay ? 12 : 0;
    mark(drawn, polyline.entity_id);
    draft.add(drawn);
  }
  const extruded = new Set();
  for (const solid of sceneState.solids || []) {
    extruded.add(solid.face_id);
    if (solid.cap_id) extruded.add(solid.cap_id);
    for (const wallId of solid.wall_ids || []) extruded.add(wallId);
  }
  for (const face of sceneState.faces || []) {
    if (hiddenIds.has(face.entity_id) || extruded.has(face.entity_id)) continue;
    const pts = face.point_ids.map((id) => byId.get(id)).filter(Boolean);
    addFaceGraphic(draft, pts, {
      fill: true,
      opacity: 0.92,
      entityId: face.entity_id,
    });
  }
  for (const circle of sceneState.circles || []) {
    if (hiddenIds.has(circle.entity_id)) continue;
    const center = byId.get(circle.center_id);
    if (!center) continue;
    const loop = sampleCircle(center, circle.radius_mm);
    const showFill = !extruded.has(circle.entity_id)
      || selectedIds.has(circle.entity_id)
      || selectFilter === "face";
    addFaceGraphic(draft, loop.slice(0, -1), {
      fill: showFill,
      opacity: 0.92,
      entityId: circle.entity_id,
    });
  }
  for (const arc of sceneState.arcs || []) {
    if (hiddenIds.has(arc.entity_id)) continue;
    const start = byId.get(arc.start_id);
    const midPt = byId.get(arc.mid_id);
    const end = byId.get(arc.end_id);
    if (!start || !midPt || !end) continue;
    addCurve(draft, sampleArc(start, midPt, end), curveFor(arc.entity_id), arc.entity_id);
  }
  for (const ellipse of sceneState.ellipses || []) {
    if (hiddenIds.has(ellipse.entity_id)) continue;
    const center = byId.get(ellipse.center_id);
    if (!center) continue;
    const loop = sampleEllipse(center, ellipse.radius_x_mm, ellipse.radius_y_mm);
    const showFill = !extruded.has(ellipse.entity_id)
      || selectedIds.has(ellipse.entity_id)
      || selectFilter === "face";
    addFaceGraphic(draft, loop.slice(0, -1), {
      fill: showFill,
      opacity: 0.92,
      entityId: ellipse.entity_id,
    });
  }
  for (const bezier of sceneState.beziers || []) {
    if (hiddenIds.has(bezier.entity_id)) continue;
    const pts = bezier.point_ids.map((id) => byId.get(id)).filter(Boolean);
    if (pts.length !== 4) continue;
    addCurve(draft, sampleBezier(pts), curveFor(bezier.entity_id), bezier.entity_id);
  }
  for (const box of sceneState.boxes || []) {
    if (hiddenIds.has(box.entity_id)) continue;
    addVolume(draft, box.origin_xyz_mm, box.size_xyz_mm, clayHex(), 1, box.entity_id);
  }
  for (const solid of sceneState.solids || []) {
    if (hiddenIds.has(solid.entity_id)) continue;
    const color = clayHex();
    const circle = (sceneState.circles || []).find((item) => item.entity_id === solid.face_id);
    const ellipse = (sceneState.ellipses || []).find((item) => item.entity_id === solid.face_id);
    const height = Math.abs(solid.distance_mm);
    if (circle) {
      const center = byId.get(circle.center_id);
      if (!center) continue;
      const originZ = solid.distance_mm >= 0 ? center.z_mm : center.z_mm - height;
      addCylinder(draft, center.x_mm, center.y_mm, circle.radius_mm, originZ, height, color, 1, solid.entity_id);
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
        1,
        solid.entity_id,
      );
      continue;
    }
    addSolidPrism(draft, solid, byId) || addSolidVolumeFallback(draft, solid, byId);
  }
  for (const point of sceneState.points || []) {
    if (!prefs.showCurves || hiddenIds.has(point.entity_id)) continue;
    addVertexDot(draft, point);
  }
  indexBrepParents();
  refreshDocks();
  rebuildGrid();
}

async function refreshFrom(payload) {
  sceneState = payload;
  try {
    rebuild();
  } catch (error) {
    console.error(error);
    try {
      indexBrepParents();
      refreshDocks();
    } catch (_ignored) { /* docks need a valid catalog */ }
    setHint(`draw error: ${error.message}`);
  }
}

function catalog() {
  const rows = [];
  const push = (kind, item) => {
    rows.push({
      id: item.entity_id,
      kind,
      name: item.label || brepKind(kind),
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

function brepKind(kind) {
  if (kind === "Point") return "Vertex";
  if (kind === "Line") return "Edge";
  return kind;
}

function lineConnecting(a, b) {
  return (sceneState.lines || []).find((line) => (
    (line.start_id === a && line.end_id === b)
    || (line.start_id === b && line.end_id === a)
  )) || null;
}

function brepChildren(row) {
  const byId = new Map(catalog().map((item) => [item.id, item]));
  const take = (id) => byId.get(id) || null;
  if (row.kind === "Solid") {
    const kids = [];
    const profile = take(row.item.face_id);
    if (profile) kids.push(profile);
    const cap = take(row.item.cap_id);
    if (cap) kids.push(cap);
    for (const wallId of row.item.wall_ids || []) {
      const wall = take(wallId);
      if (wall) kids.push(wall);
    }
    return kids;
  }
  if (row.kind === "Face") {
    const ids = row.item.point_ids || [];
    if (ids.length < 2) return ids.map(take).filter(Boolean);
    const edges = [];
    for (let i = 0; i < ids.length; i += 1) {
      const line = lineConnecting(ids[i], ids[(i + 1) % ids.length]);
      if (!line) return ids.map(take).filter(Boolean);
      edges.push(byId.get(line.entity_id));
    }
    return edges.filter(Boolean);
  }
  if (row.kind === "Line") {
    return [take(row.item.start_id), take(row.item.end_id)].filter(Boolean);
  }
  if (row.kind === "Circle" || row.kind === "Ellipse") {
    const center = take(row.item.center_id);
    return center ? [center] : [];
  }
  if (row.kind === "Arc") {
    return [take(row.item.start_id), take(row.item.mid_id), take(row.item.end_id)].filter(Boolean);
  }
  if (row.kind === "Polyline" || row.kind === "Bezier") {
    return (row.item.point_ids || []).map(take).filter(Boolean);
  }
  return [];
}

function collectNested(row, nested) {
  for (const child of brepChildren(row)) {
    nested.add(child.id);
    collectNested(child, nested);
  }
}

function brepRoots() {
  const rows = catalog();
  const nested = new Set();
  for (const row of rows) collectNested(row, nested);
  const rank = {
    Solid: 0, Box: 1, Face: 2, Circle: 2, Ellipse: 2,
    Polyline: 3, Bezier: 3, Arc: 3, Line: 4, Point: 5,
  };
  return rows
    .filter((row) => !nested.has(row.id))
    .sort((a, b) => (rank[a.kind] ?? 9) - (rank[b.kind] ?? 9) || a.id - b.id);
}

function indexBrepParents() {
  brepParent = new Map();
  for (const row of catalog()) {
    for (const child of brepChildren(row)) {
      if (child && child.id != null) brepParent.set(child.id, row.id);
    }
  }
}

function rootId(id) {
  let current = id;
  const seen = new Set();
  while (brepParent.has(current) && !seen.has(current)) {
    seen.add(current);
    current = brepParent.get(current);
  }
  return current;
}

function owningSolidId(id) {
  let current = id;
  const seen = new Set();
  while (current != null && !seen.has(current)) {
    const row = findRecord(current);
    if (row && FILTER_KINDS.solid.has(row.kind)) return current;
    seen.add(current);
    current = brepParent.get(current);
  }
  return null;
}

const collapsedTree = new Set();

function renderTreeNode(row, parent) {
  const kids = brepChildren(row);
  const node = document.createElement("div");
  node.className = "tree-node";
  const rowEl = document.createElement("div");
  const dimmed = hiddenIds.has(row.id);
  rowEl.className = `tree-row${selectedIds.has(row.id) ? " selected" : ""}${dimmed ? " dimmed" : ""}`;
  rowEl.dataset.id = String(row.id);
  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "tree-toggle";
  toggle.tabIndex = -1;
  if (kids.length) {
    const collapsed = collapsedTree.has(row.id);
    toggle.innerHTML = collapsed
      ? '<svg viewBox="0 0 24 24"><path d="M9 6 L15 12 L9 18"/></svg>'
      : '<svg viewBox="0 0 24 24"><path d="M6 9 L12 15 L18 9"/></svg>';
    toggle.addEventListener("click", (event) => {
      event.stopPropagation();
      if (collapsedTree.has(row.id)) collapsedTree.delete(row.id);
      else collapsedTree.add(row.id);
      refreshDocks();
    });
  } else {
    toggle.style.visibility = "hidden";
  }
  const kindEl = document.createElement("span");
  kindEl.className = "tree-kind";
  kindEl.textContent = brepKind(row.kind);
  const nameEl = document.createElement("span");
  nameEl.className = "tree-name";
  nameEl.textContent = row.item.label || brepKind(row.kind);
  rowEl.append(toggle, kindEl, nameEl);
  rowEl.addEventListener("click", (event) => setSelection(row.id, { shift: event.shiftKey }));
  rowEl.addEventListener("dblclick", (event) => {
    event.preventDefault();
    beginRename(row, rowEl);
  });
  rowEl.addEventListener("contextmenu", (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (!selectedIds.has(row.id)) setSelection(row.id);
    openTreeMenu(event.clientX, event.clientY, row);
  });
  node.append(rowEl);
  if (kids.length && !collapsedTree.has(row.id)) {
    const branch = document.createElement("div");
    branch.className = "tree-kids";
    for (const child of kids) renderTreeNode(child, branch);
    node.append(branch);
  }
  parent.append(node);
}

const ctxMenu = document.getElementById("ctx-menu");
let ctxRow = null;

function closeTreeMenu() {
  ctxMenu.classList.remove("open");
  ctxMenu.hidden = true;
  ctxRow = null;
}

function openTreeMenu(x, y, row) {
  ctxRow = row;
  const hidden = hiddenIds.has(row.id);
  const kids = brepChildren(row);
  ctxMenu.innerHTML = "";
  const addItem = (label, cmd, shortcut = "") => {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.treeCmd = cmd;
    button.innerHTML = shortcut ? `${label} <kbd>${shortcut}</kbd>` : label;
    ctxMenu.append(button);
  };
  addItem("Select", "select");
  addItem("Rename", "rename", "F2");
  addItem("Duplicate", "duplicate");
  addItem(hidden ? "Show" : "Hide", hidden ? "show" : "hide");
  addItem("Fit", "fit");
  const sep = document.createElement("div");
  sep.className = "menu-sep";
  ctxMenu.append(sep);
  if (kids.length) addItem(collapsedTree.has(row.id) ? "Expand" : "Collapse", "toggle");
  addItem("Delete", "delete", "Del");
  ctxMenu.hidden = false;
  ctxMenu.classList.add("open");
  const pad = 6;
  const rect = ctxMenu.getBoundingClientRect();
  const left = Math.min(x, window.innerWidth - rect.width - pad);
  const top = Math.min(y, window.innerHeight - rect.height - pad);
  ctxMenu.style.left = `${Math.max(pad, left)}px`;
  ctxMenu.style.top = `${Math.max(pad, top)}px`;
}

ctxMenu.addEventListener("click", (event) => {
  const button = event.target.closest("[data-tree-cmd]");
  if (!button || !ctxRow) return;
  event.stopPropagation();
  const row = ctxRow;
  const cmd = button.dataset.treeCmd;
  closeTreeMenu();
  runTreeCommand(cmd, row);
});

function hideSubtree(row, hide) {
  const ids = new Set([row.id]);
  collectNested(row, ids);
  for (const id of ids) {
    if (hide) hiddenIds.add(id);
    else hiddenIds.delete(id);
  }
  rebuild();
}

function beginRename(row, rowEl) {
  closeTreeMenu();
  const nameEl = rowEl.querySelector(".tree-name");
  if (!nameEl || rowEl.querySelector(".tree-rename")) return;
  const input = document.createElement("input");
  input.className = "tree-rename";
  input.type = "text";
  input.value = row.item.label || "";
  input.setAttribute("aria-label", "Rename");
  nameEl.replaceWith(input);
  input.focus();
  input.select();
  let finished = false;
  const finish = async (commit) => {
    if (finished) return;
    finished = true;
    if (!commit) {
      refreshDocks();
      return;
    }
    const next = input.value.trim() === "" ? null : input.value.trim();
    if (next === (row.item.label || null)) {
      refreshDocks();
      return;
    }
    try {
      await refreshFrom(await api("/api/op", "POST", {
        op: "SetLabel",
        entity_id: row.id,
        label: next,
      }));
      setHint(next ? `Renamed to ${next}.` : "Label cleared.");
    } catch (error) {
      setHint(error.message);
      refreshDocks();
    }
  };
  input.addEventListener("keydown", (event) => {
    event.stopPropagation();
    if (event.key === "Enter") {
      event.preventDefault();
      finish(true);
    }
    if (event.key === "Escape") {
      event.preventDefault();
      finish(false);
    }
  });
  input.addEventListener("blur", () => finish(true));
}

function gatherPoints(row, into = []) {
  if (row.kind === "Point") into.push(row.item);
  if (row.kind === "Box" && row.item.origin_xyz_mm && row.item.size_xyz_mm) {
    const o = row.item.origin_xyz_mm;
    const s = row.item.size_xyz_mm;
    into.push(
      { x_mm: o[0], y_mm: o[1], z_mm: o[2] },
      { x_mm: o[0] + s[0], y_mm: o[1] + s[1], z_mm: o[2] + s[2] },
    );
  }
  for (const child of brepChildren(row)) gatherPoints(child, into);
  return into;
}

function fitEntity(row) {
  const pts = gatherPoints(row);
  const box = new THREE.Box3();
  for (const point of pts) {
    box.expandByPoint(new THREE.Vector3(point.x_mm, point.y_mm, point.z_mm || 0));
  }
  if (box.isEmpty()) {
    fitView();
    return;
  }
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const radius = Math.max(size.length() * 0.55, gridMinorMm() * 2, 1);
  let dir = namedView ? VIEW_PRESETS[namedView].dir.clone() : camera().position.clone().sub(controls.target);
  if (dir.lengthSq() < 1e-8) dir.copy(ISO_DIR);
  resetViewZoom();
  goToView(dir, {
    target: center,
    dist: frameDistance(radius),
    up: viewUp.clone(),
    axis: Boolean(namedView),
  });
}

async function duplicateEntities(ids) {
  if (!ids.length) {
    setHint("Select something to duplicate.");
    return;
  }
  await refreshFrom(await api("/api/op", "POST", {
    op: "ArrayLinear",
    entity_ids: ids,
    dx_mm: gridMinorMm(),
    dy_mm: 0,
    dz_mm: 0,
    copies: 1,
  }));
  setHint("Duplicated.");
}

function runTreeCommand(cmd, row) {
  if (cmd === "select") {
    setSelection(row.id);
    return;
  }
  if (cmd === "rename") {
    const rowEl = treeEl.querySelector(`.tree-row[data-id="${row.id}"]`);
    if (rowEl) beginRename(row, rowEl);
    return;
  }
  if (cmd === "duplicate") {
    const ids = selectedIds.has(row.id) ? [...selectedIds] : [row.id];
    duplicateEntities(ids).catch((error) => setHint(error.message));
    return;
  }
  if (cmd === "hide") {
    hideSubtree(row, true);
    setHint("Hidden in the view. Right-click → Show to restore.");
    return;
  }
  if (cmd === "show") {
    hideSubtree(row, false);
    return;
  }
  if (cmd === "fit") {
    fitEntity(row);
    return;
  }
  if (cmd === "toggle") {
    if (collapsedTree.has(row.id)) collapsedTree.delete(row.id);
    else collapsedTree.add(row.id);
    refreshDocks();
    return;
  }
  if (cmd === "delete") {
    if (!selectedIds.has(row.id)) setSelection(row.id);
    commitDelete().catch((error) => setHint(error.message));
  }
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
  const roots = brepRoots();
  if (!roots.length) {
    treeEl.textContent = "No entities.";
  } else {
    for (const row of roots) renderTreeNode(row, treeEl);
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
  const fields = [["Type", brepKind(row.kind)], ["Label", item.label || "—"]];
  if (row.kind === "Point") {
    fields.push(["X", formatMm(item.x_mm)], ["Y", formatMm(item.y_mm)], ["Z", formatMm(item.z_mm)]);
  }
  if (row.kind === "Line") {
    const start = pointById(item.start_id);
    const end = pointById(item.end_id);
    if (start && end) fields.push(["Length", formatMm(dist3(start, end))]);
  }
  if (row.kind === "Polyline") {
    const pts = (item.point_ids || []).map(pointById).filter(Boolean);
    let length = 0;
    for (let index = 1; index < pts.length; index += 1) length += dist3(pts[index - 1], pts[index]);
    if (item.closed && pts.length > 2) length += dist3(pts[pts.length - 1], pts[0]);
    if (pts.length) fields.push(["Length", formatMm(length)], ["Vertices", String(pts.length)]);
  }
  if (row.kind === "Face") {
    const pts = (item.point_ids || []).map(pointById).filter(Boolean);
    if (pts.length) {
      const xs = pts.map((point) => point.x_mm);
      const ys = pts.map((point) => point.y_mm);
      const zs = pts.map((point) => point.z_mm);
      fields.push(["Width", formatMm(Math.max(...xs) - Math.min(...xs))]);
      fields.push(["Depth", formatMm(Math.max(...ys) - Math.min(...ys))]);
      const dz = Math.max(...zs) - Math.min(...zs);
      if (dz > 0.5) fields.push(["Elevation", formatMm(zs[0])]);
      fields.push(["Vertices", String(pts.length)]);
    }
  }
  if (row.kind === "Circle") fields.push(["Radius", formatMm(item.radius_mm)]);
  if (row.kind === "Ellipse") {
    fields.push(["Rx", formatMm(item.radius_x_mm)], ["Ry", formatMm(item.radius_y_mm)]);
  }
  if (row.kind === "Arc") {
    const start = pointById(item.start_id);
    const mid = pointById(item.mid_id);
    const end = pointById(item.end_id);
    const circ = start && mid && end ? circumcircle(start, mid, end) : null;
    if (circ) fields.push(["Radius", formatMm(circ.radius)]);
  }
  if (row.kind === "Solid") fields.push(["Height", formatMm(item.distance_mm)]);
  if (row.kind === "Box" && item.size_xyz_mm) {
    fields.push(["Size", item.size_xyz_mm.map((value) => formatMm(value)).join(" × ")]);
  }
  return fields;
}

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

function profileWorldPoints(row) {
  if (row.kind === "Face") {
    return (row.item.point_ids || []).map(pointById).filter(Boolean);
  }
  if (row.kind === "Circle") {
    const center = pointById(row.item.center_id);
    if (!center) return [];
    return sampleCircle(center, row.item.radius_mm).slice(0, -1);
  }
  if (row.kind === "Ellipse") {
    const center = pointById(row.item.center_id);
    if (!center) return [];
    return sampleEllipse(center, row.item.radius_x_mm, row.item.radius_y_mm).slice(0, -1);
  }
  return [];
}

function offsetPoints(pts, dx, dy, dz) {
  return pts.map((point) => ({
    x_mm: point.x_mm + dx,
    y_mm: point.y_mm + dy,
    z_mm: (point.z_mm || 0) + dz,
  }));
}

function curveWorldPoints(row) {
  if (row.kind === "Line") {
    const start = pointById(row.item.start_id);
    const end = pointById(row.item.end_id);
    return start && end ? { pts: [start, end], closed: false } : null;
  }
  if (row.kind === "Polyline") {
    const pts = (row.item.point_ids || []).map(pointById).filter(Boolean);
    return pts.length >= 2 ? { pts, closed: Boolean(row.item.closed) } : null;
  }
  if (row.kind === "Bezier") {
    const pts = (row.item.point_ids || []).map(pointById).filter(Boolean);
    if (pts.length !== 4) return null;
    return { pts: sampleBezier(pts), closed: false };
  }
  if (row.kind === "Arc") {
    const start = pointById(row.item.start_id);
    const mid = pointById(row.item.mid_id);
    const end = pointById(row.item.end_id);
    if (!start || !mid || !end) return null;
    return { pts: sampleArc(start, mid, end), closed: false };
  }
  return null;
}

function pickClosestPoint(event) {
  let best = null;
  for (const point of sceneState.points || []) {
    if (hiddenIds.has(point.entity_id)) continue;
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
    if (!FILTER_KINDS.line.has(row.kind) || hiddenIds.has(row.id)) continue;
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
    if (!FILTER_KINDS.face.has(row.kind) || hiddenIds.has(row.id)) continue;
    const pts = profileWorldPoints(row);
    if (pts.length >= 3) polygons.push({ id: row.id, pts });
  }
  for (const solid of sceneState.solids || []) {
    if (hiddenIds.has(solid.entity_id)) continue;
    const profile = findRecord(solid.face_id);
    if (!profile || (profile.kind !== "Circle" && profile.kind !== "Ellipse")) continue;
    if (hiddenIds.has(profile.id)) continue;
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
    if (!FILTER_KINDS.solid.has(row.kind) || hiddenIds.has(row.id)) continue;
    const dist = rayHitsSolid(ray, row);
    if (dist != null && (!best || dist < best.dist)) best = { id: row.id, dist };
  }
  return best ? best.id : null;
}

function pickClosestElement(event) {
  const line = pickClosestLine(event);
  if (line != null) return rootId(line);
  const point = pickClosestPoint(event);
  if (point != null) return rootId(point);
  const face = pickClosestFace(event);
  if (face != null) return rootId(face);
  const solid = pickClosestSolid(event);
  if (solid != null) return rootId(solid);
  return null;
}

function pickByFilter(event, filter) {
  indexBrepParents();
  if (filter === "point") return pickClosestPoint(event);
  if (filter === "line") return pickClosestLine(event);
  if (filter === "face") return pickClosestFace(event);
  if (filter === "solid") return pickClosestSolid(event);
  return pickClosestElement(event);
}

function pickEntity(event) {
  if (tool === "select") return pickByFilter(event, selectFilter);
  if (tool === "trim" || tool === "extend" || tool === "break") {
    return pickClosestLine(event);
  }
  if (tool === "node") {
    return pickClosestLine(event) || pickClosestFace(event);
  }
  const drawn = pickDrawnEntity(event);
  return drawn ? drawn.id : null;
}

function filterSelectionIds(ids) {
  indexBrepParents();
  if (selectFilter === "element") {
    return [...new Set(ids.map((id) => rootId(id)))];
  }
  const kinds = FILTER_KINDS[selectFilter];
  return ids.filter((id) => {
    const row = findRecord(id);
    return row && kinds.has(row.kind);
  });
}

function setSelectFilter(next) {
  if (!SELECT_FILTERS.includes(next)) return;
  selectFilter = next;
  for (const button of document.querySelectorAll("#sel-filters [data-filter]")) {
    button.classList.toggle("active", button.dataset.filter === selectFilter);
  }
  refreshToggles();
  const labels = {
    point: "points",
    line: "lines",
    face: "faces",
    solid: "solids",
    element: "whole elements",
  };
  setHint(`Select ${labels[selectFilter]} (1–5). Click, window, or crossing.`);
  rebuild();
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
    const pts = gatherPoints(row).map((point) => clientOf(point.x_mm, point.y_mm, point.z_mm || 0));
    return pts.length ? { pts, closed: false } : null;
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
  const hits = filterSelectionIds(entitiesInWindow(rect, crossing));
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
  lookAtScene(ISO_DIR, { up: WORLD_UP.clone() });
}

function snapToStep(value, step) {
  return Math.round(value / step) * step;
}

function snapGrid(value) {
  const minor = gridMinorMm();
  const major = gridMajorMm();
  const a = snapToStep(value, minor);
  const b = snapToStep(value, major);
  return Math.abs(value - b) <= Math.abs(value - a) ? b : a;
}

function nearestGridPoint(raw) {
  const minor = gridMinorMm();
  const major = gridMajorMm();
  const xs = [snapToStep(raw.x_mm, minor), snapToStep(raw.x_mm, major)];
  const ys = [snapToStep(raw.y_mm, minor), snapToStep(raw.y_mm, major)];
  let best = null;
  for (const x_mm of xs) {
    for (const y_mm of ys) {
      const dist = Math.hypot(x_mm - raw.x_mm, y_mm - raw.y_mm);
      const onMajor = Math.abs(x_mm - snapToStep(x_mm, major)) < 1e-6
        && Math.abs(y_mm - snapToStep(y_mm, major)) < 1e-6;
      const kind = onMajor ? "grid-major" : "grid-minor";
      if (
        !best
        || dist < best.dist - 1e-6
        || (Math.abs(dist - best.dist) < 1e-6 && kind === "grid-major")
      ) {
        best = { x_mm, y_mm, z_mm: 0, dist, snap: kind };
      }
    }
  }
  return best;
}

function isGridSnap(kind) {
  return kind === "grid" || kind === "grid-minor" || kind === "grid-major";
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
  }
  if (gridSnapOn) {
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
  return gridSnapOn ? snapGrid(hit.z) : hit.z;
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

function ghostPolyline(pts, cursor) {
  const all = cursor ? pts.concat([cursor]) : pts;
  for (let index = 0; index < all.length - 1; index += 1) {
    ghostStroke(all[index], all[index + 1], 0x6cb3ff, index === all.length - 2);
  }
}

function polylineCloses(end) {
  return Boolean(
    pending
    && pending.kind === "polyline"
    && pending.pts.length >= 3
    && dist3(pending.pts[0], end) <= SNAP_APERTURE_MM,
  );
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
  const size = kind === "node" ? 180 : kind === "grid-major" ? 160 : 110;
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
    new THREE.LineBasicMaterial({ color: SNAP_COLOR }),
  ));
}

function currentEnd(event) {
  if (!pending) return null;
  if (pending.kind === "polyline") {
    const raw = rawHit(event);
    if (!raw) return null;
    const last = pending.pts[pending.pts.length - 1];
    if (pending.pts.length >= 3 && dist3(pending.pts[0], raw) <= SNAP_APERTURE_MM) {
      return { ...pending.pts[0], snap: "node" };
    }
    const hit = applySnaps(raw);
    if (!hit) return null;
    if (hit.snap === "node") return hit;
    return applyLength(last, orthogonalize(last, hit, event), activeLength());
  }
  const raw = hitWorkplane(event);
  if (!raw) return null;
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
  if (hit && (hit.snap === "node" || isGridSnap(hit.snap))) drawSnapMarker(hit, hit.snap);
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
  if (pending.kind === "polyline") {
    const end = currentEnd(event);
    if (end) {
      ghostPolyline(pending.pts, end);
      const last = pending.pts[pending.pts.length - 1];
      setCoords(end, last);
      if (polylineCloses(end)) drawSnapMarker(pending.pts[0], "node");
    }
    return;
  }
  if (pending.kind === "line" || pending.kind === "move" || pending.kind === "array" || pending.kind === "mirror") {
    const end = currentEnd(event);
    if (end) {
      ghostLine(pending.a, end);
      setCoords(end, pending.a);
    }
    return;
  }
  if (pending.kind === "rotate") {
    const end = hitWorkplane(event);
    if (end) {
      ghostLine(pending.a, end);
      setCoords(end, pending.a);
    }
    return;
  }
  if (pending.kind === "rect") {
    const end = currentEnd(event);
    if (end) {
      ghostRect(pending.a, end);
      setCoords(end, pending.a);
    }
    return;
  }
  if (pending.kind === "height" || pending.kind === "extrude") {
    const height = hitHeight(event, pending.a, pending.b);
    ghostRect(pending.a, pending.b, height);
    setCoords(hit);
    return;
  }
  if (pending.kind === "radial") {
    const rim = currentEnd(event);
    if (!rim) return;
    const radius = dist3(pending.a, rim);
    if (tool === "circle") {
      addFaceGraphic(ghosts, sampleCircle(pending.a, radius).slice(0, -1), { fill: true, opacity: 0.22 });
    } else if (tool === "polygon") {
      addFaceGraphic(ghosts, regularPolygon(pending.a, rim, sidesValue()), { fill: true, opacity: 0.18 });
    } else if (tool === "ellipse") {
      const rx = Math.max(Math.abs(rim.x_mm - pending.a.x_mm), 1);
      const ry = Math.max(Math.abs(rim.y_mm - pending.a.y_mm), 1);
      addFaceGraphic(ghosts, sampleEllipse(pending.a, rx, ry).slice(0, -1), { fill: true, opacity: 0.22 });
    }
    setCoords(rim, pending.a);
    return;
  }
  if (pending.kind === "arc") {
    const cur = currentEnd(event) || hit;
    if (!cur) return;
    if (pending.pts.length === 1) {
      ghostLine(pending.pts[0], cur);
    } else {
      addCurve(ghosts, sampleArc(pending.pts[0], pending.pts[1], cur), 0x6cb3ff);
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
  if (dist3(pending.a, end) < 1) {
    setHint("Line: click a different point, or Esc to end the chain.");
    return;
  }
  const startId = await ensurePoint(pending.a);
  const endId = await ensurePoint(end);
  await refreshFrom(await api("/api/op", "POST", {
    op: "AddLine",
    start_id: startId,
    end_id: endId,
    label: pending.chain ? null : labelValue(),
  }));
  clearTyped();
  ghosts.clear();
  ghostDims = [];
  pending = {
    kind: "line",
    a: { x_mm: end.x_mm, y_mm: end.y_mm, z_mm: end.z_mm || 0, entity_id: endId },
    chain: true,
  };
  refreshToggles();
  setHint("Line: click the next point. Esc ends the chain.");
  if (lastPointer) updateGhost(lastPointer);
}

function polylineHint() {
  if (!pending || pending.pts.length < 2) {
    return "Polyline: click the next point.";
  }
  if (pending.pts.length < 3) {
    return "Polyline: click the next point, or Enter to finish.";
  }
  return "Polyline: click the next point, Enter to finish, click start or type C to close.";
}

async function appendPolylineVertex(end) {
  if (polylineCloses(end)) {
    await finishPolyline(true);
    return;
  }
  const last = pending.pts[pending.pts.length - 1];
  if (dist3(last, end) < 1) {
    setHint("Polyline: click a different point, Enter to finish, or Esc to cancel.");
    return;
  }
  pending.pts.push(end);
  clearTyped();
  setHint(polylineHint());
  if (lastPointer) updateGhost(lastPointer);
}

async function finishPolyline(closed) {
  const pts = pending.pts;
  if (pts.length < 2 || (closed && pts.length < 3)) {
    setHint(closed ? "Polyline: need three points to close." : "Polyline: click at least two points, then Enter.");
    return;
  }
  const ids = [];
  for (const point of pts) ids.push(await ensurePoint(point));
  if (new Set(ids).size !== ids.length) {
    throw new Error("polyline vertices collapsed; click distinct points");
  }
  await refreshFrom(await api("/api/op", "POST", {
    op: "AddPolyline",
    point_ids: ids,
    closed: Boolean(closed),
    label: labelValue(),
  }));
  pending = null;
  clearTyped();
  ghosts.clear();
  ghostDims = [];
  refreshToggles();
  setHint(closed ? "Closed polyline placed." : "Polyline placed. LMB starts another.");
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
      const picked = pickEntity(event);
      setSelection(picked, { shift: event.shiftKey });
      if (picked == null && !event.shiftKey) setHint("Selection cleared.");
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
        setHint("Line: click the next point, or type a length and Enter.");
        return;
      }
      const end = currentEnd(event);
      if (!end) return;
      await finishLine(end);
      return;
    }
    if (tool === "polyline") {
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      if (!pending) {
        pending = { kind: "polyline", pts: [xyz] };
        setHint("Polyline: click the next point.");
        return;
      }
      const end = currentEnd(event);
      if (!end) return;
      await appendPolylineVertex(end);
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
  if (!pending) {
    const echoed = typedText();
    if (/^grid\s+auto$/i.test(echoed)) {
      appendLog(`${consolePrompt.textContent} ${echoed}`);
      setGridAuto(true);
      clearTyped();
      return;
    }
    if (/^grid\s+manual$/i.test(echoed)) {
      appendLog(`${consolePrompt.textContent} ${echoed}`);
      setGridAuto(false);
      clearTyped();
      return;
    }
    const match = echoed.match(/^grid(?:\s+|=)(\d+(?:\.\d+)?)(?:\s+(\d+(?:\.\d+)?))?$/i);
    if (match) {
      appendLog(`${consolePrompt.textContent} ${echoed}`);
      setGridSpacing(
        fromDisplay(Number(match[1])),
        match[2] != null ? fromDisplay(Number(match[2])) : undefined,
      );
      clearTyped();
      return;
    }
    const majorMatch = echoed.match(/^major(?:\s+|=)(\d+(?:\.\d+)?)$/i);
    if (majorMatch) {
      appendLog(`${consolePrompt.textContent} ${echoed}`);
      setGridSpacing(gridMinorMm(), fromDisplay(Number(majorMatch[1])));
      clearTyped();
      return;
    }
    const hiddenMatch = echoed.match(/^hidden(?:\s+|=)(\d+(?:\.\d+)?)$/i);
    if (hiddenMatch) {
      appendLog(`${consolePrompt.textContent} ${echoed}`);
      setGridHiddenScale(Number(hiddenMatch[1]));
      clearTyped();
      return;
    }
    const dotMatch = echoed.match(/^dot(?:size)?(?:\s+|=)(\d+(?:\.\d+)?)$/i);
    if (dotMatch) {
      appendLog(`${consolePrompt.textContent} ${echoed}`);
      setGridDotSize(Number(dotMatch[1]));
      clearTyped();
      return;
    }
    const thickMatch = echoed.match(/^(?:thick(?:ness)?|linew(?:idth)?)(?:\s+|=)(\d+(?:\.\d+)?)$/i);
    if (thickMatch) {
      appendLog(`${consolePrompt.textContent} ${echoed}`);
      setGridLineWidth(Number(thickMatch[1]));
      clearTyped();
      return;
    }
    const styleMatch = echoed.match(/^(?:minor\s+)?(dots|lines)$/i);
    if (styleMatch) {
      appendLog(`${consolePrompt.textContent} ${echoed}`);
      setGridMinorStyle(styleMatch[1].toLowerCase());
      clearTyped();
      return;
    }
    const unitMatch = echoed.match(/^(mm|cm|m|in)$/i);
    if (unitMatch) {
      appendLog(`${consolePrompt.textContent} ${echoed}`);
      setDisplayUnit(unitMatch[1].toLowerCase());
      clearTyped();
      return;
    }
    const viewMatch = echoed.match(/^(top|front|right|left|back|bottom)$/i);
    if (viewMatch) {
      appendLog(`${consolePrompt.textContent} ${echoed}`);
      goNamedView(viewMatch[1].toLowerCase());
      clearTyped();
      return;
    }
    if (/^persp(ective)?$/i.test(echoed)) {
      appendLog(`${consolePrompt.textContent} ${echoed}`);
      setProjectionMode("perspective");
      clearTyped();
      return;
    }
    if (/^parallel$/i.test(echoed)) {
      appendLog(`${consolePrompt.textContent} ${echoed}`);
      setProjectionMode("parallel");
      clearTyped();
      return;
    }
    return;
  }
  const echoed = typedText();
  if (echoed) appendLog(`${consolePrompt.textContent} ${echoed}`);
  try {
    if (pending.kind === "polyline") {
      const token = echoed.trim().toLowerCase();
      if (token === "c" || token === "close") {
        await finishPolyline(true);
        return;
      }
      if (activeLength() != null && lastPointer) {
        const end = currentEnd(lastPointer);
        if (end) await appendPolylineVertex(end);
        return;
      }
      await finishPolyline(false);
      return;
    }
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
  select: "Select: click, or drag L→R window / R→L crossing. Filter 1–5. Shift adds. Delete removes.",
  line: "Line: click to chain segments. Type a length, Enter to commit. Esc ends the chain.",
  polyline: "Polyline: click vertices. Enter finishes. Click start or type C to close.",
  rect: "Rect: two clicks for a rectangle on XY.",
  circle: "Circle: centre, then radius. Then Select + Extrude.",
  arc: "Arc: three clicks (start, on-arc, end).",
  ellipse: "Ellipse: centre, then a corner of the bounding box.",
  polygon: "Polygon: centre, then radius. The library places a hexagon.",
  bezier: "Bézier: four control points.",
  box: "Box: rectangle, then pull height. Type height and Enter.",
  extrude: "Extrude: select a face/circle/ellipse, then pull height.",
  move: "Move (M): select entities, click a base point, then the destination.",
  rotate: "Rotate: select, click the pivot, type degrees or click an angle.",
  mirror: "Mirror: select, then two clicks for the mirror axis.",
  array: "Array: select, click spacing to the next copy.",
  polar: "Polar: select, click the centre. Length = sweep ° (default 360).",
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
for (const button of document.querySelectorAll("#sel-filters [data-filter]")) {
  button.addEventListener("click", () => {
    setTool("select");
    setSelectFilter(button.dataset.filter);
  });
}

projButton.addEventListener("click", () => {
  setProjectionMode(projection === "perspective" ? "parallel" : "perspective");
});
snapButton.addEventListener("click", () => {
  snapOn = !snapOn;
  refreshToggles();
  if (lastPointer) updateGhost(lastPointer);
});
gridSnapButton.addEventListener("click", () => {
  setGridSnapOn(!gridSnapOn);
  if (lastPointer) updateGhost(lastPointer);
});
orthoButton.addEventListener("click", () => {
  orthoOn = !orthoOn;
  refreshToggles();
  if (lastPointer) updateGhost(lastPointer);
});
gridButton.addEventListener("click", () => {
  setGridOn(!gridOn);
  if (lastPointer) updateGhost(lastPointer);
});
consoleInput.addEventListener("input", () => {
  refreshToggles();
  if (lastPointer) updateGhost(lastPointer);
});

canvas.addEventListener("pointerdown", (event) => {
  canvas.focus();
  if (event.button === 0 && event.altKey) {
    controls.mouseButtons.LEFT = THREE.MOUSE.ROTATE;
  } else {
    controls.mouseButtons.LEFT = -1;
  }
  if (event.button === 1 || (event.button === 0 && event.altKey)) {
    releaseNamedViewForOrbit();
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
  if (event.key === "F7") {
    event.preventDefault();
    setGridSnapOn(!gridSnapOn);
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
    setGridOn(!gridOn);
    if (lastPointer) updateGhost(lastPointer);
    return;
  }
  if (event.key === "F2") {
    if (isTypingField(event) || event.target === consoleInput) return;
    event.preventDefault();
    if (selectedIds.size !== 1) {
      setHint("Select one entity to rename.");
      return;
    }
    const id = [...selectedIds][0];
    const row = findRecord(id);
    const rowEl = treeEl.querySelector(`.tree-row[data-id="${id}"]`);
    if (row && rowEl) beginRename(row, rowEl);
    return;
  }
  if (event.ctrlKey || event.metaKey) {
    const key = event.key.toLowerCase();
    if (key === "n") {
      event.preventDefault();
      newDocument().catch((error) => setHint(error.message));
      return;
    }
    if (key === "o") {
      event.preventDefault();
      openDocument();
      return;
    }
    if (key === "s") {
      event.preventDefault();
      saveDocument(event.shiftKey);
      return;
    }
    if (key === "z") {
      event.preventDefault();
      undoDocument().catch((error) => setHint(error.message));
      return;
    }
    if (key === "y") {
      event.preventDefault();
      redoDocument().catch((error) => setHint(error.message));
      return;
    }
    if (key === "a") {
      if (event.target === consoleInput || isTypingField(event)) return;
      event.preventDefault();
      selectAll();
      return;
    }
    return;
  }
  if (event.key === "Escape") {
    if (document.querySelector(".menu.open")) {
      event.preventDefault();
      closeMenus();
      return;
    }
    if (document.querySelector("dialog[open]")) return;
    if (pending) {
      const endedChain = pending.kind === "line" && pending.chain;
      pending = null;
      clearTyped();
      ghosts.clear();
      ghostDims = [];
      hideMarquee();
      refreshToggles();
      setHint(endedChain
        ? "Line chain ended. Click to start another, or Esc for Select."
        : "Cancelled.");
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
      if (event.key === "m" || event.key === "M") {
        event.preventDefault();
        setTool("move");
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
    if (tool === "select") {
      const filters = { 1: "point", 2: "line", 3: "face", 4: "solid", 5: "element" };
      if (filters[event.key]) {
        event.preventDefault();
        setSelectFilter(filters[event.key]);
        return;
      }
    }
    if (event.key === "t" || event.key === "T") {
      event.preventDefault();
      setTool("trim");
      return;
    }
    if (event.key === "m" || event.key === "M") {
      event.preventDefault();
      setTool("move");
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
    setProjectionMode(projection === "perspective" ? "parallel" : "perspective");
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
const outlinerEl = document.getElementById("outliner");
const propsEl = document.getElementById("props");
const consoleEl = document.getElementById("console");
const fileOpenEl = document.getElementById("file-open");
const prefsDialog = document.getElementById("prefs-dialog");
const gridPrefsDialog = document.getElementById("grid-prefs-dialog");
const helpDialog = document.getElementById("help-dialog");

function persistLayout() {
  sessionStorage.setItem(LAYOUT_KEY, JSON.stringify({
    outliner: outlinerEl.style.width || "260px",
    props: propsEl.style.height || "140px",
    console: consoleEl.style.height || "72px",
    outlinerCollapsed: workspaceEl.classList.contains("outliner-collapsed"),
    railCollapsed: workspaceEl.classList.contains("rail-collapsed"),
    consoleCollapsed: document.body.classList.contains("console-collapsed"),
  }));
}

function restoreLayout() {
  try {
    const layout = JSON.parse(sessionStorage.getItem(LAYOUT_KEY) || "null");
    if (!layout || typeof layout !== "object") return;
    if (layout.outliner) outlinerEl.style.width = layout.outliner;
    if (layout.props) propsEl.style.height = layout.props;
    if (layout.console) consoleEl.style.height = layout.console;
    workspaceEl.classList.toggle("outliner-collapsed", !!layout.outlinerCollapsed);
    workspaceEl.classList.toggle("rail-collapsed", !!layout.railCollapsed);
    document.body.classList.toggle("console-collapsed", !!layout.consoleCollapsed);
  } catch (_error) {
    /* keep defaults */
  }
}

function setGridOn(next) {
  gridOn = next;
  prefs.grid = next;
  savePrefs();
  refreshToggles();
  grid.visible = gridOn;
}

function setGridSnapOn(next) {
  gridSnapOn = next;
  prefs.gridSnap = next;
  savePrefs();
  refreshToggles();
}

function applyViz() {
  const pal = BACKGROUNDS[prefs.background] || BACKGROUNDS.g5;
  scene.background.setHex(pal.bg);
  document.getElementById("stage").style.background = `#${pal.bg.toString(16).padStart(6, "0")}`;
  rebuildGrid();
  const dark = prefs.background === "g2";
  hemi.color.setHex(dark ? 0xc8cdd3 : 0xf4f7fb);
  hemi.groundColor.setHex(prefs.ao ? (dark ? 0x0a0a0a : 0x6e757c) : (dark ? 0x2a2a2a : 0xc5cad0));
  hemi.intensity = prefs.ao ? 0.58 : 0.42;
  key.visible = prefs.keyLight;
  key.intensity = prefs.keyLight ? 0.45 : 0;
  contact.visible = prefs.ao;
  contact.material.opacity = dark ? 0.18 : 0.06;
  rebuild();
}

function savePrefs() {
  localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
}

function syncPrefsForm() {
  document.getElementById("pref-background").value = prefs.background;
  document.getElementById("pref-clay").value = String(prefs.clay);
  document.getElementById("pref-curve").value = prefs.curve;
  document.getElementById("pref-key").checked = prefs.keyLight;
  document.getElementById("pref-ao").checked = prefs.ao;
  document.getElementById("pref-edges").checked = prefs.showEdges;
  document.getElementById("pref-curves").checked = prefs.showCurves;
  document.getElementById("pref-faces").checked = prefs.showFaces;
}

function readPrefsForm() {
  prefs = {
    background: document.getElementById("pref-background").value,
    clay: Number(document.getElementById("pref-clay").value) || 176,
    curve: document.getElementById("pref-curve").value,
    keyLight: document.getElementById("pref-key").checked,
    ao: document.getElementById("pref-ao").checked,
    showEdges: document.getElementById("pref-edges").checked,
    showCurves: document.getElementById("pref-curves").checked,
    showFaces: document.getElementById("pref-faces").checked,
    grid: gridOn,
    gridSnap: gridSnapOn,
    gridMinorOn,
    gridAuto: gridAutoOn(),
    gridMinor: prefMinorMm(),
    gridMajor: prefMajorMm(),
    gridHiddenScale: hiddenLineScale(),
    gridMinorStyle: gridMinorStyle(),
    gridDotSize: gridDotSize(),
    gridLineWidth: gridLineWidth(),
    displayUnit: displayUnit(),
  };
  savePrefs();
  applyViz();
  refreshToggles();
  if (lastPointer) updateGhost(lastPointer);
}

function downloadJson(filename) {
  const blob = new Blob([JSON.stringify(sceneState.document, null, 2)], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  URL.revokeObjectURL(link.href);
}

function saveDocument(saveAs = false) {
  if (saveAs) {
    const next = window.prompt("Save as", saveName) || "";
    if (!next.trim()) return;
    saveName = next.trim().endsWith(".json") ? next.trim() : `${next.trim()}.json`;
  }
  downloadJson(saveName);
  setHint(`Saved ${saveName}. Preferences are not in this file.`);
}

function openDocument() {
  fileOpenEl.click();
}

function documentFromFile(parsed) {
  if (parsed && parsed.schema && Array.isArray(parsed.ops)) return parsed;
  if (parsed && parsed.document && parsed.document.schema) return parsed.document;
  throw new Error("not an apeCAD document JSON");
}

async function loadDocumentDict(dict, name) {
  pending = null;
  ghosts.clear();
  selectedIds.clear();
  await refreshFrom(await api("/api/load", "POST", dict));
  if (name) saveName = name;
  namedView = null;
  viewUp.copy(WORLD_UP);
  bindProjectionCamera();
  lookAtScene(ISO_DIR, { up: WORLD_UP.clone() });
  setHint(`Opened ${saveName}.`);
}

async function newDocument() {
  pending = null;
  ghosts.clear();
  selectedIds.clear();
  await refreshFrom(await api("/api/reset", "POST", {}));
  saveName = "apecad.json";
  namedView = null;
  viewUp.copy(WORLD_UP);
  bindProjectionCamera();
  lookAtScene(ISO_DIR, { up: WORLD_UP.clone() });
  setHint("New document.");
}

async function undoDocument() {
  pending = null;
  ghosts.clear();
  await refreshFrom(await api("/api/undo", "POST", {}));
}

async function redoDocument() {
  await refreshFrom(await api("/api/redo", "POST", {}));
}

function selectAll() {
  indexBrepParents();
  const ids = selectFilter === "element"
    ? brepRoots().map((row) => row.id)
    : catalog().filter((row) => FILTER_KINDS[selectFilter].has(row.kind)).map((row) => row.id);
  selectedIds = new Set(ids);
  rebuild();
  setHint(selectedIds.size ? `${selectedIds.size} selected.` : "Nothing to select.");
}

function closeMenus() {
  for (const menu of document.querySelectorAll(".menu.open")) menu.classList.remove("open");
  closeTreeMenu();
}

function runCommand(cmd) {
  closeMenus();
  if (cmd === "new") return newDocument().catch((error) => setHint(error.message));
  if (cmd === "open" || cmd === "import") return openDocument();
  if (cmd === "save") return saveDocument(false);
  if (cmd === "save-as" || cmd === "export") return saveDocument(true);
  if (cmd === "prefs") {
    syncPrefsForm();
    prefsDialog.showModal();
    return;
  }
  if (cmd === "grid-prefs") {
    syncGridPrefsForm();
    gridPrefsDialog.showModal();
    return;
  }
  if (cmd === "quit") {
    window.close();
    setHint("Close the browser tab to quit.");
    return;
  }
  if (cmd === "undo") return undoDocument().catch((error) => setHint(error.message));
  if (cmd === "redo") return redoDocument().catch((error) => setHint(error.message));
  if (cmd === "select-all") return selectAll();
  if (cmd === "delete") return commitDelete().catch((error) => setHint(error.message));
  if (cmd === "perspective") return setProjectionMode("perspective");
  if (cmd === "parallel") return setProjectionMode("parallel");
  if (cmd === "view-top") return goNamedView("top");
  if (cmd === "view-front") return goNamedView("front");
  if (cmd === "view-right") return goNamedView("right");
  if (cmd === "view-left") return goNamedView("left");
  if (cmd === "view-back") return goNamedView("back");
  if (cmd === "view-bottom") return goNamedView("bottom");
  if (cmd === "projection") {
    return setProjectionMode(projection === "perspective" ? "parallel" : "perspective");
  }
  if (cmd === "snap") {
    snapOn = !snapOn;
    refreshToggles();
    return;
  }
  if (cmd === "grid-snap") {
    setGridSnapOn(!gridSnapOn);
    return;
  }
  if (cmd === "ortho") {
    orthoOn = !orthoOn;
    refreshToggles();
    return;
  }
  if (cmd === "grid") {
    setGridOn(!gridOn);
    return;
  }
  if (cmd === "fit") return document.getElementById("view-fit").click();
  if (cmd === "iso") return document.getElementById("view-iso").click();
  if (cmd === "viewcube") {
    viewCubeOn = !viewCubeOn;
    document.getElementById("viewcube-wrap").hidden = !viewCubeOn;
    return;
  }
  if (cmd === "toggle-outliner") {
    workspaceEl.classList.toggle("outliner-collapsed");
    persistLayout();
    syncCameras();
    return;
  }
  if (cmd === "toggle-rail") {
    workspaceEl.classList.toggle("rail-collapsed");
    persistLayout();
    return;
  }
  if (cmd === "toggle-console") {
    document.body.classList.toggle("console-collapsed");
    persistLayout();
    syncCameras();
    return;
  }
  if (cmd === "help") {
    helpDialog.showModal();
  }
}

for (const menu of document.querySelectorAll(".menu")) {
  const button = menu.querySelector(":scope > button");
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    const wasOpen = menu.classList.contains("open");
    closeMenus();
    if (!wasOpen) menu.classList.add("open");
  });
}
document.addEventListener("click", closeMenus);
document.getElementById("tree-wrap").addEventListener("contextmenu", (event) => {
  event.preventDefault();
});
for (const button of document.querySelectorAll("[data-cmd]")) {
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    runCommand(button.dataset.cmd);
  });
}

fileOpenEl.addEventListener("change", async () => {
  const file = fileOpenEl.files && fileOpenEl.files[0];
  fileOpenEl.value = "";
  if (!file) return;
  try {
    await loadDocumentDict(documentFromFile(JSON.parse(await file.text())), file.name);
  } catch (error) {
    setHint(error.message);
  }
});

for (const id of [
  "pref-background", "pref-clay", "pref-curve", "pref-key", "pref-ao",
  "pref-edges", "pref-curves", "pref-faces",
]) {
  document.getElementById(id).addEventListener("change", readPrefsForm);
  document.getElementById(id).addEventListener("input", readPrefsForm);
}
document.getElementById("prefs-close").addEventListener("click", () => prefsDialog.close());
document.getElementById("grid-prefs-close").addEventListener("click", () => gridPrefsDialog.close());
document.getElementById("help-close").addEventListener("click", () => helpDialog.close());
document.getElementById("grid-menu").addEventListener("click", (event) => event.stopPropagation());
document.getElementById("grid-minor-on").addEventListener("change", (event) => {
  setGridMinorOn(event.target.checked);
});
document.getElementById("gpref-show").addEventListener("change", (event) => {
  setGridOn(event.target.checked);
});
document.getElementById("gpref-minor-on").addEventListener("change", (event) => {
  setGridMinorOn(event.target.checked);
});
document.getElementById("gpref-snap").addEventListener("change", (event) => {
  setGridSnapOn(event.target.checked);
});
document.getElementById("gpref-auto").addEventListener("change", (event) => {
  setGridAuto(event.target.checked);
});
document.getElementById("gpref-minor-style").addEventListener("change", (event) => {
  setGridMinorStyle(event.target.value);
});
function readGridSpacingForm() {
  setGridSpacing(
    fromDisplay(document.getElementById("gpref-minor").value),
    fromDisplay(document.getElementById("gpref-major").value),
  );
}
document.getElementById("gpref-minor").addEventListener("change", readGridSpacingForm);
document.getElementById("gpref-major").addEventListener("change", readGridSpacingForm);
document.getElementById("gpref-unit").addEventListener("change", (event) => {
  setDisplayUnit(event.target.value);
});
const hiddenScaleEl = document.getElementById("gpref-hidden-scale");
const hiddenScaleNum = document.getElementById("gpref-hidden-scale-num");
hiddenScaleEl.addEventListener("input", () => {
  setGridHiddenScale(hiddenScaleEl.value, { silent: true });
});
hiddenScaleEl.addEventListener("change", () => {
  setGridHiddenScale(hiddenScaleEl.value);
});
hiddenScaleNum.addEventListener("input", () => {
  setGridHiddenScale(hiddenScaleNum.value, { silent: true });
});
hiddenScaleNum.addEventListener("change", () => {
  setGridHiddenScale(hiddenScaleNum.value);
});
const dotSizeEl = document.getElementById("gpref-dot-size");
const dotSizeNum = document.getElementById("gpref-dot-size-num");
dotSizeEl.addEventListener("input", () => {
  setGridDotSize(dotSizeEl.value, { silent: true });
});
dotSizeEl.addEventListener("change", () => {
  setGridDotSize(dotSizeEl.value);
});
dotSizeNum.addEventListener("input", () => {
  setGridDotSize(dotSizeNum.value, { silent: true });
});
dotSizeNum.addEventListener("change", () => {
  setGridDotSize(dotSizeNum.value);
});
const lineWidthEl = document.getElementById("gpref-line-width");
const lineWidthNum = document.getElementById("gpref-line-width-num");
lineWidthEl.addEventListener("input", () => {
  setGridLineWidth(lineWidthEl.value, { silent: true });
});
lineWidthEl.addEventListener("change", () => {
  setGridLineWidth(lineWidthEl.value);
});
lineWidthNum.addEventListener("input", () => {
  setGridLineWidth(lineWidthNum.value, { silent: true });
});
lineWidthNum.addEventListener("change", () => {
  setGridLineWidth(lineWidthNum.value);
});
for (const button of document.querySelectorAll("[data-grid-minor]")) {
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    setGridSpacing(button.dataset.gridMinor, button.dataset.gridMajor);
  });
}

bindSplit(document.getElementById("split-outliner"), (event) => {
  const rect = workspaceEl.getBoundingClientRect();
  const maxWidth = Math.max(rect.width * 0.5, 180);
  outlinerEl.style.width = `${Math.min(Math.max(event.clientX - rect.left, 180), maxWidth)}px`;
  persistLayout();
  syncCameras();
});
bindSplit(document.getElementById("split-tree"), (event) => {
  const rect = outlinerEl.getBoundingClientRect();
  const height = Math.min(Math.max(rect.bottom - event.clientY, 72), rect.height - 140);
  propsEl.style.height = `${height}px`;
  persistLayout();
});
bindSplit(document.getElementById("split-console"), (event) => {
  const body = document.body.getBoundingClientRect();
  consoleEl.style.height = `${Math.min(Math.max(body.bottom - event.clientY, 56), body.height * 0.4)}px`;
  persistLayout();
  syncCameras();
});

document.getElementById("outliner-toggle").addEventListener("click", () => {
  workspaceEl.classList.add("outliner-collapsed");
  persistLayout();
  syncCameras();
});
document.getElementById("outliner-expand").addEventListener("click", () => {
  workspaceEl.classList.remove("outliner-collapsed");
  persistLayout();
  syncCameras();
});
document.getElementById("rail-toggle").addEventListener("click", () => {
  workspaceEl.classList.add("rail-collapsed");
  persistLayout();
});
document.getElementById("rail-expand").addEventListener("click", () => {
  workspaceEl.classList.remove("rail-collapsed");
  persistLayout();
});

function tick() {
  tickViewAnim();
  syncCameras();
  renderer.render(scene, camera());
  syncCube();
  projectDims();
  requestAnimationFrame(tick);
}
restoreLayout();
syncPrefsForm();
applyViz();
refreshToggles();
tick();
reload().catch((error) => setHint(error.message));
