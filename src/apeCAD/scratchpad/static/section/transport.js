// Transport adapters and scene/draft normalization for the embeddable 2-D section editor (ADR 0026).

export const TRANSPORT_VERSION = 1;

const BAR_DIAMETERS_MM = {
  "Ø8": 8, "Ø10": 10, "Ø12": 12, "Ø14": 14, "Ø16": 16, "Ø18": 18,
  "Ø20": 20, "Ø22": 22, "Ø25": 25, "Ø28": 28, "Ø32": 32,
  "#3": 9.525, "#4": 12.7, "#5": 15.875, "#6": 19.05, "#7": 22.225,
  "#8": 25.4, "#9": 28.65, "#10": 32.26, "#11": 35.81, "#14": 43.0, "#18": 57.33,
  "6M": 6, "8M": 8, "10M": 10, "12M": 12, "16M": 16, "20M": 20,
  "22M": 22, "25M": 25, "28M": 28, "32M": 32, "36M": 36, "40M": 40,
};

export function barDiameterMm(size) {
  const s = String(size || "Ø16");
  if (BAR_DIAMETERS_MM[s]) return BAR_DIAMETERS_MM[s];
  const m = s.match(/^Ø(\d+(?:\.\d+)?)$/);
  return m ? Number(m[1]) : 16;
}

export function legOutline(start, end, thickness) {
  const dx = end[0] - start[0], dy = end[1] - start[1];
  const len = Math.hypot(dx, dy) || 1;
  const nx = (-dy / len) * (thickness / 2), ny = (dx / len) * (thickness / 2);
  return [
    [start[0] - nx, start[1] - ny],
    [end[0] - nx, end[1] - ny],
    [end[0] + nx, end[1] + ny],
    [start[0] + nx, start[1] + ny],
  ];
}

export function insetRing(ring, inset) {
  if (!ring || ring.length < 3 || !(inset > 0)) return (ring || []).map((p) => [p[0], p[1]]);
  const xs = ring.map((p) => p[0]), ys = ring.map((p) => p[1]);
  const x0 = Math.min(...xs) + inset, x1 = Math.max(...xs) - inset;
  const y0 = Math.min(...ys) + inset, y1 = Math.max(...ys) - inset;
  if (x1 <= x0 || y1 <= y0) return ring.map((p) => [p[0], p[1]]);
  return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]];
}

export function emptyScene() {
  return {
    unit: "mm", revision: 0, points: [], lines: [], solids: [], faces: [],
    concrete_faces: [], wall_legs: [], cover_guides: [], bars: [], hoops: [], crossties: [], warnings: [],
  };
}

export function resolveXY(v, ptById) {
  if (Array.isArray(v)) return [Number(v[0]), Number(v[1])];
  if (v && Array.isArray(v.xyz)) return [Number(v.xyz[0]), Number(v.xyz[1])];
  if (typeof v === "number") return ptById.get(v) || [0, 0];
  if (v && typeof v.id === "number") return ptById.get(v.id) || [0, 0];
  return [0, 0];
}

