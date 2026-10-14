// Unit tests for the pure parts of the theme module. Run: node --test tests/js
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  CANVASES,
  INK,
  THEMES,
  cssHex,
  parseCssColor,
  readInk,
  resolveTheme,
} from "../../src/apeCAD/scratchpad/static/js/theme.js";

test("parseCssColor reads #rgb, #rrggbb and #rrggbbaa", () => {
  assert.equal(parseCssColor("#2f74ad"), 0x2f74ad);
  assert.equal(parseCssColor(" #fff "), 0xffffff);
  assert.equal(parseCssColor("#c64a1a1f"), 0xc64a1a);
  assert.equal(parseCssColor(""), null);
  assert.equal(parseCssColor("steelblue"), null);
  assert.equal(parseCssColor("#12345"), null);
});

test("cssHex round-trips with parseCssColor", () => {
  assert.equal(cssHex(0x000077), "#000077");
  assert.equal(parseCssColor(cssHex(0x14181d)), 0x14181d);
});

test("resolveTheme honours an explicit choice, else the system", () => {
  assert.equal(resolveTheme("light", true), "light");
  assert.equal(resolveTheme("dark", false), "dark");
  assert.equal(resolveTheme("system", true), "dark");
  assert.equal(resolveTheme("system", false), "light");
  assert.equal(resolveTheme(undefined, false), "light");
  assert.deepEqual(THEMES, ["system", "light", "dark"]);
  assert.deepEqual(CANVASES, ["theme", "paper", "mist", "carbon"]);
});

test("readInk fills INK from the canvas roles and keeps a value it cannot read", () => {
  const vars = {
    "--canvas": "#f7f6f3",
    "--grid-major": "#d8d5cd",
    "--grid-minor": "#e7e4dd",
    "--ink-edge": "#14181d",
    "--pick": "#2f74ad",
    "--hover": "#3d8fce",
    "--snap": "#c64a1a",
    "--ghost": "",
    "--light-sky": "#f4f7fb",
    "--light-ground": "#6e757c",
    "--light-ground-flat": "#c5cad0",
    "--contact-opacity": " 0.18",
  };
  INK.ghost = 0x123456;
  readInk({ getPropertyValue: (name) => vars[name] ?? "" });
  assert.equal(INK.canvas, 0xf7f6f3);
  assert.equal(INK.pick, 0x2f74ad);
  assert.equal(INK.snap, 0xc64a1a);
  assert.equal(INK.ghost, 0x123456);
  assert.equal(INK.contactOpacity, 0.18);
});
