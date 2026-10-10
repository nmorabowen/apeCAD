import * as THREE from "three";
import { S } from "./js/state.js";
import { api } from "./js/api.js";
import { findRecord } from "./js/brep.js";
import {
  bindProjectionCamera,
  camera,
  goNamedView,
  initCamera,
  lookAtScene,
  projButton,
  releaseNamedViewForOrbit,
  setProjectionMode,
  syncCameras,
  tickViewAnim,
} from "./js/camera.js";
import {
  activeLength,
  appendLog,
  clearTyped,
  consoleInput,
  consolePrompt,
  gridButton,
  gridSnapButton,
  isTypingField,
  orthoButton,
  projectDims,
  refreshToggles,
  setHint,
  setTyped,
  snapButton,
  typedText,
} from "./js/cmdline.js";
import {
  appendPolylineVertex,
  finishArc,
  finishBezier,
  finishBox,
  finishCircle,
  finishEllipse,
  finishExtrude,
  finishFace,
  finishLine,
  finishPolygon,
  finishPolyline,
} from "./js/create.js";
import { currentEnd, updateGhost } from "./js/ghosts.js";
import {
  bindGridPrefs,
  setDisplayUnit,
  setGridAuto,
  setGridDotSize,
  setGridHiddenScale,
  setGridLineWidth,
  setGridMinorStyle,
  setGridOn,
  setGridSnapOn,
  setGridSpacing,
  syncGridPrefsForm,
} from "./js/grid-ui.js";
import { gridMinorMm, rebuildGrid } from "./js/grid.js";
import { commitDelete } from "./js/modify.js";
import { beginRename, bindOutliner, closeTreeMenu, treeEl } from "./js/outliner.js";
import {
  BACKGROUNDS,
  LAYOUT_KEY,
  displayUnit,
  fromDisplay,
  gridAutoOn,
  gridDotSize,
  gridLineWidth,
  gridMinorStyle,
  hiddenLineScale,
  initPrefs,
  prefMajorMm,
  prefMinorMm,
  savePrefs,
} from "./js/prefs.js";
import { updatePreselect } from "./js/preselect.js";
import { rebuild, refreshFrom } from "./js/render.js";
import {
  applyWindowSelect,
  hideMarquee,
  selectAll,
  setSelectFilter,
  setSelection,
  updateMarquee,
} from "./js/selection.js";
import { hitWorkplane } from "./js/snap.js";
import { onClick, setTool } from "./js/tools.js";
import { finishArray, finishMirror, finishMove, finishRotate } from "./js/transform.js";
import { bindViewCube, syncCube } from "./js/viewcube.js";
import {
  ISO_DIR,
  WORLD_UP,
  canvas,
  contact,
  controls,
  ghosts,
  hemi,
  keyLight,
  renderer,
  scene,
  viewUp,
} from "./js/viewport.js";

initPrefs();

let pointerDown = null;


rebuildGrid();

initCamera();

bindViewCube();

bindOutliner();

async function reload() {
  await refreshFrom(await api("/api/scene"));
  lookAtScene(ISO_DIR, { up: WORLD_UP.clone() });
}

