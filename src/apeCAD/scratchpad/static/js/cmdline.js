// The command line and status bar: prompt/hint and log, the typed length buffer, toggle
// buttons, and the cursor coordinate readout.
import { S } from "./state.js";
import { refusalText, t } from "./strings.js";
import { dist3 } from "./geom.js";
import { syncGridMenu, syncGridPrefsForm } from "./grid-ui.js";
import { grid, gridMajorMm, gridMinorMm } from "./grid.js";
import { displayUnit, formatLength, formatNumber, parseLength } from "./prefs.js";
import { formatDeg } from "./units.js";

const status = document.getElementById("status");
const labelInput = document.getElementById("label");
const consoleLog = document.getElementById("console-log");
export const consolePrompt = document.getElementById("console-prompt");
export const consoleInput = document.getElementById("console-input");
export const snapButton = document.getElementById("snap");
export const gridSnapButton = document.getElementById("grid-snap");
export const orthoButton = document.getElementById("ortho");
export const gridButton = document.getElementById("grid");
const coordsEl = document.getElementById("coords");
const dimsEl = document.getElementById("dims");

// `kind` "refused" marks a refusal (ADR 0031 §2.6); it stays on the line when it moves to the log.
export function setHint(text, kind = "hint") {
  const idle = t("prompt.idle");
  const next = text && text.trim() !== "" ? text : idle;
  const previous = consolePrompt.textContent;
  if (previous && previous !== next && previous !== idle) {
    appendLog(previous, consolePrompt.classList.contains("refused") ? "refused" : "hint");
  }
  consolePrompt.textContent = next;
  consolePrompt.title = next;
  consolePrompt.classList.toggle("refused", kind === "refused" && next !== idle);
}

// Show a refused op or client check as `Refused: <reason>.`; takes an Error or a message.
export function refuse(reason) {
  setHint(refusalText(reason instanceof Error ? reason.message : reason), "refused");
}

export function appendLog(text, kind = "hint") {
  if (!text) return;
  const last = consoleLog.lastElementChild;
  if (last && last.textContent === text) {
    consoleLog.scrollTop = consoleLog.scrollHeight;
    return;
  }
  const line = document.createElement("div");
  if (kind === "refused") line.className = "refused";
  line.textContent = text;
  consoleLog.appendChild(line);
  while (consoleLog.childElementCount > 80) consoleLog.removeChild(consoleLog.firstChild);
  consoleLog.scrollTop = consoleLog.scrollHeight;
}

export function typedText() {
  return consoleInput.value.trim();
}

export function clearTyped() {
  consoleInput.value = "";
}

export function setTyped(value) {
  consoleInput.value = value;
}

export function isTypingField(event) {
  if (event.target === consoleInput) return false;
  const tag = event.target && event.target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  return Boolean(event.target && event.target.closest && event.target.closest("dialog"));
}

export function refreshToggles() {
  snapButton.classList.toggle("active", S.snapOn);
  gridSnapButton.classList.toggle("active", S.gridSnapOn);
  orthoButton.classList.toggle("active", S.orthoOn);
  gridButton.classList.toggle("active", S.gridOn);
  // Mode chips (ADR 0031 §1.6): every mode shows, steel when on and muted when off.
  const chips = [
    [t("chip.snap"), S.snapOn],
    [t("chip.gridSnap", {
      minor: formatNumber(gridMinorMm()), major: formatNumber(gridMajorMm()), unit: displayUnit(),
    }), S.gridSnapOn],
    [t("chip.ortho"), S.orthoOn],
    [t("chip.grid"), S.gridOn],
  ];
  if (S.tool === "select") {
    chips.push([t("chip.filter", { filter: t(`filter.${S.selectFilter || "element"}`) }), true]);
  }
  const typed = activeLength();
  if (typed !== null) chips.push([formatLength(typed), true]);
  status.replaceChildren(...chips.map(([text, on]) => {
    const chip = document.createElement("span");
    chip.className = on ? "chip on" : "chip";
    chip.textContent = text;
    return chip;
  }));
  grid.visible = S.gridOn;
  syncGridMenu();
  syncGridPrefsForm();
}

export function labelValue() {
  const value = labelInput.value.trim();
  return value === "" ? null : value;
}

function fieldLength() {
  return parseLength(typedText());
}

export function activeLength() {
  return fieldLength();
}

export function bufferLength() {
  return fieldLength();
}

export function sidesValue() {
  return 6;
}

export function arrayCount() {
  return 4;
}

export function projectDims() {
  dimsEl.innerHTML = "";
}

export function setCoords(hit, origin) {
  if (!hit) {
    coordsEl.textContent = `X 0   Y 0   Z 0   ${displayUnit()}`;
    return;
  }
  const x = formatNumber(hit.x_mm);
  const y = formatNumber(hit.y_mm);
  const z = formatNumber(hit.z_mm || 0);
  let text = `X ${x}   Y ${y}   Z ${z}   ${displayUnit()}`;
  if (origin) {
    const dx = hit.x_mm - origin.x_mm;
    const dy = hit.y_mm - origin.y_mm;
    const length = dist3(origin, hit);
    const ang = Math.atan2(dy, dx);
    text += `    ΔX ${formatNumber(dx)}   ΔY ${formatNumber(dy)}    L ${formatLength(length)}    ${formatDeg(ang)}`;
  }
  coordsEl.textContent = text;
}
