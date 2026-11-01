// The section client's results overlay (ADR 0041 D2, stage C2-S2). Oracles: the shared
// fixtures of `tests/fixtures/section_overlay/` (the same code and path as the Python reader,
// `apeCAD.render.overlay.parse_overlay`), the hand-worked colour lookups, the code-built cases
// JSON cannot carry, and the ADR 0038 contrast and CVD gates for the example scales.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { create, mockTransport } from "../../src/apeCAD/scratchpad/static/section/apecad-section.js";
import {
  OVERLAY_EXAMPLE_SCALES, OVERLAY_TOKENS, PALETTE, createViewport, renderSectionCanvas,
} from "../../src/apeCAD/scratchpad/static/section/canvas2d.js";
import {
  MAX_OVERLAY_PRIMITIVES, OverlayError, STALE_ALPHA, liveTokens, paintOverlay, parseOverlay, scaleColor,
} from "../../src/apeCAD/scratchpad/static/section/overlay.js";
import { contrastRatio, oklabDistance, simulateCvdHex } from "../../src/apeCAD/scratchpad/static/js/theme.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES = path.resolve(HERE, "../fixtures/section_overlay");
const readJson = (name) => JSON.parse(fs.readFileSync(path.join(FIXTURES, name), "utf8"));
const VALID = fs.readdirSync(path.join(FIXTURES, "valid")).filter((f) => f.endsWith(".json"));

function one(primitive, scale = null, revision = 0) {
  return {
    schema: "apeCAD.section-overlay", version: 1, units: "mm", revision,
    layers: [{ id: "a", label: "A", visible: true, scale, primitives: [primitive] }],
  };
}

function refusalOf(value) {
  try {
    parseOverlay(value);
  } catch (err) {
    assert.ok(err instanceof OverlayError, String(err));
    assert.ok(err.message.startsWith(`${err.path} `), err.message);
    return { code: err.code, path: err.path };
  }
  return null;
}

// --- parity with the Python reader --------------------------------------------------------

test("every valid fixture is accepted", () => {
  assert.ok(VALID.length >= 4);
  for (const name of VALID) {
    const overlay = parseOverlay(readJson(path.join("valid", name)));
    assert.ok(Array.isArray(overlay.layers), name);
  }
});

test("every invalid fixture is refused with the Python reader's code and path", () => {
  const cases = readJson("invalid.json");
  assert.ok(cases.length >= 70);
  for (const c of cases) assert.deepEqual(refusalOf(c.overlay), c.refusal, c.case);
});

test("every hand-worked colour lookup is reproduced exactly", () => {
  for (const c of readJson("colors.json")) {
    const { scale } = parseOverlay(one({ kind: "point", at: [0, 0], style: { fill: "#000" } }, c.scale)).layers[0];
    assert.equal(scaleColor(scale, c.value), c.color, c.case);
  }
});

test("non-finite numbers, built in code, are refused naming the field", () => {
  for (const bad of [Number.NaN, Infinity, -Infinity]) {
    assert.deepEqual(refusalOf(one({ kind: "point", at: [bad, 0], style: { fill: "#000" } })),
      { code: "INVALID_ARGUMENT", path: "overlay.layers[0].primitives[0].at[0]" });
    const scale = { kind: "sequential", domain: [0, bad], colors: ["#000", "#fff"], unit: "", title: "" };
    assert.deepEqual(refusalOf(one({ kind: "point", at: [0, 0], value: 0 }, scale)),
      { code: "INVALID_ARGUMENT", path: "overlay.layers[0].scale.domain[1]" });
  }
});

function many(count, item) {
  return {
    schema: "apeCAD.section-overlay", version: 1, units: "mm", revision: 0,
    layers: [
      { id: "a", label: "", visible: true, scale: null, primitives: new Array(count - 1).fill(item) },
      { id: "b", label: "", visible: false, scale: null, primitives: [item] },
    ],
  };
}

test("the cap plus one is refused before any primitive is read, never truncated", () => {
  assert.equal(MAX_OVERLAY_PRIMITIVES, 200000);
  assert.deepEqual(refusalOf(many(MAX_OVERLAY_PRIMITIVES + 1, null)), { code: "TOO_LARGE", path: "overlay.layers" });
  const point = { kind: "point", at: [0, 0], style: { fill: "#000" } };
  assert.equal(parseOverlay(many(MAX_OVERLAY_PRIMITIVES, point)).primitiveCount, MAX_OVERLAY_PRIMITIVES);
});

