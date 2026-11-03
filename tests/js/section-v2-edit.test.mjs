// The 2-D client edits v2 (C5 record §3 "Editing" and "API", §4 invariants 9-11; C5-S4).
// Pure checks against a scripted transport: the create option and its refusals, the tool ids,
// the `draft` that follows each v2 change, refusals by name, select-as-unit, Delete and
// Explode of a template, snapping to v2 faces, and huge input. The live-transport oracles
// (each tool's op replayed to `section_draft(doc, version=2)`, TEMPLATE_LOCKED, the v1
// request log) are `tests/test_section_client_v2.py`'s.
import assert from "node:assert/strict";
import test from "node:test";

import { API_VERSION, APECADSection, create, mockTransport, snapPoint2D } from "../../src/apeCAD/scratchpad/static/section/apecad-section.js";
import { normalizeScene } from "../../src/apeCAD/scratchpad/static/section/transport.js";
import { MAX_GESTURE_POINTS, TOOLS_V2, faceAt, templateLines, templateOf } from "../../src/apeCAD/scratchpad/static/section/tools-v2.js";

const ring = (x0, y0, x1, y1) => [[x0, y0], [x1, y0], [x1, y1], [x0, y1]];
const face = (id, role, outer, holes = []) => ({
  entity_id: id, label: null, role, material: role === "void" ? null : "C30",
  boundary: { kind: "ring", ring_mm: outer }, holes: holes.map((h) => ({ kind: "ring", ring_mm: h })),
});
const tick = () => new Promise((r) => setTimeout(r, 2));

// A transport that answers every request with `scene`, logs it, and refuses what `refuse` names.
function scripted(scene, refuse = () => null) {
  const log = [];
  const send = async (req) => {
    log.push(req);
    const why = refuse(req);
    if (why) return { ok: false, status: 422, error: { code: why.code, message: why.message } };
    if (req.action === "draft") return { ok: true, status: 200, scene, draft: { schema: "apeCAD.section-draft", version: req.version, n: log.length } };
    return { ok: true, status: 200, scene, draft: null };
  };
  send.log = log;
  return send;
}

function mount(opts) {
  const listeners = {};
  const container = { children: [], appendChild(c) { this.children.push(c); return c; }, addEventListener(t, f) { listeners[t] = f; }, removeEventListener() {} };
  const ed = create(container, opts);
  const [toolbar, stage, bottom] = container.children[0].children;
  const [prompt, cmd] = bottom.children;
  return {
    ed, toolbar, prompt, cmd,
    props: () => stage.children[1].children[0].children.map((c) => c.textContent),
    tools: () => toolbar.children.map((b) => b.dataset.tool).filter(Boolean),
    type: async (...inputs) => { for (const t of inputs) { cmd.value = t; cmd.dispatchEvent({ type: "keydown", key: "Enter" }); await tick(); } },
    key: async (evt) => { listeners.keydown({ target: null, preventDefault() {}, ...evt }); await tick(); },
    click: async (action) => { toolbar.children.find((b) => b.dataset.action === action).dispatchEvent({ type: "click" }); await tick(); },
  };
}

// --- API 3: the option, and what it refuses -----------------------------------------------

test("API_VERSION is 3, and create reads version 1 (the default) and 2 only", () => {
  assert.equal(API_VERSION, 3);
  assert.equal(APECADSection.API_VERSION, 3);
  for (const version of [undefined, null, 1]) create({}, { version }).dispose();
  create({}, { version: 2, transport: scripted({}) }).dispose();
  for (const [bad, named] of [[3, "3"], [0, "0"], [1.5, "1.5"], ["2", '"2"'], [true, "true"], [{}, "{}"], [[2], "[2]"], [Number.NaN, "NaN"]]) {
    assert.throws(() => create({}, { version: bad, transport: scripted({}) }), new RegExp(`version ${named.replace(/[[\]{}.]/g, "\\$&")} is not supported, expected 1 or 2`));
  }
  assert.throws(() => create({}, { version: 2 }), /version 2 needs a transport; mockTransport is v1 only/);
});

test("the mock transport refuses a v2 draft by name instead of handing out v1", async () => {
  const res = await mockTransport()({ action: "draft", version: 2 });
  assert.equal(res.ok, false);
  assert.match(res.error.message, /mockTransport writes section-draft version 1 only, not 2/);
  assert.equal((await mockTransport()({ action: "draft" })).draft.version, 1);
});

