// Section-mode helpers, rubber-band ghost previews, and the #section-bar toolbar (ADR 0024).
import * as THREE from "three";
import { S } from "./state.js";
import { pointById } from "./brep.js";
import { goNamedView } from "./camera.js";
import { activeLength } from "./cmdline.js";
import { addFaceGraphic } from "./draw.js";
import { sampleCircle } from "./geom.js";
import { pickByFilter } from "./pick.js";
import { roundedRing } from "./section-geom.js";
import { SNAP_APERTURE_MM, applyLength, orthogonalize } from "./snap.js";
import { INK } from "./theme.js";
import { disposeObject3D, ghosts } from "./viewport.js";

export function clearGhosts() {
  disposeObject3D(ghosts);
  ghosts.clear();
}

export const SECTION_TOOLS = new Set([
  "section-outline",
  "wall-chain",
  "wall-leg",
  "cover-guide",
  "bar",
  "bar-row",
  "bars-edge",
  "hoop",
  "crosstie",
]);

export function isSectionTool(tool = S.tool) {
  return SECTION_TOOLS.has(tool);
}

export function diaMm(designation) {
  const num = Number(String(designation || "Ø16").replace(/^Ø/, ""));
  return Number.isFinite(num) && num > 0 ? num : 16;
}

export function pointSpec(pt) {
  if (pt && pt.entity_id != null) return pt.entity_id;
  return { xyz: [pt.x_mm, pt.y_mm, 0] };
}

export function activeConcreteFaceId() {
  const faces = S.sceneState.concrete_faces || [];
  for (const id of S.selectedIds) {
    if (faces.some((f) => f.entity_id === id)) return id;
  }
  return faces.length === 1 ? faces[0].entity_id : null;
}

export function selectedBarIds() {
  const barSet = new Set((S.sceneState.bars || []).map((b) => b.entity_id));
  return [...S.selectedIds].filter((id) => barSet.has(id));
}

export function pickBarAt(event, hit) {
  const picked = pickByFilter(event, "section");
  if (picked != null && (S.sceneState.bars || []).some((b) => b.entity_id === picked)) {
    return picked;
  }
  if (!hit) return null;
  let best = null;
  let bestDist = SNAP_APERTURE_MM;
  for (const bar of S.sceneState.bars || []) {
    const pt = pointById(bar.point_id);
    if (!pt) continue;
    const d = Math.hypot(pt.x_mm - hit.x_mm, pt.y_mm - hit.y_mm);
    if (d <= bestDist) {
      best = bar.entity_id;
      bestDist = d;
    }
  }
  return best;
}

export function nearestFaceEdge(hit) {
  if (!hit) return null;
  let best = null;
  let bestDist = Number.POSITIVE_INFINITY;
  for (const face of S.sceneState.concrete_faces || []) {
    const pts = face.point_ids.map(pointById).filter(Boolean);
    if (pts.length < 3) continue;
    for (let i = 0; i < pts.length; i += 1) {
      const a = pts[i];
      const b = pts[(i + 1) % pts.length];
      const dx = b.x_mm - a.x_mm;
      const dy = b.y_mm - a.y_mm;
      const len2 = dx * dx + dy * dy;
      if (len2 < 1e-6) continue;
      const u = Math.max(0, Math.min(1, ((hit.x_mm - a.x_mm) * dx + (hit.y_mm - a.y_mm) * dy) / len2));
      const d = Math.hypot(a.x_mm + u * dx - hit.x_mm, a.y_mm + u * dy - hit.y_mm);
      if (d < bestDist) {
        bestDist = d;
        best = { faceId: face.entity_id, edgeIndex: i, a, b };
      }
    }
  }
  return best;
}