async function commitWithEnter() {
  if (!S.pending) {
    const echoed = typedText();
    if (/^grid\s+auto$/i.test(echoed)) {
      appendLog(`${consolePrompt.textContent} ${echoed}`);
      setGridAuto(true);
      clearTyped();
      return;
    }
    if (/^grid\s+manual$/i.test(echoed)) {
      appendLog(`${consolePrompt.textContent} ${echoed}`);
      setGridAuto(false);
      clearTyped();
      return;
    }
    const match = echoed.match(/^grid(?:\s+|=)(\d+(?:\.\d+)?)(?:\s+(\d+(?:\.\d+)?))?$/i);
    if (match) {
      appendLog(`${consolePrompt.textContent} ${echoed}`);
      setGridSpacing(
        fromDisplay(Number(match[1])),
        match[2] != null ? fromDisplay(Number(match[2])) : undefined,
      );
      clearTyped();
      return;
    }
    const majorMatch = echoed.match(/^major(?:\s+|=)(\d+(?:\.\d+)?)$/i);
    if (majorMatch) {
      appendLog(`${consolePrompt.textContent} ${echoed}`);
      setGridSpacing(gridMinorMm(), fromDisplay(Number(majorMatch[1])));
      clearTyped();
      return;
    }
    const hiddenMatch = echoed.match(/^hidden(?:\s+|=)(\d+(?:\.\d+)?)$/i);
    if (hiddenMatch) {
      appendLog(`${consolePrompt.textContent} ${echoed}`);
      setGridHiddenScale(Number(hiddenMatch[1]));
      clearTyped();
      return;
    }
    const dotMatch = echoed.match(/^dot(?:size)?(?:\s+|=)(\d+(?:\.\d+)?)$/i);
    if (dotMatch) {
      appendLog(`${consolePrompt.textContent} ${echoed}`);
      setGridDotSize(Number(dotMatch[1]));
      clearTyped();
      return;
    }
    const thickMatch = echoed.match(/^(?:thick(?:ness)?|linew(?:idth)?)(?:\s+|=)(\d+(?:\.\d+)?)$/i);
    if (thickMatch) {
      appendLog(`${consolePrompt.textContent} ${echoed}`);
      setGridLineWidth(Number(thickMatch[1]));
      clearTyped();
      return;
    }
    const styleMatch = echoed.match(/^(?:minor\s+)?(dots|lines)$/i);
    if (styleMatch) {
      appendLog(`${consolePrompt.textContent} ${echoed}`);
      setGridMinorStyle(styleMatch[1].toLowerCase());
      clearTyped();
      return;
    }
    const unitMatch = echoed.match(/^(mm|cm|m|in)$/i);
    if (unitMatch) {
      appendLog(`${consolePrompt.textContent} ${echoed}`);
      setDisplayUnit(unitMatch[1].toLowerCase());
      clearTyped();
      return;
    }
    const viewMatch = echoed.match(/^(top|front|right|left|back|bottom)$/i);
    if (viewMatch) {
      appendLog(`${consolePrompt.textContent} ${echoed}`);
      goNamedView(viewMatch[1].toLowerCase());
      clearTyped();
      return;
    }
    if (/^persp(ective)?$/i.test(echoed)) {
      appendLog(`${consolePrompt.textContent} ${echoed}`);
      setProjectionMode("perspective");
      clearTyped();
      return;
    }
    if (/^parallel$/i.test(echoed)) {
      appendLog(`${consolePrompt.textContent} ${echoed}`);
      setProjectionMode("parallel");
      clearTyped();
      return;
    }
    return;
  }
  const echoed = typedText();
  if (echoed) appendLog(`${consolePrompt.textContent} ${echoed}`);
  try {
    if (S.pending.kind === "polyline") {
      const token = echoed.trim().toLowerCase();
      if (token === "c" || token === "close") {
        await finishPolyline(true);
        return;
      }
      if (activeLength() != null && S.lastPointer) {
        const end = currentEnd(S.lastPointer);
        if (end) await appendPolylineVertex(end);
        return;
      }
      await finishPolyline(false);
      return;
    }
    if (S.pending.kind === "rotate") {
      const typed = activeLength();
      if (typed != null) {
        await finishRotate(S.pending.a, typed);
        return;
      }
      if (!S.lastPointer) return;
      const end = hitWorkplane(S.lastPointer);
      if (end) {
        await finishRotate(
          S.pending.a,
          Math.atan2(end.y_mm - S.pending.a.y_mm, end.x_mm - S.pending.a.x_mm) * 180 / Math.PI,
        );
      }
      return;
    }
    if (!S.lastPointer) return;
    if (S.pending.kind === "line" || S.pending.kind === "move" || S.pending.kind === "array" || S.pending.kind === "mirror") {
      const end = currentEnd(S.lastPointer);
      if (end) {
        if (S.pending.kind === "move") await finishMove(end);
        else if (S.pending.kind === "array") await finishArray(end);
        else if (S.pending.kind === "mirror") await finishMirror(S.pending.a, end);
        else await finishLine(end);
      }
      return;
    }
    if (S.pending.kind === "rect" && S.tool === "rect") {
      const end = currentEnd(S.lastPointer);
      if (end) await finishFace(end);
      return;
    }
    if (S.pending.kind === "radial") {
      const rim = currentEnd(S.lastPointer);
      if (!rim) return;
      if (S.tool === "circle") await finishCircle(rim);
      else if (S.tool === "polygon") await finishPolygon(rim);
      else if (S.tool === "ellipse") await finishEllipse(rim);
      return;
    }
    if (S.pending.kind === "arc" && S.pending.pts.length === 2) {
      const end = currentEnd(S.lastPointer);
      if (end) await finishArc(end);
      return;
    }
    if (S.pending.kind === "bezier" && S.pending.pts.length === 3) {
      const end = currentEnd(S.lastPointer);
      if (end) await finishBezier(end);
      return;
    }
    if (S.pending.kind === "rect" && S.tool === "box") {
      const end = currentEnd(S.lastPointer);
      if (!end) return;
      S.pending = { kind: "height", a: S.pending.a, b: end };
      setHint("Box: move for height, type a length, then click or Enter.");
      updateGhost(S.lastPointer);
      return;
    }
    if (S.pending.kind === "height") await finishBox(S.lastPointer);
    if (S.pending.kind === "extrude") await finishExtrude(S.lastPointer);
  } catch (error) {
    setHint(error.message);
    S.pending = null;
    ghosts.clear();
  }
}