test("v1 keeps its 13 tool ids; v2 swaps Opening for Hole, adds Circle, hides Edge bars", () => {
  const v1 = mount({ transport: mockTransport() });
  assert.deepEqual(v1.tools(), ["select", "rect", "polygon", "opening", "wall-chain", "wall-leg", "cover", "bar", "bar-row", "bars-edge", "hoop", "crosstie", "delete"]);
  assert.equal(v1.toolbar.children.some((b) => b.dataset.action === "explode"), false);
  const v2 = mount({ transport: scripted({}), version: 2 });
  assert.deepEqual(v2.tools(), TOOLS_V2.map(([id]) => id));
  assert.deepEqual(v2.tools(), ["select", "rect", "polygon", "circle", "hole", "wall-chain", "wall-leg", "cover", "bar", "bar-row", "hoop", "crosstie", "delete"]);
  assert.equal(v2.toolbar.children.filter((b) => b.dataset.action === "explode").length, 1);
});

// --- invariant 9: v2 mode follows each change with `draft` at version 2 ----------------------

test("v2 mode asks for the v2 draft after each change; getDraft and onChange carry it", async () => {
  const changes = [];
  const transport = scripted(normalizeScene({ section_faces: [face(1, "concrete", ring(0, 0, 400, 400))] }));
  const m = mount({ transport, version: 2, onChange: (d) => changes.push(d) });
  await tick();
  assert.deepEqual(transport.log.map((r) => r.action), ["scene", "draft"]);
  assert.equal(m.ed.getDraft().version, 2);
  await m.ed.applyOp({ op: "AddBar", x_mm: 1, y_mm: 1, designation: "Ø16" });
  await m.ed.undo();
  await m.ed.redo();
  await m.ed.loadDraft({ schema: "apeCAD.document.v1", units: "mm", ops: [] });
  assert.deepEqual(transport.log.map((r) => r.action), ["scene", "draft", "apply", "draft", "undo", "draft", "redo", "draft", "load", "draft"]);
  assert.ok(transport.log.filter((r) => r.action === "draft").every((r) => r.version === 2));
  assert.deepEqual(changes.map((d) => d.n), [4, 6, 8], "onChange: apply, undo, redo, not load");
  assert.equal(m.ed.getDraft().n, 10);
});

test("v1 mode sends no draft request", async () => {
  const log = [];
  const inner = mockTransport();
  const ed = create({}, { transport: (req) => { log.push(req.action); return inner(req); } });
  await tick();
  await ed.applyOp({ op: "AddBar", x_mm: 1, y_mm: 1, designation: "Ø16" });
  await ed.undo();
  assert.deepEqual(log, ["scene", "apply", "undo"]);
  assert.equal(ed.getDraft().version, 1);
});

test("a refusal shows Refused: <message>; a refused draft leaves no draft rather than a stale one", async () => {
  let refuseDraft = false;
  const transport = scripted({}, (req) => (req.action === "apply" ? { code: "TEMPLATE_LOCKED", message: "bar 5 belongs to section template 1" }
    : refuseDraft && req.action === "draft" ? { code: "INVALID_ARGUMENT", message: "the draft is broken" } : null));
  const changes = [];
  const m = mount({ transport, version: 2, onChange: (d) => changes.push(d) });
  await tick();
  const res = await m.ed.applyOp({ op: "Delete", entity_ids: [5] });
  assert.equal(res.ok, false);
  assert.equal(m.prompt.textContent, "Refused: bar 5 belongs to section template 1");
  assert.equal(transport.log.at(-1).action, "apply", "no draft after a refusal");
  refuseDraft = true;
  await m.ed.undo();
  assert.equal(m.ed.getDraft(), null);
  assert.equal(m.prompt.textContent, "Refused: the draft is broken");
  assert.deepEqual(changes, []);
});

// --- tools: the ops they post -------------------------------------------------------------

