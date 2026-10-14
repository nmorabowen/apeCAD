// Section-mode entities in the 3-D view (ADR 0024): the concrete face, cover ring, leg axis,
// hoops, crossties and bars, flat on their own z. All their colours live in SECTION_STYLE,
// the one table the APE drawing-style slice (ADR 0031) swaps later.
import * as THREE from "three";
import { S } from "./state.js";
import { pointById } from "./brep.js";
import { mark, selectionTints } from "./draw.js";
import { sampleCircle } from "./geom.js";
import { formatMm } from "./prefs.js";
import { dashSegments, roundedRing } from "./section-geom.js";
import { INK } from "./theme.js";

// Neutral ink until ADR 0031 is approved. Dash patterns are in mm on the section plane.
export const SECTION_STYLE = {
  concrete: { fill: 0xc8ccd1, opacity: 0.6, edge: 0x1f2933 },
  cover: { color: 0x7b8794, dash: [60, 40] },
  leg: { color: 0x7b8794, dash: [160, 40, 20, 40] },
  hoop: { color: 0x1f2933 },
  crosstie: { color: 0x1f2933 },
  bar: { color: 0x1f2933 },
};

export const SECTION_KINDS = ["ConcreteFace", "Bar", "Hoop", "Crosstie", "WallLeg", "CoverGuide"];

const SOURCES = {
  ConcreteFace: "concrete_faces",
  Bar: "bars",
  Hoop: "hoops",
  Crosstie: "crossties",
  WallLeg: "wall_legs",
  CoverGuide: "cover_guides",
};

// [kind, payload item] for every section entity in the scene.
export function sectionItems() {
  const out = [];
  for (const kind of SECTION_KINDS) {
    for (const item of S.sceneState[SOURCES[kind]] || []) out.push([kind, item]);
  }
  return out;
}

export function barPointIds() {
  return new Set((S.sceneState.bars || []).map((bar) => bar.point_id));
}

function barById(id) {
  return (S.sceneState.bars || []).find((bar) => bar.entity_id === id) || null;
}

function barCentre(id) {
  const bar = barById(id);
  return bar ? pointById(bar.point_id) : null;
}

function faceRing(faceId) {
  const face = (S.sceneState.concrete_faces || []).find((item) => item.entity_id === faceId);
  return face ? face.point_ids.map(pointById).filter(Boolean) : [];
}

function hoopRing(hoop) {
  const bars = hoop.bar_ids.map(barById).filter(Boolean);
  const centres = bars.map((bar) => pointById(bar.point_id));
  if (centres.length < 2 || centres.some((c) => !c)) return [];
  return roundedRing(centres, bars.map((bar) => bar.diameter_mm / 2 + hoop.diameter_mm / 2));
}

function coverRing(guide) {
  const ring = guide.cover_ring_mm;
  if (!ring) return [];
  const z = (faceRing(guide.face_id)[0] || {}).z_mm || 0;
  return ring.map(([x, y]) => ({ x_mm: x, y_mm: y, z_mm: z }));
}

// World outline of one section entity: {pts, closed}, or null. Picking, the marquee and
// the hover highlight all use it.
export function sectionShape(kind, item) {
  if (kind === "ConcreteFace") {
    const pts = item.point_ids.map(pointById).filter(Boolean);
    return pts.length >= 3 ? { pts, closed: true } : null;
  }
  if (kind === "Bar") {
    const centre = pointById(item.point_id);
    return centre ? { pts: sampleCircle(centre, item.diameter_mm / 2, 24).slice(0, -1), closed: true } : null;
  }
  if (kind === "Hoop") {
    const pts = hoopRing(item);
    return pts.length ? { pts, closed: true } : null;
  }
  if (kind === "Crosstie") {
    const pts = [barCentre(item.bar_a_id), barCentre(item.bar_b_id)];
    return pts.every(Boolean) ? { pts, closed: false } : null;
  }
  if (kind === "WallLeg") {
    const pts = [pointById(item.start_id), pointById(item.end_id)];
    return pts.every(Boolean) ? { pts, closed: false } : null;
  }
  if (kind === "CoverGuide") {
    const pts = coverRing(item);
    return pts.length >= 3 ? { pts, closed: true } : null;
  }
  return null;
}

const vec = (p, lift = 0) => new THREE.Vector3(p.x_mm, p.y_mm, (p.z_mm || 0) + lift);

function lineMaterial(color, entityId) {
  return new THREE.LineBasicMaterial({
    color: selectionTints(entityId) ? INK.pick : color,
    depthTest: false,
  });
}

function addPolyline(group, pts, closed, color, entityId) {
  const loop = pts.map((p) => vec(p));
  if (closed) loop.push(loop[0].clone());
  const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(loop), lineMaterial(color, entityId));
  line.renderOrder = 6;
  mark(line, entityId);
  group.add(line);
}

