// Document file actions: new, open, save, exports, undo / redo against the server document.
import { S } from "./state.js";
import { t } from "./strings.js";
import { api } from "./api.js";
import { bindProjectionCamera, goNamedView, lookAtScene } from "./camera.js";
import { refuse, setHint } from "./cmdline.js";
import { updateGhost } from "./ghosts.js";
import { refreshFrom } from "./render.js";
import { ISO_DIR, WORLD_UP, ghosts, viewUp } from "./viewport.js";

export async function reload() {
  await refreshFrom(await api("/api/scene"));
  lookAtScene(ISO_DIR, { up: WORLD_UP.clone() });
}

const fileOpenEl = document.getElementById("file-open");

function downloadBlob(blob, filename) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  URL.revokeObjectURL(link.href);
}

function downloadJson(data, filename) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  downloadBlob(blob, filename);
}

function baseStem() {
  return (S.saveName || "apecad.json").replace(/(\.section-draft)?\.json$/i, "");
}

export async function saveDocument(saveAs = false) {
  const body = JSON.stringify(S.sceneState.document, null, 2);
  if (!saveAs && S.fileHandle && typeof S.fileHandle.createWritable === "function") {
    try {
      const writable = await S.fileHandle.createWritable();
      await writable.write(body);
      await writable.close();
      setHint(t("done.saved", { name: S.saveName }));
      return;
    } catch (error) {
      if (error && error.name === "AbortError") return;
    }
  }
  if (typeof window.showSaveFilePicker === "function") {
    try {
      const handle = await window.showSaveFilePicker({
        suggestedName: S.saveName || "apecad.json",
        types: [{
          description: "apeCAD JSON",
          accept: { "application/json": [".json"] },
        }],
      });
      if (!handle) return;
      const writable = await handle.createWritable();
      await writable.write(body);
      await writable.close();
      S.fileHandle = handle;
      if (handle.name) S.saveName = handle.name;
      setHint(t("done.saved", { name: S.saveName }));
      return;
    } catch (error) {
      if (error && error.name === "AbortError") return;
      refuse(error);
      return;
    }
  }
  if (saveAs) {
    const next = window.prompt(t("menu.saveAsPrompt"), S.saveName) || "";
    if (!next.trim()) return;
    S.saveName = next.trim().endsWith(".json") ? next.trim() : `${next.trim()}.json`;
  }
  downloadJson(S.sceneState.document, S.saveName);
  setHint(t("done.saved", { name: S.saveName }));
}

export async function exportSectionDraft() {
  const env = await api("/api/section/draft");
  const name = `${baseStem()}.section-draft.json`;
  downloadJson(env.draft, name);
  setHint(t("done.exportedDraft", { name }));
}

export async function exportSvg() {
  const isSection = (S.sceneState.concrete_faces || []).length > 0 || (S.sceneState.bars || []).length > 0;
  const view = S.namedView || (isSection ? "top" : "iso");
  const response = await fetch(`/api/render.svg?view=${encodeURIComponent(view)}&annotate=true`);
  if (!response.ok) {
    const err = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(err.error || response.statusText);
  }
  const name = `${baseStem()}.svg`;
  downloadBlob(await response.blob(), name);
  setHint(t("done.exportedSvg", { name }));
}

export async function exportDxf() {
  const response = await fetch("/api/export.dxf");
  if (!response.ok) {
    const err = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(err.error || response.statusText);
  }
  const name = `${baseStem()}.dxf`;
  downloadBlob(await response.blob(), name);
  setHint(t("done.exportedDxf", { name }));
}

export async function openDocument() {
  if (typeof window.showOpenFilePicker === "function") {
    try {
      const [handle] = await window.showOpenFilePicker({
        types: [{
          description: "apeCAD JSON",
          accept: { "application/json": [".json"] },
        }],
        multiple: false,
      });
      if (!handle) return;
      const file = await handle.getFile();
      S.fileHandle = handle;
      await loadDocumentDict(documentFromFile(JSON.parse(await file.text())), file.name);
    } catch (error) {
      if (error && error.name === "AbortError") return;
      refuse(error);
    }
    return;
  }
  fileOpenEl.click();
}

function documentFromFile(parsed) {
  if (parsed && parsed.schema && Array.isArray(parsed.ops)) return parsed;
  if (parsed && (parsed.schema === "apeCAD.section-draft" || parsed.schema === "apeCAD.section-seed")) {
    return parsed;
  }
  if (parsed && parsed.document && parsed.document.schema) return parsed.document;
  throw new Error(t("reason.notDocument"));
}

async function loadDocumentDict(dict, name) {
  S.pending = null;
  ghosts.clear();
  S.selectedIds.clear();
  await refreshFrom(await api("/api/load", "POST", dict));
  if (name) S.saveName = name;
  const hasSection = (S.sceneState.concrete_faces || []).length > 0 || (S.sceneState.bars || []).length > 0;
  const has3D = (S.sceneState.solids || []).length > 0 || (S.sceneState.boxes || []).length > 0;
  if (hasSection && !has3D) {
    goNamedView("top");
  } else {
    S.namedView = null;
    viewUp.copy(WORLD_UP);
    bindProjectionCamera();
    lookAtScene(ISO_DIR, { up: WORLD_UP.clone() });
  }
  setHint(t("done.opened", { name: S.saveName }));
}

export async function newDocument() {
  S.pending = null;
  S.fileHandle = null;
  ghosts.clear();
  S.selectedIds.clear();
  await refreshFrom(await api("/api/reset", "POST", {}));
  S.saveName = "apecad.json";
  S.namedView = null;
  viewUp.copy(WORLD_UP);
  bindProjectionCamera();
  lookAtScene(ISO_DIR, { up: WORLD_UP.clone() });
  setHint(t("done.new"));
}

export async function undoDocument() {
  if (S.pending && S.pending.kind === "line" && S.pending.pts && S.pending.pts.length > 1) {
    // Mid-chain nothing is posted yet (ADR 0030): Ctrl+Z takes back the last vertex.
    S.pending.pts.pop();
    S.pending.a = S.pending.pts[S.pending.pts.length - 1];
    updateGhost(S.lastPointer);
    setHint(t("hint.line.vertexRemoved"));
    return;
  }
  S.pending = null;
  ghosts.clear();
  await refreshFrom(await api("/api/undo", "POST", {}));
}

export async function redoDocument() {
  await refreshFrom(await api("/api/redo", "POST", {}));
}

export function bindFileOpen() {
  fileOpenEl.addEventListener("change", async () => {
    const file = fileOpenEl.files && fileOpenEl.files[0];
    fileOpenEl.value = "";
    if (!file) return;
    try {
      S.fileHandle = null;
      await loadDocumentDict(documentFromFile(JSON.parse(await file.text())), file.name);
    } catch (error) {
      refuse(error);
    }
  });
}
