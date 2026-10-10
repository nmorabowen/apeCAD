// Shared mutable client state (ADR 0023). An imported `let` binding is read-only in the
// importing module, so anything more than one module reassigns lives on this one object.
// Client state only: none of it is in the ops log or the saved document (ADR 0013-0015).
export const S = {
  // Active tool and its in-progress command (`pending.kind` names the step).
  tool: "select",
  pending: null,
  lastPointer: null,
  // Selection, the selection filter, and per-session visibility.
  selectedIds: new Set(),
  selectFilter: "element",
  hiddenIds: new Set(),
  cutterIds: new Set(),
  marqueeOrigin: null,
  // Scene payload from the server, and the B-rep maps indexed from it (ADR 0018).
  sceneState: {
    points: [], lines: [], boxes: [], polylines: [], faces: [], solids: [],
    circles: [], arcs: [], ellipses: [], beziers: [],
  },
  brepChildrenOf: new Map(),
  brepParentsOf: new Map(),
  brepRootOf: new Map(),
  brepSolidOf: new Map(),
  // View: projection lens and the named (axis) view, if any.
  useOrtho: true,
  projection: "parallel",
  namedView: null,
  viewCubeOn: true,
  // Drafting toggles.
  snapOn: true,
  gridSnapOn: true,
  gridOn: true,
  gridMinorOn: true,
  orthoOn: false,
  ghostDims: [],
  committedDims: [],
  // Visualization and grid preferences (localStorage, never in the document).
  prefs: null,
  saveName: "apecad.json",
};
