// Unit tests for the scratchpad's pure client modules. Run: node --test tests/js
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  circumcircle,
  dist3,
  lineIntersectMm,
  projectT,
  rectCorners,
  regularPolygon,
  sampleArc,
  sampleCircle,
  vertexRef,
} from "../../src/apeCAD/scratchpad/static/js/geom.js";
import {
  pointInPolygon2d,
  segmentHitsRect,
  shapeQualifies,
} from "../../src/apeCAD/scratchpad/static/js/screen.js";

const p = (x, y, z = 0) => ({ x_mm: x, y_mm: y, z_mm: z });
const near = (actual, expected, tol = 1e-9) =>
  assert.ok(Math.abs(actual - expected) <= tol, `${actual} != ${expected}`);

test("dist3 treats a missing z as 0", () => {
  assert.equal(dist3({ x_mm: 0, y_mm: 0 }, p(3, 4)), 5);
});

test("sampleCircle closes on its start point", () => {
  const pts = sampleCircle(p(10, 0), 5, 8);
  assert.equal(pts.length, 9);
  near(pts[0].x_mm, pts[8].x_mm);
  near(pts[0].y_mm, pts[8].y_mm);
});

test("circumcircle of three points on the unit circle", () => {
  const c = circumcircle(p(1, 0), p(0, 1), p(-1, 0));
  near(c.x_mm, 0);
  near(c.y_mm, 0);
  near(c.radius, 1);
  assert.equal(circumcircle(p(0, 0), p(1, 1), p(2, 2)), null);
});

test("sampleArc passes through its mid point side", () => {
  const pts = sampleArc(p(1, 0), p(0, 1), p(-1, 0), 2);
  near(pts[1].x_mm, 0);
  near(pts[1].y_mm, 1);
  const below = sampleArc(p(1, 0), p(0, -1), p(-1, 0), 2);
  near(below[1].y_mm, -1);
});

test("sampleArc degrades to its three points when collinear", () => {
  const pts = sampleArc(p(0, 0), p(1, 0), p(2, 0));
  assert.deepEqual(pts, [p(0, 0), p(1, 0), p(2, 0)]);
});

test("regularPolygon starts at the rim point", () => {
  const pts = regularPolygon(p(0, 0), p(2, 0), 4);
  assert.equal(pts.length, 4);
  near(pts[0].x_mm, 2);
  near(pts[1].y_mm, 2);
});

test("lineIntersectMm returns parameters on both lines", () => {
  const hit = lineIntersectMm(p(0, 0), p(2, 0), p(1, -1), p(1, 1));
  near(hit.x_mm, 1);
  near(hit.t, 0.5);
  near(hit.u, 0.5);
  assert.equal(lineIntersectMm(p(0, 0), p(1, 0), p(0, 1), p(1, 1)), null);
});

test("projectT is 0 for a degenerate segment", () => {
  near(projectT(p(5, 5), p(0, 0), p(10, 0)), 0.5);
  assert.equal(projectT(p(5, 5), p(1, 1), p(1, 1)), 0);
});

const rect = { left: 0, top: 0, right: 10, bottom: 10 };
const xy = (x, y) => ({ x, y });

test("window selection needs every point inside", () => {
  assert.ok(shapeQualifies([xy(1, 1), xy(9, 9)], false, false, rect));
  assert.ok(!shapeQualifies([xy(1, 1), xy(19, 9)], false, false, rect));
});

test("crossing selection takes a segment that only passes through", () => {
  assert.ok(segmentHitsRect(xy(-5, 5), xy(15, 5), rect));
  assert.ok(shapeQualifies([xy(-5, 5), xy(15, 5)], false, true, rect));
  assert.ok(!shapeQualifies([xy(-5, -5), xy(-1, -1)], false, true, rect));
});

test("crossing selection takes a closed shape that surrounds the window", () => {
  const big = [xy(-5, -5), xy(15, -5), xy(15, 15), xy(-5, 15)];
  assert.ok(pointInPolygon2d(xy(5, 5), big));
  assert.ok(shapeQualifies(big, true, true, rect));
  assert.ok(!shapeQualifies(big, false, false, rect));
});

test("vertexRef posts a snapped id, else coordinates (ADR 0030)", () => {
  assert.equal(vertexRef({ ...p(5, 6), entity_id: 7 }), 7);
  assert.deepEqual(vertexRef(p(5, 6, 2)), { xyz: [5, 6, 2] });
  assert.deepEqual(vertexRef({ x_mm: 5, y_mm: 6 }), { xyz: [5, 6, 0] });
});

test("rectCorners runs counter-clockwise from the min corner and refuses slivers", () => {
  assert.deepEqual(rectCorners(p(10, 20), p(0, 0)), [p(0, 0), p(10, 0), p(10, 20), p(0, 20)]);
  assert.equal(rectCorners(p(0, 0), p(10, 0.5)), null);
});
