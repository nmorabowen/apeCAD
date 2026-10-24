// Read-only queries over the scene payload: the entity catalog and the B-rep tree the
// document ships (ADR 0018), with a local fallback when the payload has no `brep` block.
import { S } from "./state.js";
import { sampleArc, sampleBezier, sampleCircle, sampleEllipse } from "./geom.js";

export const SELECT_FILTERS = ["point", "line", "face", "solid", "element", "section"];

export const FILTER_KINDS = {
  point: new Set(["Point"]),
  line: new Set(["Line", "Polyline", "Arc", "Bezier"]),
  face: new Set(["Face", "Circle", "Ellipse"]),
  solid: new Set(["Solid", "Box"]),
  // Section mode (ADR 0024): each picks as itself, not as its points.
  section: new Set(["ConcreteFace", "Bar", "Hoop", "Crosstie", "WallLeg", "CoverGuide"]),
};

const SECTION_SOURCES = [
  ["ConcreteFace", "concrete_faces"],
  ["Bar", "bars"],
  ["Hoop", "hoops"],
  ["Crosstie", "crossties"],
  ["WallLeg", "wall_legs"],
  ["CoverGuide", "cover_guides"],
];

export function catalog() {
  const rows = [];
  const push = (kind, item) => {
    rows.push({
      id: item.entity_id,
      kind,
      name: item.label || item.designation || brepKind(kind),
      item,
    });
  };
  for (const item of S.sceneState.points || []) push("Point", item);
  for (const item of S.sceneState.lines || []) push("Line", item);
  for (const item of S.sceneState.polylines || []) push("Polyline", item);
  for (const item of S.sceneState.faces || []) push("Face", item);
  for (const item of S.sceneState.circles || []) push("Circle", item);
  for (const item of S.sceneState.arcs || []) push("Arc", item);
  for (const item of S.sceneState.ellipses || []) push("Ellipse", item);
  for (const item of S.sceneState.beziers || []) push("Bezier", item);
  for (const item of S.sceneState.boxes || []) push("Box", item);
  for (const item of S.sceneState.solids || []) push("Solid", item);
  for (const [kind, key] of SECTION_SOURCES) {
    for (const item of S.sceneState[key] || []) push(kind, item);
  }
  rows.sort((a, b) => a.id - b.id);
  return rows;
}

const SECTION_NAMES = { ConcreteFace: "Concrete", WallLeg: "Leg", CoverGuide: "Cover" };

export function brepKind(kind) {
  if (kind === "Point") return "Vertex";
  if (kind === "Line") return "Edge";
  return SECTION_NAMES[kind] || kind;
}

function lineConnecting(a, b) {
  return (S.sceneState.lines || []).find((line) => (
    (line.start_id === a && line.end_id === b)
    || (line.start_id === b && line.end_id === a)
  )) || null;
}

function brepChildrenLocal(row) {
  const byId = new Map(catalog().map((item) => [item.id, item]));
  const take = (id) => byId.get(id) || null;
  if (row.kind === "Solid") {
    const kids = [];
    const profile = take(row.item.face_id);
    if (profile) kids.push(profile);
    const cap = take(row.item.cap_id);
    if (cap) kids.push(cap);
    for (const wallId of row.item.wall_ids || []) {
      const wall = take(wallId);
      if (wall) kids.push(wall);
    }
    return kids;
  }
  if (row.kind === "Face") {
    const ids = row.item.point_ids || [];
    if (ids.length < 2) return ids.map(take).filter(Boolean);
    const edges = [];
    for (let i = 0; i < ids.length; i += 1) {
      const line = lineConnecting(ids[i], ids[(i + 1) % ids.length]);
      if (!line) return ids.map(take).filter(Boolean);
      edges.push(byId.get(line.entity_id));
    }
    return edges.filter(Boolean);
  }
  if (row.kind === "Line") {
    return [take(row.item.start_id), take(row.item.end_id)].filter(Boolean);
  }
  if (row.kind === "Circle" || row.kind === "Ellipse") {
    const center = take(row.item.center_id);
    return center ? [center] : [];
  }
  if (row.kind === "Arc") {
    return [take(row.item.start_id), take(row.item.mid_id), take(row.item.end_id)].filter(Boolean);
  }
  if (row.kind === "Polyline" || row.kind === "Bezier") {
    return (row.item.point_ids || []).map(take).filter(Boolean);
  }
  return [];
}

