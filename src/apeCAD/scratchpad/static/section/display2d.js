// The 2-D section client's display list (C5 record §3 "Client drawing"; ADR 0039, 0040).
// Every section kind of the scene, on its layer, back to front, in `render`'s layer order;
// hit-testing by role, holes excluded; scene bounds; the selected entity's title.
// Pure: no DOM, no canvas, no colours (those are `canvas2d.js::PALETTE`).

// Back to front, as `apeCAD.render.drawable.SECTION_LAYERS` paints (C5 record §3): role
// decides overlap, void over steel over concrete, whatever the ids (ADR 0039 D3).
export const SECTION_LAYERS = Object.freeze([
  "concrete", "steel", "void", "cover", "leg", "hoop", "crosstie", "circular-tie", "bar",
]);
export const FACE_LAYERS = Object.freeze(["concrete", "steel", "void"]);

// Every scene list that holds section entities, and the kind each item is. `templates` draws
// nothing of its own: its children sit in the other lists (ADR 0040 D7, never re-expanded).
export const SECTION_KINDS = Object.freeze({
  concrete_faces: "ConcreteFace", section_faces: "SectionFace", cover_guides: "CoverGuide",
  wall_legs: "WallLeg", hoops: "Hoop", crossties: "Crosstie", circular_ties: "CircularTie",
  bars: "Bar", templates: null,
});

// Hit order, topmost first: bars, then the lines (v1's order), then the faces by role.
const HIT_LAYERS = ["bar", "circular-tie", "crosstie", "hoop", "cover", "leg", "void", "steel", "concrete"];

const idOf = (item) => item.id ?? item.entity_id;
const finite = (v) => typeof v === "number" && Number.isFinite(v);
const isXY = (p) => Array.isArray(p) && p.length >= 2 && finite(Number(p[0])) && finite(Number(p[1]));
const xy = (p) => [Number(p[0]), Number(p[1])];

function ringOf(ring, min) {
  if (!Array.isArray(ring) || ring.length < min || !ring.every(isXY)) return null;
  return ring.map(xy);
}

// One loop of a v2 face: `{ring}` or `{centre, radius}`; a string names why it is refused.
function loopOf(boundary, what) {
  const kind = boundary?.kind;
  if (kind === "ring") {
    const ring = ringOf(boundary.ring_mm, 3);
    return ring ? { ring } : `${what} ring_mm is not a ring of 3 or more [x, y] points`;
  }
  if (kind === "circle") {
    const r = Number(boundary.radius_mm);
    if (!isXY(boundary.center_mm) || !finite(r) || !(r > 0)) return `${what} is not a circle with a centre and a radius > 0`;
    return { centre: xy(boundary.center_mm), radius: r };
  }
  return `${what} has an unknown boundary kind ${JSON.stringify(kind ?? null)}`;
}

function sectionFace(f, id) {
  if (!FACE_LAYERS.includes(f.role)) return `face ${id} has an unknown role ${JSON.stringify(f.role ?? null)}`;
  const loops = [];
  const sources = [["boundary", f.boundary], ...(Array.isArray(f.holes) ? f.holes : []).map((h, i) => [`hole ${i}`, h])];
  for (const [name, boundary] of sources) {
    const loop = loopOf(boundary, `face ${id} ${name}`);
    if (typeof loop === "string") return loop;
    loops.push(loop);
  }
  return { layer: f.role, loops };
}

