// Grid menu and Grid -> Preferences dialog: the setters behind them and their form sync.
import { S } from "./state.js";
import { requestRender } from "./store.js";
import { t } from "./strings.js";
import { refreshToggles, setHint, syncGridMenu, syncGridPrefsForm } from "./cmdline.js";
import { updateGhost } from "./ghosts.js";
import { grid, gridMajorMm, gridMinorMm, rebuildGrid } from "./grid.js";
import {
  GRID_DEFAULT_MAJOR_MM,
  GRID_DEFAULT_MINOR_MM,
  clampDotSize,
  clampGridSpacing,
  clampHiddenScale,
  clampLineWidth,
  displayUnit,
  formatLength,
  fromDisplay,
  gridDotSize,
  gridLineWidth,
  gridMinorStyle,
  hiddenLineScale,
  savePrefs,
} from "./prefs.js";
import { UNIT_MM } from "./units.js";

export { syncGridMenu, syncGridPrefsForm };

export function setGridAuto(next) {
  S.prefs.gridAuto = Boolean(next);
  savePrefs();
  rebuildGrid();
  refreshToggles();
  setHint(S.prefs.gridAuto
    ? t("grid.auto", { minor: formatLength(gridMinorMm()), major: formatLength(gridMajorMm()) })
    : t("grid.manual"));
}

function setGridMinorOn(next) {
  S.gridMinorOn = next;
  S.prefs.gridMinorOn = next;
  savePrefs();
  rebuildGrid();
  refreshToggles();
  setHint(t(S.gridMinorOn ? "grid.minorOn" : "grid.minorOff"));
}

export function setGridHiddenScale(next, opts = {}) {
  S.prefs.gridHiddenScale = clampHiddenScale(next);
  savePrefs();
  rebuildGrid();
  syncGridPrefsForm();
  requestRender();
  if (!opts.silent) setHint(t("grid.dashScale", { s: hiddenLineScale() }));
}

export function setGridMinorStyle(next) {
  S.prefs.gridMinorStyle = next === "lines" ? "lines" : "dots";
  savePrefs();
  rebuildGrid();
  syncGridPrefsForm();
  requestRender();
  setHint(t(S.prefs.gridMinorStyle === "dots" ? "grid.dots" : "grid.lines"));
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
  requestRender();
  if (!opts.silent) setHint(t("grid.dotSize", { n: size }));
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
  requestRender();
  if (!opts.silent) setHint(t("grid.lineWidth", { n: width }));
}

export function setGridOn(next) {
  S.gridOn = next;
  S.prefs.grid = next;
  savePrefs();
  refreshToggles();
  if (grid) grid.visible = S.gridOn;
  requestRender();
}

export function setGridSnapOn(next) {
  S.gridSnapOn = next;
  S.prefs.gridSnap = next;
  savePrefs();
  refreshToggles();
}

export function setGridSpacing(minor, major) {
  S.prefs.gridAuto = false;
  S.prefs.gridMinor = clampGridSpacing(minor, GRID_DEFAULT_MINOR_MM);
  if (major != null) S.prefs.gridMajor = clampGridSpacing(major, GRID_DEFAULT_MAJOR_MM);
  if (S.prefs.gridMajor < S.prefs.gridMinor) S.prefs.gridMajor = S.prefs.gridMinor;
  savePrefs();
  rebuildGrid();
  refreshToggles();
  if (S.lastPointer) updateGhost(S.lastPointer);
  setHint(t("grid.spacing", { minor: formatLength(gridMinorMm()), major: formatLength(gridMajorMm()) }));
}

export function setDisplayUnit(next) {
  S.prefs.displayUnit = UNIT_MM[next] ? next : "mm";
  savePrefs();
  refreshToggles();
  if (S.lastPointer) updateGhost(S.lastPointer);
  setHint(t("grid.units", { unit: displayUnit() }));
}

function readGridSpacingForm() {
  setGridSpacing(
    fromDisplay(document.getElementById("gpref-minor").value),
    fromDisplay(document.getElementById("gpref-major").value),
  );
}

// Each slider has a number box twin: typing previews silently, committing reports a hint.
function bindSliderPair(rangeId, numId, set) {
  for (const el of [document.getElementById(rangeId), document.getElementById(numId)]) {
    el.addEventListener("input", () => set(el.value, { silent: true }));
    el.addEventListener("change", () => set(el.value));
  }
}

export function bindGridPrefs() {
  document.getElementById("grid-menu").addEventListener("click", (event) => event.stopPropagation());
  document.getElementById("grid-minor-on").addEventListener("change", (event) => {
    setGridMinorOn(event.target.checked);
  });
  document.getElementById("gpref-show").addEventListener("change", (event) => {
    setGridOn(event.target.checked);
  });
  document.getElementById("gpref-minor-on").addEventListener("change", (event) => {
    setGridMinorOn(event.target.checked);
  });
  document.getElementById("gpref-snap").addEventListener("change", (event) => {
    setGridSnapOn(event.target.checked);
  });
  document.getElementById("gpref-auto").addEventListener("change", (event) => {
    setGridAuto(event.target.checked);
  });
  document.getElementById("gpref-minor-style").addEventListener("change", (event) => {
    setGridMinorStyle(event.target.value);
  });
  document.getElementById("gpref-minor").addEventListener("change", readGridSpacingForm);
  document.getElementById("gpref-major").addEventListener("change", readGridSpacingForm);
  document.getElementById("gpref-unit").addEventListener("change", (event) => {
    setDisplayUnit(event.target.value);
  });
  bindSliderPair("gpref-hidden-scale", "gpref-hidden-scale-num", setGridHiddenScale);
  bindSliderPair("gpref-dot-size", "gpref-dot-size-num", setGridDotSize);
  bindSliderPair("gpref-line-width", "gpref-line-width-num", setGridLineWidth);
  for (const button of document.querySelectorAll("[data-grid-minor]")) {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      setGridSpacing(button.dataset.gridMinor, button.dataset.gridMajor);
    });
  }
}
