// Document file actions: new, open, save, undo / redo against the server document.
import { S } from "./state.js";
import { t } from "./strings.js";
import { api } from "./api.js";
import { bindProjectionCamera, lookAtScene } from "./camera.js";
import { refuse, setHint } from "./cmdline.js";
import { updateGhost } from "./ghosts.js";
import { refreshFrom } from "./render.js";
import { ISO_DIR, WORLD_UP, ghosts, viewUp } from "./viewport.js";

export async function reload() {
  await refreshFrom(await api("/api/scene"));
  lookAtScene(ISO_DIR, { up: WORLD_UP.clone() });
}

const fileOpenEl = document.getElementById("file-open");

function downloadJson(filename) {
  const blob = new Blob([JSON.stringify(S.sceneState.document, null, 2)], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  URL.revokeObjectURL(link.href);
}

export function saveDocument(saveAs = false) {
  if (saveAs) {
    const next = window.prompt(t("menu.saveAsPrompt"), S.saveName) || "";
    if (!next.trim()) return;
    S.saveName = next.trim().endsWith(".json") ? next.trim() : `${next.trim()}.json`;
  }
  downloadJson(S.saveName);
  setHint(t("done.saved", { name: S.saveName }));
}

export function openDocument() {
  fileOpenEl.click();
}

function documentFromFile(parsed) {
  if (parsed && parsed.schema && Array.isArray(parsed.ops)) return parsed;
  if (parsed && parsed.document && parsed.document.schema) return parsed.document;
  throw new Error(t("reason.notDocument"));
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
  setHint(t("done.opened", { name: S.saveName }));
}

export async function newDocument() {
  S.pending = null;
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
      await loadDocumentDict(documentFromFile(JSON.parse(await file.text())), file.name);
    } catch (error) {
      refuse(error);
    }
  });
}
