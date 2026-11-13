// Overlay legibility and the axes glyph in the section client (C8b; RGc3 findings F6 and F7;
// the SVG side is `tests/test_render_legibility.py`). Oracles:
// - F6: over an overlay, the section's outlines, hoops, ties and bars are stroked again, every
//   halo first, then every ink line, above the overlay and under the host's glyphs.
// - F6: a valued marker is ringed in `--ink-edge` on a paper halo; ink or halo contrasts at least
//   3:1 (WCAG 2.1 non-text) with every colour the example and fixture scales can paint.
// - F6: a legend tick sits at its stop: a diverging mid at (mid - lo) / (hi - lo) of the bar.
// - F6: the diverging example palette is colour-vision-safe by a stated method (below).
// - F7: the axes and origin glyph is on every frame, at the world origin, x right and y up;
//   the host's centroid glyph keeps its place and its style.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { create, mockTransport } from "../../src/apeCAD/scratchpad/static/section/apecad-section.js";
import {
  AXES_ARM_PX, OVERLAY_EXAMPLE_SCALES, OVERLAY_TOKENS, PALETTE, createViewport, renderSectionCanvas,
} from "../../src/apeCAD/scratchpad/static/section/canvas2d.js";
import { MARKER_MIN_RADIUS_PX, MARKER_RING, paintOverlay, parseOverlay, scaleColor, tickPercent } from "../../src/apeCAD/scratchpad/static/section/overlay.js";
import { normalizeScene } from "../../src/apeCAD/scratchpad/static/section/transport.js";
import { contrastRatio, oklabDistance, relativeLuminance, simulateCvdHex } from "../../src/apeCAD/scratchpad/static/js/theme.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES = path.resolve(HERE, "../fixtures/section_overlay/valid");
const readJson = (name) => JSON.parse(fs.readFileSync(path.join(FIXTURES, name), "utf8"));

// A recording 2-D context: strokes with their style and width, fills, arcs, path points, text.
function recorder() {
  const log = [];
  const ctx = {
    globalAlpha: 1, fillStyle: "", strokeStyle: "", lineWidth: 1, font: "", lineCap: "", lineJoin: "",
    save() {}, restore() {}, beginPath() {}, closePath() {}, setLineDash() {}, fillRect() {}, strokeRect() {},
    moveTo(x, y) { log.push(["move", x, y]); },
    lineTo(x, y) { log.push(["line", x, y]); },
    arc(x, y, r) { log.push(["arc", x, y, r, ctx.lineWidth, ctx.strokeStyle]); },
    fill() { log.push(["fill", ctx.fillStyle]); },
    stroke() { log.push(["stroke", ctx.strokeStyle, ctx.lineWidth]); },
    fillText(text, x, y) { log.push(["text", text, ctx.fillStyle, x, y]); },
  };
  return { ctx, log, canvas: { getContext: () => ctx, clientWidth: 800, clientHeight: 600 } };
}

const SEED = {
  schema: "apeCAD.section-seed", version: 1, units: "mm",
  section: {
    concrete_faces: [{ ring_mm: [[0, 0], [1000, 0], [1000, 200], [0, 200]], material: "concrete" }],
    bars: [
      { x_mm: 50, y_mm: 50, designation: "Ø16", diameter_mm: 16 },
      { x_mm: 950, y_mm: 50, designation: "Ø16", diameter_mm: 16 },
      { x_mm: 950, y_mm: 150, designation: "Ø16", diameter_mm: 16 },
      { x_mm: 50, y_mm: 150, designation: "Ø16", diameter_mm: 16 },
    ],
    hoops: [{ bar_ids: [0, 1, 2, 3], designation: "Ø10", diameter_mm: 10, spacing_mm: 100, hooks: "135" }],
    crossties: [{ bar_a_id: 0, bar_b_id: 2, designation: "Ø10", diameter_mm: 10, spacing_mm: 100, hooks: "135-90" }],
  },
};

