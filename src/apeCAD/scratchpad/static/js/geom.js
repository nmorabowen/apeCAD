// Pure millimetre geometry: curve sampling, intersections, projections.
// Points are {x_mm, y_mm, z_mm} records as the scene payload ships them. No DOM, no THREE.

export function dist3(a, b) {
  return Math.hypot(b.x_mm - a.x_mm, b.y_mm - a.y_mm, (b.z_mm || 0) - (a.z_mm || 0));
}

export function sampleCircle(center, radius, count = 64) {
  const pts = [];
  for (let i = 0; i <= count; i += 1) {
    const a = (i / count) * Math.PI * 2;
    pts.push({
      x_mm: center.x_mm + radius * Math.cos(a),
      y_mm: center.y_mm + radius * Math.sin(a),
      z_mm: center.z_mm || 0,
    });
  }
  return pts;
}

export function sampleEllipse(center, rx, ry, count = 64) {
  const pts = [];
  for (let i = 0; i <= count; i += 1) {
    const a = (i / count) * Math.PI * 2;
    pts.push({
      x_mm: center.x_mm + rx * Math.cos(a),
      y_mm: center.y_mm + ry * Math.sin(a),
      z_mm: center.z_mm || 0,
    });
  }
  return pts;
}

export function circumcircle(a, b, c) {
  const d = 2 * (
    a.x_mm * (b.y_mm - c.y_mm)
    + b.x_mm * (c.y_mm - a.y_mm)
    + c.x_mm * (a.y_mm - b.y_mm)
  );
  if (Math.abs(d) < 1e-8) return null;
  const a2 = a.x_mm * a.x_mm + a.y_mm * a.y_mm;
  const b2 = b.x_mm * b.x_mm + b.y_mm * b.y_mm;
  const c2 = c.x_mm * c.x_mm + c.y_mm * c.y_mm;
  const ux = (a2 * (b.y_mm - c.y_mm) + b2 * (c.y_mm - a.y_mm) + c2 * (a.y_mm - b.y_mm)) / d;
  const uy = (a2 * (c.x_mm - b.x_mm) + b2 * (a.x_mm - c.x_mm) + c2 * (b.x_mm - a.x_mm)) / d;
  return { x_mm: ux, y_mm: uy, z_mm: 0, radius: Math.hypot(ux - a.x_mm, uy - a.y_mm) };
}

export function ccwDelta(from, to) {
  let delta = to - from;
  while (delta <= 0) delta += Math.PI * 2;
  while (delta > Math.PI * 2) delta -= Math.PI * 2;
  return delta;
}

export function sampleArc(start, mid, end, count = 48) {
  const circ = circumcircle(start, mid, end);
  if (!circ) return [start, mid, end];
  const a0 = Math.atan2(start.y_mm - circ.y_mm, start.x_mm - circ.x_mm);
  const a1 = Math.atan2(mid.y_mm - circ.y_mm, mid.x_mm - circ.x_mm);
  const a2 = Math.atan2(end.y_mm - circ.y_mm, end.x_mm - circ.x_mm);
  const total = ccwDelta(a0, a1) < ccwDelta(a0, a2)
    ? ccwDelta(a0, a2)
    : ccwDelta(a0, a2) - Math.PI * 2;
  const pts = [];
  for (let i = 0; i <= count; i += 1) {
    const angle = a0 + total * (i / count);
    pts.push({
      x_mm: circ.x_mm + circ.radius * Math.cos(angle),
      y_mm: circ.y_mm + circ.radius * Math.sin(angle),
      z_mm: 0,
    });
  }
  return pts;
}

export function sampleBezier(pts, count = 32) {
  const [p0, p1, p2, p3] = pts;
  const out = [];
  for (let i = 0; i <= count; i += 1) {
    const t = i / count;
    const u = 1 - t;
    out.push({
      x_mm: u * u * u * p0.x_mm + 3 * u * u * t * p1.x_mm + 3 * u * t * t * p2.x_mm + t * t * t * p3.x_mm,
      y_mm: u * u * u * p0.y_mm + 3 * u * u * t * p1.y_mm + 3 * u * t * t * p2.y_mm + t * t * t * p3.y_mm,
      z_mm: 0,
    });
  }
  return out;
}

export function regularPolygon(center, rim, sides) {
  const radius = dist3(center, rim);
  const a0 = Math.atan2(rim.y_mm - center.y_mm, rim.x_mm - center.x_mm);
  const pts = [];
  for (let i = 0; i < sides; i += 1) {
    const angle = a0 + (i * 2 * Math.PI) / sides;
    pts.push({
      x_mm: center.x_mm + radius * Math.cos(angle),
      y_mm: center.y_mm + radius * Math.sin(angle),
      z_mm: 0,
    });
  }
  return pts;
}

export function lineIntersectMm(a1, a2, b1, b2) {
  const ax = a1.x_mm;
  const ay = a1.y_mm;
  const bx = a2.x_mm - ax;
  const by = a2.y_mm - ay;
  const cx = b1.x_mm;
  const cy = b1.y_mm;
  const dx = b2.x_mm - cx;
  const dy = b2.y_mm - cy;
  const denom = bx * dy - by * dx;
  if (Math.abs(denom) < 1e-12) return null;
  const t = ((cx - ax) * dy - (cy - ay) * dx) / denom;
  const u = ((cx - ax) * by - (cy - ay) * bx) / denom;
  return { x_mm: ax + t * bx, y_mm: ay + t * by, z_mm: 0, t, u };
}

export function projectT(point, start, end) {
  const vx = end.x_mm - start.x_mm;
  const vy = end.y_mm - start.y_mm;
  const length2 = vx * vx + vy * vy;
  if (length2 === 0) return 0;
  return ((point.x_mm - start.x_mm) * vx + (point.y_mm - start.y_mm) * vy) / length2;
}
