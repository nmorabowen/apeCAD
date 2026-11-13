// A point-sampling 2-D canvas context for pixel oracles (C8b review F1). It keeps no image:
// it tracks, for each sample point, the style of the last fill or stroke that covers it, in
// painter's order, exactly as a canvas would leave that pixel's centre (no anti-aliasing, alpha
// ignored). A fill covers a point inside its path (even-odd or non-zero, counted the same way
// here, which is exact for the simple rings and discs the section client draws); a stroke
// covers a point within half the line width of a segment or circle. Arcs are full circles.
// Text is ignored: no sample sits under a label.

function segDistance([px, py], [ax, ay], [bx, by]) {
  const dx = bx - ax, dy = by - ay, len = dx * dx + dy * dy;
  const t = len ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len)) : 0;
  return Math.hypot(px - ax - t * dx, py - ay - t * dy);
}

function crossings([px, py], pts) {
  let inside = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const [xi, yi] = pts[i], [xj, yj] = pts[j];
    if ((yi > py) !== (yj > py) && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

export function samplingContext(samples, background = null) {
  const colors = samples.map(() => background);
  let path = [], current = null;
  const stack = [];
  const ctx = {
    fillStyle: "", strokeStyle: "", lineWidth: 1, globalAlpha: 1, font: "", lineCap: "", lineJoin: "",
    save() { stack.push([ctx.fillStyle, ctx.strokeStyle, ctx.lineWidth, ctx.globalAlpha]); },
    restore() { [ctx.fillStyle, ctx.strokeStyle, ctx.lineWidth, ctx.globalAlpha] = stack.pop(); },
    setLineDash() {}, fillText() {}, strokeText() {},
    beginPath() { path = []; current = null; },
    moveTo(x, y) { current = { pts: [[x, y]], closed: false }; path.push(current); },
    lineTo(x, y) { if (!current) ctx.moveTo(x, y); else current.pts.push([x, y]); },
    closePath() { if (current) current.closed = true; },
    arc(x, y, r) { path.push({ circle: [x, y, r] }); current = null; },
    rect(x, y, w, h) { ctx.moveTo(x, y); ctx.lineTo(x + w, y); ctx.lineTo(x + w, y + h); ctx.lineTo(x, y + h); ctx.closePath(); },
    fillRect(x, y, w, h) {
      samples.forEach(([px, py], i) => { if (px >= x && px <= x + w && py >= y && py <= y + h) colors[i] = ctx.fillStyle; });
    },
    strokeRect() {},
    fill() {
      samples.forEach((p, i) => {
        let inside = false;
        for (const sub of path) {
          if (sub.circle) { if (Math.hypot(p[0] - sub.circle[0], p[1] - sub.circle[1]) < sub.circle[2]) inside = !inside; }
          else if (sub.pts.length > 2 && crossings(p, sub.pts)) inside = !inside;
        }
        if (inside) colors[i] = ctx.fillStyle;
      });
    },
    stroke() {
      const half = ctx.lineWidth / 2;
      samples.forEach((p, i) => {
        for (const sub of path) {
          let d = Infinity;
          if (sub.circle) d = Math.abs(Math.hypot(p[0] - sub.circle[0], p[1] - sub.circle[1]) - sub.circle[2]);
          else {
            const pts = sub.closed ? [...sub.pts, sub.pts[0]] : sub.pts;
            for (let k = 1; k < pts.length; k++) d = Math.min(d, segDistance(p, pts[k - 1], pts[k]));
          }
          if (d <= half) { colors[i] = ctx.strokeStyle; return; }
        }
      });
    },
  };
  return { ctx, colors, canvas: { getContext: () => ctx, clientWidth: 800, clientHeight: 600 } };
}
