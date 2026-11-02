// The 2-D client draws v2 (C5 record §3 "Client drawing", §4 invariants 3, 4, 8 and 12; C5-S3).
// Oracles named from outside the code: the record's layer order, the role order void > steel >
// concrete whatever the ids, even-odd fill whatever a ring's winding, the geometry of a hole,
// `require_v1_expressible`'s four cases, and the ADR 0038 gates. The fixtures' ids against
// `render` are `tests/test_section_client_v2.py`'s (a pytest-driven node run).
import assert from "node:assert/strict";
import test from "node:test";

import { create, mockTransport } from "../../src/apeCAD/scratchpad/static/section/apecad-section.js";
import { PALETTE, createViewport, hitTestSection, renderSectionCanvas } from "../../src/apeCAD/scratchpad/static/section/canvas2d.js";
import { SECTION_LAYERS, displayList, entityTitle, sceneBoundsMm } from "../../src/apeCAD/scratchpad/static/section/display2d.js";
import { normalizeScene, seedToOps, v1DraftOrNull, v1Unsayable } from "../../src/apeCAD/scratchpad/static/section/transport.js";
import { contrastRatio, oklabDistance, simulateCvdHex } from "../../src/apeCAD/scratchpad/static/js/theme.js";

const ring = (x0, y0, x1, y1) => [[x0, y0], [x1, y0], [x1, y1], [x0, y1]];
const ringFace = (id, role, outer, holes = []) => ({
  entity_id: id, label: null, role, material: role === "void" ? null : role === "steel" ? "S355" : "C30",
  boundary: { kind: "ring", ring_mm: outer }, holes: holes.map((h) => (Array.isArray(h) ? { kind: "ring", ring_mm: h } : h)),
});
const circle = (c, r) => ({ kind: "circle", center_mm: c, radius_mm: r });
const sceneOf = (extra) => normalizeScene({ points: [], ...extra });

// A recording 2-D context: each fill is logged with its style, rule and the subpaths of the
// path it fills (one per moveTo), so a hole's place in the face's path is visible.
function recorder() {
  const log = [];
  let subpaths = 0;
  const ctx = {
    fillStyle: "", strokeStyle: "", lineWidth: 1,
    save() {}, restore() {}, closePath() {}, lineTo() {}, arc() {}, setLineDash() {}, fillRect() {}, strokeRect() {},
    beginPath() { subpaths = 0; },
    moveTo() { subpaths += 1; },
    fill(rule) { log.push({ op: "fill", style: ctx.fillStyle, rule: rule ?? "nonzero", subpaths }); },
    stroke() { log.push({ op: "stroke", style: ctx.strokeStyle, subpaths }); },
  };
  return { canvas: { getContext: () => ctx, clientWidth: 800, clientHeight: 600 }, log };
}

function paint(scene, selectedIds = new Set()) {
  const rec = recorder();
  const view = createViewport(rec.canvas);
  view.fit(scene);
  renderSectionCanvas(rec.canvas, view, { scene, selectedIds, gridOn: false });
  return { log: rec.log.filter((e) => e.op === "fill"), view };
}

const at = (view, xy) => view.worldToScreen(xy);

// --- invariant 3: overlaps paint concrete, steel, void, whatever the ids ------------------

test("a reversed-id document paints concrete, then steel, then void", () => {
  const scene = sceneOf({
    section_faces: [
      ringFace(1, "void", ring(150, 150, 250, 250)),
      ringFace(2, "steel", ring(100, 100, 300, 300)),
      ringFace(3, "concrete", ring(0, 0, 400, 400)),
    ],
  });
  const display = displayList(scene);
  assert.deepEqual(display.entries.map((e) => [e.id, e.layer]), [[3, "concrete"], [2, "steel"], [1, "void"]]);
  assert.deepEqual(display.notDrawn, []);
  const { log, view } = paint(scene);
  assert.deepEqual(log.map((e) => e.style), [PALETTE.concreteFill, PALETTE.steelFill, PALETTE.voidFill]);
  // What is on top is what a click takes: the void, then the steel around it, then concrete.
  assert.equal(hitTestSection(at(view, [200, 200]), view, scene).id, 1);
  assert.deepEqual(hitTestSection(at(view, [120, 200]), view, scene, 2), { kind: "SectionFace", id: 2, item: scene.section_faces[1], role: "steel" });
  assert.equal(hitTestSection(at(view, [50, 200]), view, scene, 2).id, 3);
});

