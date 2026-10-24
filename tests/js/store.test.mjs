// Node unit tests for static/js/store.js (ADR 0035): pure reducer, two-signature
// separation, microtask coalescing reconciler, and dirty-flagged render wake.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { S } from "../../src/apeCAD/scratchpad/static/js/state.js";
import {
  consumeRenderDirty,
  createReconciler,
  geometrySignature,
  initialStoreState,
  reduce,
  requestRender,
  selectionSignature,
  setRenderWake,
  Store,
} from "../../src/apeCAD/scratchpad/static/js/store.js";

describe("reduce (pure state transitions)", () => {
  it("returns the identical reference on no-op selection/hover/filter dispatches", () => {
    const s0 = initialStoreState({ selectedIds: ["a", "b"], hoverIds: ["x"] });
    assert.equal(reduce(s0, { type: "selection/set", ids: ["b", "a"] }), s0);
    assert.equal(reduce(s0, { type: "hover/set", ids: ["x"] }), s0);
    assert.equal(reduce(s0, { type: "filter/set", filter: "element" }), s0);
    assert.equal(reduce(s0, { type: "unknown/action" }), s0);
  });

  it("toggles and clears selection without mutating previous state", () => {
    const s0 = initialStoreState({ selectedIds: ["a"] });
    const s1 = reduce(s0, { type: "selection/toggle", id: "b" });
    assert.notEqual(s1, s0);
    assert.deepEqual([...s0.selectedIds], ["a"]);
    assert.deepEqual([...s1.selectedIds].sort(), ["a", "b"]);

    const s2 = reduce(s1, { type: "selection/clear" });
    assert.equal(s2.selectedIds.size, 0);
    assert.equal(reduce(s2, { type: "selection/clear" }), s2);
  });

  it("separates geometrySignature from selectionSignature", () => {
    const s0 = initialStoreState({ revision: 1, selectedIds: [] });
    const s1 = reduce(s0, { type: "selection/set", ids: ["l1", "l2"] });
    const s2 = reduce(s1, { type: "hover/set", ids: ["b1"] });
    assert.equal(geometrySignature(s0), geometrySignature(s1));
    assert.equal(geometrySignature(s1), geometrySignature(s2));
    assert.notEqual(selectionSignature(s0), selectionSignature(s1));
    assert.notEqual(selectionSignature(s1), selectionSignature(s2));

    const s3 = reduce(s2, { type: "scene/set", sceneState: { points: [] }, revision: 2 });
    assert.notEqual(geometrySignature(s2), geometrySignature(s3));
  });

  it("syncs only changed slices to S when syncS is enabled", () => {
    const st = new Store(initialStoreState({ tool: "select", vizVersion: 0, selectedIds: [1] }), {
      syncS: true,
    });
    S.tool = "line";
    S.pending = { kind: "line", a: { x_mm: 0, y_mm: 0, z_mm: 0 } };
    S.selectedIds = new Set([10, 11]);
    S.vizVersion = 3;

    st.dispatch({ type: "hover/set", ids: [42] });
    assert.deepEqual([...S.hoverIds], [42]);
    assert.equal(S.tool, "line");
    assert.deepEqual(S.pending, { kind: "line", a: { x_mm: 0, y_mm: 0, z_mm: 0 } });
    assert.deepEqual([...S.selectedIds], [10, 11]);
    assert.equal(S.vizVersion, 3);

    st.dispatch({ type: "filter/set", filter: "face" });
    assert.equal(S.selectFilter, "face");
    assert.deepEqual([...S.selectedIds], [10, 11]);
    assert.equal(S.vizVersion, 3);

    S.tool = "select";
    S.pending = null;
    S.selectFilter = "element";
    S.selectedIds = new Set();
    S.hoverIds = new Set();
    S.vizVersion = 0;
  });
});

