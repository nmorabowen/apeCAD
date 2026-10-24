import assert from "node:assert/strict";
import test from "node:test";

import {
  APECADSection,
  API_VERSION,
  create,
  mockTransport,
  parseInput,
  snapPoint2D,
} from "../../src/apeCAD/scratchpad/static/section/apecad-section.js";
import {
  createViewport,
  hitTestSection,
  pointInPolygon,
  renderSectionCanvas,
} from "../../src/apeCAD/scratchpad/static/section/canvas2d.js";

test("parseInput handles absolute, relative, polar, length, thickness, and commands", () => {
  assert.deepEqual(parseInput("100, 200"), {
    kind: "point",
    point: [100, 200],
    relative: false,
  });
  assert.deepEqual(parseInput("@50,-25", [100, 200]), {
    kind: "point",
    point: [150, 175],
    relative: true,
  });
  const polar = parseInput("@100<90", [10, 20]);
  assert.equal(polar.kind, "point");
  assert.ok(Math.abs(polar.point[0] - 10) < 1e-9);
  assert.ok(Math.abs(polar.point[1] - 120) < 1e-9);

  const dir = parseInput("300", [0, 0], [1, 0]);
  assert.equal(dir.kind, "point");
  assert.deepEqual(dir.point, [300, 0]);

  assert.deepEqual(parseInput("t 250"), { kind: "thickness", thickness_mm: 250 });
  assert.deepEqual(parseInput("thickness=30cm"), { kind: "thickness", thickness_mm: 300 });
  assert.deepEqual(parseInput("c"), { kind: "command", command: "close" });
  assert.deepEqual(parseInput("u"), { kind: "command", command: "undo" });
  assert.equal(parseInput("").kind, "error");
});

test("snapPoint2D prioritizes bar > cover-corner > vertex/midpoint > cover-edge > edge > grid", () => {
  const view = {
    scale: 1,
    panX: 0,
    panY: 0,
    height: 600,
    worldToScreen: ([x, y]) => [x, 600 - y],
  };
  const scene = {
    concrete_faces: [
      { id: 1, outer_mm: [[0, 0], [400, 0], [400, 400], [0, 400]] },
    ],
    cover_guides: [
      {
        id: 2,
        face_id: 1,
        cover_ring_mm: [[40, 40], [360, 40], [360, 360], [40, 360]],
        bar_centre_ring_mm: [[58, 58], [342, 58], [342, 342], [58, 342]],
      },
    ],
    bars: [{ id: 10, centre_mm: [58, 58], diameter_mm: 16 }],
  };

  // Near (58, 58) where bar and cover-corner coincide: bar wins (priority 1)
  const snapBar = snapPoint2D(view.worldToScreen([60, 60]), [60, 60], view, scene);
  assert.equal(snapBar.snapped, true);
  assert.equal(snapBar.kind, "bar");
  assert.equal(snapBar.id, 10);

  // Near (342, 58) where only cover-corner exists: cover-corner wins
  const snapCorner = snapPoint2D(view.worldToScreen([340, 58]), [340, 58], view, scene);
  assert.equal(snapCorner.kind, "cover-corner");
  assert.deepEqual(snapCorner.point, [342, 58]);

  // Near (200, 0) midpoint of bottom face edge
  const snapMid = snapPoint2D(view.worldToScreen([202, 2]), [202, 2], view, scene);
  assert.equal(snapMid.kind, "midpoint");
  assert.deepEqual(snapMid.point, [200, 0]);

  // Near (200, 58) on cover-edge
  const snapCovEdge = snapPoint2D(view.worldToScreen([200, 61]), [200, 61], view, scene);
  assert.equal(snapCovEdge.kind, "cover-edge");
  assert.deepEqual(snapCovEdge.point, [200, 58]);

  // Far from geometry with gridStepMm = 50
  const snapGrid = snapPoint2D(view.worldToScreen([173, 224]), [173, 224], view, scene, {
    gridStepMm: 50,
    gridSnap: true,
  });
  assert.equal(snapGrid.kind, "grid");
  assert.deepEqual(snapGrid.point, [150, 200]);
});