// The drawing of one scene item, or a string naming why it draws nothing.
function shapeOf(kind, item, id) {
  switch (kind) {
    case "ConcreteFace": {
      const outer = ringOf(item.outer_mm || item.ring_mm, 3);
      if (!outer) return `face ${id} has no ring of 3 or more points`;
      const holes = (item.openings_mm || []).map((r) => ringOf(r, 3)).filter(Boolean);
      return { layer: "concrete", loops: [{ ring: outer }, ...holes.map((ring) => ({ ring }))] };
    }
    case "SectionFace":
      return sectionFace(item, id);
    case "CoverGuide": {
      const cover = ringOf(item.cover_ring_mm, 3);
      if (!cover) return `cover guide ${id} has no cover ring${item.reason ? `: ${item.reason}` : ""}`;
      return { layer: "cover", rings: [cover], centreRing: ringOf(item.bar_centre_ring_mm, 3) };
    }
    case "WallLeg": {
      const a = item.axis_start_mm || item.start_mm, b = item.axis_end_mm || item.end_mm;
      return isXY(a) && isXY(b) ? { layer: "leg", segment: [xy(a), xy(b)] } : `wall leg ${id} has no axis`;
    }
    case "Hoop": {
      const ring = ringOf(item.display_ring_mm || item.ring_mm, 2);
      return ring ? { layer: "hoop", rings: [ring] } : `hoop ${id} has no ring`;
    }
    case "Crosstie":
      return isXY(item.start_mm) && isXY(item.end_mm)
        ? { layer: "crosstie", segment: [xy(item.start_mm), xy(item.end_mm)] }
        : `crosstie ${id} has no ends`;
    case "CircularTie": {
      const r = Number(item.centerline_radius_mm);
      if (!isXY(item.center_mm) || !finite(r) || !(r > 0)) return `circular tie ${id} is not a circle with a centre and a radius > 0`;
      return { layer: "circular-tie", circle: { centre: xy(item.center_mm), radius: r } };
    }
    case "Bar": {
      const c = item.centre_mm || [item.x_mm, item.y_mm];
      return isXY(c) ? { layer: "bar", disc: { centre: xy(c), radius: (item.diameter_mm || 16) / 2 } } : `bar ${id} has no centre`;
    }
    default:
      return `an unknown section kind ${JSON.stringify(kind)}`;
  }
}

// `{entries, notDrawn}`: entries `{id, kind, layer, item, ...shape}` by layer, then by id;
// `notDrawn` `{id, kind, message}` for each item that draws nothing, named, never guessed.
export function displayList(scene) {
  const entries = [], notDrawn = [];
  if (!scene) return { entries, notDrawn };
  for (const [key, kind] of Object.entries(SECTION_KINDS)) {
    if (kind === null) continue;
    for (const item of Array.isArray(scene[key]) ? scene[key] : []) {
      const id = idOf(item);
      const shape = shapeOf(kind, item, id);
      if (typeof shape === "string") notDrawn.push({ id, kind, message: shape });
      else entries.push({ id, kind, item, ...shape });
    }
  }
  const rank = (e) => SECTION_LAYERS.indexOf(e.layer);
  entries.sort((a, b) => rank(a) - rank(b) || Number(a.id) - Number(b.id));
  return { entries, notDrawn };
}

// --- geometry --------------------------------------------------------------------------

