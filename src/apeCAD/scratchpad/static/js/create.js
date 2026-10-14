// Drawing tools: the ops that create points, lines, polylines, faces, circles, ellipses,
// polygons, arcs, Beziers, boxes and extrusions. One gesture posts one op, its vertices as
// point ids or coordinates, so one undo removes the whole shape (ADR 0030).
import { S } from "./state.js";
import { t } from "./strings.js";
import { api } from "./api.js";
import { findRecord } from "./brep.js";
import { clearTyped, labelValue, refreshToggles, refuse, setHint, sidesValue } from "./cmdline.js";
import { dist3, rectCorners, regularPolygon, vertexRef } from "./geom.js";
import { polylineCloses, updateGhost } from "./ghosts.js";
import { refreshFrom } from "./render.js";
import { hitHeight } from "./snap.js";
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

function rectRing(a, b) {
  const corners = rectCorners(a, b);
  if (!corners) throw new Error(t("reason.rectangle"));
  return corners.map(vertexRef);
}

// Each click adds a vertex to the pending chain; Esc, Enter or a tool switch posts the whole
// chain as one AddLineChain (finishLineChain).
export async function finishLine(end) {
  if (dist3(S.pending.a, end) < 1) {
    setHint(t("hint.line.different"));
    return;
  }
  const pts = (S.pending.pts || [S.pending.a]).concat([end]);
  clearTyped();
  ghosts.clear();
  S.ghostDims = [];
  S.pending = { kind: "line", a: end, pts, chain: true };
  refreshToggles();
  setHint(t("hint.line.next"));
  if (S.lastPointer) updateGhost(S.lastPointer);
}

export function pendingChain() {
  return S.pending && S.pending.kind === "line" && S.pending.pts && S.pending.pts.length >= 2;
}

export async function finishLineChain() {
  const pts = S.pending.pts;
  S.pending = null;
  ghosts.clear();
  S.ghostDims = [];
  await refreshFrom(await api("/api/op", "POST", {
    op: "AddLineChain", point_ids: pts.map(vertexRef), label: labelValue(),
  }));
  clearTyped();
  refreshToggles();
}

function polylineHint() {
  if (!S.pending || S.pending.pts.length < 2) {
    return t("hint.polyline.next");
  }
  if (S.pending.pts.length < 3) {
    return t("hint.polyline.nextOrFinish");
  }
  return t("hint.polyline.nextFinishClose");
}

export async function appendPolylineVertex(end) {
  if (polylineCloses(end)) {
    await finishPolyline(true);
    return;
  }
  const last = S.pending.pts[S.pending.pts.length - 1];
  if (dist3(last, end) < 1) {
    setHint(t("hint.polyline.different"));
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
    if (closed) refuse(t("reason.closedPolyline"));
    else setHint(t("hint.polyline.twoPoints"));
    return;
  }
  await refreshFrom(await api("/api/op", "POST", {
    op: "AddPolyline",
    point_ids: pts.map(vertexRef),
    closed: Boolean(closed),
    label: labelValue(),
  }));
  S.pending = null;
  clearTyped();
  ghosts.clear();
  S.ghostDims = [];
  refreshToggles();
  setHint(t(closed ? "done.polylineClosed" : "done.polyline"));
}

export async function finishFace(end) {
  await refreshFrom(await api("/api/op", "POST", {
    op: "AddFace", point_ids: rectRing(S.pending.a, end), label: labelValue(),
  }));
  S.pending = null;
  clearTyped();
  ghosts.clear();
  S.ghostDims = [];
  refreshToggles();
  setHint(t("done.rect"));
}

export async function finishBox(event) {
  const height = hitHeight(event, S.pending.a, S.pending.b);
  const distance = height === 0 ? 100 : height;
  await refreshFrom(await api("/api/op", "POST", {
    op: "Extrude",
    face_id: null,
    ring: rectRing(S.pending.a, S.pending.b),
    distance_mm: distance,
    label: labelValue(),
  }));
  S.pending = null;
  clearTyped();
  ghosts.clear();
  S.ghostDims = [];
  refreshToggles();
  setHint(t("done.box"));
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
  setHint(t("done.solid"));
}

export async function finishCircle(rim) {
  const radius = dist3(S.pending.a, rim);
  if (radius < 1) throw new Error(t("reason.radius"));
  await refreshFrom(await api("/api/op", "POST", {
    op: "AddCircle", center_id: vertexRef(S.pending.a), radius_mm: radius, label: labelValue(),
  }));
  S.pending = null;
  clearTyped();
  ghosts.clear();
  S.ghostDims = [];
  refreshToggles();
  setHint(t("done.circle"));
}

export async function finishEllipse(rim) {
  const rx = Math.abs(rim.x_mm - S.pending.a.x_mm);
  const ry = Math.abs(rim.y_mm - S.pending.a.y_mm);
  if (rx < 1 || ry < 1) throw new Error(t("reason.ellipse"));
  await refreshFrom(await api("/api/op", "POST", {
    op: "AddEllipse",
    center_id: vertexRef(S.pending.a),
    radius_x_mm: rx,
    radius_y_mm: ry,
    label: labelValue(),
  }));
  S.pending = null;
  clearTyped();
  ghosts.clear();
  S.ghostDims = [];
  refreshToggles();
  setHint(t("done.ellipse"));
}

export async function finishPolygon(rim) {
  const pts = regularPolygon(S.pending.a, rim, sidesValue());
  await refreshFrom(await api("/api/op", "POST", {
    op: "AddFace", point_ids: pts.map(vertexRef), label: labelValue(),
  }));
  S.pending = null;
  clearTyped();
  ghosts.clear();
  S.ghostDims = [];
  refreshToggles();
  setHint(t("done.polygon"));
}

export async function finishArc(end) {
  const refs = S.pending.pts.concat([end]).map(vertexRef);
  await refreshFrom(await api("/api/op", "POST", {
    op: "AddArc",
    start_id: refs[0],
    mid_id: refs[1],
    end_id: refs[2],
    label: labelValue(),
  }));
  S.pending = null;
  clearTyped();
  ghosts.clear();
  S.ghostDims = [];
  refreshToggles();
  setHint(t("done.arc"));
}

export async function finishBezier(end) {
  await refreshFrom(await api("/api/op", "POST", {
    op: "AddBezier", point_ids: S.pending.pts.concat([end]).map(vertexRef), label: labelValue(),
  }));
  S.pending = null;
  clearTyped();
  ghosts.clear();
  S.ghostDims = [];
  refreshToggles();
  setHint(t("done.bezier"));
}