export function normalizeScene(rawScene) {
  const scene = rawScene ? { ...rawScene } : {};
  const ptById = new Map();
  for (const p of scene.points || []) {
    const id = p.entity_id ?? p.id;
    ptById.set(id, [Number(p.x_mm ?? p.position?.[0] ?? 0), Number(p.y_mm ?? p.position?.[1] ?? 0)]);
  }
  scene.concrete_faces = (scene.concrete_faces || []).map((f) => {
    const id = f.entity_id ?? f.id;
    const outer = (f.outer_mm || f.ring_mm || (f.point_ids || []).map((pid) => ptById.get(pid)).filter(Boolean))
      .map((p) => [Number(p[0]), Number(p[1])]);
    const openings = (f.openings_mm || []).map((r) => r.map((p) => [Number(p[0]), Number(p[1])]));
    return { ...f, id, entity_id: id, material: f.material || "concrete", role: f.role || "solid", outer_mm: outer, ring_mm: outer, openings_mm: openings };
  });
  scene.wall_legs = (scene.wall_legs || []).map((l) => {
    const id = l.entity_id ?? l.id;
    const s = (l.axis_start_mm || l.start_mm || ptById.get(l.start_id) || [0, 0]).map(Number);
    const e = (l.axis_end_mm || l.end_mm || ptById.get(l.end_id) || [0, 0]).map(Number);
    const t = Number(l.thickness_mm || 250);
    return { ...l, id, entity_id: id, axis_start_mm: s, axis_end_mm: e, start_mm: s, end_mm: e, thickness_mm: t, outline_mm: l.outline_mm || legOutline(s, e, t) };
  });
  scene.bars = (scene.bars || []).map((b) => {
    const id = b.entity_id ?? b.id;
    const c = (b.centre_mm || (b.x_mm != null ? [b.x_mm, b.y_mm] : ptById.get(b.point_id)) || [0, 0]).map(Number);
    const desig = b.designation || b.size || "Ø16";
    const d = Number(b.diameter_mm || barDiameterMm(desig));
    return { ...b, id, entity_id: id, centre_mm: c, x_mm: c[0], y_mm: c[1], designation: desig, size: desig, diameter_mm: d, area_mm2: Number(b.area_mm2 || Math.PI * (d / 2) ** 2) };
  });
  const barById = new Map(scene.bars.map((b) => [b.id, b]));
  scene.hoops = (scene.hoops || []).map((h) => {
    const id = h.entity_id ?? h.id;
    const desig = h.designation || h.size || "Ø10";
    const d = Number(h.diameter_mm || barDiameterMm(desig));
    const ring = (h.display_ring_mm || h.ring_mm || []).map((p) => [Number(p[0]), Number(p[1])]);
    return { ...h, id, entity_id: id, designation: desig, size: desig, diameter_mm: d, area_mm2: Number(h.area_mm2 || Math.PI * (d / 2) ** 2), spacing_mm: Number(h.spacing_mm || 100), hooks: String(h.hooks || "135"), ring_mm: ring, display_ring_mm: ring };
  });
  scene.crossties = (scene.crossties || []).map((t) => {
    const id = t.entity_id ?? t.id;
    const desig = t.designation || t.size || "Ø10";
    const d = Number(t.diameter_mm || barDiameterMm(desig));
    const s = (t.start_mm || barById.get(t.bar_a_id)?.centre_mm || [0, 0]).map(Number);
    const e = (t.end_mm || barById.get(t.bar_b_id)?.centre_mm || [0, 0]).map(Number);
    return { ...t, id, entity_id: id, designation: desig, size: desig, diameter_mm: d, area_mm2: Number(t.area_mm2 || Math.PI * (d / 2) ** 2), spacing_mm: Number(t.spacing_mm || 100), hooks: typeof t.hooks === "string" ? t.hooks : "135-135", start_mm: s, end_mm: e };
  });
  scene.cover_guides = (scene.cover_guides || []).map((g) => {
    const id = g.entity_id ?? g.id, faceId = g.face_id ?? g.target_id;
    return { ...g, id, entity_id: id, face_id: faceId, target_id: faceId };
  });
  scene.warnings = scene.warnings || [];
  return scene;
}

