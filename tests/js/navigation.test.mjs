// Node unit tests for static/js/navigation.js (ADR 0037): Z-up zero-roll turntable basis,
// cursor-pivot orbit, zoom-to-cursor, pan-keep-point, and stage frustum offset.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  Navigator,
  applyStageViewOffset,
  bindCadNavigation,
  headingBasis,
  orbitAroundCursor,
  panKeepPoint,
  vDot,
  viewOffsetForStage,
  zoomAtCursor,
} from "../../src/apeCAD/scratchpad/static/js/navigation.js";
import * as navMath from "../../src/apeCAD/scratchpad/static/js/nav-math.js";
import { S } from "../../src/apeCAD/scratchpad/static/js/state.js";

const near = (a, b, tol = 1e-6) =>
  assert.ok(Math.abs(a - b) <= tol, `expected ${a} ≈ ${b} (tol=${tol})`);

const len3 = (v) => Math.hypot(v.x, v.y, v.z);

function makeMockCanvas(width = 800, height = 600) {
  const listeners = new Map();
  const captured = new Set();
  return {
    clientWidth: width,
    clientHeight: height,
    captured,
    getBoundingClientRect: () => ({ left: 0, top: 0, width, height }),
    addEventListener(type, fn) {
      if (!listeners.has(type)) listeners.set(type, new Set());
      listeners.get(type).add(fn);
    },
    removeEventListener(type, fn) {
      listeners.get(type)?.delete(fn);
    },
    setPointerCapture(id) {
      captured.add(id);
    },
    releasePointerCapture(id) {
      captured.delete(id);
    },
    emit(type, ev = {}) {
      const set = listeners.get(type);
      if (!set) return;
      for (const fn of [...set]) fn({ type, ...ev });
    },
    listenerCount(type) {
      return listeners.get(type)?.size || 0;
    },
  };
}

function makeMockCamera(x = 0, y = -1000, z = 500) {
  const lookTargets = [];
  return {
    position: {
      x,
      y,
      z,
      set(nx, ny, nz) {
        this.x = nx;
        this.y = ny;
        this.z = nz;
      },
    },
    up: {
      x: 0,
      y: 0,
      z: 1,
      set(nx, ny, nz) {
        this.x = nx;
        this.y = ny;
        this.z = nz;
      },
    },
    fov: 50,
    zoom: 1,
    lookTargets,
    lookAt(t) {
      lookTargets.push({ x: t.x, y: t.y, z: t.z });
    },
  };
}

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

describe("zoomAtCursor, panKeepPoint & applyStageViewOffset", () => {
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

  it("viewOffsetForStage and applyStageViewOffset shift and clear camera view offsets", () => {
    const stageRect = { left: 0, top: 0, width: 1000, height: 800 };
    const dockRect = { left: 760, top: 0, width: 240, height: 800 };
    const off = viewOffsetForStage(stageRect, dockRect);
    near(off.offsetX, 120);
    near(off.fullWidth, 1000);

    const makeOffsetCam = () => ({
      view: null,
      cleared: 0,
      setViewOffset(fullWidth, fullHeight, offsetX, offsetY, width, height) {
        this.view = { enabled: true, fullWidth, fullHeight, offsetX, offsetY, width, height };
      },
      clearViewOffset() {
        if (this.view) this.view.enabled = false;
        this.cleared += 1;
      },
    });
    const perspCam = makeOffsetCam();
    const orthoCam = makeOffsetCam();

    applyStageViewOffset([perspCam, orthoCam], stageRect, dockRect);
    assert.equal(perspCam.view.enabled, true);
    near(perspCam.view.offsetX, 120);
    near(orthoCam.view.offsetX, 120);

    // Closing the dock clears the view offset on both cameras.
    applyStageViewOffset([perspCam, orthoCam], stageRect, null);
    assert.equal(perspCam.view.enabled, false);
    assert.equal(orthoCam.view.enabled, false);
    assert.equal(perspCam.cleared, 1);
    assert.equal(orthoCam.cleared, 1);
  });
});

