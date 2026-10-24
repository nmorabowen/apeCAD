// In-memory mock transport for offline previews and unit tests of the 2-D section editor (ADR 0026).
import {
  TRANSPORT_VERSION,
  barDiameterMm,
  buildDraftFromScene,
  emptyScene,
  insetRing,
  legOutline,
  normalizeScene,
  resolveXY,
  seedToOps,
} from "./transport.js";

function applyOpToScene(scene, op, nextId, ptById) {
  const created = [];
  const kind = op.op;
  const allocPt = (xy) => {
    const pid = nextId();
    const p = [Number(xy[0]), Number(xy[1])];
    ptById.set(pid, p);
    scene.points.push({ entity_id: pid, x_mm: p[0], y_mm: p[1], z_mm: 0, label: null });
    return pid;
  };
  if (kind === "RectSection") {
    const b = Number(op.b_mm), h = Number(op.h_mm);
    if (!(b > 0 && h > 0)) throw new Error("b_mm and h_mm must be > 0");
    const [ox, oy] = op.origin || [0, 0];
    return applyOpToScene(scene, {
      op: "AddSectionOutline",
      point_ids: [{ xyz: [ox, oy, 0] }, { xyz: [ox + b, oy, 0] }, { xyz: [ox + b, oy + h, 0] }, { xyz: [ox, oy + h, 0] }],
      material: op.material || "concrete", label: op.label ?? null,
    }, nextId, ptById);
  }
  if (kind === "PolygonSection" || kind === "AddSectionOutline" || kind === "AddConcreteFace") {
    const rawPts = op.outer || op.point_ids || [];
    const outer = rawPts.map((v) => resolveXY(v, ptById));
    if (outer.length < 3) throw new Error("Section outline needs at least 3 vertices");
    const pids = outer.map(allocPt);
    const id = nextId();
    scene.concrete_faces.push({
      id, entity_id: id, point_ids: pids, outer_mm: outer, ring_mm: outer,
      openings_mm: (op.openings || []).map((r) => r.map((p) => [Number(p[0]), Number(p[1])])),
      material: op.material || "concrete", role: "solid", label: op.label ?? null,
    });
    created.push(id);
  } else if (kind === "AddOpening") {
    const face = scene.concrete_faces.find((f) => f.id === (op.face ?? op.face_id));
    if (!face) throw new Error("Unknown face");
    face.openings_mm.push((op.polygon || []).map((p) => [Number(p[0]), Number(p[1])]));
  } else if (kind === "WallLeg" || kind === "AddWallLeg") {
    const s = resolveXY(op.start ?? op.start_id, ptById);
    const e = resolveXY(op.end ?? op.end_id, ptById);
    const t = Number(op.thickness_mm || 250);
    if (!(t > 0)) throw new Error("thickness_mm must be > 0");
    const outline = legOutline(s, e, t);
    let faceId = op.face_id ?? scene.concrete_faces[0]?.id ?? null;
    if (faceId == null) {
      faceId = nextId();
      scene.concrete_faces.push({
        id: faceId, entity_id: faceId, point_ids: outline.map(allocPt),
        outer_mm: outline, ring_mm: outline, openings_mm: [], material: "concrete", role: "solid", label: op.label ?? null,
      });
      created.push(faceId);
    }
    const legId = nextId();
    scene.wall_legs.push({
      id: legId, entity_id: legId, start_id: allocPt(s), end_id: allocPt(e),
      axis_start_mm: s, axis_end_mm: e, start_mm: s, end_mm: e,
      thickness_mm: t, outline_mm: outline, face_id: faceId,
      horizontal: op.horizontal ?? null, label: op.label ?? null,
    });
    created.push(legId);
  } else if (kind === "WallSegmentChain" || kind === "AddWallChain") {
    const rawPts = op.points || op.point_ids || [];
    const pts = rawPts.map((v) => resolveXY(v, ptById));
    if (pts.length < 2) throw new Error("Wall chain needs at least 2 points");
    const tArr = Array.isArray(op.thickness_mm) ? op.thickness_mm : [op.thickness_mm || 250];
    const t0 = Number(tArr[0] || 250);
    const leftSide = [], rightSide = [];
    for (let i = 0; i < pts.length - 1; i++) {
      const ti = Number(tArr[i] ?? t0);
      const lo = legOutline(pts[i], pts[i + 1], ti);
      if (i === 0) { leftSide.push(lo[0]); rightSide.push(lo[3]); }
      leftSide.push(lo[1]);
      rightSide.push(lo[2]);
    }
    const outline = leftSide.concat(rightSide.reverse());
    const faceId = nextId();
    scene.concrete_faces.push({
      id: faceId, entity_id: faceId, point_ids: outline.map(allocPt),
      outer_mm: outline, ring_mm: outline, openings_mm: [],
      material: op.material || "concrete", role: "solid", label: op.label ?? null,
    });
    created.push(faceId);
    for (let i = 0; i < pts.length - 1; i++) {
      const ti = Number(tArr[i] ?? t0);
      const legId = nextId();
      scene.wall_legs.push({
        id: legId, entity_id: legId, start_id: allocPt(pts[i]), end_id: allocPt(pts[i + 1]),
        axis_start_mm: pts[i], axis_end_mm: pts[i + 1], start_mm: pts[i], end_mm: pts[i + 1],
        thickness_mm: ti, outline_mm: legOutline(pts[i], pts[i + 1], ti),
        face_id: faceId, horizontal: op.horizontal ?? null, label: null,
      });
      created.push(legId);
    }
  } else if (kind === "SetCover") {
    const targetId = op.face_id ?? op.target;
    const face = scene.concrete_faces.find((f) => f.id === targetId);
    if (!face) throw new Error(`Unknown face: ${targetId}`);
    const clear = Number(op.cover_mm ?? op.clear_cover_mm ?? 25);
    const tieD = Number(op.tie_diameter_mm ?? barDiameterMm(op.stirrup_size || "Ø10"));
    const barD = Number(op.bar_diameter_mm ?? barDiameterMm(op.main_bar_size || "Ø16"));
    const coverRing = insetRing(face.outer_mm, clear);
    const centreRing = insetRing(face.outer_mm, clear + tieD + barD / 2);
    const existing = scene.cover_guides.find((g) => g.face_id === face.id);
    const guideId = existing ? existing.id : nextId();
    const guide = {
      id: guideId, entity_id: guideId, face_id: face.id, target_id: face.id,
      cover_mm: clear, clear_cover_mm: clear, tie_diameter_mm: tieD, bar_diameter_mm: barD,
      cover_ring_mm: coverRing, bar_centre_ring_mm: centreRing, label: null,
    };
    if (existing) Object.assign(existing, guide);
    else scene.cover_guides.push(guide);
    created.push(guideId);
  } else if (kind === "SetMaterial") {
    const ids = op.entity_ids || (op.target != null ? [op.target] : []);
    for (const id of ids) {
      const face = scene.concrete_faces.find((f) => f.id === id);
      if (!face) throw new Error(`Unknown face: ${id}`);
      if (op.material) face.material = String(op.material);
      if (op.fc_mpa != null) face.fc_mpa = Number(op.fc_mpa);
    }
  } else if (kind === "PlaceBar" || kind === "AddBar") {
    const xy = op.at ? [Number(op.at[0]), Number(op.at[1])] : [Number(op.x_mm), Number(op.y_mm)];
    const desig = String(op.designation || op.size || "Ø16");
    const d = barDiameterMm(desig);
    const pid = allocPt(xy);
    const id = nextId();
    scene.bars.push({
      id, entity_id: id, point_id: pid, centre_mm: xy, x_mm: xy[0], y_mm: xy[1],
      designation: desig, size: desig, diameter_mm: d, area_mm2: Math.PI * (d / 2) ** 2,
      role: op.role || "longitudinal", face_id: op.face || scene.concrete_faces[0]?.id || null, label: op.label ?? null,
    });
    created.push(id);
  } else if (kind === "PlaceBarRow" || kind === "AddBarRow") {
    const [x0, y0] = op.start || [Number(op.start_x_mm), Number(op.start_y_mm)];
    const [x1, y1] = op.end || [Number(op.end_x_mm), Number(op.end_y_mm)];
    const len = Math.hypot(x1 - x0, y1 - y0);
    const count = op.count != null ? Number(op.count) : Math.max(2, Math.floor(len / Number(op.spacing_mm || 150)) + 1);
    if (count < 2) throw new Error("Bar row count must be >= 2");
    const desig = String(op.designation || op.size || "Ø16");
    for (let i = 0; i < count; i++) {
      const t = i / (count - 1);
      created.push(...applyOpToScene(scene, {
        op: "AddBar", x_mm: x0 + (x1 - x0) * t, y_mm: y0 + (y1 - y0) * t, designation: desig,
      }, nextId, ptById));
    }
  } else if (kind === "PlaceBarsOnEdge" || kind === "AddBarsAlongEdge") {
    const faceId = op.face_id ?? op.target;
    const guide = scene.cover_guides.find((g) => g.face_id === faceId);
    const face = scene.concrete_faces.find((f) => f.id === faceId);
    const ring = guide?.bar_centre_ring_mm || face?.outer_mm || [];
    const idx = Number(op.edge_index || 0);
    if (ring.length < 2) throw new Error("Face has no ring for edge bars");
    const p0 = ring[idx % ring.length], p1 = ring[(idx + 1) % ring.length];
    created.push(...applyOpToScene(scene, {
      op: "AddBarRow", start: p0, end: p1, designation: op.designation || op.size || "Ø16",
      count: op.count, spacing_mm: op.spacing_mm,
    }, nextId, ptById));
  } else if (kind === "PlaceHoop" || kind === "AddHoop") {
    const barIds = op.bar_ids || op.bars || [];
    const desig = String(op.designation || op.size || "Ø10");
    const d = barDiameterMm(desig);
    let ring = op.ring ? op.ring.map((p) => [Number(p[0]), Number(p[1])]) : null;
    if (!ring) {
      if (barIds.length < 3) throw new Error("AddHoop requires at least 3 bars");
      const pts = barIds.map((bid) => scene.bars.find((b) => b.id === bid)).filter(Boolean).map((b) => b.centre_mm);
      if (pts.length < 3) throw new Error("AddHoop bars not found");
      const sorted = pts.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]);
      const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
      const lower = [], upper = [];
      for (const p of sorted) {
        while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop();
        lower.push(p);
      }
      for (let i = sorted.length - 1; i >= 0; i--) {
        const p = sorted[i];
        while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop();
        upper.push(p);
      }
      lower.pop();
      upper.pop();
      ring = lower.concat(upper);
      if (ring.length < 3) ring = pts.slice();
    }
    const id = nextId();
    scene.hoops.push({
      id, entity_id: id, bar_ids: barIds.slice(), ring_mm: ring, display_ring_mm: ring,
      designation: desig, size: desig, diameter_mm: d, area_mm2: Math.PI * (d / 2) ** 2,
      spacing_mm: Number(op.spacing_mm || 100), hooks: String(op.hooks || "135"), label: op.label ?? null,
    });
    created.push(id);
  } else if (kind === "PlaceCrosstie" || kind === "AddCrosstie") {
    const aId = op.bar_a_id ?? op.bar_a, bId = op.bar_b_id ?? op.bar_b;
    const ba = scene.bars.find((b) => b.id === aId), bb = scene.bars.find((b) => b.id === bId);
    if (!ba || !bb || ba.id === bb.id) throw new Error("AddCrosstie requires two distinct bars");
    const desig = String(op.designation || op.size || "Ø10");
    const d = barDiameterMm(desig);
    const id = nextId();
    scene.crossties.push({
      id, entity_id: id, bar_a_id: ba.id, bar_b_id: bb.id,
      start_mm: ba.centre_mm.slice(), end_mm: bb.centre_mm.slice(),
      designation: desig, size: desig, diameter_mm: d, area_mm2: Math.PI * (d / 2) ** 2,
      spacing_mm: Number(op.spacing_mm || 100), hooks: String(op.hooks || "135-135"), label: op.label ?? null,
    });
    created.push(id);
  } else if (kind === "SetBarSize") {
    const desig = String(op.designation || op.size || "Ø16");
    const d = barDiameterMm(desig);
    for (const id of op.entity_ids || op.bars || []) {
      const b = scene.bars.find((x) => x.id === id);
      if (b) { b.designation = desig; b.size = desig; b.diameter_mm = d; b.area_mm2 = Math.PI * (d / 2) ** 2; }
    }
  } else if (kind === "SetTransverse") {
    const desig = op.designation || op.size;
    const d = desig ? barDiameterMm(desig) : null;
    for (const id of op.entity_ids || op.targets || []) {
      const h = scene.hoops.find((x) => x.id === id) || scene.crossties.find((x) => x.id === id);
      if (h) {
        if (desig && d) { h.designation = String(desig); h.size = String(desig); h.diameter_mm = d; }
        if (op.spacing_mm != null) h.spacing_mm = Number(op.spacing_mm);
        if (op.hooks != null) h.hooks = String(op.hooks);
      }
    }
  } else if (kind === "SetLegReinforcement") {
    const leg = scene.wall_legs.find((l) => l.id === (op.leg_id ?? op.leg));
    if (!leg) throw new Error("Unknown leg");
    leg.horizontal = {
      designation: String(op.designation || op.bar_size || "Ø12"),
      spacing_mm: Number(op.spacing_mm || 200),
      curtains: Number(op.curtains || 2),
    };
  } else if (kind === "Delete") {
    const ids = new Set(op.entity_ids || (op.target != null ? [op.target] : []));
    for (const key of ["concrete_faces", "wall_legs", "cover_guides", "bars", "hoops", "crossties"]) {
      scene[key] = scene[key].filter((item) => !ids.has(item.id));
    }
  } else if (kind === "SetLabel") {
    for (const key of ["concrete_faces", "wall_legs", "cover_guides", "bars", "hoops", "crossties"]) {
      const item = scene[key].find((x) => x.id === op.entity_id);
      if (item) item.label = op.label ?? null;
    }
  } else {
    throw new Error(`Unsupported op: ${kind}`);
  }
  return created;
}

