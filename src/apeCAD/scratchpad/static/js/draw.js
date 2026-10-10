// Scene-graph builders: clay materials, curves, faces, volumes and vertex dots, tinted by
// selection. Each object carries its entity id in userData for picking.
import * as THREE from "three";
import { S } from "./state.js";
import { ghosts, preselects } from "./viewport.js";

const EDGE_COLOR = 0x111111;
const CURVE_PICK = 0x4a90d9;
export const CURVE_HOVER = 0x6aa8e8;
export const SNAP_COLOR = 0xd55e00;

function isOverlayGroup(group) {
  return group === ghosts || group === preselects;
}

function parseCssHex(value, fallback) {
  const raw = String(value || "").replace("#", "").trim();
  const hex = raw.length === 3
    ? raw.split("").map((ch) => ch + ch).join("")
    : raw;
  const parsed = Number.parseInt(hex, 16);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function clayHex() {
  const value = Math.max(80, Math.min(230, Number(S.prefs.clay) || 176));
  return (value << 16) | (value << 8) | value;
}

function curveIdle() {
  return parseCssHex(S.prefs.curve, EDGE_COLOR);
}

function isPicked(entityId) {
  return entityId != null && S.selectedIds.has(entityId);
}

function selectionTints(entityId) {
  if (entityId == null) return false;
  if (isPicked(entityId)) return true;
  const seen = new Set();
  const stack = [...(S.brepParentsOf.get(entityId) || [])];
  while (stack.length) {
    const parentId = stack.pop();
    if (seen.has(parentId)) continue;
    seen.add(parentId);
    if (isPicked(parentId)) return true;
    stack.push(...(S.brepParentsOf.get(parentId) || []));
  }
  return false;
}

export function curveFor(entityId) {
  if (selectionTints(entityId)) return CURVE_PICK;
  if (entityId != null && S.cutterIds.has(entityId)) return CURVE_HOVER;
  return curveIdle();
}

export function lineOverlay(entityId) {
  return S.selectFilter === "line" || selectionTints(entityId);
}

function clayMat(preview, opacity, entityId = null) {
  return new THREE.MeshLambertMaterial({
    color: preview || selectionTints(entityId) ? CURVE_PICK : clayHex(),
    transparent: preview || opacity < 0.99,
    opacity,
    side: THREE.DoubleSide,
  });
}

function addEdgeOverlay(group, mesh, entityId, preview) {
  if (preview || !S.prefs.showEdges) return;
  const edges = new THREE.LineSegments(
    new THREE.EdgesGeometry(mesh.geometry),
    new THREE.LineBasicMaterial({ color: EDGE_COLOR }),
  );
  edges.position.copy(mesh.position);
  edges.quaternion.copy(mesh.quaternion);
  mark(edges, entityId);
  group.add(edges);
}

export function addCurve(group, pts, color = curveIdle(), entityId = null) {
  if (pts.length < 2) return;
  if (!isOverlayGroup(group) && !S.prefs.showCurves) return;
  const overlay = group !== ghosts && lineOverlay(entityId);
  const line = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(
      pts.map((point) => {
        const p = xyzMm(point);
        return new THREE.Vector3(p.x_mm, p.y_mm, p.z_mm);
      }),
    ),
    new THREE.LineBasicMaterial({ color, depthTest: !overlay }),
  );
  line.renderOrder = overlay ? 12 : 0;
  mark(line, entityId);
  group.add(line);
}

export function mark(object, entityId) {
  if (entityId == null) return;
  object.userData.entityId = entityId;
}

export function addVolume(group, origin, size, color, opacity, entityId = null) {
  const preview = isOverlayGroup(group);
  const mesh = new THREE.Mesh(
    new THREE.BoxGeometry(size[0], size[1], size[2]),
    clayMat(preview, opacity, entityId),
  );
  mesh.position.set(origin[0] + size[0] / 2, origin[1] + size[1] / 2, origin[2] + size[2] / 2);
  mark(mesh, entityId);
  if (!preview && !S.prefs.showFaces) mesh.visible = false;
  group.add(mesh);
  addEdgeOverlay(group, mesh, entityId, preview);
}

export function addCylinder(group, cx, cy, radius, originZ, height, color, opacity, entityId = null) {
  const preview = isOverlayGroup(group);
  const mesh = new THREE.Mesh(
    new THREE.CylinderGeometry(radius, radius, Math.max(Math.abs(height), 1), 48),
    clayMat(preview, opacity, entityId),
  );
  mesh.rotation.x = Math.PI / 2;
  mesh.position.set(cx, cy, originZ + height / 2);
  mark(mesh, entityId);
  if (!preview && !S.prefs.showFaces) mesh.visible = false;
  group.add(mesh);
  addEdgeOverlay(group, mesh, entityId, preview);
}

