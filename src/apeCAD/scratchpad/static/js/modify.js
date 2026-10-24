// Modify tools: trim / extend / break solvers and the edit ops they post, plus join, sew,
// simplify, delete, corner chamfer/fillet and node insertion.
import { S } from "./state.js";
import { entities, t } from "./strings.js";
import { api } from "./api.js";
import { catalog, findRecord, lineRows, pointById } from "./brep.js";
import { activeLength, clearTyped, labelValue, setHint } from "./cmdline.js";
import { lineIntersectMm, projectT } from "./geom.js";
import { displayUnit } from "./prefs.js";
import { pickEntity } from "./pick.js";
import { refreshFrom } from "./render.js";
import { setSelection } from "./selection.js";
import { hitWorkplane } from "./snap.js";

function cutterCandidates(victimId) {
  const pinned = [...S.cutterIds].filter((id) => id !== victimId);
  const source = pinned.length
    ? pinned.map((id) => findRecord(id)).filter((row) => row && row.kind === "Line")
    : lineRows().filter((row) => row.id !== victimId);
  return source;
}

export function seedCuttersFromSelection() {
  S.cutterIds = new Set([...S.selectedIds].filter((id) => {
    const row = findRecord(id);
    return row && row.kind === "Line";
  }));
}

export function solveTrimOrExtend(victimId, click, mode) {
  const row = findRecord(victimId);
  if (!row || row.kind !== "Line" || !click) return null;
  const a1 = pointById(row.item.start_id);
  const a2 = pointById(row.item.end_id);
  if (!a1 || !a2) return null;
  const tClick = projectT(click, a1, a2);
  const hits = [];
  for (const cutter of cutterCandidates(victimId)) {
    const b1 = pointById(cutter.item.start_id);
    const b2 = pointById(cutter.item.end_id);
    if (!b1 || !b2) continue;
    const hit = lineIntersectMm(a1, a2, b1, b2);
    if (!hit) continue;
    const onCutter = hit.u > 1e-6 && hit.u < 1 - 1e-6;
    hits.push({ ...hit, cutterId: cutter.id, onCutter });
  }
  const prefer = (left, right) => {
    if (left.onCutter !== right.onCutter) return left.onCutter ? -1 : 1;
    return 0;
  };
  if (mode === "trim") {
    const onVictim = hits.filter((hit) => hit.t > 1e-4 && hit.t < 1 - 1e-4);
    if (!onVictim.length) return null;
    const tMin = Math.min(...onVictim.map((hit) => hit.t));
    const tMax = Math.max(...onVictim.map((hit) => hit.t));
    let chosen = null;
    let keepId = null;
    if (tClick <= tMin + 1e-9) {
      chosen = onVictim.filter((hit) => Math.abs(hit.t - tMin) < 1e-9).sort(prefer)[0];
      keepId = row.item.end_id;
    } else if (tClick >= tMax - 1e-9) {
      chosen = onVictim.filter((hit) => Math.abs(hit.t - tMax) < 1e-9).sort(prefer)[0];
      keepId = row.item.start_id;
    } else {
      return null;
    }
    const keepStart = keepId === row.item.start_id;
    return {
      mode: "trim",
      lineId: victimId,
      keepId,
      cutterId: chosen.cutterId,
      cut: { x_mm: chosen.x_mm, y_mm: chosen.y_mm, z_mm: 0 },
      keepA: keepStart ? a1 : a2,
      discardA: keepStart ? a2 : a1,
    };
  }
  const beyond = hits.filter((hit) => hit.t < -1e-4 || hit.t > 1 + 1e-4);
  if (!beyond.length) return null;
  const towardStart = tClick < 0.5;
  const candidates = beyond.filter((hit) => (towardStart ? hit.t < 0 : hit.t > 1));
  if (!candidates.length) return null;
  candidates.sort((left, right) => {
    const pin = prefer(left, right);
    if (pin !== 0) return pin;
    return towardStart ? right.t - left.t : left.t - right.t;
  });
  const chosen = candidates[0];
  const from = towardStart ? a1 : a2;
  const grow = Math.hypot(chosen.x_mm - from.x_mm, chosen.y_mm - from.y_mm);
  if (grow > 100000) return null;
  return {
    mode: "extend",
    lineId: victimId,
    keepId: towardStart ? row.item.end_id : row.item.start_id,
    cutterId: chosen.cutterId,
    cut: { x_mm: chosen.x_mm, y_mm: chosen.y_mm, z_mm: 0 },
    from,
    keepA: towardStart ? a2 : a1,
  };
}

export function solveBreak(firstId, secondId) {
  if (firstId == null || secondId == null || firstId === secondId) return null;
  const a = findRecord(firstId);
  const b = findRecord(secondId);
  if (!a || !b || a.kind !== "Line" || b.kind !== "Line") return null;
  const a1 = pointById(a.item.start_id);
  const a2 = pointById(a.item.end_id);
  const b1 = pointById(b.item.start_id);
  const b2 = pointById(b.item.end_id);
  if (!a1 || !a2 || !b1 || !b2) return null;
  const hit = lineIntersectMm(a1, a2, b1, b2);
  if (!hit) return null;
  if (hit.t <= 1e-6 || hit.t >= 1 - 1e-6 || hit.u <= 1e-6 || hit.u >= 1 - 1e-6) return null;
  return { lineA: firstId, lineB: secondId, cut: { x_mm: hit.x_mm, y_mm: hit.y_mm, z_mm: 0 } };
}

