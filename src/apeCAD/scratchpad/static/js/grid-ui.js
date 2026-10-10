// Grid menu and Grid -> Preferences dialog: the setters behind them and their form sync.
import { S } from "./state.js";
import { refreshToggles, setHint } from "./cmdline.js";
import { grid, gridMajorMm, gridMinorMm, rebuildGrid } from "./grid.js";
import {
  GRID_MAX_MM,
  GRID_MIN_MM,
  clampDotSize,
  clampHiddenScale,
  clampLineWidth,
  displayUnit,
  formatGridInput,
  formatLength,
  gridAutoOn,
  gridDotSize,
  gridLineWidth,
  gridMinorStyle,
  hiddenLineScale,
  mmToUnit,
  savePrefs,
} from "./prefs.js";
import { UNIT_STEP } from "./units.js";

export function setGridAuto(next) {
  S.prefs.gridAuto = Boolean(next);
  savePrefs();
  rebuildGrid();
  refreshToggles();
  setHint(S.prefs.gridAuto
    ? `Grid auto ${formatLength(gridMinorMm())} / ${formatLength(gridMajorMm())}.`
    : "Grid spacing is manual.");
}

export function setGridMinorOn(next) {
  S.gridMinorOn = next;
  S.prefs.gridMinorOn = next;
  savePrefs();
  rebuildGrid();
  refreshToggles();
  setHint(S.gridMinorOn ? "Minor grid on." : "Minor grid off.");
}

export function setGridHiddenScale(next, opts = {}) {
  S.prefs.gridHiddenScale = clampHiddenScale(next);
  savePrefs();
  rebuildGrid();
  syncGridPrefsForm();
  if (!opts.silent) setHint(`Hidden line scale ${hiddenLineScale()}.`);
}

export function setGridMinorStyle(next) {
  S.prefs.gridMinorStyle = next === "lines" ? "lines" : "dots";
  savePrefs();
  rebuildGrid();
  syncGridPrefsForm();
  setHint(S.prefs.gridMinorStyle === "dots" ? "Minor grid: dots." : "Minor grid: lines.");
}

export function setGridDotSize(next, opts = {}) {
  S.prefs.gridDotSize = clampDotSize(next);
  savePrefs();
  const size = gridDotSize();
  let updated = false;
  if (grid) {
    grid.traverse((node) => {
      if (node.isPoints && node.material) {
        node.material.size = size;
        updated = true;
      }
    });
  }
  if (!updated && gridMinorStyle() === "dots") rebuildGrid();
  syncGridPrefsForm();
  if (!opts.silent) setHint(`Dot size ${size} px.`);
}

export function setGridLineWidth(next, opts = {}) {
  S.prefs.gridLineWidth = clampLineWidth(next);
  savePrefs();
  const width = gridLineWidth();
  let updated = false;
  if (grid) {
    grid.traverse((node) => {
      if (node.material && node.material.linewidth != null) {
        node.material.linewidth = width;
        updated = true;
      }
    });
  }
  if (!updated) rebuildGrid();
  syncGridPrefsForm();
  if (!opts.silent) setHint(`Line thickness ${width} px.`);
}

export function syncGridMenu() {
  const minorOnEl = document.getElementById("grid-minor-on");
  if (minorOnEl) minorOnEl.checked = S.gridMinorOn;
}

export function syncGridPrefsForm() {
  const showEl = document.getElementById("gpref-show");
  if (!showEl) return;
  showEl.checked = S.gridOn;
  document.getElementById("gpref-minor-on").checked = S.gridMinorOn;
  document.getElementById("gpref-snap").checked = S.gridSnapOn;
  const autoEl = document.getElementById("gpref-auto");
  if (autoEl) autoEl.checked = gridAutoOn();
  const styleEl = document.getElementById("gpref-minor-style");
  if (styleEl && document.activeElement !== styleEl) styleEl.value = gridMinorStyle();
  const unitEl = document.getElementById("gpref-unit");
  if (unitEl && document.activeElement !== unitEl) unitEl.value = displayUnit();
  const dots = gridMinorStyle() === "dots";
  const dotOpts = document.getElementById("gpref-dot-opts");
  const lineOpts = document.getElementById("gpref-line-opts");
  if (dotOpts) dotOpts.hidden = !dots;
  if (lineOpts) lineOpts.hidden = dots;
  const unit = displayUnit();
  const step = UNIT_STEP[unit];
  const min = mmToUnit(GRID_MIN_MM);
  const max = mmToUnit(GRID_MAX_MM);
  const minorEl = document.getElementById("gpref-minor");
  const majorEl = document.getElementById("gpref-major");
  for (const el of [minorEl, majorEl]) {
    el.min = String(min);
    el.max = String(max);
    el.step = String(step);
    el.disabled = gridAutoOn();
  }
  if (document.activeElement !== minorEl) minorEl.value = formatGridInput(gridMinorMm());
  if (document.activeElement !== majorEl) majorEl.value = formatGridInput(gridMajorMm());
  const scaleEl = document.getElementById("gpref-hidden-scale");
  const scaleNum = document.getElementById("gpref-hidden-scale-num");
  const scale = hiddenLineScale();
  if (document.activeElement !== scaleEl) scaleEl.value = String(scale);
  if (document.activeElement !== scaleNum) scaleNum.value = String(scale);
  const dotEl = document.getElementById("gpref-dot-size");
  const dotNum = document.getElementById("gpref-dot-size-num");
  const size = gridDotSize();
  if (dotEl && document.activeElement !== dotEl) dotEl.value = String(size);
  if (dotNum && document.activeElement !== dotNum) dotNum.value = String(size);
  const widthEl = document.getElementById("gpref-line-width");
  const widthNum = document.getElementById("gpref-line-width-num");
  const width = gridLineWidth();
  if (widthEl && document.activeElement !== widthEl) widthEl.value = String(width);
  if (widthNum && document.activeElement !== widthNum) widthNum.value = String(width);
  for (const button of document.querySelectorAll("[data-grid-minor]")) {
    button.textContent = `${formatGridInput(Number(button.dataset.gridMinor))} / ${formatGridInput(Number(button.dataset.gridMajor))}`;
  }
  const placeholder = document.getElementById("console-input");
  if (placeholder) placeholder.placeholder = `length ${unit} · angle ° · Enter`;
}

export function setGridOn(next) {
  S.gridOn = next;
  S.prefs.grid = next;
  savePrefs();
  refreshToggles();
  grid.visible = S.gridOn;
}

export function setGridSnapOn(next) {
  S.gridSnapOn = next;
  S.prefs.gridSnap = next;
  savePrefs();
  refreshToggles();
}
