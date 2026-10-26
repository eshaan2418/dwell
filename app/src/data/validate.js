// @ts-check
/**
 * Hand-written validator for the `dwell-report/1` bundle (docs/REPORT_SCHEMA.md).
 * Plain ESM JavaScript so it runs unchanged in the browser (via Vite) and in Node
 * (scripts/check_bundle.mjs) without a build step or any network access.
 *
 * Every function returns a list of human-readable error strings; an empty list means valid.
 */

export const SCHEMA_ID = 'dwell-report/1';
const EPS = 1e-6;

/** @param {unknown} v */
const isNum = (v) => typeof v === 'number' && Number.isFinite(v);
/** @param {unknown} v */
const isStr = (v) => typeof v === 'string';
/** @param {unknown} v @returns {v is Record<string, any>} */
const isObj = (v) => typeof v === 'object' && v !== null && !Array.isArray(v);

/**
 * @param {string[]} errs
 * @param {string} path
 * @param {unknown} v
 * @param {number} dim
 */
function point(errs, path, v, dim) {
  if (!Array.isArray(v) || v.length !== dim || !v.every(isNum)) {
    errs.push(`${path}: expected [${dim} finite numbers]`);
    return false;
  }
  return true;
}

/** @param {string[]} errs @param {string} path @param {unknown} v @param {number} minPts */
function polyline(errs, path, v, minPts) {
  if (!Array.isArray(v) || v.length < minPts) {
    errs.push(`${path}: expected an array of at least ${minPts} [x, y] points`);
    return;
  }
  v.forEach((p, i) => point(errs, `${path}[${i}]`, p, 2));
}

/** @param {string[]} errs @param {string} path @param {unknown} v */
function interval(errs, path, v) {
  if (!isObj(v) || !isNum(v.pred) || !isNum(v.lo) || !isNum(v.hi)) {
    errs.push(`${path}: expected {pred, lo, hi} finite numbers`);
    return;
  }
  if (!(v.lo <= v.pred + EPS && v.pred <= v.hi + EPS)) {
    errs.push(`${path}: interval must satisfy lo <= pred <= hi (got ${v.lo}, ${v.pred}, ${v.hi})`);
  }
}

/** @param {string[]} errs @param {string} path @param {Record<string, any>} o @param {string} key */
function optNum(errs, path, o, key) {
  if (o[key] !== undefined && o[key] !== null && !isNum(o[key])) errs.push(`${path}.${key}: expected a number`);
}

/** @param {string[]} errs @param {string} path @param {unknown} v @param {number} len */
function numArray(errs, path, v, len) {
  if (v === undefined) return;
  if (!Array.isArray(v) || v.length !== len || !v.every(isNum)) errs.push(`${path}: expected ${len} numbers`);
}

/**
 * Per-room section helper: checks the section is an object keyed by known room ids.
 * @param {string[]} errs @param {string} path @param {unknown} v @param {Set<string>} roomIds
 * @param {(p: string, entry: any) => void} each
 */
function roomMap(errs, path, v, roomIds, each) {
  if (!isObj(v)) {
    errs.push(`${path}: expected an object keyed by room id`);
    return;
  }
  for (const [rid, entry] of Object.entries(v)) {
    if (!roomIds.has(rid)) errs.push(`${path}: unknown room id "${rid}"`);
    each(`${path}.${rid}`, entry);
  }
}

/** A relative path inside the unit directory (no absolute paths, URLs or `..`). */
/** @param {unknown} p */
export function isSafeRelativePath(p) {
  return isStr(p) && p.length > 0 && !p.startsWith('/') && !p.includes('\\') && !/^[a-z]+:/i.test(p)
    && !p.split('/').includes('..');
}

/**
 * Validate a parsed report.json object.
 * @param {unknown} r
 * @returns {string[]} errors
 */
