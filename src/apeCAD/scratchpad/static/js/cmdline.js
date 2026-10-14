// The command line and status bar: prompt/hint and log, the typed length buffer, toggle
// buttons, and the cursor coordinate readout.
import { S } from "./state.js";
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

export function setHint(text) {
  const next = text && text.trim() !== "" ? text : "Command:";
  const previous = consolePrompt.textContent;
  if (previous && previous !== next && previous !== "Command:") {
    appendLog(previous);
  }
  consolePrompt.textContent = next;
  consolePrompt.title = next;
}

export function appendLog(text) {
  if (!text) return;
  const last = consoleLog.lastElementChild;
  if (last && last.textContent === text) {
    consoleLog.scrollTop = consoleLog.scrollHeight;
    return;
  }
  const line = document.createElement("div");
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
  const parts = [];
  if (S.snapOn) parts.push("SNAP");
  if (S.gridSnapOn) parts.push(`GRIDSNAP ${formatNumber(gridMinorMm())}/${formatNumber(gridMajorMm())}`);
  if (S.orthoOn) parts.push("ORTHO");
  if (S.gridOn) parts.push("GRID");
  if (S.tool === "select") {
    const names = {
      point: "POINT", line: "LINE", face: "FACE", solid: "SOLID", element: "ELEMENT", section: "SECTION",
    };
    parts.push(names[S.selectFilter] || "ELEMENT");
  }
  const typed = activeLength();
  if (typed !== null) parts.push(formatLength(typed));
  status.textContent = parts.join(" · ") || "free";
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
