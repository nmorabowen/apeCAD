// The results overlay of the section client: read `apeCAD.section-overlay` v1, paint it, and
// show its layers, legends and staleness (ADR 0041 decision 2; spec `section-overlay.md`).
// `parseOverlay` mirrors `apeCAD.render.overlay.parse_overlay` and must refuse every case of
// `tests/fixtures/section_overlay/` with the same code and path. Overlay text is never HTML:
// it reaches the page through `textContent` and the canvas through `fillText` only.
// Zero external dependencies; no module-scope DOM access.

import { OVERLAY_TOKENS } from "./canvas2d.js";

export const OVERLAY_SCHEMA = "apeCAD.section-overlay";
export const OVERLAY_SCHEMA_VERSION = 1;
export const MAX_OVERLAY_PRIMITIVES = 200000;
export const SCALE_KINDS = ["sequential", "diverging", "categorical"];
export const PRIMITIVE_KINDS = ["polygon", "circle", "polyline", "point", "label"];
export const STALE_ALPHA = 0.35;
const VALUE_STROKE_PX = 1.5;
const POINT_RADIUS_PX = 2.5;
const INVALID_ARGUMENT = "INVALID_ARGUMENT";
const TOO_LARGE = "TOO_LARGE";
const HEX = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;
const TOKEN_NAMES = new Set(Object.keys(OVERLAY_TOKENS));

const PAINTS = { polygon: ["fill", "stroke"], circle: ["fill", "stroke"], polyline: ["stroke"], point: ["fill"], label: ["fill"] };
const SHAPE_KEYS = { polygon: ["ring", "holes"], circle: ["center", "radius"], polyline: ["points"], point: ["at"], label: ["at", "text"] };
const REQUIRED_SHAPE_KEYS = { ...SHAPE_KEYS, polygon: ["ring"] };
const PRIMITIVE_KEYS = ["kind", "style", "value", "ids"];

/** An overlay the contract refuses: `code` and the exact `path` of the refused field. */
export class OverlayError extends Error {
  constructor(path, text, code = INVALID_ARGUMENT) {
    super(`${path} ${text}`);
    this.name = "OverlayError";
    this.path = path;
    this.code = code;
  }
}

const show = (v) => {
  try {
    const s = JSON.stringify(v);
    return s === undefined ? String(v) : s.length > 40 ? `a value of ${s.length} chars` : s;
  } catch {
    return typeof v;
  }
};
const typeName = (v) => (v === null ? "null" : Array.isArray(v) ? "list" : typeof v);
const isObject = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
const has = (obj, key) => Object.prototype.hasOwnProperty.call(obj, key);

// Python's `sorted` orders strings by code point; JS's default sort by UTF-16 unit.
function byCodePoint(a, b) {
  const x = Array.from(a, (c) => c.codePointAt(0)), y = Array.from(b, (c) => c.codePointAt(0));
  for (let i = 0; i < Math.min(x.length, y.length); i++) if (x[i] !== y[i]) return x[i] - y[i];
  return x.length - y.length;
}

// --- field readers (mirror `render/overlay.py`) -------------------------------------------

function readObject(path, value, allowed, required = allowed) {
  if (!isObject(value)) throw new OverlayError(path, `must be an object, got ${typeName(value)}`);
  const keys = Object.keys(value);
  const extra = keys.filter((k) => !allowed.includes(k)).sort(byCodePoint);
  if (extra.length) throw new OverlayError(`${path}.${extra[0]}`, "is an unknown key");
  const missing = required.filter((k) => !has(value, k)).sort(byCodePoint);
  if (missing.length) throw new OverlayError(`${path}.${missing[0]}`, "is missing");
  return value;
}

// A dense copy: a hole in a sparse array reads as `undefined` and is refused at its own path,
// as Python refuses `null` there (`.map` would skip it and store the hole).
function readList(path, value) {
  if (!Array.isArray(value)) throw new OverlayError(path, `must be a list, got ${typeName(value)}`);
  return Array.from(value);
}

function readStr(path, value) {
  if (typeof value !== "string") throw new OverlayError(path, `must be a string, got ${show(value)}`);
  return value;
}