export function brepChildren(row) {
  if (S.brepChildrenOf.has(row.id)) {
    return (S.brepChildrenOf.get(row.id) || []).map(findRecord).filter(Boolean);
  }
  return brepChildrenLocal(row);
}

// The outliner rows under `kids`: a nested Vertex row (a corner, a bar's point) shows only
// under the Point filter, as a bar's dot does on the canvas. Loose points are roots, not
// kids, so they always show. The B-rep itself (brepChildren, picking) is unchanged.
export function outlinerChildren(kids, filter) {
  return filter === "point" ? kids : kids.filter((row) => row.kind !== "Point");
}

export function collectNested(row, nested) {
  for (const child of brepChildren(row)) {
    nested.add(child.id);
    collectNested(child, nested);
  }
}

export function brepRoots() {
  const rows = catalog();
  const nested = new Set();
  for (const row of rows) collectNested(row, nested);
  const rank = {
    Solid: 0, Box: 1, Face: 2, Circle: 2, Ellipse: 2, ConcreteFace: 2,
    Polyline: 3, Bezier: 3, Arc: 3, Hoop: 3, Crosstie: 3, Bar: 4, Line: 4, Point: 5,
  };
  return rows
    .filter((row) => !nested.has(row.id))
    .sort((a, b) => (rank[a.kind] ?? 9) - (rank[b.kind] ?? 9) || a.id - b.id);
}

let _indexedSceneState = null;

export function indexBrep(force = false) {
  if (!force && _indexedSceneState === S.sceneState && S.brepRootOf.size > 0) {
    return;
  }
  _indexedSceneState = S.sceneState;
  S.brepChildrenOf = new Map();
  S.brepParentsOf = new Map();
  S.brepRootOf = new Map();
  S.brepSolidOf = new Map();
  const raw = S.sceneState.brep;
  if (raw && raw.children && raw.root) {
    for (const [key, kids] of Object.entries(raw.children)) {
      S.brepChildrenOf.set(Number(key), (kids || []).map(Number));
    }
    for (const [key, pars] of Object.entries(raw.parents || {})) {
      S.brepParentsOf.set(Number(key), (pars || []).map(Number));
    }
    for (const [key, value] of Object.entries(raw.root)) {
      S.brepRootOf.set(Number(key), Number(value));
    }
    for (const [key, value] of Object.entries(raw.solid || {})) {
      S.brepSolidOf.set(Number(key), Number(value));
    }
    return;
  }
  for (const row of catalog()) {
    const kids = brepChildrenLocal(row);
    S.brepChildrenOf.set(row.id, kids.map((child) => child.id));
    for (const child of kids) {
      const pars = S.brepParentsOf.get(child.id) || [];
      if (!pars.includes(row.id)) pars.push(row.id);
      S.brepParentsOf.set(child.id, pars);
    }
  }
  for (const row of catalog()) {
    S.brepRootOf.set(row.id, walkRoot(row.id));
    const owner = walkSolid(row.id);
    if (owner != null) S.brepSolidOf.set(row.id, owner);
  }
}

function walkRoot(id) {
  const seen = new Set();
  let current = id;
  while (true) {
    const pars = S.brepParentsOf.get(current) || [];
    if (!pars.length) return current;
    const solid = pars.find((pid) => {
      const row = findRecord(pid);
      return row && FILTER_KINDS.solid.has(row.kind);
    });
    const nxt = solid != null ? solid : pars[0];
    if (seen.has(nxt)) return current;
    seen.add(current);
    current = nxt;
  }
}

