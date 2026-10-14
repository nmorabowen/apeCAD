// Tool switching and the canvas click state machine that drives every tool.
import { S } from "./state.js";
import { count, t } from "./strings.js";
import { findRecord } from "./brep.js";
import { activeLength, clearTyped, refreshToggles, refuse, setHint } from "./cmdline.js";
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
    commitFaceFromLines().catch((error) => refuse(error));
    return;
  }
  if (next === "join") {
    commitJoin().catch((error) => refuse(error));
    return;
  }
  if (next === "sew") {
    commitSew().catch((error) => refuse(error));
    return;
  }
  if (next === "simplify") {
    commitSimplify().catch((error) => refuse(error));
    return;
  }
  if (next === "delete") {
    commitDelete().catch((error) => refuse(error));
    return;
  }
  const previous = S.tool;
  if (pendingChain()) finishLineChain().catch((error) => refuse(error));
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
      ? t("hint.trim.pinned", { n: S.cutterIds.size, cutters: cutterNoun(S.cutterIds.size) })
      : t("hint.trim.none"));
  } else if (next === "extend") {
    setHint(S.cutterIds.size
      ? t("hint.extend.pinned", { n: S.cutterIds.size, boundaries: boundaryNoun(S.cutterIds.size) })
      : t("hint.extend.none"));
  } else {
    setHint(TOOL_HINTS.has(S.tool) ? t(`tool.${S.tool}`) : "");
  }
  if (next === "trim" || next === "extend" || previous === "trim" || previous === "extend") rebuild();
}

export async function onClick(event) {
  try {
    if (S.tool === "select") {
      const picked = pickEntity(event);
      setSelection(picked, { shift: event.shiftKey });
      if (picked == null && !event.shiftKey) setHint(t("done.selectionCleared"));
      return;
    }
    if (S.tool === "move") {
      if (S.selectedIds.size === 0) {
        setHint(t("hint.selectFirst", { verb: "Move" }));
        return;
      }
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      if (!S.pending) {
        S.pending = { kind: "move", a: xyz };
        setHint(t("hint.move.dest"));
        return;
      }
      const end = currentEnd(event);
      if (!end) return;
      await finishMove(end);
      return;
    }
    if (S.tool === "rotate") {
      if (S.selectedIds.size === 0) {
        setHint(t("hint.selectFirst", { verb: "Rotate" }));
        return;
      }
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      if (!S.pending) {
        S.pending = { kind: "rotate", a: xyz };
        setHint(t("hint.rotate.angle"));
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
        setHint(t("hint.selectFirst", { verb: "Mirror" }));
        return;
      }
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      if (!S.pending) {
        S.pending = { kind: "mirror", a: xyz };
        setHint(t("hint.mirror.second"));
        return;
      }
      const end = currentEnd(event);
      if (!end) return;
      await finishMirror(S.pending.a, end);
      return;
    }
    if (S.tool === "array") {
      if (S.selectedIds.size === 0) {
        setHint(t("hint.selectFirstCount", { verb: "Array" }));
        return;
      }
      const xyz = hitWorkplane(event);
      if (!xyz) return;
      if (!S.pending) {
        S.pending = { kind: "array", a: xyz };
        setHint(t("hint.array.spacing"));
        return;
      }
      const end = currentEnd(event);
      if (!end) return;
      await finishArray(end);
      return;
    }
    if (S.tool === "polar") {
      if (S.selectedIds.size === 0) {
        setHint(t("hint.selectFirstCount", { verb: "Polar" }));
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
        const n = S.cutterIds.size;
        if (S.tool === "extend") {
          setHint(n ? t("hint.extend.pins", { n, boundaries: boundaryNoun(n) }) : t("hint.extend.allLines"));
        } else {
          setHint(n ? t("hint.trim.pins", { n, cutters: cutterNoun(n) }) : t("hint.trim.allLines"));
        }
        return;
      }
      if (!row || row.kind !== "Line") {
        setHint(t(S.tool === "extend" ? "hint.extend.pick" : "hint.trim.pick"));
        return;
      }
      const click = hitWorkplane(event);
      const preview = solveTrimOrExtend(picked, click, S.tool);
      if (!preview) {
        setHint(t(S.tool === "extend" ? "hint.extend.shortEnd" : "hint.trim.freeEnd"));
        return;
      }
      await commitTrimPreview(preview);
      return;
    }
    if (S.tool === "break") {
      const picked = pickEntity(event);
      const row = findRecord(picked);
      if (!row || row.kind !== "Line") {
        setHint(t("hint.break.first"));
        return;
      }
      if (!S.pending) {
        S.pending = { kind: "break", lineId: picked };
        setHint(t("hint.break.second"));
        return;
      }
      const preview = solveBreak(S.pending.lineId, picked);
      if (!preview) {
        refuse(t("reason.noCross"));
        return;
      }
      await commitBreak(preview);
      return;
    }
    if (S.tool === "node") {
      const picked = pickEntity(event);
      const row = findRecord(picked);
      if (!row || (row.kind !== "Line" && row.kind !== "Face" && row.kind !== "Polyline")) {
        setHint(t("hint.node.pick"));
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
        setHint(t("hint.extrude.select"));
        return;
      }
      if (!S.pending) {
        const extents = profileExtents(profileId);
        if (!extents) return;
        S.pending = { kind: "extrude", a: extents.a, b: extents.b, profileId };
        setHint(t("hint.extrude.height"));
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
        setHint(t("hint.line.nextOrType"));
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
        setHint(t("hint.polyline.next"));
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
        setHint(t("hint.rect.corner"));
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
        setHint(t(S.tool === "circle"
          ? "hint.circle.radius"
          : S.tool === "polygon" ? "hint.polygon.radius" : "hint.ellipse.corner"));
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
        setHint(t("hint.arc.second"));
        return;
      }
      if (S.pending.pts.length === 1) {
        S.pending.pts.push(xyz);
        setHint(t("hint.arc.end"));
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
        setHint(t("hint.bezier.point", { n: 2 }));
        return;
      }
      if (S.pending.pts.length < 3) {
        S.pending.pts.push(xyz);
        setHint(t("hint.bezier.point", { n: S.pending.pts.length + 1 }));
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
        setHint(t("hint.box.corner"));
        return;
      }
      if (S.pending.kind === "rect") {
        const end = currentEnd(event);
        if (!end) return;
        S.pending = { kind: "height", a: S.pending.a, b: end };
        setHint(t("hint.box.height"));
        return;
      }
      await finishBox(event);
    }
  } catch (error) {
    refuse(error);
    S.pending = null;
    ghosts.clear();
    S.ghostDims = [];
  }
}

// Tools whose start hint lives in strings.js as `tool.<name>`.
const TOOL_HINTS = new Set([
  "select", "line", "polyline", "rect", "circle", "arc", "ellipse", "polygon", "bezier", "box",
  "extrude", "move", "rotate", "mirror", "array", "polar", "trim", "extend", "break", "node",
  "chamfer", "fillet",
]);

function cutterNoun(n) {
  return count(n, "cutter", "cutters").replace(/^\d+ /, "");
}

function boundaryNoun(n) {
  return count(n, "boundary", "boundaries").replace(/^\d+ /, "");
}
