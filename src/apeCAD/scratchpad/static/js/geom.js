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

// A creation op's vertex (ADR 0030): a snapped point's id, else its coordinates. The server
// reuses a point within 1 mm, so one gesture posts one op instead of AddPoint per vertex.
export function vertexRef(xyz) {
  if (xyz.entity_id) return xyz.entity_id;
  return { xyz: [xyz.x_mm, xyz.y_mm, xyz.z_mm || 0] };
}

// The four corners of the axis-aligned rectangle spanned by a and b on the z = 0 workplane,
// counter-clockwise from the min corner. Null if thinner than 1 mm.
export function rectCorners(a, b) {
  const x0 = Math.min(a.x_mm, b.x_mm);
  const y0 = Math.min(a.y_mm, b.y_mm);
  const x1 = Math.max(a.x_mm, b.x_mm);
  const y1 = Math.max(a.y_mm, b.y_mm);
  if (x1 - x0 < 1 || y1 - y0 < 1) return null;
  return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]].map(([x, y]) => ({ x_mm: x, y_mm: y, z_mm: 0 }));
}

// Dispose every BufferGeometry and Material under a Three.js Object3D subtree before .clear().
export function disposeObject3D(root) {
  if (!root || typeof root.traverse !== "function") return;
  root.traverse((node) => {
    if (node.geometry && typeof node.geometry.dispose === "function") {
      node.geometry.dispose();
    }
    for (const mat of [].concat(node.material || [])) {
      if (mat && typeof mat.dispose === "function") mat.dispose();
    }
  });
}

// Wrap a Three.js Group so .clear() automatically disposes child GPU resources and notifies onClear.
export function wrapAutoDispose(group, onClear = null) {
  if (!group || typeof group.clear !== "function") return group;
  const origClear = group.clear.bind(group);
  group.clear = () => {
    disposeObject3D(group);
    const out = origClear();
    if (typeof onClear === "function") onClear();
    return out;
  };
  return group;
}

function toUV(p) {
  if (Array.isArray(p)) return [Number(p[0]) || 0, Number(p[1]) || 0];
  if (typeof p.x_mm === "number") return [p.x_mm, p.y_mm];
  return [Number(p.x) || 0, Number(p.y) || 0];
}

function toXYZ(p) {
  if (Array.isArray(p)) return [Number(p[0]) || 0, Number(p[1]) || 0, Number(p[2]) || 0];
  if (typeof p.x_mm === "number") return [p.x_mm, p.y_mm, p.z_mm || 0];
  return [Number(p.x) || 0, Number(p.y) || 0, Number(p.z) || 0];
}

function cross2D(a, b, c) {
  return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
}

function pointInTriangle2D(p, a, b, c, sign) {
  const eps = -1e-7;
  const c1 = sign * cross2D(a, b, p);
  const c2 = sign * cross2D(b, c, p);
  const c3 = sign * cross2D(c, a, p);
  return c1 >= eps && c2 >= eps && c3 >= eps;
}

