// Rebuilding the draft group from the scene payload on geometry changes, and updating
// selection/hover in place on selectionSignature changes (ADRs 0035, 0036).
import { S } from "./state.js";
import {
  appReconciler,
  registerReconcileHooks,
  requestRender,
  store,
  syncStoreFromS,
} from "./store.js";
import { t } from "./strings.js";
import { indexBrep } from "./brep.js";
import { invalidateSceneBounds } from "./camera.js";
import { logWarnings, refreshToggles, setHint } from "./cmdline.js";
import {
  LINE_WEIGHT_SELECTED_PX,
  LINE_WEIGHT_WIRE_PX,
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
  makeScreenLineSegments,
  pointsToSegmentPositions,
  rebuildSelectionHalos,
  selectionTints,
  syncDraftSelection,
} from "./draw.js";
import { sampleArc, sampleBezier, sampleCircle, sampleEllipse } from "./geom.js";
import { rebuildGrid } from "./grid.js";
import { clearPreselect, syncHoverPreselect, updatePreselect } from "./preselect.js";
import { barPointIds, drawSection } from "./section.js";
import { INK, parseCssColor } from "./theme.js";
import { disposeObject3D, draft } from "./viewport.js";

let _refreshDocks = () => {};
let _syncSelectionDocks = () => {};

export function registerDockHooks({ refreshDocks, syncSelectionDocks } = {}) {
  if (typeof refreshDocks === "function") _refreshDocks = refreshDocks;
  if (typeof syncSelectionDocks === "function") _syncSelectionDocks = syncSelectionDocks;
}

export function refreshSelection() {
  syncDraftSelection(draft);
  _syncSelectionDocks();
  syncHoverPreselect();
  requestRender();
}

export function rebuild() {
  invalidateSceneBounds();
  disposeObject3D(draft);
  draft.clear();
  S.committedDims = [];
  indexBrep(true);
  const idleCurve = parseCssColor(S.prefs.curve) ?? INK.edge;
  const byId = new Map((S.sceneState.points || []).map((point) => [point.entity_id, point]));
  for (const line of S.sceneState.lines || []) {
    if (S.hiddenIds.has(line.entity_id)) continue;
    const start = byId.get(line.start_id);
    const end = byId.get(line.end_id);
    if (!start || !end) continue;
    if (S.prefs.showCurves) {
      const picked = selectionTints(line.entity_id);
      const overlay = lineOverlay(line.entity_id);
      const flat = pointsToSegmentPositions([start, end], false);
      const drawn = makeScreenLineSegments(flat, {
        color: curveFor(line.entity_id),
        linewidth: picked ? LINE_WEIGHT_SELECTED_PX : LINE_WEIGHT_WIRE_PX,
        depthTest: !overlay,
        renderOrder: overlay ? 12 : 1,
        entityId: line.entity_id,
        role: "curve",
        baseColor: idleCurve,
        baseLinewidth: LINE_WEIGHT_WIRE_PX,
      });
      if (drawn) draft.add(drawn);
    }
  }
  for (const polyline of S.sceneState.polylines || []) {
    if (S.hiddenIds.has(polyline.entity_id)) continue;
    const pts = polyline.point_ids.map((id) => byId.get(id)).filter(Boolean);
    if (pts.length < 2) continue;
    if (!S.prefs.showCurves) continue;
    const picked = selectionTints(polyline.entity_id);
    const overlay = lineOverlay(polyline.entity_id);
    const flat = pointsToSegmentPositions(pts, Boolean(polyline.closed));
    const drawn = makeScreenLineSegments(flat, {
      color: curveFor(polyline.entity_id),
      linewidth: picked ? LINE_WEIGHT_SELECTED_PX : LINE_WEIGHT_WIRE_PX,
      depthTest: !overlay,
      renderOrder: overlay ? 12 : 1,
      entityId: polyline.entity_id,
      role: "curve",
      baseColor: idleCurve,
      baseLinewidth: LINE_WEIGHT_WIRE_PX,
    });
    if (drawn) draft.add(drawn);
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
    const isExtruded = extruded.has(circle.entity_id);
    const showFill = !isExtruded
      || S.selectedIds.has(circle.entity_id)
      || S.selectFilter === "face";
    addFaceGraphic(draft, loop.slice(0, -1), {
      fill: showFill,
      extrudedProfile: isExtruded,
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
    const isExtruded = extruded.has(ellipse.entity_id);
    const showFill = !isExtruded
      || S.selectedIds.has(ellipse.entity_id)
      || S.selectFilter === "face";
    addFaceGraphic(draft, loop.slice(0, -1), {
      fill: showFill,
      extrudedProfile: isExtruded,
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
  rebuildSelectionHalos(draft);
  _refreshDocks();
  rebuildGrid();
  if (S.lastPointer && S.tool === "select") updatePreselect(S.lastPointer);
  else if (S.hoverIds && S.hoverIds.size > 0) syncHoverPreselect();
  else clearPreselect();
  const st = syncStoreFromS(store);
  appReconciler.markBaseline(st);
  requestRender();
}

registerReconcileHooks({
  onGeometry: () => rebuild(),
  onSelection: () => refreshSelection(),
});

export async function refreshFrom(payload) {
  S.sceneState = payload;
  try {
    rebuild();
    logWarnings(payload.warnings);
    refreshToggles();
  } catch (error) {
    console.error(error);
    try {
      indexBrep(true);
      _refreshDocks();
    } catch (_ignored) { /* docks need a valid catalog */ }
    setHint(t("refuse.draw", { reason: error.message }), "refused");
  }
}
