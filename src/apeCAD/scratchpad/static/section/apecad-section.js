// Embeddable 2-D Canvas section & rebar client (ADR 0026, stages C7 & C9).
// Zero CDN URLs, no innerHTML, no module-scope DOM access.

import { createViewport, hitTestSection, renderSectionCanvas } from "./canvas2d.js";
import { parseInput, snapPoint2D } from "./input-parse.js";
import { barDiameterMm, buildDraftFromScene, httpTransport, mockTransport, normalizeScene } from "./transport.js";

export const API_VERSION = 1;
export { httpTransport, mockTransport, parseInput, snapPoint2D };

const TOOLS = [
  ["select", "Select"], ["rect", "Rectangle"], ["polygon", "Polygon"], ["opening", "Opening"],
  ["wall-chain", "Wall chain"], ["wall-leg", "Wall leg"], ["cover", "Cover"],
  ["bar", "Bar"], ["bar-row", "Bar row"], ["bars-edge", "Edge bars"],
  ["hoop", "Hoop"], ["crosstie", "Crosstie"], ["delete", "Delete"],
];

function makeMockElement(tag) {
  const listeners = new Map();
  const children = [];
  const classSet = new Set();
  const el = {
    tagName: String(tag).toUpperCase(), className: "", textContent: "", value: "",
    type: "", placeholder: "", disabled: false, tabIndex: -1,
    width: 800, height: 600, clientWidth: 800, clientHeight: 600, style: {}, dataset: {}, children,
    classList: {
      add: (...c) => c.forEach((x) => classSet.add(x)),
      remove: (...c) => c.forEach((x) => classSet.delete(x)),
      toggle: (c, f) => (f === undefined ? (classSet.has(c) ? classSet.delete(c) : classSet.add(c)) : f ? classSet.add(c) : classSet.delete(c)),
      contains: (c) => classSet.has(c),
    },
    appendChild(child) { children.push(child); return child; },
    replaceChildren(...next) { children.length = 0; children.push(...next); },
    remove() {},
    addEventListener(type, fn) {
      if (!listeners.has(type)) listeners.set(type, []);
      listeners.get(type).push(fn);
    },
    removeEventListener(type, fn) {
      const arr = listeners.get(type);
      if (arr) { const i = arr.indexOf(fn); if (i >= 0) arr.splice(i, 1); }
    },
    dispatchEvent(evt) { for (const fn of (listeners.get(evt?.type) || []).slice()) fn(evt); },
    getBoundingClientRect: () => ({ left: 0, top: 0, width: el.clientWidth || 800, height: el.clientHeight || 600 }),
    getContext: () => ({
      save() {}, restore() {}, beginPath() {}, closePath() {}, moveTo() {}, lineTo() {},
      arc() {}, fill() {}, stroke() {}, fillRect() {}, strokeRect() {}, setLineDash() {},
    }),
  };
  return el;
}

function getDoc(container) {
  if (container?.ownerDocument && typeof container.ownerDocument.createElement === "function") return container.ownerDocument;
  if (typeof globalThis.document !== "undefined" && typeof globalThis.document.createElement === "function") return globalThis.document;
  return { createElement: (tag) => makeMockElement(tag) };
}