test("the display list holds every section kind on render's layers, in render's order", () => {
  assert.deepEqual(SECTION_LAYERS, ["concrete", "steel", "void", "cover", "leg", "hoop", "crosstie", "circular-tie", "bar"]);
  const scene = sceneOf({
    bars: [{ entity_id: 2, x_mm: 0, y_mm: 0, diameter_mm: 20, designation: "Ø20" }],
    circular_ties: [{ entity_id: 3, kind: "spiral", center_mm: [0, 0], centerline_radius_mm: 200, designation: "Ø10", diameter_mm: 10, pitch_mm: 75 }],
    cover_guides: [{ entity_id: 4, face_id: 9, cover_ring_mm: ring(-240, -240, 240, 240) }],
    section_faces: [ringFace(9, "concrete", ring(-300, -300, 300, 300))],
    templates: [{ entity_id: 1, template: "circular_column", template_version: 1, params: {}, child_ids: [2, 3, 4, 9] }],
  });
  assert.deepEqual(displayList(scene).entries.map((e) => [e.id, e.layer]), [[9, "concrete"], [4, "cover"], [3, "circular-tie"], [2, "bar"]]);
  const { log } = paint(scene);
  assert.deepEqual(log.map((e) => e.style), [PALETTE.concreteFill, PALETTE.rebar]);
  const [minX, , maxX] = sceneBoundsMm({ circular_ties: scene.circular_ties });
  assert.deepEqual([minX, maxX], [-200, 200]);
});

// --- invariant 4: holes stay unfilled, whatever the ring orientation ----------------------

for (const [name, hole] of [
  ["a counter-clockwise ring", ring(150, 150, 250, 250)],
  ["a clockwise ring", ring(150, 150, 250, 250).reverse()],
  ["a circle", circle([200, 200], 50)],
]) {
  test(`a hole drawn as ${name} is one even-odd path with its face, and a click in it misses`, () => {
    for (const outer of [ring(0, 0, 400, 400), ring(0, 0, 400, 400).reverse()]) {
      const scene = sceneOf({ section_faces: [ringFace(5, "steel", outer, [hole])] });
      const { log, view } = paint(scene);
      assert.deepEqual(log, [{ op: "fill", style: PALETTE.steelFill, rule: "evenodd", subpaths: 2 }]);
      assert.equal(hitTestSection(at(view, [200, 200]), view, scene, 2), null, "inside the hole");
      assert.equal(hitTestSection(at(view, [60, 200]), view, scene, 2)?.id, 5, "in the steel");
      const selected = paint(scene, new Set([5])).log;
      assert.ok(selected.every((e) => e.rule === "evenodd" && e.subpaths === 2), JSON.stringify(selected));
    }
  });
}

test("a circle face is drawn exactly and a filled tube keeps its concrete core clickable", () => {
  const scene = sceneOf({
    section_faces: [
      { ...ringFace(7, "steel", []), boundary: circle([0, 0], 200), holes: [circle([0, 0], 190)] },
      { ...ringFace(8, "concrete", []), boundary: circle([0, 0], 190), holes: [] },
    ],
  });
  const { log, view } = paint(scene);
  assert.deepEqual(log.map((e) => [e.style, e.rule, e.subpaths]), [
    [PALETTE.concreteFill, "evenodd", 1], [PALETTE.steelFill, "evenodd", 2],
  ]);
  assert.equal(hitTestSection(at(view, [0, 0]), view, scene, 2).id, 8, "the core, through the tube's hole");
  assert.equal(hitTestSection(at(view, [0, 195]), view, scene, 1).id, 7, "the tube wall");
});

// --- refuse by name, never guess ----------------------------------------------------------

test("a face or a tie the reader does not know draws nothing and is named", () => {
  const scene = sceneOf({
    section_faces: [
      ringFace(1, "glass", ring(0, 0, 1, 1)),
      { ...ringFace(2, "concrete", []), boundary: { kind: "spline" } },
      ringFace(3, "concrete", ring(0, 0, 100, 100), [{ kind: "circle", center_mm: [50, 50], radius_mm: 0 }]),
    ],
    circular_ties: [{ entity_id: 4, kind: "spiral", center_mm: [0, 0], centerline_radius_mm: -5 }],
  });
  const { entries, notDrawn } = displayList(scene);
  assert.deepEqual(entries, []);
  assert.deepEqual(notDrawn.map((n) => n.message), [
    'face 1 has an unknown role "glass"',
    'face 2 boundary has an unknown boundary kind "spline"',
    "face 3 hole 0 is not a circle with a centre and a radius > 0",
    "circular tie 4 is not a circle with a centre and a radius > 0",
  ]);
});

