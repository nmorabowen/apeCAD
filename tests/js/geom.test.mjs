// Unit tests for the scratchpad's pure client modules. Run: node --test tests/js
import assert from "node:assert/strict";
import { register } from "node:module";
import path from "node:path";
import { test } from "node:test";
import { pathToFileURL } from "node:url";

import {
  circumcircle,
  disposeObject3D,
  dist3,
  lineIntersectMm,
  projectT,
  rectCorners,
  regularPolygon,
  sampleArc,
  sampleCircle,
  triangulatePlanar3D,
  triangulatePolygon2D,
  vertexRef,
  wrapAutoDispose,
} from "../../src/apeCAD/scratchpad/static/js/geom.js";
import {
  configurePickRaycaster,
  pointInPolygon2d,
  segmentHitsRect,
  shapeQualifies,
} from "../../src/apeCAD/scratchpad/static/js/screen.js";
import {
  consumeRenderDirty,
  requestRender,
  setRenderWake,
} from "../../src/apeCAD/scratchpad/static/js/store.js";

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

test("disposeObject3D disposes geometry, single material, and material arrays across tree", () => {
  const disposed = [];
  const mkDisp = (tag) => ({ dispose: () => disposed.push(tag) });
  const nodes = [
    { geometry: mkDisp("g1"), material: mkDisp("m1") },
    { geometry: mkDisp("g2"), material: [mkDisp("m2a"), null, mkDisp("m2b")] },
    {},
  ];
  const root = {
    traverse(fn) {
      fn(root);
      for (const n of nodes) fn(n);
    },
  };
  disposeObject3D(null);
  disposeObject3D({});
  disposeObject3D(root);
  assert.deepEqual(disposed, ["g1", "m1", "g2", "m2a", "m2b"]);
});

test("triangulatePolygon2D and triangulatePlanar3D ear-clip concave L-shapes without spanning the void", () => {
  // Start vertex 0 right at the reflex inner corner (50, 50) where a vertex-0 fan fails.
  const lShape = [
    p(50, 50, 10),
    p(50, 100, 10),
    p(0, 100, 10),
    p(0, 0, 10),
    p(100, 0, 10),
    p(100, 50, 10),
  ];
  const tris2d = triangulatePolygon2D(lShape);
  const tris3d = triangulatePlanar3D(lShape);
  assert.equal(tris2d.length, 4);
  assert.deepEqual(tris3d, tris2d);

  let totalArea = 0;
  for (const [i0, i1, i2] of tris3d) {
    const a = lShape[i0];
    const b = lShape[i1];
    const c = lShape[i2];
    const triArea = 0.5 * Math.abs((b.x_mm - a.x_mm) * (c.y_mm - a.y_mm) - (c.x_mm - a.x_mm) * (b.y_mm - a.y_mm));
    totalArea += triArea;
    // Centroid of every triangle must lie strictly outside the missing quadrant (x > 50 && y > 50).
    const cx = (a.x_mm + b.x_mm + c.x_mm) / 3;
    const cy = (a.y_mm + b.y_mm + c.y_mm) / 3;
    assert.ok(!(cx > 50 && cy > 50), `triangle (${i0},${i1},${i2}) spans concave void at (${cx},${cy})`);
  }
  // 100x100 minus 50x50 = 7500 mm^2.
  near(totalArea, 7500);
});