async function seededScene() {
  const res = await mockTransport()({ action: "seed", payload: SEED });
  assert.equal(res.ok, true);
  return normalizeScene(res.scene);
}

const strokes = (log) => log.filter((e) => e[0] === "stroke");

// --- F6: the section's ink over the overlay ------------------------------------------------

test("over an overlay the section is stroked again: every halo, then every ink line, under the glyphs", async () => {
  const scene = await seededScene();
  const view = createViewport({ width: 800, height: 600 });
  view.fit(scene);
  const rec = recorder();
  renderSectionCanvas(rec.canvas, view, {
    scene, gridOn: false,
    drawOverlay: () => rec.log.push(["overlay"]),
    drawMarkers: () => rec.log.push(["markers"]),
    drawGlyphs: () => rec.log.push(["glyphs"]),
  });
  const at = (tag) => rec.log.findIndex((e) => e[0] === tag);
  const between = strokes(rec.log.slice(at("overlay"), at("markers")));
  // The face's outline, the hoop, the crosstie and the four bars: back to front, as drawn.
  const inks = [PALETTE.concreteEdge, PALETTE.hoop, PALETTE.crosstie, ...Array(4).fill(PALETTE.rebar)];
  assert.deepEqual(between.map((e) => e[1]), [...Array(inks.length).fill(PALETTE.bg), ...inks]);
  // Each halo line is 1 px wider each side than its ink line, bars excepted (rings below).
  between.slice(0, 3).forEach((halo, i) => assert.equal(halo[2], between[inks.length + i][2] + 2));
  // A bar is a ring at its drawn radius, its halo just outside it: the overlay shows inside.
  const arcs = rec.log.slice(at("overlay"), at("markers")).filter((e) => e[0] === "arc");
  const r = Math.max(3.5, 8 * view.scale);
  assert.deepEqual(arcs.map((e) => [e[3], e[4], e[5]]), [
    ...Array(4).fill([r + 1, 1, PALETTE.bg]), ...Array(4).fill([r, 1, PALETTE.rebar]),
  ]);
  assert.ok(at("glyphs") < rec.log.findIndex((e) => e[0] === "text" && e[1] === "x"), "the axes over the glyphs");
  // The valued markers come after every ink line and before the host's glyphs (review F1).
  assert.ok(at("markers") < at("glyphs"));
  assert.deepEqual(strokes(rec.log.slice(at("markers"), at("glyphs"))), [], "no ink over the markers");
});

test("with no overlay nothing is stroked again", async () => {
  const scene = await seededScene();
  const view = createViewport({ width: 800, height: 600 });
  view.fit(scene);
  const rec = recorder();
  renderSectionCanvas(rec.canvas, view, { scene, gridOn: false });
  assert.deepEqual(strokes(rec.log).filter((e) => e[1] === PALETTE.bg), [["stroke", PALETTE.bg, 3]]); // the axes' halo only
});

// --- F6: valued markers --------------------------------------------------------------------

