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
