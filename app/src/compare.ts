/**
 * Metric definitions (fixed display scales shared by cards and compare) and the interval
 * comparison logic used by Compare mode. Pure functions only.
 */
import type { Interval, Report, Room } from './data/schema';

export type MetricKey = 'winter_sun' | 'summer_sun' | 'noise_closed' | 'noise_open' | 'heat_typical' | 'heat_wave';

export interface MetricDef {
  key: MetricKey;
  label: string;
  unit: string;
  /** Fixed scale so bands are comparable across rooms and units. */
  min: number;
  max: number;
  better: 'higher' | 'lower';
  get(r: Report, roomId: string): Interval | undefined;
}

export const METRICS: MetricDef[] = [
  { key: 'winter_sun', label: 'Winter sun (Dec–Feb)', unit: 'h/day', min: 0, max: 12, better: 'higher',
    get: (r, id) => r.sun.rooms[id]?.winter_sun_h },
  { key: 'summer_sun', label: 'Summer sun (Jun–Aug)', unit: 'h/day', min: 0, max: 12, better: 'higher',
    get: (r, id) => r.sun.rooms[id]?.summer_sun_h },
  { key: 'noise_closed', label: 'Night noise, windows closed', unit: 'dB(A)', min: 10, max: 70, better: 'lower',
    get: (r, id) => r.noise.rooms[id]?.night_laeq_closed },
  { key: 'noise_open', label: 'Night noise, window ajar', unit: 'dB(A)', min: 10, max: 70, better: 'lower',
    get: (r, id) => r.noise.rooms[id]?.night_laeq_open },
  { key: 'heat_typical', label: 'Typical summer peak', unit: '°C', min: 18, max: 42, better: 'lower',
    get: (r, id) => r.heat.rooms[id]?.typical_summer_peak },
  { key: 'heat_wave', label: 'Heat-wave peak', unit: '°C', min: 18, max: 42, better: 'lower',
    get: (r, id) => r.heat.rooms[id]?.heatwave_peak },
];

export const metric = (k: MetricKey): MetricDef => METRICS.find((m) => m.key === k)!;

export function intervalsOverlap(a: Interval, b: Interval): boolean {
  return a.lo <= b.hi && b.lo <= a.hi;
}

export type Verdict = 'a' | 'b' | 'too_close';

export interface Comparison {
  verdict: Verdict;
  /** b.pred - a.pred */
  diff: number;
  overlap: boolean;
}

/**
 * Which interval is better? We only declare a winner when the two 90 % intervals do not overlap —
 * a deliberately conservative rule (non-overlap of two 90 % intervals is stronger evidence than a
 * formal 90 % test of the difference), so "too close to call" errs on the side of humility.
 */
export function compareIntervals(a: Interval, b: Interval, better: 'higher' | 'lower'): Comparison {
  const overlap = intervalsOverlap(a, b);
  const diff = b.pred - a.pred;
  if (overlap) return { verdict: 'too_close', diff, overlap };
  const aHigher = a.lo > b.hi;
  const aWins = better === 'higher' ? aHigher : !aHigher;
  return { verdict: aWins ? 'a' : 'b', diff, overlap };
}

/** The question each headline comparison answers, and how the representative room is chosen. */
export interface Headline {
  question: string;
  adjective: string;
  metric: MetricKey;
  roomRule: string;
  pick(r: Report): { room: Room; interval: Interval } | null;
}

/** Pick the room whose `pred` is extreme (max or min) among rooms passing `filter`. */
function pickRoom(r: Report, m: MetricKey, mode: 'max' | 'min', filter: (room: Room) => boolean = () => true) {
  const def = metric(m);
  let best: { room: Room; interval: Interval } | null = null;
  for (const room of r.geometry.rooms) {
    if (!filter(room)) continue;
    const iv = def.get(r, room.id);
    if (!iv) continue;
    if (!best || (mode === 'max' ? iv.pred > best.interval.pred : iv.pred < best.interval.pred)) {
      best = { room, interval: iv };
    }
  }
  return best;
}

const isBedroom = (room: Room) => room.kind.toLowerCase().includes('bed');

export const HEADLINES: Headline[] = [
  { question: 'Which is sunnier in winter?', adjective: 'sunnier', metric: 'winter_sun',
    roomRule: 'sunniest room', pick: (r) => pickRoom(r, 'winter_sun', 'max') },
  { question: 'Which is quieter at night (windows closed)?', adjective: 'quieter', metric: 'noise_closed',
    roomRule: 'loudest bedroom (or loudest room if no bedroom)',
    pick: (r) => (r.geometry.rooms.some(isBedroom) && pickRoom(r, 'noise_closed', 'max', isBedroom))
      || pickRoom(r, 'noise_closed', 'max') },
  { question: 'Which stays cooler in a heat wave?', adjective: 'cooler', metric: 'heat_wave',
    roomRule: 'hottest room', pick: (r) => pickRoom(r, 'heat_wave', 'max') },
];

export interface HeadlineResult {
  headline: Headline;
  a: { room: Room; interval: Interval } | null;
  b: { room: Room; interval: Interval } | null;
  comparison: Comparison | null;
  text: string;
}

const fmt = (v: number) => (Math.abs(v) >= 10 ? v.toFixed(0) : v.toFixed(1));

export function summarize(a: Report, b: Report, labelA = 'A', labelB = 'B'): HeadlineResult[] {
  return HEADLINES.map((headline) => {
    const pa = headline.pick(a);
    const pb = headline.pick(b);
    const def = metric(headline.metric);
    if (!pa || !pb) {
      return { headline, a: pa, b: pb, comparison: null, text: 'Not estimated for both units.' };
    }
    const c = compareIntervals(pa.interval, pb.interval, def.better);
    const gap = `${fmt(Math.abs(c.diff))} ${def.unit}`;
    const text = c.verdict === 'too_close'
      ? `Too close to call — the 90 % intervals overlap (point estimates differ by ${gap}).`
      : `${c.verdict === 'a' ? labelA : labelB} is likely ${headline.adjective} (by ~${gap}); `
        + 'the difference is bigger than the uncertainty (intervals do not overlap).';
    return { headline, a: pa, b: pb, comparison: c, text };
  });
}
