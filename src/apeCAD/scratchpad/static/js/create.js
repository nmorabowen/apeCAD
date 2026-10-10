// Drawing tools: the ops that create points, lines, polylines, faces, circles, ellipses,
// polygons, arcs, Beziers, boxes and extrusions.
import { S } from "./state.js";
import { api, createdId } from "./api.js";
import { findRecord } from "./brep.js";
import { clearTyped, labelValue, refreshToggles, setHint, sidesValue } from "./cmdline.js";
import { dist3, regularPolygon } from "./geom.js";
import { polylineCloses, updateGhost } from "./ghosts.js";
import { refreshFrom } from "./render.js";
import { hitHeight, nearestPoint } from "./snap.js";
import { ghosts } from "./viewport.js";

export function profileExtents(id) {
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

export async function finishLine(end) {
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

export async function appendPolylineVertex(end) {
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

export async function finishPolyline(closed) {
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

export async function finishFace(end) {
  await addFaceFromCorners(S.pending.a, end, labelValue());
  S.pending = null;
  clearTyped();
  ghosts.clear();
  S.ghostDims = [];
  refreshToggles();
  setHint("Rect placed.");
}

export async function finishBox(event) {
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

export async function finishExtrude(event) {
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

export async function finishCircle(rim) {
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

export async function finishEllipse(rim) {
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

export async function finishPolygon(rim) {
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

export async function finishArc(end) {
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

export async function finishBezier(end) {
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