function walkSolid(id) {
  const row = findRecord(id);
  if (row && FILTER_KINDS.solid.has(row.kind)) return id;
  const stack = [...(S.brepParentsOf.get(id) || [])];
  const seen = new Set();
  while (stack.length) {
    const pid = stack.pop();
    if (seen.has(pid)) continue;
    seen.add(pid);
    const parent = findRecord(pid);
    if (parent && FILTER_KINDS.solid.has(parent.kind)) return pid;
    stack.push(...(S.brepParentsOf.get(pid) || []));
  }
  return null;
}

export function rootId(id) {
  return S.brepRootOf.has(id) ? S.brepRootOf.get(id) : id;
}

export function owningSolidId(id) {
  const row = findRecord(id);
  if (row && FILTER_KINDS.solid.has(row.kind)) return id;
  return S.brepSolidOf.has(id) ? S.brepSolidOf.get(id) : null;
}

export function gatherPoints(row, into = []) {
  if (row.kind === "Point") into.push(row.item);
  if (row.kind === "Box" && row.item.origin_xyz_mm && row.item.size_xyz_mm) {
    const o = row.item.origin_xyz_mm;
    const s = row.item.size_xyz_mm;
    into.push(
      { x_mm: o[0], y_mm: o[1], z_mm: o[2] },
      { x_mm: o[0] + s[0], y_mm: o[1] + s[1], z_mm: o[2] + s[2] },
    );
  }
  for (const child of brepChildren(row)) gatherPoints(child, into);
  return into;
}

export function findRecord(id) {
  return catalog().find((row) => row.id === id) || null;
}

export function isProfile(id) {
  const row = findRecord(id);
  return row != null && (row.kind === "Face" || row.kind === "Circle" || row.kind === "Ellipse");
}

export function profileWorldPoints(row) {
  if (row.kind === "Face") {
    return (row.item.point_ids || []).map(pointById).filter(Boolean);
  }
  if (row.kind === "Circle") {
    const center = pointById(row.item.center_id);
    if (!center) return [];
    return sampleCircle(center, row.item.radius_mm).slice(0, -1);
  }
  if (row.kind === "Ellipse") {
    const center = pointById(row.item.center_id);
    if (!center) return [];
    return sampleEllipse(center, row.item.radius_x_mm, row.item.radius_y_mm).slice(0, -1);
  }
  return [];
}

export function offsetPoints(pts, dx, dy, dz) {
  return pts.map((point) => ({
    x_mm: point.x_mm + dx,
    y_mm: point.y_mm + dy,
    z_mm: (point.z_mm || 0) + dz,
  }));
}

export function curveWorldPoints(row) {
  if (row.kind === "Line") {
    const start = pointById(row.item.start_id);
    const end = pointById(row.item.end_id);
    return start && end ? { pts: [start, end], closed: false } : null;
  }
  if (row.kind === "Polyline") {
    const pts = (row.item.point_ids || []).map(pointById).filter(Boolean);
    return pts.length >= 2 ? { pts, closed: Boolean(row.item.closed) } : null;
  }
  if (row.kind === "Bezier") {
    const pts = (row.item.point_ids || []).map(pointById).filter(Boolean);
    if (pts.length !== 4) return null;
    return { pts: sampleBezier(pts), closed: false };
  }
  if (row.kind === "Arc") {
    const start = pointById(row.item.start_id);
    const mid = pointById(row.item.mid_id);
    const end = pointById(row.item.end_id);
    if (!start || !mid || !end) return null;
    return { pts: sampleArc(start, mid, end), closed: false };
  }
  return null;
}

export function pointById(id) {
  return (S.sceneState.points || []).find((point) => point.entity_id === id) || null;
}

export function descendantIds(id) {
  const out = [];
  const stack = [...(S.brepChildrenOf.get(id) || [])];
  const seen = new Set();
  while (stack.length) {
    const childId = stack.pop();
    if (seen.has(childId)) continue;
    seen.add(childId);
    out.push(childId);
    stack.push(...(S.brepChildrenOf.get(childId) || []));
  }
  return out;
}

export function lineRows() {
  return catalog().filter((row) => row.kind === "Line");
}
