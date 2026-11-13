// Client API 4 (C8a): `sync()`, the `chrome` option and `setGlyphs`, for apeSection's embed
// (its `docs/contracts/host-api-v1.md` §9). Pure checks against a fake host transport that
// holds the document and its revision, as apeSection's `verbTransport` does. The oracles:
// the view transform is read back from the canvas, never from the client's internals; a glyph
// is placed by canvas2d's own transform for a bar at the same world point.
import assert from "node:assert/strict";
import test from "node:test";

import { create, mockTransport } from "../../src/apeCAD/scratchpad/static/section/apecad-section.js";

const tick = () => new Promise((r) => setTimeout(r, 2));
const RING = [[0, 0], [400, 0], [400, 600], [0, 600]];

// A host that owns the document: `apply` adds a bar and moves the revision; `scene` and
// `draft` read it. `outside(op)` is another writer (an agent, a second tab). `hold(action)`
// keeps the next reply to `action` on the wire, already computed, until it is released.
function fakeHost({ revision = 0, revisions = true } = {}) {
  const st = { revision, bars: [], nextId: 2 };
  const log = [], holds = new Map();
  const scene = () => ({
    section_faces: [{ entity_id: 1, label: null, role: "concrete", material: "C30", boundary: { kind: "ring", ring_mm: RING }, holes: [] }],
    bars: st.bars.map((b) => ({ ...b, centre_mm: [...b.centre_mm] })),
  });
  const apply = (op) => {
    const id = st.nextId++;
    st.bars.push({ id, centre_mm: [op.x_mm, op.y_mm], diameter_mm: 16, material: null });
    st.revision += 1;
    return id;
  };
  const stamp = (res) => (revisions ? { ...res, revision: st.revision } : res);
  const send = async (req) => {
    log.push(req.action);
    let res;
    if (req.action === "apply") res = stamp({ ok: true, status: 200, created_id: apply(req.op), scene: scene() });
    else if (req.action === "draft") res = stamp({ ok: true, status: 200, draft: { schema: "apeCAD.section-draft", version: 2, bar_ids: st.bars.map((b) => b.id) } });
    else if (req.action === "scene") res = stamp({ ok: true, status: 200, scene: scene() });
    else res = { ok: false, status: 422, error: { code: "REFUSED", message: `the host refuses ${req.action}` } };
    const gate = holds.get(req.action);
    if (gate) { holds.delete(req.action); await gate; }
    return res;
  };
  send.log = log;
  send.state = st;
  send.outside = (op) => apply(op);
  send.hold = (action) => { let release; holds.set(action, new Promise((r) => { release = r; })); return () => release(); };
  return send;
}

function recorder() {
  const log = [];
  const ctx = {
    globalAlpha: 1, fillStyle: "", strokeStyle: "", lineWidth: 1, font: "", lineCap: "", lineJoin: "",
    save() {}, restore() {}, beginPath() {}, closePath() {}, moveTo() {}, lineTo() {}, setLineDash() {},
    fillRect() {}, strokeRect() {}, fill() {}, stroke() {}, fillText() {},
    arc(x, y, r) { log.push({ x, y, r, lineWidth: ctx.lineWidth, strokeStyle: ctx.strokeStyle }); },
  };
  return { ctx, log };
}

function mount(opts) {
  const listeners = {};
  const container = { children: [], appendChild(c) { this.children.push(c); return c; }, addEventListener(t, f) { listeners[t] = f; }, removeEventListener() {} };
  const changes = [];
  const ed = create(container, { onChange: (d) => changes.push(d), ...opts });
  const root = container.children[0];
  const stage = root.children.find((c) => c.className === "apecad-section-stage");
  const canvas = stage.children[0];
  const rec = recorder();
  canvas.getContext = () => rec.ctx;
  const fire = (evt) => canvas.dispatchEvent(evt);
  return {
    ed, root, stage, changes, rec,
    prompt: () => root.children.at(-1).children[0].textContent,
    key: (evt) => listeners.keydown({ target: null, preventDefault() {}, ...evt }),
    zoom: (x, y, deltaY) => fire({ type: "wheel", clientX: x, clientY: y, deltaY, preventDefault() {} }),
    pan: (dx, dy) => {
      fire({ type: "mousedown", button: 0, altKey: true, clientX: 300, clientY: 300 });
      fire({ type: "mousemove", clientX: 300 + dx, clientY: 300 + dy });
      fire({ type: "mouseup" });
    },
    glyphArcs: () => rec.log.filter((a) => a.r === 6 && a.lineWidth === 1.25),
  };
}

