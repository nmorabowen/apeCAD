// Unit tests for section-mode plan geometry. Run: node --test tests/js
import assert from "node:assert/strict";
import { test } from "node:test";

import { dashSegments, roundedRing } from "../../src/apeCAD/scratchpad/static/js/section-geom.js";

const p = (x, y) => ({ x_mm: x, y_mm: y, z_mm: 0 });

test("roundedRing keeps every point at the offset from the nearest centre", () => {
  const centres = [p(0, 0), p(500, 0), p(500, 200), p(0, 200)];
  const ring = roundedRing(centres, [13, 13, 13, 13]);
  assert.ok(ring.length > 8);
  for (const q of ring) {
    const gap = Math.min(...centres.map((c) => Math.hypot(q.x_mm - c.x_mm, q.y_mm - c.y_mm)));
    assert.ok(Math.abs(gap - 13) < 1e-9, `gap ${gap}`);
  }
  const xs = ring.map((q) => q.x_mm);
  const ys = ring.map((q) => q.y_mm);
  assert.ok(Math.abs(Math.min(...xs) + 13) < 1e-9 && Math.abs(Math.max(...xs) - 513) < 1e-9);
  assert.ok(Math.abs(Math.min(...ys) + 13) < 1e-9 && Math.abs(Math.max(...ys) - 213) < 1e-9);
});

test("roundedRing of two centres is a stadium", () => {
  const ring = roundedRing([p(0, 0), p(100, 0)], [5, 5]);
  const ys = ring.map((q) => q.y_mm);
  assert.ok(Math.abs(Math.max(...ys) - 5) < 1e-9 && Math.abs(Math.min(...ys) + 5) < 1e-9);
  assert.deepEqual(roundedRing([p(0, 0)], [5]), []);
});

test("dashSegments follows the pattern across vertices", () => {
  const dashes = dashSegments([p(0, 0), p(100, 0)], false, [30, 20]);
  assert.deepEqual(dashes.map(([a, b]) => [a.x_mm, b.x_mm]), [[0, 30], [50, 80]]);
  const ring = dashSegments([p(0, 0), p(10, 0), p(10, 10), p(0, 10)], true, [5, 5]);
  const on = ring.reduce((sum, [a, b]) => sum + Math.hypot(b.x_mm - a.x_mm, b.y_mm - a.y_mm), 0);
  assert.ok(Math.abs(on - 20) < 1e-9);
  const dashDot = dashSegments([p(0, 0), p(200, 0)], false, [100, 20, 10, 20]);
  assert.deepEqual(dashDot.map(([a, b]) => [a.x_mm, b.x_mm]), [[0, 100], [120, 130], [150, 200]]);
  assert.deepEqual(dashSegments([p(0, 0)], false, [1, 1]), []);
});