test("the editor names an undrawable item in its warnings and titles v2 entities", async () => {
  const ed = create({}, { transport: async () => ({
    ok: true, status: 200, draft: null,
    scene: { section_faces: [ringFace(1, "glass", ring(0, 0, 1, 1)), ringFace(2, "void", ring(0, 0, 9, 9))] },
  }) });
  await new Promise((r) => setTimeout(r, 10));
  assert.equal(ed.getDraft(), null);
  const status = ({ children }) => children[2].children[2].textContent;
  const container = {};
  const shown = create(container, { transport: async () => ({ ok: true, status: 200, draft: null, scene: ed.getScene() }) });
  await new Promise((r) => setTimeout(r, 10));
  assert.match(status(container.children[0]), /2 face .* WARN 1$/);
  const warnBox = container.children[0].children[1].children[1].children[1];
  assert.deepEqual(warnBox.children.map((c) => c.textContent), ['[not-drawn] face 1 has an unknown role "glass"']);
  assert.equal(entityTitle(ed.getScene(), 2), "Face #2 (void)");
  assert.equal(entityTitle({ circular_ties: [{ id: 3, kind: "hoop", designation: "Ø10", pitch_mm: 150 }] }, 3), "Tie #3 (Ø10 @ 150)");
  ed.dispose();
  shown.dispose();
});

// --- invariant 8: no client path writes a v1 draft that drops a v2 entity -----------------

test("v1 cannot say a v2 face, a circular tie, a template or a steel bar: no v1 draft for them", () => {
  const cases = {
    "face 1 is a v2 concrete face": { section_faces: [ringFace(1, "concrete", ring(0, 0, 9, 9))] },
    "entity 2 is a circular tie (spiral)": { circular_ties: [{ entity_id: 2, kind: "spiral", center_mm: [0, 0], centerline_radius_mm: 9 }] },
    "entity 3 is a rect_column template": { templates: [{ entity_id: 3, template: "rect_column", child_ids: [] }] },
    'bar 4 names its steel "B500"': { bars: [{ entity_id: 4, x_mm: 0, y_mm: 0, designation: "Ø16", material: "B500" }] },
  };
  for (const [reason, raw] of Object.entries(cases)) {
    const scene = sceneOf(raw);
    assert.equal(v1Unsayable(scene), reason);
    assert.equal(v1DraftOrNull(scene), null, reason);
  }
  const v1 = sceneOf({ bars: [{ entity_id: 4, x_mm: 0, y_mm: 0, designation: "Ø16", material: null }] });
  assert.equal(v1Unsayable(v1), null);
  assert.equal(v1DraftOrNull(v1).section.bars.length, 1);
});

test("the v1 seed reader refuses a v2 block by name instead of dropping its faces", async () => {
  const seed = { schema: "apeCAD.section-seed", version: 2, units: "mm", section: { faces: [{ role: "concrete" }], bars: [] } };
  assert.throws(() => seedToOps(seed, () => []), /apeCAD.section-seed version 2 is not read here/);
  const unversioned = { schema: "apeCAD.section-seed", section: { faces: [] } };
  assert.throws(() => seedToOps(unversioned, () => []), /version null is not read here/);
  const res = await mockTransport()({ action: "seed", payload: seed });
  assert.equal(res.ok, false);
  assert.match(res.error.message, /version 2 is not read here/);
});

// --- invariant 12: the steel fill passes ADR 0038's gates on this canvas -------------------

const over = (rgba, bg) => {
  const [r, g, b, a] = rgba.match(/[\d.]+/g).map(Number);
  const [br, bgG, bb] = [1, 3, 5].map((i) => parseInt(bg.slice(i, i + 2), 16));
  const mix = (c, d) => Math.round(a * c + (1 - a) * d).toString(16).padStart(2, "0");
  return `#${mix(r, br)}${mix(g, bgG)}${mix(b, bb)}`;
};

test("steel reads apart from the canvas, the concrete and the bars (ADR 0038)", () => {
  const concrete = over(PALETTE.concreteFill, PALETTE.bg);
  assert.ok(contrastRatio(PALETTE.steelFill, PALETTE.bg) >= 2.2);
  assert.ok(contrastRatio(PALETTE.rebar, PALETTE.steelFill) >= 2.2);
  for (const mode of ["normal", "protan", "deutan"]) {
    const [a, b] = mode === "normal" ? [PALETTE.steelFill, concrete] : [simulateCvdHex(PALETTE.steelFill, mode), simulateCvdHex(concrete, mode)];
    assert.ok(oklabDistance(a, b) >= 0.055, mode);
  }
  assert.equal(PALETTE.voidFill, PALETTE.bg, "a void is the paper colour");
});

// --- huge input: bounded time, nothing dropped ---------------------------------------------

test("a scene of 10^5 bars is listed, painted and hit-tested in bounded time", () => {
  const bars = Array.from({ length: 100000 }, (_, i) => ({ entity_id: i + 1, x_mm: (i % 400) * 10, y_mm: Math.floor(i / 400) * 10, designation: "Ø8", diameter_mm: 8 }));
  const t0 = Date.now();
  const scene = sceneOf({ bars });
  assert.equal(displayList(scene).entries.length, 100000);
  const { log, view } = paint(scene);
  assert.equal(log.length, 100000);
  assert.equal(hitTestSection(at(view, [0, 0]), view, scene).id, 1);
  assert.ok(Date.now() - t0 < 10000, `${Date.now() - t0} ms`);
});