for (const button of document.querySelectorAll("button[data-tool]")) {
  button.addEventListener("click", () => setTool(button.dataset.tool));
}
for (const button of document.querySelectorAll("#sel-filters [data-filter]")) {
  button.addEventListener("click", () => {
    setTool("select");
    setSelectFilter(button.dataset.filter);
  });
}

projButton.addEventListener("click", () => {
  setProjectionMode(S.projection === "perspective" ? "parallel" : "perspective");
});
snapButton.addEventListener("click", () => {
  S.snapOn = !S.snapOn;
  refreshToggles();
  if (S.lastPointer) updateGhost(S.lastPointer);
});
gridSnapButton.addEventListener("click", () => {
  setGridSnapOn(!S.gridSnapOn);
  if (S.lastPointer) updateGhost(S.lastPointer);
});
orthoButton.addEventListener("click", () => {
  S.orthoOn = !S.orthoOn;
  refreshToggles();
  if (S.lastPointer) updateGhost(S.lastPointer);
});
gridButton.addEventListener("click", () => {
  setGridOn(!S.gridOn);
  if (S.lastPointer) updateGhost(S.lastPointer);
});
consoleInput.addEventListener("input", () => {
  refreshToggles();
  if (S.lastPointer) updateGhost(S.lastPointer);
});

canvas.addEventListener("pointerdown", (event) => {
  canvas.focus();
  if (event.button === 0 && event.altKey) {
    controls.mouseButtons.LEFT = THREE.MOUSE.ROTATE;
  } else {
    controls.mouseButtons.LEFT = -1;
  }
  if (event.button === 1 || (event.button === 0 && event.altKey)) {
    releaseNamedViewForOrbit();
  }
  if (event.button !== 0) return;
  pointerDown = { x: event.clientX, y: event.clientY };
  if (S.tool === "select" && !event.altKey) {
    S.marqueeOrigin = { x: event.clientX, y: event.clientY };
    canvas.setPointerCapture(event.pointerId);
  }
}, true);
canvas.addEventListener("pointermove", (event) => {
  S.lastPointer = event;
  if (S.marqueeOrigin) updateMarquee(event);
  updatePreselect(event);
  updateGhost(event);
});
canvas.addEventListener("pointerup", (event) => {
  controls.mouseButtons.LEFT = -1;
  if (event.button !== 0 || !pointerDown) return;
  const origin = S.marqueeOrigin;
  const moved = Math.hypot(event.clientX - pointerDown.x, event.clientY - pointerDown.y);
  pointerDown = null;
  if (origin && moved > 5) {
    applyWindowSelect(origin, event);
    return;
  }
  hideMarquee();
  if (event.altKey || moved > 5) return;
  onClick(event);
});
canvas.addEventListener("contextmenu", (event) => event.preventDefault());

