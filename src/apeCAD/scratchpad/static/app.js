// Bootstrap: build the scene, wire the UI, start the render loop, load the document.
// Behaviour lives in js/*.js (ADR 0023); client state is the S object in js/state.js.
import { camera, initCamera, syncCameras, tickViewAnim } from "./js/camera.js";
import { projectDims, refreshToggles, setHint } from "./js/cmdline.js";
import { bindMenus } from "./js/commands.js";
import { bindFileOpen, reload } from "./js/docfile.js";
import { bindGridPrefs } from "./js/grid-ui.js";
import { rebuildGrid } from "./js/grid.js";
import { bindCanvas, bindKeys, bindToolButtons } from "./js/input.js";
import { bindLayout, restoreLayout } from "./js/layout.js";
import { bindOutliner } from "./js/outliner.js";
import { applyViz, bindPrefsDialogs, syncPrefsForm } from "./js/prefs-ui.js";
import { initPrefs } from "./js/prefs.js";
import { bindViewCube, syncCube } from "./js/viewcube.js";
import { renderer, scene } from "./js/viewport.js";

initPrefs();
rebuildGrid();
initCamera();

bindViewCube();
bindOutliner();
bindToolButtons();
bindCanvas();
bindKeys();
bindMenus();
bindFileOpen();
bindPrefsDialogs();
bindGridPrefs();
bindLayout();

function tick() {
  tickViewAnim();
  syncCameras();
  renderer.render(scene, camera());
  syncCube();
  projectDims();
  requestAnimationFrame(tick);
}

restoreLayout();
syncPrefsForm();
applyViz();
refreshToggles();
tick();
reload().catch((error) => setHint(error.message));