// An integer by value (spec "Integers"): `1.0` is 1; `-0` normalises to 0.
function integral(value) {
  return typeof value === "number" && Number.isInteger(value) ? value + 0 : null;
}

function readInt(path, value) {
  const whole = integral(value);
  if (whole === null || whole < 0) {
    throw new OverlayError(path, `must be a finite non-negative integer, got ${show(value)}`);
  }
  return whole;
}

function readNumber(path, value) {
  if (typeof value !== "number") throw new OverlayError(path, `must be a number, got ${show(value)}`);
  if (!Number.isFinite(value)) throw new OverlayError(path, `must be finite, got ${value}`);
  return value;
}

function readXY(path, value) {
  const items = readList(path, value);
  if (items.length !== 2) throw new OverlayError(path, `must be [x, y] in mm, got ${items.length} values`);
  return [readNumber(`${path}[0]`, items[0]), readNumber(`${path}[1]`, items[1])];
}

function readPoints(path, value, least) {
  const points = readList(path, value).map((p, i) => readXY(`${path}[${i}]`, p));
  if (points.length < least) throw new OverlayError(path, `needs at least ${least} points, got ${points.length}`);
  return points;
}

/** Lower-case `#rrggbb` for a hex colour, the token name for a known token, else null. */
export function normalizeColor(value) {
  if (typeof value !== "string") return null;
  if (TOKEN_NAMES.has(value)) return value;
  if (!HEX.test(value)) return null;
  const digits = value.slice(1).toLowerCase();
  return `#${digits.length === 3 ? digits.split("").map((c) => c + c).join("") : digits}`;
}

function readColor(path, value) {
  if (typeof value !== "string") throw new OverlayError(path, `must be a colour string, got ${show(value)}`);
  const color = normalizeColor(value);
  if (color === null) {
    throw new OverlayError(path, `must be #rgb, #rrggbb or a design token (${[...TOKEN_NAMES].join(", ")}), got ${show(value)}`);
  }
  return color;
}

// --- reading ------------------------------------------------------------------------------

/** The overlay, validated and copied, or an `OverlayError` naming what it refuses. */
export function parseOverlay(value) {
  const top = readObject("overlay", value, ["schema", "version", "units", "revision", "layers"]);
  if (top.schema !== OVERLAY_SCHEMA) throw new OverlayError("overlay.schema", `must be "${OVERLAY_SCHEMA}", got ${show(top.schema)}`);
  if (integral(top.version) !== OVERLAY_SCHEMA_VERSION) {
    throw new OverlayError("overlay.version", `must be ${OVERLAY_SCHEMA_VERSION}, got ${show(top.version)}`);
  }
  if (top.units !== "mm") throw new OverlayError("overlay.units", `must be "mm", got ${show(top.units)}`);
  const revision = readInt("overlay.revision", top.revision);
  const shells = readList("overlay.layers", top.layers).map((item, i) =>
    readObject(`overlay.layers[${i}]`, item, ["id", "label", "visible", "scale", "primitives"]));
  const rawPrimitives = shells.map((shell, i) => readList(`overlay.layers[${i}].primitives`, shell.primitives));
  const total = rawPrimitives.reduce((n, items) => n + items.length, 0);
  if (total > MAX_OVERLAY_PRIMITIVES) {
    throw new OverlayError("overlay.layers", `hold ${total} primitives, more than MAX_OVERLAY_PRIMITIVES (${MAX_OVERLAY_PRIMITIVES}); the overlay is refused, never truncated`, TOO_LARGE);
  }
  const seen = new Set();
  const layers = shells.map((shell, i) => readLayer(`overlay.layers[${i}]`, shell, rawPrimitives[i], seen));
  return { revision, layers, primitiveCount: total };
}

