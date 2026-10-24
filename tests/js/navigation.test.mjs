// Node unit tests for static/js/navigation.js (ADR 0037): Z-up zero-roll turntable basis,
// cursor-pivot orbit, zoom-to-cursor, pan-keep-point, and stage frustum offset.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  headingBasis,
  orbitAroundCursor,
  panKeepPoint,
  vDot,
  viewOffsetForStage,
  zoomAtCursor,
} from "../../src/apeCAD/scratchpad/static/js/navigation.js";

const near = (a, b, tol = 1e-6) =>
  assert.ok(Math.abs(a - b) <= tol, `expected ${a} ≈ ${b} (tol=${tol})`);

const len3 = (v) => Math.hypot(v.x, v.y, v.z);

describe("headingBasis (zero-roll Z-up orthonormal frame)", () => {
  it("constructs an orthonormal basis with zero roll (right.z === 0)", () => {
    const { right, up, forward } = headingBasis([-1, 1, -0.8], [0, 0, 1]);
    near(len3(right), 1);
    near(len3(up), 1);
    near(len3(forward), 1);
    near(right.z, 0);
    near(vDot(right, up), 0);
    near(vDot(right, forward), 0);
    near(vDot(up, forward), 0);
  });

  it("handles exact +-Z pole views by falling back to +X right and +-Y up", () => {
    const top = headingBasis([0, 0, -1], [0, 0, 1]);
    near(top.right.x, 1);
    near(top.up.y, 1);
  });
});

describe("orbitAroundCursor", () => {
  it("keeps the 3D cursor pivot point at an invariant distance and preserves zero roll", () => {
    const eye = [1000, -1000, 1000];
    const target = [0, 0, 0];
    const pivot = [250, 120, 0];
    const res = orbitAroundCursor({
      eye,
      target,
      pivot,
      yawDeltaRad: Math.PI / 4,
      pitchDeltaRad: -0.15,
    });
    const dBefore = Math.hypot(eye[0] - pivot[0], eye[1] - pivot[1], eye[2] - pivot[2]);
    const dAfter = Math.hypot(
      res.eye.x - pivot[0],
      res.eye.y - pivot[1],
      res.eye.z - pivot[2],
    );
    near(dAfter, dBefore, 1e-5);
    near(res.right.z, 0, 1e-6);
  });

  it("clamps polar angle away from the +-Z poles", () => {
    const res = orbitAroundCursor({
      eye: [100, 0, 1000],
      target: [0, 0, 0],
      pivot: [0, 0, 0],
      yawDeltaRad: 0,
      pitchDeltaRad: -Math.PI,
      poleMarginRad: 0.05,
    });
    const dx = res.eye.x - res.target.x;
    const dy = res.eye.y - res.target.y;
    const dz = res.eye.z - res.target.z;
    const dist = Math.hypot(dx, dy, dz);
    assert.ok(dz / dist <= Math.cos(0.05) + 1e-6);
  });
});

describe("zoomAtCursor & panKeepPoint", () => {
  it("zoomAtCursor scales eye and target homothetically around the cursor pivot", () => {
    const pivot = [400, -200, 0];
    const res = zoomAtCursor({
      eye: [400, -1200, 1000],
      target: [0, 0, 0],
      pivot,
      zoomFactor: 0.5,
    });
    near(res.scale, 0.5);
    near(res.eye.x - pivot[0], 0);
    near(res.eye.y - pivot[1], -500);
    near(res.eye.z - pivot[2], 500);
    near(res.target.x - pivot[0], -200);
    near(res.target.y - pivot[1], 100);
  });

  it("panKeepPoint translates eye and target by identical world offsets", () => {
    const { right, up } = headingBasis([0, 1, 0], [0, 0, 1]);
    const res = panKeepPoint({
      eye: [0, -1000, 0],
      target: [0, 0, 0],
      right,
      up,
      worldPerPixelX: 2,
      worldPerPixelY: 2,
      dxPx: 10,
      dyPx: -5,
    });
    near(res.eye.x - res.target.x, 0);
    near(res.eye.y - res.target.y, -1000);
    near(res.target.x, -20);
    near(res.target.z, -10);
  });

  it("viewOffsetForStage shifts optical center left when right dock overlaps stage", () => {
    const off = viewOffsetForStage(
      { left: 0, top: 0, width: 1000, height: 800 },
      { left: 760, top: 0, width: 240, height: 800 },
    );
    near(off.offsetX, 120);
    near(off.fullWidth, 1000);
  });
});
