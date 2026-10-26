import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

export const FIXTURES = fileURLToPath(new URL('./fixtures/reports/', import.meta.url));

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function loadFixture(id = 'fixture_a'): any {
  return JSON.parse(readFileSync(`${FIXTURES}${id}/report.json`, 'utf8'));
}
