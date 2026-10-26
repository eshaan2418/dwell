import { describe, expect, it } from 'vitest';
import { compareIntervals, intervalsOverlap, summarize } from '../src/compare';
import type { Report } from '../src/data/schema';
import { loadFixture } from './helpers';

const iv = (pred: number, lo: number, hi: number) => ({ pred, lo, hi });

describe('interval comparison', () => {
  it('detects overlap, including touching endpoints', () => {
    expect(intervalsOverlap(iv(1, 0, 2), iv(3, 2, 4))).toBe(true);
    expect(intervalsOverlap(iv(1, 0, 1.9), iv(3, 2, 4))).toBe(false);
  });
  it('is "too close to call" when intervals overlap even if point estimates differ', () => {
    const c = compareIntervals(iv(30, 26, 35), iv(33, 28, 38), 'lower');
    expect(c.verdict).toBe('too_close');
    expect(c.diff).toBeCloseTo(3);
  });
  it('picks the higher interval when higher is better', () => {
    expect(compareIntervals(iv(5, 4, 6), iv(1, 0, 2), 'higher').verdict).toBe('a');
    expect(compareIntervals(iv(1, 0, 2), iv(5, 4, 6), 'higher').verdict).toBe('b');
  });
  it('picks the lower interval when lower is better', () => {
    expect(compareIntervals(iv(25, 24, 26), iv(31, 29, 33), 'lower').verdict).toBe('a');
    expect(compareIntervals(iv(31, 29, 33), iv(25, 24, 26), 'lower').verdict).toBe('b');
  });
  it('is symmetric', () => {
    const a = iv(2.1, 1.2, 3.0);
    const b = iv(0.2, 0, 0.6);
    expect(compareIntervals(a, b, 'higher').verdict).toBe('a');
    expect(compareIntervals(b, a, 'higher').verdict).toBe('b');
  });
});

describe('summarize (fixtures)', () => {
  const a = loadFixture('fixture_a') as Report;
  const b = loadFixture('fixture_b') as Report;
  const rows = summarize(a, b, 'A', 'B');
  it('south unit is sunnier beyond the uncertainty', () => {
    expect(rows[0].comparison?.verdict).toBe('a');
    expect(rows[0].a?.room.kind).toBe('living');
    expect(rows[0].text).toContain('A is likely sunnier');
  });
  it('bedroom noise is too close to call', () => {
    expect(rows[1].a?.room.kind).toBe('bedroom');
    expect(rows[1].comparison?.verdict).toBe('too_close');
    expect(rows[1].text).toContain('Too close to call');
  });
  it('heat-wave peak (hottest rooms) is too close to call', () => {
    expect(rows[2].comparison?.verdict).toBe('too_close');
  });
});
