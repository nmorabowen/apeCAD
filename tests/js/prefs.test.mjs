// Unit tests for the pure units module and the prefs clamps/merge. Run: node --test tests/js
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  clampDotSize,
  clampGridSpacing,
  clampHiddenScale,
  clampLineWidth,
  displayUnit,
  formatLength,
  mergePrefs,
  niceLength,
  parseLength,
} from "../../src/apeCAD/scratchpad/static/js/prefs.js";
import { S } from "../../src/apeCAD/scratchpad/static/js/state.js";
import {
  formatDeg,
  formatIn,
  fromUnit,
  parseLengthIn,
  toUnit,
} from "../../src/apeCAD/scratchpad/static/js/units.js";

test("unit conversion round-trips through millimetres", () => {
  assert.equal(toUnit(2500, "m"), 2.5);
  assert.equal(fromUnit("2.5", "m"), 2500);
  assert.equal(fromUnit(1, "in"), 25.4);
  assert.ok(Number.isNaN(fromUnit("x", "mm")));
});

test("formatIn rounds to the unit's decimals", () => {
  assert.equal(formatIn(1234.567, "mm"), "1235");
  assert.equal(formatIn(1234.567, "cm"), "123.5");
  assert.equal(formatIn(1234.567, "m"), "1.235");
  assert.equal(formatIn(25.4, "in"), "1");
});

test("parseLengthIn reads bare numbers in the unit and explicit suffixes", () => {
  assert.equal(parseLengthIn("250", "mm"), 250);
  assert.equal(parseLengthIn("250", "cm"), 2500);
  assert.equal(parseLengthIn("2.5 m", "mm"), 2500);
  assert.equal(parseLengthIn('10"', "mm"), 254);
  assert.equal(parseLengthIn("0", "mm"), null);
  assert.equal(parseLengthIn("-5", "mm"), null);
  assert.equal(parseLengthIn("abc", "mm"), null);
});

test("formatDeg wraps negative angles", () => {
  assert.equal(formatDeg(Math.PI / 2), "90°");
  assert.equal(formatDeg(-Math.PI / 2), "270°");
});

test("grid clamps fall back on bad input and bound good input", () => {
  assert.equal(clampGridSpacing("abc"), 100);
  assert.equal(clampGridSpacing(0.2), 1);
  assert.equal(clampGridSpacing(1e9), 10000);
  assert.equal(clampHiddenScale(10), 4);
  assert.equal(clampHiddenScale(0.333), 0.33);
  assert.equal(clampDotSize(2.3), 2.5);
  assert.equal(clampLineWidth(-1), 1);
});

test("niceLength picks a 1-2-5 step", () => {
  assert.equal(niceLength(130), 100);
  assert.equal(niceLength(300), 200);
  assert.equal(niceLength(4000), 5000);
  assert.equal(niceLength(8000), 10000);
});

test("mergePrefs migrates the v1 gridSpacing and keeps major >= minor", () => {
  const migrated = mergePrefs({ gridSpacing: 250 });
  assert.equal(migrated.gridMinor, 250);
  assert.equal(migrated.gridMajor, 2500);
  assert.equal(mergePrefs({ gridMinor: 500, gridMajor: 100 }).gridMajor, 500);
  assert.equal(mergePrefs(null).theme, "system");
  assert.equal(mergePrefs(null).canvas, "theme");
});

test("mergePrefs maps the v2 background presets onto ADR 0031 canvases", () => {
  assert.equal(mergePrefs({ background: "g2" }).canvas, "carbon");
  assert.equal(mergePrefs({ background: "g5" }).canvas, "theme");
  assert.equal(mergePrefs({ background: "g6" }).canvas, "mist");
  assert.equal(mergePrefs({ background: "g6", canvas: "paper" }).canvas, "paper");
  assert.equal("background" in mergePrefs({ background: "g2" }), false);
  assert.equal(mergePrefs({ theme: "sepia", canvas: "neon" }).theme, "system");
  assert.equal(mergePrefs({ theme: "sepia", canvas: "neon" }).canvas, "theme");
  assert.equal(mergePrefs({ curve: "#111111" }).curve, "");
  assert.equal(mergePrefs({ curve: "#336699" }).curve, "#336699");
});

test("display-unit wrappers follow S.prefs", () => {
  S.prefs = mergePrefs({ displayUnit: "cm" });
  assert.equal(displayUnit(), "cm");
  assert.equal(parseLength("25"), 250);
  assert.equal(formatLength(1234), "123.4 cm");
  S.prefs = mergePrefs({ displayUnit: "furlong" });
  assert.equal(displayUnit(), "mm");
});