test("rect, circle and polygon post AddSectionFace with the role; a void has no material", async () => {
  const transport = scripted({});
  const m = mount({ transport, version: 2 });
  await tick();
  m.ed.setParam("material", "C30");
  m.ed.setTool("rect"); await m.type("0,0", "400,600");
  m.ed.setParam("role", "steel"); m.ed.setParam("material", "S355");
  m.ed.setTool("circle"); await m.type("100,100", "@0,30");
  m.ed.setParam("role", "void");
  m.ed.setTool("polygon"); await m.type("0,0", "10,0", "0,10", "c");
  const ops = transport.log.filter((r) => r.action === "apply").map((r) => r.op);
  const xyz = (x, y) => ({ xyz: [x, y, 0] });
  assert.deepEqual(ops, [
    { op: "AddSectionFace", role: "concrete", material: "C30", point_ids: [xyz(0, 0), xyz(400, 0), xyz(400, 600), xyz(0, 600)] },
    { op: "AddSectionFace", role: "steel", material: "S355", center_id: xyz(100, 100), radius_mm: 30 },
    { op: "AddSectionFace", role: "void", material: null, point_ids: [xyz(0, 0), xyz(10, 0), xyz(0, 10)] },
  ]);
});

test("the hole tool posts AddFaceHole on the face on top at its first point, holes excluded", async () => {
  const scene = normalizeScene({ section_faces: [face(1, "concrete", ring(0, 0, 400, 400), [ring(50, 50, 150, 150)]), face(2, "steel", ring(200, 200, 300, 300))] });
  assert.equal(faceAt(scene, [250, 250]).id, 2, "steel over concrete");
  assert.equal(faceAt(scene, [100, 100]), null, "inside the hole");
  assert.equal(faceAt(scene, [20, 20]).id, 1);
  const transport = scripted(scene);
  const m = mount({ transport, version: 2 });
  await tick();
  m.ed.setTool("hole");
  await m.type("100,100");
  assert.equal(m.prompt.textContent, "Hole: start inside a face");
  await m.type("210,210", "@50,0", "@0,50", "c");
  const ops = transport.log.filter((r) => r.action === "apply").map((r) => r.op);
  assert.deepEqual(ops, [{ op: "AddFaceHole", face_id: 2, point_ids: [[210, 210], [260, 210], [260, 260]].map(([x, y]) => ({ xyz: [x, y, 0] })) }]);
});

// --- templates: one unit, deleted or exploded by the server -------------------------------

function templateScene() {
  return normalizeScene({
    section_faces: [face(2, "concrete", ring(0, 0, 400, 600))],
    bars: [{ entity_id: 3, x_mm: 60, y_mm: 60, designation: "Ø20", diameter_mm: 20 }, { entity_id: 9, x_mm: 900, y_mm: 60, designation: "Ø20", diameter_mm: 20 }],
    templates: [{ entity_id: 1, template: "rect_column", template_version: 1, params: { material: "C30", b: 400, h: 600 }, child_ids: [2, 3], label: null }],
  });
}

test("a click on a template child selects the template: name, version, params, locked", async () => {
  const scene = templateScene();
  assert.equal(templateOf(scene, 3).id, 1);
  assert.equal(templateOf(scene, 9), null);
  assert.deepEqual(templateLines(scene.templates[0]), [
    "Template #1 (rect_column v1) · locked", 'material = "C30"', "b = 400", "h = 600", "2 children: edit its params, Delete it or Explode it",
  ]);
  const transport = scripted(scene);
  const m = mount({ transport, version: 2 });
  await tick();
  m.ed.setTool("select");
  await m.type("60,60");
  assert.equal(m.props()[0], "Template #1 (rect_column v1) · locked");
  await m.type("900,60");
  assert.deepEqual(m.props(), ["Bar #9 (Ø20)"], "a freehand bar is itself");
});

test("Delete on a child posts Delete{template_id}; Explode posts ExplodeSectionTemplate", async () => {
  const transport = scripted(templateScene());
  const m = mount({ transport, version: 2 });
  await tick();
  m.ed.setTool("select"); await m.type("60,60");
  await m.key({ key: "Delete" });
  m.ed.setTool("delete"); await m.type("200,300");
  m.ed.setTool("select"); await m.type("60,60");
  await m.click("explode");
  await m.click("explode");
  const ops = transport.log.filter((r) => r.action === "apply").map((r) => r.op);
  assert.deepEqual(ops, [
    { op: "Delete", entity_ids: [1] }, { op: "Delete", entity_ids: [1] }, { op: "ExplodeSectionTemplate", template_id: 1 },
  ]);
  assert.equal(m.prompt.textContent, "Explode: select a template first", "nothing selected after the explode");
});

// --- snapping to v2 faces -----------------------------------------------------------------

