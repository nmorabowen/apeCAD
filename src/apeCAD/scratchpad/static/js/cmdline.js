// The command line and status bar: prompt/hint and log, the typed length buffer, toggle
// buttons, and the cursor coordinate readout.
import { S } from "./state.js";
import { notifySelectionChanged, requestRender, store } from "./store.js";
import { refusalText, t } from "./strings.js";
import { dist3 } from "./geom.js";
import { grid, gridMajorMm, gridMinorMm } from "./grid.js";
import {
  GRID_MAX_MM,
  GRID_MIN_MM,
  displayUnit,
  formatGridInput,
  formatLength,
  formatNumber,
  gridAutoOn,
  gridDotSize,
  gridLineWidth,
  gridMinorStyle,
  hiddenLineScale,
  mmToUnit,
  parseLength,
} from "./prefs.js";
import { UNIT_STEP, formatDeg } from "./units.js";

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
  if (kind === "refused" || kind === "warn") line.className = "refused";
  line.textContent = text;
  consoleLog.appendChild(line);
  while (consoleLog.childElementCount > 80) consoleLog.removeChild(consoleLog.firstChild);
  consoleLog.scrollTop = consoleLog.scrollHeight;
}

export function logWarnings(warnings) {
  const nextKeys = new Set();
  for (const w of warnings || []) {
    const key = `${w.code}:${(w.ids || []).join(",")}:${w.message}`;
    nextKeys.add(key);
    if (!S.seenWarnings.has(key)) {
      const msg = String(w.message || "").trim().replace(/\.+$/, "");
      appendLog(t("warn.prefix", { message: msg }), "warn");
    }
  }
  S.seenWarnings = nextKeys;
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

export function syncGridMenu() {
  const minorOnEl = document.getElementById("grid-minor-on");
  if (minorOnEl) minorOnEl.checked = S.gridMinorOn;
}

export function syncGridPrefsForm() {
  const showEl = document.getElementById("gpref-show");
  if (!showEl) return;
  showEl.checked = S.gridOn;
  document.getElementById("gpref-minor-on").checked = S.gridMinorOn;
  document.getElementById("gpref-snap").checked = S.gridSnapOn;
  const autoEl = document.getElementById("gpref-auto");
  if (autoEl) autoEl.checked = gridAutoOn();
  const styleEl = document.getElementById("gpref-minor-style");
  if (styleEl && document.activeElement !== styleEl) styleEl.value = gridMinorStyle();
  const unitEl = document.getElementById("gpref-unit");
  if (unitEl && document.activeElement !== unitEl) unitEl.value = displayUnit();
  const dots = gridMinorStyle() === "dots";
  const dotOpts = document.getElementById("gpref-dot-opts");
  const lineOpts = document.getElementById("gpref-line-opts");
  if (dotOpts) dotOpts.hidden = !dots;
  if (lineOpts) lineOpts.hidden = dots;
  const unit = displayUnit();
  const step = UNIT_STEP[unit];
  const min = mmToUnit(GRID_MIN_MM);
  const max = mmToUnit(GRID_MAX_MM);
  const minorEl = document.getElementById("gpref-minor");
  const majorEl = document.getElementById("gpref-major");
  for (const el of [minorEl, majorEl]) {
    el.min = String(min);
    el.max = String(max);
    el.step = String(step);
    el.disabled = gridAutoOn();
  }
  if (document.activeElement !== minorEl) minorEl.value = formatGridInput(gridMinorMm());
  if (document.activeElement !== majorEl) majorEl.value = formatGridInput(gridMajorMm());
  const scaleEl = document.getElementById("gpref-hidden-scale");
  const scaleNum = document.getElementById("gpref-hidden-scale-num");
  const scale = hiddenLineScale();
  if (document.activeElement !== scaleEl) scaleEl.value = String(scale);
  if (document.activeElement !== scaleNum) scaleNum.value = String(scale);
  const dotEl = document.getElementById("gpref-dot-size");
  const dotNum = document.getElementById("gpref-dot-size-num");
  const size = gridDotSize();
  if (dotEl && document.activeElement !== dotEl) dotEl.value = String(size);
  if (dotNum && document.activeElement !== dotNum) dotNum.value = String(size);
  const widthEl = document.getElementById("gpref-line-width");
  const widthNum = document.getElementById("gpref-line-width-num");
  const width = gridLineWidth();
  if (widthEl && document.activeElement !== widthEl) widthEl.value = String(width);
  if (widthNum && document.activeElement !== widthNum) widthNum.value = String(width);
  for (const button of document.querySelectorAll("[data-grid-minor]")) {
    button.textContent = `${formatGridInput(Number(button.dataset.gridMinor))} / ${formatGridInput(Number(button.dataset.gridMajor))}`;
  }
  const placeholder = document.getElementById("console-input");
  if (placeholder) placeholder.placeholder = t("grid.placeholder", { unit });
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
  const warnings = S.sceneState.warnings || [];
  if (warnings.length > 0) {
    chips.push([t("chip.warn", { n: warnings.length }), "warn"]);
  }
  const typed = activeLength();
  if (typed !== null) chips.push([formatLength(typed), true]);
  status.replaceChildren(...chips.map(([text, state]) => {
    const chip = document.createElement("span");
    chip.className = state === "warn" ? "chip warn" : state ? "chip on" : "chip";
    chip.textContent = text;
    if (state === "warn") {
      chip.title = warnings.map((w) => w.message).join("\n");
      const warnIds = [];
      for (const w of warnings) {
        for (const id of w.ids || []) warnIds.push(id);
      }
      if (warnIds.length > 0) {
        chip.addEventListener("pointerenter", () => {
          store.dispatch({ type: "hover/set", ids: warnIds });
          notifySelectionChanged();
        });
        chip.addEventListener("pointerleave", () => {
          store.dispatch({ type: "hover/clear" });
          notifySelectionChanged();
        });
      }
    }
    return chip;
  }));
  if (grid) grid.visible = S.gridOn;
  syncGridMenu();
  syncGridPrefsForm();
  requestRender();
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
