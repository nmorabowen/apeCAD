// 2-D HTML5 Canvas renderer, viewport math, and hit-testing for the section client (ADR 0026).
// Zero external dependencies; no module-scope DOM access. What is drawn, on which layer, and
// what a click hits come from the display list (`display2d.js`); the colours stay here.

import { displayList, hitTestDisplay, pointInPolygon, sceneBoundsMm } from "./display2d.js";

export const PALETTE = {
  bg: "#f7f6f3",
  gridMinor: "#e7e4dd",
  gridMajor: "#d8d5cd",
  axis: "#b9b5ab",
  concreteFill: "rgba(180, 180, 180, 0.55)",
  concreteEdge: "#14181d",
  // v2 faces (ADR 0039; render/style.py, C5-S1): steel cut on Grey128, a void in the paper
  // colour so it takes away what it cuts, both edged like concrete.
  steelFill: "#808080",
  steelEdge: "#14181d",
  voidFill: "#f7f6f3",
  voidEdge: "#14181d",
  legAxis: "#6e757c",
  coverRing: "#808080",
  centreRing: "#97a1ad",
  rebar: "#000077",
  hoop: "#000077",
  crosstie: "#000077",
  circularTie: "#000077",
  barSelectedEdge: "#ffffff",
  selected: "#2f74ad",
  selectedFill: "rgba(47, 116, 173, 0.24)",
  ghost: "#2f74ad",
  ghostFill: "rgba(47, 116, 173, 0.14)",
  snap: "#c64a1a",
  warn: "#c64a1a",
  // C8b (RGc3 F7): the axes and origin glyph, in the render's annotation blue (ADR-004).
  originGlyph: "#000077",
};

// The ADR 0031 roles an overlay colour may name (spec section-overlay "Colours"), at their
// light-theme value in `static/css/app.css`: the fallback when the host page does not define
// the role. `apeCAD.render.overlay.COLOR_TOKENS` holds the same table (a test keeps them equal).
export const OVERLAY_TOKENS = Object.freeze({
  "--text": "#1c2127",
  "--muted": "#4a525c",
  "--accent": "#2f74ad",
  "--signal": "#c64a1a",
  "--ink-edge": "#14181d",
  "--ink-rebar": "#000077",
  "--ink-concrete": "#000000",
  "--ink-section-guide": "#808080",
  "--fill-concrete": "#b4b4b4",
});

// Example overlay scales for hosts (ADR 0041). Each passes the ADR 0038 contrast and CVD
// gates on this canvas (`tests/js/section-overlay.test.mjs`). Red against green does not:
// it is under 0.055 OKLab apart for a deuteranope.
export const OVERLAY_EXAMPLE_SCALES = Object.freeze({
  stress: { kind: "diverging", domain: [-30, 0, 420], colors: ["#2166ac", "#f7f7f7", "#b2182b"], unit: "MPa", title: "Stress" },
  strain: { kind: "sequential", domain: [0, 0.003], colors: ["#6baed6", "#2171b5", "#08306b"], unit: "", title: "Strain" },
  bar_state: { kind: "categorical", domain: ["elastic", "yielded", "fractured"], colors: ["#2f74ad", "#c64a1a", "#14181d"], unit: "", title: "Bar state" },
});

// The scene is painted from its display list, layer by layer; a click hits by role.
export { pointInPolygon, sceneBoundsMm };

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
  return scene ? hitTestDisplay(screenPt, view, displayList(scene), aperturePx) : null;
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

function traceLoop(ctx, view, loop) {
  if (loop.ring) { traceRing(ctx, view, loop.ring); return; }
  const [sx, sy] = view.worldToScreen(loop.centre);
  const r = loop.radius * view.scale;
  ctx.moveTo(sx + r, sy);
  ctx.arc(sx, sy, r, 0, Math.PI * 2);
  ctx.closePath();
}

