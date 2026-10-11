// Tool switching and the canvas click state machine that drives every tool.
import { S } from "./state.js";
import { findRecord } from "./brep.js";
import { activeLength, clearTyped, refreshToggles, setHint } from "./cmdline.js";
import {
  appendPolylineVertex,
  finishArc,
  finishBezier,
  finishBox,
  finishCircle,
  finishEllipse,
  finishExtrude,
  finishFace,
  finishLine,
  finishLineChain,
  finishPolygon,
  pendingChain,
  profileExtents,
} from "./create.js";
import { currentEnd } from "./ghosts.js";
import {
  commitBreak,
  commitDelete,
  commitFaceFromLines,
  commitJoin,
  commitSew,
  commitSimplify,
  commitTrimPreview,
  finishCorner,
  finishInsertNode,
  seedCuttersFromSelection,
  solveBreak,
  solveTrimOrExtend,
} from "./modify.js";
import { pickEntity } from "./pick.js";
import { rebuild } from "./render.js";
import { selectedProfileId, setSelection } from "./selection.js";
import { hitWorkplane } from "./snap.js";
import { finishArray, finishMirror, finishMove, finishPolar, finishRotate } from "./transform.js";
import { ghosts } from "./viewport.js";

export function setTool(next) {
  if (next === "face-lines") {
    commitFaceFromLines().catch((error) => setHint(error.message));
    return;
  }
  if (next === "join") {
    commitJoin().catch((error) => setHint(error.message));
    return;
  }
  if (next === "sew") {
    commitSew().catch((error) => setHint(error.message));
    return;
  }
  if (next === "simplify") {
    commitSimplify().catch((error) => setHint(error.message));
    return;
  }
  if (next === "delete") {
    commitDelete().catch((error) => setHint(error.message));
    return;
  }
  const previous = S.tool;
  if (pendingChain()) finishLineChain().catch((error) => setHint(error.message));
  S.tool = next;
  S.pending = null;
  clearTyped();
  ghosts.clear();
  S.ghostDims = [];
  if (next === "trim" || next === "extend") {
    seedCuttersFromSelection();
  } else {
    S.cutterIds.clear();
  }
  for (const button of document.querySelectorAll("button[data-tool]")) {
    button.classList.toggle("active", button.dataset.tool === S.tool);
  }
  refreshToggles();
  if (next === "trim") {
    setHint(S.cutterIds.size
      ? `Trim (T): click the part to remove. ${S.cutterIds.size} cutter(s) pinned. Shift pins more.`
      : "Trim (T): click the part to remove. Shift pins a cutter. All lines cut if none pinned.");
  } else if (next === "extend") {
    setHint(S.cutterIds.size
      ? `Extend (E): click the end to grow. ${S.cutterIds.size} boundary line(s) pinned.`
      : "Extend (E): click the end to grow. Shift pins a boundary. All lines if none pinned.");
  } else {
    setHint(toolHints[S.tool] || "");
  }
  if (next === "trim" || next === "extend" || previous === "trim" || previous === "extend") rebuild();
}

