// Coordinate parser and 10 px 2-D snap engine for the section client (ADR 0026).

export const SNAP_PX = 10;

const UNIT_FACTORS = {
  mm: 1,
  cm: 10,
  m: 1000,
  in: 25.4,
};

export function parseLengthMm(raw) {
  const s = String(raw ?? "").trim();
  const m = s.match(/^([+-]?(?:\d+\.?\d*|\.\d+))\s*(mm|cm|m|in)?$/i);
  if (!m) return NaN;
  const val = Number(m[1]);
  const unit = (m[2] || "mm").toLowerCase();
  return val * (UNIT_FACTORS[unit] || 1);
}

export function parseInput(raw, lastPoint = null, dirHint = null) {
  const s = String(raw ?? "").trim();
  if (!s) return { kind: "error", message: "Empty input." };
  const lower = s.toLowerCase();
  if (lower === "c" || lower === "close") {
    return { kind: "command", command: "close" };
  }
  if (lower === "u" || lower === "undo") {
    return { kind: "command", command: "undo" };
  }
  const tm = s.match(/^t(?:hickness)?(?:\s+|\s*=\s*)(.+)$/i);
  if (tm) {
    const t = parseLengthMm(tm[1]);
    if (!(t > 0)) return { kind: "error", message: "Invalid thickness." };
    return { kind: "thickness", thickness_mm: t };
  }

  const origin = Array.isArray(lastPoint) && lastPoint.length >= 2 ? lastPoint : [0, 0];

  if (s.startsWith("@")) {
    const rest = s.slice(1).trim();
    const polar = rest.match(/^([^<,]+)<\s*([+-]?(?:\d+\.?\d*|\.\d+))$/);
    if (polar) {
      const r = parseLengthMm(polar[1]);
      const deg = Number(polar[2]);
      if (!Number.isFinite(r) || !(r >= 0) || !Number.isFinite(deg)) {
        return { kind: "error", message: "Invalid polar coordinate." };
      }
      const rad = (deg * Math.PI) / 180;
      return {
        kind: "point",
        point: [origin[0] + r * Math.cos(rad), origin[1] + r * Math.sin(rad)],
        relative: true,
        polar: true,
      };
    }
    const parts = rest.split(/\s*,\s*|\s+/);
    if (parts.length === 2) {
      const dx = parseLengthMm(parts[0]);
      const dy = parseLengthMm(parts[1]);
      if (!Number.isFinite(dx) || !Number.isFinite(dy)) {
        return { kind: "error", message: "Invalid relative coordinate." };
      }
      return {
        kind: "point",
        point: [origin[0] + dx, origin[1] + dy],
        relative: true,
      };
    }
    return { kind: "error", message: "Invalid relative input." };
  }

  const parts = s.split(/\s*,\s*|\s+/);
  if (parts.length === 2) {
    const x = parseLengthMm(parts[0]);
    const y = parseLengthMm(parts[1]);
    if (!Number.isFinite(x) || !Number.isFinite(y)) {
      return { kind: "error", message: "Invalid coordinate." };
    }
    return { kind: "point", point: [x, y], relative: false };
  }

  const len = parseLengthMm(s);
  if (Number.isFinite(len)) {
    if (Array.isArray(lastPoint) && Array.isArray(dirHint)) {
      const norm = Math.hypot(dirHint[0], dirHint[1]);
      if (norm > 1e-9) {
        return {
          kind: "point",
          point: [
            lastPoint[0] + (dirHint[0] / norm) * len,
            lastPoint[1] + (dirHint[1] / norm) * len,
          ],
          length_mm: len,
          relative: true,
        };
      }
    }
    return { kind: "length", length_mm: len };
  }

  return { kind: "error", message: "Unrecognized input." };
}

function toScreen(pt, view) {
  if (view && typeof view.worldToScreen === "function") {
    return view.worldToScreen(pt);
  }
  const scale = view?.scale ?? 1;
  const panX = view?.panX ?? 0;
  const panY = view?.panY ?? 0;
  const height = view?.height ?? 600;
  return [pt[0] * scale + panX, height - (pt[1] * scale + panY)];
}

function closestOnSegment(p, a, b) {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const len2 = dx * dx + dy * dy;
  if (len2 <= 1e-12) return a.slice();
  const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / len2));
  return [a[0] + t * dx, a[1] + t * dy];
}

