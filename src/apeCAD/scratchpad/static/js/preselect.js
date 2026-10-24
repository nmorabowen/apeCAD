// Hover highlight (preselection) of what a click would select, shared across canvas pointer,
// outliner row hover, and status warning chip hover (ADR 0035).
import * as THREE from "three";
import { S } from "./state.js";
import { notifySelectionChanged, requestRender, setsEqual } from "./store.js";
import {
  FILTER_KINDS,
  curveWorldPoints,
  descendantIds,
  findRecord,
  indexBrep,
  owningSolidId,
  pointById,
  profileWorldPoints,
} from "./brep.js";
import { addCurve, addCylinder, addPlanarFace, xyzMm } from "./draw.js";
import { pickByFilter } from "./pick.js";
import { sectionShape } from "./section.js";
import { INK } from "./theme.js";
import { windowHits } from "./selection.js";
import { canvas, disposeObject3D, preselects } from "./viewport.js";

let preselectKey = "";

function addHoverDot(point) {
  const p = xyzMm(point);
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute([p.x_mm, p.y_mm, p.z_mm], 3));
  const dot = new THREE.Points(geometry, new THREE.PointsMaterial({
    color: INK.hover,
    size: 12,
    sizeAttenuation: false,
    depthTest: false,
    depthWrite: false,
  }));
  dot.renderOrder = 22;
  dot.raycast = () => {};
  preselects.add(dot);
}

function drawPreselectEntity(id, shown) {
  if (shown.has(id)) return;
  shown.add(id);
  const row = findRecord(id);
  if (!row) return;
  const asSolid = FILTER_KINDS.solid.has(row.kind)
    || (S.selectFilter === "element" && owningSolidId(id) === id);
  if (asSolid) {
    for (const childId of descendantIds(id)) {
      const child = findRecord(childId);
      if (child && FILTER_KINDS.face.has(child.kind)) drawPreselectEntity(childId, shown);
    }
    if (row.kind === "Solid") {
      const profile = findRecord(row.item.face_id);
      const height = Math.abs(row.item.distance_mm);
      if (profile && profile.kind === "Circle") {
        const center = pointById(profile.item.center_id);
        if (center) {
          const originZ = row.item.distance_mm >= 0 ? center.z_mm : center.z_mm - height;
          addCylinder(
            preselects, center.x_mm, center.y_mm, profile.item.radius_mm,
            originZ, height, INK.hover, 0.28, row.id,
          );
        }
      }
    }
    return;
  }
  if (row.kind === "Point") {
    addHoverDot(row.item);
    return;
  }
  if (FILTER_KINDS.section.has(row.kind)) {
    const shape = sectionShape(row.kind, row.item);
    if (shape) addCurve(preselects, shape.closed ? shape.pts.concat([shape.pts[0]]) : shape.pts, INK.hover, row.id);
    return;
  }
  if (FILTER_KINDS.line.has(row.kind)) {
    const shape = curveWorldPoints(row);
    if (shape) addCurve(preselects, shape.closed ? shape.pts.concat([shape.pts[0]]) : shape.pts, INK.hover, row.id);
    return;
  }
  if (FILTER_KINDS.face.has(row.kind)) {
    const pts = profileWorldPoints(row);
    if (pts.length >= 3) addPlanarFace(preselects, pts, row.id);
  }
}

export function syncHoverPreselect() {
  const ids = [...(S.hoverIds || [])];
  const key = `${S.selectFilter}:${ids.map(String).sort().join(",")}`;
  if (key === preselectKey) return;
  preselectKey = key;
  disposeObject3D(preselects);
  preselects.clear();
  const shown = new Set();
  for (const id of ids) {
    if (S.selectedIds.has(id)) continue;
    drawPreselectEntity(id, shown);
  }
  requestRender();
}

export function clearPreselect() {
  preselectKey = "";
  disposeObject3D(preselects);
  preselects.clear();
  canvas.style.cursor = "";
  if (S.hoverIds && S.hoverIds.size > 0) {
    S.hoverIds = new Set();
    notifySelectionChanged();
  }
  requestRender();
}

export function updatePreselect(event) {
  if (S.tool !== "select" || !event) {
    clearPreselect();
    return;
  }
  indexBrep();
  let ids = [];
  if (S.marqueeOrigin && Math.hypot(event.clientX - S.marqueeOrigin.x, event.clientY - S.marqueeOrigin.y) > 5) {
    ids = windowHits(S.marqueeOrigin, event);
  } else {
    const picked = pickByFilter(event, S.selectFilter);
    if (picked != null) ids = [picked];
  }
  canvas.style.cursor = ids.length ? "pointer" : "";
  const nextHover = new Set(ids);
  if (!setsEqual(nextHover, S.hoverIds)) {
    S.hoverIds = nextHover;
    notifySelectionChanged();
  } else {
    syncHoverPreselect();
  }
}
