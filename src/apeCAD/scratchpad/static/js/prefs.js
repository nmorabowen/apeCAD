// Visualization and grid preferences: defaults, clamps, localStorage, and display-unit
// formatting. Client state only, never in the document (ADR 0013, ADR 0014).
import { S } from "./state.js";
import { UNIT_MM, formatIn, fromUnit, parseLengthIn, toUnit } from "./units.js";

export const GRID_DEFAULT_MINOR_MM = 100;
export const GRID_DEFAULT_MAJOR_MM = 1000;
export const GRID_EXTENT_MM = 40000;
export const GRID_MAX_DIVISIONS = 800;
export const GRID_MIN_MM = 1;
export const GRID_MAX_MM = 10000;
const GRID_HIDDEN_SCALE_DEFAULT = 0.25;
const GRID_HIDDEN_SCALE_MIN = 0.25;
const GRID_HIDDEN_SCALE_MAX = 4;
const GRID_MINOR_STYLE_DEFAULT = "dots";
const GRID_DOT_SIZE_DEFAULT = 1.5;
const GRID_DOT_SIZE_MIN = 0.5;
const GRID_DOT_SIZE_MAX = 8;
const GRID_LINE_WIDTH_DEFAULT = 1;
const GRID_LINE_WIDTH_MIN = 0.5;
const GRID_LINE_WIDTH_MAX = 8;
const PREFS_KEY = "apeCAD.prefs.v2";
export const LAYOUT_KEY = "apeCAD.layout.v2";

const PREF_DEFAULTS = {
  background: "g5",
  clay: 176,
  curve: "#111111",
  keyLight: true,
  ao: true,
  showEdges: true,
  showCurves: true,
  showFaces: true,
  grid: true,
  gridSnap: true,
  gridMinorOn: true,
  gridMinor: GRID_DEFAULT_MINOR_MM,
  gridMajor: GRID_DEFAULT_MAJOR_MM,
  gridAuto: true,
  gridHiddenScale: GRID_HIDDEN_SCALE_DEFAULT,
  gridMinorStyle: GRID_MINOR_STYLE_DEFAULT,
  gridDotSize: GRID_DOT_SIZE_DEFAULT,
  gridLineWidth: GRID_LINE_WIDTH_DEFAULT,
  displayUnit: "mm",
};

export const BACKGROUNDS = {
  g2: { bg: 0x1c1c1c, major: 0x3c3c3c, minor: 0x2a2a2a },
  g5: { bg: 0xe4e9ee, major: 0xc0c0c0, minor: 0xd2d2d2 },
  g6: { bg: 0xa3a6aa, major: 0x8a8e92, minor: 0x96999d },
};

export function clampGridSpacing(value, fallback = GRID_DEFAULT_MINOR_MM) {
  const raw = Number(value);
  if (!Number.isFinite(raw) || raw <= 0) return fallback;
  return Math.min(Math.max(raw, GRID_MIN_MM), GRID_MAX_MM);
}

// Merge stored prefs over the defaults, migrating the v1 single `gridSpacing` field.
export function mergePrefs(raw) {
  const stored = raw && typeof raw === "object" ? raw : null;
  const merged = { ...PREF_DEFAULTS, ...(stored || {}) };
  if (stored && stored.gridMinor == null && stored.gridSpacing != null) {
    merged.gridMinor = clampGridSpacing(stored.gridSpacing);
  }
  if (stored && stored.gridMajor == null) {
    merged.gridMajor = clampGridSpacing(merged.gridMinor * 10, GRID_DEFAULT_MAJOR_MM);
  }
  if (merged.gridMajor < merged.gridMinor) merged.gridMajor = merged.gridMinor;
  return merged;
}

function loadPrefs() {
  try {
    return mergePrefs(JSON.parse(localStorage.getItem(PREFS_KEY) || "null"));
  } catch (_error) {
    return { ...PREF_DEFAULTS };
  }
}

