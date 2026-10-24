// Bootstrap: build the scene, wire the UI, start the dirty-flagged render loop, load the document.
// Behaviour lives in js/*.js (ADR 0023); client state is the S object in js/state.js + store.js.
import { camera, initCamera, syncCameras, tickViewAnim, updateCameraMatrices } from "./js/camera.js";
import { projectDims, refreshToggles, refuse } from "./js/cmdline.js";
import { bindMenus } from "./js/commands.js";
import { bindFileOpen, reload } from "./js/docfile.js";
import { bindGridPrefs } from "./js/grid-ui.js";
import { rebuildGrid } from "./js/grid.js";
import { api } from "./js/api.js";
import { bindCanvas, bindKeys, bindToolButtons } from "./js/input.js";
import { bindLayout, restoreLayout } from "./js/layout.js";
import { startRevisionPoll } from "./js/live.js";
import { bindCadNavigation } from "./js/navigation.js";
import { bindOutliner } from "./js/outliner.js";
import { applyViz, bindPrefsDialogs, syncPrefsForm } from "./js/prefs-ui.js";
import { initPrefs } from "./js/prefs.js";
import { refreshFrom } from "./js/render.js";
import { bindSectionBar } from "./js/section-tools.js";
import { hideMarquee } from "./js/selection.js";
import { cursorPivot } from "./js/snap.js";
import { S } from "./js/state.js";
import { consumeRenderDirty, requestRender, setRenderWake } from "./js/store.js";
import { bindViewCube, syncCube } from "./js/viewcube.js";
import { canvas, exportViewportPng, controls, renderer, scene } from "./js/viewport.js";

initPrefs();
rebuildGrid();
initCamera();

bindViewCube();
bindOutliner();
bindToolButtons();
bindSectionBar();
bindCanvas();
bindCadNavigation({
  canvas,
  controls,
  hitWorkplane: cursorPivot,
  hideMarquee,
});
bindKeys();
bindMenus();
bindFileOpen();
bindPrefsDialogs();
bindGridPrefs();
bindLayout();

// Dirty-flagged render loop (ADR 0035): sleeps at 0 fps when the scene, camera, and overlays
// are clean, and wakes immediately on requestRender() or while a camera animation is active.
let _rafPending = false;

function scheduleTick() {
  if (_rafPending) return;
  _rafPending = true;
  requestAnimationFrame(tick);
}

function tick() {
  consumeRenderDirty();
  const animating = tickViewAnim();
  updateCameraMatrices();
  consumeRenderDirty();
  _rafPending = false;
  renderer.render(scene, camera());
  syncCube();
  projectDims();
  if (animating) {
    scheduleTick();
  }
}

setRenderWake(scheduleTick);
window.__apecadCaptureStill = () => exportViewportPng(camera());

restoreLayout();
syncPrefsForm();
applyViz();
refreshToggles();
requestRender();
const _wantCapture = new URLSearchParams(window.location.search).get("capture") === "1";
if (_wantCapture) {
  updateCameraMatrices();
  document.documentElement.dataset.apecadStill = window.__apecadCaptureStill();
}
await reload()
  .then(() => {
    if (_wantCapture) {
      tickViewAnim(true);
      updateCameraMatrices();
      document.documentElement.dataset.apecadStill = window.__apecadCaptureStill();
    }
  })
  .catch((error) => refuse(error));
if (!_wantCapture) {
  startRevisionPoll({
    fetchJson: api,
    current: () => S.sceneState,
    apply: refreshFrom,
    busy: () => Boolean(S.pending),
  });
}
