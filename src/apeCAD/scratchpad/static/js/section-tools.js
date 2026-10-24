// Section-mode authoring tool actions in the main scratchpad (ADR 0024): concrete outline, wall
// chain, wall leg, cover guide, bar, bar row, bars along edge, hoop, and crosstie.
import { S } from "./state.js";
import { t } from "./strings.js";
import { api } from "./api.js";
import { clearTyped, labelValue, refuse, setHint } from "./cmdline.js";
import { dist3 } from "./geom.js";
import { pickByFilter } from "./pick.js";
import { refreshFrom } from "./render.js";
import {
  SECTION_TOOLS,
  activeConcreteFaceId,
  bindSectionBar,
  clearGhosts,
  constrainedPoint,
  diaMm,
  ensureTopViewOnFirstSectionOp,
  isSectionTool,
  legHorizontalPayload,
  nearestFaceEdge,
  pickBarAt,
  pointSpec,
  selectedBarIds,
  syncSectionBar,
  updateSectionGhost,
} from "./section-ghosts.js";
import { SNAP_APERTURE_MM, hitWorkplane } from "./snap.js";

export {
  SECTION_TOOLS,
  bindSectionBar,
  clearGhosts,
  diaMm,
  isSectionTool,
  syncSectionBar,
  updateSectionGhost,
};

export async function applyCoverToFace(faceId) {
  await refreshFrom(await api("/api/op", "POST", {
    op: "SetCover",
    face_id: faceId,
    cover_mm: S.sec.coverMm,
    tie_diameter_mm: diaMm(S.sec.tieDia),
    bar_diameter_mm: diaMm(S.sec.barDia),
  }));
  setHint(t("done.coverGuide", { cover: S.sec.coverMm }));
}

export async function applyHoopToBars(barIds) {
  await refreshFrom(await api("/api/op", "POST", {
    op: "AddHoop",
    bar_ids: barIds,
    designation: S.sec.tieDia,
    spacing_mm: S.sec.tieSpacingMm,
    hooks: "135",
    label: labelValue(),
  }));
  S.pending = null;
  clearGhosts();
  setHint(t("done.hoop", { dia: S.sec.tieDia, spacing: S.sec.tieSpacingMm }));
}

export function onStartSectionTool(tool) {
  syncSectionBar();
  if (tool === "cover-guide") {
    const faceId = activeConcreteFaceId();
    if (faceId != null) {
      applyCoverToFace(faceId).catch((error) => refuse(error));
      return true;
    }
  }
  if (tool === "hoop") {
    const bars = selectedBarIds();
    if (bars.length >= 3) {
      applyHoopToBars(bars).catch((error) => refuse(error));
      return true;
    }
  }
  return false;
}

export async function finishSectionOutline(pts) {
  let ring = pts;
  if (pts.length === 2) {
    const [a, b] = pts;
    const x0 = Math.min(a.x_mm, b.x_mm), y0 = Math.min(a.y_mm, b.y_mm);
    const x1 = Math.max(a.x_mm, b.x_mm), y1 = Math.max(a.y_mm, b.y_mm);
    ring = [
      { x_mm: x0, y_mm: y0, z_mm: 0 },
      { x_mm: x1, y_mm: y0, z_mm: 0 },
      { x_mm: x1, y_mm: y1, z_mm: 0 },
      { x_mm: x0, y_mm: y1, z_mm: 0 },
    ];
  }
  const scene = await api("/api/op", "POST", {
    op: "AddSectionOutline",
    point_ids: ring.map(pointSpec),
    material: S.sec.material,
    label: labelValue(),
  });
  S.pending = null;
  clearTyped();
  clearGhosts();
  await refreshFrom(scene);
  ensureTopViewOnFirstSectionOp();
  setHint(t("done.sectionOutline"));
}

