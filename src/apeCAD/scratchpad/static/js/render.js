// Rebuilding the draft group from the scene payload after every op.
import * as THREE from "three";
import { S } from "./state.js";
import { t } from "./strings.js";
import { indexBrep } from "./brep.js";
import { setHint } from "./cmdline.js";
import {
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
} from "./draw.js";
import { sampleArc, sampleBezier, sampleCircle, sampleEllipse } from "./geom.js";
import { rebuildGrid } from "./grid.js";
import { refreshDocks } from "./outliner.js";
import { clearPreselect, updatePreselect } from "./preselect.js";
import { barPointIds, drawSection } from "./section.js";
import { draft } from "./viewport.js";

export function rebuild() {
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
  drawSection(draft);
  // A bar's disc stands for its point; the dot shows only under the point filter.
  const barPoints = S.selectFilter === "point" ? new Set() : barPointIds();
  for (const point of S.sceneState.points || []) {
    if (!S.prefs.showCurves || S.hiddenIds.has(point.entity_id)) continue;
    if (barPoints.has(point.entity_id)) continue;
    addVertexDot(draft, point);
  }
  indexBrep();
  refreshDocks();
  rebuildGrid();
  if (S.lastPointer && S.tool === "select") updatePreselect(S.lastPointer);
  else clearPreselect();
}

export async function refreshFrom(payload) {
  S.sceneState = payload;
  try {
    rebuild();
  } catch (error) {
    console.error(error);
    try {
      indexBrep();
      refreshDocks();
    } catch (_ignored) { /* docks need a valid catalog */ }
    setHint(t("refuse.draw", { reason: error.message }), "refused");
  }
}