// The view transform, read off the canvas: the screen points of two world probes, drawn as
// the centroid glyph. Bit-equal probes mean an equal scale and pan.
function transformOf(m) {
  const at = (pt) => {
    m.rec.log.length = 0;
    assert.equal(m.ed.setGlyphs({ centroid_mm: pt }).ok, true);
    const arcs = m.glyphArcs();
    assert.equal(arcs.length, 1);
    return [arcs[0].x, arcs[0].y];
  };
  const out = [at([0, 0]), at([1000, -750])];
  m.ed.setGlyphs(null);
  return out;
}

// --- sync() --------------------------------------------------------------------------------

test("after an outside apply, sync() shows it, keeps the view bit-equal, fires no onChange, and takes the host's revision", async () => {
  const host = fakeHost({ revision: 40 });
  const m = mount({ transport: host, version: 2 });
  await tick();
  assert.equal(m.ed.getOverlayState().revision, 40);
  m.ed.fitView();
  m.zoom(250, 180, -1);
  m.pan(37, -11);
  const before = transformOf(m);
  host.outside({ x_mm: 100, y_mm: 100 });
  host.outside({ x_mm: 300, y_mm: 500 });
  host.outside({ x_mm: 200, y_mm: 300 }); // the host is now at 43: three outside edits
  host.log.length = 0;

  const res = await m.ed.sync();
  assert.equal(res.ok, true);
  assert.deepEqual(host.log, ["scene", "draft"]);
  assert.deepEqual(m.ed.getScene().bars.map((b) => b.id), [2, 3, 4]);
  assert.deepEqual(m.ed.getDraft().bar_ids, [2, 3, 4]);
  assert.equal(m.ed.getOverlayState().revision, 43, "the client's revision is the host's, not 40 + 1");
  assert.deepEqual(m.changes, [], "sync never fires onChange");
  assert.deepEqual(transformOf(m), before, "sync never refits or moves the view");
  m.ed.fitView();
  assert.notDeepEqual(transformOf(m), before, "the probe sees a refit");
});

test("sync() with a transport that sends no revision leaves the revision as it was", async () => {
  const host = fakeHost({ revisions: false });
  const m = mount({ transport: host, version: 2 });
  await tick();
  await m.ed.applyOp({ op: "AddBar", x_mm: 50, y_mm: 50, designation: "Ø16" });
  assert.equal(m.ed.getOverlayState().revision, 1);
  host.outside({ x_mm: 60, y_mm: 60 });
  await m.ed.sync();
  await m.ed.sync();
  assert.equal(m.ed.getOverlayState().revision, 1, "sync never counts an edit");
  assert.deepEqual(m.ed.getScene().bars.map((b) => b.id), [2, 3]);
  assert.equal(m.changes.length, 1, "onChange only for the local apply");
});

test("v1 mode: sync() re-reads the scene only and keeps a v1 draft", async () => {
  const inner = mockTransport();
  const log = [];
  const m = mount({ transport: (req) => { log.push(req.action); return inner(req); } });
  await tick();
  await inner({ action: "apply", op: { op: "AddBar", x_mm: 10, y_mm: 20, designation: "Ø16" } });
  log.length = 0;
  const res = await m.ed.sync();
  assert.equal(res.ok, true);
  assert.deepEqual(log, ["scene"]);
  assert.equal(m.ed.getScene().bars.length, 1);
  assert.equal(m.ed.getDraft().version, 1);
  assert.equal(m.ed.getOverlayState().revision, res.revision);
  assert.deepEqual(m.changes, []);
});

test("a local edit that starts while sync() is on the wire wins", async () => {
  const host = fakeHost({ revision: 5 });
  const m = mount({ transport: host, version: 2 });
  await tick();
  host.outside({ x_mm: 1, y_mm: 1 }); // 6
  const release = host.hold("scene");
  const syncing = m.ed.sync(); // its reply (bar 2, revision 6) is computed and held
  await tick();
  await m.ed.applyOp({ op: "AddBar", x_mm: 9, y_mm: 9, designation: "Ø16" }); // bar 3, revision 7
  release();
  const res = await syncing;
  assert.equal(res.stale, true, "the older sync reply is dropped");
  assert.deepEqual(m.ed.getScene().bars.map((b) => b.id), [2, 3]);
  assert.deepEqual(m.ed.getDraft().bar_ids, [2, 3]);
  assert.equal(m.ed.getOverlayState().revision, 7);
  assert.equal(m.changes.length, 1);
});

