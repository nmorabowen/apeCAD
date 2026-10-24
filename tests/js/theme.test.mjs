// Unit tests for the pure parts of the theme module and WCAG / CVD token gates (ADR 0038).
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import {
  CANVASES,
  INK,
  THEMES,
  contrastRatio,
  cssHex,
  oklabDistance,
  parseCssColor,
  readInk,
  relativeLuminance,
  resolveTheme,
  simulateCvdHex,
} from "../../src/apeCAD/scratchpad/static/js/theme.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const APP_CSS_PATH = path.resolve(
  __dirname,
  "../../src/apeCAD/scratchpad/static/css/app.css",
);

function parseCssBlocks(cssText) {
  const blocks = {};
  const blockRe = /([^{]+)\{([^}]+)\}/g;
  let m;
  while ((m = blockRe.exec(cssText)) !== null) {
    const selector = m[1].replace(/\/\*[\s\S]*?\*\//g, "").trim();
    const body = m[2];
    const vars = {};
    const varRe = /(--[a-z0-9-]+)\s*:\s*([^;]+);/gi;
    let vm;
    while ((vm = varRe.exec(body)) !== null) {
      vars[vm[1].trim()] = vm[2].trim();
    }
    if (Object.keys(vars).length > 0) {
      blocks[selector] = { ...(blocks[selector] || {}), ...vars };
    }
  }
  return blocks;
}

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

test("WCAG 2.1 contrast and Viénot protanopia/deuteranopia OKLab gates hold across app.css", () => {
  assert.ok(Math.abs(relativeLuminance(0x000000)) < 1e-9);
  assert.ok(Math.abs(relativeLuminance(0xffffff) - 1) < 1e-9);
  assert.ok(Math.abs(contrastRatio(0x000000, 0xffffff) - 21) < 1e-6);

  const css = fs.readFileSync(APP_CSS_PATH, "utf8");
  const blocks = parseCssBlocks(css);
  const rootLight = blocks[":root"] || {};
  const rootDark = { ...rootLight, ...(blocks[':root[data-theme="dark"]'] || {}) };

  // 1. UI chrome text contrast >= 4.5:1 on all three surfaces in light and dark themes.
  for (const [themeName, themeVars] of [["light", rootLight], ["dark", rootDark]]) {
    for (const surf of ["--surface-0", "--surface-1", "--surface-2"]) {
      for (const ink of ["--text", "--accent-text", "--signal-text"]) {
        const cr = contrastRatio(themeVars[ink], themeVars[surf]);
        assert.ok(
          cr >= 4.5,
          `${themeName} ${ink} on ${surf} contrast ${cr.toFixed(2)} < 4.5`,
        );
      }
    }
  }

  // 2. Canvas stroke contrast >= 2.2:1 and CVD OKLab distance >= 0.055 across all canvas presets.
  const canvasEntries = Object.entries(blocks).filter(
    ([sel, vars]) => vars["--canvas"] && (sel === ":root" || sel.includes("data-canvas") || sel.includes("data-theme")),
  );
  assert.ok(canvasEntries.length >= 4);
  for (const [sel, rawVars] of canvasEntries) {
    const vars = { ...rootLight, ...rawVars };
    const bg = vars["--canvas"];
    for (const stroke of [
      "--ink-edge",
      "--pick",
      "--snap",
      "--ink-concrete",
      "--ink-section-guide",
      "--ink-rebar",
    ]) {
      const cr = contrastRatio(vars[stroke], bg);
      assert.ok(cr >= 2.2, `${sel} ${stroke} on --canvas contrast ${cr.toFixed(2)} < 2.2`);
    }
    for (const mode of ["protan", "deutan"]) {
      const dPickSnap = oklabDistance(
        simulateCvdHex(vars["--pick"], mode),
        simulateCvdHex(vars["--snap"], mode),
      );
      assert.ok(
        dPickSnap >= 0.055,
        `${sel} (${mode}) --pick vs --snap OKLab distance ${dPickSnap.toFixed(3)} < 0.055`,
      );
      const dPickEdge = oklabDistance(
        simulateCvdHex(vars["--pick"], mode),
        simulateCvdHex(vars["--ink-edge"], mode),
      );
      assert.ok(
        dPickEdge >= 0.055,
        `${sel} (${mode}) --pick vs --ink-edge OKLab distance ${dPickEdge.toFixed(3)} < 0.055`,
      );
    }
  }
});