function addDashed(group, pts, closed, style, entityId) {
  const flat = [];
  for (const [a, b] of dashSegments(pts, closed, style.dash)) flat.push(vec(a), vec(b));
  if (!flat.length) return;
  const line = new THREE.LineSegments(
    new THREE.BufferGeometry().setFromPoints(flat),
    lineMaterial(style.color, entityId),
  );
  line.renderOrder = 5;
  mark(line, entityId);
  group.add(line);
}

function addConcrete(group, face) {
  const pts = face.point_ids.map(pointById).filter(Boolean);
  if (pts.length < 3) return;
  const style = SECTION_STYLE.concrete;
  const tinted = selectionTints(face.entity_id);
  if (S.prefs.showFaces) {
    const shape = new THREE.Shape(pts.map((p) => new THREE.Vector2(p.x_mm, p.y_mm)));
    const mesh = new THREE.Mesh(new THREE.ShapeGeometry(shape), new THREE.MeshBasicMaterial({
      color: tinted ? INK.pick : style.fill,
      transparent: true,
      opacity: tinted ? 0.35 : style.opacity,
      side: THREE.DoubleSide,
      depthWrite: false,
    }));
    mesh.position.z = pts[0].z_mm || 0;
    mesh.renderOrder = 1;
    mark(mesh, face.entity_id);
    group.add(mesh);
  }
  addPolyline(group, pts, true, style.edge, face.entity_id);
}

function addBar(group, bar) {
  const centre = pointById(bar.point_id);
  if (!centre) return;
  const disc = new THREE.Mesh(
    new THREE.CircleGeometry(bar.diameter_mm / 2, 24),
    new THREE.MeshBasicMaterial({
      color: selectionTints(bar.entity_id) ? INK.pick : SECTION_STYLE.bar.color,
      side: THREE.DoubleSide,
      depthTest: false,
    }),
  );
  disc.position.copy(vec(centre));
  disc.renderOrder = 7;
  mark(disc, bar.entity_id);
  group.add(disc);
}

// Draw every visible section entity into `group`, back to front.
export function drawSection(group) {
  for (const [kind, item] of sectionItems()) {
    if (S.hiddenIds.has(item.entity_id)) continue;
    if (kind === "ConcreteFace") addConcrete(group, item);
    else if (kind === "Bar") addBar(group, item);
    else if (kind === "CoverGuide" || kind === "WallLeg") {
      const shape = sectionShape(kind, item);
      const style = kind === "CoverGuide" ? SECTION_STYLE.cover : SECTION_STYLE.leg;
      if (shape) addDashed(group, shape.pts, shape.closed, style, item.entity_id);
    } else {
      const shape = sectionShape(kind, item);
      const style = kind === "Hoop" ? SECTION_STYLE.hoop : SECTION_STYLE.crosstie;
      if (shape) addPolyline(group, shape.pts, shape.closed, style.color, item.entity_id);
    }
  }
}

// Properties-dock rows for a section entity.
export function sectionFields(kind, item) {
  if (kind === "ConcreteFace") {
    return [["Material", item.material], ["Vertices", String(item.point_ids.length)]];
  }
  if (kind === "Bar") {
    const centre = pointById(item.point_id);
    const at = centre ? [["X", formatMm(centre.x_mm)], ["Y", formatMm(centre.y_mm)]] : [];
    return [["Bar", item.designation], ["Diameter", formatMm(item.diameter_mm)], ...at];
  }
  if (kind === "Hoop" || kind === "Crosstie") {
    const rows = [["Tie", item.designation], ["Spacing", formatMm(item.spacing_mm)], ["Hooks", item.hooks]];
    if (kind === "Hoop") rows.push(["Bars", String(item.bar_ids.length)]);
    return rows;
  }
  if (kind === "WallLeg") {
    const steel = item.horizontal;
    const web = steel ? `${steel.curtains} × ${steel.designation} @ ${formatMm(steel.spacing_mm)}` : "—";
    return [["Thickness", formatMm(item.thickness_mm)], ["Horizontal", web]];
  }
  if (kind === "CoverGuide") {
    return [
      ["Cover", formatMm(item.cover_mm)],
      ["Tie", formatMm(item.tie_diameter_mm)],
      ["Bar", formatMm(item.bar_diameter_mm)],
    ];
  }
  return [];
}

// Is a ray's crossing of the entity's plane inside the plan polygon `pts` (even-odd)?
// Concrete outlines may be concave (L, C walls), so no fan triangulation here.
export function rayInsidePlan(ray, pts) {
  if (pts.length < 3 || Math.abs(ray.direction.z) < 1e-9) return null;
  const z = pts[0].z_mm || 0;
  const t = (z - ray.origin.z) / ray.direction.z;
  if (t < 0) return null;
  const x = ray.origin.x + ray.direction.x * t;
  const y = ray.origin.y + ray.direction.y * t;
  let inside = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i, i += 1) {
    const a = pts[i];
    const b = pts[j];
    if ((a.y_mm > y) !== (b.y_mm > y)
      && x < ((b.x_mm - a.x_mm) * (y - a.y_mm)) / (b.y_mm - a.y_mm) + a.x_mm) inside = !inside;
  }
  return inside ? t : null;
}