test("a local edit that lands while sync() waits for its draft wins", async () => {
  const host = fakeHost();
  const m = mount({ transport: host, version: 2 });
  await tick();
  host.outside({ x_mm: 1, y_mm: 1 }); // 1
  const release = host.hold("draft");
  const syncing = m.ed.sync(); // scene at 1; its draft (bar 2 only) is held
  await tick();
  const applying = m.ed.applyOp({ op: "AddBar", x_mm: 9, y_mm: 9, designation: "Ø16" }); // 2
  await tick();
  release();
  assert.equal((await syncing).stale, true);
  await applying;
  assert.deepEqual(m.ed.getDraft().bar_ids, [2, 3]);
  assert.deepEqual(m.ed.getScene().bars.map((b) => b.id), [2, 3]);
  assert.equal(m.ed.getOverlayState().revision, 2);
  assert.equal(m.changes.length, 1);
});

test("a local edit already in flight when sync() starts still ends on screen", async () => {
  const host = fakeHost();
  const m = mount({ transport: host, version: 2 });
  await tick();
  const release = host.hold("apply");
  const applying = m.ed.applyOp({ op: "AddBar", x_mm: 9, y_mm: 9, designation: "Ø16" }); // bar 2, revision 1, held
  await tick();
  await m.ed.sync(); // reads the host after the apply
  release();
  await applying;
  assert.deepEqual(m.ed.getScene().bars.map((b) => b.id), [2]);
  assert.deepEqual(m.ed.getDraft().bar_ids, [2]);
  assert.equal(m.ed.getOverlayState().revision, 1);
  assert.equal(m.changes.length, 1);
});

test("a refused sync() names the refusal and changes nothing", async () => {
  const host = fakeHost({ revision: 3 });
  let refuse = false;
  const m = mount({ transport: (req) => (refuse ? { ok: false, status: 409, error: { code: "STALE", message: "revision 3 is behind 4" } } : host(req)), version: 2 });
  await tick();
  const draft = m.ed.getDraft();
  refuse = true;
  const res = await m.ed.sync();
  assert.equal(res.ok, false);
  assert.equal(m.prompt(), "Refused: revision 3 is behind 4");
  assert.equal(m.ed.getOverlayState().revision, 3);
  assert.equal(m.ed.getDraft(), draft);
  assert.deepEqual(m.changes, []);
});

test("a read-only editor syncs too", async () => {
  const host = fakeHost({ revision: 2 });
  const m = mount({ transport: host, version: 2, readOnly: true });
  await tick();
  host.outside({ x_mm: 5, y_mm: 5 });
  assert.equal((await m.ed.sync()).ok, true);
  assert.deepEqual(m.ed.getDraft().bar_ids, [2]);
  assert.equal(m.ed.getOverlayState().revision, 3);
});

// --- chrome --------------------------------------------------------------------------------

function classes(node, out = []) {
  if (node.className) out.push(node.className);
  for (const child of node.children || []) classes(child, out);
  return out;
}

test("chrome {toolbar: false, sidebar: false} renders neither; the canvas and command line stay", () => {
  const m = mount({ transport: fakeHost(), version: 2, chrome: { toolbar: false, sidebar: false } });
  const all = classes(m.root);
  assert.equal(all.includes("apecad-section-toolbar"), false);
  assert.equal(all.includes("apecad-section-sidebar"), false);
  assert.equal(all.includes("apecad-section-btn"), false);
  assert.ok(all.includes("apecad-section-canvas") && all.includes("apecad-section-cmd"));
  assert.deepEqual(m.root.children.map((c) => c.className), ["apecad-section-stage", "apecad-section-bottom"]);
  assert.deepEqual(m.stage.children.map((c) => c.className), ["apecad-section-canvas"]);
});

test("with the toolbar hidden, the keys still undo and redo", async () => {
  const host = fakeHost();
  const m = mount({ transport: host, version: 2, chrome: { toolbar: false } });
  await tick();
  host.log.length = 0;
  m.key({ key: "z", ctrlKey: true });
  await tick();
  m.key({ key: "y", ctrlKey: true });
  await tick();
  assert.deepEqual(host.log, ["undo", "redo"]);
});

test("chrome hides each part on its own, and the default shows both", () => {
  const names = (chrome) => classes(mount({ transport: mockTransport(), chrome }).root);
  for (const [chrome, toolbar, sidebar] of [[undefined, true, true], [null, true, true], [{}, true, true],
    [{ toolbar: false }, false, true], [{ sidebar: false }, true, false], [{ toolbar: true, sidebar: true }, true, true]]) {
    const all = names(chrome);
    assert.equal(all.includes("apecad-section-toolbar"), toolbar, JSON.stringify(chrome));
    assert.equal(all.includes("apecad-section-sidebar"), sidebar, JSON.stringify(chrome));
  }
});

