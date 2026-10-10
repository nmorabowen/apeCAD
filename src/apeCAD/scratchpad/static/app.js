import * as THREE from "three";
import { S } from "./js/state.js";
import { api, createdId } from "./js/api.js";
import {
  FILTER_KINDS,
  SELECT_FILTERS,
  brepChildren,
  brepKind,
  brepRoots,
  catalog,
  collectNested,
  findRecord,
  gatherPoints,
  indexBrep,
  lineRows,
  pointById,
} from "./js/brep.js";
import {
  bindProjectionCamera,
  camera,
  fitView,
  frameDistance,
  goNamedView,
  goToView,
  initCamera,
  lookAtScene,
  projButton,
  releaseNamedViewForOrbit,
  resetViewZoom,
  setProjectionMode,
  syncCameras,
  tickViewAnim,
} from "./js/camera.js";
import {
  activeLength,
  appendLog,
  arrayCount,
  bufferLength,
  clearTyped,
  consoleInput,
  consolePrompt,
  gridButton,
  gridSnapButton,
  isTypingField,
  labelValue,
  orthoButton,
  projectDims,
  refreshToggles,
  setCoords,
  setHint,
  setTyped,
  sidesValue,
  snapButton,
  typedText,
} from "./js/cmdline.js";
import {
  SNAP_COLOR,
  addCurve,
  addCylinder,
  addFaceGraphic,
  addSolidPrism,
  addSolidVolumeFallback,
  addVertexDot,
  addVolume,
  clayHex,
  curveFor,
  lineOverlay,
  mark,
  xyzMm,
} from "./js/draw.js";
import {
  circumcircle,
  dist3,
  lineIntersectMm,
  projectT,
  regularPolygon,
  sampleArc,
  sampleBezier,
  sampleCircle,
  sampleEllipse,
} from "./js/geom.js";
import {
  setGridAuto,
  setGridDotSize,
  setGridHiddenScale,
  setGridLineWidth,
  setGridMinorOn,
  setGridMinorStyle,
  setGridOn,
  setGridSnapOn,
  syncGridPrefsForm,
} from "./js/grid-ui.js";
import {
  gridMajorMm,
  gridMinorMm,
  isGridSnap,
  nearestGridPoint,
  rebuildGrid,
  snapGrid,
} from "./js/grid.js";
import { ndcFromEvent, pickEntity } from "./js/pick.js";
import {
  BACKGROUNDS,
  GRID_DEFAULT_MAJOR_MM,
  GRID_DEFAULT_MINOR_MM,
  LAYOUT_KEY,
  clampGridSpacing,
  displayUnit,
  formatLength,
  formatMm,
  fromDisplay,
  gridAutoOn,
  gridDotSize,
  gridLineWidth,
  gridMinorStyle,
  hiddenLineScale,
  initPrefs,
  prefMajorMm,
  prefMinorMm,
  savePrefs,
} from "./js/prefs.js";
import { clearPreselect, updatePreselect } from "./js/preselect.js";
import {
  convertSelectionToFilter,
  hideMarquee,
  selectedProfileId,
  updateMarquee,
  windowHits,
} from "./js/selection.js";
import { UNIT_MM } from "./js/units.js";
import { bindViewCube, syncCube } from "./js/viewcube.js";
import {
  ISO_DIR,
  VIEW_PRESETS,
  WORLD_UP,
  canvas,
  contact,
  controls,
  draft,
  ghosts,
  hemi,
  keyLight,
  renderer,
  scene,
  viewUp,
} from "./js/viewport.js";

const SNAP_APERTURE_MM = 400;

const treeEl = document.getElementById("tree");
const propBody = document.getElementById("prop-body");

initPrefs();

let pointerDown = null;


function setGridSpacing(minor, major) {
  S.prefs.gridAuto = false;
  S.prefs.gridMinor = clampGridSpacing(minor, GRID_DEFAULT_MINOR_MM);
  if (major != null) S.prefs.gridMajor = clampGridSpacing(major, GRID_DEFAULT_MAJOR_MM);
  if (S.prefs.gridMajor < S.prefs.gridMinor) S.prefs.gridMajor = S.prefs.gridMinor;
  savePrefs();
  rebuildGrid();
  refreshToggles();
  if (S.lastPointer) updateGhost(S.lastPointer);
  setHint(`Grid ${formatLength(gridMinorMm())} / ${formatLength(gridMajorMm())}.`);
}

function setDisplayUnit(next) {
  S.prefs.displayUnit = UNIT_MM[next] ? next : "mm";
  savePrefs();
  refreshToggles();
  if (S.lastPointer) updateGhost(S.lastPointer);
  setHint(`Units ${displayUnit()}.`);
}

rebuildGrid();

initCamera();

bindViewCube();

