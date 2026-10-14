// Transform tools: move, rotate, mirror, and linear / polar arrays of the selection.
import { S } from "./state.js";
import { entities, t } from "./strings.js";
import { api } from "./api.js";
import { activeLength, arrayCount, clearTyped, setHint } from "./cmdline.js";
import { refreshFrom } from "./render.js";
import { ghosts } from "./viewport.js";

export async function finishMove(end) {
  const dx = end.x_mm - S.pending.a.x_mm;
  const dy = end.y_mm - S.pending.a.y_mm;
  const dz = (end.z_mm || 0) - (S.pending.a.z_mm || 0);
  if (Math.hypot(dx, dy, dz) < 1) {
    S.pending = null;
    ghosts.clear();
    setHint(t("done.moveCancelled"));
    return;
  }
  await refreshFrom(await api("/api/op", "POST", {
    op: "Translate",
    entity_ids: [...S.selectedIds],
    dx_mm: dx,
    dy_mm: dy,
    dz_mm: dz,
  }));
  S.pending = null;
  clearTyped();
  ghosts.clear();
  S.ghostDims = [];
  setHint(t("done.moved", { entities: entities(S.selectedIds.size) }));
}

export async function finishRotate(pivot, angleDeg) {
  await refreshFrom(await api("/api/op", "POST", {
    op: "Rotate",
    entity_ids: [...S.selectedIds],
    origin_x_mm: pivot.x_mm,
    origin_y_mm: pivot.y_mm,
    angle_deg: angleDeg,
  }));
  S.pending = null;
  clearTyped();
  ghosts.clear();
  S.ghostDims = [];
  setHint(t("done.rotated", { entities: entities(S.selectedIds.size) }));
}

export async function finishMirror(axisA, axisB) {
  await refreshFrom(await api("/api/op", "POST", {
    op: "Mirror",
    entity_ids: [...S.selectedIds],
    ax_mm: axisA.x_mm,
    ay_mm: axisA.y_mm,
    bx_mm: axisB.x_mm,
    by_mm: axisB.y_mm,
  }));
  S.pending = null;
  clearTyped();
  ghosts.clear();
  S.ghostDims = [];
  setHint(t("done.mirrored", { entities: entities(S.selectedIds.size) }));
}

export async function finishArray(end) {
  const copies = arrayCount() - 1;
  if (copies < 1) throw new Error(t("reason.arrayCount"));
  await refreshFrom(await api("/api/op", "POST", {
    op: "ArrayLinear",
    entity_ids: [...S.selectedIds],
    dx_mm: end.x_mm - S.pending.a.x_mm,
    dy_mm: end.y_mm - S.pending.a.y_mm,
    dz_mm: 0,
    copies,
  }));
  S.pending = null;
  clearTyped();
  ghosts.clear();
  S.ghostDims = [];
  setHint(t("done.arrayLinear", { n: arrayCount() }));
}

export async function finishPolar(center) {
  const typed = activeLength();
  await refreshFrom(await api("/api/op", "POST", {
    op: "ArrayPolar",
    entity_ids: [...S.selectedIds],
    origin_x_mm: center.x_mm,
    origin_y_mm: center.y_mm,
    count: arrayCount(),
    angle_deg: typed != null ? typed : 360,
  }));
  S.pending = null;
  clearTyped();
  ghosts.clear();
  S.ghostDims = [];
  setHint(t("done.arrayPolar", { n: arrayCount() }));
}
