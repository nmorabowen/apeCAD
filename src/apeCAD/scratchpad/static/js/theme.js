// Theme and canvas colours (ADR 0031 §1; values in css/app.css, roles in
// AProjects/specs/ape-design.md §1.1). css/app.css is the only place a colour is written;
// this module sets data-theme / data-canvas and reads the canvas roles into INK for
// three.js. Top-level code touches no DOM, so the pure helpers run under node --test.

export const THEMES = ["system", "light", "dark"];
export const CANVASES = ["theme", "paper", "mist", "carbon"];

// The canvas roles three.js reads, refreshed by applyTheme(); numbers like 0xrrggbb.
export const INK = {
  canvas: 0,
  gridMajor: 0,
  gridMinor: 0,
  edge: 0,
  pick: 0,
  hover: 0,
  snap: 0,
  ghost: 0,
  concreteFill: 0,
  concreteEdge: 0,
  sectionGuide: 0,
  rebar: 0,
  lightSky: 0,
  lightGround: 0,
  lightGroundFlat: 0,
  contactOpacity: 0.06,
};

const ROLE_VARS = {
  canvas: "--canvas",
  gridMajor: "--grid-major",
  gridMinor: "--grid-minor",
  edge: "--ink-edge",
  pick: "--pick",
  hover: "--hover",
  snap: "--snap",
  ghost: "--ghost",
  concreteFill: "--fill-concrete",
  concreteEdge: "--ink-concrete",
  sectionGuide: "--ink-section-guide",
  rebar: "--ink-rebar",
  lightSky: "--light-sky",
  lightGround: "--light-ground",
  lightGroundFlat: "--light-ground-flat",
};

// "#rgb", "#rrggbb" or "#rrggbbaa" (alpha dropped) → 0xrrggbb; null when unreadable.
export function parseCssColor(value) {
  const raw = String(value || "").trim().replace(/^#/, "");
  if (!/^[0-9a-fA-F]+$/.test(raw)) return null;
  if (raw.length === 3) return Number.parseInt(raw.split("").map((ch) => ch + ch).join(""), 16);
  if (raw.length === 6 || raw.length === 8) return Number.parseInt(raw.slice(0, 6), 16);
  return null;
}

export function cssHex(value) {
  return `#${(value >>> 0).toString(16).padStart(6, "0").slice(-6)}`;
}

export function resolveTheme(pref, systemDark) {
  if (pref === "light" || pref === "dark") return pref;
  return systemDark ? "dark" : "light";
}

// Read the computed canvas roles of `element` into INK.
export function readInk(style) {
  for (const [key, name] of Object.entries(ROLE_VARS)) {
    const parsed = parseCssColor(style.getPropertyValue(name));
    if (parsed !== null) INK[key] = parsed;
  }
  const opacity = Number.parseFloat(style.getPropertyValue("--contact-opacity"));
  if (Number.isFinite(opacity)) INK.contactOpacity = opacity;
  return INK;
}

// Chrome colours for 2-D canvases (the view cube faces), read from the document root.
export function chromeColors() {
  const style = getComputedStyle(document.documentElement);
  const pick = (name) => style.getPropertyValue(name).trim();
  return {
    surface: pick("--surface-1"),
    line: pick("--line"),
    text: pick("--text"),
    font: pick("--font-ui"),
  };
}

function systemDark() {
  return Boolean(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
}

// Set the theme and canvas attributes from the prefs, then refresh INK. Returns the
// resolved theme name ("light" or "dark").
export function applyTheme(prefs) {
  const theme = resolveTheme(prefs.theme, systemDark());
  document.documentElement.dataset.theme = theme;
  const stage = document.getElementById("stage");
  if (prefs.canvas && prefs.canvas !== "theme") stage.dataset.canvas = prefs.canvas;
  else delete stage.dataset.canvas;
  readInk(getComputedStyle(stage));
  return theme;
}

// Call `onChange` when the system theme flips and the Theme preference is "system".
export function watchSystemTheme(prefsOf, onChange) {
  if (!window.matchMedia) return;
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if ((prefsOf().theme || "system") === "system") onChange();
  });
}

function toHexInt(c) {
  return typeof c === "number" ? c >>> 0 : (parseCssColor(c) ?? 0);
}

function srgbToLinear(u8) {
  const c = (u8 & 255) / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function linearToSrgbU8(lin) {
  const c = Math.max(0, Math.min(1, lin));
  const s = c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055;
  return Math.round(s * 255);
}

// WCAG 2.1 relative luminance in [0, 1] from a 0xrrggbb number or "#rrggbb" string (ADR 0038).
export function relativeLuminance(color) {
  const hex = toHexInt(color);
  const r = srgbToLinear((hex >> 16) & 255);
  const g = srgbToLinear((hex >> 8) & 255);
  const b = srgbToLinear(hex & 255);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrastRatio(colorA, colorB) {
  const l1 = relativeLuminance(colorA);
  const l2 = relativeLuminance(colorB);
  const hi = Math.max(l1, l2);
  const lo = Math.min(l1, l2);
  return (hi + 0.05) / (lo + 0.05);
}

// Viénot, Brettel & Mollon (1999) linear-sRGB simulation matrices for protanopia and deuteranopia.
const CVD_MATRICES = {
  protan: [
    [0.152286, 1.052583, -0.204868],
    [0.114503, 0.786281, 0.099216],
    [-0.003882, -0.048116, 1.051998],
  ],
  deutan: [
    [0.367322, 0.860646, -0.227968],
    [0.280085, 0.672501, 0.047413],
    [-0.01182, 0.04294, 0.968881],
  ],
};

export function simulateCvdHex(color, mode = "deutan") {
  const hex = toHexInt(color);
  const r = srgbToLinear((hex >> 16) & 255);
  const g = srgbToLinear((hex >> 8) & 255);
  const b = srgbToLinear(hex & 255);
  const m = CVD_MATRICES[mode] || CVD_MATRICES.deutan;
  const nr = linearToSrgbU8(m[0][0] * r + m[0][1] * g + m[0][2] * b);
  const ng = linearToSrgbU8(m[1][0] * r + m[1][1] * g + m[1][2] * b);
  const nb = linearToSrgbU8(m[2][0] * r + m[2][1] * g + m[2][2] * b);
  return (nr << 16) | (ng << 8) | nb;
}

function toOklab(color) {
  const hex = toHexInt(color);
  const r = srgbToLinear((hex >> 16) & 255);
  const g = srgbToLinear((hex >> 8) & 255);
  const b = srgbToLinear(hex & 255);
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
}

// Perceptual Euclidean distance in OKLab space (ADR 0038).
export function oklabDistance(colorA, colorB) {
  const a = toOklab(colorA);
  const b = toOklab(colorB);
  return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}