window.addEventListener("keydown", (event) => {
  if (event.key === "F3") {
    event.preventDefault();
    S.snapOn = !S.snapOn;
    refreshToggles();
    if (S.lastPointer) updateGhost(S.lastPointer);
    return;
  }
  if (event.key === "F7") {
    event.preventDefault();
    setGridSnapOn(!S.gridSnapOn);
    if (S.lastPointer) updateGhost(S.lastPointer);
    return;
  }
  if (event.key === "F8") {
    event.preventDefault();
    S.orthoOn = !S.orthoOn;
    refreshToggles();
    if (S.lastPointer) updateGhost(S.lastPointer);
    return;
  }
  if (event.key === "F9") {
    event.preventDefault();
    setGridOn(!S.gridOn);
    if (S.lastPointer) updateGhost(S.lastPointer);
    return;
  }
  if (event.key === "F2") {
    if (isTypingField(event) || event.target === consoleInput) return;
    event.preventDefault();
    if (S.selectedIds.size !== 1) {
      setHint("Select one entity to rename.");
      return;
    }
    const id = [...S.selectedIds][0];
    const row = findRecord(id);
    const rowEl = treeEl.querySelector(`.tree-row[data-id="${id}"]`);
    if (row && rowEl) beginRename(row, rowEl);
    return;
  }
  if (event.ctrlKey || event.metaKey) {
    const key = event.key.toLowerCase();
    if (key === "n") {
      event.preventDefault();
      newDocument().catch((error) => setHint(error.message));
      return;
    }
    if (key === "o") {
      event.preventDefault();
      openDocument();
      return;
    }
    if (key === "s") {
      event.preventDefault();
      saveDocument(event.shiftKey);
      return;
    }
    if (key === "z") {
      event.preventDefault();
      undoDocument().catch((error) => setHint(error.message));
      return;
    }
    if (key === "y") {
      event.preventDefault();
      redoDocument().catch((error) => setHint(error.message));
      return;
    }
    if (key === "a") {
      if (event.target === consoleInput || isTypingField(event)) return;
      event.preventDefault();
      selectAll();
      return;
    }
    return;
  }
  if (event.key === "Escape") {
    if (document.querySelector(".menu.open")) {
      event.preventDefault();
      closeMenus();
      return;
    }
    if (document.querySelector("dialog[open]")) return;
    if (S.pending) {
      const endedChain = S.pending.kind === "line" && S.pending.chain;
      S.pending = null;
      clearTyped();
      ghosts.clear();
      S.ghostDims = [];
      hideMarquee();
      refreshToggles();
      setHint(endedChain
        ? "Line chain ended. Click to start another, or Esc for Select."
        : "Cancelled.");
      return;
    }
    if (S.tool !== "select") {
      setTool("select");
      return;
    }
    setSelection(null);
    setHint("Selection cleared.");
    return;
  }
  if (event.target === consoleInput) {
    if (event.key === "Enter") {
      event.preventDefault();
      commitWithEnter();
      return;
    }
    if (event.key === "Delete" && consoleInput.value === "") {
      event.preventDefault();
      commitDelete().catch((error) => setHint(error.message));
      return;
    }
    if (consoleInput.value === "" && !event.ctrlKey && !event.metaKey && !event.altKey) {
      if (event.key === "t" || event.key === "T") {
        event.preventDefault();
        setTool("trim");
        return;
      }
      if (event.key === "m" || event.key === "M") {
        event.preventDefault();
        setTool("move");
        return;
      }
      if (event.key === "e" || event.key === "E") {
        event.preventDefault();
        setTool("extend");
        return;
      }
      if (event.key === "j" || event.key === "J") {
        event.preventDefault();
        setTool("join");
        return;
      }
    }
    return;
  }
  if (isTypingField(event)) return;
  if (!event.ctrlKey && !event.metaKey && !event.altKey) {
    if (S.tool === "select") {
      const filters = { 1: "point", 2: "line", 3: "face", 4: "solid", 5: "element" };
      if (filters[event.key]) {
        event.preventDefault();
        setSelectFilter(filters[event.key]);
        return;
      }
    }
    if (event.key === "t" || event.key === "T") {
      event.preventDefault();
      setTool("trim");
      return;
    }
    if (event.key === "m" || event.key === "M") {
      event.preventDefault();
      setTool("move");
      return;
    }
    if (event.key === "e" || event.key === "E") {
      event.preventDefault();
      setTool("extend");
      return;
    }
    if (event.key === "j" || event.key === "J") {
      event.preventDefault();
      setTool("join");
      return;
    }
  }
  if (event.key === "Delete") {
    event.preventDefault();
    commitDelete().catch((error) => setHint(error.message));
    return;
  }
  if (event.key === "o" || event.key === "O") {
    setProjectionMode(S.projection === "perspective" ? "parallel" : "perspective");
    return;
  }
  if (event.key === "Enter") {
    event.preventDefault();
    commitWithEnter();
    return;
  }
  if (event.key === "Backspace" && consoleInput.value !== "") {
    event.preventDefault();
    setTyped(consoleInput.value.slice(0, -1));
    refreshToggles();
    if (S.lastPointer) updateGhost(S.lastPointer);
    return;
  }
  if (event.key.length === 1 && /[0-9.]/.test(event.key)) {
    if (event.key === "." && consoleInput.value.includes(".")) return;
    setTyped(consoleInput.value + event.key);
    refreshToggles();
    if (S.lastPointer) updateGhost(S.lastPointer);
  }
});

