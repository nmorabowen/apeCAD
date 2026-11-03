// The 2-D client edits v2 (C5 record §3 "Editing", §4 invariants 9-11; ADR 0039, 0040; C5-S4).
// `create(container, {version: 2})` swaps v1's outline tools for `AddSectionFace` (rect,
// polygon, circle) and `AddFaceHole` (hole), hides edge bars (v1-only), selects a template as
// one unit, and deletes or explodes it. The client never expands a template and never checks
// the lock itself: the server refuses (`TEMPLATE_LOCKED`) and the client shows its message.
// Pure apart from the editor context it is given: no DOM, no canvas, no module-scope state.

import { displayList, pointInPolygon } from "./display2d.js";

export const EDIT_VERSIONS = Object.freeze([1, 2]);

// v2 mode's tool ids: v1's, with Opening replaced by Hole, a Circle added, Edge bars hidden.
export const TOOLS_V2 = Object.freeze([
  ["select", "Select"], ["rect", "Rectangle"], ["polygon", "Polygon"], ["circle", "Circle"], ["hole", "Hole"],
  ["wall-chain", "Wall chain"], ["wall-leg", "Wall leg"], ["cover", "Cover"],
  ["bar", "Bar"], ["bar-row", "Bar row"], ["hoop", "Hoop"], ["crosstie", "Crosstie"], ["delete", "Delete"],
].map((t) => Object.freeze(t)));

// A polygon or hole gesture takes at most this many points; the next one is refused by name.
export const MAX_GESTURE_POINTS = 10000;

function describe(value) {
  if (typeof value === "string") return JSON.stringify(value);
  if (typeof value === "number" || typeof value === "boolean" || typeof value === "bigint") return String(value);
  try { return JSON.stringify(value) ?? String(value); } catch { return String(value); }
}

// `opts.version` of `create`: absent or null is 1; 1 and 2 are read; anything else is refused.
export function editVersion(value) {
  if (value === undefined || value === null) return 1;
  if (Number.isInteger(value) && EDIT_VERSIONS.includes(value)) return value;
  throw new Error(`APECADSection.create: version ${describe(value)} is not supported, expected 1 or 2`);
}

export const refusalText = (res) => `Refused: ${res?.error?.message || "the operation was refused"}`;

// Why `draft` is not a v2 section-draft, or null when it is. A v2 editor hands nothing else to
// getDraft or onChange: a transport that dropped `version` answers v1, and that is refused.
export function v2DraftProblem(draft) {
  if (!draft || typeof draft !== "object" || Array.isArray(draft)) return `the transport's draft is ${describe(draft ?? null)}, not an apeCAD.section-draft object`;
  if (draft.schema !== "apeCAD.section-draft" || draft.version !== 2) {
    return `the transport answered a v2 draft request with ${describe(draft.schema ?? null)} version ${describe(draft.version ?? null)}; a v2 editor takes apeCAD.section-draft version 2 only`;
  }
  return null;
}

// `res` (a change that landed) followed by `{action: "draft", version: 2}`: `res` plus `draft`,
// or `draft: null` and a named `draft_refusal` (a refused, failed or non-v2 draft). The landed
// change still shows. When `isCurrent()` turns false while the draft is in flight (a newer
// change began), the result is `stale` and the caller drops it: an old draft never wins.
export async function followWithDraft(transport, res, isCurrent) {
  if (!res || !res.ok) return res;
  const refused = (code, message) => ({ ...res, draft: null, draft_refusal: { code, message } });
  let out;
  try {
    out = await transport({ action: "draft", version: 2 });
  } catch (err) {
    return isCurrent() ? refused("TRANSPORT_ERROR", `the draft request failed: ${err?.message ?? describe(err)}`) : { ...res, stale: true };
  }
  if (!isCurrent()) return { ...res, stale: true };
  if (!out || !out.ok) return refused(out?.error?.code || "REFUSED", out?.error?.message || "the draft request was refused");
  const problem = v2DraftProblem(out.draft);
  return problem ? refused("INVALID_ARGUMENT", problem) : { ...res, draft: out.draft };
}

