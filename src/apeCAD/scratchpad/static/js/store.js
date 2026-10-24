// Pure state reducer, observable Store, two-signature microtask reconciler, and
// dirty-flagged render wake (ADR 0035). Ported from apeGmshViewer's state.ts +
// reconciler.ts and synchronized with the shared mutable `S` facade in state.js.

import { S } from "./state.js";

function isValidId(id) {
  return (typeof id === "number" && Number.isFinite(id)) || (typeof id === "string" && id.length > 0);
}

function toIdSet(iter) {
  const out = new Set();
  if (!iter) return out;
  for (const id of iter) {
    if (isValidId(id)) out.add(id);
  }
  return out;
}

export function setsEqual(a, b) {
  if (a === b) return true;
  if (!a || !b || a.size !== b.size) return false;
  for (const v of a) {
    if (!b.has(v)) return false;
  }
  return true;
}

function sortedJoin(set) {
  if (!set || set.size === 0) return "";
  return [...set].map(String).sort().join(",");
}

export function initialStoreState(seed = {}) {
  return {
    revision: seed.revision ?? 0,
    sceneState: seed.sceneState ?? S.sceneState,
    selectedIds: toIdSet(seed.selectedIds ?? S.selectedIds),
    hoverIds: toIdSet(seed.hoverIds ?? S.hoverIds),
    selectFilter: seed.selectFilter ?? S.selectFilter ?? "element",
    hiddenIds: toIdSet(seed.hiddenIds ?? S.hiddenIds),
    cutterIds: toIdSet(seed.cutterIds ?? S.cutterIds),
    tool: seed.tool ?? S.tool ?? "select",
    pending: seed.pending ?? S.pending ?? null,
    useOrtho: seed.useOrtho ?? S.useOrtho ?? true,
    projection: seed.projection ?? S.projection ?? "parallel",
    namedView: seed.namedView ?? S.namedView ?? null,
    viewCubeOn: seed.viewCubeOn ?? S.viewCubeOn ?? true,
    gridOn: seed.gridOn ?? S.gridOn ?? true,
    gridMinorOn: seed.gridMinorOn ?? S.gridMinorOn ?? true,
    committedDimsCount: seed.committedDimsCount ?? (S.committedDims ? S.committedDims.length : 0),
    theme: seed.theme ?? S.theme ?? "light",
    canvas: seed.canvas ?? S.canvas ?? "theme",
    vizVersion: seed.vizVersion ?? S.vizVersion ?? 0,
  };
}

