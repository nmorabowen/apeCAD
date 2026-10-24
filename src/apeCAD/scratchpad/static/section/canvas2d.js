// 2-D HTML5 Canvas renderer, viewport math, and hit-testing for the section client (ADR 0026).
// Zero external dependencies; no module-scope DOM access.

export const PALETTE = {
  bg: "#f7f6f3",
  gridMinor: "#e7e4dd",
  gridMajor: "#d8d5cd",
  axis: "#b9b5ab",
  concreteFill: "rgba(180, 180, 180, 0.55)",
  concreteEdge: "#14181d",
  legAxis: "#6e757c",
  coverRing: "#808080",
  centreRing: "#97a1ad",
  rebar: "#000077",
  hoop: "#000077",
  crosstie: "#000077",
  selected: "#2f74ad",
  selectedFill: "rgba(47, 116, 173, 0.24)",
  ghost: "#2f74ad",
  ghostFill: "rgba(47, 116, 173, 0.14)",
  snap: "#c64a1a",
  warn: "#c64a1a",
};

function distToSegment(p, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const len2 = dx * dx + dy * dy;
  if (len2 <= 1e-12) return Math.hypot(p[0] - a[0], p[1] - a[1]);
  const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / len2));
  return Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy));
}

export function pointInPolygon(pt, ring) {
  if (!ring || ring.length < 3) return false;
  let inside = false;
  const x = pt[0], y = pt[1];
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0], yi = ring[i][1];
    const xj = ring[j][0], yj = ring[j][1];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

export function sceneBoundsMm(scene) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  const visit = (pt) => {
    if (!Array.isArray(pt) || pt.length < 2) return;
    const x = Number(pt[0]), y = Number(pt[1]);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;
    if (x < minX) minX = x;
    if (y < minY) minY = y;
    if (x > maxX) maxX = x;
    if (y > maxY) maxY = y;
  };
  if (scene) {
    for (const f of scene.concrete_faces || []) {
      for (const p of f.outer_mm || f.ring_mm || []) visit(p);
    }
    for (const l of scene.wall_legs || []) {
      for (const p of l.outline_mm || [l.start_mm, l.end_mm]) visit(p);
    }
    for (const b of scene.bars || []) {
      const c = b.centre_mm || [b.x_mm, b.y_mm];
      const r = (b.diameter_mm || 16) / 2;
      visit([c[0] - r, c[1] - r]);
      visit([c[0] + r, c[1] + r]);
    }
    for (const h of scene.hoops || []) {
      for (const p of h.display_ring_mm || h.ring_mm || []) visit(p);
    }
  }
  if (!Number.isFinite(minX)) return [0, 0, 500, 500];
  if (maxX - minX < 1e-3) { minX -= 100; maxX += 100; }
  if (maxY - minY < 1e-3) { minY -= 100; maxY += 100; }
  return [minX, minY, maxX, maxY];
}

export function createViewport(canvas) {
  const view = {
    width: 800,
    height: 600,
    scale: 0.8,
    panX: 120,
    panY: 80,
    worldToScreen(pt) {
      return [pt[0] * view.scale + view.panX, view.height - (pt[1] * view.scale + view.panY)];
    },
    screenToWorld(sp) {
      return [(sp[0] - view.panX) / view.scale, (view.height - sp[1] - view.panY) / view.scale];
    },
    resize() {
      const w = Number(canvas?.clientWidth || canvas?.width || 800) || 800;
      const h = Number(canvas?.clientHeight || canvas?.height || 600) || 600;
      view.width = w;
      view.height = h;
      if (canvas && typeof canvas === "object") {
        canvas.width = w;
        canvas.height = h;
      }
    },
    fit(scene) {
      view.resize();
      const [minX, minY, maxX, maxY] = sceneBoundsMm(scene);
      const bw = Math.max(10, maxX - minX);
      const bh = Math.max(10, maxY - minY);
      const pad = 0.78;
      view.scale = Math.max(0.02, Math.min((view.width * pad) / bw, (view.height * pad) / bh));
      const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
      view.panX = view.width / 2 - cx * view.scale;
      view.panY = view.height / 2 - cy * view.scale;
    },
    zoomAt(screenPt, factor) {
      const [wx, wy] = view.screenToWorld(screenPt);
      view.scale = Math.max(0.01, Math.min(40, view.scale * factor));
      view.panX = screenPt[0] - wx * view.scale;
      view.panY = view.height - screenPt[1] - wy * view.scale;
    },
    panBy(dxPx, dyPx) {
      view.panX += dxPx;
      view.panY -= dyPx;
    },
  };
  view.resize();
  return view;
}