export function mockTransport(initialDraft = null) {
  let history = [];
  let redoStack = [];
  let rev = 0;

  function rebuild(ops) {
    const scene = emptyScene();
    const ptById = new Map();
    let seq = 0;
    const nextId = () => ++seq;
    let lastCreated = [];
    for (const op of ops) lastCreated = applyOpToScene(scene, op, nextId, ptById);
    scene.revision = rev;
    return { scene: normalizeScene(scene), lastCreated };
  }

  function loadPayload(doc) {
    history = seedToOps(doc, applyOpToScene);
    redoStack = [];
    rev += 1;
  }

  if (initialDraft) loadPayload(initialDraft);

  return async function handle(request) {
    const action = request?.action;
    try {
      if (action === "scene" || action === "draft") {
        const { scene } = rebuild(history);
        const docDict = { schema: "apeCAD.document.v1", units: "mm", ops: history.slice() };
        return {
          ok: true, status: 200, transport_version: TRANSPORT_VERSION, revision: rev,
          can_undo: history.length > 0, can_redo: redoStack.length > 0,
          document: docDict, redo: redoStack.slice(), scene, draft: buildDraftFromScene(scene, docDict),
        };
      }
      if (action === "apply") {
        const batch = Array.isArray(request.ops) ? request.ops : request.op ? [request.op] : [];
        if (!batch.length) throw new Error("apply requires op or ops");
        const nextHistory = history.concat(batch);
        const { scene, lastCreated } = rebuild(nextHistory);
        history = nextHistory;
        redoStack = [];
        rev += 1;
        scene.revision = rev;
        const docDict = { schema: "apeCAD.document.v1", units: "mm", ops: history.slice() };
        return {
          ok: true, status: 200, transport_version: TRANSPORT_VERSION, revision: rev,
          can_undo: history.length > 0, can_redo: false,
          created_id: lastCreated[0] ?? null, result: lastCreated[0] ?? null, created_ids: lastCreated,
          document: docDict, redo: [], scene, draft: buildDraftFromScene(scene, docDict),
        };
      }
      if (action === "undo") {
        if (!history.length) throw new Error("Nothing to undo");
        redoStack.push(history.pop());
        rev += 1;
        const { scene } = rebuild(history);
        const docDict = { schema: "apeCAD.document.v1", units: "mm", ops: history.slice() };
        return {
          ok: true, status: 200, transport_version: TRANSPORT_VERSION, revision: rev,
          can_undo: history.length > 0, can_redo: redoStack.length > 0,
          document: docDict, redo: redoStack.slice(), scene, draft: buildDraftFromScene(scene, docDict),
        };
      }
      if (action === "redo") {
        if (!redoStack.length) throw new Error("Nothing to redo");
        history.push(redoStack.pop());
        rev += 1;
        const { scene } = rebuild(history);
        const docDict = { schema: "apeCAD.document.v1", units: "mm", ops: history.slice() };
        return {
          ok: true, status: 200, transport_version: TRANSPORT_VERSION, revision: rev,
          can_undo: history.length > 0, can_redo: redoStack.length > 0,
          document: docDict, redo: redoStack.slice(), scene, draft: buildDraftFromScene(scene, docDict),
        };
      }
      if (action === "load" || action === "seed") {
        loadPayload(request.payload ?? request.document ?? request.seed);
        const { scene } = rebuild(history);
        const docDict = { schema: "apeCAD.document.v1", units: "mm", ops: history.slice() };
        return {
          ok: true, status: 200, transport_version: TRANSPORT_VERSION, revision: rev,
          can_undo: false, can_redo: false,
          document: docDict, redo: [], scene, draft: buildDraftFromScene(scene, docDict), warnings: [],
        };
      }
      return { ok: false, status: 422, transport_version: TRANSPORT_VERSION, error: { code: "unknown_action", message: `Unknown action: ${action}` } };
    } catch (err) {
      return { ok: false, status: 422, transport_version: TRANSPORT_VERSION, error: { code: "REFUSED", message: String(err.message || err) } };
    }
  };
}