export function buildDraftFromScene(rawScene, docDict = null) {
  const scene = normalizeScene(rawScene);
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const f of scene.concrete_faces) {
    for (const [x, y] of f.outer_mm) {
      if (x < minX) minX = x;
      if (y < minY) minY = y;
      if (x > maxX) maxX = x;
      if (y > maxY) maxY = y;
    }
  }
  const bbox_mm = Number.isFinite(minX) ? [minX, minY, maxX, maxY] : [0, 0, 0, 0];
  const sectionBlock = {
    concrete_faces: scene.concrete_faces.map((f) => ({
      id: f.id, label: f.label ?? null, material: f.material || "concrete",
      role: "solid", ring_mm: f.outer_mm,
    })),
    wall_legs: scene.wall_legs.map((l) => ({
      id: l.id, label: l.label ?? null, start_mm: l.start_mm, end_mm: l.end_mm,
      thickness_mm: l.thickness_mm, outline_mm: l.outline_mm,
      concrete_face_id: l.face_id ?? l.concrete_face_id ?? null,
      horizontal: l.horizontal ?? null,
    })),
    bars: scene.bars.map((b) => ({
      id: b.id, label: b.label ?? null, x_mm: b.x_mm, y_mm: b.y_mm,
      diameter_mm: b.diameter_mm, designation: b.designation,
    })),
    hoops: scene.hoops.map((h) => ({
      id: h.id, label: h.label ?? null, bar_ids: h.bar_ids || [],
      ring_mm: h.ring_mm, diameter_mm: h.diameter_mm,
      designation: h.designation, spacing_mm: h.spacing_mm, hooks: h.hooks,
    })),
    crossties: scene.crossties.map((t) => ({
      id: t.id, label: t.label ?? null, bar_a_id: t.bar_a_id, bar_b_id: t.bar_b_id,
      start_mm: t.start_mm, end_mm: t.end_mm, diameter_mm: t.diameter_mm,
      designation: t.designation, spacing_mm: t.spacing_mm, hooks: t.hooks,
    })),
    cover_guides: scene.cover_guides.map((g) => ({
      id: g.id, face_id: g.face_id, cover_mm: Number(g.cover_mm ?? g.clear_cover_mm ?? 25),
      tie_diameter_mm: Number(g.tie_diameter_mm ?? 10), bar_diameter_mm: Number(g.bar_diameter_mm ?? 16),
    })),
  };
  return {
    schema: "apeCAD.section-draft",
    version: 1,
    schema_version: 1,
    units: "mm",
    frame: { x: "right", y: "up", origin: "world" },
    producer: { apeCAD_version: "0.1.0", apeCAD_commit: null },
    bbox_mm,
    document: docDict || scene.document || { schema: "apeCAD.document.v1", units: "mm", ops: [] },
    section: sectionBlock,
    concrete_faces: sectionBlock.concrete_faces,
    wall_legs: sectionBlock.wall_legs,
    bars: sectionBlock.bars,
    hoops: sectionBlock.hoops,
    crossties: sectionBlock.crossties,
    cover_guides: sectionBlock.cover_guides,
    warnings: scene.warnings || [],
  };
}

