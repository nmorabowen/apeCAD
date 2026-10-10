// Pure display-unit conversion and formatting. Lengths are millimetres internally (ADR 0006);
// a display unit only changes what the user reads and types.

export const UNIT_MM = { mm: 1, cm: 10, m: 1000, in: 25.4 };
export const UNIT_STEP = { mm: 1, cm: 0.1, m: 0.01, in: 0.01 };
const UNIT_DECIMALS = { mm: 0, cm: 1, m: 3, in: 2 };

export function toUnit(mm, unit) {
  return mm / UNIT_MM[unit];
}

export function fromUnit(value, unit) {
  const raw = Number(value);
  if (!Number.isFinite(raw)) return NaN;
  return raw * UNIT_MM[unit];
}

// Millimetres as a plain number string in `unit`, rounded to that unit's decimals.
export function formatIn(mm, unit) {
  const rounded = Number(toUnit(mm, unit).toFixed(UNIT_DECIMALS[unit]));
  return String(rounded);
}

// A positive length typed as "250", "25cm", "2.5 m" or '10"'; bare numbers are in `unit`.
// Returns millimetres, or null when the text is not a positive length.
export function parseLengthIn(text, unit) {
  const match = String(text || "").trim().match(/^([+-]?\d+(?:\.\d+)?)\s*(mm|cm|m|in|")?$/i);
  if (!match) return null;
  const n = Number(match[1]);
  if (!Number.isFinite(n) || n <= 0) return null;
  const suffix = match[2] ? match[2].toLowerCase() : unit;
  const key = suffix === '"' ? "in" : suffix;
  const factor = UNIT_MM[key];
  if (!factor) return null;
  return n * factor;
}

export function formatDeg(rad) {
  let deg = rad * 180 / Math.PI;
  if (deg < 0) deg += 360;
  return `${Math.round(deg * 10) / 10}°`;
}