export function previewRowPoints(a, b) {
  const len = Math.hypot(b.x_mm - a.x_mm, b.y_mm - a.y_mm);
  if (len < 1e-3) return [a];
  let n = S.sec.mode === "count"
    ? Math.max(2, Math.round(S.sec.count))
    : Math.floor(len / Math.max(10, S.sec.spacingMm)) + 1;
  n = Math.max(2, Math.min(200, n));
  const out = [];
  for (let i = 0; i < n; i += 1) {
    const u = i / (n - 1);
    out.push({
      x_mm: a.x_mm + (b.x_mm - a.x_mm) * u,
      y_mm: a.y_mm + (b.y_mm - a.y_mm) * u,
      z_mm: 0,
    });
  }
  return out;
}

export function legHorizontalPayload() {
  if (S.sec.curtains <= 0) return null;
  return {
    designation: S.sec.barDia,
    spacing_mm: S.sec.spacingMm,
    curtains: S.sec.curtains,
  };
}

export function ensureTopViewOnFirstSectionOp() {
  const has3D = (S.sceneState.solids || []).length > 0 || (S.sceneState.boxes || []).length > 0;
  if (!has3D && S.namedView !== "top") {
    goNamedView("top");
  }
}

export function constrainedPoint(last, hit, event) {
  if (!last || !hit) return hit;
  if (hit.snap === "node") return hit;
  return applyLength(last, orthogonalize(last, hit, event), activeLength());
}

function addGhostLine(a, b, dashed = true) {
  const mat = dashed
    ? new THREE.LineDashedMaterial({ color: INK.ghost, dashSize: 80, gapSize: 60 })
    : new THREE.LineBasicMaterial({ color: INK.ghost });
  const line = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(a.x_mm, a.y_mm, 5),
      new THREE.Vector3(b.x_mm, b.y_mm, 5),
    ]),
    mat,
  );
  if (dashed) line.computeLineDistances();
  ghosts.add(line);
}

function addGhostBarDisc(pt, radiusMm) {
  addFaceGraphic(ghosts, sampleCircle(pt, radiusMm, 20).slice(0, -1), { fill: true, opacity: 0.35 });
}

export function updateSectionGhost(event, hit) {
  if (!isSectionTool()) return false;
  const rBar = diaMm(S.sec.barDia) / 2;
  if (S.tool === "bar" && hit) {
    addGhostBarDisc(hit, rBar);
    return true;
  }
  if (S.tool === "bars-edge" && hit) {
    const edge = nearestFaceEdge(hit);
    if (edge) addGhostLine(edge.a, edge.b, false);
    return true;
  }
  if (!S.pending) return true;

  if (S.pending.kind === "section-outline" && hit) {
    const pts = S.pending.pts;
    const all = pts.concat([constrainedPoint(pts[pts.length - 1], hit, event)]);
    if (all.length === 2) {
      const [a, b] = all;
      addFaceGraphic(ghosts, [
        { x_mm: a.x_mm, y_mm: a.y_mm, z_mm: 0 },
        { x_mm: b.x_mm, y_mm: a.y_mm, z_mm: 0 },
        { x_mm: b.x_mm, y_mm: b.y_mm, z_mm: 0 },
        { x_mm: a.x_mm, y_mm: b.y_mm, z_mm: 0 },
      ], { fill: true, opacity: 0.16 });
    } else if (all.length >= 3) {
      addFaceGraphic(ghosts, all, { fill: true, opacity: 0.16 });
    }
    return true;
  }

  if (S.pending.kind === "wall-chain" && hit) {
    const pts = S.pending.pts;
    const all = pts.concat([constrainedPoint(pts[pts.length - 1], hit, event)]);
    for (let i = 0; i < all.length - 1; i += 1) {
      const a = all[i], b = all[i + 1];
      addGhostLine(a, b, true);
      const dx = b.x_mm - a.x_mm, dy = b.y_mm - a.y_mm;
      const len = Math.hypot(dx, dy);
      if (len > 1) {
        const nx = (-dy / len) * (S.sec.thicknessMm / 2);
        const ny = (dx / len) * (S.sec.thicknessMm / 2);
        addGhostLine({ x_mm: a.x_mm + nx, y_mm: a.y_mm + ny }, { x_mm: b.x_mm + nx, y_mm: b.y_mm + ny }, false);
        addGhostLine({ x_mm: a.x_mm - nx, y_mm: a.y_mm - ny }, { x_mm: b.x_mm - nx, y_mm: b.y_mm - ny }, false);
      }
    }
    return true;
  }

  if (S.pending.kind === "wall-leg" && hit) {
    addGhostLine(S.pending.a, constrainedPoint(S.pending.a, hit, event), true);
    return true;
  }

  if (S.pending.kind === "bar-row" && hit) {
    const cur = constrainedPoint(S.pending.a, hit, event);
    addGhostLine(S.pending.a, cur, true);
    for (const pt of previewRowPoints(S.pending.a, cur)) addGhostBarDisc(pt, rBar);
    return true;
  }

  if (S.pending.kind === "hoop") {
    const bars = S.pending.barIds
      .map((id) => (S.sceneState.bars || []).find((b) => b.entity_id === id))
      .filter(Boolean);
    const centres = bars.map((b) => pointById(b.point_id)).filter(Boolean);
    for (const c of centres) addGhostBarDisc(c, rBar * 1.35);
    if (centres.length >= 2) {
      const rTie = diaMm(S.sec.tieDia) / 2;
      const ring = roundedRing(centres, bars.map((b) => b.diameter_mm / 2 + rTie));
      for (let i = 0; i < ring.length; i += 1) {
        addGhostLine(ring[i], ring[(i + 1) % ring.length], false);
      }
    }
    return true;
  }

  if (S.pending.kind === "crosstie" && hit) {
    const barA = (S.sceneState.bars || []).find((b) => b.entity_id === S.pending.barA);
    const ptA = barA ? pointById(barA.point_id) : null;
    if (ptA) addGhostLine(ptA, hit, false);
    return true;
  }

  return true;
}