function readLayer(path, shell, items, seen) {
  const id = readStr(`${path}.id`, shell.id);
  if (!id) throw new OverlayError(`${path}.id`, "must not be empty");
  if (seen.has(id)) throw new OverlayError(`${path}.id`, `${show(id)} is used by another layer`);
  seen.add(id);
  const label = readStr(`${path}.label`, shell.label);
  if (typeof shell.visible !== "boolean") throw new OverlayError(`${path}.visible`, `must be true or false, got ${show(shell.visible)}`);
  const scale = shell.scale === null ? null : readScale(`${path}.scale`, shell.scale);
  const primitives = items.map((item, j) => readPrimitive(`${path}.primitives[${j}]`, item, scale));
  return { id, label, visible: shell.visible, scale, primitives };
}

function readScale(path, value) {
  const raw = readObject(path, value, ["kind", "domain", "colors", "unit", "title"]);
  const kind = raw.kind;
  if (typeof kind !== "string" || !SCALE_KINDS.includes(kind)) {
    throw new OverlayError(`${path}.kind`, `must be one of ${SCALE_KINDS.join(", ")}, got ${show(kind)}`);
  }
  const colors = readList(`${path}.colors`, raw.colors).map((c, i) => readColor(`${path}.colors[${i}]`, c));
  if (colors.length < 2) throw new OverlayError(`${path}.colors`, `needs at least 2 colours, got ${colors.length}`);
  const items = readList(`${path}.domain`, raw.domain);
  let domain;
  if (kind === "categorical") {
    domain = items.map((c, i) => readStr(`${path}.domain[${i}]`, c));
    domain.forEach((name, i) => {
      if (domain.slice(0, i).includes(name)) throw new OverlayError(`${path}.domain[${i}]`, `repeats the category ${show(name)}`);
    });
    if (domain.length !== colors.length) {
      throw new OverlayError(`${path}.colors`, `needs one colour per category: ${domain.length} categories, ${colors.length} colours`);
    }
  } else {
    domain = items.map((c, i) => readNumber(`${path}.domain[${i}]`, c));
    const want = kind === "sequential" ? 2 : 3;
    if (domain.length !== want) throw new OverlayError(`${path}.domain`, `of a ${kind} scale needs ${want} numbers`);
    if (domain.some((a, i) => i + 1 < domain.length && a >= domain[i + 1])) {
      throw new OverlayError(`${path}.domain`, `must increase strictly, got ${show(domain)}`);
    }
    if (!Number.isFinite(domain[domain.length - 1] - domain[0])) {
      throw new OverlayError(`${path}.domain`, `must span a finite range, got ${show(domain)}`);
    }
    if (kind === "diverging" && colors.length % 2 === 0) {
      throw new OverlayError(`${path}.colors`, `of a diverging scale must be an odd number, at least 3, got ${colors.length}`);
    }
  }
  const unit = readStr(`${path}.unit`, raw.unit);
  return { kind, domain, colors, unit, title: readStr(`${path}.title`, raw.title) };
}

function readPrimitive(path, value, scale) {
  if (!isObject(value)) throw new OverlayError(path, `must be an object, got ${typeName(value)}`);
  const kind = has(value, "kind") ? value.kind : undefined;
  if (typeof kind !== "string" || !PRIMITIVE_KINDS.includes(kind)) {
    throw new OverlayError(`${path}.kind`, `must be one of ${PRIMITIVE_KINDS.join(", ")}, got ${show(kind)}`);
  }
  const raw = readObject(path, value, [...SHAPE_KEYS[kind], ...PRIMITIVE_KEYS], [...REQUIRED_SHAPE_KEYS[kind], "kind"]);
  const hasStyle = has(raw, "style"), hasValue = has(raw, "value");
  if (hasStyle === hasValue) throw new OverlayError(path, "must carry exactly one of style or value");
  const out = { kind, points: [], holes: [], radius: 0, text: "", style: null, value: null, ids: [] };
  if (kind === "polygon") {
    out.points = readPoints(`${path}.ring`, raw.ring, 3);
    if (has(raw, "holes")) out.holes = readList(`${path}.holes`, raw.holes).map((h, i) => readPoints(`${path}.holes[${i}]`, h, 3));
  } else if (kind === "circle") {
    out.points = [readXY(`${path}.center`, raw.center)];
    out.radius = readNumber(`${path}.radius`, raw.radius);
    if (out.radius <= 0) throw new OverlayError(`${path}.radius`, `must be positive, got ${out.radius}`);
  } else if (kind === "polyline") {
    out.points = readPoints(`${path}.points`, raw.points, 2);
  } else {
    out.points = [readXY(`${path}.at`, raw.at)];
    if (kind === "label") out.text = readStr(`${path}.text`, raw.text);
  }
  if (has(raw, "ids")) out.ids = readList(`${path}.ids`, raw.ids).map((v, i) => readInt(`${path}.ids[${i}]`, v));
  if (hasStyle) out.style = readStyle(`${path}.style`, raw.style, kind);
  else out.value = readValue(`${path}.value`, raw.value, scale);
  return out;
}

