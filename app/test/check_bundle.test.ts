import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, describe, expect, it } from 'vitest';
import { writeFixtureBundle } from '../scripts/copy_fixture.mjs';
import { FIXTURES } from './helpers';

const SCRIPT = fileURLToPath(new URL('../scripts/check_bundle.mjs', import.meta.url));
const run = (...args: string[]) => spawnSync(process.execPath, [SCRIPT, ...args], { encoding: 'utf8' });
const dirs: string[] = [];
const tmp = () => { const d = mkdtempSync(join(tmpdir(), 'dwell-bundle-')); dirs.push(d); return d; };
afterEach(() => dirs.splice(0).forEach((d) => rmSync(d, { recursive: true, force: true })));

describe('check_bundle.mjs', () => {
  it('passes on the fixture bundle with audio', () => {
    const d = tmp();
    writeFixtureBundle(FIXTURES, d);
    const r = run(d);
    expect(r.stdout + r.stderr).toContain('OK');
    expect(r.status).toBe(0);
  });
  it('fails when an audio file is missing', () => {
    const d = tmp();
    writeFixtureBundle(FIXTURES, d);
    rmSync(join(d, 'fixture_a', 'audio', 'fixture_a_bedroom_0200_open.wav'));
    const r = run(d);
    expect(r.status).toBe(1);
    expect(r.stderr).toContain('file not found');
  });
  it('fails on a schema violation', () => {
    const d = tmp();
    writeFixtureBundle(FIXTURES, d);
    const p = join(d, 'fixture_b', 'report.json');
    const rep = JSON.parse(readFileSync(p, 'utf8'));
    rep.data_kind = 'maybe';
    writeFileSync(p, JSON.stringify(rep));
    expect(run(d).status).toBe(1);
  });
  it('fails on an empty directory unless --allow-empty', () => {
    const d = tmp();
    expect(run(d).status).toBe(1);
    expect(run(d, '--allow-empty').status).toBe(0);
  });
});
