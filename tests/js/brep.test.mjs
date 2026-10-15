// Unit tests for the B-rep queries over a scene payload. Run: node --test tests/js
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  brepRoots,
  catalog,
  curveWorldPoints,
  descendantIds,
  findRecord,
  gatherPoints,
  indexBrep,
  outlinerChildren,
  owningSolidId,
  rootId,
} from "../../src/apeCAD/scratchpad/static/js/brep.js";
import { S } from "../../src/apeCAD/scratchpad/static/js/state.js";

const pt = (id, x, y, z = 0) => ({ entity_id: id, x_mm: x, y_mm: y, z_mm: z, label: null });
const ln = (id, a, b) => ({ entity_id: id, start_id: a, end_id: b, label: null });

// A unit square face (points 1-4, edges 5-8, face 9) plus a loose line 11 between points 10, 12.
function squareScene() {
  return {
    points: [pt(1, 0, 0), pt(2, 100, 0), pt(3, 100, 100), pt(4, 0, 100), pt(10, 500, 0), pt(12, 600, 0)],
    lines: [ln(5, 1, 2), ln(6, 2, 3), ln(7, 3, 4), ln(8, 4, 1), ln(11, 10, 12)],
    faces: [{ entity_id: 9, point_ids: [1, 2, 3, 4], label: "slab" }],
    polylines: [], boxes: [], solids: [], circles: [], arcs: [], ellipses: [], beziers: [],
  };
}

test("catalog lists every entity sorted by id, with B-rep names", () => {
  S.sceneState = squareScene();
  const rows = catalog();
  assert.deepEqual(rows.map((row) => row.id), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]);
  assert.equal(findRecord(5).name, "Edge");
  assert.equal(findRecord(1).name, "Vertex");
  assert.equal(findRecord(9).name, "slab");
});

test("local fallback nests edges under the face and vertices under edges", () => {
  S.sceneState = squareScene();
  indexBrep();
  assert.deepEqual(S.brepChildrenOf.get(9), [5, 6, 7, 8]);
  assert.deepEqual(S.brepChildrenOf.get(5), [1, 2]);
  assert.equal(rootId(1), 9);
  assert.equal(rootId(10), 11);
  assert.deepEqual(brepRoots().map((row) => row.id), [9, 11]);
  assert.deepEqual(descendantIds(9).sort((a, b) => a - b), [1, 2, 3, 4, 5, 6, 7, 8]);
  assert.equal(owningSolidId(1), null);
});

test("the server brep block wins over the local fallback", () => {
  S.sceneState = {
    ...squareScene(),
    solids: [{ entity_id: 20, face_id: 9, distance_mm: 50, label: null }],
    brep: {
      children: { 20: [9], 9: [5, 6, 7, 8], 5: [1, 2] },
      parents: { 9: [20], 5: [9], 1: [5] },
      root: { 20: 20, 9: 20, 5: 20, 1: 20 },
      solid: { 9: 20, 5: 20, 1: 20 },
    },
  };
  indexBrep();
  assert.equal(rootId(1), 20);
  assert.equal(owningSolidId(5), 20);
  assert.equal(owningSolidId(20), 20);
  assert.deepEqual(S.brepChildrenOf.get(20), [9]);
});

test("gatherPoints and curveWorldPoints read point records", () => {
  S.sceneState = squareScene();
  indexBrep();
  assert.equal(gatherPoints(findRecord(9)).length, 8);
  const shape = curveWorldPoints(findRecord(11));
  assert.equal(shape.closed, false);
  assert.deepEqual(shape.pts.map((p) => p.x_mm), [500, 600]);
});

test("outlinerChildren hides nested Vertex rows except under the Point filter", () => {
  const kids = [{ id: 1, kind: "Point" }, { id: 5, kind: "Line" }, { id: 2, kind: "Point" }];
  assert.deepEqual(outlinerChildren(kids, "element").map((row) => row.id), [5]);
  assert.deepEqual(outlinerChildren(kids, "section").map((row) => row.id), [5]);
  assert.deepEqual(outlinerChildren(kids, "point").map((row) => row.id), [1, 5, 2]);
  assert.deepEqual(outlinerChildren([], "element"), []);
});
