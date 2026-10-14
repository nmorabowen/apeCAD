// Pure plan geometry for drawing section-mode entities (ADR 0024). Points are
// {x_mm, y_mm, z_mm} records. No DOM, no THREE. Mirrors apeCAD.render.section.

// The CCW ring `centres` grown outward by offsets[i] at each vertex, with round corners:
// how a hoop wraps its bars (bar radius + half the tie). Two centres give a stadium.
export function roundedRing(centres, offsets, stepRad = Math.PI / 16) {
  const count = centres.length;
  if (count < 2) return [];
  const normals = centres.map((a, i) => {
    const b = centres[(i + 1) % count];
    const dx = b.x_mm - a.x_mm;
    const dy = b.y_mm - a.y_mm;
    const length = Math.hypot(dx, dy) || 1;
    return [dy / length, -dx / length];
  });
  const out = [];
  for (let i = 0; i < count; i += 1) {
    const before = normals[(i - 1 + count) % count];
    const after = normals[i];
    const start = Math.atan2(before[1], before[0]);
    let sweep = Math.atan2(after[1], after[0]) - start;
    sweep = ((sweep % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI);
    const steps = Math.max(2, Math.ceil(sweep / stepRad));
    const c = centres[i];
    for (let k = 0; k <= steps; k += 1) {
      const a = start + (sweep * k) / steps;
      out.push({
        x_mm: c.x_mm + offsets[i] * Math.cos(a),
        y_mm: c.y_mm + offsets[i] * Math.sin(a),
        z_mm: c.z_mm || 0,
      });
    }
  }
  return out;
}

// Dash a polyline by a repeating pattern of mm lengths [on, off, on, off, ...]. Returns
// the "on" pieces as [a, b] pairs. The pattern runs on across vertices.
export function dashSegments(pts, closed, pattern) {
  const path = closed && pts.length > 2 ? pts.concat([pts[0]]) : pts;
  const total = pattern.reduce((sum, value) => sum + value, 0);
  const out = [];
  if (path.length < 2 || !(total > 0)) return out;
  let index = 0;
  let left = pattern[0];
  for (let i = 0; i + 1 < path.length; i += 1) {
    const a = path[i];
    const b = path[i + 1];
    const length = Math.hypot(b.x_mm - a.x_mm, b.y_mm - a.y_mm, (b.z_mm || 0) - (a.z_mm || 0));
    let t = 0;
    while (t < length - 1e-9) {
      const step = Math.min(left, length - t);
      if (index % 2 === 0) out.push([lerp(a, b, t / length), lerp(a, b, (t + step) / length)]);
      t += step;
      left -= step;
      if (left <= 1e-9) {
        index = (index + 1) % pattern.length;
        left = pattern[index];
      }
    }
  }
  return out;
}

function lerp(a, b, f) {
  return {
    x_mm: a.x_mm + (b.x_mm - a.x_mm) * f,
    y_mm: a.y_mm + (b.y_mm - a.y_mm) * f,
    z_mm: (a.z_mm || 0) + ((b.z_mm || 0) - (a.z_mm || 0)) * f,
  };
}