// Ear-clipping triangulation of a simple 2-D polygon (convex or concave, ADR 0036).
// Returns an array of [i0, i1, i2] index triples into the unclosed input vertex list.
export function triangulatePolygon2D(pts) {
  if (!pts || pts.length < 3) return [];
  const uv = pts.map(toUV);
  if (
    uv.length > 3 &&
    Math.hypot(uv[uv.length - 1][0] - uv[0][0], uv[uv.length - 1][1] - uv[0][1]) < 1e-6
  ) {
    uv.pop();
  }
  const n = uv.length;
  if (n < 3) return [];
  if (n === 3) return [[0, 1, 2]];

  let area2 = 0;
  for (let i = 0; i < n; i++) {
    const a = uv[i];
    const b = uv[(i + 1) % n];
    area2 += a[0] * b[1] - b[0] * a[1];
  }
  const sign = area2 >= 0 ? 1 : -1;
  const ring = Array.from({ length: n }, (_, i) => i);
  const tris = [];
  let guard = n * n + 4;

  while (ring.length > 3 && guard-- > 0) {
    const m = ring.length;
    let clipped = false;
    for (let i = 0; i < m; i++) {
      const iPrev = ring[(i + m - 1) % m];
      const iCurr = ring[i];
      const iNext = ring[(i + 1) % m];
      const a = uv[iPrev];
      const b = uv[iCurr];
      const c = uv[iNext];
      if (sign * cross2D(a, b, c) <= 1e-8) continue;

      let containsOther = false;
      for (let j = 0; j < m; j++) {
        const idx = ring[j];
        if (idx === iPrev || idx === iCurr || idx === iNext) continue;
        const p = uv[idx];
        if (
          Math.hypot(p[0] - a[0], p[1] - a[1]) < 1e-7 ||
          Math.hypot(p[0] - b[0], p[1] - b[1]) < 1e-7 ||
          Math.hypot(p[0] - c[0], p[1] - c[1]) < 1e-7
        ) {
          continue;
        }
        if (pointInTriangle2D(p, a, b, c, sign)) {
          containsOther = true;
          break;
        }
      }
      if (!containsOther) {
        tris.push([iPrev, iCurr, iNext]);
        ring.splice(i, 1);
        clipped = true;
        break;
      }
    }
    if (!clipped) {
      // Degenerate or nearly collinear vertex fallback: clip the most convex remaining corner.
      let bestI = 0;
      let bestCross = -Infinity;
      for (let i = 0; i < m; i++) {
        const a = uv[ring[(i + m - 1) % m]];
        const b = uv[ring[i]];
        const c = uv[ring[(i + 1) % m]];
        const cr = sign * cross2D(a, b, c);
        if (cr > bestCross) {
          bestCross = cr;
          bestI = i;
        }
      }
      tris.push([ring[(bestI + m - 1) % m], ring[bestI], ring[(bestI + 1) % m]]);
      ring.splice(bestI, 1);
    }
  }
  if (ring.length === 3) {
    tris.push([ring[0], ring[1], ring[2]]);
  }
  return tris;
}

// Project a planar 3-D polygon onto its Newell plane basis and ear-clip it (ADR 0036).
export function triangulatePlanar3D(pts) {
  if (!pts || pts.length < 3) return [];
  const xyz = pts.map(toXYZ);
  if (
    xyz.length > 3 &&
    Math.hypot(
      xyz[xyz.length - 1][0] - xyz[0][0],
      xyz[xyz.length - 1][1] - xyz[0][1],
      xyz[xyz.length - 1][2] - xyz[0][2],
    ) < 1e-6
  ) {
    xyz.pop();
  }
  const n = xyz.length;
  if (n < 3) return [];
  if (n === 3) return [[0, 1, 2]];

  let nx = 0;
  let ny = 0;
  let nz = 0;
  for (let i = 0; i < n; i++) {
    const a = xyz[i];
    const b = xyz[(i + 1) % n];
    nx += (a[1] - b[1]) * (a[2] + b[2]);
    ny += (a[2] - b[2]) * (a[0] + b[0]);
    nz += (a[0] - b[0]) * (a[1] + b[1]);
  }
  const nLen = Math.hypot(nx, ny, nz);
  if (nLen < 1e-9) return [];
  nx /= nLen;
  ny /= nLen;
  nz /= nLen;

  // Orthonormal tangent basis (u, v) on the polygon plane.
  const ref = Math.abs(nx) < 0.9 ? [1, 0, 0] : [0, 1, 0];
  let ux = ny * ref[2] - nz * ref[1];
  let uy = nz * ref[0] - nx * ref[2];
  let uz = nx * ref[1] - ny * ref[0];
  const uLen = Math.hypot(ux, uy, uz) || 1;
  ux /= uLen;
  uy /= uLen;
  uz /= uLen;
  const vx = ny * uz - nz * uy;
  const vy = nz * ux - nx * uz;
  const vz = nx * uy - ny * ux;

  const p0 = xyz[0];
  const uv = xyz.map((p) => {
    const dx = p[0] - p0[0];
    const dy = p[1] - p0[1];
    const dz = p[2] - p0[2];
    return [dx * ux + dy * uy + dz * uz, dx * vx + dy * vy + dz * vz];
  });
  return triangulatePolygon2D(uv);
}