test("chrome refuses what it does not know, by name", () => {
  for (const [bad, named] of [[{ menu: false }, /unknown chrome option "menu"/], [{ toolbar: 0 }, /chrome\.toolbar must be true or false, not 0/],
    [{ sidebar: "no" }, /chrome\.sidebar must be true or false, not "no"/], ["none", /chrome "none" is not supported/],
    [false, /chrome false is not supported/], [[], /chrome \[\] is not supported/]]) {
    assert.throws(() => create({}, { chrome: bad }), named);
  }
});

// --- setGlyphs -----------------------------------------------------------------------------

test("setGlyphs draws the host's centroid at its world point, through pan, zoom and sync", async () => {
  const host = fakeHost();
  const m = mount({ transport: host, version: 2 });
  await tick();
  await m.ed.applyOp({ op: "AddBar", x_mm: 137.5, y_mm: 412.25, designation: "Ø16" }); // the witness
  const atBar = () => {
    m.rec.log.length = 0;
    m.ed.setParam("gridStepMm", 50); // any redraw
    const glyph = m.glyphArcs();
    const bar = m.rec.log.filter((a) => !glyph.includes(a));
    assert.equal(glyph.length, 1, "one centroid glyph");
    assert.ok(bar.length >= 1, "the bar is drawn");
    for (const b of bar) assert.deepEqual([b.x, b.y], [glyph[0].x, glyph[0].y]);
    return [glyph[0].x, glyph[0].y];
  };
  const res = m.ed.setGlyphs({ centroid_mm: [137.5, 412.25] });
  assert.deepEqual(res, { ok: true, status: 200, centroid_mm: [137.5, 412.25] });
  const first = atBar();
  m.zoom(90, 70, -1);
  const zoomed = atBar();
  m.pan(-23, 41);
  const panned = atBar();
  assert.notDeepEqual(zoomed, first);
  assert.notDeepEqual(panned, zoomed);
  host.outside({ x_mm: 5, y_mm: 5 });
  await m.ed.sync();
  m.rec.log.length = 0;
  m.ed.setParam("gridStepMm", 50);
  assert.deepEqual(m.glyphArcs().map((a) => [a.x, a.y]), [panned], "sync keeps the glyph and the view");
  assert.deepEqual(m.changes.length, 1);
});

test("setGlyphs refuses by name, and a refusal or null clears the glyph", async () => {
  const m = mount({ transport: fakeHost(), version: 2 });
  await tick();
  const drawn = () => { m.rec.log.length = 0; m.ed.setParam("gridStepMm", 50); return m.glyphArcs().length; };
  assert.equal(drawn(), 0);
  assert.equal(m.ed.setGlyphs({ centroid_mm: [0, 0] }).ok, true);
  assert.equal(drawn(), 1);
  for (const [bad, path] of [[{ axes: { angle_deg: 0 } }, "glyphs.axes"], [{ centroid_mm: [1, Number.NaN] }, "glyphs.centroid_mm"],
    [{ centroid_mm: [1, 2, 3] }, "glyphs.centroid_mm"], [{ centroid_mm: "0,0" }, "glyphs.centroid_mm"],
    [{ centroid_mm: [1, "2"] }, "glyphs.centroid_mm"], [[0, 0], "glyphs"], ["centroid", "glyphs"]]) {
    m.ed.setGlyphs({ centroid_mm: [0, 0] });
    const res = m.ed.setGlyphs(bad);
    assert.equal(res.ok, false, JSON.stringify(bad));
    assert.equal(res.status, 422);
    assert.equal(res.error.code, "INVALID_ARGUMENT");
    assert.equal(res.error.path, path);
    assert.equal(drawn(), 0, `a refused ${JSON.stringify(bad)} leaves no glyph`);
  }
  assert.match(m.ed.setGlyphs({ axes: {} }).error.message, /unknown glyph "axes", expected centroid_mm/);
  m.ed.setGlyphs({ centroid_mm: [0, 0] });
  assert.deepEqual(m.ed.setGlyphs(null), { ok: true, status: 200, centroid_mm: null });
  assert.equal(drawn(), 0);
  assert.deepEqual(m.ed.setGlyphs({}), { ok: true, status: 200, centroid_mm: null });
  assert.deepEqual(m.changes, [], "a glyph is not an edit");
});
