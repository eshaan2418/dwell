/**
 * Pure coordinate + slider helpers (no three.js / DOM so they are trivially unit-testable).
 *
 * Report frame: local ENU metres, x = east, y = north, z = up (right-handed).
 * three.js frame: y-up, right-handed. We map  X = east, Y = up, Z = -north  (i.e. +Z points south),
 * which keeps the handedness (det = +1), so polygons keep their winding.
 */
export type Vec3 = [number, number, number];

export function enuToThree(e: number, n: number, u: number): Vec3 {
  return [e, u, n === 0 ? 0 : -n];
}

export function threeToEnu(x: number, y: number, z: number): Vec3 {
  return [x, z === 0 ? 0 : -z, y];
}

/** Column-major 4x4 matrix (three.js Matrix4.fromArray order) implementing enuToThree. */
export const ENU_TO_THREE_MATRIX: number[] = [
  1, 0, 0, 0, // column 0: image of east  → +X
  0, 0, -1, 0, // column 1: image of north → -Z
  0, 1, 0, 0, // column 2: image of up    → +Y
  0, 0, 0, 1,
];

const DEG = Math.PI / 180;

/**
 * Unit vector pointing from the scene TOWARDS the sun, in ENU.
 * azimuth: degrees clockwise from north; elevation: degrees above the horizon.
 */
export function sunDirectionEnu(azDeg: number, elDeg: number): Vec3 {
  const az = azDeg * DEG;
  const el = elDeg * DEG;
  return [Math.sin(az) * Math.cos(el), Math.cos(az) * Math.cos(el), Math.sin(el)];
}

export function sunDirectionThree(azDeg: number, elDeg: number): Vec3 {
  const [e, n, u] = sunDirectionEnu(azDeg, elDeg);
  return enuToThree(e, n, u);
}

/** Index into `hours` closest to `value` (ties → lower index); -1 for an empty list. */
export function nearestHourIndex(hours: number[], value: number): number {
  let best = -1;
  let bestD = Infinity;
  hours.forEach((h, i) => {
    const d = Math.abs(h - value);
    if (d < bestD - 1e-9) {
      best = i;
      bestD = d;
    }
  });
  return best;
}

/** The slider works on integer indices 0..n-1; clamp/round whatever the input element reports. */
export function sliderToIndex(raw: string | number, n: number): number {
  const v = typeof raw === 'number' ? raw : Number.parseFloat(raw);
  if (!Number.isFinite(v) || n <= 0) return 0;
  return Math.min(n - 1, Math.max(0, Math.round(v)));
}

/** Index of the hour closest to solar noon — a sensible default slider position. */
export function defaultHourIndex(hours: number[]): number {
  return Math.max(0, nearestHourIndex(hours, 12));
}

/** 6.5 → "06:30" (local solar clock). */
export function formatHour(h: number): string {
  const totalMin = Math.round(h * 60);
  const hh = Math.floor(totalMin / 60) % 24;
  const mm = totalMin % 60;
  return `${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')}`;
}

/** Position of `v` on a fixed [min, max] scale as a 0..100 percentage, clamped. */
export function scalePct(v: number, min: number, max: number): number {
  if (max <= min) return 0;
  return Math.min(100, Math.max(0, ((v - min) / (max - min)) * 100));
}