// child id (and the template's own id) -> the template item; one pass per scene object.
const INDEX = new WeakMap();
export function templateIndex(scene) {
  let index = scene ? INDEX.get(scene) : null;
  if (index) return index;
  index = new Map();
  for (const t of scene?.templates || []) {
    for (const child of t.child_ids || []) index.set(child, t);
    index.set(t.id ?? t.entity_id, t);
  }
  if (scene) INDEX.set(scene, index);
  return index;
}

export const templateOf = (scene, id) => (id == null ? null : templateIndex(scene).get(id) ?? null);

// The props panel of a selected template: name, version, params, and that it is locked.
export function templateLines(t) {
  const id = t.id ?? t.entity_id;
  const lines = [`Template #${id} (${t.template} v${t.template_version}) · locked`];
  for (const [key, value] of Object.entries(t.params || {})) lines.push(`${key} = ${describe(value)}`);
  lines.push(`${(t.child_ids || []).length} children: edit its params, Delete it or Explode it`);
  return lines;
}

const inLoop = (pt, loop) => (loop.ring ? pointInPolygon(pt, loop.ring) : Math.hypot(pt[0] - loop.centre[0], pt[1] - loop.centre[1]) < loop.radius);

// The face on top at `pt` (void over steel over concrete), holes excluded, or null.
export function faceAt(scene, pt) {
  const { entries } = displayList(scene);
  for (let i = entries.length - 1; i >= 0; i--) {
    const e = entries[i];
    if (!e.loops) continue;
    const [outer, ...holes] = e.loops;
    if (inLoop(pt, outer) && !holes.some((h) => inLoop(pt, h))) return { kind: e.kind, id: e.id, role: e.layer };
  }
  return null;
}

const xyz = (p) => ({ xyz: [p[0], p[1], 0] });

function faceOp(params, shape) {
  const role = String(params.role || "concrete");
  return { op: "AddSectionFace", role, material: role === "void" ? null : String(params.material || "concrete"), ...shape };
}

export const ringFaceOp = (params, ring) => faceOp(params, { point_ids: ring.map(xyz) });
export const circleFaceOp = (params, centre, radius) => faceOp(params, { center_id: xyz(centre), radius_mm: radius });
export const holeOp = (faceId, ring) => ({ op: "AddFaceHole", face_id: faceId, point_ids: ring.map(xyz) });

function circleRing(centre, radius, n = 64) {
  return Array.from({ length: n }, (_, i) => [centre[0] + radius * Math.cos((2 * Math.PI * i) / n), centre[1] + radius * Math.sin((2 * Math.PI * i) / n)]);
}