function rebuild() {
  draft.clear();
  S.committedDims = [];
  indexBrep();
  const byId = new Map((S.sceneState.points || []).map((point) => [point.entity_id, point]));
  for (const line of S.sceneState.lines || []) {
    if (S.hiddenIds.has(line.entity_id)) continue;
    const start = byId.get(line.start_id);
    const end = byId.get(line.end_id);
    if (!start || !end) continue;
    if (S.prefs.showCurves) {
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
  for (const polyline of S.sceneState.polylines || []) {
    if (S.hiddenIds.has(polyline.entity_id)) continue;
    const pts = polyline.point_ids.map((id) => byId.get(id)).filter(Boolean);
    if (pts.length < 2) continue;
    if (!S.prefs.showCurves) continue;
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
  for (const solid of S.sceneState.solids || []) {
    extruded.add(solid.face_id);
    if (solid.cap_id) extruded.add(solid.cap_id);
    for (const wallId of solid.wall_ids || []) extruded.add(wallId);
  }
  for (const face of S.sceneState.faces || []) {
    if (S.hiddenIds.has(face.entity_id) || extruded.has(face.entity_id)) continue;
    const pts = face.point_ids.map((id) => byId.get(id)).filter(Boolean);
    addFaceGraphic(draft, pts, {
      fill: true,
      opacity: 0.92,
      entityId: face.entity_id,
    });
  }
  for (const circle of S.sceneState.circles || []) {
    if (S.hiddenIds.has(circle.entity_id)) continue;
    const center = byId.get(circle.center_id);
    if (!center) continue;
    const loop = sampleCircle(center, circle.radius_mm);
    const showFill = !extruded.has(circle.entity_id)
      || S.selectedIds.has(circle.entity_id)
      || S.selectFilter === "face";
    addFaceGraphic(draft, loop.slice(0, -1), {
      fill: showFill,
      opacity: 0.92,
      entityId: circle.entity_id,
    });
  }
  for (const arc of S.sceneState.arcs || []) {
    if (S.hiddenIds.has(arc.entity_id)) continue;
    const start = byId.get(arc.start_id);
    const midPt = byId.get(arc.mid_id);
    const end = byId.get(arc.end_id);
    if (!start || !midPt || !end) continue;
    addCurve(draft, sampleArc(start, midPt, end), curveFor(arc.entity_id), arc.entity_id);
  }
  for (const ellipse of S.sceneState.ellipses || []) {
    if (S.hiddenIds.has(ellipse.entity_id)) continue;
    const center = byId.get(ellipse.center_id);
    if (!center) continue;
    const loop = sampleEllipse(center, ellipse.radius_x_mm, ellipse.radius_y_mm);
    const showFill = !extruded.has(ellipse.entity_id)
      || S.selectedIds.has(ellipse.entity_id)
      || S.selectFilter === "face";
    addFaceGraphic(draft, loop.slice(0, -1), {
      fill: showFill,
      opacity: 0.92,
      entityId: ellipse.entity_id,
    });
  }
  for (const bezier of S.sceneState.beziers || []) {
    if (S.hiddenIds.has(bezier.entity_id)) continue;
    const pts = bezier.point_ids.map((id) => byId.get(id)).filter(Boolean);
    if (pts.length !== 4) continue;
    addCurve(draft, sampleBezier(pts), curveFor(bezier.entity_id), bezier.entity_id);
  }
  for (const box of S.sceneState.boxes || []) {
    if (S.hiddenIds.has(box.entity_id)) continue;
    addVolume(draft, box.origin_xyz_mm, box.size_xyz_mm, clayHex(), 1, box.entity_id);
  }
  for (const solid of S.sceneState.solids || []) {
    if (S.hiddenIds.has(solid.entity_id)) continue;
    const color = clayHex();
    const circle = (S.sceneState.circles || []).find((item) => item.entity_id === solid.face_id);
    const ellipse = (S.sceneState.ellipses || []).find((item) => item.entity_id === solid.face_id);
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
  for (const point of S.sceneState.points || []) {
    if (!S.prefs.showCurves || S.hiddenIds.has(point.entity_id)) continue;
    addVertexDot(draft, point);
  }
  indexBrep();
  refreshDocks();
  rebuildGrid();
  if (S.lastPointer && S.tool === "select") updatePreselect(S.lastPointer);
  else clearPreselect();
}

async function refreshFrom(payload) {
  S.sceneState = payload;
  try {
    rebuild();
  } catch (error) {
    console.error(error);
    try {
      indexBrep();
      refreshDocks();
    } catch (_ignored) { /* docks need a valid catalog */ }
    setHint(`draw error: ${error.message}`);
  }
}

const collapsedTree = new Set();

function renderTreeNode(row, parent) {
  const kids = brepChildren(row);
  const node = document.createElement("div");
  node.className = "tree-node";
  const rowEl = document.createElement("div");
  const dimmed = S.hiddenIds.has(row.id);
  rowEl.className = `tree-row${S.selectedIds.has(row.id) ? " selected" : ""}${dimmed ? " dimmed" : ""}`;
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
    if (!S.selectedIds.has(row.id)) setSelection(row.id);
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
  const hidden = S.hiddenIds.has(row.id);
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
    if (hide) S.hiddenIds.add(id);
    else S.hiddenIds.delete(id);
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
  let dir = S.namedView ? VIEW_PRESETS[S.namedView].dir.clone() : camera().position.clone().sub(controls.target);
  if (dir.lengthSq() < 1e-8) dir.copy(ISO_DIR);
  resetViewZoom();
  goToView(dir, {
    target: center,
    dist: frameDistance(radius),
    up: viewUp.clone(),
    axis: Boolean(S.namedView),
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
    const ids = S.selectedIds.has(row.id) ? [...S.selectedIds] : [row.id];
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
    if (!S.selectedIds.has(row.id)) setSelection(row.id);
    commitDelete().catch((error) => setHint(error.message));
  }
}

function setSelection(id, { shift = false } = {}) {
  if (id == null) {
    if (!shift) S.selectedIds.clear();
  } else if (shift) {
    if (S.selectedIds.has(id)) S.selectedIds.delete(id);
    else S.selectedIds.add(id);
  } else {
    S.selectedIds.clear();
    S.selectedIds.add(id);
  }
  rebuild();
}

function refreshDocks() {
  const rows = catalog();
  for (const id of [...S.selectedIds]) {
    if (!rows.some((row) => row.id === id)) S.selectedIds.delete(id);
  }
  treeEl.innerHTML = "";
  const roots = brepRoots();
  if (!roots.length) {
    treeEl.textContent = "No entities.";
  } else {
    for (const row of roots) renderTreeNode(row, treeEl);
  }
  if (S.selectedIds.size === 0) {
    propBody.textContent = "Nothing selected.";
    return;
  }
  if (S.selectedIds.size > 1) {
    propBody.textContent = `${S.selectedIds.size} entities selected.`;
    return;
  }
  const selected = rows.find((row) => S.selectedIds.has(row.id)) || null;
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

function setSelectFilter(next) {
  if (!SELECT_FILTERS.includes(next)) return;
  S.selectFilter = next;
  S.selectedIds = convertSelectionToFilter(next);
  for (const button of document.querySelectorAll("#sel-filters [data-filter]")) {
    button.classList.toggle("active", button.dataset.filter === S.selectFilter);
  }
  refreshToggles();
  const labels = {
    point: "points",
    line: "lines",
    face: "faces",
    solid: "solids",
    element: "whole elements",
  };
  setHint(`Select ${labels[S.selectFilter]} (1–5). Click, window, or crossing.`);
  rebuild();
}

function applyWindowSelect(origin, event) {
  const crossing = event.clientX < origin.x;
  const hits = windowHits(origin, event);
  hideMarquee();
  if (!event.shiftKey) S.selectedIds.clear();
  for (const id of hits) S.selectedIds.add(id);
  rebuild();
  setHint(hits.length
    ? `${crossing ? "Crossing" : "Window"}: ${S.selectedIds.size} selected.`
    : "Nothing in the window.");
}

function cutterCandidates(victimId) {
  const pinned = [...S.cutterIds].filter((id) => id !== victimId);
  const source = pinned.length
    ? pinned.map((id) => findRecord(id)).filter((row) => row && row.kind === "Line")
    : lineRows().filter((row) => row.id !== victimId);
  return source;
}

function seedCuttersFromSelection() {
  S.cutterIds = new Set([...S.selectedIds].filter((id) => {
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
  if (S.lastPointer) updateGhost(S.lastPointer);
}

async function commitBreak(preview) {
  const after = await api("/api/op", "POST", {
    op: "BreakCrossing",
    line_a_id: preview.lineA,
    line_b_id: preview.lineB,
  });
  await refreshFrom(after);
  S.pending = null;
  if (after.created_id != null) setSelection(after.created_id);
  setHint("Broke at the crossing. Click two more lines, or Esc.");
}

async function finishMove(end) {
  const dx = end.x_mm - S.pending.a.x_mm;
  const dy = end.y_mm - S.pending.a.y_mm;
  const dz = (end.z_mm || 0) - (S.pending.a.z_mm || 0);
  if (Math.hypot(dx, dy, dz) < 1) {
    S.pending = null;
    ghosts.clear();
    setHint("Move cancelled (zero displacement).");
    return;
  }
  await refreshFrom(await api("/api/op", "POST", {
    op: "Translate",
    entity_ids: [...S.selectedIds],
    dx_mm: dx,
    dy_mm: dy,
    dz_mm: dz,
  }));
  S.pending = null;
  clearTyped();
  ghosts.clear();
  S.ghostDims = [];
  setHint(`Moved ${S.selectedIds.size} entities.`);
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
  const lineIds = [...S.selectedIds].filter((id) => {
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
  const ids = [...S.selectedIds].filter((id) => {
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
  if (S.selectedIds.size === 0) {
    setHint("Select entities, then Sew to merge coincident points.");
    return;
  }
  await refreshFrom(await api("/api/op", "POST", {
    op: "Sew",
    entity_ids: [...S.selectedIds],
    tolerance_mm: 1,
  }));
  setHint("Sewed coincident points.");
}

async function commitSimplify() {
  const ids = [...S.selectedIds].filter((id) => {
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
  if (S.pending) {
    setHint("Finish or Esc the current command before deleting.");
    return;
  }
  if (S.selectedIds.size === 0) {
    setHint("Select entities, then Delete.");
    return;
  }
  const count = S.selectedIds.size;
  await refreshFrom(await api("/api/op", "POST", {
    op: "Delete",
    entity_ids: [...S.selectedIds],
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
    entity_ids: [...S.selectedIds],
    origin_x_mm: pivot.x_mm,
    origin_y_mm: pivot.y_mm,
    angle_deg: angleDeg,
  }));
  S.pending = null;
  clearTyped();
  ghosts.clear();
  S.ghostDims = [];
  setHint(`Rotated ${S.selectedIds.size} entities.`);
}

async function finishMirror(axisA, axisB) {
  await refreshFrom(await api("/api/op", "POST", {
    op: "Mirror",
    entity_ids: [...S.selectedIds],
    ax_mm: axisA.x_mm,
    ay_mm: axisA.y_mm,
    bx_mm: axisB.x_mm,
    by_mm: axisB.y_mm,
  }));
  S.pending = null;
  clearTyped();
  ghosts.clear();
  S.ghostDims = [];
  setHint(`Mirrored ${S.selectedIds.size} entities.`);
}

async function finishArray(end) {
  const copies = arrayCount() - 1;
  if (copies < 1) throw new Error("n must be at least 2 for an array");
  await refreshFrom(await api("/api/op", "POST", {
    op: "ArrayLinear",
    entity_ids: [...S.selectedIds],
    dx_mm: end.x_mm - S.pending.a.x_mm,
    dy_mm: end.y_mm - S.pending.a.y_mm,
    dz_mm: 0,
    copies,
  }));
  S.pending = null;
  clearTyped();
  ghosts.clear();
  S.ghostDims = [];
  setHint(`Linear array: ${arrayCount()} items.`);
}

async function finishPolar(center) {
  const typed = activeLength();
  await refreshFrom(await api("/api/op", "POST", {
    op: "ArrayPolar",
    entity_ids: [...S.selectedIds],
    origin_x_mm: center.x_mm,
    origin_y_mm: center.y_mm,
    count: arrayCount(),
    angle_deg: typed != null ? typed : 360,
  }));
  S.pending = null;
  clearTyped();
  ghosts.clear();
  S.ghostDims = [];
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
  const byId = new Map((S.sceneState.points || []).map((point) => [point.entity_id, point]));
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
  const previous = S.tool;
  S.tool = next;
  S.pending = null;
  clearTyped();
  ghosts.clear();
  S.ghostDims = [];
  if (next === "trim" || next === "extend") {
    seedCuttersFromSelection();
  } else {
    S.cutterIds.clear();
  }
  for (const button of document.querySelectorAll("button[data-tool]")) {
    button.classList.toggle("active", button.dataset.tool === S.tool);
  }
  refreshToggles();
  if (next === "trim") {
    setHint(S.cutterIds.size
      ? `Trim (T): click the part to remove. ${S.cutterIds.size} cutter(s) pinned. Shift pins more.`
      : "Trim (T): click the part to remove. Shift pins a cutter. All lines cut if none pinned.");
  } else if (next === "extend") {
    setHint(S.cutterIds.size
      ? `Extend (E): click the end to grow. ${S.cutterIds.size} boundary line(s) pinned.`
      : "Extend (E): click the end to grow. Shift pins a boundary. All lines if none pinned.");
  } else {
    setHint(toolHints[S.tool] || "");
  }
  if (next === "trim" || next === "extend" || previous === "trim" || previous === "extend") rebuild();
}

async function reload() {
  await refreshFrom(await api("/api/scene"));
  lookAtScene(ISO_DIR, { up: WORLD_UP.clone() });
}

function nearestPoint(xyz, tolerance = SNAP_APERTURE_MM) {
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

function hitWorkplane(event) {
  return applySnaps(rawHit(event));
}

function wantOrtho(event) {
  return Boolean(S.orthoOn) !== Boolean(event && event.shiftKey);
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
  return S.gridSnapOn ? snapGrid(hit.z) : hit.z;
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
    S.pending
    && S.pending.kind === "polyline"
    && S.pending.pts.length >= 3
    && dist3(S.pending.pts[0], end) <= SNAP_APERTURE_MM,
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
  if (!S.pending) return null;
  if (S.pending.kind === "polyline") {
    const raw = rawHit(event);
    if (!raw) return null;
    const last = S.pending.pts[S.pending.pts.length - 1];
    if (S.pending.pts.length >= 3 && dist3(S.pending.pts[0], raw) <= SNAP_APERTURE_MM) {
      return { ...S.pending.pts[0], snap: "node" };
    }
    const hit = applySnaps(raw);
    if (!hit) return null;
    if (hit.snap === "node") return hit;
    return applyLength(last, orthogonalize(last, hit, event), activeLength());
  }
  const raw = hitWorkplane(event);
  if (!raw) return null;
  if (raw.snap === "node") return raw;
  if (S.pending.kind === "line" || S.pending.kind === "move" || S.pending.kind === "array" || S.pending.kind === "mirror" || (S.pending.kind === "radial" && S.tool !== "ellipse")) {
    return applyLength(S.pending.a, orthogonalize(S.pending.a, raw, event), activeLength());
  }
  if (S.pending.kind === "rect") {
    return orthogonalize(S.pending.a, raw, event);
  }
  return raw;
}

function updateGhost(event) {
  ghosts.clear();
  S.ghostDims = [];
  if (!event) {
    setCoords(null);
    return;
  }
  const hit = hitWorkplane(event);
  if (hit && (hit.snap === "node" || isGridSnap(hit.snap))) drawSnapMarker(hit, hit.snap);
  if ((S.tool === "trim" || S.tool === "extend") && !S.pending) {
    const picked = pickEntity(event);
    const preview = picked ? solveTrimOrExtend(picked, hit, S.tool) : null;
    if (preview) drawTrimPreview(preview);
    setCoords(hit);
    return;
  }
  if (S.tool === "break" && S.pending && S.pending.kind === "break") {
    const picked = pickEntity(event);
    const preview = solveBreak(S.pending.lineId, picked);
    if (preview) drawSnapMarker(preview.cut, "node");
    setCoords(hit);
    return;
  }
  if (!S.pending) {
    setCoords(hit);
    return;
  }
  if (S.pending.kind === "polyline") {
    const end = currentEnd(event);
    if (end) {
      ghostPolyline(S.pending.pts, end);
      const last = S.pending.pts[S.pending.pts.length - 1];
      setCoords(end, last);
      if (polylineCloses(end)) drawSnapMarker(S.pending.pts[0], "node");
    }
    return;
  }
  if (S.pending.kind === "line" || S.pending.kind === "move" || S.pending.kind === "array" || S.pending.kind === "mirror") {
    const end = currentEnd(event);
    if (end) {
      ghostLine(S.pending.a, end);
      setCoords(end, S.pending.a);
    }
    return;
  }
  if (S.pending.kind === "rotate") {
    const end = hitWorkplane(event);
    if (end) {
      ghostLine(S.pending.a, end);
      setCoords(end, S.pending.a);
    }
    return;
  }
  if (S.pending.kind === "rect") {
    const end = currentEnd(event);
    if (end) {
      ghostRect(S.pending.a, end);
      setCoords(end, S.pending.a);
    }
    return;
  }
  if (S.pending.kind === "height" || S.pending.kind === "extrude") {
    const height = hitHeight(event, S.pending.a, S.pending.b);
    ghostRect(S.pending.a, S.pending.b, height);
    setCoords(hit);
    return;
  }
  if (S.pending.kind === "radial") {
    const rim = currentEnd(event);
    if (!rim) return;
    const radius = dist3(S.pending.a, rim);
    if (S.tool === "circle") {
      addFaceGraphic(ghosts, sampleCircle(S.pending.a, radius).slice(0, -1), { fill: true, opacity: 0.22 });
    } else if (S.tool === "polygon") {
      addFaceGraphic(ghosts, regularPolygon(S.pending.a, rim, sidesValue()), { fill: true, opacity: 0.18 });
    } else if (S.tool === "ellipse") {
      const rx = Math.max(Math.abs(rim.x_mm - S.pending.a.x_mm), 1);
      const ry = Math.max(Math.abs(rim.y_mm - S.pending.a.y_mm), 1);
      addFaceGraphic(ghosts, sampleEllipse(S.pending.a, rx, ry).slice(0, -1), { fill: true, opacity: 0.22 });
    }
    setCoords(rim, S.pending.a);
    return;
  }
  if (S.pending.kind === "arc") {
    const cur = currentEnd(event) || hit;
    if (!cur) return;
    if (S.pending.pts.length === 1) {
      ghostLine(S.pending.pts[0], cur);
    } else {
      addCurve(ghosts, sampleArc(S.pending.pts[0], S.pending.pts[1], cur), 0x6cb3ff);
    }
    setCoords(cur, S.pending.pts[0]);
    return;
  }
  if (S.pending.kind === "bezier") {
    const cur = currentEnd(event) || hit;
    if (!cur) return;
    const pts = S.pending.pts.concat([cur]);
    if (pts.length === 2) ghostLine(pts[0], pts[1]);
    else if (pts.length === 3) addCurve(ghosts, sampleBezier([pts[0], pts[1], pts[2], pts[2]]), 0x6cb3ff);
    else addCurve(ghosts, sampleBezier(pts.slice(0, 4)), 0x6cb3ff);
    setCoords(cur, S.pending.pts[0]);
  }
}

async function finishLine(end) {
  if (dist3(S.pending.a, end) < 1) {
    setHint("Line: click a different point, or Esc to end the chain.");
    return;
  }
  const startId = await ensurePoint(S.pending.a);
  const endId = await ensurePoint(end);
  await refreshFrom(await api("/api/op", "POST", {
    op: "AddLine",
    start_id: startId,
    end_id: endId,
    label: S.pending.chain ? null : labelValue(),
  }));
  clearTyped();
  ghosts.clear();
  S.ghostDims = [];
  S.pending = {
    kind: "line",
    a: { x_mm: end.x_mm, y_mm: end.y_mm, z_mm: end.z_mm || 0, entity_id: endId },
    chain: true,
  };
  refreshToggles();
  setHint("Line: click the next point. Esc ends the chain.");
  if (S.lastPointer) updateGhost(S.lastPointer);
}

function polylineHint() {
  if (!S.pending || S.pending.pts.length < 2) {
    return "Polyline: click the next point.";
  }
  if (S.pending.pts.length < 3) {
    return "Polyline: click the next point, or Enter to finish.";
  }
  return "Polyline: click the next point, Enter to finish, click start or type C to close.";
}

async function appendPolylineVertex(end) {
  if (polylineCloses(end)) {
    await finishPolyline(true);
    return;
  }
  const last = S.pending.pts[S.pending.pts.length - 1];
  if (dist3(last, end) < 1) {
    setHint("Polyline: click a different point, Enter to finish, or Esc to cancel.");
    return;
  }
  S.pending.pts.push(end);
  clearTyped();
  setHint(polylineHint());
  if (S.lastPointer) updateGhost(S.lastPointer);
}

async function finishPolyline(closed) {
  const pts = S.pending.pts;
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
  S.pending = null;
  clearTyped();
  ghosts.clear();
  S.ghostDims = [];
  refreshToggles();
  setHint(closed ? "Closed polyline placed." : "Polyline placed. LMB starts another.");
}

async function finishFace(end) {
  await addFaceFromCorners(S.pending.a, end, labelValue());
  S.pending = null;
  clearTyped();
  ghosts.clear();
  S.ghostDims = [];
  refreshToggles();
  setHint("Rect placed.");
}

async function finishBox(event) {
  const height = hitHeight(event, S.pending.a, S.pending.b);
  const faceId = await addFaceFromCorners(S.pending.a, S.pending.b, labelValue());
  const distance = height === 0 ? 100 : height;
  await refreshFrom(await api("/api/op", "POST", {
    op: "Extrude",
    face_id: faceId,
    distance_mm: distance,
    label: labelValue() ? `${labelValue()}_solid` : null,
  }));
  S.pending = null;
  clearTyped();
  ghosts.clear();
  S.ghostDims = [];
  refreshToggles();
  setHint("Solid placed (face + extrude).");
}

async function finishExtrude(event) {
  const height = hitHeight(event, S.pending.a, S.pending.b);
  const distance = height === 0 ? 100 : height;
  await refreshFrom(await api("/api/op", "POST", {
    op: "Extrude",
    face_id: S.pending.profileId,
    distance_mm: distance,
    label: labelValue() ? `${labelValue()}_solid` : null,
  }));
  S.pending = null;
  clearTyped();
  ghosts.clear();
  S.ghostDims = [];
  refreshToggles();
  setHint("Solid placed.");
}

async function finishCircle(rim) {
  const radius = dist3(S.pending.a, rim);
  if (radius < 1) throw new Error("circle radius must be positive");
  const centerId = await ensurePoint(S.pending.a);
  await refreshFrom(await api("/api/op", "POST", {
    op: "AddCircle", center_id: centerId, radius_mm: radius, label: labelValue(),
  }));
  S.pending = null;
  clearTyped();
  ghosts.clear();
  S.ghostDims = [];
  refreshToggles();
  setHint("Circle placed. Select it, then Extrude.");
}

async function finishEllipse(rim) {
  const rx = Math.abs(rim.x_mm - S.pending.a.x_mm);
  const ry = Math.abs(rim.y_mm - S.pending.a.y_mm);
  if (rx < 1 || ry < 1) throw new Error("ellipse needs two positive radii");
  const centerId = await ensurePoint(S.pending.a);
  await refreshFrom(await api("/api/op", "POST", {
    op: "AddEllipse",
    center_id: centerId,
    radius_x_mm: rx,
    radius_y_mm: ry,
    label: labelValue(),
  }));
  S.pending = null;
  clearTyped();
  ghosts.clear();
  S.ghostDims = [];
  refreshToggles();
  setHint("Ellipse placed.");
}

async function finishPolygon(rim) {
  const pts = regularPolygon(S.pending.a, rim, sidesValue());
  const ids = [];
  for (const point of pts) ids.push(await ensurePoint(point));
  if (new Set(ids).size !== pts.length) {
    throw new Error("polygon vertices collapsed; draw a larger radius");
  }
  await refreshFrom(await api("/api/op", "POST", {
    op: "AddFace", point_ids: ids, label: labelValue(),
  }));
  S.pending = null;
  clearTyped();
  ghosts.clear();
  S.ghostDims = [];
  refreshToggles();
  setHint("Polygon placed.");
}

async function finishArc(end) {
  const ids = [];
  for (const point of S.pending.pts.concat([end])) ids.push(await ensurePoint(point));
  await refreshFrom(await api("/api/op", "POST", {
    op: "AddArc",
    start_id: ids[0],
    mid_id: ids[1],
    end_id: ids[2],
    label: labelValue(),
  }));
  S.pending = null;
  clearTyped();
  ghosts.clear();
  S.ghostDims = [];
  refreshToggles();
  setHint("Arc placed.");
}

async function finishBezier(end) {
  const ids = [];
  for (const point of S.pending.pts.concat([end])) ids.push(await ensurePoint(point));
  await refreshFrom(await api("/api/op", "POST", {
    op: "AddBezier", point_ids: ids, label: labelValue(),
  }));
  S.pending = null;
  clearTyped();
  ghosts.clear();
  S.ghostDims = [];
  refreshToggles();
  setHint("Bézier placed.");
}

async function onClick(event) {
  try {
    if (S.tool === "select") {
      const picked = pickEntity(event);
      setSelection(picked, { shift: event.shiftKey });
      if (picked == null && !event.shiftKey) setHint("Selection cleared.");
      return;
    }
    if (S.tool === "move") {
      if (S.selectedIds.size === 0) {
        setHint("Select entities first, then Move.");
        return;
      }
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      if (!S.pending) {
        S.pending = { kind: "move", a: xyz };
        setHint("Move: click the destination, or type a length and Enter.");
        return;
      }
      const end = currentEnd(event);
      if (!end) return;
      await finishMove(end);
      return;
    }
    if (S.tool === "rotate") {
      if (S.selectedIds.size === 0) {
        setHint("Select entities first, then Rotate.");
        return;
      }
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      if (!S.pending) {
        S.pending = { kind: "rotate", a: xyz };
        setHint("Rotate: type degrees and Enter, or click a second point for the angle.");
        return;
      }
      const typed = activeLength();
      const end = hitWorkplane(event);
      if (typed == null && !end) return;
      const angle = typed != null
        ? typed
        : Math.atan2(end.y_mm - S.pending.a.y_mm, end.x_mm - S.pending.a.x_mm) * 180 / Math.PI;
      await finishRotate(S.pending.a, angle);
      return;
    }
    if (S.tool === "mirror") {
      if (S.selectedIds.size === 0) {
        setHint("Select entities first, then Mirror.");
        return;
      }
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      if (!S.pending) {
        S.pending = { kind: "mirror", a: xyz };
        setHint("Mirror: click the second point of the axis.");
        return;
      }
      const end = currentEnd(event);
      if (!end) return;
      await finishMirror(S.pending.a, end);
      return;
    }
    if (S.tool === "array") {
      if (S.selectedIds.size === 0) {
        setHint("Select entities first, then Array. n is the count.");
        return;
      }
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      if (!S.pending) {
        S.pending = { kind: "array", a: xyz };
        setHint("Array: click the spacing to the next copy. n is the total count.");
        return;
      }
      const end = currentEnd(event);
      if (!end) return;
      await finishArray(end);
      return;
    }
    if (S.tool === "polar") {
      if (S.selectedIds.size === 0) {
        setHint("Select entities first, then Polar. n is the count.");
        return;
      }
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      await finishPolar(xyz);
      return;
    }
    if (S.tool === "chamfer") {
      await finishCorner("chamfer", event);
      return;
    }
    if (S.tool === "fillet") {
      await finishCorner("fillet", event);
      return;
    }
    if (S.tool === "trim" || S.tool === "extend") {
      const picked = pickEntity(event);
      const row = findRecord(picked);
      if (event.shiftKey && row && row.kind === "Line") {
        if (S.cutterIds.has(picked)) S.cutterIds.delete(picked);
        else S.cutterIds.add(picked);
        rebuild();
        const noun = S.tool === "extend" ? "boundary" : "cutter";
        setHint(S.cutterIds.size
          ? `${S.tool === "extend" ? "Extend" : "Trim"}: ${S.cutterIds.size} ${noun}(s). Click a part.`
          : `${S.tool === "extend" ? "Extend" : "Trim"}: all lines. Click a part.`);
        return;
      }
      if (!row || row.kind !== "Line") {
        setHint(S.tool === "extend"
          ? "Extend: click the end to grow, or Shift-click a boundary."
          : "Trim: click the part to remove, or Shift-click a cutter.");
        return;
      }
      const click = hitWorkplane(event);
      const preview = solveTrimOrExtend(picked, click, S.tool);
      if (!preview) {
        setHint(S.tool === "extend"
          ? "Extend: click the short end toward a boundary (implied intersection is OK)."
          : "Trim: click a free end — the stub past the nearest cutter.");
        return;
      }
      await commitTrimPreview(preview);
      return;
    }
    if (S.tool === "break") {
      const picked = pickEntity(event);
      const row = findRecord(picked);
      if (!row || row.kind !== "Line") {
        setHint("Break: click the first line.");
        return;
      }
      if (!S.pending) {
        S.pending = { kind: "break", lineId: picked };
        setHint("Break: click the crossing line.");
        return;
      }
      const preview = solveBreak(S.pending.lineId, picked);
      if (!preview) {
        setHint("Break: those lines do not cross. Click another line.");
        return;
      }
      await commitBreak(preview);
      return;
    }
    if (S.tool === "node") {
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
    if (S.tool === "extrude") {
      const profileId = selectedProfileId();
      if (profileId == null) {
        setHint("Select a face, circle, or ellipse first.");
        return;
      }
      if (!S.pending) {
        const extents = profileExtents(profileId);
        if (!extents) return;
        S.pending = { kind: "extrude", a: extents.a, b: extents.b, profileId };
        setHint("Extrude: move for height, then click or Enter.");
        return;
      }
      await finishExtrude(event);
      return;
    }
    if (S.tool === "line") {
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      if (!S.pending) {
        S.pending = { kind: "line", a: xyz };
        setHint("Line: click the next point, or type a length and Enter.");
        return;
      }
      const end = currentEnd(event);
      if (!end) return;
      await finishLine(end);
      return;
    }
    if (S.tool === "polyline") {
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      if (!S.pending) {
        S.pending = { kind: "polyline", pts: [xyz] };
        setHint("Polyline: click the next point.");
        return;
      }
      const end = currentEnd(event);
      if (!end) return;
      await appendPolylineVertex(end);
      return;
    }
    if (S.tool === "rect") {
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      if (!S.pending) {
        S.pending = { kind: "rect", a: xyz };
        setHint("Rect: click the opposite corner.");
        return;
      }
      const end = currentEnd(event);
      if (!end) return;
      await finishFace(end);
      return;
    }
    if (S.tool === "circle" || S.tool === "polygon" || S.tool === "ellipse") {
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      if (!S.pending) {
        S.pending = { kind: "radial", a: xyz };
        setHint(S.tool === "circle"
          ? "Circle: click the radius, or type it and Enter."
          : S.tool === "polygon"
            ? "Polygon: click the radius."
            : "Ellipse: click a corner of the bounding box.");
        return;
      }
      const rim = currentEnd(event);
      if (!rim) return;
      if (S.tool === "circle") await finishCircle(rim);
      else if (S.tool === "polygon") await finishPolygon(rim);
      else await finishEllipse(rim);
      return;
    }
    if (S.tool === "arc") {
      const xyz = currentEnd(event) || hitWorkplane(event);
      if (!xyz) return;
      if (!S.pending) {
        S.pending = { kind: "arc", pts: [xyz] };
        setHint("Arc: click a second point on the arc.");
        return;
      }
      if (S.pending.pts.length === 1) {
        S.pending.pts.push(xyz);
        setHint("Arc: click the end point.");
        return;
      }
      await finishArc(xyz);
      return;
    }
    if (S.tool === "bezier") {
      const xyz = currentEnd(event) || hitWorkplane(event);
      if (!xyz) return;
      if (!S.pending) {
        S.pending = { kind: "bezier", pts: [xyz] };
        setHint("Bézier: click control point 2.");
        return;
      }
      if (S.pending.pts.length < 3) {
        S.pending.pts.push(xyz);
        setHint(`Bézier: click control point ${S.pending.pts.length + 1}.`);
        return;
      }
      await finishBezier(xyz);
      return;
    }
    if (S.tool === "box") {
      if (!S.pending) {
        const xyz = hitWorkplane(event);
        if (!xyz) return;
        S.pending = { kind: "rect", a: xyz };
        setHint("Box: click the opposite corner of the face.");
        return;
      }
      if (S.pending.kind === "rect") {
        const end = currentEnd(event);
        if (!end) return;
        S.pending = { kind: "height", a: S.pending.a, b: end };
        setHint("Box: move for height, type a length, then click or Enter.");
        return;
      }
      await finishBox(event);
    }
  } catch (error) {
    setHint(error.message);
    S.pending = null;
    ghosts.clear();
    S.ghostDims = [];
  }
}

async function commitWithEnter() {
  if (!S.pending) {
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
    if (S.pending.kind === "polyline") {
      const token = echoed.trim().toLowerCase();
      if (token === "c" || token === "close") {
        await finishPolyline(true);
        return;
      }
      if (activeLength() != null && S.lastPointer) {
        const end = currentEnd(S.lastPointer);
        if (end) await appendPolylineVertex(end);
        return;
      }
      await finishPolyline(false);
      return;
    }
    if (S.pending.kind === "rotate") {
      const typed = activeLength();
      if (typed != null) {
        await finishRotate(S.pending.a, typed);
        return;
      }
      if (!S.lastPointer) return;
      const end = hitWorkplane(S.lastPointer);
      if (end) {
        await finishRotate(
          S.pending.a,
          Math.atan2(end.y_mm - S.pending.a.y_mm, end.x_mm - S.pending.a.x_mm) * 180 / Math.PI,
        );
      }
      return;
    }
    if (!S.lastPointer) return;
    if (S.pending.kind === "line" || S.pending.kind === "move" || S.pending.kind === "array" || S.pending.kind === "mirror") {
      const end = currentEnd(S.lastPointer);
      if (end) {
        if (S.pending.kind === "move") await finishMove(end);
        else if (S.pending.kind === "array") await finishArray(end);
        else if (S.pending.kind === "mirror") await finishMirror(S.pending.a, end);
        else await finishLine(end);
      }
      return;
    }
    if (S.pending.kind === "rect" && S.tool === "rect") {
      const end = currentEnd(S.lastPointer);
      if (end) await finishFace(end);
      return;
    }
    if (S.pending.kind === "radial") {
      const rim = currentEnd(S.lastPointer);
      if (!rim) return;
      if (S.tool === "circle") await finishCircle(rim);
      else if (S.tool === "polygon") await finishPolygon(rim);
      else if (S.tool === "ellipse") await finishEllipse(rim);
      return;
    }
    if (S.pending.kind === "arc" && S.pending.pts.length === 2) {
      const end = currentEnd(S.lastPointer);
      if (end) await finishArc(end);
      return;
    }
    if (S.pending.kind === "bezier" && S.pending.pts.length === 3) {
      const end = currentEnd(S.lastPointer);
      if (end) await finishBezier(end);
      return;
    }
    if (S.pending.kind === "rect" && S.tool === "box") {
      const end = currentEnd(S.lastPointer);
      if (!end) return;
      S.pending = { kind: "height", a: S.pending.a, b: end };
      setHint("Box: move for height, type a length, then click or Enter.");
      updateGhost(S.lastPointer);
      return;
    }
    if (S.pending.kind === "height") await finishBox(S.lastPointer);
    if (S.pending.kind === "extrude") await finishExtrude(S.lastPointer);
  } catch (error) {
    setHint(error.message);
    S.pending = null;
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
  setProjectionMode(S.projection === "perspective" ? "parallel" : "perspective");
});
snapButton.addEventListener("click", () => {
  S.snapOn = !S.snapOn;
  refreshToggles();
  if (S.lastPointer) updateGhost(S.lastPointer);
});
gridSnapButton.addEventListener("click", () => {
  setGridSnapOn(!S.gridSnapOn);
  if (S.lastPointer) updateGhost(S.lastPointer);
});
orthoButton.addEventListener("click", () => {
  S.orthoOn = !S.orthoOn;
  refreshToggles();
  if (S.lastPointer) updateGhost(S.lastPointer);
});
gridButton.addEventListener("click", () => {
  setGridOn(!S.gridOn);
  if (S.lastPointer) updateGhost(S.lastPointer);
});
consoleInput.addEventListener("input", () => {
  refreshToggles();
  if (S.lastPointer) updateGhost(S.lastPointer);
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
  if (S.tool === "select" && !event.altKey) {
    S.marqueeOrigin = { x: event.clientX, y: event.clientY };
    canvas.setPointerCapture(event.pointerId);
  }
}, true);
canvas.addEventListener("pointermove", (event) => {
  S.lastPointer = event;
  if (S.marqueeOrigin) updateMarquee(event);
  updatePreselect(event);
  updateGhost(event);
});
canvas.addEventListener("pointerup", (event) => {
  controls.mouseButtons.LEFT = -1;
  if (event.button !== 0 || !pointerDown) return;
  const origin = S.marqueeOrigin;
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
    S.snapOn = !S.snapOn;
    refreshToggles();
    if (S.lastPointer) updateGhost(S.lastPointer);
    return;
  }
  if (event.key === "F7") {
    event.preventDefault();
    setGridSnapOn(!S.gridSnapOn);
    if (S.lastPointer) updateGhost(S.lastPointer);
    return;
  }
  if (event.key === "F8") {
    event.preventDefault();
    S.orthoOn = !S.orthoOn;
    refreshToggles();
    if (S.lastPointer) updateGhost(S.lastPointer);
    return;
  }
  if (event.key === "F9") {
    event.preventDefault();
    setGridOn(!S.gridOn);
    if (S.lastPointer) updateGhost(S.lastPointer);
    return;
  }
  if (event.key === "F2") {
    if (isTypingField(event) || event.target === consoleInput) return;
    event.preventDefault();
    if (S.selectedIds.size !== 1) {
      setHint("Select one entity to rename.");
      return;
    }
    const id = [...S.selectedIds][0];
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
    if (S.pending) {
      const endedChain = S.pending.kind === "line" && S.pending.chain;
      S.pending = null;
      clearTyped();
      ghosts.clear();
      S.ghostDims = [];
      hideMarquee();
      refreshToggles();
      setHint(endedChain
        ? "Line chain ended. Click to start another, or Esc for Select."
        : "Cancelled.");
      return;
    }
    if (S.tool !== "select") {
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
    if (S.tool === "select") {
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
    setProjectionMode(S.projection === "perspective" ? "parallel" : "perspective");
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
    if (S.lastPointer) updateGhost(S.lastPointer);
    return;
  }
  if (event.key.length === 1 && /[0-9.]/.test(event.key)) {
    if (event.key === "." && consoleInput.value.includes(".")) return;
    setTyped(consoleInput.value + event.key);
    refreshToggles();
    if (S.lastPointer) updateGhost(S.lastPointer);
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

function applyViz() {
  const pal = BACKGROUNDS[S.prefs.background] || BACKGROUNDS.g5;
  scene.background.setHex(pal.bg);
  document.getElementById("stage").style.background = `#${pal.bg.toString(16).padStart(6, "0")}`;
  rebuildGrid();
  const dark = S.prefs.background === "g2";
  hemi.color.setHex(dark ? 0xc8cdd3 : 0xf4f7fb);
  hemi.groundColor.setHex(S.prefs.ao ? (dark ? 0x0a0a0a : 0x6e757c) : (dark ? 0x2a2a2a : 0xc5cad0));
  hemi.intensity = S.prefs.ao ? 0.58 : 0.42;
  keyLight.visible = S.prefs.keyLight;
  keyLight.intensity = S.prefs.keyLight ? 0.45 : 0;
  contact.visible = S.prefs.ao;
  contact.material.opacity = dark ? 0.18 : 0.06;
  rebuild();
}

function syncPrefsForm() {
  document.getElementById("pref-background").value = S.prefs.background;
  document.getElementById("pref-clay").value = String(S.prefs.clay);
  document.getElementById("pref-curve").value = S.prefs.curve;
  document.getElementById("pref-key").checked = S.prefs.keyLight;
  document.getElementById("pref-ao").checked = S.prefs.ao;
  document.getElementById("pref-edges").checked = S.prefs.showEdges;
  document.getElementById("pref-curves").checked = S.prefs.showCurves;
  document.getElementById("pref-faces").checked = S.prefs.showFaces;
}

function readPrefsForm() {
  S.prefs = {
    background: document.getElementById("pref-background").value,
    clay: Number(document.getElementById("pref-clay").value) || 176,
    curve: document.getElementById("pref-curve").value,
    keyLight: document.getElementById("pref-key").checked,
    ao: document.getElementById("pref-ao").checked,
    showEdges: document.getElementById("pref-edges").checked,
    showCurves: document.getElementById("pref-curves").checked,
    showFaces: document.getElementById("pref-faces").checked,
    grid: S.gridOn,
    gridSnap: S.gridSnapOn,
    gridMinorOn: S.gridMinorOn,
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
  if (S.lastPointer) updateGhost(S.lastPointer);
}

function downloadJson(filename) {
  const blob = new Blob([JSON.stringify(S.sceneState.document, null, 2)], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  URL.revokeObjectURL(link.href);
}

function saveDocument(saveAs = false) {
  if (saveAs) {
    const next = window.prompt("Save as", S.saveName) || "";
    if (!next.trim()) return;
    S.saveName = next.trim().endsWith(".json") ? next.trim() : `${next.trim()}.json`;
  }
  downloadJson(S.saveName);
  setHint(`Saved ${S.saveName}. Preferences are not in this file.`);
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
  S.pending = null;
  ghosts.clear();
  S.selectedIds.clear();
  await refreshFrom(await api("/api/load", "POST", dict));
  if (name) S.saveName = name;
  S.namedView = null;
  viewUp.copy(WORLD_UP);
  bindProjectionCamera();
  lookAtScene(ISO_DIR, { up: WORLD_UP.clone() });
  setHint(`Opened ${S.saveName}.`);
}

async function newDocument() {
  S.pending = null;
  ghosts.clear();
  S.selectedIds.clear();
  await refreshFrom(await api("/api/reset", "POST", {}));
  S.saveName = "apecad.json";
  S.namedView = null;
  viewUp.copy(WORLD_UP);
  bindProjectionCamera();
  lookAtScene(ISO_DIR, { up: WORLD_UP.clone() });
  setHint("New document.");
}

async function undoDocument() {
  S.pending = null;
  ghosts.clear();
  await refreshFrom(await api("/api/undo", "POST", {}));
}

async function redoDocument() {
  await refreshFrom(await api("/api/redo", "POST", {}));
}

function selectAll() {
  indexBrep();
  const ids = S.selectFilter === "element"
    ? brepRoots().map((row) => row.id)
    : catalog().filter((row) => FILTER_KINDS[S.selectFilter].has(row.kind)).map((row) => row.id);
  S.selectedIds = new Set(ids);
  rebuild();
  setHint(S.selectedIds.size ? `${S.selectedIds.size} selected.` : "Nothing to select.");
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
    return setProjectionMode(S.projection === "perspective" ? "parallel" : "perspective");
  }
  if (cmd === "snap") {
    S.snapOn = !S.snapOn;
    refreshToggles();
    return;
  }
  if (cmd === "grid-snap") {
    setGridSnapOn(!S.gridSnapOn);
    return;
  }
  if (cmd === "ortho") {
    S.orthoOn = !S.orthoOn;
    refreshToggles();
    return;
  }
  if (cmd === "grid") {
    setGridOn(!S.gridOn);
    return;
  }
  if (cmd === "fit") return document.getElementById("view-fit").click();
  if (cmd === "iso") return document.getElementById("view-iso").click();
  if (cmd === "viewcube") {
    S.viewCubeOn = !S.viewCubeOn;
    document.getElementById("viewcube-wrap").hidden = !S.viewCubeOn;
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