function readStyle(path, value, kind) {
  const raw = readObject(path, value, ["stroke", "fill", "width_px", "opacity"], []);
  for (const key of ["fill", "stroke"]) {
    if (has(raw, key) && !PAINTS[kind].includes(key)) throw new OverlayError(`${path}.${key}`, `is not taken by a ${kind}`);
  }
  const fill = raw.fill == null ? null : readColor(`${path}.fill`, raw.fill);
  const stroke = raw.stroke == null ? null : readColor(`${path}.stroke`, raw.stroke);
  if (fill === null && stroke === null) {
    throw new OverlayError(path, `paints nothing: give a ${[...PAINTS[kind]].sort().join(" or ")}`);
  }
  const width = has(raw, "width_px") ? readNumber(`${path}.width_px`, raw.width_px) : 1;
  if (width <= 0) throw new OverlayError(`${path}.width_px`, `must be positive, got ${width}`);
  const opacity = has(raw, "opacity") ? readNumber(`${path}.opacity`, raw.opacity) : 1;
  if (!(opacity >= 0 && opacity <= 1)) throw new OverlayError(`${path}.opacity`, `must be between 0 and 1, got ${opacity}`);
  return { fill, stroke, width_px: width, opacity };
}

function readValue(path, value, scale) {
  if (scale === null) throw new OverlayError(path, "needs a layer scale");
  if (scale.kind === "categorical") {
    if (typeof value !== "string") throw new OverlayError(path, `must be a category of a categorical scale, got ${show(value)}`);
    if (!scale.domain.includes(value)) throw new OverlayError(path, `${show(value)} is not a category of the layer scale`);
    return value;
  }
  if (typeof value === "string") throw new OverlayError(path, `must be a number on a ${scale.kind} scale, got ${show(value)}`);
  return readNumber(path, value);
}

// --- colour (spec "Scales") ----------------------------------------------------------------

/** Resolve a normalised colour: a token through `tokens` (default: the light theme). */
export function resolveColor(color, tokens = OVERLAY_TOKENS) {
  return TOKEN_NAMES.has(color) ? tokens[color] || OVERLAY_TOKENS[color] : color;
}

/** Where each colour sits on a numeric scale's domain. */
export function scaleStops(scale) {
  const n = scale.colors.length;
  if (scale.kind === "sequential") {
    const [lo, hi] = scale.domain;
    return scale.colors.map((_, i) => lo + ((hi - lo) * i) / (n - 1));
  }
  const [lo, mid, hi] = scale.domain;
  const k = (n - 1) / 2;
  const left = [];
  for (let i = 0; i < k; i++) left.push(lo + ((mid - lo) * i) / k);
  for (let j = 0; j <= k; j++) left.push(mid + ((hi - mid) * j) / k);
  return left;
}

function mix(c0, c1, t) {
  let out = "#";
  for (const k of [1, 3, 5]) {
    const p = Number.parseInt(c0.slice(k, k + 2), 16), q = Number.parseInt(c1.slice(k, k + 2), 16);
    out += Math.floor(p + (q - p) * t + 0.5).toString(16).padStart(2, "0");
  }
  return out;
}