test("integers are read by value and normalised", () => {
  const overlay = parseOverlay({ ...one({ kind: "point", at: [0, 0], style: { fill: "#000" }, ids: [3.0] }), version: 1.0, revision: -0 });
  assert.ok(Object.is(overlay.revision, 0));
  assert.deepEqual(overlay.layers[0].primitives[0].ids, [3]);
  assert.equal(refusalOf({ ...one({ kind: "point", at: [0, 0], style: { fill: "#000" } }), revision: 1.5 }).path, "overlay.revision");
});

// --- painting and the editor --------------------------------------------------------------

function recorder() {
  const log = [];
  const ctx = {
    globalAlpha: 1, fillStyle: "", strokeStyle: "", lineWidth: 1, font: "", lineCap: "", lineJoin: "",
    save() {}, restore() {}, beginPath() {}, closePath() {}, moveTo() {}, lineTo() {}, arc() {},
    setLineDash() {}, fillRect() {}, strokeRect() {},
    fill() { log.push(["fill", ctx.fillStyle, ctx.globalAlpha]); },
    stroke() { log.push(["stroke", ctx.strokeStyle, ctx.globalAlpha]); },
    fillText(text) { log.push(["text", text, ctx.fillStyle, ctx.globalAlpha]); },
  };
  return { ctx, log };
}

const VIEW = { scale: 1, worldToScreen: ([x, y]) => [x, -y] };

test("a stale overlay is dimmed, not hidden; a current one is drawn at its own opacity", () => {
  const overlay = parseOverlay(one({ kind: "circle", center: [0, 0], radius: 5, style: { fill: "#123456", opacity: 0.8 } }));
  const fresh = recorder();
  paintOverlay(fresh.ctx, VIEW, overlay, { stale: false });
  assert.deepEqual(fresh.log, [["fill", "#123456", 0.8]]);
  const stale = recorder();
  paintOverlay(stale.ctx, VIEW, overlay, { stale: true });
  assert.deepEqual(stale.log, [["fill", "#123456", 0.8 * STALE_ALPHA]]);
  assert.ok(STALE_ALPHA > 0 && STALE_ALPHA < 1);
});

test("hidden layers draw nothing; valued polylines are stroked, other kinds filled", () => {
  const scale = { kind: "sequential", domain: [0, 10], colors: ["#000000", "#ffffff"], unit: "", title: "" };
  const value = {
    schema: "apeCAD.section-overlay", version: 1, units: "mm", revision: 0,
    layers: [
      { id: "v", label: "V", visible: true, scale, primitives: [
        { kind: "polyline", points: [[0, 0], [1, 1]], value: 5 },
        { kind: "polygon", ring: [[0, 0], [1, 0], [1, 1]], value: 10 },
      ] },
      { id: "h", label: "H", visible: false, scale: null, primitives: [{ kind: "point", at: [0, 0], style: { fill: "#abcdef" } }] },
    ],
  };
  const { ctx, log } = recorder();
  paintOverlay(ctx, VIEW, parseOverlay(value));
  assert.deepEqual(log, [["stroke", "#808080", 1], ["fill", "#ffffff", 1]]);
});

test("draw order: section, then overlay, then the selection on top", () => {
  const scene = { bars: [{ id: 7, centre_mm: [10, 10], diameter_mm: 16 }] };
  const { ctx, log } = recorder();
  const canvas = { getContext: () => ctx };
  const view = createViewport({ width: 200, height: 200 });
  const drawOverlay = (c) => { c.fillStyle = "#123456"; c.fill(); };
  renderSectionCanvas(canvas, view, { scene, selectedIds: new Set([7]), gridOn: false, drawOverlay });
  const fills = log.filter((e) => e[0] === "fill").map((e) => e[1]);
  assert.deepEqual(fills, [PALETTE.selected, "#123456", PALETTE.selected]);
  const plain = recorder();
  renderSectionCanvas({ getContext: () => plain.ctx }, view, { scene, selectedIds: new Set(), gridOn: false });
  assert.deepEqual(plain.log.filter((e) => e[0] === "fill").map((e) => e[1]), [PALETTE.rebar]);
});

