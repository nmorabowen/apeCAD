// Canvas pointer and window keyboard handling, and the rail / toggle button wiring.
import * as THREE from "three";
import { S } from "./state.js";
import { t } from "./strings.js";
import { findRecord } from "./brep.js";
import { projButton, releaseNamedViewForOrbit, setProjectionMode } from "./camera.js";
import {
  clearTyped,
  consoleInput,
  gridButton,
  gridSnapButton,
  isTypingField,
  orthoButton,
  refreshToggles,
  refuse,
  setHint,
  setTyped,
  snapButton,
} from "./cmdline.js";
import { closeMenus, commitWithEnter } from "./commands.js";
import { finishLineChain, pendingChain } from "./create.js";
import { newDocument, openDocument, redoDocument, saveDocument, undoDocument } from "./docfile.js";
import { updateGhost } from "./ghosts.js";
import { setGridOn, setGridSnapOn } from "./grid-ui.js";
import { commitDelete } from "./modify.js";
import { beginRename, treeEl } from "./outliner.js";
import { updatePreselect } from "./preselect.js";
import {
  applyWindowSelect,
  hideMarquee,
  selectAll,
  setSelectFilter,
  setSelection,
  updateMarquee,
} from "./selection.js";
import { onClick, setTool } from "./tools.js";
import { canvas, controls, ghosts } from "./viewport.js";

// Where the left button went down, to tell a click from a drag (window / crossing select).
let pointerDown = null;

export function bindToolButtons() {
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
}

export function bindCanvas() {
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
}

export function bindKeys() {
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
        setHint(t("hint.rename.one"));
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
        newDocument().catch((error) => refuse(error));
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
        undoDocument().catch((error) => refuse(error));
        return;
      }
      if (key === "y") {
        event.preventDefault();
        redoDocument().catch((error) => refuse(error));
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
      if (pendingChain()) {
        finishLineChain()
          .then(() => setHint(t("done.lineChainNext")))
          .catch((error) => refuse(error));
        return;
      }
      if (S.pending) {
        S.pending = null;
        clearTyped();
        ghosts.clear();
        S.ghostDims = [];
        hideMarquee();
        refreshToggles();
        setHint(t("done.cancelled"));
        return;
      }
      if (S.tool !== "select") {
        setTool("select");
        return;
      }
      setSelection(null);
      setHint(t("done.selectionCleared"));
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
        commitDelete().catch((error) => refuse(error));
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
        const filters = { 1: "point", 2: "line", 3: "face", 4: "solid", 5: "element", 6: "section" };
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
      commitDelete().catch((error) => refuse(error));
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
}