test("a valued marker: paper disc under it, fill of at least 3 px, ring outside the fill; styled ones as styled", () => {
  assert.equal(MARKER_RING, OVERLAY_TOKENS["--ink-edge"]);
  const scale = { kind: "categorical", domain: ["elastic", "yielded"], colors: ["#2f74ad", "#c64a1a"], unit: "", title: "" };
  const overlay = parseOverlay({
    schema: "apeCAD.section-overlay", version: 1, units: "mm", revision: 0,
    layers: [{ id: "b", label: "", visible: true, scale, primitives: [
      { kind: "circle", center: [0, 0], radius: 8, value: "yielded" },
      { kind: "point", at: [10, 0], value: "elastic" },
      { kind: "circle", center: [20, 0], radius: 8, style: { fill: "#123456" } },
    ] }],
  });
  assert.equal(MARKER_MIN_RADIUS_PX, 3);
  const rec = recorder();
  const view = { scale: 0.2, worldToScreen: ([x, y]) => [x, -y] }; // 1:25: the 8 mm radius is 1.6 px
  paintOverlay(rec.ctx, view, overlay);
  const ops = rec.log.filter((e) => e[0] !== "move" && e[0] !== "line").map((e) => (e[0] === "arc" ? e.slice(0, 4) : e));
  assert.deepEqual(ops, [
    ["arc", 0, -0, 5], ["fill", PALETTE.bg], ["arc", 0, -0, 3], ["fill", "#c64a1a"],
    ["arc", 0, -0, 3.5], ["stroke", MARKER_RING, 1],
    ["arc", 10, -0, 5], ["fill", PALETTE.bg], ["arc", 10, -0, 3], ["fill", "#2f74ad"],
    ["arc", 10, -0, 3.5], ["stroke", MARKER_RING, 1],
    ["arc", 20, -0, 1.6], ["fill", "#123456"],
  ]);
  // `pass` splits them: the field pass leaves the markers out, the marker pass draws only them.
  const field = recorder(), markers = recorder();
  paintOverlay(field.ctx, view, overlay, { pass: "field" });
  paintOverlay(markers.ctx, view, overlay, { pass: "markers" });
  assert.deepEqual(field.log.filter((e) => e[0] === "fill").map((e) => e[1]), ["#123456"]);
  assert.deepEqual(markers.log.filter((e) => e[0] === "fill").map((e) => e[1]), [PALETTE.bg, "#c64a1a", PALETTE.bg, "#2f74ad"]);
});

const sampled = (scaleJson) => {
  const one = { schema: "apeCAD.section-overlay", version: 1, units: "mm", revision: 0, layers: [{ id: "a", label: "", visible: true, scale: scaleJson, primitives: [] }] };
  const scale = parseOverlay(one).layers[0].scale;
  if (scale.kind === "categorical") return scale.domain.map((v) => scaleColor(scale, v));
  const lo = scale.domain[0], hi = scale.domain[scale.domain.length - 1];
  return Array.from({ length: 33 }, (_, k) => scaleColor(scale, lo + ((hi - lo) * k) / 32));
};

test("a ring or its halo contrasts 3:1 with every colour the example and fixture scales paint", () => {
  const scales = [...Object.values(OVERLAY_EXAMPLE_SCALES), ...readJson("rect_wall_results.json").layers.map((l) => l.scale).filter(Boolean)];
  const pens = [MARKER_RING, PALETTE.rebar, PALETTE.hoop, PALETTE.concreteEdge, PALETTE.originGlyph];
  const worst = [];
  for (const scale of scales) {
    for (const field of sampled(scale)) {
      for (const pen of pens) worst.push(Math.max(contrastRatio(pen, field), contrastRatio(PALETTE.bg, field)));
    }
  }
  assert.ok(worst.length > 200);
  assert.ok(Math.min(...worst) >= 3, `worst ${Math.min(...worst).toFixed(2)}`);
});

// --- F6: legend ticks at their stops -------------------------------------------------------

const SQUARE = {
  schema: "apeCAD.document.v1", units: "mm",
  ops: [{ op: "AddSectionOutline", point_ids: [{ xyz: [0, 0, 0] }, { xyz: [400, 0, 0] }, { xyz: [400, 400, 0] }, { xyz: [0, 400, 0] }], material: "concrete" }],
};

async function editorWithRecorder() {
  const container = {};
  const editor = create(container, { transport: mockTransport() });
  await editor.loadDraft(SQUARE);
  const root = container.children[0];
  const rec = recorder();
  root.children[1].children[0].getContext = () => rec.ctx;
  return { editor, rec, panel: root.children[1].children[1].children[2] };
}

