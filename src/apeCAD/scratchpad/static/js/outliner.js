// The Model outliner (B-rep tree), its context menu, rename, and the Properties dock.
import * as THREE from "three";
import { S } from "./state.js";
import { notifySelectionChanged, store } from "./store.js";
import { entities, t } from "./strings.js";
import { api } from "./api.js";
import {
  brepChildren,
  brepKind,
  brepRoots,
  catalog,
  collectNested,
  gatherPoints,
  outlinerChildren,
  pointById,
} from "./brep.js";
import { camera, fitView, frameDistance, goToView, resetViewZoom } from "./camera.js";
import { refuse, setHint } from "./cmdline.js";
import { circumcircle, dist3 } from "./geom.js";
import { gridMinorMm } from "./grid.js";
import { commitDelete } from "./modify.js";
import { formatMm } from "./prefs.js";
import { rebuild, refreshFrom, registerDockHooks } from "./render.js";
import { renderSectionProps } from "./section-props.js";
import { sectionFields } from "./section.js";
import { setSelection } from "./selection.js";
import { ISO_DIR, VIEW_PRESETS, controls, viewUp } from "./viewport.js";

export const treeEl = document.getElementById("tree");
const propBody = document.getElementById("prop-body");
const collapsedTree = new Set();

function renderTreeNode(row, parent) {
  const kids = outlinerChildren(brepChildren(row), S.selectFilter);
  const node = document.createElement("div");
  node.className = "tree-node";
  const rowEl = document.createElement("div");
  const dimmed = S.hiddenIds.has(row.id);
  const hovered = S.hoverIds && S.hoverIds.has(row.id);
  rowEl.className = `tree-row${S.selectedIds.has(row.id) ? " selected" : ""}${hovered ? " hovered" : ""}${dimmed ? " dimmed" : ""}`;
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
  nameEl.textContent = row.name;
  rowEl.append(toggle, kindEl, nameEl);
  rowEl.addEventListener("click", (event) => setSelection(row.id, { shift: event.shiftKey }));
  rowEl.addEventListener("dblclick", (event) => {
    event.preventDefault();
    beginRename(row, rowEl);
  });
  rowEl.addEventListener("pointerenter", () => {
    store.dispatch({ type: "hover/set", ids: [row.id] });
    notifySelectionChanged();
  });
  rowEl.addEventListener("pointerleave", () => {
    store.dispatch({ type: "hover/clear" });
    notifySelectionChanged();
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
  addItem(t("menu.ctx.select"), "select");
  addItem(t("menu.ctx.rename"), "rename", "F2");
  addItem(t("menu.ctx.duplicate"), "duplicate");
  addItem(t(hidden ? "menu.ctx.show" : "menu.ctx.hide"), hidden ? "show" : "hide");
  addItem(t("menu.ctx.fit"), "fit");
  const sep = document.createElement("div");
  sep.className = "menu-sep";
  ctxMenu.append(sep);
  if (kids.length) addItem(t(collapsedTree.has(row.id) ? "menu.ctx.expand" : "menu.ctx.collapse"), "toggle");
  addItem(t("menu.ctx.delete"), "delete", "Del");
  ctxMenu.hidden = false;
  ctxMenu.classList.add("open");
  const pad = 6;
  const rect = ctxMenu.getBoundingClientRect();
  const left = Math.min(x, window.innerWidth - rect.width - pad);
  const top = Math.min(y, window.innerHeight - rect.height - pad);
  ctxMenu.style.left = `${Math.max(pad, left)}px`;
  ctxMenu.style.top = `${Math.max(pad, top)}px`;
}

function hideSubtree(row, hide) {
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
      setHint(next ? t("done.renamed", { name: next }) : t("done.labelCleared"));
    } catch (error) {
      refuse(error);
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
  input.addEventListener("blur", () => {
    if (!input.isConnected) {
      finished = true;
      return;
    }
    finish(true);
  });
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
    setHint(t("hint.selectFirst", { verb: "Duplicate" }));
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
  setHint(t("done.duplicated", { entities: entities(ids.length) }));
}

export function syncTreeHighlight() {
  for (const rowEl of treeEl.querySelectorAll(".tree-row[data-id]")) {
    const raw = rowEl.dataset.id;
    const num = Number(raw);
    const id = Number.isFinite(num) ? num : raw;
    rowEl.classList.toggle("selected", S.selectedIds.has(id));
    rowEl.classList.toggle("hovered", Boolean(S.hoverIds && S.hoverIds.has(id)));
    rowEl.classList.toggle("dimmed", S.hiddenIds.has(id));
  }
}

export function refreshProps(rows = catalog()) {
  for (const id of [...S.selectedIds]) {
    if (!rows.some((row) => row.id === id)) S.selectedIds.delete(id);
  }
  if (S.selectedIds.size === 0) {
    propBody.textContent = t("props.none");
    return;
  }
  if (renderSectionProps(propBody, rows)) {
    return;
  }
  if (S.selectedIds.size > 1) {
    propBody.textContent = t("props.many", { n: S.selectedIds.size });
    return;
  }
  const selected = rows.find((row) => S.selectedIds.has(row.id)) || null;
  if (!selected) {
    propBody.textContent = t("props.none");
    return;
  }
  const fields = propertyFields(selected);
  propBody.innerHTML = fields.map(([key, value]) => (
    `<div class="prop"><dt>${key}</dt><dd>${value}</dd></div>`
  )).join("");
}

export function syncSelectionDocks() {
  syncTreeHighlight();
  refreshProps();
}

export function refreshDocks() {
  const rows = catalog();
  for (const id of [...S.selectedIds]) {
    if (!rows.some((row) => row.id === id)) S.selectedIds.delete(id);
  }
  treeEl.innerHTML = "";
  const roots = brepRoots();
  if (!roots.length) {
    treeEl.textContent = t("tree.empty");
  } else {
    for (const row of roots) renderTreeNode(row, treeEl);
  }
  refreshProps(rows);
}

registerDockHooks({
  refreshDocks,
  syncSelectionDocks,
});

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
  fields.push(...sectionFields(row.kind, item));
  return fields;
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
    duplicateEntities(ids).catch((error) => refuse(error));
    return;
  }
  if (cmd === "hide") {
    hideSubtree(row, true);
    setHint(t("hint.hidden"));
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
    commitDelete().catch((error) => refuse(error));
  }
}

export function bindOutliner() {
  ctxMenu.addEventListener("click", (event) => {
    const button = event.target.closest("[data-tree-cmd]");
    if (!button || !ctxRow) return;
    event.stopPropagation();
    const row = ctxRow;
    const cmd = button.dataset.treeCmd;
    closeTreeMenu();
    runTreeCommand(cmd, row);
  });
  document.getElementById("tree-wrap").addEventListener("contextmenu", (event) => {
    event.preventDefault();
  });
}
