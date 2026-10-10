// Pure screen-space hit tests for window and crossing selection.
// Points are {x, y} client pixels; rects are DOMRect-like {left, top, right, bottom}.

export function inRect(point, rect) {
  return point.x >= rect.left && point.x <= rect.right && point.y >= rect.top && point.y <= rect.bottom;
}

export function segmentsCross2d(a1, a2, b1, b2) {
  const ax = a2.x - a1.x;
  const ay = a2.y - a1.y;
  const bx = b2.x - b1.x;
  const by = b2.y - b1.y;
  const denom = ax * by - ay * bx;
  if (Math.abs(denom) < 1e-9) return false;
  const t = ((b1.x - a1.x) * by - (b1.y - a1.y) * bx) / denom;
  const u = ((b1.x - a1.x) * ay - (b1.y - a1.y) * ax) / denom;
  return t >= 0 && t <= 1 && u >= 0 && u <= 1;
}

export function segmentHitsRect(a, b, rect) {
  if (inRect(a, rect) || inRect(b, rect)) return true;
  const corners = [
    { x: rect.left, y: rect.top },
    { x: rect.right, y: rect.top },
    { x: rect.right, y: rect.bottom },
    { x: rect.left, y: rect.bottom },
  ];
  for (let i = 0; i < 4; i += 1) {
    if (segmentsCross2d(a, b, corners[i], corners[(i + 1) % 4])) return true;
  }
  return false;
}

export function pointInPolygon2d(point, pts) {
  let inside = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i, i += 1) {
    const a = pts[i];
    const b = pts[j];
    const crosses = ((a.y > point.y) !== (b.y > point.y))
      && (point.x < ((b.x - a.x) * (point.y - a.y)) / ((b.y - a.y) || 1e-12) + a.x);
    if (crosses) inside = !inside;
  }
  return inside;
}

export function shapeQualifies(pts, closed, crossing, rect) {
  if (!pts.length) return false;
  if (!crossing) return pts.every((point) => inRect(point, rect));
  if (pts.some((point) => inRect(point, rect))) return true;
  const last = closed ? pts.length : pts.length - 1;
  for (let i = 0; i < last; i += 1) {
    if (segmentHitsRect(pts[i], pts[(i + 1) % pts.length], rect)) return true;
  }
  if (closed) {
    const corners = [
      { x: rect.left, y: rect.top },
      { x: rect.right, y: rect.top },
      { x: rect.right, y: rect.bottom },
      { x: rect.left, y: rect.bottom },
    ];
    if (corners.some((corner) => pointInPolygon2d(corner, pts))) return true;
  }
  return false;
}