export function hitTestSection(screenPt, view, scene, aperturePx = 10) {
  if (!scene) return null;
  const worldPt = view.screenToWorld(screenPt);

  let bestBar = null, bestBarD = Infinity;
  for (const b of scene.bars || []) {
    const c = b.centre_mm || [b.x_mm, b.y_mm];
    const sp = view.worldToScreen(c);
    const rPx = Math.max(aperturePx, ((b.diameter_mm || 16) / 2) * view.scale + 4);
    const d = Math.hypot(sp[0] - screenPt[0], sp[1] - screenPt[1]);
    if (d <= rPx && d < bestBarD) {
      bestBar = { kind: "Bar", id: b.id ?? b.entity_id, item: b };
      bestBarD = d;
    }
  }
  if (bestBar) return bestBar;

  for (const t of scene.crossties || []) {
    if (!t.start_mm || !t.end_mm) continue;
    const a = view.worldToScreen(t.start_mm), b = view.worldToScreen(t.end_mm);
    if (distToSegment(screenPt, a, b) <= aperturePx) {
      return { kind: "Crosstie", id: t.id ?? t.entity_id, item: t };
    }
  }

  for (const h of scene.hoops || []) {
    const ring = h.display_ring_mm || h.ring_mm || [];
    for (let i = 0; i < ring.length; i++) {
      const a = view.worldToScreen(ring[i]), b = view.worldToScreen(ring[(i + 1) % ring.length]);
      if (distToSegment(screenPt, a, b) <= aperturePx) {
        return { kind: "Hoop", id: h.id ?? h.entity_id, item: h };
      }
    }
  }

  for (const g of scene.cover_guides || []) {
    const ring = g.cover_ring_mm || [];
    for (let i = 0; i < ring.length; i++) {
      const a = view.worldToScreen(ring[i]), b = view.worldToScreen(ring[(i + 1) % ring.length]);
      if (distToSegment(screenPt, a, b) <= aperturePx) {
        return { kind: "CoverGuide", id: g.id ?? g.entity_id, item: g };
      }
    }
  }

  for (const l of scene.wall_legs || []) {
    const s = l.axis_start_mm || l.start_mm, e = l.axis_end_mm || l.end_mm;
    if (s && e) {
      const a = view.worldToScreen(s), b = view.worldToScreen(e);
      if (distToSegment(screenPt, a, b) <= aperturePx) {
        return { kind: "WallLeg", id: l.id ?? l.entity_id, item: l };
      }
    }
  }

  for (const f of scene.concrete_faces || []) {
    const ring = f.outer_mm || f.ring_mm || [];
    for (let i = 0; i < ring.length; i++) {
      const a = view.worldToScreen(ring[i]), b = view.worldToScreen(ring[(i + 1) % ring.length]);
      if (distToSegment(screenPt, a, b) <= aperturePx) {
        return { kind: "ConcreteFace", id: f.id ?? f.entity_id, item: f, edge_index: i };
      }
    }
    if (pointInPolygon(worldPt, ring)) {
      const inHole = (f.openings_mm || []).some((hole) => pointInPolygon(worldPt, hole));
      if (!inHole) return { kind: "ConcreteFace", id: f.id ?? f.entity_id, item: f };
    }
  }

  return null;
}

function traceRing(ctx, view, ring) {
  if (!ring || ring.length < 2) return;
  const [x0, y0] = view.worldToScreen(ring[0]);
  ctx.moveTo(x0, y0);
  for (let i = 1; i < ring.length; i++) {
    const [x, y] = view.worldToScreen(ring[i]);
    ctx.lineTo(x, y);
  }
  ctx.closePath();
}