function strokeSegment(ctx, view, [s, e]) {
  const [x0, y0] = view.worldToScreen(s), [x1, y1] = view.worldToScreen(e);
  ctx.beginPath();
  ctx.moveTo(x0, y0);
  ctx.lineTo(x1, y1);
  ctx.stroke();
}

function strokeRing(ctx, view, ring) {
  ctx.beginPath();
  traceRing(ctx, view, ring);
  ctx.stroke();
}

function strokeCircle(ctx, view, circle) {
  ctx.beginPath();
  traceLoop(ctx, view, circle);
  ctx.stroke();
}

const FACE_FILL = { concrete: "concreteFill", steel: "steelFill", void: "voidFill" };
const FACE_EDGE = { concrete: "concreteEdge", steel: "steelEdge", void: "voidEdge" };

// One face: its boundary and holes are one path filled even-odd, so a hole stays open
// whatever its ring's orientation (ADR 0039; C5 record invariant 4). A void is painted in
// the paper colour, so it takes away what it cuts.
function paintFace(ctx, view, e, sel) {
  ctx.beginPath();
  for (const loop of e.loops) traceLoop(ctx, view, loop);
  if (!sel || e.layer === "void") {
    ctx.fillStyle = PALETTE[FACE_FILL[e.layer]];
    ctx.fill("evenodd");
  }
  if (sel) {
    ctx.fillStyle = PALETTE.selectedFill;
    ctx.fill("evenodd");
  }
  ctx.strokeStyle = sel ? PALETTE.selected : PALETTE[FACE_EDGE[e.layer]];
  ctx.lineWidth = sel ? 2.2 : 1.5;
  ctx.stroke();
}

// One display-list entry on its layer (`display2d.js::SECTION_LAYERS`).
function paintEntry(ctx, view, e, sel) {
  const d = e.item.diameter_mm || 10;
  if (e.loops) {
    paintFace(ctx, view, e, sel);
  } else if (e.layer === "cover") {
    ctx.save();
    ctx.setLineDash([6, 4]);
    ctx.strokeStyle = sel ? PALETTE.selected : PALETTE.coverRing;
    ctx.lineWidth = sel ? 1.8 : 1.1;
    strokeRing(ctx, view, e.rings[0]);
    ctx.restore();
    if (e.centreRing) {
      ctx.save();
      ctx.setLineDash([2, 4]);
      ctx.strokeStyle = PALETTE.centreRing;
      ctx.lineWidth = 1;
      strokeRing(ctx, view, e.centreRing);
      ctx.restore();
    }
  } else if (e.layer === "leg") { // dash-dot centreline
    ctx.save();
    ctx.setLineDash([10, 4, 2, 4]);
    ctx.strokeStyle = sel ? PALETTE.selected : PALETTE.legAxis;
    ctx.lineWidth = sel ? 2 : 1.2;
    strokeSegment(ctx, view, e.segment);
    ctx.restore();
  } else if (e.layer === "hoop") {
    ctx.strokeStyle = sel ? PALETTE.selected : PALETTE.hoop;
    ctx.lineWidth = Math.max(sel ? 2.4 : 1.6, d * view.scale * 0.6);
    strokeRing(ctx, view, e.rings[0]);
  } else if (e.layer === "crosstie") {
    ctx.strokeStyle = sel ? PALETTE.selected : PALETTE.crosstie;
    ctx.lineWidth = Math.max(sel ? 2.4 : 1.5, d * view.scale * 0.55);
    strokeSegment(ctx, view, e.segment);
  } else if (e.layer === "circular-tie") { // the centreline, the hoop's pen
    ctx.strokeStyle = sel ? PALETTE.selected : PALETTE.circularTie;
    ctx.lineWidth = Math.max(sel ? 2.4 : 1.6, d * view.scale * 0.6);
    strokeCircle(ctx, view, e.circle);
  } else if (e.layer === "bar") {
    const [sx, sy] = view.worldToScreen(e.disc.centre);
    ctx.beginPath();
    ctx.arc(sx, sy, Math.max(3.5, e.disc.radius * view.scale), 0, Math.PI * 2);
    ctx.fillStyle = sel ? PALETTE.selected : PALETTE.rebar;
    ctx.fill();
    if (sel) {
      ctx.strokeStyle = PALETTE.barSelectedEdge;
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }
  }
}