test("mockTransport supports apply, undo, redo, load, seed, and draft", async () => {
  const send = mockTransport();
  const r1 = await send({
    action: "apply",
    op: { op: "RectSection", b_mm: 400, h_mm: 600, material: "H30" },
  });
  assert.equal(r1.ok, true);
  assert.equal(r1.scene.concrete_faces.length, 1);
  const faceId = r1.scene.concrete_faces[0].id;

  const r2 = await send({
    action: "apply",
    op: { op: "SetCover", face_id: faceId, cover_mm: 40, tie_diameter_mm: 10, bar_diameter_mm: 16 },
  });
  assert.equal(r2.ok, true);
  assert.equal(r2.scene.cover_guides.length, 1);

  const r3 = await send({
    action: "apply",
    op: {
      op: "AddBarRow",
      start_x_mm: 58,
      start_y_mm: 58,
      end_x_mm: 342,
      end_y_mm: 58,
      designation: "Ø16",
      count: 3,
    },
  });
  assert.equal(r3.ok, true);
  assert.equal(r3.scene.bars.length, 3);

  const u1 = await send({ action: "undo" });
  assert.equal(u1.ok, true);
  assert.equal(u1.scene.bars.length, 0);

  const redo1 = await send({ action: "redo" });
  assert.equal(redo1.ok, true);
  assert.equal(redo1.scene.bars.length, 3);

  const seedLoad = await send({
    action: "seed",
    payload: {
      schema: "apeCAD.section-seed",
      version: 1,
      units: "mm",
      section: {
        concrete_faces: [{ ring_mm: [[0, 0], [300, 0], [300, 300], [0, 300]], material: "concrete" }],
        bars: [{ x_mm: 50, y_mm: 50, designation: "Ø20", diameter_mm: 20 }],
      },
    },
  });
  assert.equal(seedLoad.ok, true);
  assert.equal(seedLoad.scene.bars.length, 1);
  assert.equal(seedLoad.scene.bars[0].diameter_mm, 20);
});

test("APECADSection.create fires onChange on apply/undo/redo and NOT on loadDraft/loadSeed", async () => {
  assert.equal(API_VERSION, 1);
  assert.equal(APECADSection.API_VERSION, 1);

  const changes = [];
  const container = {};
  const editor = create(container, {
    transport: mockTransport(),
    onChange: (draft) => changes.push(draft),
  });

  await editor.loadDraft({
    schema: "apeCAD.document.v1",
    units: "mm",
    ops: [
      {
        op: "AddSectionOutline",
        point_ids: [{ xyz: [0, 0, 0] }, { xyz: [400, 0, 0] }, { xyz: [400, 400, 0] }, { xyz: [0, 400, 0] }],
        material: "concrete",
      },
    ],
  });
  assert.equal(changes.length, 0, "loadDraft must NOT fire onChange");

  await editor.loadSeed({
    schema: "apeCAD.section-seed",
    version: 1,
    units: "mm",
    section: {
      concrete_faces: [{ ring_mm: [[0, 0], [400, 0], [400, 400], [0, 400]], material: "concrete" }],
      bars: [],
    },
  });
  assert.equal(changes.length, 0, "loadSeed must NOT fire onChange");

  await editor.applyOp({ op: "AddBar", x_mm: 60, y_mm: 60, designation: "Ø16" });
  assert.equal(changes.length, 1, "applyOp must fire onChange");
  assert.equal(editor.getDraft().bars.length, 1);

  await editor.undo();
  assert.equal(changes.length, 2, "undo must fire onChange");
  assert.equal(editor.getDraft().bars.length, 0);

  await editor.redo();
  assert.equal(changes.length, 3, "redo must fire onChange");
  assert.equal(editor.getDraft().bars.length, 1);

  editor.dispose();
});

test("canvas2d viewport, hitTestSection, pointInPolygon, and readOnly mode", async () => {
  const ring = [[0, 0], [400, 0], [400, 400], [0, 400]];
  assert.equal(pointInPolygon([200, 200], ring), true);
  assert.equal(pointInPolygon([500, 200], ring), false);

  const view = createViewport({ width: 800, height: 600 });
  const scene = {
    concrete_faces: [{ id: 1, outer_mm: ring, openings_mm: [] }],
    bars: [{ id: 5, centre_mm: [60, 60], diameter_mm: 16 }],
  };
  view.fit(scene);
  const barScreen = view.worldToScreen([60, 60]);
  const hit = hitTestSection(barScreen, view, scene);
  assert.equal(hit?.kind, "Bar");
  assert.equal(hit?.id, 5);

  renderSectionCanvas({ getContext: () => null }, view, { scene });

  const roEditor = create({}, { transport: mockTransport(), readOnly: true });
  const res = await roEditor.applyOp({ op: "AddBar", x_mm: 50, y_mm: 50, designation: "Ø16" });
  assert.equal(res.ok, false);
  roEditor.dispose();
});

