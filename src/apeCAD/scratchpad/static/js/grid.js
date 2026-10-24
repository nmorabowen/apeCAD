// The drafting grid on the XY workplane: spacing (auto from the model or manual), the minor
// dots/lines and major lines it draws, and snapping to it. Client state only (ADR 0014).
import * as THREE from "three";
import { LineSegments2 } from "three/addons/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/addons/lines/LineSegmentsGeometry.js";
import { LineMaterial } from "three/addons/lines/LineMaterial.js";
import { S } from "./state.js";
import {
  GRID_DEFAULT_MAJOR_MM,
  GRID_EXTENT_MM,
  GRID_MAX_DIVISIONS,
  clampGridSpacing,
  gridAutoOn,
  gridDotSize,
  gridLineWidth,
  gridMinorStyle,
  hiddenLineScale,
  niceLength,
  prefMajorMm,
  prefMinorMm,
} from "./prefs.js";
import { INK } from "./theme.js";
import { canvas, disposeObject3D, scene } from "./viewport.js";

export let grid = null;

function scenePlanBox() {
  const box = new THREE.Box3();
  for (const point of S.sceneState.points || []) {
    box.expandByPoint(new THREE.Vector3(point.x_mm, point.y_mm, 0));
  }
  return box.isEmpty() ? null : box;
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

export function gridMinorMm() {
  return effectiveGrid().minor;
}

export function gridMajorMm() {
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
  const group = new THREE.Group();
  const minor = gridMinorMm();
  const major = gridMajorMm();
  if (S.gridMinorOn && major > minor + 1e-6) {
    const minorGrid = gridMinorStyle() === "dots"
      ? makeMinorDots(minor, INK.gridMinor, major)
      : makeGridHelper(minor, INK.gridMinor, true, major);
    if (minorGrid) group.add(minorGrid);
  }
  const majorGrid = makeGridHelper(major, INK.gridMajor, false);
  if (majorGrid) group.add(majorGrid);
  group.visible = S.gridOn;
  return group;
}

export function rebuildGrid() {
  const next = makeGrid();
  if (grid) {
    scene.remove(grid);
    disposeObject3D(grid);
  }
  grid = next;
  scene.add(grid);
  syncGridLineResolution(grid);
}

export function syncGridLineResolution(root = grid) {
  if (!root) return;
  const width = Math.max(canvas.clientWidth, 1);
  const height = Math.max(canvas.clientHeight, 1);
  root.traverse((node) => {
    if (node.material && node.material.resolution) {
      node.material.resolution.set(width, height);
    }
  });
}


function sendBehind(object, order) {
  object.renderOrder = order;
  const materials = [].concat(object.material || []);
  for (const mat of materials) {
    if (!mat) continue;
    mat.depthTest = false;
    mat.depthWrite = false;
  }
}

function snapToStep(value, step) {
  return Math.round(value / step) * step;
}

export function snapGrid(value) {
  const minor = gridMinorMm();
  const major = gridMajorMm();
  const a = snapToStep(value, minor);
  const b = snapToStep(value, major);
  return Math.abs(value - b) <= Math.abs(value - a) ? b : a;
}

export function nearestGridPoint(raw) {
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

export function isGridSnap(kind) {
  return kind === "grid" || kind === "grid-minor" || kind === "grid-major";
}
