// The Preferences dialog: background, clay, curve colour, lights and visibility toggles.
import { S } from "./state.js";
import { refreshToggles } from "./cmdline.js";
import { updateGhost } from "./ghosts.js";
import { rebuildGrid } from "./grid.js";
import {
  BACKGROUNDS,
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
import { contact, hemi, keyLight, scene } from "./viewport.js";

export const prefsDialog = document.getElementById("prefs-dialog");
export const gridPrefsDialog = document.getElementById("grid-prefs-dialog");
export const helpDialog = document.getElementById("help-dialog");

export function applyViz() {
  const pal = BACKGROUNDS[S.prefs.background] || BACKGROUNDS.g5;
  scene.background.setHex(pal.bg);
  document.getElementById("stage").style.background = `#${pal.bg.toString(16).padStart(6, "0")}`;
  rebuildGrid();
  const dark = S.prefs.background === "g2";
  hemi.color.setHex(dark ? 0xc8cdd3 : 0xf4f7fb);
  hemi.groundColor.setHex(S.prefs.ao ? (dark ? 0x0a0a0a : 0x6e757c) : (dark ? 0x2a2a2a : 0xc5cad0));
  hemi.intensity = S.prefs.ao ? 0.58 : 0.42;
  keyLight.visible = S.prefs.keyLight;
  keyLight.intensity = S.prefs.keyLight ? 0.45 : 0;
  contact.visible = S.prefs.ao;
  contact.material.opacity = dark ? 0.18 : 0.06;
  rebuild();
}

export function syncPrefsForm() {
  document.getElementById("pref-background").value = S.prefs.background;
  document.getElementById("pref-clay").value = String(S.prefs.clay);
  document.getElementById("pref-curve").value = S.prefs.curve;
  document.getElementById("pref-key").checked = S.prefs.keyLight;
  document.getElementById("pref-ao").checked = S.prefs.ao;
  document.getElementById("pref-edges").checked = S.prefs.showEdges;
  document.getElementById("pref-curves").checked = S.prefs.showCurves;
  document.getElementById("pref-faces").checked = S.prefs.showFaces;
}

function readPrefsForm() {
  S.prefs = {
    background: document.getElementById("pref-background").value,
    clay: Number(document.getElementById("pref-clay").value) || 176,
    curve: document.getElementById("pref-curve").value,
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
    "pref-background", "pref-clay", "pref-curve", "pref-key", "pref-ao",
    "pref-edges", "pref-curves", "pref-faces",
  ]) {
    document.getElementById(id).addEventListener("change", readPrefsForm);
    document.getElementById(id).addEventListener("input", readPrefsForm);
  }
  document.getElementById("prefs-close").addEventListener("click", () => prefsDialog.close());
  document.getElementById("grid-prefs-close").addEventListener("click", () => gridPrefsDialog.close());
  document.getElementById("help-close").addEventListener("click", () => helpDialog.close());
}