export function seedToOps(doc, applyOpToScene) {
  if (!doc || typeof doc !== "object") throw new Error("Payload must be an object");
  if (doc.document && Array.isArray(doc.document.ops)) return doc.document.ops.slice();
  if (Array.isArray(doc.ops)) return doc.ops.slice();
  if (doc.schema !== "apeCAD.section-seed" && doc.schema !== "apeCAD.section-draft") {
    throw new Error("Unsupported load payload");
  }
  const sec = doc.section || doc;
  const ops = [], tmp = emptyScene(), ptById = new Map(), faceIds = [], barIds = [];
  const faceMap = new Map(), barMap = new Map();
  let seq = 0;
  const pushOp = (op) => { ops.push(op); return applyOpToScene(tmp, op, () => ++seq, ptById); };
  for (const [idx, f] of (sec.concrete_faces || []).entries()) {
    const ring = f.ring_mm || f.outer_mm || [];
    const [fid] = pushOp({ op: "AddSectionOutline", point_ids: ring.map((p) => ({ xyz: [p[0], p[1], 0] })), material: f.material || "concrete", label: f.label ?? null });
    faceIds.push(fid); faceMap.set(idx, fid); if (f.id != null) faceMap.set(f.id, fid);
    for (const opRing of f.openings_mm || f.openings || []) pushOp({ op: "AddOpening", face_id: fid, polygon: opRing });
  }
  for (const l of sec.wall_legs || []) {
    const s = l.start_mm || l.axis_start_mm || [0, 0], e = l.end_mm || l.axis_end_mm || [0, 0];
    const fid = faceMap.get(l.concrete_face_id ?? l.face_id) ?? faceIds[0] ?? null;
    const ids = pushOp({ op: "AddWallLeg", face_id: fid, start_id: { xyz: [s[0], s[1], 0] }, end_id: { xyz: [e[0], e[1], 0] }, thickness_mm: l.thickness_mm ?? 250, label: l.label ?? null });
    if (!faceIds.length && ids.length > 1) { faceIds.push(ids[0]); faceMap.set(0, ids[0]); }
    if (l.horizontal) pushOp({ op: "SetLegReinforcement", leg_id: ids[ids.length - 1], designation: l.horizontal.designation || "Ø12", spacing_mm: l.horizontal.spacing_mm ?? 200, curtains: l.horizontal.curtains ?? 2 });
  }
  for (const g of sec.cover_guides || []) {
    const fid = faceMap.get(g.face_id ?? 0) ?? faceIds[0];
    if (fid != null) pushOp({ op: "SetCover", face_id: fid, cover_mm: g.cover_mm ?? 25, tie_diameter_mm: g.tie_diameter_mm ?? 10, bar_diameter_mm: g.bar_diameter_mm ?? 16 });
  }
  for (const [idx, b] of (sec.bars || []).entries()) {
    const xy = b.centre_mm || [b.x_mm, b.y_mm];
    const [bid] = pushOp({ op: "AddBar", x_mm: xy[0], y_mm: xy[1], designation: b.designation || b.size || "Ø16", label: b.label ?? null });
    barIds.push(bid); barMap.set(idx, bid); if (b.id != null) barMap.set(b.id, bid);
  }
  for (const h of sec.hoops || []) {
    const bids = (h.bar_ids || []).map((id) => barMap.get(id) ?? barIds[id]).filter((id) => id != null);
    if (bids.length >= 3) pushOp({ op: "AddHoop", bar_ids: bids, designation: h.designation || h.size || "Ø10", spacing_mm: h.spacing_mm ?? 100, hooks: h.hooks || "135", label: h.label ?? null });
  }
  for (const t of sec.crossties || []) {
    const ba = barMap.get(t.bar_a_id) ?? barIds[t.bar_a_id], bb = barMap.get(t.bar_b_id) ?? barIds[t.bar_b_id];
    if (ba != null && bb != null && ba !== bb) pushOp({ op: "AddCrosstie", bar_a_id: ba, bar_b_id: bb, designation: t.designation || t.size || "Ø10", spacing_mm: t.spacing_mm ?? 100, hooks: t.hooks || "135-135", label: t.label ?? null });
  }
  return ops;
}

export function httpTransport(url = "/api/section/transport") {
  let docState = null;
  let redoState = [];
  return async function send(request) {
    const action = request?.action || "scene";
    const body = { transport_version: TRANSPORT_VERSION, action };
    if (action === "load" || action === "seed") {
      body.payload = request.payload ?? request.document ?? request.seed;
    } else {
      body.document = request.document !== undefined ? request.document : docState;
      body.redo = request.redo !== undefined ? request.redo : redoState;
      if (action === "apply") body.op = request.op || (Array.isArray(request.ops) ? request.ops[0] : null);
    }
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (data && data.ok) {
      docState = data.document || docState;
      redoState = Array.isArray(data.redo) ? data.redo : [];
      if (data.scene) data.scene = normalizeScene(data.scene);
      if (!data.draft && data.scene) data.draft = buildDraftFromScene(data.scene, docState);
    }
    return data;
  };
}

export { mockTransport } from "./mock-transport.js";