export function validateReport(r) {
  /** @type {string[]} */
  const errs = [];
  if (!isObj(r)) return ['report: expected a JSON object'];

  if (r.schema !== SCHEMA_ID) errs.push(`schema: expected "${SCHEMA_ID}", got ${JSON.stringify(r.schema)}`);
  if (r.data_kind !== 'synthetic' && r.data_kind !== 'real') errs.push('data_kind: expected "synthetic" or "real"');
  if (!isStr(r.disclaimer) || !r.disclaimer.trim()) errs.push('disclaimer: expected a non-empty string');
  if (r.generated_utc !== undefined && !isStr(r.generated_utc)) errs.push('generated_utc: expected a string');

  // unit
  if (!isObj(r.unit)) errs.push('unit: expected an object');
  else {
    if (!isStr(r.unit.id) || !r.unit.id) errs.push('unit.id: expected a non-empty string');
    if (!isStr(r.unit.label)) errs.push('unit.label: expected a string');
    optNum(errs, 'unit', r.unit, 'floor');
    optNum(errs, 'unit', r.unit, 'year_built');
    if (r.unit.has_ac !== undefined && r.unit.has_ac !== null && typeof r.unit.has_ac !== 'boolean') {
      errs.push('unit.has_ac: expected a boolean');
    }
  }

  // geometry
  /** @type {Set<string>} */
  const roomIds = new Set();
  const g = r.geometry;
  if (!isObj(g)) errs.push('geometry: expected an object');
  else {
    if (!Array.isArray(g.rooms) || g.rooms.length === 0) errs.push('geometry.rooms: expected a non-empty array');
    else {
      g.rooms.forEach((room, i) => {
        const p = `geometry.rooms[${i}]`;
        if (!isObj(room)) return errs.push(`${p}: expected an object`);
        if (!isStr(room.id) || !room.id) errs.push(`${p}.id: expected a non-empty string`);
        else if (roomIds.has(room.id)) errs.push(`${p}.id: duplicate room id "${room.id}"`);
        else roomIds.add(room.id);
        if (!isStr(room.kind)) errs.push(`${p}.kind: expected a string`);
        if (room.name !== undefined && !isStr(room.name)) errs.push(`${p}.name: expected a string`);
        polyline(errs, `${p}.polygon`, room.polygon, 3);
        if (!isNum(room.floor_z)) errs.push(`${p}.floor_z: expected a number`);
        if (!isNum(room.ceiling_height) || room.ceiling_height <= 0) errs.push(`${p}.ceiling_height: expected a positive number`);
      });
    }
    if (!Array.isArray(g.windows)) errs.push('geometry.windows: expected an array');
    else {
      g.windows.forEach((w, i) => {
        const p = `geometry.windows[${i}]`;
        if (!isObj(w)) return errs.push(`${p}: expected an object`);
        if (!isStr(w.id)) errs.push(`${p}.id: expected a string`);
        if (!isStr(w.room_id) || !roomIds.has(w.room_id)) errs.push(`${p}.room_id: must reference a room in geometry.rooms`);
        if (!Array.isArray(w.corners) || w.corners.length !== 4) errs.push(`${p}.corners: expected 4 [x, y, z] corners`);
        else w.corners.forEach((c, j) => point(errs, `${p}.corners[${j}]`, c, 3));
        if (!isNum(w.azimuth)) errs.push(`${p}.azimuth: expected a number`);
        optNum(errs, p, w, 'overhang_depth');
      });
    }
    for (const key of ['context_buildings', 'roads', 'trees']) {
      if (g[key] !== undefined && !Array.isArray(g[key])) errs.push(`geometry.${key}: expected an array`);
    }
    (Array.isArray(g.context_buildings) ? g.context_buildings : []).forEach((b, i) => {
      const p = `geometry.context_buildings[${i}]`;
      if (!isObj(b)) return errs.push(`${p}: expected an object`);
      polyline(errs, `${p}.footprint`, b.footprint, 3);
      if (!isNum(b.height) || b.height < 0) errs.push(`${p}.height: expected a non-negative number`);
      if (b.own !== undefined && typeof b.own !== 'boolean') errs.push(`${p}.own: expected a boolean`);
    });
    (Array.isArray(g.roads) ? g.roads : []).forEach((rd, i) => {
      const p = `geometry.roads[${i}]`;
      if (!isObj(rd)) return errs.push(`${p}: expected an object`);
      polyline(errs, `${p}.coords`, rd.coords, 2);
      if (rd.road_class !== undefined && !isStr(rd.road_class)) errs.push(`${p}.road_class: expected a string`);
    });
    (Array.isArray(g.trees) ? g.trees : []).forEach((t, i) => {
      const p = `geometry.trees[${i}]`;
      if (!isObj(t) || !['x', 'y', 'radius', 'height'].every((k) => isNum(t[k]))) {
        errs.push(`${p}: expected {x, y, radius, height} numbers`);
      }
    });
  }

  // sun
  const s = r.sun;
  if (!isObj(s)) errs.push('sun: expected an object');
  else {
    const nD = Array.isArray(s.dates) ? s.dates.length : 0;
    const nH = Array.isArray(s.hours) ? s.hours.length : 0;
    if (!nD || !s.dates.every((/** @type {unknown} */ d) => isStr(d) && /^\d{4}-\d{2}-\d{2}$/.test(d))) {
      errs.push('sun.dates: expected a non-empty array of YYYY-MM-DD strings');
    }
    if (!nH || !s.hours.every(isNum)) errs.push('sun.hours: expected a non-empty array of numbers');
    else if (s.hours.some((/** @type {number} */ h, /** @type {number} */ i) => i > 0 && h <= s.hours[i - 1])) {
      errs.push('sun.hours: expected strictly increasing hours');
    }
    if (!Array.isArray(s.sun_position) || s.sun_position.length !== nD) errs.push(`sun.sun_position: expected ${nD} rows (one per date)`);
    else {
      s.sun_position.forEach((row, d) => {
        if (!Array.isArray(row) || row.length !== nH) return errs.push(`sun.sun_position[${d}]: expected ${nH} [az, el] pairs`);
        row.forEach((ae, h) => point(errs, `sun.sun_position[${d}][${h}]`, ae, 2));
      });
    }
    roomMap(errs, 'sun.patches', s.patches, roomIds, (p, perDate) => {
      if (!Array.isArray(perDate) || perDate.length !== nD) return errs.push(`${p}: expected ${nD} rows (one per date)`);
      perDate.forEach((perHour, d) => {
        if (!Array.isArray(perHour) || perHour.length !== nH) return errs.push(`${p}[${d}]: expected ${nH} entries (one per hour)`);
        perHour.forEach((poly, h) => { if (poly !== null) polyline(errs, `${p}[${d}][${h}]`, poly, 3); });
      });
    });
    roomMap(errs, 'sun.rooms', s.rooms, roomIds, (p, e) => {
      if (!isObj(e)) return errs.push(`${p}: expected an object`);
      interval(errs, `${p}.winter_sun_h`, e.winter_sun_h);
      interval(errs, `${p}.summer_sun_h`, e.summer_sun_h);
      numArray(errs, `${p}.monthly_sun_h`, e.monthly_sun_h, 12);
      optNum(errs, p, e, 'clear_sky_winter_solstice_h');
      optNum(errs, p, e, 'daylight_factor_pct');
    });
  }

  // noise
  const n = r.noise;
  if (!isObj(n)) errs.push('noise: expected an object');
  else {
    roomMap(errs, 'noise.rooms', n.rooms, roomIds, (p, e) => {
      if (!isObj(e)) return errs.push(`${p}: expected an object`);
      interval(errs, `${p}.night_laeq_closed`, e.night_laeq_closed);
      interval(errs, `${p}.night_laeq_open`, e.night_laeq_open);
      optNum(errs, p, e, 'outdoor_night_facade');
      if (e.attribution_db !== undefined && (!isObj(e.attribution_db) || !Object.values(e.attribution_db).every(isNum))) {
        errs.push(`${p}.attribution_db: expected an object of numbers`);
      }
      numArray(errs, `${p}.hourly_closed`, e.hourly_closed, 24);
      if (e.who_guideline_note !== undefined && e.who_guideline_note !== null && !isStr(e.who_guideline_note)) {
        errs.push(`${p}.who_guideline_note: expected a string`);
      }
    });
    if (n.audio !== undefined) {
      roomMap(errs, 'noise.audio', n.audio, roomIds, (p, a) => {
        if (!isObj(a)) return errs.push(`${p}: expected an object`);
        for (const k of ['closed', 'open']) {
          if (!isSafeRelativePath(a[k])) errs.push(`${p}.${k}: expected a relative path inside the unit directory`);
        }
        if (a.label !== undefined && !isStr(a.label)) errs.push(`${p}.label: expected a string`);
      });
    }
  }

  // heat
  const h = r.heat;
  if (!isObj(h)) errs.push('heat: expected an object');
  else {
    roomMap(errs, 'heat.rooms', h.rooms, roomIds, (p, e) => {
      if (!isObj(e)) return errs.push(`${p}: expected an object`);
      interval(errs, `${p}.typical_summer_peak`, e.typical_summer_peak);
      interval(errs, `${p}.heatwave_peak`, e.heatwave_peak);
      optNum(errs, p, e, 'hours_above_26_typical_summer');
      optNum(errs, p, e, 'hours_above_28_typical_summer');
    });
  }

  // uncertainty (optional)
  if (r.uncertainty !== undefined) {
    roomMap(errs, 'uncertainty', r.uncertainty, roomIds, (p, e) => {
      if (!isObj(e) || !Array.isArray(e.what_we_couldnt_see)) return errs.push(`${p}.what_we_couldnt_see: expected an array`);
      e.what_we_couldnt_see.forEach((/** @type {any} */ item, /** @type {number} */ i) => {
        const q = `${p}.what_we_couldnt_see[${i}]`;
        if (!isObj(item)) return errs.push(`${q}: expected an object`);
        if (!isStr(item.property)) errs.push(`${q}.property: expected a string`);
        if (!isStr(item.explanation)) errs.push(`${q}.explanation: expected a string`);
        for (const k of ['posterior', 'variance_share']) {
          const o = item[k];
          if (o === undefined && k === 'variance_share') continue;
          if (!isObj(o) || !Object.values(o).every((x) => isNum(x) && x >= -EPS && x <= 1 + EPS)) {
            errs.push(`${q}.${k}: expected an object of numbers in [0, 1]`);
          }
        }
        // an empty posterior marks an aggregate of non-hidden inputs (e.g. "other_inputs"): no distribution to check
        if (isObj(item.posterior) && Object.keys(item.posterior).length > 0) {
          const sum = Object.values(item.posterior).reduce((a, b) => a + (isNum(b) ? b : 0), 0);
          if (Math.abs(sum - 1) > 0.02) errs.push(`${q}.posterior: probabilities must sum to 1 (got ${sum.toFixed(3)})`);
        }
      });
    });
  }

  if (r.provenance !== undefined && !isObj(r.provenance)) errs.push('provenance: expected an object');
  return errs;
}

/**
 * Validate reports/index.json.
 * @param {unknown} idx
 * @returns {string[]}
 */
export function validateIndex(idx) {
  if (!Array.isArray(idx)) return ['index: expected an array'];
  /** @type {string[]} */
  const errs = [];
  const seen = new Set();
  idx.forEach((e, i) => {
    if (!isObj(e)) return errs.push(`index[${i}]: expected an object`);
    if (!isStr(e.id) || !isSafeRelativePath(e.id) || e.id.includes('/')) errs.push(`index[${i}].id: expected a plain directory name`);
    else if (seen.has(e.id)) errs.push(`index[${i}].id: duplicate "${e.id}"`);
    seen.add(e.id);
    if (!isStr(e.label)) errs.push(`index[${i}].label: expected a string`);
    if (e.data_kind !== 'synthetic' && e.data_kind !== 'real') errs.push(`index[${i}].data_kind: expected "synthetic" or "real"`);
  });
  return errs;
}