describe("Navigator class (ADR 0037 replacement for OrbitControls)", () => {
  it("ignores LMB when mouseButtons.LEFT === -1 and orbits on MMB around the 3D cursor pivot", () => {
    const canvas = makeMockCanvas();
    const cam = makeMockCamera(0, -1000, 500);
    const pivot = { x_mm: 200, y_mm: 100, z_mm: 0 };
    const nav = new Navigator(cam, canvas, {
      getPivot: () => pivot,
    });
    let changes = 0;
    nav.addEventListener("change", () => {
      changes += 1;
    });

    // LMB with mouseButtons.LEFT === -1 is completely ignored.
    canvas.emit("pointerdown", { button: 0, pointerId: 1, clientX: 100, clientY: 100 });
    canvas.emit("pointermove", { pointerId: 1, clientX: 150, clientY: 120 });
    canvas.emit("pointerup", { button: 0, pointerId: 1, clientX: 150, clientY: 120 });
    assert.equal(changes, 0);
    assert.equal(canvas.captured.size, 0);
    near(cam.position.x, 0);

    // MMB (button 1) captures pointer, orbits around cursor pivot, and dispatches "change".
    const dPivotBefore = Math.hypot(
      cam.position.x - pivot.x_mm,
      cam.position.y - pivot.y_mm,
      cam.position.z - pivot.z_mm,
    );
    canvas.emit("pointerdown", { button: 1, pointerId: 2, clientX: 200, clientY: 200 });
    assert.equal(canvas.captured.has(2), true);
    canvas.emit("pointermove", { pointerId: 2, clientX: 240, clientY: 180 });
    assert.equal(changes, 1);
    const dPivotAfter = Math.hypot(
      cam.position.x - pivot.x_mm,
      cam.position.y - pivot.y_mm,
      cam.position.z - pivot.z_mm,
    );
    near(dPivotAfter, dPivotBefore, 1e-5);
    assert.ok(cam.position.x < 0, "dragging right orbits camera toward -X so model rotates right");
    canvas.emit("pointerup", { button: 1, pointerId: 2, clientX: 240, clientY: 180 });
    assert.equal(canvas.captured.has(2), false);
  });

  it("pans on RMB, zooms toward cursor on wheel, and cleans up on pointercancel", () => {
    const canvas = makeMockCanvas();
    const cam = makeMockCamera(0, -1000, 0);
    const pivot = { x_mm: 300, y_mm: -100, z_mm: 0 };
    const nav = new Navigator(cam, canvas, {
      getPivot: () => pivot,
    });
    let changes = 0;
    nav.addEventListener("change", () => {
      changes += 1;
    });

    // RMB (button 2) pans eye and target identically.
    canvas.emit("pointerdown", { button: 2, pointerId: 5, clientX: 400, clientY: 300 });
    canvas.emit("pointermove", { pointerId: 5, clientX: 420, clientY: 290 });
    assert.equal(changes, 1);
    near(cam.position.x - nav.target.x, 0);
    near(cam.position.y - nav.target.y, -1000);
    assert.ok(nav.target.x < 0);

    // pointercancel terminates the active pan and releases pointer capture.
    canvas.emit("pointercancel", { pointerId: 5 });
    assert.equal(canvas.captured.has(5), false);
    const prevX = nav.target.x;
    canvas.emit("pointermove", { pointerId: 5, clientX: 500, clientY: 500 });
    near(nav.target.x, prevX);

    // Wheel zooms toward the 3D cursor pivot and dispatches "change".
    const prevChanges = changes;
    const distBefore = Math.hypot(
      cam.position.x - nav.target.x,
      cam.position.y - nav.target.y,
      cam.position.z - nav.target.z,
    );
    canvas.emit("wheel", { deltaY: -100, clientX: 400, clientY: 300 });
    assert.equal(changes, prevChanges + 1);
    const distAfter = Math.hypot(
      cam.position.x - nav.target.x,
      cam.position.y - nav.target.y,
      cam.position.z - nav.target.z,
    );
    near(distAfter, distBefore * 0.9, 1e-5);

    nav.dispose();
    assert.equal(canvas.listenerCount("pointerdown"), 0);
  });

  it("supports Alt+LMB orbit (mouseButtons.LEFT = 0), lostpointercapture cleanup, and view-plane pivot fallback", () => {
    const canvas = makeMockCanvas(800, 600);
    const cam = makeMockCamera(0, -1000, 0);
    // Simulate Front view where Z=0 workplane intersection returns null.
    const nav = new Navigator(cam, canvas, {
      getPivot: () => null,
    });
    let changes = 0;
    nav.addEventListener("change", () => {
      changes += 1;
    });

    // Enable Alt+LMB orbit as input.js does in capture phase.
    nav.mouseButtons.LEFT = 0;
    canvas.emit("pointerdown", { button: 0, pointerId: 7, clientX: 600, clientY: 150 });
    assert.equal(canvas.captured.has(7), true);

    // Secondary pointer events with a different pointerId do not hijack or cancel pointer 7.
    canvas.emit("pointerdown", { button: 2, pointerId: 8, clientX: 100, clientY: 100 });
    canvas.emit("pointercancel", { pointerId: 8 });
    assert.equal(canvas.captured.has(7), true);

    canvas.emit("pointermove", { pointerId: 7, clientX: 630, clientY: 140 });
    assert.equal(changes, 1);

    // lostpointercapture on active pointer 7 cleans up the gesture and resets mouseButtons.LEFT to -1.
    canvas.emit("lostpointercapture", { pointerId: 7 });
    assert.equal(canvas.captured.has(7), false);
    assert.equal(nav.mouseButtons.LEFT, -1);

    // Subsequent plain LMB (button: 0) pointerdown does not enter orbit mode.
    canvas.emit("pointerdown", { button: 0, pointerId: 9, clientX: 400, clientY: 300 });
    canvas.emit("pointermove", { pointerId: 9, clientX: 450, clientY: 320 });
    canvas.emit("pointerup", { button: 0, pointerId: 9, clientX: 450, clientY: 320 });
    assert.equal(changes, 1);
    assert.equal(canvas.captured.has(9), false);

    // Alt+LMB orbit terminated by pointerup or pointercancel also resets mouseButtons.LEFT to -1.
    for (const endEvent of ["pointerup", "pointercancel"]) {
      nav.mouseButtons.LEFT = 0;
      canvas.emit("pointerdown", { button: 0, pointerId: 10, clientX: 300, clientY: 200 });
      assert.equal(canvas.captured.has(10), true);
      canvas.emit("pointermove", { pointerId: 10, clientX: 320, clientY: 190 });
      const afterOrbit = changes;
      canvas.emit(endEvent, { button: 0, pointerId: 10, clientX: 320, clientY: 190 });
      assert.equal(nav.mouseButtons.LEFT, -1, `${endEvent} must reset mouseButtons.LEFT to -1`);
      assert.equal(canvas.captured.has(10), false);

      // Plain LMB drag immediately afterward is ignored by Navigator.
      canvas.emit("pointerdown", { button: 0, pointerId: 11, clientX: 320, clientY: 190 });
      canvas.emit("pointermove", { pointerId: 11, clientX: 360, clientY: 210 });
      canvas.emit("pointerup", { button: 0, pointerId: 11, clientX: 360, clientY: 210 });
      assert.equal(changes, afterOrbit);
    }

    // Wheel zoom with getPivot() === null uses the cursor's target-plane world coordinate.
    const beforeWheel = changes;
    canvas.emit("wheel", { deltaY: -100, clientX: 600, clientY: 150 });
    assert.equal(changes, beforeWheel + 1);
    assert.ok(nav.target.x > 0 && nav.target.z > 0, "zooms toward upper-right cursor on XZ view plane");
    nav.dispose();
  });

  it("bindCadNavigation resets mouseButtons.LEFT and hides marquee on pointercancel/lostpointercapture/blur while ignoring foreign pointers, and nav-math re-exports match", () => {
    assert.equal(navMath.headingBasis, headingBasis);
    assert.equal(navMath.orbitAroundCursor, orbitAroundCursor);
    assert.equal(navMath.panKeepPoint, panKeepPoint);
    assert.equal(navMath.zoomAtCursor, zoomAtCursor);
    assert.equal(navMath.viewOffsetForStage, viewOffsetForStage);
    assert.equal(navMath.applyStageViewOffset, applyStageViewOffset);

    const canvas = makeMockCanvas(800, 600);
    const mockWin = makeMockCanvas();
    const cam = makeMockCamera(0, -1000, 500);
    const nav = new Navigator(cam, canvas);
    let marqueeHidden = 0;
    const pivotFn = () => ({ x: 10, y: 20, z: 0 });
    bindCadNavigation({
      canvas,
      controls: nav,
      hitWorkplane: pivotFn,
      hideMarquee: () => {
        marqueeHidden += 1;
        S.marqueeOrigin = null;
      },
      win: mockWin,
    });
    assert.equal(nav.getPivot, pivotFn);

    // Even when _state === "none" (e.g. nav was disabled on pointerdown), pointerup with an event resets LEFT to -1.
    nav.enabled = false;
    nav.mouseButtons.LEFT = 0;
    canvas.emit("pointerdown", { button: 0, pointerId: 1, clientX: 100, clientY: 100 });
    assert.equal(nav._state, "none");
    canvas.emit("pointerup", { button: 0, pointerId: 1, clientX: 100, clientY: 100 });
    assert.equal(nav.mouseButtons.LEFT, -1);
    nav.enabled = true;

    // Simulate Alt+LMB press where pointercancel fires before any drag or marquee cancel happens.
    nav.mouseButtons.LEFT = 0;
    S.marqueeOrigin = { x: 100, y: 100 };
    canvas.emit("pointercancel", { pointerId: 1 });
    assert.equal(nav.mouseButtons.LEFT, -1);
    assert.equal(marqueeHidden, 1);

    // Active Alt+LMB orbit on pointer 7 ignores foreign pointer 8 pointercancel under bindCadNavigation,
    // then terminates cleanly on window.blur and resets mouseButtons.LEFT to -1.
    let changes = 0;
    nav.addEventListener("change", () => {
      changes += 1;
    });
    nav.mouseButtons.LEFT = 0;
    canvas.emit("pointerdown", { button: 0, pointerId: 7, clientX: 200, clientY: 200 });
    assert.equal(nav._state, "orbit");
    assert.equal(canvas.captured.has(7), true);
    canvas.emit("pointercancel", { pointerId: 8 });
    assert.equal(nav._state, "orbit", "foreign pointercancel must not abort active orbit");
    assert.equal(nav.mouseButtons.LEFT, 0);

    // Window blur (e.g. Alt+Tab mid-orbit) terminates the gesture and resets mouseButtons.LEFT to -1.
    S.marqueeOrigin = { x: 200, y: 200 };
    mockWin.emit("blur");
    assert.equal(nav._state, "none");
    assert.equal(canvas.captured.has(7), false);
    assert.equal(nav.mouseButtons.LEFT, -1);
    assert.equal(marqueeHidden, 2);

    // Subsequent plain LMB (button: 0) pointerdown does not enter orbit mode.
    const beforePlainClick = changes;
    canvas.emit("pointerdown", { button: 0, pointerId: 12, clientX: 250, clientY: 250 });
    canvas.emit("pointermove", { pointerId: 12, clientX: 300, clientY: 280 });
    canvas.emit("pointerup", { button: 0, pointerId: 12, clientX: 300, clientY: 280 });
    assert.equal(changes, beforePlainClick);
    assert.equal(canvas.captured.has(12), false);

    nav.dispose();
  });
});