export async function finishWallChain(pts) {
  const scene = await api("/api/op", "POST", {
    op: "AddWallChain",
    point_ids: pts.map(pointSpec),
    thickness_mm: [S.sec.thicknessMm],
    material: S.sec.material,
    horizontal: legHorizontalPayload(),
    label: labelValue(),
  });
  S.pending = null;
  clearTyped();
  clearGhosts();
  await refreshFrom(scene);
  ensureTopViewOnFirstSectionOp();
  setHint(t("done.wallChain"));
}

export async function onSectionClick(event) {
  const hit = hitWorkplane(event);
  if (S.tool === "section-outline") {
    if (!hit) return;
    if (!S.pending) {
      S.pending = { kind: "section-outline", pts: [hit] };
      setHint(t("hint.sectionOutline.next"));
      return;
    }
    const pts = S.pending.pts;
    if (pts.length >= 3 && dist3(pts[0], hit) <= SNAP_APERTURE_MM) {
      await finishSectionOutline(pts);
      return;
    }
    pts.push(constrainedPoint(pts[pts.length - 1], hit, event));
    clearTyped();
    setHint(t("hint.sectionOutline.next"));
    return;
  }

  if (S.tool === "wall-chain") {
    if (!hit) return;
    if (!S.pending) {
      S.pending = { kind: "wall-chain", pts: [hit] };
      setHint(t("hint.wallChain.next"));
      return;
    }
    const pts = S.pending.pts;
    pts.push(constrainedPoint(pts[pts.length - 1], hit, event));
    clearTyped();
    setHint(t("hint.wallChain.next"));
    return;
  }

  if (S.tool === "wall-leg") {
    if (!hit) return;
    const faceId = activeConcreteFaceId();
    if (faceId == null) {
      setHint(t("hint.cover.pickFace"));
      return;
    }
    if (!S.pending) {
      S.pending = { kind: "wall-leg", a: hit };
      setHint(t("hint.wallLeg.end"));
      return;
    }
    const end = constrainedPoint(S.pending.a, hit, event);
    const scene = await api("/api/op", "POST", {
      op: "AddWallLeg",
      start_id: pointSpec(S.pending.a),
      end_id: pointSpec(end),
      thickness_mm: S.sec.thicknessMm,
      face_id: faceId,
      horizontal: legHorizontalPayload(),
      label: labelValue(),
    });
    S.pending = null;
    clearTyped();
    clearGhosts();
    await refreshFrom(scene);
    setHint(t("done.wallLeg"));
    return;
  }

  if (S.tool === "cover-guide") {
    const picked = pickByFilter(event, "section");
    const faceId = (S.sceneState.concrete_faces || []).some((f) => f.entity_id === picked)
      ? picked
      : activeConcreteFaceId();
    if (faceId == null) {
      setHint(t("hint.cover.pickFace"));
      return;
    }
    await applyCoverToFace(faceId);
    return;
  }

  if (S.tool === "bar") {
    if (!hit) return;
    clearGhosts();
    await refreshFrom(await api("/api/op", "POST", {
      op: "AddBar",
      x_mm: hit.x_mm,
      y_mm: hit.y_mm,
      designation: S.sec.barDia,
      label: labelValue(),
    }));
    setHint(t("done.bar", { dia: S.sec.barDia }));
    return;
  }

  if (S.tool === "bar-row") {
    if (!hit) return;
    if (!S.pending) {
      S.pending = { kind: "bar-row", a: hit };
      setHint(t("hint.barRow.end"));
      return;
    }
    const end = constrainedPoint(S.pending.a, hit, event);
    const beforeCount = (S.sceneState.bars || []).length;
    const body = {
      op: "AddBarRow",
      start_x_mm: S.pending.a.x_mm,
      start_y_mm: S.pending.a.y_mm,
      end_x_mm: end.x_mm,
      end_y_mm: end.y_mm,
      designation: S.sec.barDia,
    };
    if (S.sec.mode === "count") body.count = Math.max(2, Math.round(S.sec.count));
    else body.spacing_mm = S.sec.spacingMm;
    const scene = await api("/api/op", "POST", body);
    S.pending = null;
    clearTyped();
    clearGhosts();
    await refreshFrom(scene);
    const added = Math.max(0, (scene.bars || []).length - beforeCount);
    setHint(t("done.barRow", { n: added, dia: S.sec.barDia }));
    return;
  }

  if (S.tool === "bars-edge") {
    const edge = nearestFaceEdge(hit);
    if (!edge) {
      setHint(t("hint.barsEdge.pickEdge"));
      return;
    }
    const beforeCount = (S.sceneState.bars || []).length;
    const body = {
      op: "AddBarsAlongEdge",
      face_id: edge.faceId,
      edge_index: edge.edgeIndex,
      designation: S.sec.barDia,
    };
    if (S.sec.mode === "count") body.count = Math.max(2, Math.round(S.sec.count));
    else body.spacing_mm = S.sec.spacingMm;
    clearGhosts();
    const scene = await api("/api/op", "POST", body);
    await refreshFrom(scene);
    const added = Math.max(0, (scene.bars || []).length - beforeCount);
    setHint(t("done.barsEdge", { n: added, dia: S.sec.barDia, edge: edge.edgeIndex }));
    return;
  }

  if (S.tool === "hoop") {
    const barId = pickBarAt(event, hit);
    if (barId == null) {
      setHint(t("hint.hoop.needThree"));
      return;
    }
    if (!S.pending || S.pending.kind !== "hoop") {
      S.pending = { kind: "hoop", barIds: [barId] };
      setHint(t("hint.hoop.next", { n: 1 }));
      return;
    }
    const ids = S.pending.barIds;
    if (ids.length >= 3 && ids[0] === barId) {
      await applyHoopToBars(ids);
      return;
    }
    const idx = ids.indexOf(barId);
    if (idx >= 0) ids.splice(idx, 1);
    else ids.push(barId);
    setHint(t("hint.hoop.next", { n: ids.length }));
    return;
  }

  if (S.tool === "crosstie") {
    const barId = pickBarAt(event, hit);
    if (barId == null) {
      setHint(t("hint.crosstie.pickBar"));
      return;
    }
    if (!S.pending || S.pending.kind !== "crosstie") {
      S.pending = { kind: "crosstie", barA: barId };
      setHint(t("hint.crosstie.second"));
      return;
    }
    await refreshFrom(await api("/api/op", "POST", {
      op: "AddCrosstie",
      bar_a_id: S.pending.barA,
      bar_b_id: barId,
      designation: S.sec.tieDia,
      spacing_mm: S.sec.tieSpacingMm,
      hooks: S.sec.hooks,
      label: labelValue(),
    }));
    S.pending = null;
    clearGhosts();
    setHint(t("done.crosstie", { dia: S.sec.tieDia, spacing: S.sec.tieSpacingMm }));
  }
}

export async function onSectionEnter(echoed) {
  const thickCmd = (echoed || "").match(/^t(?:hick(?:ness)?)?\s+(\d+(?:\.\d+)?)$/i);
  if (thickCmd) {
    S.sec.thicknessMm = Number(thickCmd[1]);
    syncSectionBar();
    clearTyped();
    setHint(t("done.thickness", { t: S.sec.thicknessMm }));
    return true;
  }
  if (!S.pending) return false;
  if (S.pending.kind === "section-outline" && S.pending.pts.length >= 2) {
    await finishSectionOutline(S.pending.pts);
    return true;
  }
  if (S.pending.kind === "wall-chain" && S.pending.pts.length >= 2) {
    await finishWallChain(S.pending.pts);
    return true;
  }
  if (S.pending.kind === "hoop") {
    if (S.pending.barIds.length < 3) {
      setHint(t("hint.hoop.needThree"));
      return true;
    }
    await applyHoopToBars(S.pending.barIds);
    return true;
  }
  return false;
}