describe("createReconciler (microtask coalescing)", () => {
  it("coalesces a synchronous burst of selection dispatches into 1 onSelection and 0 onGeometry calls", async () => {
    const st = new Store(initialStoreState({ revision: 1 }));
    let geomCalls = 0;
    let selCalls = 0;
    const rec = createReconciler(st, {
      onGeometry: () => {
        geomCalls += 1;
      },
      onSelection: () => {
        selCalls += 1;
      },
    });

    st.dispatch({ type: "selection/set", ids: ["e1"] });
    st.dispatch({ type: "selection/toggle", id: "e2" });
    st.dispatch({ type: "hover/set", ids: ["e3"] });
    st.dispatch({ type: "selection/set", ids: ["e1", "e2", "e4"] });

    assert.equal(geomCalls, 0);
    assert.equal(selCalls, 0);

    await new Promise((resolve) => queueMicrotask(resolve));
    assert.equal(geomCalls, 0);
    assert.equal(selCalls, 1);

    rec.dispose();
  });

  it("coalesces mixed scene + selection dispatches in one turn into 1 onGeometry call and 0 onSelection calls", async () => {
    const st = new Store(initialStoreState({ revision: 1 }));
    let geomCalls = 0;
    let selCalls = 0;
    const rec = createReconciler(st, {
      onGeometry: () => {
        geomCalls += 1;
      },
      onSelection: () => {
        selCalls += 1;
      },
    });

    st.dispatch({ type: "selection/set", ids: ["e1"] });
    st.dispatch({ type: "scene/set", sceneState: { points: [{ id: "p1" }] }, revision: 2 });
    st.dispatch({ type: "hover/set", ids: ["p1"] });

    await new Promise((resolve) => queueMicrotask(resolve));
    assert.equal(geomCalls, 1);
    assert.equal(selCalls, 0);

    rec.dispose();
  });
});

describe("requestRender wake flag", () => {
  it("tracks dirty state and invokes wake callback once per requestRender", () => {
    consumeRenderDirty();
    let wakes = 0;
    setRenderWake(() => {
      wakes += 1;
    });
    assert.equal(consumeRenderDirty(), false);
    requestRender();
    assert.equal(wakes, 1);
    assert.equal(consumeRenderDirty(), true);
    assert.equal(consumeRenderDirty(), false);
    setRenderWake(null);
  });

  it("sleeps at 0 idle rAF dispatches after a non-animating tick and after final animation frame (u >= 1)", () => {
    consumeRenderDirty();
    let rafPending = false;
    const rafQueue = [];
    let preRenderHook = () => false;

    function scheduleTick() {
      if (rafPending) return;
      rafPending = true;
      rafQueue.push(simulatedTick);
    }

    // Mirrors tick() in app.js: _rafPending stays true until pre-render updates
    // (tickViewAnim + updateCameraMatrices + consumeRenderDirty) finish.
    function simulatedTick() {
      consumeRenderDirty();
      const animating = preRenderHook();
      // updateCameraMatrices() updates projections without calling requestRender()
      consumeRenderDirty();
      rafPending = false;
      if (animating) {
        scheduleTick();
      }
    }

    setRenderWake(scheduleTick);
    requestRender();
    assert.equal(rafQueue.length, 1);

    // Case 1: Normal non-animating tick sleeps at 0 follow-up rAFs.
    rafQueue.shift()();
    assert.equal(rafQueue.length, 0);
    assert.equal(rafPending, false);
    assert.equal(consumeRenderDirty(), false);

    // Case 2: Final frame of camera animation (u >= 1 in tickViewAnim), where
    // controls.update() synchronously fires OrbitControls "change" -> syncCameras() -> requestRender()
    // before renderer.render() executes, must also settle at 0 follow-up rAFs.
    preRenderHook = () => {
      requestRender();
      return false;
    };
    requestRender();
    assert.equal(rafQueue.length, 1);
    rafQueue.shift()();
    assert.equal(rafQueue.length, 0);
    assert.equal(rafPending, false);
    assert.equal(consumeRenderDirty(), false);

    setRenderWake(null);
  });
});

