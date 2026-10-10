// Rubber-band previews (ghosts) for the active tool, and snap markers.
import * as THREE from "three";
import { S } from "./state.js";
import { activeLength, setCoords, sidesValue } from "./cmdline.js";
import { SNAP_COLOR, addCurve, addFaceGraphic, addVolume } from "./draw.js";
import {
  dist3,
  regularPolygon,
  sampleArc,
  sampleBezier,
  sampleCircle,
  sampleEllipse,
} from "./geom.js";
import { isGridSnap } from "./grid.js";
import { solveBreak, solveTrimOrExtend } from "./modify.js";
import { pickEntity } from "./pick.js";
import {
  SNAP_APERTURE_MM,
  applyLength,
  applySnaps,
  hitHeight,
  hitWorkplane,
  orthogonalize,
  rawHit,
} from "./snap.js";
import { ghosts } from "./viewport.js";

function ghostLine(a, b) {
  ghostStroke(a, b, 0x6cb3ff, true);
}

function ghostPolyline(pts, cursor) {
  const all = cursor ? pts.concat([cursor]) : pts;
  for (let index = 0; index < all.length - 1; index += 1) {
    ghostStroke(all[index], all[index + 1], 0x6cb3ff, index === all.length - 2);
  }
}

export function polylineCloses(end) {
  return Boolean(
    S.pending
    && S.pending.kind === "polyline"
    && S.pending.pts.length >= 3
    && dist3(S.pending.pts[0], end) <= SNAP_APERTURE_MM,
  );
}

function ghostStroke(a, b, color, dashed) {
  const material = dashed
    ? new THREE.LineDashedMaterial({ color, dashSize: 120, gapSize: 80 })
    : new THREE.LineBasicMaterial({ color });
  const line = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(a.x_mm, a.y_mm, a.z_mm || 0),
      new THREE.Vector3(b.x_mm, b.y_mm, b.z_mm || 0),
    ]),
    material,
  );
  if (dashed) line.computeLineDistances();
  ghosts.add(line);
}

function drawTrimPreview(preview) {
  if (preview.mode === "extend") {
    ghostStroke(preview.from, preview.cut, 0x7dce7d, true);
    ghostStroke(preview.keepA, preview.from, 0x6cb3ff, false);
  } else {
    ghostStroke(preview.discardA, preview.cut, 0xff6b6b, true);
    ghostStroke(preview.keepA, preview.cut, 0x6cb3ff, false);
  }
  drawSnapMarker(preview.cut, "node");
}

function ghostRect(a, b, height = 0) {
  const x0 = Math.min(a.x_mm, b.x_mm);
  const y0 = Math.min(a.y_mm, b.y_mm);
  const x1 = Math.max(a.x_mm, b.x_mm);
  const y1 = Math.max(a.y_mm, b.y_mm);
  addFaceGraphic(ghosts, [
    { x_mm: x0, y_mm: y0, z_mm: 0 },
    { x_mm: x1, y_mm: y0, z_mm: 0 },
    { x_mm: x1, y_mm: y1, z_mm: 0 },
    { x_mm: x0, y_mm: y1, z_mm: 0 },
  ], { fill: true, opacity: 0.18 });
  if (Math.abs(height) > 1) {
    addVolume(
      ghosts,
      [x0, y0, Math.min(0, height)],
      [Math.max(x1 - x0, 100), Math.max(y1 - y0, 100), Math.abs(height)],
      0x6cb3ff,
      0.18,
    );
  }
}

function drawSnapMarker(xyz, kind) {
  const size = kind === "node" ? 180 : kind === "grid-major" ? 160 : 110;
  const z = xyz.z_mm + 40;
  const loop = [
    [xyz.x_mm - size, xyz.y_mm - size, z],
    [xyz.x_mm + size, xyz.y_mm - size, z],
    [xyz.x_mm + size, xyz.y_mm + size, z],
    [xyz.x_mm - size, xyz.y_mm + size, z],
    [xyz.x_mm - size, xyz.y_mm - size, z],
  ].map((corner) => new THREE.Vector3(...corner));
  ghosts.add(new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(loop),
    new THREE.LineBasicMaterial({ color: SNAP_COLOR }),
  ));
}

export function currentEnd(event) {
  if (!S.pending) return null;
  if (S.pending.kind === "polyline") {
    const raw = rawHit(event);
    if (!raw) return null;
    const last = S.pending.pts[S.pending.pts.length - 1];
    if (S.pending.pts.length >= 3 && dist3(S.pending.pts[0], raw) <= SNAP_APERTURE_MM) {
      return { ...S.pending.pts[0], snap: "node" };
    }
    const hit = applySnaps(raw);
    if (!hit) return null;
    if (hit.snap === "node") return hit;
    return applyLength(last, orthogonalize(last, hit, event), activeLength());
  }
  const raw = hitWorkplane(event);
  if (!raw) return null;
  if (raw.snap === "node") return raw;
  if (S.pending.kind === "line" || S.pending.kind === "move" || S.pending.kind === "array" || S.pending.kind === "mirror" || (S.pending.kind === "radial" && S.tool !== "ellipse")) {
    return applyLength(S.pending.a, orthogonalize(S.pending.a, raw, event), activeLength());
  }
  if (S.pending.kind === "rect") {
    return orthogonalize(S.pending.a, raw, event);
  }
  return raw;
}

