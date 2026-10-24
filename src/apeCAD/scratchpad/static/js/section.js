// Section-mode entities in the 3-D view (ADR 0024): the concrete face, cover ring, leg axis,
// hoops, crossties and bars, flat on their own z. All their colours live in SECTION_STYLE,
// the one table the APE drawing-style slice (ADR 0031, stage D3) swaps later.
import * as THREE from "three";
import { S } from "./state.js";
import { pointById } from "./brep.js";
import {
  LINE_WEIGHT_REBAR_PX,
  LINE_WEIGHT_SECTION_PX,
  LINE_WEIGHT_SELECTED_PX,
  makeScreenLineSegments,
  mark,
  pointsToSegmentPositions,
  selectionTints,
} from "./draw.js";
import { sampleCircle, triangulatePlanar3D } from "./geom.js";
import { formatMm } from "./prefs.js";
import { dashSegments, roundedRing } from "./section-geom.js";
import { INK } from "./theme.js";

// Colours come from the active canvas (css/app.css --fill-concrete, --ink-concrete,
// --ink-section-guide, --ink-rebar via INK), so the section reads on paper and on carbon.
// Light canvases use the APE drawing ink of render/style.py (ADR 0031 §3): Grey210 cut,
// black edge, Dark Grey guides, rebar in (0, 0, 119); carbon lifts them. Dash patterns are
// in mm on the section plane.
export const SECTION_STYLE = {
  concrete: { get fill() { return INK.concreteFill; }, opacity: 0.6, get edge() { return INK.concreteEdge; } },
  cover: { get color() { return INK.sectionGuide; }, dash: [60, 40] },
  leg: { get color() { return INK.sectionGuide; }, dash: [160, 40, 20, 40] },
  hoop: { get color() { return INK.rebar; } },
  crosstie: { get color() { return INK.rebar; } },
  bar: { get color() { return INK.rebar; } },
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

// Lines and bars sit in three.js's transparent pass (opacity 1), so renderOrder draws them
// over the translucent concrete fill; screen-space LineSegments2 weights differentiate
// concrete/guides (2.25 px) from hoops/crossties (3.0 px) (ADR 0036).
function addPolyline(group, pts, closed, color, entityId, baseWidth = LINE_WEIGHT_SECTION_PX) {
  const flat = pointsToSegmentPositions(pts, closed);
  const picked = selectionTints(entityId);
  const line = makeScreenLineSegments(flat, {
    color: picked ? INK.pick : color,
    linewidth: picked ? LINE_WEIGHT_SELECTED_PX : baseWidth,
    depthTest: false,
    renderOrder: 6,
    entityId,
    role: "section-line",
    baseColor: color,
    baseLinewidth: baseWidth,
  });
  if (line) group.add(line);
}

function addDashed(group, pts, closed, style, entityId) {
  const flat = [];
  for (const [a, b] of dashSegments(pts, closed, style.dash)) {
    flat.push(a.x_mm, a.y_mm, a.z_mm || 0, b.x_mm, b.y_mm, b.z_mm || 0);
  }
  if (flat.length < 6) return;
  const picked = selectionTints(entityId);
  const line = makeScreenLineSegments(flat, {
    color: picked ? INK.pick : style.color,
    linewidth: picked ? LINE_WEIGHT_SELECTED_PX : LINE_WEIGHT_SECTION_PX,
    depthTest: false,
    renderOrder: 5,
    entityId,
    role: "section-line",
    baseColor: style.color,
    baseLinewidth: LINE_WEIGHT_SECTION_PX,
  });
  if (line) group.add(line);
}

function addConcrete(group, face) {
  const pts = face.point_ids.map(pointById).filter(Boolean);
  if (pts.length < 3) return;
  const style = SECTION_STYLE.concrete;
  const tinted = selectionTints(face.entity_id);
  if (S.prefs.showFaces) {
    const tris = triangulatePlanar3D(pts);
    const vertices = [];
    const z = pts[0].z_mm || 0;
    for (const [i0, i1, i2] of tris) {
      vertices.push(
        pts[i0].x_mm, pts[i0].y_mm, z,
        pts[i1].x_mm, pts[i1].y_mm, z,
        pts[i2].x_mm, pts[i2].y_mm, z,
      );
    }
    if (vertices.length >= 9) {
      const geom = new THREE.BufferGeometry();
      geom.setAttribute("position", new THREE.Float32BufferAttribute(vertices, 3));
      const mesh = new THREE.Mesh(geom, new THREE.MeshBasicMaterial({
        color: tinted ? INK.pick : style.fill,
        transparent: true,
        opacity: tinted ? 0.35 : style.opacity,
        side: THREE.DoubleSide,
        depthWrite: false,
      }));
      mesh.renderOrder = 1;
      mark(mesh, face.entity_id, {
        role: "concrete",
        baseColor: style.fill,
        baseOpacity: style.opacity,
      });
      group.add(mesh);
    }
  }
  addPolyline(group, pts, true, style.edge, face.entity_id, LINE_WEIGHT_SECTION_PX);
}

function addBar(group, bar) {
  const centre = pointById(bar.point_id);
  if (!centre) return;
  const radius = bar.diameter_mm / 2;
  const disc = new THREE.Mesh(
    new THREE.CircleGeometry(radius, 24),
    new THREE.MeshBasicMaterial({
      color: selectionTints(bar.entity_id) ? INK.pick : SECTION_STYLE.bar.color,
      side: THREE.DoubleSide,
      depthTest: false,
      transparent: true,
    }),
  );
  disc.position.copy(vec(centre));
  disc.renderOrder = 7;
  const flatPositions = pointsToSegmentPositions(
    sampleCircle({ x_mm: 0, y_mm: 0, z_mm: 0 }, radius, 24),
    false,
  );
  mark(disc, bar.entity_id, {
    role: "bar",
    baseColor: SECTION_STYLE.bar.color,
    flatPositions,
  });
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
      if (shape) addPolyline(group, shape.pts, shape.closed, style.color, item.entity_id, LINE_WEIGHT_REBAR_PX);
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
