// The Preferences dialog: theme, canvas, clay, curve colour, lights and visibility toggles.
import { S } from "./state.js";
import { refreshToggles } from "./cmdline.js";
import { updateGhost } from "./ghosts.js";
import { rebuildGrid } from "./grid.js";
import {
  displayUnit,
  gridAutoOn,
  gridDotSize,
  gridLineWidth,
  gridMinorStyle,
  hiddenLineScale,
  prefMajorMm,
  prefMinorMm,
  savePrefs,
} from "./prefs.js";
import { rebuild } from "./render.js";
import { INK, applyTheme, cssHex, watchSystemTheme } from "./theme.js";
import { restyleCube } from "./viewcube.js";
import { contact, hemi, keyLight, LIGHT_SCALE, LIGHTS, scene } from "./viewport.js";

export const prefsDialog = document.getElementById("prefs-dialog");
export const gridPrefsDialog = document.getElementById("grid-prefs-dialog");
export const helpDialog = document.getElementById("help-dialog");

export function applyViz() {
  applyTheme(S.prefs);
  scene.background.setHex(INK.canvas);
  rebuildGrid();
  hemi.color.setHex(INK.lightSky);
  hemi.groundColor.setHex(S.prefs.ao ? INK.lightGround : INK.lightGroundFlat);
  hemi.intensity = (S.prefs.ao ? LIGHTS.hemi : LIGHTS.hemiFlat) * LIGHT_SCALE;
  keyLight.visible = S.prefs.keyLight;
  keyLight.intensity = S.prefs.keyLight ? LIGHTS.key * LIGHT_SCALE : 0;
  contact.visible = S.prefs.ao;
  contact.material.opacity = INK.contactOpacity;
  restyleCube();
  syncCurveInput();
  rebuild();
}

export function syncPrefsForm() {
  document.getElementById("pref-theme").value = S.prefs.theme;
  document.getElementById("pref-canvas").value = S.prefs.canvas;
  document.getElementById("pref-clay").value = String(S.prefs.clay);
  syncCurveInput();
  document.getElementById("pref-key").checked = S.prefs.keyLight;
  document.getElementById("pref-ao").checked = S.prefs.ao;
  document.getElementById("pref-edges").checked = S.prefs.showEdges;
  document.getElementById("pref-curves").checked = S.prefs.showCurves;
  document.getElementById("pref-faces").checked = S.prefs.showFaces;
}

// The colour input shows the theme's edge ink until a curve colour is chosen.
function syncCurveInput() {
  document.getElementById("pref-curve").value = S.prefs.curve || cssHex(INK.edge);
}

function readPrefsForm(event) {
  const curveInput = document.getElementById("pref-curve");
  S.prefs = {
    theme: document.getElementById("pref-theme").value,
    canvas: document.getElementById("pref-canvas").value,
    clay: Number(document.getElementById("pref-clay").value) || 176,
    curve: event && event.target === curveInput ? curveInput.value : S.prefs.curve,
    keyLight: document.getElementById("pref-key").checked,
    ao: document.getElementById("pref-ao").checked,
    showEdges: document.getElementById("pref-edges").checked,
    showCurves: document.getElementById("pref-curves").checked,
    showFaces: document.getElementById("pref-faces").checked,
    grid: S.gridOn,
    gridSnap: S.gridSnapOn,
    gridMinorOn: S.gridMinorOn,
    gridAuto: gridAutoOn(),
    gridMinor: prefMinorMm(),
    gridMajor: prefMajorMm(),
    gridHiddenScale: hiddenLineScale(),
    gridMinorStyle: gridMinorStyle(),
    gridDotSize: gridDotSize(),
    gridLineWidth: gridLineWidth(),
    displayUnit: displayUnit(),
  };
  savePrefs();
  applyViz();
  refreshToggles();
  if (S.lastPointer) updateGhost(S.lastPointer);
}

export function bindPrefsDialogs() {
  for (const id of [
    "pref-theme", "pref-canvas", "pref-clay", "pref-curve", "pref-key", "pref-ao",
    "pref-edges", "pref-curves", "pref-faces",
  ]) {
    document.getElementById(id).addEventListener("change", readPrefsForm);
    document.getElementById(id).addEventListener("input", readPrefsForm);
  }
  watchSystemTheme(() => S.prefs, applyViz);
  document.getElementById("prefs-close").addEventListener("click", () => prefsDialog.close());
  document.getElementById("grid-prefs-close").addEventListener("click", () => gridPrefsDialog.close());
  document.getElementById("help-close").addEventListener("click", () => helpDialog.close());
}