export async function commitTrimPreview(preview) {
  await refreshFrom(await api("/api/op", "POST", {
    op: "TrimLine",
    line_id: preview.lineId,
    keep_id: preview.keepId,
    x_mm: preview.cut.x_mm,
    y_mm: preview.cut.y_mm,
    z_mm: 0,
  }));
  setHint(preview.mode === "extend"
    ? t("done.extended")
    : t("done.trimmed"));
}

export async function commitBreak(preview) {
  const after = await api("/api/op", "POST", {
    op: "BreakCrossing",
    line_a_id: preview.lineA,
    line_b_id: preview.lineB,
  });
  await refreshFrom(after);
  S.pending = null;
  if (after.created_id != null) setSelection(after.created_id);
  setHint(t("done.broken"));
}

export async function finishInsertNode(targetId, xyz) {
  const after = await api("/api/op", "POST", {
    op: "InsertNode",
    target_id: targetId,
    x_mm: xyz.x_mm,
    y_mm: xyz.y_mm,
    z_mm: xyz.z_mm || 0,
  });
  await refreshFrom(after);
  if (after.created_id != null) setSelection(after.created_id);
  setHint(t("done.node"));
}

export async function commitFaceFromLines() {
  const lineIds = [...S.selectedIds].filter((id) => {
    const row = findRecord(id);
    return row && row.kind === "Line";
  });
  if (lineIds.length < 3) {
    setHint(t("hint.face.select"));
    return;
  }
  const after = await api("/api/op", "POST", {
    op: "AddFaceFromLines",
    line_ids: lineIds,
    label: labelValue(),
  });
  await refreshFrom(after);
  if (after.created_id != null) setSelection(after.created_id);
  setHint(t("done.face", { n: lineIds.length }));
}

export async function commitJoin() {
  const ids = [...S.selectedIds].filter((id) => {
    const row = findRecord(id);
    return row && (row.kind === "Line" || row.kind === "Polyline");
  });
  if (ids.length < 2) {
    setHint(t("hint.join.select"));
    return;
  }
  const after = await api("/api/op", "POST", {
    op: "JoinPolyline",
    entity_ids: ids,
    label: labelValue(),
  });
  await refreshFrom(after);
  if (after.created_id != null) setSelection(after.created_id);
  setHint(t("done.join", { n: ids.length }));
}

export async function commitSew() {
  if (S.selectedIds.size === 0) {
    setHint(t("hint.sew.select"));
    return;
  }
  const sewn = S.selectedIds.size;
  await refreshFrom(await api("/api/op", "POST", {
    op: "Sew",
    entity_ids: [...S.selectedIds],
    tolerance_mm: 1,
  }));
  setHint(t("done.sew", { entities: entities(sewn) }));
}

export async function commitSimplify() {
  const ids = [...S.selectedIds].filter((id) => {
    const row = findRecord(id);
    return row && (row.kind === "Face" || row.kind === "Polyline");
  });
  if (!ids.length) {
    setHint(t("hint.simplify.select"));
    return;
  }
  await refreshFrom(await api("/api/op", "POST", {
    op: "Simplify",
    entity_ids: ids,
  }));
  setHint(t("done.simplify", { entities: entities(ids.length) }));
}

export async function commitDelete() {
  if (S.pending) {
    setHint(t("hint.delete.pending"));
    return;
  }
  if (S.selectedIds.size === 0) {
    setHint(t("hint.selectFirst", { verb: "Delete" }));
    return;
  }
  const count = S.selectedIds.size;
  await refreshFrom(await api("/api/op", "POST", {
    op: "Delete",
    entity_ids: [...S.selectedIds],
  }));
  setHint(t("done.delete", { entities: entities(count) }));
}

function nearestVertexId(row, xyz) {
  const ids = row.item.point_ids || [];
  let best = null;
  let bestDist = Infinity;
  for (const id of ids) {
    const point = pointById(id);
    if (!point) continue;
    const dist = Math.hypot(point.x_mm - xyz.x_mm, point.y_mm - xyz.y_mm);
    if (dist < bestDist) {
      bestDist = dist;
      best = id;
    }
  }
  return bestDist < 800 ? best : null;
}

function cornerTarget(event) {
  const xyz = hitWorkplane(event);
  if (!xyz) return null;
  const picked = pickEntity(event);
  const row = findRecord(picked);
  if (row && (row.kind === "Face" || row.kind === "Polyline")) {
    const vertexId = nearestVertexId(row, xyz);
    if (vertexId != null) return { targetId: row.id, vertexId };
  }
  if (row && row.kind === "Point") {
    for (const candidate of catalog()) {
      if (candidate.kind !== "Face" && candidate.kind !== "Polyline") continue;
      if ((candidate.item.point_ids || []).includes(row.id)) {
        return { targetId: candidate.id, vertexId: row.id };
      }
    }
  }
  return null;
}

export async function finishCorner(kind, event) {
  const dist = activeLength();
  if (dist == null) {
    setHint(t(kind === "chamfer" ? "hint.chamfer.distance" : "hint.fillet.radius", {
      unit: displayUnit(),
    }));
    return;
  }
  const corner = cornerTarget(event);
  if (!corner) {
    setHint(t(kind === "chamfer" ? "hint.chamfer.corner" : "hint.fillet.corner"));
    return;
  }
  const body = kind === "chamfer"
    ? {
      op: "ChamferCorner",
      target_id: corner.targetId,
      vertex_id: corner.vertexId,
      distance_mm: dist,
    }
    : {
      op: "FilletCorner",
      target_id: corner.targetId,
      vertex_id: corner.vertexId,
      radius_mm: dist,
    };
  const after = await api("/api/op", "POST", body);
  await refreshFrom(after);
  clearTyped();
  setHint(t(kind === "chamfer" ? "done.chamfer" : "done.fillet"));
}
