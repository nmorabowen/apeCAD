// The Model outliner (B-rep tree), its context menu, rename, and the Properties dock.
import * as THREE from "three";
import { S } from "./state.js";
import { api } from "./api.js";
import {
  brepChildren,
  brepKind,
  brepRoots,
  catalog,
  collectNested,
  gatherPoints,
  pointById,
} from "./brep.js";
import { camera, fitView, frameDistance, goToView, resetViewZoom } from "./camera.js";
import { setHint } from "./cmdline.js";
import { circumcircle, dist3 } from "./geom.js";
import { gridMinorMm } from "./grid.js";
import { formatMm } from "./prefs.js";
import { rebuild, refreshFrom } from "./render.js";
import { setSelection } from "./selection.js";
import { ISO_DIR, VIEW_PRESETS, controls, viewUp } from "./viewport.js";

export const treeEl = document.getElementById("tree");
const propBody = document.getElementById("prop-body");
export const collapsedTree = new Set();

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

export const ctxMenu = document.getElementById("ctx-menu");
export let ctxRow = null;

export function closeTreeMenu() {
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

export function hideSubtree(row, hide) {
  const ids = new Set([row.id]);
  collectNested(row, ids);
  for (const id of ids) {
    if (hide) S.hiddenIds.add(id);
    else S.hiddenIds.delete(id);
  }
  rebuild();
}

export function beginRename(row, rowEl) {
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

export function fitEntity(row) {
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

export async function duplicateEntities(ids) {
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

export function refreshDocks() {
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