export async function onClick(event) {
  try {
    if (S.tool === "select") {
      const picked = pickEntity(event);
      setSelection(picked, { shift: event.shiftKey });
      if (picked == null && !event.shiftKey) setHint("Selection cleared.");
      return;
    }
    if (S.tool === "move") {
      if (S.selectedIds.size === 0) {
        setHint("Select entities first, then Move.");
        return;
      }
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      if (!S.pending) {
        S.pending = { kind: "move", a: xyz };
        setHint("Move: click the destination, or type a length and Enter.");
        return;
      }
      const end = currentEnd(event);
      if (!end) return;
      await finishMove(end);
      return;
    }
    if (S.tool === "rotate") {
      if (S.selectedIds.size === 0) {
        setHint("Select entities first, then Rotate.");
        return;
      }
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      if (!S.pending) {
        S.pending = { kind: "rotate", a: xyz };
        setHint("Rotate: type degrees and Enter, or click a second point for the angle.");
        return;
      }
      const typed = activeLength();
      const end = hitWorkplane(event);
      if (typed == null && !end) return;
      const angle = typed != null
        ? typed
        : Math.atan2(end.y_mm - S.pending.a.y_mm, end.x_mm - S.pending.a.x_mm) * 180 / Math.PI;
      await finishRotate(S.pending.a, angle);
      return;
    }
    if (S.tool === "mirror") {
      if (S.selectedIds.size === 0) {
        setHint("Select entities first, then Mirror.");
        return;
      }
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      if (!S.pending) {
        S.pending = { kind: "mirror", a: xyz };
        setHint("Mirror: click the second point of the axis.");
        return;
      }
      const end = currentEnd(event);
      if (!end) return;
      await finishMirror(S.pending.a, end);
      return;
    }
    if (S.tool === "array") {
      if (S.selectedIds.size === 0) {
        setHint("Select entities first, then Array. n is the count.");
        return;
      }
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      if (!S.pending) {
        S.pending = { kind: "array", a: xyz };
        setHint("Array: click the spacing to the next copy. n is the total count.");
        return;
      }
      const end = currentEnd(event);
      if (!end) return;
      await finishArray(end);
      return;
    }
    if (S.tool === "polar") {
      if (S.selectedIds.size === 0) {
        setHint("Select entities first, then Polar. n is the count.");
        return;
      }
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      await finishPolar(xyz);
      return;
    }
    if (S.tool === "chamfer") {
      await finishCorner("chamfer", event);
      return;
    }
    if (S.tool === "fillet") {
      await finishCorner("fillet", event);
      return;
    }
    if (S.tool === "trim" || S.tool === "extend") {
      const picked = pickEntity(event);
      const row = findRecord(picked);
      if (event.shiftKey && row && row.kind === "Line") {
        if (S.cutterIds.has(picked)) S.cutterIds.delete(picked);
        else S.cutterIds.add(picked);
        rebuild();
        const noun = S.tool === "extend" ? "boundary" : "cutter";
        setHint(S.cutterIds.size
          ? `${S.tool === "extend" ? "Extend" : "Trim"}: ${S.cutterIds.size} ${noun}(s). Click a part.`
          : `${S.tool === "extend" ? "Extend" : "Trim"}: all lines. Click a part.`);
        return;
      }
      if (!row || row.kind !== "Line") {
        setHint(S.tool === "extend"
          ? "Extend: click the end to grow, or Shift-click a boundary."
          : "Trim: click the part to remove, or Shift-click a cutter.");
        return;
      }
      const click = hitWorkplane(event);
      const preview = solveTrimOrExtend(picked, click, S.tool);
      if (!preview) {
        setHint(S.tool === "extend"
          ? "Extend: click the short end toward a boundary (implied intersection is OK)."
          : "Trim: click a free end — the stub past the nearest cutter.");
        return;
      }
      await commitTrimPreview(preview);
      return;
    }
    if (S.tool === "break") {
      const picked = pickEntity(event);
      const row = findRecord(picked);
      if (!row || row.kind !== "Line") {
        setHint("Break: click the first line.");
        return;
      }
      if (!S.pending) {
        S.pending = { kind: "break", lineId: picked };
        setHint("Break: click the crossing line.");
        return;
      }
      const preview = solveBreak(S.pending.lineId, picked);
      if (!preview) {
        setHint("Break: those lines do not cross. Click another line.");
        return;
      }
      await commitBreak(preview);
      return;
    }
    if (S.tool === "node") {
      const picked = pickEntity(event);
      const row = findRecord(picked);
      if (!row || (row.kind !== "Line" && row.kind !== "Face" && row.kind !== "Polyline")) {
        setHint("Node: click a line, face, or polyline.");
        return;
      }
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      await finishInsertNode(picked, xyz);
      return;
    }
    if (S.tool === "extrude") {
      const profileId = selectedProfileId();
      if (profileId == null) {
        setHint("Select a face, circle, or ellipse first.");
        return;
      }
      if (!S.pending) {
        const extents = profileExtents(profileId);
        if (!extents) return;
        S.pending = { kind: "extrude", a: extents.a, b: extents.b, profileId };
        setHint("Extrude: move for height, then click or Enter.");
        return;
      }
      await finishExtrude(event);
      return;
    }
    if (S.tool === "line") {
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      if (!S.pending) {
        S.pending = { kind: "line", a: xyz };
        setHint("Line: click the next point, or type a length and Enter.");
        return;
      }
      const end = currentEnd(event);
      if (!end) return;
      await finishLine(end);
      return;
    }
    if (S.tool === "polyline") {
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      if (!S.pending) {
        S.pending = { kind: "polyline", pts: [xyz] };
        setHint("Polyline: click the next point.");
        return;
      }
      const end = currentEnd(event);
      if (!end) return;
      await appendPolylineVertex(end);
      return;
    }
    if (S.tool === "rect") {
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      if (!S.pending) {
        S.pending = { kind: "rect", a: xyz };
        setHint("Rect: click the opposite corner.");
        return;
      }
      const end = currentEnd(event);
      if (!end) return;
      await finishFace(end);
      return;
    }
    if (S.tool === "circle" || S.tool === "polygon" || S.tool === "ellipse") {
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      if (!S.pending) {
        S.pending = { kind: "radial", a: xyz };
        setHint(S.tool === "circle"
          ? "Circle: click the radius, or type it and Enter."
          : S.tool === "polygon"
            ? "Polygon: click the radius."
            : "Ellipse: click a corner of the bounding box.");
        return;
      }
      const rim = currentEnd(event);
      if (!rim) return;
      if (S.tool === "circle") await finishCircle(rim);
      else if (S.tool === "polygon") await finishPolygon(rim);
      else await finishEllipse(rim);
      return;
    }
    if (S.tool === "arc") {
      const xyz = currentEnd(event) || hitWorkplane(event);
      if (!xyz) return;
      if (!S.pending) {
        S.pending = { kind: "arc", pts: [xyz] };
        setHint("Arc: click a second point on the arc.");
        return;
      }
      if (S.pending.pts.length === 1) {
        S.pending.pts.push(xyz);
        setHint("Arc: click the end point.");
        return;
      }
      await finishArc(xyz);
      return;
    }
    if (S.tool === "bezier") {
      const xyz = currentEnd(event) || hitWorkplane(event);
      if (!xyz) return;
      if (!S.pending) {
        S.pending = { kind: "bezier", pts: [xyz] };
        setHint("Bézier: click control point 2.");
        return;
      }
      if (S.pending.pts.length < 3) {
        S.pending.pts.push(xyz);
        setHint(`Bézier: click control point ${S.pending.pts.length + 1}.`);
        return;
      }
      await finishBezier(xyz);
      return;
    }
    if (S.tool === "box") {
      if (!S.pending) {
        const xyz = hitWorkplane(event);
        if (!xyz) return;
        S.pending = { kind: "rect", a: xyz };
        setHint("Box: click the opposite corner of the face.");
        return;
      }
      if (S.pending.kind === "rect") {
        const end = currentEnd(event);
        if (!end) return;
        S.pending = { kind: "height", a: S.pending.a, b: end };
        setHint("Box: move for height, type a length, then click or Enter.");
        return;
      }
      await finishBox(event);
    }
  } catch (error) {
    setHint(error.message);
    S.pending = null;
    ghosts.clear();
    S.ghostDims = [];
  }
}