export function distToSegment(p, a, b) {
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
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

const inLoop = (pt, loop) => (loop.ring ? pointInPolygon(pt, loop.ring) : Math.hypot(pt[0] - loop.centre[0], pt[1] - loop.centre[1]) < loop.radius);

// The index of the ring edge within `aperturePx` of `screenPt`, or -1.
function nearRingEdge(screenPt, view, ring, aperturePx) {
  for (let i = 0; i < ring.length; i++) {
    const a = view.worldToScreen(ring[i]), b = view.worldToScreen(ring[(i + 1) % ring.length]);
    if (distToSegment(screenPt, a, b) <= aperturePx) return i;
  }
  return -1;
}

function nearCircle(screenPt, view, circle, aperturePx) {
  const c = view.worldToScreen(circle.centre);
  return Math.abs(Math.hypot(screenPt[0] - c[0], screenPt[1] - c[1]) - circle.radius * view.scale) <= aperturePx;
}

function hitEntry(e, screenPt, worldPt, view, aperturePx) {
  const hit = (extra = {}) => ({ kind: e.kind, id: e.id, item: e.item, ...extra });
  if (e.segment) {
    const [a, b] = e.segment.map((p) => view.worldToScreen(p));
    return distToSegment(screenPt, a, b) <= aperturePx ? hit() : null;
  }
  if (e.circle) return nearCircle(screenPt, view, e.circle, aperturePx) ? hit() : null;
  if (e.rings) return e.rings.some((r) => nearRingEdge(screenPt, view, r, aperturePx) >= 0) ? hit() : null;
  if (!e.loops) return null;
  const role = e.kind === "SectionFace" ? { role: e.layer } : {};
  const [outer, ...holes] = e.loops;
  if (e.kind === "ConcreteFace") { // v1: an edge of the outline carries its index (edge bars)
    const edge = nearRingEdge(screenPt, view, outer.ring, aperturePx);
    if (edge >= 0) return hit({ edge_index: edge });
  } else if (e.loops.some((l) => (l.ring ? nearRingEdge(screenPt, view, l.ring, aperturePx) >= 0 : nearCircle(screenPt, view, l, aperturePx)))) {
    return hit(role);
  }
  return inLoop(worldPt, outer) && !holes.some((h) => inLoop(worldPt, h)) ? hit(role) : null;
}

// The entity under `screenPt`: the nearest bar, else the first line, else the face on top by
// role (void, steel, concrete); a point inside a hole misses that face.
export function hitTestDisplay(screenPt, view, display, aperturePx = 10) {
  const worldPt = view.screenToWorld(screenPt);
  let bestBar = null, bestBarD = Infinity;
  for (const e of display.entries) {
    if (e.layer !== "bar") continue;
    const sp = view.worldToScreen(e.disc.centre);
    const rPx = Math.max(aperturePx, e.disc.radius * view.scale + 4);
    const d = Math.hypot(sp[0] - screenPt[0], sp[1] - screenPt[1]);
    if (d <= rPx && d < bestBarD) { bestBar = { kind: "Bar", id: e.id, item: e.item }; bestBarD = d; }
  }
  if (bestBar) return bestBar;
  for (const layer of HIT_LAYERS.slice(1)) {
    for (const e of display.entries) {
      if (e.layer !== layer) continue;
      const found = hitEntry(e, screenPt, worldPt, view, aperturePx);
      if (found) return found;
    }
  }
  return null;
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
  const visitCircle = (c, r) => {
    if (!isXY(c) || !finite(Number(r))) return;
    visit([Number(c[0]) - Number(r), Number(c[1]) - Number(r)]);
    visit([Number(c[0]) + Number(r), Number(c[1]) + Number(r)]);
  };
  if (scene) {
    for (const f of scene.concrete_faces || []) for (const p of f.outer_mm || f.ring_mm || []) visit(p);
    for (const l of scene.wall_legs || []) for (const p of l.outline_mm || [l.start_mm, l.end_mm]) visit(p);
    for (const b of scene.bars || []) visitCircle(b.centre_mm || [b.x_mm, b.y_mm], (b.diameter_mm || 16) / 2);
    for (const h of scene.hoops || []) for (const p of h.display_ring_mm || h.ring_mm || []) visit(p);
    for (const f of scene.section_faces || []) {
      const b = f.boundary || {};
      if (b.kind === "circle") visitCircle(b.center_mm, b.radius_mm);
      else for (const p of b.ring_mm || []) visit(p);
    }
    for (const t of scene.circular_ties || []) visitCircle(t.center_mm, t.centerline_radius_mm);
  }
  if (!Number.isFinite(minX)) return [0, 0, 500, 500];
  if (maxX - minX < 1e-3) { minX -= 100; maxX += 100; }
  if (maxY - minY < 1e-3) { minY -= 100; maxY += 100; }
  return [minX, minY, maxX, maxY];
}

// The props-panel title of the entity `id`, or null when no section item has it.
export function entityTitle(scene, id) {
  const find = (key) => (scene?.[key] || []).find((item) => idOf(item) === id);
  const bar = find("bars"), face = find("concrete_faces"), hoop = find("hoops");
  const tie = find("crossties"), leg = find("wall_legs"), sface = find("section_faces");
  const ctie = find("circular_ties");
  if (bar) return `Bar #${id} (${bar.designation})`;
  if (face) return `Outline #${id} (${face.material})`;
  if (hoop) return `Hoop #${id} (${hoop.designation} @ ${hoop.spacing_mm})`;
  if (tie) return `Crosstie #${id} (${tie.designation})`;
  if (leg) return `WallLeg #${id} (t=${leg.thickness_mm} mm)`;
  if (sface) return `Face #${id} (${sface.role}${sface.material ? `, ${sface.material}` : ""})`;
  if (ctie) return `${ctie.kind === "spiral" ? "Spiral" : "Tie"} #${id} (${ctie.designation} @ ${ctie.pitch_mm})`;
  return null;
}