const SQUARE = {
  schema: "apeCAD.document.v1", units: "mm",
  ops: [{ op: "AddSectionOutline", point_ids: [{ xyz: [0, 0, 0] }, { xyz: [400, 0, 0] }, { xyz: [400, 400, 0] }, { xyz: [0, 400, 0] }], material: "concrete" }],
};

function texts(node, out = []) {
  if (node.textContent) out.push(node.textContent);
  for (const child of node.children || []) texts(child, out);
  return out;
}

async function editorWithRecorder() {
  const container = {};
  const editor = create(container, { transport: mockTransport() });
  await editor.loadDraft(SQUARE);
  const root = container.children[0];
  const canvas = root.children[1].children[0];
  const panel = root.children[1].children[1].children[2];
  const rec = recorder();
  canvas.getContext = () => rec.ctx;
  return { editor, panel, rec };
}

test("setOverlay draws at the current revision and dims with a 'stale' badge once it moves", async () => {
  const { editor, panel, rec } = await editorWithRecorder();
  const revision = editor.getOverlayState().revision;
  assert.equal(Number.isInteger(revision), true);
  const result = editor.setOverlay(one({ kind: "polygon", ring: [[0, 0], [400, 0], [400, 400]], style: { fill: "#123456" } }, null, revision));
  assert.equal(result.ok, true);
  assert.equal(result.stale, false);
  assert.ok(rec.log.some((e) => e[0] === "fill" && e[1] === "#123456" && e[2] === 1));
  assert.equal(texts(panel).includes("stale"), false);

  rec.log.length = 0;
  await editor.applyOp({ op: "AddBar", x_mm: 60, y_mm: 60, designation: "Ø16" });
  const state = editor.getOverlayState();
  assert.equal(state.stale, true);
  assert.ok(state.revision > state.overlay_revision);
  assert.ok(rec.log.some((e) => e[0] === "fill" && e[1] === "#123456" && e[2] === STALE_ALPHA), "dimmed, not hidden");
  assert.ok(texts(panel).includes("stale"));
  assert.ok(panel.classList.contains("stale"));

  editor.setOverlay(null);
  assert.equal(editor.getOverlayState().active, false);
  rec.log.length = 0;
  editor.fitView();
  assert.equal(rec.log.some((e) => e[1] === "#123456"), false);
  editor.dispose();
});

test("a refused overlay is reported by code and path and replaces the previous one", async () => {
  const { editor, panel, rec } = await editorWithRecorder();
  editor.setOverlay(one({ kind: "point", at: [0, 0], style: { fill: "#123456" } }));
  const refused = editor.setOverlay(one({ kind: "point", at: [0, 0], style: { fill: "red" } }));
  assert.equal(refused.ok, false);
  assert.deepEqual([refused.error.code, refused.error.path], ["INVALID_ARGUMENT", "overlay.layers[0].primitives[0].style.fill"]);
  assert.equal(editor.getOverlayState().active, false);
  assert.equal(editor.getOverlayState().refusal.path, "overlay.layers[0].primitives[0].style.fill");
  rec.log.length = 0;
  editor.fitView();
  assert.equal(rec.log.some((e) => e[1] === "#123456"), false, "nothing of the old overlay is drawn");
  assert.ok(texts(panel).some((t) => t.startsWith("Overlay refused: overlay.layers[0].primitives[0].style.fill ")));
  const big = editor.setOverlay(many(MAX_OVERLAY_PRIMITIVES + 1, null));
  assert.deepEqual([big.ok, big.error.code, big.error.path], [false, "TOO_LARGE", "overlay.layers"]);
  editor.dispose();
});

test("overlay text reaches the page as textContent and the canvas as fillText, never as markup", async () => {
  const { editor, panel, rec } = await editorWithRecorder();
  const evil = "<img src=x onerror=alert(1)>";
  const overlay = one({ kind: "label", at: [10, 10], text: evil, style: { fill: "--signal" } },
    { kind: "categorical", domain: [evil, "b"], colors: ["#000", "#fff"], unit: evil, title: evil });
  overlay.layers[0].label = evil;
  assert.equal(editor.setOverlay(overlay).ok, true);
  const shown = texts(panel);
  assert.ok(shown.includes(evil), "the layer label, verbatim");
  assert.ok(shown.includes(`${evil} (${evil})`), "the legend title and unit, verbatim");
  assert.ok(rec.log.some((e) => e[0] === "text" && e[1] === evil && e[2] === OVERLAY_TOKENS["--signal"]));
  const source = fs.readFileSync(path.resolve(HERE, "../../src/apeCAD/scratchpad/static/section/overlay.js"), "utf8");
  assert.equal(/innerHTML|outerHTML|insertAdjacentHTML|document\.write/.test(source), false);
  editor.dispose();
});