test("wrapAutoDispose disposes child geometries/materials and requests a render on clear()", () => {
  const disposed = [];
  const mkDisp = (tag) => ({ dispose: () => disposed.push(tag) });
  const children = [
    { geometry: mkDisp("halo-g1"), material: mkDisp("halo-m1") },
    { geometry: mkDisp("halo-g2"), material: [mkDisp("halo-m2a"), mkDisp("halo-m2b")] },
  ];
  const group = {
    children,
    traverse(fn) {
      fn(group);
      for (const ch of [...group.children]) fn(ch);
    },
    clear() {
      group.children.length = 0;
      return group;
    },
  };
  consumeRenderDirty();
  let wakes = 0;
  setRenderWake(() => {
    wakes += 1;
  });
  wrapAutoDispose(group, requestRender);
  const ret = group.clear();
  assert.equal(ret, group);
  assert.equal(group.children.length, 0);
  assert.deepEqual(disposed, ["halo-g1", "halo-m1", "halo-g2", "halo-m2a", "halo-m2b"]);
  assert.equal(wakes, 1);
  assert.equal(consumeRenderDirty(), true);
  setRenderWake(null);
});

test("configurePickRaycaster sets Line and Line2 screen-pixel thresholds and hits real LineSegments2", async () => {
  const raycaster = { params: {} };
  configurePickRaycaster(raycaster);
  assert.deepEqual(raycaster.params.Line, { threshold: 160 });
  assert.deepEqual(raycaster.params.Line2, { threshold: 12 });

  const threeUrl = pathToFileURL(
    path.resolve("src/apeCAD/scratchpad/static/vendor/three/build/three.module.min.js"),
  ).href;
  const addonsPrefix =
    pathToFileURL(path.resolve("src/apeCAD/scratchpad/static/vendor/three/examples/jsm")).href + "/";
  const loaderCode = `
export async function resolve(specifier, context, nextResolve) {
  if (specifier === "three") return { url: ${JSON.stringify(threeUrl)}, shortCircuit: true };
  if (specifier.startsWith("three/addons/")) {
    return { url: ${JSON.stringify(addonsPrefix)} + specifier.slice("three/addons/".length), shortCircuit: true };
  }
  return nextResolve(specifier, context);
}
`;
  register("data:text/javascript," + encodeURIComponent(loaderCode));
  const THREE = await import("three");
  const { LineSegments2 } = await import("three/addons/lines/LineSegments2.js");
  const { LineSegmentsGeometry } = await import("three/addons/lines/LineSegmentsGeometry.js");
  const { LineMaterial } = await import("three/addons/lines/LineMaterial.js");

  const orthoCam = new THREE.OrthographicCamera(-500, 500, 500, -500, -80000, 80000);
  orthoCam.up.set(0, 1, 0);
  orthoCam.position.set(0, 0, 10000);
  orthoCam.lookAt(0, 0, 0);
  orthoCam.updateMatrixWorld(true);
  orthoCam.updateProjectionMatrix();

  const perspCam = new THREE.PerspectiveCamera(50, 1, 10, 80000);
  perspCam.up.set(0, 1, 0);
  perspCam.position.set(0, 0, 1000);
  perspCam.lookAt(0, 0, 0);
  perspCam.updateMatrixWorld(true);
  perspCam.updateProjectionMatrix();

  const geom = new LineSegmentsGeometry();
  geom.setPositions([-200, 0, 0, 200, 0, 0]);
  const mat = new LineMaterial({
    linewidth: 1.5,
    worldUnits: false,
    resolution: new THREE.Vector2(1000, 1000),
  });
  const segs = new LineSegments2(geom, mat);
  segs.updateMatrixWorld(true);

  const ndc5px = new THREE.Vector2(0, 5 / 500);
  const ndc20px = new THREE.Vector2(0, 20 / 500);

  for (const cam of [orthoCam, perspCam]) {
    const rWithout = new THREE.Raycaster();
    rWithout.params.Line = { threshold: 160 };
    rWithout.setFromCamera(ndc5px, cam);
    assert.equal(rWithout.intersectObject(segs).length, 0);

    const rWith = new THREE.Raycaster();
    configurePickRaycaster(rWith);
    rWith.setFromCamera(ndc5px, cam);
    assert.equal(rWith.intersectObject(segs).length, 1);

    rWith.setFromCamera(ndc20px, cam);
    assert.equal(rWith.intersectObject(segs).length, 0);
  }
});