/** The `#rrggbb` a value takes on a parsed scale: clamped, 8-bit sRGB, no gamma. */
export function scaleColor(scale, value, tokens = OVERLAY_TOKENS) {
  const colors = scale.colors.map((c) => resolveColor(c, tokens));
  if (scale.kind === "categorical") {
    const i = scale.domain.indexOf(value);
    if (i < 0) throw new OverlayError("value", `${show(value)} is not a category of the layer scale`);
    return colors[i];
  }
  const stops = scaleStops(scale);
  if (value <= stops[0]) return colors[0];
  if (value >= stops[stops.length - 1]) return colors[colors.length - 1];
  let i = 0;
  for (let j = 0; j < stops.length - 1; j++) if (stops[j] <= value) i = j;
  return mix(colors[i], colors[i + 1], (value - stops[i]) / (stops[i + 1] - stops[i]));
}

// --- painting ------------------------------------------------------------------------------

function paintOf(p, scale, tokens) {
  if (p.style) {
    const { fill, stroke, width_px, opacity } = p.style;
    return { fill: fill && resolveColor(fill, tokens), stroke: stroke && resolveColor(stroke, tokens), width: width_px, opacity };
  }
  const color = scaleColor(scale, p.value, tokens);
  return p.kind === "polyline"
    ? { fill: null, stroke: color, width: VALUE_STROKE_PX, opacity: 1 }
    : { fill: color, stroke: null, width: 1, opacity: 1 };
}