export function initPrefs() {
  S.prefs = loadPrefs();
  if (S.prefs.grid === false) S.gridOn = false;
  if (S.prefs.gridSnap === false) S.gridSnapOn = false;
  if (S.prefs.gridMinorOn === false) S.gridMinorOn = false;
  S.prefs.gridHiddenScale = clampHiddenScale(S.prefs.gridHiddenScale);
  S.prefs.gridMinorStyle = gridMinorStyle();
  S.prefs.gridDotSize = clampDotSize(S.prefs.gridDotSize);
  S.prefs.gridLineWidth = clampLineWidth(S.prefs.gridLineWidth);
  S.prefs.displayUnit = displayUnit();
}

export function clampHiddenScale(value) {
  const raw = Number(value);
  if (!Number.isFinite(raw) || raw <= 0) return GRID_HIDDEN_SCALE_DEFAULT;
  const clamped = Math.min(Math.max(raw, GRID_HIDDEN_SCALE_MIN), GRID_HIDDEN_SCALE_MAX);
  return Math.round(clamped * 100) / 100;
}

export function hiddenLineScale() {
  return clampHiddenScale(S.prefs.gridHiddenScale);
}

export function clampDotSize(value) {
  const raw = Number(value);
  if (!Number.isFinite(raw) || raw <= 0) return GRID_DOT_SIZE_DEFAULT;
  const clamped = Math.min(Math.max(raw, GRID_DOT_SIZE_MIN), GRID_DOT_SIZE_MAX);
  return Math.round(clamped * 2) / 2;
}

export function gridDotSize() {
  return clampDotSize(S.prefs.gridDotSize);
}

export function clampLineWidth(value) {
  const raw = Number(value);
  if (!Number.isFinite(raw) || raw <= 0) return GRID_LINE_WIDTH_DEFAULT;
  const clamped = Math.min(Math.max(raw, GRID_LINE_WIDTH_MIN), GRID_LINE_WIDTH_MAX);
  return Math.round(clamped * 2) / 2;
}

export function gridLineWidth() {
  return clampLineWidth(S.prefs.gridLineWidth);
}

export function gridMinorStyle() {
  return S.prefs.gridMinorStyle === "lines" ? "lines" : "dots";
}

export function displayUnit() {
  return UNIT_MM[S.prefs.displayUnit] ? S.prefs.displayUnit : "mm";
}

export function mmToUnit(mm, unit = displayUnit()) {
  return toUnit(mm, unit);
}

export function fromDisplay(value, unit = displayUnit()) {
  return fromUnit(value, unit);
}

export function formatGridInput(mm) {
  return formatIn(mm, displayUnit());
}

export function formatNumber(mm) {
  return formatGridInput(mm);
}

export function prefMinorMm() {
  return clampGridSpacing(S.prefs.gridMinor, GRID_DEFAULT_MINOR_MM);
}

export function prefMajorMm() {
  const minor = prefMinorMm();
  return Math.max(clampGridSpacing(S.prefs.gridMajor, GRID_DEFAULT_MAJOR_MM), minor);
}

export function gridAutoOn() {
  return S.prefs.gridAuto !== false;
}

export function niceLength(mm) {
  if (!Number.isFinite(mm) || mm <= 0) return GRID_DEFAULT_MINOR_MM;
  const exp = Math.floor(Math.log10(mm));
  const base = 10 ** exp;
  const n = mm / base;
  const nice = n <= 1.5 ? 1 : n <= 3.5 ? 2 : n <= 7.5 ? 5 : 10;
  return clampGridSpacing(nice * base);
}

export function parseLength(text) {
  return parseLengthIn(text, displayUnit());
}

export function formatLength(mm) {
  if (!Number.isFinite(mm)) return "—";
  return `${formatNumber(mm)} ${displayUnit()}`;
}

export function formatMm(value) {
  return formatLength(value);
}

export function savePrefs() {
  localStorage.setItem(PREFS_KEY, JSON.stringify(S.prefs));
}