function bindSplit(handle, onMove) {
  handle.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    event.preventDefault();
    handle.setPointerCapture(event.pointerId);
    handle.classList.add("dragging");
    const onPointerMove = (moveEvent) => onMove(moveEvent);
    const onPointerUp = () => {
      handle.classList.remove("dragging");
      try { handle.releasePointerCapture(event.pointerId); } catch (_error) { /* already released */ }
      handle.removeEventListener("pointermove", onPointerMove);
      handle.removeEventListener("pointerup", onPointerUp);
      syncCameras();
    };
    handle.addEventListener("pointermove", onPointerMove);
    handle.addEventListener("pointerup", onPointerUp);
  });
}

const workspaceEl = document.getElementById("workspace");
const outlinerEl = document.getElementById("outliner");
const propsEl = document.getElementById("props");
const consoleEl = document.getElementById("console");
const fileOpenEl = document.getElementById("file-open");
const prefsDialog = document.getElementById("prefs-dialog");
const gridPrefsDialog = document.getElementById("grid-prefs-dialog");
const helpDialog = document.getElementById("help-dialog");

function persistLayout() {
  sessionStorage.setItem(LAYOUT_KEY, JSON.stringify({
    outliner: outlinerEl.style.width || "260px",
    props: propsEl.style.height || "140px",
    console: consoleEl.style.height || "72px",
    outlinerCollapsed: workspaceEl.classList.contains("outliner-collapsed"),
    railCollapsed: workspaceEl.classList.contains("rail-collapsed"),
    consoleCollapsed: document.body.classList.contains("console-collapsed"),
  }));
}