test("one legend per visible layer with a scale: title, unit and domain ticks", async () => {
  const { editor, panel } = await editorWithRecorder();
  const results = readJson(path.join("valid", "rect_wall_results.json"));
  results.revision = editor.getOverlayState().revision;
  assert.equal(editor.setOverlay(results).ok, true);
  const legends = panel.children.filter((n) => n.className === "apecad-section-legend");
  const visibleScaled = results.layers.filter((l) => l.visible && l.scale);
  assert.deepEqual(legends.map((n) => n.dataset.layer), visibleScaled.map((l) => l.id));
  const stress = legends[0];
  assert.equal(stress.children[0].textContent, "Stress (MPa)");
  assert.match(stress.children[1].style.background, /^linear-gradient\(to right, #2166ac 0%, #f7f7f7 6\.97674%, #b2182b 100%\)$/);
  assert.deepEqual(stress.children[2].children.map((n) => n.textContent), ["-30", "0", "400"]);
  const layers = editor.getOverlayState().layers.map((l) => [l.id, l.visible]);
  assert.deepEqual(layers, results.layers.map((l) => [l.id, l.visible]));
  assert.ok(texts(panel).some((t) => t.endsWith("(hidden)")));
  editor.dispose();
});

test("tokens resolve from the live theme when the page defines them, else the light value", () => {
  const saved = globalThis.getComputedStyle;
  globalThis.getComputedStyle = () => ({ getPropertyValue: (name) => (name === "--accent" ? " #3D8FCE " : name === "--signal" ? "var(--x)" : "") });
  try {
    const tokens = liveTokens({});
    assert.equal(tokens["--accent"], "#3d8fce");
    assert.equal(tokens["--signal"], OVERLAY_TOKENS["--signal"]);
  } finally {
    globalThis.getComputedStyle = saved;
  }
  assert.deepEqual(liveTokens(null), { ...OVERLAY_TOKENS });
});

// --- ADR 0038: the example scales pass the contrast and CVD gates -------------------------

const MODES = ["normal", "protan", "deutan"];
const distance = (a, b, mode) => (mode === "normal" ? oklabDistance(a, b) : oklabDistance(simulateCvdHex(a, mode), simulateCvdHex(b, mode)));

function gateFailures(scaleJson) {
  const { scale } = parseOverlay(one({ kind: "point", at: [0, 0], style: { fill: "#000" } }, scaleJson)).layers[0];
  const colors = scale.colors.map((c) => (c.startsWith("--") ? OVERLAY_TOKENS[c] : c));
  const failures = [];
  const marks = scale.kind === "categorical" ? colors : [colors[0], colors[colors.length - 1]];
  for (const c of marks) {
    const cr = contrastRatio(c, PALETTE.bg);
    if (cr < 2.2) failures.push(`${c} on the canvas: ${cr.toFixed(2)} < 2.2`);
  }
  const pairs = [];
  if (scale.kind === "categorical") colors.forEach((a, i) => colors.slice(i + 1).forEach((b) => pairs.push([a, b])));
  else colors.slice(1).forEach((b, i) => pairs.push([colors[i], b]));
  for (const [a, b] of pairs) {
    for (const mode of MODES) {
      const d = distance(a, b, mode);
      if (d < 0.055) failures.push(`${a} vs ${b} (${mode}): ${d.toFixed(3)} < 0.055`);
    }
  }
  return failures;
}

test("each example scale passes the ADR 0038 contrast and CVD gates", () => {
  assert.deepEqual(Object.keys(OVERLAY_EXAMPLE_SCALES).sort(), ["bar_state", "strain", "stress"]);
  for (const [name, scale] of Object.entries(OVERLAY_EXAMPLE_SCALES)) assert.deepEqual(gateFailures(scale), [], name);
});

test("the gate has teeth: red against green fails it for a deuteranope", () => {
  const redGreen = readJson(path.join("valid", "rect_wall_results.json")).layers.find((l) => l.id === "bars").scale;
  assert.deepEqual(gateFailures(redGreen), ["#1a9850 vs #d73027 (deutan): 0.051 < 0.055"]);
});
