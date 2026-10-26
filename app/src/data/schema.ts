/** Types for the `dwell-report/1` bundle (docs/REPORT_SCHEMA.md) + loading helpers. */
import { validateReport as validateJs, validateIndex as validateIndexJs, SCHEMA_ID } from './validate.js';

export { SCHEMA_ID };

export type XY = [number, number];
export type XYZ = [number, number, number];
export type DataKind = 'synthetic' | 'real';

export interface Interval { pred: number; lo: number; hi: number }

export interface Room {
  id: string; kind: string; name?: string; polygon: XY[]; floor_z: number; ceiling_height: number;
}
export interface Window { id: string; room_id: string; corners: XYZ[]; azimuth: number; overhang_depth?: number }
export interface ContextBuilding { footprint: XY[]; height: number; own?: boolean }
export interface Road { coords: XY[]; road_class?: string }
export interface Tree { x: number; y: number; radius: number; height: number }

export interface SunRoom {
  winter_sun_h: Interval; summer_sun_h: Interval; monthly_sun_h?: number[];
  clear_sky_winter_solstice_h?: number; daylight_factor_pct?: number;
}
export interface NoiseRoom {
  night_laeq_closed: Interval; night_laeq_open: Interval; outdoor_night_facade?: number;
  attribution_db?: Record<string, number>; hourly_closed?: number[]; who_guideline_note?: string | null;
}
export interface HeatRoom {
  typical_summer_peak: Interval; heatwave_peak: Interval;
  hours_above_26_typical_summer?: number; hours_above_28_typical_summer?: number;
}
export interface UnseenItem {
  property: string; posterior: Record<string, number>; variance_share?: Record<string, number>; explanation: string;
}
export interface AudioRef { closed: string; open: string; label?: string }

export interface Report {
  schema: typeof SCHEMA_ID;
  generated_utc?: string;
  data_kind: DataKind;
  disclaimer: string;
  unit: {
    id: string; label: string; floor?: number; building_kind?: string; year_built?: number;
    main_orientation?: string; has_ac?: boolean | null;
  };
  geometry: {
    rooms: Room[]; windows: Window[]; context_buildings?: ContextBuilding[]; roads?: Road[]; trees?: Tree[];
  };
  sun: {
    dates: string[]; hours: number[]; sun_position: XY[][];
    patches: Record<string, (XY[] | null)[][]>; rooms: Record<string, SunRoom>;
  };
  noise: { rooms: Record<string, NoiseRoom>; audio?: Record<string, AudioRef> };
  heat: { rooms: Record<string, HeatRoom> };
  uncertainty?: Record<string, { what_we_couldnt_see: UnseenItem[] }>;
  provenance?: Record<string, unknown>;
}

export interface IndexEntry { id: string; label: string; data_kind: DataKind }

/** A report plus where it came from (needed to resolve relative audio paths). */
export interface LoadedReport { report: Report; baseUrl: string | null }

export function validateReport(x: unknown): string[] {
  return validateJs(x);
}
export function validateIndex(x: unknown): string[] {
  return validateIndexJs(x);
}

export class ReportError extends Error {
  constructor(message: string, public readonly details: string[] = []) {
    super(message);
  }
}

/** Parse + validate; throws ReportError listing the first problems. */
export function parseReport(json: unknown, source: string): Report {
  const errs = validateReport(json);
  if (errs.length) throw new ReportError(`${source} does not match ${SCHEMA_ID}`, errs.slice(0, 12));
  return json as Report;
}

export const REPORTS_BASE = 'reports/';

/** Returns [] when no index exists yet (fresh checkout before `make demo`). */
export async function fetchIndex(): Promise<IndexEntry[]> {
  let res: Response;
  try {
    res = await fetch(REPORTS_BASE + 'index.json', { cache: 'no-cache' });
  } catch {
    return [];
  }
  if (!res.ok) return [];
  let json: unknown;
  try {
    json = await res.json();
  } catch {
    // dev servers answer unknown paths with index.html → not JSON → treat as "no reports"
    return [];
  }
  const errs = validateIndex(json);
  if (errs.length) throw new ReportError('reports/index.json is malformed', errs);
  return json as IndexEntry[];
}

export async function fetchReport(id: string): Promise<LoadedReport> {
  const baseUrl = `${REPORTS_BASE}${encodeURIComponent(id)}/`;
  const res = await fetch(baseUrl + 'report.json', { cache: 'no-cache' });
  if (!res.ok) throw new ReportError(`Could not load report "${id}" (HTTP ${res.status})`);
  return { report: parseReport(await res.json(), `reports/${id}/report.json`), baseUrl };
}

export async function readReportFile(file: File): Promise<LoadedReport> {
  let json: unknown;
  try {
    json = JSON.parse(await file.text());
  } catch {
    throw new ReportError(`${file.name} is not valid JSON`);
  }
  return { report: parseReport(json, file.name), baseUrl: null };
}

export function roomName(room: Room): string {
  return room.name ?? room.kind.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());
}
