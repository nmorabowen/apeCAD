// The selection set, the selection filter, and window / crossing marquee selection.
import * as THREE from "three";
import { S } from "./state.js";
import {
  FILTER_KINDS,
  SELECT_FILTERS,
  brepRoots,
  catalog,
  findRecord,
  gatherPoints,
  indexBrep,
  isProfile,
  owningSolidId,
  pointById,
  rootId,
} from "./brep.js";
import { camera } from "./camera.js";
import { refreshToggles, setHint } from "./cmdline.js";
import { sampleCircle } from "./geom.js";
import { rebuild } from "./render.js";
import { shapeQualifies } from "./screen.js";
import { canvas } from "./viewport.js";

const marqueeEl = document.getElementById("marquee");

export function selectedProfileId() {
  const profiles = [...S.selectedIds].filter((id) => isProfile(id));
  return profiles.length === 1 ? profiles[0] : null;
}

function filterSelectionIds(ids) {
  indexBrep();
  if (S.selectFilter === "element") {
    return [...new Set(ids.map((id) => rootId(id)))];
  }
  if (S.selectFilter === "solid") {
    const solids = new Set();
    for (const id of ids) {
      const row = findRecord(id);
      if (row && FILTER_KINDS.solid.has(row.kind)) solids.add(id);
      const owner = owningSolidId(id);
      if (owner != null) solids.add(owner);
    }
    return [...solids];
  }
  const kinds = FILTER_KINDS[S.selectFilter];
  return ids.filter((id) => {
    const row = findRecord(id);
    return row && kinds.has(row.kind);
  });
}

function convertSelectionToFilter(filter) {
  indexBrep();
  const next = new Set();
  if (filter === "element") {
    for (const id of S.selectedIds) next.add(rootId(id));
    return next;
  }
  const kinds = FILTER_KINDS[filter];
  for (const id of S.selectedIds) {
    const row = findRecord(id);
    if (!row) continue;
    if (kinds.has(row.kind)) {
      next.add(id);
      continue;
    }
    const stack = [...(S.brepChildrenOf.get(id) || [])];
    const seen = new Set();
    while (stack.length) {
      const childId = stack.pop();
      if (seen.has(childId)) continue;
      seen.add(childId);
      const child = findRecord(childId);
      if (child && kinds.has(child.kind)) next.add(childId);
      stack.push(...(S.brepChildrenOf.get(childId) || []));
    }
    if (filter === "solid") {
      const owner = owningSolidId(id);
      if (owner != null) next.add(owner);
    } else {
      const up = [...(S.brepParentsOf.get(id) || [])];
      const seenUp = new Set();
      while (up.length) {
        const parentId = up.pop();
        if (seenUp.has(parentId)) continue;
        seenUp.add(parentId);
        const parent = findRecord(parentId);
        if (parent && kinds.has(parent.kind)) next.add(parentId);
        up.push(...(S.brepParentsOf.get(parentId) || []));
      }
    }
  }
  return next;
}

function clientOf(xMm, yMm, zMm = 0) {
  const vector = new THREE.Vector3(xMm, yMm, zMm).project(camera());
  const rect = canvas.getBoundingClientRect();
  return {
    x: rect.left + (vector.x * 0.5 + 0.5) * rect.width,
    y: rect.top + (-vector.y * 0.5 + 0.5) * rect.height,
  };
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

export function hideMarquee() {
  S.marqueeOrigin = null;
  marqueeEl.hidden = true;
  marqueeEl.classList.remove("crossing");
}

export function updateMarquee(event) {
  if (!S.marqueeOrigin) return;
  const stage = document.getElementById("stage").getBoundingClientRect();
  const x0 = S.marqueeOrigin.x;
  const y0 = S.marqueeOrigin.y;
  const x1 = event.clientX;
  const y1 = event.clientY;
  marqueeEl.hidden = false;
  marqueeEl.classList.toggle("crossing", x1 < x0);
  marqueeEl.style.left = `${Math.min(x0, x1) - stage.left}px`;
  marqueeEl.style.top = `${Math.min(y0, y1) - stage.top}px`;
  marqueeEl.style.width = `${Math.abs(x1 - x0)}px`;
  marqueeEl.style.height = `${Math.abs(y1 - y0)}px`;
}

export function windowHits(origin, event) {
  const crossing = event.clientX < origin.x;
  const rect = {
    left: Math.min(origin.x, event.clientX),
    right: Math.max(origin.x, event.clientX),
    top: Math.min(origin.y, event.clientY),
    bottom: Math.max(origin.y, event.clientY),
  };
  return filterSelectionIds(entitiesInWindow(rect, crossing));
}

export function setSelection(id, { shift = false } = {}) {
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

export function setSelectFilter(next) {
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

export function applyWindowSelect(origin, event) {
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

export function selectAll() {
  indexBrep();
  const ids = S.selectFilter === "element"
    ? brepRoots().map((row) => row.id)
    : catalog().filter((row) => FILTER_KINDS[S.selectFilter].has(row.kind)).map((row) => row.id);
  S.selectedIds = new Set(ids);
  rebuild();
  setHint(S.selectedIds.size ? `${S.selectedIds.size} selected.` : "Nothing to select.");
}