const toolHints = {
  select: "Select: click, or drag L→R window / R→L crossing. Filter 1–5. Shift adds. Delete removes.",
  line: "Line: click to chain segments, or type a length and Enter. Enter or Esc places the chain.",
  polyline: "Polyline: click vertices. Enter finishes. Click start or type C to close.",
  rect: "Rect: two clicks for a rectangle on XY.",
  circle: "Circle: centre, then radius. Then Select + Extrude.",
  arc: "Arc: three clicks (start, on-arc, end).",
  ellipse: "Ellipse: centre, then a corner of the bounding box.",
  polygon: "Polygon: centre, then radius. The library places a hexagon.",
  bezier: "Bézier: four control points.",
  box: "Box: rectangle, then pull height. Type height and Enter.",
  extrude: "Extrude: select a face/circle/ellipse, then pull height.",
  move: "Move (M): select entities, click a base point, then the destination.",
  rotate: "Rotate: select, click the pivot, type degrees or click an angle.",
  mirror: "Mirror: select, then two clicks for the mirror axis.",
  array: "Array: select, click spacing to the next copy.",
  polar: "Polar: select, click the centre. Length = sweep ° (default 360).",
  trim: "Trim (T): click the part to remove. Shift pins a cutter. Implied intersection is OK.",
  extend: "Extend (E): click the short end to grow to a boundary. Shift pins a boundary.",
  break: "Break: click two crossing lines to insert a shared node.",
  node: "Node: click a line, face, or polyline to insert a shared point.",
  chamfer: "Chamfer: type a distance, then click a face or polyline corner.",
  fillet: "Fillet: type a radius, then click a face or polyline corner.",
};
