// Scene-graph builders: clay materials, screen-space LineSegments2 curves/edges, ear-clipped
// faces, volumes, vertex dots, and depth-exempt SelectionHalos (ADRs 0035, 0036).
import * as THREE from "three";
import { LineMaterial } from "three/addons/lines/LineMaterial.js";
import { LineSegments2 } from "three/addons/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/addons/lines/LineSegmentsGeometry.js";
import { triangulatePlanar3D } from "./geom.js";
import { S } from "./state.js";
import { INK, parseCssColor } from "./theme.js";
import { currentLineResolution, disposeObject3D, ghosts, preselects, selectionHalos } from "./viewport.js";

export const LINE_WEIGHT_WIRE_PX = 1.5;
export const LINE_WEIGHT_SECTION_PX = 2.25;
export const LINE_WEIGHT_REBAR_PX = 3.0;
export const LINE_WEIGHT_SELECTED_PX = 3.0;
export const HALO_CASING_PX = 4.5;
export const HALO_CORE_PX = 2.5;

function isOverlayGroup(group) {
  return group === ghosts || group === preselects || group === selectionHalos;
}

export function clayHex() {
  const value = Math.max(80, Math.min(230, Number(S.prefs.clay) || 176));
  return (value << 16) | (value << 8) | value;
}

function curveIdle() {
  return parseCssColor(S.prefs.curve) ?? INK.edge;
}

function isPicked(entityId) {
  return entityId != null && S.selectedIds.has(entityId);
}

export function selectionTints(entityId) {
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
  if (selectionTints(entityId)) return INK.pick;
  if (entityId != null && S.cutterIds.has(entityId)) return INK.hover;
  return curveIdle();
}

export function lineOverlay(entityId) {
  return S.selectFilter === "line" || selectionTints(entityId);
}

export function xyzMm(point) {
  const x = Number(point.x_mm ?? point.x);
  const y = Number(point.y_mm ?? point.y);
  const z = Number(point.z_mm ?? point.z);
  return {
    x_mm: Number.isFinite(x) ? x : 0,
    y_mm: Number.isFinite(y) ? y : 0,
    z_mm: Number.isFinite(z) ? z : 0,
  };
}

export function pointsToSegmentPositions(pts, closed = false, zOverride = null) {
  const out = [];
  if (!pts || pts.length < 2) return out;
  const coords = pts.map((pt) => {
    const p = xyzMm(pt);
    return [p.x_mm, p.y_mm, zOverride != null ? zOverride : p.z_mm];
  });
  for (let i = 0; i < coords.length - 1; i += 1) {
    const a = coords[i];
    const b = coords[i + 1];
    out.push(a[0], a[1], a[2], b[0], b[1], b[2]);
  }
  if (closed && coords.length >= 3) {
    const last = coords[coords.length - 1];
    const first = coords[0];
    if (
      Math.hypot(last[0] - first[0], last[1] - first[1], last[2] - first[2]) > 1e-6
    ) {
      out.push(last[0], last[1], last[2], first[0], first[1], first[2]);
    }
  }
  return out;
}

export function makeScreenLineSegments(
  flatPositions,
  {
    color = INK.edge,
    linewidth = LINE_WEIGHT_WIRE_PX,
    depthTest = true,
    renderOrder = 0,
    entityId = null,
    role = "wire",
    baseColor = color,
    baseLinewidth = linewidth,
  } = {},
) {
  if (!flatPositions || flatPositions.length < 6) return null;
  const geom = new LineSegmentsGeometry();
  geom.setPositions(flatPositions);
  const mat = new LineMaterial({
    color,
    linewidth,
    worldUnits: false,
    resolution: currentLineResolution(),
    depthTest,
    depthWrite: depthTest,
    transparent: !depthTest,
  });
  const segs = new LineSegments2(geom, mat);
  segs.renderOrder = renderOrder;
  mark(segs, entityId, { role, baseColor, baseLinewidth, flatPositions });
  return segs;
}

function clayMat(preview, opacity, entityId = null) {
  return new THREE.MeshLambertMaterial({
    color: preview || selectionTints(entityId) ? INK.pick : clayHex(),
    transparent: preview || opacity < 0.99,
    opacity,
    side: THREE.DoubleSide,
  });
}

function addEdgeOverlay(group, mesh, entityId, preview) {
  if (preview || !S.prefs.showEdges) return;
  const edgeGeom = new THREE.EdgesGeometry(mesh.geometry);
  const posAttr = edgeGeom.getAttribute("position");
  const flat = posAttr ? Array.from(posAttr.array) : [];
  edgeGeom.dispose();
  if (flat.length < 6) return;
  const picked = selectionTints(entityId);
  const segs = makeScreenLineSegments(flat, {
    color: picked ? INK.pick : INK.edge,
    linewidth: picked ? LINE_WEIGHT_SELECTED_PX : LINE_WEIGHT_WIRE_PX,
    depthTest: true,
    renderOrder: 2,
    entityId,
    role: "edge",
    baseColor: INK.edge,
    baseLinewidth: LINE_WEIGHT_WIRE_PX,
  });
  if (!segs) return;
  segs.position.copy(mesh.position);
  segs.quaternion.copy(mesh.quaternion);
  group.add(segs);
}