function restoreLayout() {
  try {
    const layout = JSON.parse(sessionStorage.getItem(LAYOUT_KEY) || "null");
    if (!layout || typeof layout !== "object") return;
    if (layout.outliner) outlinerEl.style.width = layout.outliner;
    if (layout.props) propsEl.style.height = layout.props;
    if (layout.console) consoleEl.style.height = layout.console;
    workspaceEl.classList.toggle("outliner-collapsed", !!layout.outlinerCollapsed);
    workspaceEl.classList.toggle("rail-collapsed", !!layout.railCollapsed);
    document.body.classList.toggle("console-collapsed", !!layout.consoleCollapsed);
  } catch (_error) {
    /* keep defaults */
  }
}

function applyViz() {
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

function syncPrefsForm() {
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

function downloadJson(filename) {
  const blob = new Blob([JSON.stringify(S.sceneState.document, null, 2)], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  URL.revokeObjectURL(link.href);
}

function saveDocument(saveAs = false) {
  if (saveAs) {
    const next = window.prompt("Save as", S.saveName) || "";
    if (!next.trim()) return;
    S.saveName = next.trim().endsWith(".json") ? next.trim() : `${next.trim()}.json`;
  }
  downloadJson(S.saveName);
  setHint(`Saved ${S.saveName}. Preferences are not in this file.`);
}

function openDocument() {
  fileOpenEl.click();
}

function documentFromFile(parsed) {
  if (parsed && parsed.schema && Array.isArray(parsed.ops)) return parsed;
  if (parsed && parsed.document && parsed.document.schema) return parsed.document;
  throw new Error("not an apeCAD document JSON");
}

async function loadDocumentDict(dict, name) {
  S.pending = null;
  ghosts.clear();
  S.selectedIds.clear();
  await refreshFrom(await api("/api/load", "POST", dict));
  if (name) S.saveName = name;
  S.namedView = null;
  viewUp.copy(WORLD_UP);
  bindProjectionCamera();
  lookAtScene(ISO_DIR, { up: WORLD_UP.clone() });
  setHint(`Opened ${S.saveName}.`);
}

async function newDocument() {
  S.pending = null;
  ghosts.clear();
  S.selectedIds.clear();
  await refreshFrom(await api("/api/reset", "POST", {}));
  S.saveName = "apecad.json";
  S.namedView = null;
  viewUp.copy(WORLD_UP);
  bindProjectionCamera();
  lookAtScene(ISO_DIR, { up: WORLD_UP.clone() });
  setHint("New document.");
}

async function undoDocument() {
  S.pending = null;
  ghosts.clear();
  await refreshFrom(await api("/api/undo", "POST", {}));
}

async function redoDocument() {
  await refreshFrom(await api("/api/redo", "POST", {}));
}

function closeMenus() {
  for (const menu of document.querySelectorAll(".menu.open")) menu.classList.remove("open");
  closeTreeMenu();
}

function runCommand(cmd) {
  closeMenus();
  if (cmd === "new") return newDocument().catch((error) => setHint(error.message));
  if (cmd === "open" || cmd === "import") return openDocument();
  if (cmd === "save") return saveDocument(false);
  if (cmd === "save-as" || cmd === "export") return saveDocument(true);
  if (cmd === "prefs") {
    syncPrefsForm();
    prefsDialog.showModal();
    return;
  }
  if (cmd === "grid-prefs") {
    syncGridPrefsForm();
    gridPrefsDialog.showModal();
    return;
  }
  if (cmd === "quit") {
    window.close();
    setHint("Close the browser tab to quit.");
    return;
  }
  if (cmd === "undo") return undoDocument().catch((error) => setHint(error.message));
  if (cmd === "redo") return redoDocument().catch((error) => setHint(error.message));
  if (cmd === "select-all") return selectAll();
  if (cmd === "delete") return commitDelete().catch((error) => setHint(error.message));
  if (cmd === "perspective") return setProjectionMode("perspective");
  if (cmd === "parallel") return setProjectionMode("parallel");
  if (cmd === "view-top") return goNamedView("top");
  if (cmd === "view-front") return goNamedView("front");
  if (cmd === "view-right") return goNamedView("right");
  if (cmd === "view-left") return goNamedView("left");
  if (cmd === "view-back") return goNamedView("back");
  if (cmd === "view-bottom") return goNamedView("bottom");
  if (cmd === "projection") {
    return setProjectionMode(S.projection === "perspective" ? "parallel" : "perspective");
  }
  if (cmd === "snap") {
    S.snapOn = !S.snapOn;
    refreshToggles();
    return;
  }
  if (cmd === "grid-snap") {
    setGridSnapOn(!S.gridSnapOn);
    return;
  }
  if (cmd === "ortho") {
    S.orthoOn = !S.orthoOn;
    refreshToggles();
    return;
  }
  if (cmd === "grid") {
    setGridOn(!S.gridOn);
    return;
  }
  if (cmd === "fit") return document.getElementById("view-fit").click();
  if (cmd === "iso") return document.getElementById("view-iso").click();
  if (cmd === "viewcube") {
    S.viewCubeOn = !S.viewCubeOn;
    document.getElementById("viewcube-wrap").hidden = !S.viewCubeOn;
    return;
  }
  if (cmd === "toggle-outliner") {
    workspaceEl.classList.toggle("outliner-collapsed");
    persistLayout();
    syncCameras();
    return;
  }
  if (cmd === "toggle-rail") {
    workspaceEl.classList.toggle("rail-collapsed");
    persistLayout();
    return;
  }
  if (cmd === "toggle-console") {
    document.body.classList.toggle("console-collapsed");
    persistLayout();
    syncCameras();
    return;
  }
  if (cmd === "help") {
    helpDialog.showModal();
  }
}

for (const menu of document.querySelectorAll(".menu")) {
  const button = menu.querySelector(":scope > button");
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    const wasOpen = menu.classList.contains("open");
    closeMenus();
    if (!wasOpen) menu.classList.add("open");
  });
}
document.addEventListener("click", closeMenus);
for (const button of document.querySelectorAll("[data-cmd]")) {
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    runCommand(button.dataset.cmd);
  });
}

