import { describe, expect, it } from 'vitest';
import { Matrix4, Vector3 } from 'three';
import {
  defaultHourIndex, ENU_TO_THREE_MATRIX, enuToThree, formatHour, nearestHourIndex, scalePct, sliderToIndex,
  sunDirectionEnu, sunDirectionThree, threeToEnu,
} from '../src/geo';

const close = (a: number[], b: number[]) => a.forEach((v, i) => expect(v).toBeCloseTo(b[i], 9));

describe('ENU → three.js', () => {
  it('maps east→+X, north→-Z, up→+Y', () => {
    expect(enuToThree(1, 0, 0)).toEqual([1, 0, 0]);
    expect(enuToThree(0, 1, 0)).toEqual([0, 0, -1]);
    expect(enuToThree(0, 0, 1)).toEqual([0, 1, 0]);
  });
  it('round-trips', () => {
    close(threeToEnu(...enuToThree(3.5, -2, 12)), [3.5, -2, 12]);
  });
  it('matrix agrees with the function and preserves handedness', () => {
    const m = new Matrix4().fromArray(ENU_TO_THREE_MATRIX);
    const v = new Vector3(2, 5, 7).applyMatrix4(m);
    close(v.toArray(), enuToThree(2, 5, 7));
    expect(m.determinant()).toBeCloseTo(1);
  });
});

describe('sun direction from az/el', () => {
  it('az 0 / el 0 points north', () => close(sunDirectionEnu(0, 0), [0, 1, 0]));
  it('az 90 points east', () => close(sunDirectionEnu(90, 0), [1, 0, 0]));
  it('az 180 points south', () => close(sunDirectionEnu(180, 0), [0, -1, 0]));
  it('el 90 points up', () => close(sunDirectionEnu(123, 90), [0, 0, 1]));
  it('is a unit vector with z = sin(el)', () => {
    const d = sunDirectionEnu(200, 30);
    expect(Math.hypot(...d)).toBeCloseTo(1);
    expect(d[2]).toBeCloseTo(0.5);
  });
  it('south-west noon-ish sun in three.js coords has +Z (south) and -X (west)', () => {
    const [x, y, z] = sunDirectionThree(225, 45);
    expect(x).toBeLessThan(0);
    expect(y).toBeCloseTo(Math.SQRT1_2);
    expect(z).toBeGreaterThan(0);
  });
});

describe('slider index mapping', () => {
  const hours = [6, 6.5, 7, 7.5, 8];
  it('clamps and rounds raw slider values', () => {
    expect(sliderToIndex('2', 5)).toBe(2);
    expect(sliderToIndex('2.6', 5)).toBe(3);
    expect(sliderToIndex(-3, 5)).toBe(0);
    expect(sliderToIndex('99', 5)).toBe(4);
    expect(sliderToIndex('abc', 5)).toBe(0);
    expect(sliderToIndex(3, 0)).toBe(0);
  });
  it('finds the nearest hour (ties → earlier)', () => {
    expect(nearestHourIndex(hours, 7.1)).toBe(2);
    expect(nearestHourIndex(hours, 6.25)).toBe(0);
    expect(nearestHourIndex([], 7)).toBe(-1);
  });
  it('defaults to the hour nearest solar noon', () => {
    expect(defaultHourIndex([6, 8, 10, 12, 14])).toBe(3);
    expect(defaultHourIndex(hours)).toBe(4);
  });
  it('formats hours', () => {
    expect(formatHour(6.5)).toBe('06:30');
    expect(formatHour(20)).toBe('20:00');
    expect(formatHour(13.25)).toBe('13:15');
  });
  it('scales to a fixed range', () => {
    expect(scalePct(5, 0, 10)).toBe(50);
    expect(scalePct(-1, 0, 10)).toBe(0);
    expect(scalePct(11, 0, 10)).toBe(100);
  });
});