export function updateGhost(event) {
  ghosts.clear();
  S.ghostDims = [];
  if (!event) {
    setCoords(null);
    return;
  }
  const hit = hitWorkplane(event);
  if (hit && (hit.snap === "node" || isGridSnap(hit.snap))) drawSnapMarker(hit, hit.snap);
  if ((S.tool === "trim" || S.tool === "extend") && !S.pending) {
    const picked = pickEntity(event);
    const preview = picked ? solveTrimOrExtend(picked, hit, S.tool) : null;
    if (preview) drawTrimPreview(preview);
    setCoords(hit);
    return;
  }
  if (S.tool === "break" && S.pending && S.pending.kind === "break") {
    const picked = pickEntity(event);
    const preview = solveBreak(S.pending.lineId, picked);
    if (preview) drawSnapMarker(preview.cut, "node");
    setCoords(hit);
    return;
  }
  if (!S.pending) {
    setCoords(hit);
    return;
  }
  if (S.pending.kind === "polyline") {
    const end = currentEnd(event);
    if (end) {
      ghostPolyline(S.pending.pts, end);
      const last = S.pending.pts[S.pending.pts.length - 1];
      setCoords(end, last);
      if (polylineCloses(end)) drawSnapMarker(S.pending.pts[0], "node");
    }
    return;
  }
  if (S.pending.kind === "line" || S.pending.kind === "move" || S.pending.kind === "array" || S.pending.kind === "mirror") {
    const end = currentEnd(event);
    if (end) {
      ghostLine(S.pending.a, end);
      setCoords(end, S.pending.a);
    }
    return;
  }
  if (S.pending.kind === "rotate") {
    const end = hitWorkplane(event);
    if (end) {
      ghostLine(S.pending.a, end);
      setCoords(end, S.pending.a);
    }
    return;
  }
  if (S.pending.kind === "rect") {
    const end = currentEnd(event);
    if (end) {
      ghostRect(S.pending.a, end);
      setCoords(end, S.pending.a);
    }
    return;
  }
  if (S.pending.kind === "height" || S.pending.kind === "extrude") {
    const height = hitHeight(event, S.pending.a, S.pending.b);
    ghostRect(S.pending.a, S.pending.b, height);
    setCoords(hit);
    return;
  }
  if (S.pending.kind === "radial") {
    const rim = currentEnd(event);
    if (!rim) return;
    const radius = dist3(S.pending.a, rim);
    if (S.tool === "circle") {
      addFaceGraphic(ghosts, sampleCircle(S.pending.a, radius).slice(0, -1), { fill: true, opacity: 0.22 });
    } else if (S.tool === "polygon") {
      addFaceGraphic(ghosts, regularPolygon(S.pending.a, rim, sidesValue()), { fill: true, opacity: 0.18 });
    } else if (S.tool === "ellipse") {
      const rx = Math.max(Math.abs(rim.x_mm - S.pending.a.x_mm), 1);
      const ry = Math.max(Math.abs(rim.y_mm - S.pending.a.y_mm), 1);
      addFaceGraphic(ghosts, sampleEllipse(S.pending.a, rx, ry).slice(0, -1), { fill: true, opacity: 0.22 });
    }
    setCoords(rim, S.pending.a);
    return;
  }
  if (S.pending.kind === "arc") {
    const cur = currentEnd(event) || hit;
    if (!cur) return;
    if (S.pending.pts.length === 1) {
      ghostLine(S.pending.pts[0], cur);
    } else {
      addCurve(ghosts, sampleArc(S.pending.pts[0], S.pending.pts[1], cur), 0x6cb3ff);
    }
    setCoords(cur, S.pending.pts[0]);
    return;
  }
  if (S.pending.kind === "bezier") {
    const cur = currentEnd(event) || hit;
    if (!cur) return;
    const pts = S.pending.pts.concat([cur]);
    if (pts.length === 2) ghostLine(pts[0], pts[1]);
    else if (pts.length === 3) addCurve(ghosts, sampleBezier([pts[0], pts[1], pts[2], pts[2]]), 0x6cb3ff);
    else addCurve(ghosts, sampleBezier(pts.slice(0, 4)), 0x6cb3ff);
    setCoords(cur, S.pending.pts[0]);
  }
}