test("mockTransport loads L-wall seed with cover_guides, wall_legs, hoops, and crossties", async () => {
  const send = mockTransport();
  const res = await send({
    action: "seed",
    payload: {
      schema: "apeCAD.section-seed",
      version: 1,
      units: "mm",
      section: {
        concrete_faces: [{
          ring_mm: [[0, 0], [1000, 0], [1000, 200], [200, 200], [200, 1000], [0, 1000]],
          material: "concrete",
        }],
        wall_legs: [
          { start_mm: [100, 100], end_mm: [900, 100], thickness_mm: 200, concrete_face_id: 0, horizontal: { designation: "Ø12", spacing_mm: 200, curtains: 2 } },
        ],
        cover_guides: [
          { face_id: 0, cover_mm: 25, tie_diameter_mm: 10, bar_diameter_mm: 16 },
        ],
        bars: [
          { x_mm: 50, y_mm: 50, designation: "Ø16", diameter_mm: 16 },
          { x_mm: 950, y_mm: 50, designation: "Ø16", diameter_mm: 16 },
          { x_mm: 950, y_mm: 150, designation: "Ø16", diameter_mm: 16 },
          { x_mm: 50, y_mm: 150, designation: "Ø16", diameter_mm: 16 },
        ],
        hoops: [
          { bar_ids: [0, 1, 2, 3], designation: "Ø10", diameter_mm: 10, spacing_mm: 100, hooks: "135" },
        ],
        crossties: [
          { bar_a_id: 0, bar_b_id: 2, designation: "Ø10", diameter_mm: 10, spacing_mm: 100, hooks: "135-90" },
        ],
      },
    },
  });
  assert.equal(res.ok, true);
  assert.equal(res.scene.concrete_faces.length, 1);
  assert.equal(res.scene.wall_legs.length, 1);
  assert.equal(res.scene.cover_guides.length, 1);
  assert.equal(res.scene.bars.length, 4);
  assert.equal(res.scene.hoops.length, 1);
  assert.equal(res.scene.crossties.length, 1);
});

test("interactive wall-chain tool emits Python-compatible AddWallChain op and initial scene race is guarded", async () => {
  const appliedOps = [];
  const base = mockTransport();
  let resolveInitialScene;
  const initialScenePromise = new Promise((r) => { resolveInitialScene = r; });
  let firstSceneCall = true;
  const slowTransport = async (req) => {
    if (req.action === "scene" && firstSceneCall) {
      firstSceneCall = false;
      return initialScenePromise;
    }
    if (req.action === "apply") appliedOps.push(req.op);
    return base(req);
  };

  const container = {};
  const editor = create(container, { transport: slowTransport });
  await editor.applyOp({ op: "AddBar", x_mm: 40, y_mm: 40, designation: "Ø16" });
  assert.equal(editor.getDraft().bars.length, 1);

  // Now resolve the delayed initial scene; it must NOT clobber the bar we just added!
  resolveInitialScene({ ok: true, status: 200, scene: { bars: [], concrete_faces: [] } });
  await new Promise((r) => setTimeout(r, 10));
  assert.equal(editor.getDraft().bars.length, 1);

  // Drive wall-chain via command input
  editor.setTool("wall-chain");
  const root = container.children[0];
  const bottomBar = root.children[2];
  const cmdInput = bottomBar.children[1];
  const sendCmd = (txt) => {
    cmdInput.value = txt;
    cmdInput.dispatchEvent({ type: "keydown", key: "Enter" });
  };
  sendCmd("t 300");
  sendCmd("0,0");
  sendCmd("2000,0");
  sendCmd("c");
  await new Promise((r) => setTimeout(r, 10));

  const chainOp = appliedOps.find((op) => op.op === "AddWallChain");
  assert.ok(chainOp, "AddWallChain op was emitted");
  assert.equal(chainOp.material, "concrete");
  assert.deepEqual(chainOp.thickness_mm, [300]);
  assert.equal("closed" in chainOp, false, "AddWallChain must not pass unknown 'closed' parameter");

  editor.dispose();
});
