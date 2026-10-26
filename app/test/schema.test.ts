import { describe, expect, it } from 'vitest';
import { parseReport, ReportError, validateIndex, validateReport } from '../src/data/schema';
import { isSafeRelativePath } from '../src/data/validate.js';
import { loadFixture } from './helpers';

describe('validateReport', () => {
  it.each(['fixture_a', 'fixture_b'])('accepts the valid fixture %s', (id) => {
    expect(validateReport(loadFixture(id))).toEqual([]);
  });

  // each mutation must produce at least one error mentioning `expect`
  const broken: [string, (r: any) => void, string][] = [ // eslint-disable-line @typescript-eslint/no-explicit-any
    ['wrong schema id', (r) => { r.schema = 'dwell-report/0'; }, 'schema'],
    ['bad data_kind', (r) => { r.data_kind = 'demo'; }, 'data_kind'],
    ['missing disclaimer', (r) => { delete r.disclaimer; }, 'disclaimer'],
    ['missing unit id', (r) => { delete r.unit.id; }, 'unit.id'],
    ['no rooms', (r) => { r.geometry.rooms = []; }, 'geometry.rooms'],
    ['duplicate room id', (r) => { r.geometry.rooms[1].id = r.geometry.rooms[0].id; }, 'duplicate'],
    ['degenerate polygon', (r) => { r.geometry.rooms[0].polygon = [[0, 0], [1, 1]]; }, 'polygon'],
    ['window on unknown room', (r) => { r.geometry.windows[0].room_id = 'nope'; }, 'room_id'],
    ['window with 3 corners', (r) => { r.geometry.windows[0].corners.pop(); }, 'corners'],
    ['inverted interval', (r) => { const k = Object.keys(r.sun.rooms)[0]; r.sun.rooms[k].winter_sun_h = { pred: 1, lo: 2, hi: 3 }; }, 'lo <= pred <= hi'],
    ['NaN-ish interval', (r) => { const k = Object.keys(r.heat.rooms)[0]; r.heat.rooms[k].heatwave_peak.hi = 'hot'; }, 'heatwave_peak'],
    ['sun_position row count', (r) => { r.sun.sun_position.pop(); }, 'sun_position'],
    ['patch hour count', (r) => { const k = Object.keys(r.sun.patches)[0]; r.sun.patches[k][0].pop(); }, 'patches'],
    ['hours not increasing', (r) => { r.sun.hours[1] = r.sun.hours[0]; }, 'increasing'],
    ['bad date', (r) => { r.sun.dates[0] = 'Dec 21'; }, 'sun.dates'],
    ['noise for unknown room', (r) => { r.noise.rooms.ghost = r.noise.rooms[Object.keys(r.noise.rooms)[0]]; }, 'unknown room'],
    ['audio path escapes bundle', (r) => { const k = Object.keys(r.noise.audio)[0]; r.noise.audio[k].open = '../../etc/passwd'; }, 'relative path'],
    ['audio as URL', (r) => { const k = Object.keys(r.noise.audio)[0]; r.noise.audio[k].closed = 'https://cdn.example/a.wav'; }, 'relative path'],
    ['posterior not summing to 1', (r) => { const k = Object.keys(r.uncertainty)[0]; r.uncertainty[k].what_we_couldnt_see[0].posterior = { a: 0.5, b: 0.2 }; }, 'sum to 1'],
    ['hourly_closed wrong length', (r) => { const k = Object.keys(r.noise.rooms)[0]; r.noise.rooms[k].hourly_closed = [1, 2]; }, 'hourly_closed'],
    ['not an object', (r) => { Object.keys(r).forEach((k) => delete r[k]); }, 'schema'],
  ];
  it.each(broken)('rejects: %s', (_name, mutate, needle) => {
    const r = loadFixture();
    mutate(r);
    const errs = validateReport(r);
    expect(errs.length).toBeGreaterThan(0);
    expect(errs.join('\n')).toContain(needle);
  });

  it('accepts an empty posterior for the aggregate "other_inputs" item', () => {
    const r = loadFixture();
    const k = Object.keys(r.uncertainty)[0];
    r.uncertainty[k].what_we_couldnt_see.push({ property: 'other_inputs', posterior: {}, variance_share: { noise: 0.5 }, explanation: 'x' });
    expect(validateReport(r)).toEqual([]);
  });

  it('rejects non-objects', () => {
    expect(validateReport(null)).toHaveLength(1);
    expect(validateReport([1, 2])).toHaveLength(1);
  });

  it('allows optional sections to be absent', () => {
    const r = loadFixture();
    delete r.uncertainty; delete r.noise.audio; delete r.geometry.trees; delete r.provenance;
    expect(validateReport(r)).toEqual([]);
  });

  it('parseReport throws ReportError with details', () => {
    const r = loadFixture();
    r.schema = 'x';
    expect(() => parseReport(r, 'test.json')).toThrow(ReportError);
  });
});

describe('validateIndex', () => {
  it('accepts a good index', () => {
    expect(validateIndex([{ id: 'u1', label: 'Unit 1', data_kind: 'real' }])).toEqual([]);
  });
  it('rejects bad entries', () => {
    expect(validateIndex({})).not.toEqual([]);
    expect(validateIndex([{ id: '../x', label: 'x', data_kind: 'real' }])).not.toEqual([]);
    expect(validateIndex([{ id: 'a', label: 'x', data_kind: 'fake' }])).not.toEqual([]);
    expect(validateIndex([{ id: 'a', label: 'x', data_kind: 'real' }, { id: 'a', label: 'y', data_kind: 'real' }])).not.toEqual([]);
  });
  it('safe relative paths', () => {
    expect(isSafeRelativePath('audio/a.wav')).toBe(true);
    expect(isSafeRelativePath('/abs.wav')).toBe(false);
    expect(isSafeRelativePath('a/../../b')).toBe(false);
    expect(isSafeRelativePath('data:audio/wav;base64,AAAA')).toBe(false);
  });
});