fileOpenEl.addEventListener("change", async () => {
  const file = fileOpenEl.files && fileOpenEl.files[0];
  fileOpenEl.value = "";
  if (!file) return;
  try {
    await loadDocumentDict(documentFromFile(JSON.parse(await file.text())), file.name);
  } catch (error) {
    setHint(error.message);
  }
});

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
bindGridPrefs();

bindSplit(document.getElementById("split-outliner"), (event) => {
  const rect = workspaceEl.getBoundingClientRect();
  const maxWidth = Math.max(rect.width * 0.5, 180);
  outlinerEl.style.width = `${Math.min(Math.max(event.clientX - rect.left, 180), maxWidth)}px`;
  persistLayout();
  syncCameras();
});
bindSplit(document.getElementById("split-tree"), (event) => {
  const rect = outlinerEl.getBoundingClientRect();
  const height = Math.min(Math.max(rect.bottom - event.clientY, 72), rect.height - 140);
  propsEl.style.height = `${height}px`;
  persistLayout();
});
bindSplit(document.getElementById("split-console"), (event) => {
  const body = document.body.getBoundingClientRect();
  consoleEl.style.height = `${Math.min(Math.max(body.bottom - event.clientY, 56), body.height * 0.4)}px`;
  persistLayout();
  syncCameras();
});

document.getElementById("outliner-toggle").addEventListener("click", () => {
  workspaceEl.classList.add("outliner-collapsed");
  persistLayout();
  syncCameras();
});
document.getElementById("outliner-expand").addEventListener("click", () => {
  workspaceEl.classList.remove("outliner-collapsed");
  persistLayout();
  syncCameras();
});
document.getElementById("rail-toggle").addEventListener("click", () => {
  workspaceEl.classList.add("rail-collapsed");
  persistLayout();
});
document.getElementById("rail-expand").addEventListener("click", () => {
  workspaceEl.classList.remove("rail-collapsed");
  persistLayout();
});

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
