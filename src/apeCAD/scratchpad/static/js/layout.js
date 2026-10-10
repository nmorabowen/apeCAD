// Dock layout: split handles, collapsible outliner / rail / console, session persistence.
import { syncCameras } from "./camera.js";
import { LAYOUT_KEY } from "./prefs.js";

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

export const workspaceEl = document.getElementById("workspace");
const outlinerEl = document.getElementById("outliner");
const propsEl = document.getElementById("props");
const consoleEl = document.getElementById("console");

export function persistLayout() {
  sessionStorage.setItem(LAYOUT_KEY, JSON.stringify({
    outliner: outlinerEl.style.width || "260px",
    props: propsEl.style.height || "140px",
    console: consoleEl.style.height || "72px",
    outlinerCollapsed: workspaceEl.classList.contains("outliner-collapsed"),
    railCollapsed: workspaceEl.classList.contains("rail-collapsed"),
    consoleCollapsed: document.body.classList.contains("console-collapsed"),
  }));
}

export function restoreLayout() {
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

export function bindLayout() {
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
}
