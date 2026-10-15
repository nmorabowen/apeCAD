// Typed commands (Enter in the command line) and menu commands.
import { S } from "./state.js";
import { t } from "./strings.js";
import { goNamedView, setProjectionMode, syncCameras } from "./camera.js";
import {
  activeLength,
  appendLog,
  clearTyped,
  consolePrompt,
  refreshToggles,
  refuse,
  setHint,
  typedText,
} from "./cmdline.js";
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
  finishLineChain,
  finishPolygon,
  finishPolyline,
  pendingChain,
} from "./create.js";
import { newDocument, openDocument, redoDocument, saveDocument, undoDocument } from "./docfile.js";
import { currentEnd, updateGhost } from "./ghosts.js";
import {
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
} from "./grid-ui.js";
import { gridMinorMm } from "./grid.js";
import { persistLayout, workspaceEl } from "./layout.js";
import { commitDelete } from "./modify.js";
import { closeTreeMenu } from "./outliner.js";
import { gridPrefsDialog, helpDialog, prefsDialog, syncPrefsForm } from "./prefs-ui.js";
import { fromDisplay } from "./prefs.js";
import { selectAll } from "./selection.js";
import { hitWorkplane } from "./snap.js";
import { finishArray, finishMirror, finishMove, finishRotate } from "./transform.js";
import { ghosts } from "./viewport.js";

export async function commitWithEnter() {
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
    if (pendingChain() && activeLength() == null) {
      await finishLineChain();
      setHint(t("done.lineChain"));
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
      setHint(t("hint.box.height"));
      updateGhost(S.lastPointer);
      return;
    }
    // The finishers clear S.pending, so test the kind once (an `if` per kind read null).
    if (S.pending.kind === "height") await finishBox(S.lastPointer);
    else if (S.pending.kind === "extrude") await finishExtrude(S.lastPointer);
  } catch (error) {
    refuse(error);
    S.pending = null;
    ghosts.clear();
  }
}

export function closeMenus() {
  for (const menu of document.querySelectorAll(".menu.open")) menu.classList.remove("open");
  closeTreeMenu();
}

function runCommand(cmd) {
  closeMenus();
  if (cmd === "new") return newDocument().catch((error) => refuse(error));
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
    setHint(t("hint.quit"));
    return;
  }
  if (cmd === "undo") return undoDocument().catch((error) => refuse(error));
  if (cmd === "redo") return redoDocument().catch((error) => refuse(error));
  if (cmd === "select-all") return selectAll();
  if (cmd === "delete") return commitDelete().catch((error) => refuse(error));
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

export function bindMenus() {
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
}