test("each legend tick sits at its stop: a diverging mid under its mark, never spread evenly", async () => {
  const { editor, panel } = await editorWithRecorder();
  const results = readJson("rect_wall_results.json");
  results.revision = editor.getOverlayState().revision;
  results.layers.find((l) => l.id === "hidden").visible = true; // a sequential legend too
  assert.equal(editor.setOverlay(results).ok, true);
  const legends = panel.children.filter((n) => n.className === "apecad-section-legend");
  const stress = legends.find((n) => n.dataset.layer === "stress");
  const [bar, ticks] = [stress.children[1], stress.children[2]];
  // Domain [-30, 0, 400]: 0 sits 30 / 430 = 6.97674 % along the bar, where the white stop is.
  assert.equal(tickPercent({ domain: [-30, 0, 400] }, 0), "6.97674");
  assert.match(bar.style.background, / #f7f7f7 6\.97674%, /);
  assert.deepEqual(ticks.children.map((n) => [n.textContent, n.dataset.at]), [["-30", "0"], ["0", "6.97674"], ["400", "100"]]);
  const [lo, mid, hi] = ticks.children.map((n) => n.style);
  assert.deepEqual([lo.left, lo.right, hi.left, hi.right], ["0", undefined, undefined, "0"]);
  assert.equal(mid.left, "clamp(0px, calc(6.97674% - 0.5ch), calc(100% - 1ch))");
  assert.ok(ticks.className.includes("two-rows") && ticks.children[1].className.includes("mid"));
  assert.deepEqual(bar.children.map((n) => [n.className, n.style.left]), [["apecad-section-legend-mark", "6.97674%"]]);
  const hidden = legends.find((n) => n.dataset.layer === "hidden");
  assert.deepEqual(hidden.children[2].children.map((n) => [n.textContent, n.dataset.at, n.style.left, n.style.right]), [["0", "0", "0", undefined], ["1", "100", undefined, "0"]]);
  assert.deepEqual(hidden.children[1].children, []);
  const css = fs.readFileSync(path.resolve(HERE, "../../src/apeCAD/scratchpad/static/section/section.css"), "utf8");
  const block = css.slice(css.indexOf(".apecad-section-legend-ticks {"), css.indexOf("}", css.indexOf(".apecad-section-legend-ticks {")));
  assert.equal(/space-between/.test(block), false);
  assert.match(block, /position: relative/);
  editor.dispose();
});

// --- F6: the diverging palette is colour-vision-safe ----------------------------------------
// Method: simulate protanopia and deuteranopia (Viénot, Brettel & Mollon 1999, `theme.js`) and
// sample each arm of the diverging scale at nine points with the renderer's own `scaleColor`.
// (1) In every vision, relative luminance rises strictly from each end to the mid, so the
// magnitude reads by lightness alone, whatever the hue. (2) In every vision, the two arms at
// the same fraction of their length from the ends, up to the half, are at least 0.055 OKLab
// apart (ADR 0038's threshold), so the sign reads by hue: compression never looks like tension.

const VISIONS = ["normal", "protan", "deutan"];
const hexOf = (n) => `#${n.toString(16).padStart(6, "0")}`;
const seen = (color, vision) => (vision === "normal" ? color : hexOf(simulateCvdHex(color, vision)));

function divergingFailures(scaleJson) {
  const one = { schema: "apeCAD.section-overlay", version: 1, units: "mm", revision: 0, layers: [{ id: "a", label: "", visible: true, scale: scaleJson, primitives: [] }] };
  const scale = parseOverlay(one).layers[0].scale;
  const [lo, mid, hi] = scale.domain;
  const failures = [];
  for (const vision of VISIONS) {
    const arm = (end) => Array.from({ length: 9 }, (_, k) => seen(scaleColor(scale, end + ((mid - end) * k) / 8), vision));
    const [left, right] = [arm(lo), arm(hi)];
    for (const [name, colors] of [["low", left], ["high", right]]) {
      const ys = colors.map((c) => relativeLuminance(c));
      ys.slice(1).forEach((y, k) => { if (!(y > ys[k])) failures.push(`${vision} ${name} arm: luminance falls at step ${k + 1}`); });
    }
    for (let k = 0; k <= 4; k++) {
      const d = oklabDistance(left[k], right[k]);
      if (d < 0.055) failures.push(`${vision} arms at ${k}/8: ${d.toFixed(3)} < 0.055`);
    }
  }
  return failures;
}

test("the diverging example palette is colour-vision-safe by the stated method", () => {
  assert.equal(OVERLAY_EXAMPLE_SCALES.stress.kind, "diverging");
  assert.deepEqual(divergingFailures(OVERLAY_EXAMPLE_SCALES.stress), []);
});

test("the method has teeth: a red-to-green diverging scale fails it for a deuteranope", () => {
  const redGreen = { kind: "diverging", domain: [-1, 0, 1], colors: ["#1a9850", "#f7f7f7", "#d73027"], unit: "", title: "" };
  const failures = divergingFailures(redGreen);
  assert.ok(failures.some((f) => f.startsWith("deutan arms")), failures.join("; "));
  assert.equal(failures.some((f) => f.startsWith("normal")), false);
});

// --- F7: the axes glyph and the centroid ----------------------------------------------------

test("the axes and origin glyph is on every frame at the world origin, x right and y up", () => {
  for (const scene of [null, { concrete_faces: [] }]) {
    const view = createViewport({ width: 400, height: 300 });
    view.panX = 37; view.panY = 51; view.scale = 0.3;
    const rec = recorder();
    renderSectionCanvas(rec.canvas, view, { scene, gridOn: false });
    const [ox, oy] = view.worldToScreen([0, 0]);
    const pts = rec.log.filter((e) => e[0] === "move" || e[0] === "line").map((e) => `${e[0]} ${e[1]} ${e[2]}`);
    for (const p of [`move ${ox} ${oy}`, `line ${ox + AXES_ARM_PX} ${oy}`, `line ${ox} ${oy - AXES_ARM_PX}`]) assert.ok(pts.includes(p), p);
    assert.deepEqual(strokes(rec.log).slice(-2), [["stroke", PALETTE.bg, 3], ["stroke", PALETTE.originGlyph, 1]]);
    const texts = rec.log.filter((e) => e[0] === "text");
    assert.deepEqual(texts.map((e) => [e[1], e[2]]), [["x", PALETTE.originGlyph], ["y", PALETTE.originGlyph]]);
    assert.ok(texts[0][3] > ox + AXES_ARM_PX && texts[1][4] < oy, "x past the x arrow, y above the origin");
  }
});

test("the host's centroid keeps its place and its style, over the section ink", async () => {
  const { editor, rec } = await editorWithRecorder();
  const centroid = () => rec.log.filter((e) => e[0] === "arc" && e[3] === 6 && e[4] === 1.25);
  rec.log.length = 0;
  assert.equal(editor.setGlyphs({ centroid_mm: [200, 200] }).ok, true);
  const [alone] = centroid();
  assert.deepEqual(alone.slice(5), [PALETTE.concreteEdge]);
  const field = { kind: "polygon", ring: [[0, 0], [400, 0], [400, 400], [0, 400]], value: 1 };
  const scale = { kind: "sequential", domain: [0, 1], colors: ["#6baed6", "#08306b"], unit: "", title: "" };
  rec.log.length = 0;
  const overlay = { schema: "apeCAD.section-overlay", version: 1, units: "mm", revision: editor.getOverlayState().revision, layers: [{ id: "f", label: "", visible: true, scale, primitives: [field] }] };
  assert.equal(editor.setOverlay(overlay).ok, true);
  const [over] = centroid();
  assert.deepEqual(over, alone, "the same place, radius, pen and colour");
  const inkAt = rec.log.findLastIndex((e) => e[0] === "stroke" && e[1] === PALETTE.concreteEdge && e[2] === 1.5);
  assert.ok(inkAt > 0 && rec.log.indexOf(over) > inkAt, "painted after the outline's ink");
  editor.dispose();
});