function drawSelectionOutline(ctx, view, display, selectedIds) {
  ctx.save();
  ctx.strokeStyle = PALETTE.selected;
  for (const e of display.entries) {
    if (!selectedIds.has(e.id)) continue;
    if (e.loops) {
      ctx.lineWidth = 2.2;
      ctx.beginPath();
      for (const loop of e.loops) traceLoop(ctx, view, loop);
      ctx.stroke();
    } else if (e.rings) {
      ctx.lineWidth = e.layer === "cover" ? 1.8 : 2.4;
      strokeRing(ctx, view, e.rings[0]);
    } else if (e.segment) {
      ctx.lineWidth = e.layer === "leg" ? 2 : 2.4;
      strokeSegment(ctx, view, e.segment);
    } else if (e.circle) {
      ctx.lineWidth = 2.4;
      strokeCircle(ctx, view, e.circle);
    } else if (e.disc) {
      const [sx, sy] = view.worldToScreen(e.disc.centre);
      ctx.beginPath();
      ctx.arc(sx, sy, Math.max(3.5, e.disc.radius * view.scale), 0, Math.PI * 2);
      ctx.fillStyle = PALETTE.selected;
      ctx.fill();
    }
  }
  ctx.restore();
}

// --- legibility over an overlay, and the axes glyph (C8b; RGc3 F6, F7; `render/svg.py`) ----

export const HALO_PX = 1; // the paper each side of an ink line over an overlay
export const AXES_ARM_PX = 18;
const INK_ROLE = { hoop: "hoop", crosstie: "crosstie", "circular-tie": "circularTie" };

// One entry's linework over an overlay: its outline, hoop, tie or bar ring, unselected pens.
// The halo pass is the same line `HALO_PX` wider each side in the paper colour; a bar's halo
// sits just outside its ring, so the overlay's colour stays visible inside the bar.
function strokeInk(ctx, view, e, halo) {
  const d = e.item.diameter_mm || 10, extra = halo ? 2 * HALO_PX : 0;
  const role = e.loops ? FACE_EDGE[e.layer] : e.layer === "bar" ? "rebar" : INK_ROLE[e.layer];
  ctx.strokeStyle = halo ? PALETTE.bg : PALETTE[role];
  if (e.loops) {
    ctx.lineWidth = 1.5 + extra;
    ctx.beginPath();
    for (const loop of e.loops) traceLoop(ctx, view, loop);
    ctx.stroke();
  } else if (e.layer === "hoop") {
    ctx.lineWidth = Math.max(1.6, d * view.scale * 0.6) + extra;
    strokeRing(ctx, view, e.rings[0]);
  } else if (e.layer === "crosstie") {
    ctx.lineWidth = Math.max(1.5, d * view.scale * 0.55) + extra;
    strokeSegment(ctx, view, e.segment);
  } else if (e.layer === "circular-tie") {
    ctx.lineWidth = Math.max(1.6, d * view.scale * 0.6) + extra;
    strokeCircle(ctx, view, e.circle);
  } else if (e.layer === "bar") {
    const [sx, sy] = view.worldToScreen(e.disc.centre), r = Math.max(3.5, e.disc.radius * view.scale);
    ctx.lineWidth = halo ? HALO_PX : 1;
    ctx.beginPath();
    ctx.arc(sx, sy, halo ? r + (1 + HALO_PX) / 2 : r, 0, Math.PI * 2);
    ctx.stroke();
  }
}

/** The section's linework again, over an overlay: all halos first, then all ink. */
export function paintInk(ctx, view, display) {
  const inked = display.entries.filter((e) => e.loops || INK_ROLE[e.layer] || e.layer === "bar");
  ctx.save();
  ctx.setLineDash([]);
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  for (const halo of [true, false]) for (const e of inked) strokeInk(ctx, view, e, halo);
  ctx.restore();
}