test("points snap to a v2 face's vertices and edges, and a circle's centre, quadrants and rim", () => {
  const view = { scale: 1, worldToScreen: ([x, y]) => [x, 600 - y] };
  const scene = {
    section_faces: [
      face(1, "concrete", ring(0, 0, 400, 400), [ring(100, 100, 200, 200)]),
      { ...face(2, "steel", []), boundary: { kind: "circle", center_mm: [700, 200], radius_mm: 100 }, holes: [] },
    ],
  };
  const snap = (x, y) => snapPoint2D(view.worldToScreen([x, y]), [x, y], view, scene);
  assert.deepEqual([snap(3, 2).kind, snap(3, 2).point, snap(3, 2).target_id], ["vertex", [0, 0], 1]);
  assert.deepEqual([snap(150, 98).kind, snap(150, 98).point, snap(150, 98).edge_index], ["midpoint", [150, 100], null]);
  assert.deepEqual([snap(200, 3).kind, snap(200, 3).edge_index], ["midpoint", 0]);
  assert.deepEqual([snap(300, 404).kind, snap(300, 404).point, snap(300, 404).edge_index], ["edge", [300, 400], 2]);
  assert.deepEqual([snap(702, 198).kind, snap(702, 198).point], ["center", [700, 200]]);
  assert.deepEqual([snap(703, 297).kind, snap(703, 297).point], ["quadrant", [700, 300]]);
  const rim = snap(700 + 100 * Math.SQRT1_2 + 3, 200 + 100 * Math.SQRT1_2 + 3);
  assert.equal(rim.kind, "edge");
  assert.ok(Math.abs(Math.hypot(rim.point[0] - 700, rim.point[1] - 200) - 100) < 1e-9, JSON.stringify(rim.point));
});

// --- huge input: bounded time ---------------------------------------------------------------

test("a v2 document of 10^4 faces and 10^5 bars edits, selects and deletes in bounded time", async () => {
  const faces = Array.from({ length: 10000 }, (_, i) => face(i + 1, i % 3 === 0 ? "steel" : "concrete", ring((i % 100) * 50, Math.floor(i / 100) * 50, (i % 100) * 50 + 40, Math.floor(i / 100) * 50 + 40)));
  const bars = Array.from({ length: 100000 }, (_, i) => ({ entity_id: 20001 + i, x_mm: (i % 400) * 12.5, y_mm: Math.floor(i / 400) * 20, designation: "Ø8", diameter_mm: 8 }));
  const childIds = [...faces.map((f) => f.entity_id), ...bars.map((b) => b.entity_id)];
  const scene = normalizeScene({ section_faces: faces, bars, templates: [{ entity_id: 20000, template: "big", template_version: 1, params: {}, child_ids: childIds }] });
  const transport = scripted(scene);
  const m = mount({ transport, version: 2 });
  await tick();
  const t0 = Date.now();
  for (let i = 0; i < 3; i++) await m.ed.applyOp({ op: "AddBar", x_mm: i, y_mm: 0, designation: "Ø8" });
  const perEdit = (Date.now() - t0) / 3;
  m.ed.setTool("select"); await m.type("0,0");
  assert.equal(m.props()[0], "Template #20000 (big v1) · locked");
  await m.key({ key: "Delete" });
  assert.deepEqual(transport.log.filter((r) => r.action === "apply").at(-1).op, { op: "Delete", entity_ids: [20000] });
  const total = Date.now() - t0;
  assert.ok(perEdit < 4000 && total < 20000, `${perEdit} ms per edit, ${total} ms in all`);
});

test("a polygon of 10^5 typed vertices refuses past the cap by name and closes without hanging", async () => {
  const transport = scripted({});
  const m = mount({ transport, version: 2 });
  await tick();
  m.ed.setTool("polygon");
  const t0 = Date.now();
  for (let i = 0; i < 100000; i++) { // typed as fast as Enter can go: one point and redraw each
    m.cmd.value = `${i},${(i * 7919) % 1000}`;
    m.cmd.dispatchEvent({ type: "keydown", key: "Enter" });
  }
  await tick();
  assert.match(m.prompt.textContent, new RegExp(`Refused: a polygon takes at most ${MAX_GESTURE_POINTS} points`));
  await m.type("c");
  const op = transport.log.filter((r) => r.action === "apply").at(-1).op;
  assert.equal(op.op, "AddSectionFace");
  assert.equal(op.point_ids.length, MAX_GESTURE_POINTS);
  assert.ok(Date.now() - t0 < 60000, `${Date.now() - t0} ms`);
});