// Pure reducer: never mutates `state`; returns the identical `state` reference when
// an action produces no state change so subscribers can short-circuit on `===`.
export function reduce(state, action) {
  if (!action || typeof action.type !== "string") return state;
  switch (action.type) {
    case "scene/set": {
      const nextScene = action.sceneState ?? state.sceneState;
      const nextRev = typeof action.revision === "number"
        ? action.revision
        : (nextScene !== state.sceneState ? state.revision + 1 : state.revision);
      if (nextScene === state.sceneState && nextRev === state.revision) return state;
      return { ...state, sceneState: nextScene, revision: nextRev };
    }
    case "selection/set": {
      const next = toIdSet(action.ids);
      if (setsEqual(next, state.selectedIds)) return state;
      return { ...state, selectedIds: next };
    }
    case "selection/toggle": {
      const id = action.id;
      if (!isValidId(id)) return state;
      const next = new Set(state.selectedIds);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return { ...state, selectedIds: next };
    }
    case "selection/clear": {
      if (state.selectedIds.size === 0) return state;
      return { ...state, selectedIds: new Set() };
    }
    case "hover/set": {
      const next = toIdSet(action.ids);
      if (setsEqual(next, state.hoverIds)) return state;
      return { ...state, hoverIds: next };
    }
    case "hover/clear": {
      if (state.hoverIds.size === 0) return state;
      return { ...state, hoverIds: new Set() };
    }
    case "filter/set": {
      const f = action.filter;
      if (!f || f === state.selectFilter) return state;
      return { ...state, selectFilter: f };
    }
    case "hidden/set": {
      const next = toIdSet(action.ids);
      if (setsEqual(next, state.hiddenIds)) return state;
      return { ...state, hiddenIds: next };
    }
    case "hidden/toggle": {
      const id = action.id;
      if (!isValidId(id)) return state;
      const next = new Set(state.hiddenIds);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return { ...state, hiddenIds: next };
    }
    case "hidden/clear": {
      if (state.hiddenIds.size === 0) return state;
      return { ...state, hiddenIds: new Set() };
    }
    case "cutter/set": {
      const next = toIdSet(action.ids);
      if (setsEqual(next, state.cutterIds)) return state;
      return { ...state, cutterIds: next };
    }
    case "tool/set": {
      const nextTool = action.tool ?? state.tool;
      const nextPending = "pending" in action ? action.pending : null;
      if (nextTool === state.tool && nextPending === state.pending) return state;
      return { ...state, tool: nextTool, pending: nextPending };
    }
    case "pending/set": {
      const nextPending = action.pending ?? null;
      if (nextPending === state.pending) return state;
      return { ...state, pending: nextPending };
    }
    case "view/set": {
      const useOrtho = action.useOrtho ?? state.useOrtho;
      const projection = action.projection ?? state.projection;
      const namedView = "namedView" in action ? action.namedView : state.namedView;
      const viewCubeOn = action.viewCubeOn ?? state.viewCubeOn;
      if (
        useOrtho === state.useOrtho &&
        projection === state.projection &&
        namedView === state.namedView &&
        viewCubeOn === state.viewCubeOn
      ) {
        return state;
      }
      return { ...state, useOrtho, projection, namedView, viewCubeOn };
    }
    case "grid/set": {
      const gridOn = action.gridOn ?? state.gridOn;
      const gridMinorOn = action.gridMinorOn ?? state.gridMinorOn;
      if (gridOn === state.gridOn && gridMinorOn === state.gridMinorOn) return state;
      return { ...state, gridOn, gridMinorOn };
    }
    case "theme/set": {
      const theme = action.theme ?? state.theme;
      const canvas = action.canvas ?? state.canvas;
      if (theme === state.theme && canvas === state.canvas) return state;
      return { ...state, theme, canvas };
    }
    case "prefs/bump": {
      return { ...state, vizVersion: state.vizVersion + 1 };
    }
    case "dims/set": {
      const count = typeof action.committedDimsCount === "number"
        ? action.committedDimsCount
        : state.committedDimsCount;
      if (count === state.committedDimsCount) return state;
      return { ...state, committedDimsCount: count };
    }
    default:
      return state;
  }
}

export function geometrySignature(state) {
  return JSON.stringify({
    rev: state.revision,
    hidden: sortedJoin(state.hiddenIds),
    cutter: sortedJoin(state.cutterIds),
    dims: state.committedDimsCount,
    theme: state.theme,
    canvas: state.canvas,
    viz: state.vizVersion,
    grid: state.gridOn ? (state.gridMinorOn ? 2 : 1) : 0,
  });
}

export function selectionSignature(state) {
  return JSON.stringify({
    sel: sortedJoin(state.selectedIds),
    hov: sortedJoin(state.hoverIds),
    flt: state.selectFilter,
  });
}

export class Store {
  constructor(initial = initialStoreState(), { syncS = false } = {}) {
    this._state = initial;
    this._listeners = new Set();
    this._syncS = syncS;
  }

  get() {
    return this._state;
  }

  dispatch(action) {
    const prev = this._state;
    const next = reduce(prev, action);
    if (next === prev) return prev;
    this._state = next;
    if (this._syncS) applyStoreToS(next, prev);
    for (const fn of [...this._listeners]) {
      fn(next, prev, action);
    }
    return next;
  }

  subscribe(fn) {
    this._listeners.add(fn);
    return () => {
      this._listeners.delete(fn);
    };
  }
}

function applyStoreToS(st, prev = null) {
  if (!prev || st.revision !== prev.revision) S.revision = st.revision;
  if (!prev || st.sceneState !== prev.sceneState) S.sceneState = st.sceneState;
  if (!prev || st.selectedIds !== prev.selectedIds) S.selectedIds = new Set(st.selectedIds);
  if (!prev || st.hoverIds !== prev.hoverIds) S.hoverIds = new Set(st.hoverIds);
  if (!prev || st.selectFilter !== prev.selectFilter) S.selectFilter = st.selectFilter;
  if (!prev || st.hiddenIds !== prev.hiddenIds) S.hiddenIds = new Set(st.hiddenIds);
  if (!prev || st.cutterIds !== prev.cutterIds) S.cutterIds = new Set(st.cutterIds);
  if (!prev || st.tool !== prev.tool) S.tool = st.tool;
  if (!prev || st.pending !== prev.pending) S.pending = st.pending;
  if (!prev || st.useOrtho !== prev.useOrtho) S.useOrtho = st.useOrtho;
  if (!prev || st.projection !== prev.projection) S.projection = st.projection;
  if (!prev || st.namedView !== prev.namedView) S.namedView = st.namedView;
  if (!prev || st.viewCubeOn !== prev.viewCubeOn) S.viewCubeOn = st.viewCubeOn;
  if (!prev || st.gridOn !== prev.gridOn) S.gridOn = st.gridOn;
  if (!prev || st.gridMinorOn !== prev.gridMinorOn) S.gridMinorOn = st.gridMinorOn;
  if (!prev || st.theme !== prev.theme) S.theme = st.theme;
  if (!prev || st.canvas !== prev.canvas) S.canvas = st.canvas;
  if (!prev || st.vizVersion !== prev.vizVersion) S.vizVersion = st.vizVersion;
}