function el(doc, tag, className = "", text = "") {
  const node = doc.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

export function create(container, opts = {}) {
  if (!container || typeof container !== "object") {
    throw new Error("APECADSection.create requires a container element");
  }
  const doc = getDoc(container);
  const readOnly = Boolean(opts.readOnly);
  const onChange = typeof opts.onChange === "function" ? opts.onChange : null;
  const transport = typeof opts.transport === "function" ? opts.transport : mockTransport(opts.initialDraft || null);

  let scene = normalizeScene(null);
  let currentDraft = buildDraftFromScene(scene);
  let activeTool = "select";
  const selectedIds = new Set();
  let gesturePts = [];
  let gestureBarIds = [];
  let snapState = null;
  let ghostState = null;
  let panDrag = null;
  let disposed = false;
  let opEpoch = 0;

  const params = {
    b_mm: 400, h_mm: 600, thickness_mm: 250, cover_mm: 25, tie_diameter_mm: 10, bar_diameter_mm: 16,
    material: "concrete", designation: "Ø16", hoop_designation: "Ø10", spacing_mm: 150, count: 4,
    hooks: "135", crosstie_hooks: "135-135", gridStepMm: 50, gridSnap: true,
    ...(opts.params || {}),
  };

  if (container.tabIndex === undefined || container.tabIndex < 0) container.tabIndex = 0;

  const root = el(doc, "div", "apecad-section-root");
  const toolbar = el(doc, "div", "apecad-section-toolbar");
  const stage = el(doc, "div", "apecad-section-stage");
  const canvas = el(doc, "canvas", "apecad-section-canvas");
  const sidebar = el(doc, "div", "apecad-section-sidebar");
  const propsBox = el(doc, "div", "apecad-section-props");
  const warnBox = el(doc, "div", "apecad-section-warnings");
  const bottomBar = el(doc, "div", "apecad-section-bottom");
  const promptLabel = el(doc, "span", "apecad-section-prompt", "Ready");
  const cmdInput = el(doc, "input", "apecad-section-cmd");
  cmdInput.type = "text";
  cmdInput.placeholder = "x,y  @dx,dy  @r<deg  t 250  c  u";
  if (readOnly) cmdInput.disabled = true;
  const statusLabel = el(doc, "span", "apecad-section-status", "0 bars");

  const toolButtons = new Map();
  if (!readOnly) {
    for (const [id, label] of TOOLS) {
      const btn = el(doc, "button", "apecad-section-btn", label);
      btn.type = "button";
      btn.dataset.tool = id;
      btn.addEventListener("click", () => setTool(id));
      toolbar.appendChild(btn);
      toolButtons.set(id, btn);
    }
    const undoBtn = el(doc, "button", "apecad-section-btn", "Undo");
    undoBtn.type = "button";
    undoBtn.addEventListener("click", () => { void undo(); });
    const redoBtn = el(doc, "button", "apecad-section-btn", "Redo");
    redoBtn.type = "button";
    redoBtn.addEventListener("click", () => { void redo(); });
    toolbar.appendChild(undoBtn);
    toolbar.appendChild(redoBtn);
  }
  const fitBtn = el(doc, "button", "apecad-section-btn", "Fit");
  fitBtn.type = "button";
  fitBtn.addEventListener("click", () => fitView());
  toolbar.appendChild(fitBtn);

  stage.appendChild(canvas);
  sidebar.appendChild(propsBox);
  sidebar.appendChild(warnBox);
  stage.appendChild(sidebar);
  bottomBar.appendChild(promptLabel);
  bottomBar.appendChild(cmdInput);
  bottomBar.appendChild(statusLabel);
  root.appendChild(toolbar);
  root.appendChild(stage);
  root.appendChild(bottomBar);
  if (typeof container.appendChild === "function") container.appendChild(root);
  else if (Array.isArray(container.children)) container.children.push(root);
  else container.children = [root];

  const view = createViewport(canvas);

  function updateStatusAndProps() {
    const nFaces = (scene.concrete_faces || []).length;
    const nBars = (scene.bars || []).length;
    const nHoops = (scene.hoops || []).length;
    const nTies = (scene.crossties || []).length;
    const warns = scene.warnings || currentDraft?.warnings || [];
    statusLabel.textContent = `${nFaces} face · ${nBars} bar · ${nHoops} hoop · ${nTies} tie` + (warns.length ? ` · WARN ${warns.length}` : "");
    if (typeof warnBox.replaceChildren === "function") {
      warnBox.replaceChildren(...warns.map((w) => el(doc, "div", "apecad-section-warn-item", `[${w.code || "WARN"}] ${w.message || ""}`)));
    }
    const selId = selectedIds.values().next().value;
    let title = `Tool: ${activeTool} · Bar ${params.designation}`;
    if (selId != null) {
      const bar = (scene.bars || []).find((b) => b.id === selId);
      const face = (scene.concrete_faces || []).find((f) => f.id === selId);
      const hoop = (scene.hoops || []).find((h) => h.id === selId);
      const tie = (scene.crossties || []).find((t) => t.id === selId);
      const leg = (scene.wall_legs || []).find((l) => l.id === selId);
      if (bar) title = `Bar #${bar.id} (${bar.designation})`;
      else if (face) title = `Outline #${face.id} (${face.material})`;
      else if (hoop) title = `Hoop #${hoop.id} (${hoop.designation} @ ${hoop.spacing_mm})`;
      else if (tie) title = `Crosstie #${tie.id} (${tie.designation})`;
      else if (leg) title = `WallLeg #${leg.id} (t=${leg.thickness_mm} mm)`;
    }
    if (typeof propsBox.replaceChildren === "function") {
      propsBox.replaceChildren(el(doc, "div", "apecad-section-prop-title", title));
    }
  }

  function redraw() {
    if (disposed) return;
    renderSectionCanvas(canvas, view, {
      scene, selectedIds, snap: snapState, ghost: ghostState, gridOn: true, gridStepMm: params.gridStepMm,
    });
    updateStatusAndProps();
  }

  function syncResponse(res, emitChange) {
    if (!res || !res.ok) {
      promptLabel.textContent = res?.error?.message || "Operation refused";
      return res;
    }
    if (res.scene) scene = normalizeScene(res.scene);
    currentDraft = res.draft || buildDraftFromScene(scene, res.document);
    if (res.warnings && !scene.warnings?.length) scene.warnings = res.warnings;
    redraw();
    if (emitChange && onChange && currentDraft) onChange(currentDraft);
    return res;
  }

  async function applyOp(opOrOps) {
    if (readOnly) return { ok: false, status: 422, error: { code: "READ_ONLY", message: "Editor is read-only" } };
    opEpoch += 1;
    const list = Array.isArray(opOrOps) ? opOrOps : [opOrOps];
    let lastRes = null;
    for (const op of list) {
      lastRes = await transport({ action: "apply", op });
      if (!lastRes || !lastRes.ok) return syncResponse(lastRes, false);
    }
    return syncResponse(lastRes, true);
  }

  async function undo() {
    if (readOnly) return { ok: false, status: 422, error: { code: "READ_ONLY", message: "Editor is read-only" } };
    if (gesturePts.length > 0) {
      gesturePts.pop();
      updateGhost(gesturePts[gesturePts.length - 1] || null);
      redraw();
      return { ok: true, status: 200, gesture_undo: true };
    }
    opEpoch += 1;
    const res = await transport({ action: "undo" });
    return syncResponse(res, Boolean(res && res.ok));
  }

  async function redo() {
    if (readOnly) return { ok: false, status: 422, error: { code: "READ_ONLY", message: "Editor is read-only" } };
    opEpoch += 1;
    const res = await transport({ action: "redo" });
    return syncResponse(res, Boolean(res && res.ok));
  }

  async function loadDraft(payload) {
    opEpoch += 1;
    const out = syncResponse(await transport({ action: "load", payload }), false);
    if (out && out.ok) view.fit(scene);
    redraw();
    return out;
  }

  async function loadSeed(seedPayload) {
    opEpoch += 1;
    const out = syncResponse(await transport({ action: "seed", payload: seedPayload }), false);
    if (out && out.ok) view.fit(scene);
    redraw();
    return out;
  }

  function setTool(toolName) {
    if (readOnly && toolName !== "select") return;
    activeTool = toolName || "select";
    gesturePts = [];
    gestureBarIds = [];
    ghostState = null;
    for (const [id, btn] of toolButtons.entries()) btn.classList.toggle("active", id === activeTool);
    promptLabel.textContent = `Tool: ${activeTool}`;
    redraw();
  }

  function setParam(key, value) { params[key] = value; redraw(); }
  function fitView() { view.fit(scene); redraw(); }
  function resize() { view.resize(); redraw(); }

  function updateGhost(cursorWorld) {
    if (!cursorWorld) { ghostState = null; return; }
    if (activeTool === "rect" && gesturePts.length === 1) {
      const [x0, y0] = gesturePts[0], [x1, y1] = cursorWorld;
      ghostState = { ring: [[x0, y0], [x1, y0], [x1, y1], [x0, y1]] };
    } else if ((activeTool === "polygon" || activeTool === "opening") && gesturePts.length >= 1) {
      ghostState = { ring: [...gesturePts, cursorWorld] };
    } else if ((activeTool === "wall-chain" || activeTool === "wall-leg") && gesturePts.length >= 1) {
      ghostState = { polyline: [...gesturePts, cursorWorld] };
    } else if (activeTool === "bar") {
      ghostState = { bars: [{ centre: cursorWorld, diameter_mm: barDiameterMm(params.designation) }] };
    } else if (activeTool === "bar-row" && gesturePts.length === 1) {
      const [x0, y0] = gesturePts[0], [x1, y1] = cursorWorld;
      const n = Math.max(2, Number(params.count || 4)), d = barDiameterMm(params.designation), bars = [];
      for (let i = 0; i < n; i++) {
        const t = i / (n - 1);
        bars.push({ centre: [x0 + (x1 - x0) * t, y0 + (y1 - y0) * t], diameter_mm: d });
      }
      ghostState = { polyline: [[x0, y0], [x1, y1]], bars };
    } else {
      ghostState = null;
    }
  }

  async function commitPolygonOrChain() {
    if ((activeTool === "polygon" || activeTool === "opening") && gesturePts.length >= 3) {
      const pts = gesturePts.slice();
      gesturePts = [];
      ghostState = null;
      if (activeTool === "opening") {
        const faceId = scene.concrete_faces[0]?.id;
        if (faceId != null) await applyOp({ op: "AddOpening", face_id: faceId, polygon: pts });
      } else {
        await applyOp({ op: "AddSectionOutline", point_ids: pts.map((p) => ({ xyz: [p[0], p[1], 0] })), material: String(params.material || "concrete") });
      }
    } else if (activeTool === "wall-chain" && gesturePts.length >= 2) {
      const pts = gesturePts.slice();
      gesturePts = [];
      ghostState = null;
      await applyOp({ op: "AddWallChain", point_ids: pts.map((p) => ({ xyz: [p[0], p[1], 0] })), thickness_mm: [Number(params.thickness_mm || 250)], material: String(params.material || "concrete") });
    } else if (activeTool === "hoop" && gestureBarIds.length >= 3) {
      const ids = gestureBarIds.slice();
      gestureBarIds = [];
      await applyOp({ op: "AddHoop", bar_ids: ids, designation: String(params.hoop_designation || "Ø10"), spacing_mm: Number(params.spacing_mm || 100), hooks: String(params.hooks || "135") });
    }
  }

  async function handlePointInput(pt, hit = null) {
    if (readOnly) return;
    if (activeTool === "select") {
      selectedIds.clear();
      if (hit && hit.id != null) selectedIds.add(hit.id);
      redraw();
    } else if (activeTool === "delete") {
      const id = hit?.id ?? selectedIds.values().next().value;
      if (id != null) { selectedIds.delete(id); await applyOp({ op: "Delete", entity_ids: [id] }); }
    } else if (activeTool === "rect") {
      gesturePts.push(pt);
      if (gesturePts.length >= 2) {
        const [p0, p1] = gesturePts;
        gesturePts = [];
        ghostState = null;
        const x0 = Math.min(p0[0], p1[0]), x1 = Math.max(p0[0], p1[0]);
        const y0 = Math.min(p0[1], p1[1]), y1 = Math.max(p0[1], p1[1]);
        if (x1 > x0 && y1 > y0) {
          await applyOp({ op: "AddSectionOutline", point_ids: [{ xyz: [x0, y0, 0] }, { xyz: [x1, y0, 0] }, { xyz: [x1, y1, 0] }, { xyz: [x0, y1, 0] }], material: String(params.material || "concrete") });
        }
      }
      redraw();
    } else if (activeTool === "polygon" || activeTool === "opening" || activeTool === "wall-chain") {
      gesturePts.push(pt);
      redraw();
    } else if (activeTool === "wall-leg") {
      gesturePts.push(pt);
      if (gesturePts.length >= 2) {
        const [s, e] = gesturePts;
        gesturePts = [];
        ghostState = null;
        const faceId = scene.concrete_faces[0]?.id;
        if (faceId != null) {
          await applyOp({ op: "AddWallLeg", face_id: faceId, start_id: { xyz: [s[0], s[1], 0] }, end_id: { xyz: [e[0], e[1], 0] }, thickness_mm: Number(params.thickness_mm || 250) });
        } else {
          await applyOp({ op: "AddWallChain", point_ids: [{ xyz: [s[0], s[1], 0] }, { xyz: [e[0], e[1], 0] }], thickness_mm: [Number(params.thickness_mm || 250)], material: String(params.material || "concrete") });
        }
      }
      redraw();
    } else if (activeTool === "cover") {
      const faceId = hit?.kind === "ConcreteFace" ? hit.id : scene.concrete_faces[0]?.id;
      if (faceId != null) {
        await applyOp({ op: "SetCover", face_id: faceId, cover_mm: Number(params.cover_mm || 25), tie_diameter_mm: Number(params.tie_diameter_mm || 10), bar_diameter_mm: Number(params.bar_diameter_mm || 16) });
      }
    } else if (activeTool === "bar") {
      await applyOp({ op: "AddBar", x_mm: pt[0], y_mm: pt[1], designation: String(params.designation || "Ø16") });
    } else if (activeTool === "bar-row") {
      gesturePts.push(pt);
      if (gesturePts.length >= 2) {
        const [p0, p1] = gesturePts;
        gesturePts = [];
        ghostState = null;
        await applyOp({ op: "AddBarRow", start_x_mm: p0[0], start_y_mm: p0[1], end_x_mm: p1[0], end_y_mm: p1[1], designation: String(params.designation || "Ø16"), count: Number(params.count || 4) });
      }
      redraw();
    } else if (activeTool === "bars-edge") {
      const faceId = hit?.target_id ?? (hit?.kind === "ConcreteFace" ? hit.id : scene.concrete_faces[0]?.id);
      const edgeIdx = hit?.edge_index ?? snapState?.edge_index ?? 0;
      if (faceId != null) {
        await applyOp({ op: "AddBarsAlongEdge", face_id: faceId, edge_index: Number(edgeIdx), designation: String(params.designation || "Ø16"), count: Number(params.count || 4) });
      }
    } else if (activeTool === "hoop") {
      const barId = hit?.kind === "Bar" ? hit.id : snapState?.kind === "bar" ? snapState.id : null;
      if (barId != null) {
        if (gestureBarIds.length >= 3 && gestureBarIds[0] === barId) await commitPolygonOrChain();
        else if (!gestureBarIds.includes(barId)) gestureBarIds.push(barId);
      }
      redraw();
    } else if (activeTool === "crosstie") {
      const barId = hit?.kind === "Bar" ? hit.id : snapState?.kind === "bar" ? snapState.id : null;
      if (barId != null && !gestureBarIds.includes(barId)) {
        gestureBarIds.push(barId);
        if (gestureBarIds.length >= 2) {
          const [a, b] = gestureBarIds;
          gestureBarIds = [];
          await applyOp({ op: "AddCrosstie", bar_a_id: a, bar_b_id: b, designation: String(params.hoop_designation || "Ø10"), spacing_mm: Number(params.spacing_mm || 100), hooks: String(params.crosstie_hooks || "135-135") });
        }
      }
      redraw();
    }
  }

  function canvasCoords(evt) {
    const rect = canvas.getBoundingClientRect ? canvas.getBoundingClientRect() : { left: 0, top: 0 };
    return [(evt.clientX ?? evt.offsetX ?? 0) - rect.left, (evt.clientY ?? evt.offsetY ?? 0) - rect.top];
  }

  const onMouseMove = (evt) => {
    const sp = canvasCoords(evt);
    if (panDrag) { view.panBy(sp[0] - panDrag[0], sp[1] - panDrag[1]); panDrag = sp; redraw(); return; }
    const wp = view.screenToWorld(sp);
    snapState = snapPoint2D(sp, wp, view, scene, { gridStepMm: params.gridStepMm, gridSnap: params.gridSnap });
    updateGhost(snapState.point);
    redraw();
  };

  const onMouseDown = (evt) => {
    if (evt.button === 1 || (evt.button === 0 && evt.altKey)) { panDrag = canvasCoords(evt); return; }
    if (evt.button !== 0) return;
    const sp = canvasCoords(evt), wp = view.screenToWorld(sp);
    snapState = snapPoint2D(sp, wp, view, scene, { gridStepMm: params.gridStepMm, gridSnap: params.gridSnap });
    void handlePointInput(snapState.point, hitTestSection(sp, view, scene));
  };

  const onMouseUp = () => { panDrag = null; };
  const onWheel = (evt) => {
    if (typeof evt.preventDefault === "function") evt.preventDefault();
    view.zoomAt(canvasCoords(evt), (evt.deltaY || 0) < 0 ? 1.12 : 1 / 1.12);
    redraw();
  };

  const onKeyDown = (evt) => {
    if (disposed) return;
    const key = evt.key || "";
    if ((evt.ctrlKey || evt.metaKey) && key.toLowerCase() === "z") {
      if (typeof evt.preventDefault === "function") evt.preventDefault();
      if (evt.shiftKey) void redo(); else void undo();
    } else if ((evt.ctrlKey || evt.metaKey) && key.toLowerCase() === "y") {
      if (typeof evt.preventDefault === "function") evt.preventDefault();
      void redo();
    } else if (key === "Escape") {
      gesturePts = []; gestureBarIds = []; ghostState = null; redraw();
    } else if (key === "Enter" && evt.target !== cmdInput) {
      void commitPolygonOrChain();
    } else if ((key === "Delete" || key === "Backspace") && evt.target !== cmdInput && !readOnly) {
      const ids = Array.from(selectedIds);
      if (ids.length) { selectedIds.clear(); void applyOp({ op: "Delete", entity_ids: ids }); }
    }
  };

  const onCmdKeyDown = (evt) => {
    if (evt.key !== "Enter") return;
    const raw = cmdInput.value;
    cmdInput.value = "";
    const parsed = parseInput(raw, gesturePts[gesturePts.length - 1] || null, null);
    if (parsed.kind === "command") {
      if (parsed.command === "close") void commitPolygonOrChain();
      else if (parsed.command === "undo") void undo();
    } else if (parsed.kind === "thickness") {
      params.thickness_mm = parsed.thickness_mm;
      promptLabel.textContent = `Thickness = ${parsed.thickness_mm} mm`;
      redraw();
    } else if (parsed.kind === "point") {
      void handlePointInput(parsed.point, null);
    } else if (parsed.kind === "error") {
      promptLabel.textContent = parsed.message;
    }
  };

  canvas.addEventListener("mousemove", onMouseMove);
  canvas.addEventListener("mousedown", onMouseDown);
  canvas.addEventListener("mouseup", onMouseUp);
  canvas.addEventListener("wheel", onWheel);
  cmdInput.addEventListener("keydown", onCmdKeyDown);
  if (typeof container.addEventListener === "function") container.addEventListener("keydown", onKeyDown);

  setTool("select");
  if (opts.initialDraft && typeof opts.transport === "function") {
    void loadDraft(opts.initialDraft);
  } else {
    const initEpoch = opEpoch;
    void transport({ action: "scene" }).then((res) => {
      if (opEpoch === initEpoch && !disposed && res && res.ok) syncResponse(res, false);
    });
  }

  return {
    loadDraft, load: loadDraft, loadSeed,
    getDraft: () => currentDraft, getScene: () => scene,
    applyOp, undo, redo, setTool, setParam, fitView, resize,
    dispose() {
      disposed = true;
      canvas.removeEventListener("mousemove", onMouseMove);
      canvas.removeEventListener("mousedown", onMouseDown);
      canvas.removeEventListener("mouseup", onMouseUp);
      canvas.removeEventListener("wheel", onWheel);
      cmdInput.removeEventListener("keydown", onCmdKeyDown);
      if (typeof container.removeEventListener === "function") container.removeEventListener("keydown", onKeyDown);
      if (typeof root.remove === "function") root.remove();
    },
  };
}

export const APECADSection = { API_VERSION, create, httpTransport, mockTransport };
if (typeof globalThis !== "undefined") globalThis.APECADSection = APECADSection;