/** The world origin and its axes, x right and y up (apeSection ADR-0006): a fixed size on
 * screen, on a paper halo, drawn on every frame. Strokes and text only; it computes nothing. */
export function paintAxes(ctx, view) {
  const [ox, oy] = view.worldToScreen([0, 0]);
  const head = 5, half = 3, xe = ox + AXES_ARM_PX, ye = oy - AXES_ARM_PX;
  ctx.save();
  ctx.setLineDash([]);
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.beginPath();
  ctx.moveTo(ox - 2.5, oy - 2.5); ctx.lineTo(ox + 2.5, oy - 2.5); ctx.lineTo(ox + 2.5, oy + 2.5); ctx.lineTo(ox - 2.5, oy + 2.5); ctx.closePath();
  ctx.moveTo(ox, oy); ctx.lineTo(xe, oy);
  ctx.moveTo(xe - head, oy - half); ctx.lineTo(xe, oy); ctx.lineTo(xe - head, oy + half);
  ctx.moveTo(ox, oy); ctx.lineTo(ox, ye);
  ctx.moveTo(ox - half, ye + head); ctx.lineTo(ox, ye); ctx.lineTo(ox + half, ye + head);
  ctx.strokeStyle = PALETTE.bg;
  ctx.lineWidth = 1 + 2 * HALO_PX;
  ctx.stroke();
  ctx.strokeStyle = PALETTE.originGlyph;
  ctx.lineWidth = 1;
  ctx.stroke();
  if (typeof ctx.fillText === "function") {
    ctx.font = "11px \"Archivo Narrow\", \"Arial Narrow\", sans-serif";
    for (const [text, x, y] of [["x", xe + 3, oy + 3.5], ["y", ox + 5, ye + 6]]) {
      if (typeof ctx.strokeText === "function") {
        ctx.strokeStyle = PALETTE.bg;
        ctx.lineWidth = 3;
        ctx.strokeText(text, x, y);
      }
      ctx.fillStyle = PALETTE.originGlyph;
      ctx.fillText(text, x, y);
    }
  }
  ctx.restore();
}

export function renderSectionCanvas(canvas, view, state) {
  const ctx = canvas && typeof canvas.getContext === "function" ? canvas.getContext("2d") : null;
  if (!ctx) return;
  const { scene, selectedIds = new Set(), snap = null, ghost = null, gridOn = true, gridStepMm = 50 } = state || {};

  ctx.save();
  ctx.fillStyle = PALETTE.bg;
  ctx.fillRect(0, 0, view.width, view.height);
  if (gridOn) drawGrid(ctx, view, gridStepMm);

  // 1-6. The section, layer by layer, back to front: concrete, steel, void, cover, leg, hoop,
  // crosstie, circular tie, bar (C5 record §3). Role decides overlap, never the id.
  const display = displayList(scene);
  for (const e of display.entries) paintEntry(ctx, view, e, selectedIds.has(e.id));

  // 6b. The results overlay sits above the section and below the selection (ADR 0041 D2).
  // Over its fields, the section's linework is stroked again on a paper halo (C8b, RGc3 F6),
  // then the overlay's valued markers (`drawMarkers`: nothing covers a bar's status colour),
  // the host's glyphs, the axes and origin glyph (F7), and the selection on top.
  const overlaid = Boolean(scene) && typeof state?.drawOverlay === "function";
  if (overlaid) {
    state.drawOverlay(ctx, view);
    paintInk(ctx, view, display);
    if (typeof state.drawMarkers === "function") state.drawMarkers(ctx, view);
  }
  const glyphs = Boolean(scene) && typeof state?.drawGlyphs === "function";
  if (glyphs) state.drawGlyphs(ctx, view);
  paintAxes(ctx, view);
  if ((overlaid || glyphs) && selectedIds.size) drawSelectionOutline(ctx, view, display, selectedIds);

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