export function syncStoreFromS(targetStore = store) {
  const prev = targetStore.get();
  const sceneChanged = S.sceneState !== prev.sceneState;
  const rev = sceneChanged ? prev.revision + 1 : Math.max(prev.revision, S.revision || 0);
  S.revision = rev;
  const next = {
    revision: rev,
    sceneState: S.sceneState,
    selectedIds: toIdSet(S.selectedIds),
    hoverIds: toIdSet(S.hoverIds),
    selectFilter: S.selectFilter,
    hiddenIds: toIdSet(S.hiddenIds),
    cutterIds: toIdSet(S.cutterIds),
    tool: S.tool,
    pending: S.pending,
    useOrtho: S.useOrtho,
    projection: S.projection,
    namedView: S.namedView,
    viewCubeOn: S.viewCubeOn,
    gridOn: S.gridOn,
    gridMinorOn: S.gridMinorOn,
    committedDimsCount: S.committedDims ? S.committedDims.length : 0,
    theme: S.theme || "light",
    canvas: S.canvas || "theme",
    vizVersion: S.vizVersion || 0,
  };
  targetStore._state = next;
  return next;
}

export function createReconciler(
  storeInstance,
  { onGeometry = () => {}, onSelection = () => {}, schedule = queueMicrotask } = {},
) {
  let scheduled = false;
  let disposed = false;
  let lastGeomSig = geometrySignature(storeInstance.get());
  let lastSelSig = selectionSignature(storeInstance.get());

  function flush() {
    scheduled = false;
    if (disposed) return;
    const s = storeInstance.get();
    const gSig = geometrySignature(s);
    const sSig = selectionSignature(s);
    if (gSig !== lastGeomSig) {
      lastGeomSig = gSig;
      lastSelSig = sSig;
      onGeometry(s);
      requestRender();
    } else if (sSig !== lastSelSig) {
      lastSelSig = sSig;
      onSelection(s);
      requestRender();
    }
  }

  function markBaseline(s = storeInstance.get()) {
    lastGeomSig = geometrySignature(s);
    lastSelSig = selectionSignature(s);
  }

  const unsubscribe = storeInstance.subscribe(() => {
    if (disposed || scheduled) return;
    scheduled = true;
    schedule(flush);
  });

  return {
    flush,
    markBaseline,
    dispose() {
      disposed = true;
      unsubscribe();
    },
  };
}

// Render-on-demand wake plumbing (ADR 0035): replaces the unconditional 60 fps rAF loop.
let _renderDirty = true;
let _renderWake = null;

export function setRenderWake(fn) {
  _renderWake = typeof fn === "function" ? fn : null;
}

export function requestRender() {
  _renderDirty = true;
  if (_renderWake) _renderWake();
}

export function consumeRenderDirty() {
  const was = _renderDirty;
  _renderDirty = false;
  return was;
}

export const store = new Store(initialStoreState(), { syncS: true });

// Registered scene/dock callbacks so lower-layer modules (selection.js, preselect.js,
// render.js) can trigger selection or dock refreshes without circular ES module imports.
let _onGeometryHook = null;
let _onSelectionHook = null;

export function registerReconcileHooks({ onGeometry, onSelection } = {}) {
  if (typeof onGeometry === "function") _onGeometryHook = onGeometry;
  if (typeof onSelection === "function") _onSelectionHook = onSelection;
}

export const appReconciler = createReconciler(store, {
  onGeometry: (s) => {
    if (_onGeometryHook) _onGeometryHook(s);
  },
  onSelection: (s) => {
    if (_onSelectionHook) _onSelectionHook(s);
  },
});

export function notifySelectionChanged() {
  syncStoreFromS(store);
  appReconciler.flush();
}