// The v2 half of the editor. `ctx` is the editor's own state:
// {getScene, params, selectedIds, gesture(), clearGesture(), applyOp, prompt(text), hitAt(pt)}.
export function createV2Tools(ctx) {
  let selectedTemplate = null;
  let holeFace = null; // the face the hole gesture's first point fell in

  const select = (hit) => {
    ctx.selectedIds.clear();
    selectedTemplate = null;
    const template = hit ? templateOf(ctx.getScene(), hit.id) : null;
    if (template) {
      selectedTemplate = template.id ?? template.entity_id;
      for (const child of template.child_ids || []) ctx.selectedIds.add(child);
    } else if (hit && hit.id != null) {
      ctx.selectedIds.add(hit.id);
    }
  };

  // The ids a Delete removes: a template child's whole template (`Delete{template_id}`).
  const deletionIds = (id = null) => {
    if (id == null && selectedTemplate != null) return [selectedTemplate];
    if (id == null) return Array.from(ctx.selectedIds);
    const template = templateOf(ctx.getScene(), id);
    return [template ? template.id ?? template.entity_id : id];
  };

  const pushPoint = (pt) => {
    const pts = ctx.gesture();
    if (pts.length >= MAX_GESTURE_POINTS) {
      ctx.prompt(`Refused: a polygon takes at most ${MAX_GESTURE_POINTS} points; press Enter to close it or Esc to drop it`);
      return;
    }
    pts.push(pt);
  };

  // `hit` is the click's hit, or for a typed point the hit at that point (`hitAt`).
  async function point(tool, pt, hit) {
    const params = ctx.params;
    if (tool === "select") {
      select(hit);
    } else if (tool === "delete") {
      const ids = deletionIds(hit?.id ?? null);
      ctx.selectedIds.clear();
      selectedTemplate = null;
      if (ids.length) await ctx.applyOp({ op: "Delete", entity_ids: ids });
    } else if (tool === "rect") {
      const pts = ctx.gesture();
      pts.push(pt);
      if (pts.length < 2) return true;
      const [p0, p1] = pts;
      ctx.clearGesture();
      const x0 = Math.min(p0[0], p1[0]), x1 = Math.max(p0[0], p1[0]);
      const y0 = Math.min(p0[1], p1[1]), y1 = Math.max(p0[1], p1[1]);
      if (x1 > x0 && y1 > y0) await ctx.applyOp(ringFaceOp(params, [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]));
    } else if (tool === "circle") {
      const pts = ctx.gesture();
      pts.push(pt);
      if (pts.length < 2) return true;
      const [c, edge] = pts;
      ctx.clearGesture();
      const radius = Math.hypot(edge[0] - c[0], edge[1] - c[1]);
      if (radius > 0) await ctx.applyOp(circleFaceOp(params, c, radius));
    } else if (tool === "polygon") {
      pushPoint(pt);
    } else if (tool === "hole") {
      if (ctx.gesture().length === 0) {
        const face = faceAt(ctx.getScene(), pt);
        if (!face) { ctx.prompt("Hole: start inside a face"); return true; }
        holeFace = face.id;
      }
      pushPoint(pt);
    } else if (tool === "cover") {
      const scene = ctx.getScene();
      const onFace = hit && (hit.kind === "SectionFace" || hit.kind === "ConcreteFace") ? hit.id : faceAt(scene, pt)?.id;
      const faceId = onFace ?? scene.section_faces[0]?.id ?? scene.concrete_faces[0]?.id;
      if (faceId != null) {
        await ctx.applyOp({ op: "SetCover", face_id: faceId, cover_mm: Number(params.cover_mm || 25), tie_diameter_mm: Number(params.tie_diameter_mm || 10), bar_diameter_mm: Number(params.bar_diameter_mm || 16) });
      }
    } else {
      return false; // v1's handler: wall chain, wall leg, bar, bar row, hoop, crosstie
    }
    return true;
  }

  async function commit(tool) {
    const pts = ctx.gesture();
    if ((tool !== "polygon" && tool !== "hole") || pts.length < 3) return false;
    const ring = pts.slice(), faceId = holeFace;
    ctx.clearGesture();
    holeFace = null;
    if (tool === "polygon") await ctx.applyOp(ringFaceOp(ctx.params, ring));
    else if (faceId != null) await ctx.applyOp(holeOp(faceId, ring));
    return true;
  }

  function ghost(tool, cursor) {
    const pts = ctx.gesture();
    if (tool === "circle" && pts.length === 1) {
      const r = Math.hypot(cursor[0] - pts[0][0], cursor[1] - pts[0][1]);
      return r > 0 ? { ring: circleRing(pts[0], r) } : null;
    }
    if ((tool === "polygon" || tool === "hole") && pts.length >= 1) return { ring: [...pts, cursor] };
    return undefined; // v1's ghost
  }

  async function explode() {
    if (selectedTemplate == null) { ctx.prompt("Explode: select a template first"); return null; }
    const templateId = selectedTemplate;
    ctx.selectedIds.clear();
    selectedTemplate = null;
    return ctx.applyOp({ op: "ExplodeSectionTemplate", template_id: templateId });
  }

  // The props lines of the selection, or null for v1's title.
  function props() {
    const template = selectedTemplate == null ? null : templateOf(ctx.getScene(), selectedTemplate);
    return template ? templateLines(template) : null;
  }

  return { point, commit, ghost, explode, props, select, deletionIds, hitAt: ctx.hitAt, reset() { holeFace = null; } };
}