function drawGrid(ctx, view, stepMm = 50) {
  const minor = stepMm > 0 ? stepMm : 50;
  const major = minor * 5;
  const [w0, h0] = view.screenToWorld([0, view.height]);
  const [w1, h1] = view.screenToWorld([view.width, 0]);
  const minX = Math.floor(Math.min(w0, w1) / minor) * minor;
  const maxX = Math.ceil(Math.max(w0, w1) / minor) * minor;
  const minY = Math.floor(Math.min(h0, h1) / minor) * minor;
  const maxY = Math.ceil(Math.max(h0, h1) / minor) * minor;

  if (minor * view.scale >= 6) {
    ctx.strokeStyle = PALETTE.gridMinor;
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let x = minX; x <= maxX; x += minor) {
      const [sx] = view.worldToScreen([x, 0]);
      ctx.moveTo(sx, 0);
      ctx.lineTo(sx, view.height);
    }
    for (let y = minY; y <= maxY; y += minor) {
      const [, sy] = view.worldToScreen([0, y]);
      ctx.moveTo(0, sy);
      ctx.lineTo(view.width, sy);
    }
    ctx.stroke();
  }

  ctx.strokeStyle = PALETTE.gridMajor;
  ctx.lineWidth = 1;
  ctx.beginPath();
  const majMinX = Math.floor(minX / major) * major;
  const majMinY = Math.floor(minY / major) * major;
  for (let x = majMinX; x <= maxX; x += major) {
    const [sx] = view.worldToScreen([x, 0]);
    ctx.moveTo(sx, 0);
    ctx.lineTo(sx, view.height);
  }
  for (let y = majMinY; y <= maxY; y += major) {
    const [, sy] = view.worldToScreen([0, y]);
    ctx.moveTo(0, sy);
    ctx.lineTo(view.width, sy);
  }
  ctx.stroke();

  const [ox, oy] = view.worldToScreen([0, 0]);
  ctx.strokeStyle = PALETTE.axis;
  ctx.lineWidth = 1.25;
  ctx.beginPath();
  ctx.moveTo(ox, 0);
  ctx.lineTo(ox, view.height);
  ctx.moveTo(0, oy);
  ctx.lineTo(view.width, oy);
  ctx.stroke();
}