export function snapPoint2D(screenPt, worldPt, view, scene, opts = {}) {
  const aperturePx = opts.aperturePx ?? SNAP_PX;
  const pointCandidates = [];
  const edgeCandidates = [];

  if (scene) {
    const ptById = new Map();
    for (const pt of scene.points || []) {
      const id = pt.entity_id ?? pt.id;
      const xy = Array.isArray(pt.position) ? [pt.position[0], pt.position[1]] : [pt.x_mm, pt.y_mm];
      if (id != null && Number.isFinite(xy[0]) && Number.isFinite(xy[1])) {
        ptById.set(id, xy);
      }
    }
    const barPointIds = new Set();
    for (const bar of scene.bars || []) {
      const id = bar.entity_id ?? bar.id;
      if (bar.point_id != null) barPointIds.add(bar.point_id);
      const xy = Array.isArray(bar.centre_mm)
        ? [bar.centre_mm[0], bar.centre_mm[1]]
        : bar.x_mm != null && bar.y_mm != null
          ? [bar.x_mm, bar.y_mm]
          : ptById.get(bar.point_id);
      if (Array.isArray(xy) && Number.isFinite(xy[0]) && Number.isFinite(xy[1])) {
        pointCandidates.push({
          point: [xy[0], xy[1]],
          kind: "bar",
          id,
          priority: 1,
        });
      }
    }
    for (const pt of scene.points || []) {
      const id = pt.entity_id ?? pt.id;
      if (barPointIds.has(id)) continue;
      const xy = Array.isArray(pt.position) ? [pt.position[0], pt.position[1]] : [pt.x_mm, pt.y_mm];
      if (Number.isFinite(xy[0]) && Number.isFinite(xy[1])) {
        pointCandidates.push({
          point: [xy[0], xy[1]],
          kind: "point",
          id,
          priority: 1,
        });
      }
    }
    for (const g of scene.cover_guides || []) {
      const targetId = g.face_id ?? g.target_id;
      const rings = [g.bar_centre_ring_mm, g.cover_ring_mm].filter(Array.isArray);
      for (const ring of rings) {
        for (let i = 0; i < ring.length; i++) {
          const v = ring[i];
          pointCandidates.push({
            point: [v[0], v[1]],
            kind: "cover-corner",
            target_id: targetId,
            priority: 2,
          });
          const next = ring[(i + 1) % ring.length];
          edgeCandidates.push({
            a: v,
            b: next,
            kind: "cover-edge",
            target_id: targetId,
            edge_index: i,
            priority: 4,
          });
        }
      }
    }
    for (const f of scene.concrete_faces || []) {
      const faceId = f.entity_id ?? f.id;
      const ring = Array.isArray(f.outer_mm)
        ? f.outer_mm
        : Array.isArray(f.ring_mm)
          ? f.ring_mm
          : (f.point_ids || []).map((pid) => ptById.get(pid)).filter(Boolean);
      for (let i = 0; i < ring.length; i++) {
        const a = ring[i];
        const b = ring[(i + 1) % ring.length];
        pointCandidates.push({
          point: [a[0], a[1]],
          kind: "vertex",
          target_id: faceId,
          priority: 3,
        });
        pointCandidates.push({
          point: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2],
          kind: "midpoint",
          target_id: faceId,
          edge_index: i,
          priority: 3,
        });
        edgeCandidates.push({
          a,
          b,
          kind: "edge",
          target_id: faceId,
          edge_index: i,
          priority: 5,
        });
      }
    }
  }

  let best = null;
  for (const cand of pointCandidates) {
    const sp = toScreen(cand.point, view);
    const d = Math.hypot(sp[0] - screenPt[0], sp[1] - screenPt[1]);
    if (d <= aperturePx) {
      if (
        !best ||
        cand.priority < best.priority ||
        (cand.priority === best.priority && d < best.distance_px)
      ) {
        best = { ...cand, distance_px: d };
      }
    }
  }
  if (best) {
    return {
      point: best.point,
      snapped: true,
      kind: best.kind,
      id: best.id || null,
      target_id: best.target_id || null,
      edge_index: best.edge_index ?? null,
      distance_px: best.distance_px,
    };
  }

  let bestEdge = null;
  for (const seg of edgeCandidates) {
    const proj = closestOnSegment(worldPt, seg.a, seg.b);
    const sp = toScreen(proj, view);
    const d = Math.hypot(sp[0] - screenPt[0], sp[1] - screenPt[1]);
    if (d <= aperturePx) {
      if (
        !bestEdge ||
        seg.priority < bestEdge.priority ||
        (seg.priority === bestEdge.priority && d < bestEdge.distance_px)
      ) {
        bestEdge = {
          point: proj,
          kind: seg.kind,
          target_id: seg.target_id,
          edge_index: seg.edge_index,
          priority: seg.priority,
          distance_px: d,
        };
      }
    }
  }
  if (bestEdge) {
    return {
      point: bestEdge.point,
      snapped: true,
      kind: bestEdge.kind,
      id: null,
      target_id: bestEdge.target_id || null,
      edge_index: bestEdge.edge_index ?? null,
      distance_px: bestEdge.distance_px,
    };
  }

  const gridStep = opts.gridStepMm ?? 0;
  if (gridStep > 0 && opts.gridSnap !== false) {
    const gx = Math.round(worldPt[0] / gridStep) * gridStep;
    const gy = Math.round(worldPt[1] / gridStep) * gridStep;
    return {
      point: [gx, gy],
      snapped: true,
      kind: "grid",
      id: null,
      target_id: null,
      edge_index: null,
      distance_px: 0,
    };
  }

  return {
    point: [worldPt[0], worldPt[1]],
    snapped: false,
    kind: null,
    id: null,
    target_id: null,
    edge_index: null,
    distance_px: Infinity,
  };
}