export function addCurve(group, pts, color = curveIdle(), entityId = null) {
  if (pts.length < 2) return;
  if (!isOverlayGroup(group) && !S.prefs.showCurves) return;
  const preview = isOverlayGroup(group);
  const picked = !preview && selectionTints(entityId);
  const overlay = group !== ghosts && lineOverlay(entityId);
  const flat = pointsToSegmentPositions(pts, false);
  const segs = makeScreenLineSegments(flat, {
    color,
    linewidth: preview || picked ? LINE_WEIGHT_SELECTED_PX : LINE_WEIGHT_WIRE_PX,
    depthTest: !overlay && !preview,
    renderOrder: overlay || preview ? 12 : 1,
    entityId,
    role: "curve",
    baseColor: curveIdle(),
    baseLinewidth: LINE_WEIGHT_WIRE_PX,
  });
  if (segs) group.add(segs);
}

export function mark(object, entityId, meta = null) {
  if (meta && typeof meta === "object") {
    Object.assign(object.userData, meta);
  }
  if (entityId != null) {
    object.userData.entityId = entityId;
  }
}

export function addVolume(group, origin, size, color, opacity, entityId = null) {
  const preview = isOverlayGroup(group);
  const mesh = new THREE.Mesh(
    new THREE.BoxGeometry(size[0], size[1], size[2]),
    clayMat(preview, opacity, entityId),
  );
  mesh.position.set(origin[0] + size[0] / 2, origin[1] + size[1] / 2, origin[2] + size[2] / 2);
  mark(mesh, entityId, { role: "clay", baseOpacity: opacity });
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
  mark(mesh, entityId, { role: "clay", baseOpacity: opacity });
  if (!preview && !S.prefs.showFaces) mesh.visible = false;
  group.add(mesh);
  addEdgeOverlay(group, mesh, entityId, preview);
}

export function addFaceGraphic(
  group,
  pts,
  { fill = true, extrudedProfile = false, opacity = 0.92, entityId = null, color = null } = {},
) {
  if (pts.length < 3) return;
  const preview = isOverlayGroup(group);
  const z = (Number.isFinite(pts[0].z_mm) ? pts[0].z_mm : 0) + 20;
  if ((fill || extrudedProfile) && (preview || S.prefs.showFaces)) {
    const tris = triangulatePlanar3D(pts);
    const vertices = [];
    for (const [i0, i1, i2] of tris) {
      vertices.push(
        pts[i0].x_mm, pts[i0].y_mm, z,
        pts[i1].x_mm, pts[i1].y_mm, z,
        pts[i2].x_mm, pts[i2].y_mm, z,
      );
    }
    if (vertices.length >= 9) {
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.Float32BufferAttribute(vertices, 3));
      geometry.computeVertexNormals();
      const mesh = new THREE.Mesh(
        geometry,
        clayMat(preview, preview ? opacity : 0.92, entityId),
      );
      if (preview && color != null) mesh.material.color.setHex(color);
      mesh.renderOrder = 2;
      mesh.visible = Boolean(fill);
      mark(mesh, entityId, { role: "clay", baseOpacity: 0.92, extrudedProfile });
      group.add(mesh);
    }
  }
  if (!preview && !S.prefs.showEdges && !S.prefs.showCurves) return;
  const flat = pointsToSegmentPositions(pts, true, z + 8);
  const picked = !preview && selectionTints(entityId);
  const outline = makeScreenLineSegments(flat, {
    color: preview ? (color ?? curveIdle()) : (picked ? INK.pick : INK.edge),
    linewidth: preview || picked ? LINE_WEIGHT_SELECTED_PX : LINE_WEIGHT_WIRE_PX,
    depthTest: !preview,
    renderOrder: preview ? 12 : 2,
    entityId,
    role: "edge",
    baseColor: INK.edge,
    baseLinewidth: LINE_WEIGHT_WIRE_PX,
  });
  if (outline) group.add(outline);
}