export function renderSectionCanvas(canvas, view, state) {
  const ctx = canvas && typeof canvas.getContext === "function" ? canvas.getContext("2d") : null;
  if (!ctx) return;
  const { scene, selectedIds = new Set(), snap = null, ghost = null, gridOn = true, gridStepMm = 50 } = state || {};

  ctx.save();
  ctx.fillStyle = PALETTE.bg;
  ctx.fillRect(0, 0, view.width, view.height);
  if (gridOn) drawGrid(ctx, view, gridStepMm);

  if (scene) {
    // 1. Concrete faces + openings
    for (const f of scene.concrete_faces || []) {
      const ring = f.outer_mm || f.ring_mm || [];
      if (ring.length < 3) continue;
      const sel = selectedIds.has(f.id ?? f.entity_id);
      ctx.beginPath();
      traceRing(ctx, view, ring);
      for (const hole of f.openings_mm || []) traceRing(ctx, view, hole);
      ctx.fillStyle = sel ? PALETTE.selectedFill : PALETTE.concreteFill;
      ctx.fill("evenodd");
      ctx.strokeStyle = sel ? PALETTE.selected : PALETTE.concreteEdge;
      ctx.lineWidth = sel ? 2.2 : 1.5;
      ctx.stroke();
    }

    // 2. Wall legs (dash-dot centreline)
    for (const l of scene.wall_legs || []) {
      const s = l.axis_start_mm || l.start_mm, e = l.axis_end_mm || l.end_mm;
      if (!s || !e) continue;
      const sel = selectedIds.has(l.id ?? l.entity_id);
      const [x0, y0] = view.worldToScreen(s), [x1, y1] = view.worldToScreen(e);
      ctx.save();
      ctx.setLineDash([10, 4, 2, 4]);
      ctx.strokeStyle = sel ? PALETTE.selected : PALETTE.legAxis;
      ctx.lineWidth = sel ? 2 : 1.2;
      ctx.beginPath();
      ctx.moveTo(x0, y0);
      ctx.lineTo(x1, y1);
      ctx.stroke();
      ctx.restore();
    }

    // 3. Cover guides
    for (const g of scene.cover_guides || []) {
      const sel = selectedIds.has(g.id ?? g.entity_id);
      if (Array.isArray(g.cover_ring_mm) && g.cover_ring_mm.length >= 3) {
        ctx.save();
        ctx.setLineDash([6, 4]);
        ctx.strokeStyle = sel ? PALETTE.selected : PALETTE.coverRing;
        ctx.lineWidth = sel ? 1.8 : 1.1;
        ctx.beginPath();
        traceRing(ctx, view, g.cover_ring_mm);
        ctx.stroke();
        ctx.restore();
      }
      if (Array.isArray(g.bar_centre_ring_mm) && g.bar_centre_ring_mm.length >= 3) {
        ctx.save();
        ctx.setLineDash([2, 4]);
        ctx.strokeStyle = PALETTE.centreRing;
        ctx.lineWidth = 1;
        ctx.beginPath();
        traceRing(ctx, view, g.bar_centre_ring_mm);
        ctx.stroke();
        ctx.restore();
      }
    }

    // 4. Hoops
    for (const h of scene.hoops || []) {
      const ring = h.display_ring_mm || h.ring_mm || [];
      if (ring.length < 2) continue;
      const sel = selectedIds.has(h.id ?? h.entity_id);
      ctx.strokeStyle = sel ? PALETTE.selected : PALETTE.hoop;
      ctx.lineWidth = Math.max(sel ? 2.4 : 1.6, (h.diameter_mm || 10) * view.scale * 0.6);
      ctx.beginPath();
      traceRing(ctx, view, ring);
      ctx.stroke();
    }

    // 5. Crossties
    for (const t of scene.crossties || []) {
      if (!t.start_mm || !t.end_mm) continue;
      const sel = selectedIds.has(t.id ?? t.entity_id);
      const [x0, y0] = view.worldToScreen(t.start_mm);
      const [x1, y1] = view.worldToScreen(t.end_mm);
      ctx.strokeStyle = sel ? PALETTE.selected : PALETTE.crosstie;
      ctx.lineWidth = Math.max(sel ? 2.4 : 1.5, (t.diameter_mm || 10) * view.scale * 0.55);
      ctx.beginPath();
      ctx.moveTo(x0, y0);
      ctx.lineTo(x1, y1);
      ctx.stroke();
    }

    // 6. Bars
    for (const b of scene.bars || []) {
      const c = b.centre_mm || [b.x_mm, b.y_mm];
      const [sx, sy] = view.worldToScreen(c);
      const rPx = Math.max(3.5, ((b.diameter_mm || 16) / 2) * view.scale);
      const sel = selectedIds.has(b.id ?? b.entity_id);
      ctx.beginPath();
      ctx.arc(sx, sy, rPx, 0, Math.PI * 2);
      ctx.fillStyle = sel ? PALETTE.selected : PALETTE.rebar;
      ctx.fill();
      if (sel) {
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }
    }
  }

  // 7. Ghost preview
  if (ghost) {
    ctx.save();
    ctx.strokeStyle = PALETTE.ghost;
    ctx.fillStyle = PALETTE.ghostFill;
    ctx.lineWidth = 1.5;
    if (ghost.ring && ghost.ring.length >= 2) {
      ctx.beginPath();
      traceRing(ctx, view, ghost.ring);
      if (ghost.ring.length >= 3) ctx.fill();
      ctx.stroke();
    }
    if (ghost.polyline && ghost.polyline.length >= 2) {
      ctx.setLineDash([6, 4]);
      ctx.beginPath();
      const [x0, y0] = view.worldToScreen(ghost.polyline[0]);
      ctx.moveTo(x0, y0);
      for (let i = 1; i < ghost.polyline.length; i++) {
        const [x, y] = view.worldToScreen(ghost.polyline[i]);
        ctx.lineTo(x, y);
      }
      ctx.stroke();
    }
    for (const b of ghost.bars || []) {
      const [sx, sy] = view.worldToScreen(b.centre);
      const rPx = Math.max(3.5, ((b.diameter_mm || 16) / 2) * view.scale);
      ctx.beginPath();
      ctx.arc(sx, sy, rPx, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    }
    ctx.restore();
  }

  // 8. Snap indicator
  if (snap && snap.snapped && Array.isArray(snap.point)) {
    const [sx, sy] = view.worldToScreen(snap.point);
    ctx.save();
    ctx.strokeStyle = PALETTE.snap;
    ctx.lineWidth = 1.6;
    if (snap.kind === "bar") {
      ctx.beginPath();
      ctx.arc(sx, sy, 6, 0, Math.PI * 2);
      ctx.stroke();
    } else if (snap.kind === "midpoint") {
      ctx.beginPath();
      ctx.moveTo(sx, sy - 6);
      ctx.lineTo(sx + 6, sy);
      ctx.lineTo(sx, sy + 6);
      ctx.lineTo(sx - 6, sy);
      ctx.closePath();
      ctx.stroke();
    } else {
      ctx.strokeRect(sx - 5, sy - 5, 10, 10);
    }
    ctx.restore();
  }

  ctx.restore();
}