const BAR_FIELDS = [
  ["sec-bar-dia", "barDia", (v) => { S.sec.barDia = v; }],
  ["sec-tie-dia", "tieDia", (v) => { S.sec.tieDia = v; }],
  ["sec-mode", "mode", (v) => { S.sec.mode = v; }],
  ["sec-count", "count", (v) => { const n = Number(v); if (n >= 2) S.sec.count = Math.round(n); }],
  ["sec-spacing", "spacingMm", (v) => { const n = Number(v); if (n > 0) S.sec.spacingMm = n; }],
  ["sec-tie-spacing", "tieSpacingMm", (v) => { const n = Number(v); if (n > 0) S.sec.tieSpacingMm = n; }],
  ["sec-hooks", "hooks", (v) => { S.sec.hooks = v; }],
  ["sec-cover", "coverMm", (v) => { const n = Number(v); if (n > 0) S.sec.coverMm = n; }],
  ["sec-thick", "thicknessMm", (v) => { const n = Number(v); if (n > 0) S.sec.thicknessMm = n; }],
  ["sec-curtains", "curtains", (v) => { const n = Number(v); if (n >= 0) S.sec.curtains = Math.round(n); }],
  ["sec-material", "material", (v) => { if (v.trim()) S.sec.material = v.trim(); }],
];

export function syncSectionBar() {
  const bar = document.getElementById("section-bar");
  if (!bar) return;
  bar.hidden = !isSectionTool(S.tool) && S.selectFilter !== "section";
  for (const [id, key] of BAR_FIELDS) {
    const el = document.getElementById(id);
    if (el && document.activeElement !== el) el.value = String(S.sec[key]);
  }
}

export function bindSectionBar() {
  for (const [id, , fn] of BAR_FIELDS) {
    const el = document.getElementById(id);
    if (!el) continue;
    el.addEventListener("change", () => fn(el.value));
    el.addEventListener("input", () => fn(el.value));
  }
  syncSectionBar();
}