function tracePath(ctx, view, pts, closed) {
  pts.forEach((pt, i) => {
    const [x, y] = view.worldToScreen(pt);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  if (closed) ctx.closePath();
}

/** Paint the visible layers in order; a stale overlay is dimmed, never hidden. */
export function paintOverlay(ctx, view, overlay, { stale = false, tokens = OVERLAY_TOKENS } = {}) {
  if (!ctx || !overlay) return;
  const dim = stale ? STALE_ALPHA : 1;
  for (const layer of overlay.layers) {
    if (!layer.visible) continue;
    for (const p of layer.primitives) {
      const paint = paintOf(p, layer.scale, tokens);
      ctx.save();
      ctx.globalAlpha = paint.opacity * dim;
      ctx.lineWidth = paint.width;
      ctx.beginPath();
      const [sx, sy] = view.worldToScreen(p.points[0]);
      if (p.kind === "polygon") {
        for (const ring of [p.points, ...p.holes]) tracePath(ctx, view, ring, true);
      } else if (p.kind === "polyline") {
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        tracePath(ctx, view, p.points, false);
      } else if (p.kind === "circle" || p.kind === "point") {
        ctx.arc(sx, sy, p.kind === "circle" ? p.radius * view.scale : POINT_RADIUS_PX, 0, Math.PI * 2);
      }
      if (p.kind === "label") {
        ctx.font = "12px \"Archivo Narrow\", \"Arial Narrow\", sans-serif";
        ctx.fillStyle = paint.fill;
        if (typeof ctx.fillText === "function") ctx.fillText(p.text, sx, sy);
      } else {
        if (paint.fill) { ctx.fillStyle = paint.fill; ctx.fill("evenodd"); }
        if (paint.stroke) { ctx.strokeStyle = paint.stroke; ctx.stroke(); }
      }
      ctx.restore();
    }
  }
}

// --- the panel: layer list, legends and the stale badge -----------------------------------

const tick = (v) => String(Number(v.toPrecision(6)));

function legendNode(doc, el, layer, tokens) {
  const { scale } = layer;
  const box = el(doc, "div", "apecad-section-legend");
  box.dataset.layer = layer.id;
  box.appendChild(el(doc, "div", "apecad-section-legend-title", scale.unit ? `${scale.title} (${scale.unit})` : scale.title));
  const colors = scale.colors.map((c) => resolveColor(c, tokens));
  if (scale.kind === "categorical") {
    scale.domain.forEach((name, i) => {
      const row = el(doc, "div", "apecad-section-legend-row");
      const swatch = el(doc, "span", "apecad-section-legend-swatch");
      swatch.style.background = colors[i];
      row.appendChild(swatch);
      row.appendChild(el(doc, "span", "apecad-section-legend-name", name));
      box.appendChild(row);
    });
    return box;
  }
  const stops = scaleStops(scale), lo = stops[0], span = stops[stops.length - 1] - lo;
  const bar = el(doc, "div", "apecad-section-legend-bar");
  bar.style.background = `linear-gradient(to right, ${colors.map((c, i) => `${c} ${tick(((stops[i] - lo) / span) * 100)}%`).join(", ")})`;
  box.appendChild(bar);
  const ticks = el(doc, "div", "apecad-section-legend-ticks");
  for (const v of scale.kind === "diverging" ? scale.domain : [scale.domain[0], scale.domain[1]]) {
    ticks.appendChild(el(doc, "span", "apecad-section-legend-tick", tick(v)));
  }
  box.appendChild(ticks);
  return box;
}

/**
 * The overlay state of one editor. `getRevision()` is the live document revision; `onChange`
 * redraws. Everything it writes to the page goes through `el(...)`, which sets `textContent`.
 * Tokens resolve to their light values: the client canvas is light-only (`PALETTE.bg`), so a
 * dark host's `--text` would vanish on it.
 */
export function createOverlayController({ doc, el, box, getRevision, onChange }) {
  let overlay = null;
  let refusal = null;
  let generation = 0; // bumped by every set; the panel is rebuilt only when it or staleness moves
  let shown = "";
  // Any other revision is stale: behind it the document moved on; ahead of it the overlay was
  // stamped for a document this client has not seen.
  const isStale = () => overlay !== null && getRevision() !== overlay.revision;
  const tokens = () => OVERLAY_TOKENS;

  function state() {
    return {
      active: overlay !== null,
      revision: getRevision(),
      overlay_revision: overlay ? overlay.revision : null,
      stale: isStale(),
      primitive_count: overlay ? overlay.primitiveCount : 0,
      layers: overlay ? overlay.layers.map((l) => ({ id: l.id, label: l.label, visible: l.visible, primitives: l.primitives.length, scale: l.scale ? l.scale.kind : null })) : [],
      refusal: refusal ? { ...refusal } : null,
    };
  }

  function refresh() {
    if (!box || typeof box.replaceChildren !== "function") return;
    const key = `${generation}:${isStale()}`;
    if (key === shown) return;
    shown = key;
    box.classList?.toggle?.("stale", isStale());
    if (!overlay && !refusal) { box.replaceChildren(); return; }
    const nodes = [];
    if (refusal) nodes.push(el(doc, "div", "apecad-section-overlay-refused", `Overlay refused: ${refusal.message}`));
    if (overlay) {
      const head = el(doc, "div", "apecad-section-overlay-head", `Overlay · revision ${overlay.revision}`);
      if (isStale()) head.appendChild(el(doc, "span", "apecad-section-overlay-stale", "stale"));
      nodes.push(head);
      const table = tokens();
      for (const layer of overlay.layers) {
        nodes.push(el(doc, "div", `apecad-section-overlay-layer${layer.visible ? "" : " hidden"}`, layer.visible ? layer.label : `${layer.label} (hidden)`));
      }
      for (const layer of overlay.layers) if (layer.visible && layer.scale) nodes.push(legendNode(doc, el, layer, table));
    }
    box.replaceChildren(...nodes);
  }

  function set(value) {
    generation += 1;
    if (value === null || value === undefined) {
      overlay = null;
      refusal = null;
    } else {
      try {
        overlay = parseOverlay(value);
        refusal = null;
      } catch (err) {
        if (!(err instanceof OverlayError)) throw err;
        overlay = null; // a refused overlay replaces the old one: nothing is drawn, never a part
        refusal = { code: err.code, path: err.path, message: err.message };
      }
    }
    refresh();
    if (typeof onChange === "function") onChange();
    return refusal
      ? { ok: false, status: 422, error: { ...refusal } }
      : { ok: true, status: 200, ...state() };
  }

  return {
    set,
    state,
    refresh,
    paint(ctx, view) { if (overlay) paintOverlay(ctx, view, overlay, { stale: isStale(), tokens: tokens() }); },
    get active() { return overlay !== null; },
  };
}