export function addFaceGraphic(group, pts, { fill = true, opacity = 0.92, entityId = null, color = null } = {}) {
  if (pts.length < 3) return;
  const preview = isOverlayGroup(group);
  const z = (Number.isFinite(pts[0].z_mm) ? pts[0].z_mm : 0) + 20;
  if (fill && (preview || S.prefs.showFaces)) {
    const vertices = [];
    const origin = pts[0];
    for (let i = 1; i < pts.length - 1; i += 1) {
      vertices.push(
        origin.x_mm, origin.y_mm, z,
        pts[i].x_mm, pts[i].y_mm, z,
        pts[i + 1].x_mm, pts[i + 1].y_mm, z,
      );
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(vertices, 3));
    geometry.computeVertexNormals();
    const mesh = new THREE.Mesh(
      geometry,
      clayMat(preview, preview ? opacity : 0.92, entityId),
    );
    if (preview && color != null) mesh.material.color.setHex(color);
    mesh.renderOrder = 2;
    mark(mesh, entityId);
    group.add(mesh);
  }
  if (!preview && !S.prefs.showEdges && !S.prefs.showCurves) return;
  const loop = pts.map((point) => new THREE.Vector3(point.x_mm, point.y_mm, z + 8));
  loop.push(loop[0].clone());
  const outline = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(loop),
    new THREE.LineBasicMaterial({
      color: preview ? (color ?? curveIdle()) : EDGE_COLOR,
    }),
  );
  mark(outline, entityId);
  group.add(outline);
}

export function xyzMm(point) {
  const x = Number(point.x_mm);
  const y = Number(point.y_mm);
  const z = Number(point.z_mm);
  return {
    x_mm: Number.isFinite(x) ? x : 0,
    y_mm: Number.isFinite(y) ? y : 0,
    z_mm: Number.isFinite(z) ? z : 0,
  };
}

export function addPlanarFace(group, pts, entityId) {
  if (pts.length < 3) return;
  const preview = isOverlayGroup(group);
  const world = pts.map(xyzMm);
  if (preview || S.prefs.showFaces) {
    const vertices = [];
    const origin = world[0];
    for (let i = 1; i < world.length - 1; i += 1) {
      vertices.push(
        origin.x_mm, origin.y_mm, origin.z_mm,
        world[i].x_mm, world[i].y_mm, world[i].z_mm,
        world[i + 1].x_mm, world[i + 1].y_mm, world[i + 1].z_mm,
      );
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(vertices, 3));
    geometry.computeVertexNormals();
    const mesh = new THREE.Mesh(geometry, clayMat(preview, preview ? 0.22 : 1, entityId));
    mesh.renderOrder = 1;
    mark(mesh, entityId);
    group.add(mesh);
  }
  if ((preview || S.prefs.showEdges || S.prefs.showCurves) && (preview || S.selectFilter !== "line")) {
    const loop = world.map((point) => new THREE.Vector3(point.x_mm, point.y_mm, point.z_mm));
    loop.push(loop[0].clone());
    const outline = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(loop),
      new THREE.LineBasicMaterial({
        color: preview ? CURVE_PICK : (selectionTints(entityId) ? CURVE_PICK : EDGE_COLOR),
      }),
    );
    mark(outline, entityId);
    group.add(outline);
  }
}

export function addSolidPrism(group, solid, byId) {
  const face = (S.sceneState.faces || []).find((item) => item.entity_id === solid.face_id);
  if (!face) return false;
  const base = face.point_ids.map((id) => byId.get(id)).filter(Boolean);
  const cap = (S.sceneState.faces || []).find((item) => item.entity_id === solid.cap_id);
  const lid = cap
    ? cap.point_ids.map((id) => byId.get(id)).filter(Boolean)
    : [];
  if (base.length < 3 || lid.length !== base.length) return false;
  addPlanarFace(group, base, face.entity_id);
  addPlanarFace(group, lid, cap.entity_id);
  const walls = solid.wall_ids || [];
  for (let i = 0; i < base.length; i += 1) {
    const j = (i + 1) % base.length;
    addPlanarFace(group, [base[i], base[j], lid[j], lid[i]], walls[i] ?? solid.entity_id);
  }
  return true;
}

export function addSolidVolumeFallback(group, solid, byId) {
  const face = (S.sceneState.faces || []).find((item) => item.entity_id === solid.face_id);
  if (!face) return;
  const pts = face.point_ids.map((id) => byId.get(id)).filter(Boolean).map(xyzMm);
  if (!pts.length) return;
  const height = Math.abs(solid.distance_mm) || 1;
  const xs = pts.map((p) => p.x_mm);
  const ys = pts.map((p) => p.y_mm);
  const zs = pts.map((p) => p.z_mm);
  const originZ = solid.distance_mm >= 0 ? Math.min(...zs) : Math.min(...zs) - height;
  addVolume(
    group,
    [Math.min(...xs), Math.min(...ys), originZ],
    [
      Math.max(Math.max(...xs) - Math.min(...xs), 1),
      Math.max(Math.max(...ys) - Math.min(...ys), 1),
      Math.max(height, 1),
    ],
    clayHex(),
    1,
    solid.entity_id,
  );
}

export function addVertexDot(group, point) {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute(
    "position",
    new THREE.Float32BufferAttribute([point.x_mm, point.y_mm, point.z_mm], 3),
  );
  const picked = selectionTints(point.entity_id);
  const material = new THREE.PointsMaterial({
    color: picked ? CURVE_PICK : EDGE_COLOR,
    size: S.selectFilter === "point" || picked ? 11 : 8,
    sizeAttenuation: false,
    depthTest: false,
    depthWrite: false,
  });
  const dot = new THREE.Points(geometry, material);
  dot.renderOrder = 20;
  dot.raycast = () => {};
  mark(dot, point.entity_id);
  group.add(dot);
}
