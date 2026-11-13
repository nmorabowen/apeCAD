// The glyphs a host supplies to the section client (client API 4, C8a), extracted from
// `apecad-section.js` (C8b) so that file stays under its 600-line limit (ADR 0023).
// Pure: no DOM, no module-scope state.

import { PALETTE } from "./canvas2d.js";

// API 4: the glyphs a host supplies (C8a: `centroid_mm`, a world point the host computed; the
// client never computes it). A refusal names the key and replaces what was shown, as an overlay's does.
export function parseGlyphs(value) {
  const refuse = (path, message) => ({ ok: false, status: 422, error: { code: "INVALID_ARGUMENT", path, message } });
  if (value == null) return { ok: true, glyphs: { centroid_mm: null } };
  if (typeof value !== "object" || Array.isArray(value)) return refuse("glyphs", "glyphs must be an object or null");
  const unknown = Object.keys(value).find((k) => k !== "centroid_mm");
  if (unknown !== undefined) return refuse(`glyphs.${unknown}`, `unknown glyph "${unknown}", expected centroid_mm`);
  const c = value.centroid_mm ?? null; // Array.from: a hole becomes undefined, which `every` would skip
  if (c !== null && !(Array.isArray(c) && c.length === 2 && Array.from(c).every((v) => typeof v === "number" && Number.isFinite(v)))) {
    return refuse("glyphs.centroid_mm", "centroid_mm must be [x, y] in finite millimetres, or null");
  }
  return { ok: true, glyphs: { centroid_mm: c && [c[0], c[1]] } };
}

// The centroid symbol: a circle quartered by a cross, a fixed size on screen, at its world point.
export function paintCentroid(ctx, view, point) {
  const [x, y] = view.worldToScreen(point), r = 6, arm = 10;
  ctx.save(); ctx.strokeStyle = PALETTE.concreteEdge; ctx.lineWidth = 1.25;
  ctx.beginPath(); ctx.arc(x, y, r, 0, 2 * Math.PI);
  ctx.moveTo(x - arm, y); ctx.lineTo(x + arm, y); ctx.moveTo(x, y - arm); ctx.lineTo(x, y + arm);
  ctx.stroke(); ctx.restore();
}