export function addPlanarFace(group, pts, entityId) {
  if (pts.length < 3) return;
  const preview = isOverlayGroup(group);
  const world = pts.map(xyzMm);
  if (preview || S.prefs.showFaces) {
    const tris = triangulatePlanar3D(world);
    const vertices = [];
    for (const [i0, i1, i2] of tris) {
      vertices.push(
        world[i0].x_mm, world[i0].y_mm, world[i0].z_mm,
        world[i1].x_mm, world[i1].y_mm, world[i1].z_mm,
        world[i2].x_mm, world[i2].y_mm, world[i2].z_mm,
      );
    }
    if (vertices.length >= 9) {
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.Float32BufferAttribute(vertices, 3));
      geometry.computeVertexNormals();
      const mesh = new THREE.Mesh(geometry, clayMat(preview, preview ? 0.22 : 1, entityId));
      mesh.renderOrder = 1;
      mark(mesh, entityId, { role: "clay", baseOpacity: 1 });
      group.add(mesh);
    }
  }
  if ((preview || S.prefs.showEdges || S.prefs.showCurves) && (preview || S.selectFilter !== "line")) {
    const flat = pointsToSegmentPositions(world, true);
    const picked = !preview && selectionTints(entityId);
    const outline = makeScreenLineSegments(flat, {
      color: preview ? INK.pick : (picked ? INK.pick : INK.edge),
      linewidth: preview || picked ? LINE_WEIGHT_SELECTED_PX : LINE_WEIGHT_WIRE_PX,
      depthTest: !preview,
      renderOrder: preview ? 12 : 2,
      entityId,
      role: "edge",
      baseColor: INK.edge,
      baseLinewidth: LINE_WEIGHT_WIRE_PX,
    });
    if (outline) group.add(outline);
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
    color: picked ? INK.pick : INK.edge,
    size: S.selectFilter === "point" || picked ? 11 : 8,
    sizeAttenuation: false,
    depthTest: false,
    depthWrite: false,
  });
  const dot = new THREE.Points(geometry, material);
  dot.renderOrder = 20;
  dot.raycast = () => {};
  mark(dot, point.entity_id, { role: "vertex" });
  group.add(dot);
}

// Depth-exempt SelectionHalo (ADR 0036) + in-place selection material update (ADR 0035).
export function rebuildSelectionHalos(draftGroup) {
  disposeObject3D(selectionHalos);
  selectionHalos.clear();
  if (!draftGroup || S.selectedIds.size === 0) return;
  for (const node of draftGroup.children) {
    const ud = node.userData || {};
    if (ud.entityId == null || !selectionTints(ud.entityId)) continue;
    if (ud.flatPositions && ud.flatPositions.length >= 6) {
      const casing = makeScreenLineSegments(ud.flatPositions, {
        color: INK.canvas,
        linewidth: HALO_CASING_PX,
        depthTest: false,
        renderOrder: 30,
      });
      const core = makeScreenLineSegments(ud.flatPositions, {
        color: INK.pick,
        linewidth: HALO_CORE_PX,
        depthTest: false,
        renderOrder: 31,
      });
      for (const h of [casing, core]) {
        if (!h) continue;
        h.position.copy(node.position);
        h.quaternion.copy(node.quaternion);
        h.raycast = () => {};
        selectionHalos.add(h);
      }
    }
  }
}

export function syncDraftSelection(draftGroup) {
  if (!draftGroup) return;
  for (const node of draftGroup.children) {
    const ud = node.userData || {};
    const id = ud.entityId;
    if (id == null || !node.material) continue;
    const picked = selectionTints(id);
    if (ud.role === "clay") {
      node.material.color.setHex(picked ? INK.pick : clayHex());
      if (ud.extrudedProfile) {
        node.visible = Boolean(S.prefs.showFaces) && (S.selectedIds.has(id) || S.selectFilter === "face");
      }
    } else if (ud.role === "concrete") {
      node.material.color.setHex(picked ? INK.pick : (ud.baseColor ?? INK.concreteFill));
      node.material.opacity = picked ? 0.35 : (ud.baseOpacity ?? 0.6);
    } else if (ud.role === "bar") {
      node.material.color.setHex(picked ? INK.pick : (ud.baseColor ?? INK.rebar));
    } else if (ud.role === "vertex") {
      node.material.color.setHex(picked ? INK.pick : INK.edge);
      node.material.size = S.selectFilter === "point" || picked ? 11 : 8;
    } else if (ud.role === "curve") {
      node.material.color.setHex(curveFor(id));
      node.material.linewidth = picked ? LINE_WEIGHT_SELECTED_PX : (ud.baseLinewidth ?? LINE_WEIGHT_WIRE_PX);
      const overlay = lineOverlay(id);
      node.material.depthTest = !overlay;
      node.renderOrder = overlay ? 12 : 1;
    } else if (ud.role === "edge" || ud.role === "section-line") {
      node.material.color.setHex(picked ? INK.pick : (ud.baseColor ?? INK.edge));
      node.material.linewidth = picked ? LINE_WEIGHT_SELECTED_PX : (ud.baseLinewidth ?? LINE_WEIGHT_WIRE_PX);
    }
  }
  rebuildSelectionHalos(draftGroup);
}
