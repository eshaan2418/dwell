#!/usr/bin/env node
// Validate a directory of Dwell report bundles against dwell-report/1 (offline, no dependencies).
//   node app/scripts/check_bundle.mjs <reports_dir> [--allow-empty]
// Checks: index.json (if present) shape + every entry has a bundle; each <id>/report.json passes the
// hand-written validator; unit.id matches the directory; every referenced audio file exists and is a
// RIFF/WAVE file. Exits 1 on any failure.
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { validateIndex, validateReport } from '../src/data/validate.js';

const args = process.argv.slice(2);
const dir = args.find((a) => !a.startsWith('--'));
const allowEmpty = args.includes('--allow-empty');
if (!dir) {
  console.error('usage: node scripts/check_bundle.mjs <reports_dir> [--allow-empty]');
  process.exit(2);
}
const root = resolve(dir);
if (!existsSync(root) || !statSync(root).isDirectory()) {
  console.error(`check_bundle: ${root} is not a directory`);
  process.exit(1);
}

const failures = [];
const fail = (where, msg) => failures.push(`${where}: ${msg}`);

const unitDirs = readdirSync(root).filter((d) => existsSync(join(root, d, 'report.json')));

const indexPath = join(root, 'index.json');
if (existsSync(indexPath)) {
  let index;
  try {
    index = JSON.parse(readFileSync(indexPath, 'utf8'));
  } catch (e) {
    fail('index.json', `invalid JSON (${e.message})`);
  }
  if (index !== undefined) {
    const errs = validateIndex(index);
    errs.forEach((e) => fail('index.json', e));
    if (!errs.length) {
      for (const e of index) if (!unitDirs.includes(e.id)) fail('index.json', `entry "${e.id}" has no ${e.id}/report.json`);
      for (const d of unitDirs) if (!index.some((e) => e.id === d)) fail('index.json', `bundle "${d}" is missing from the index`);
    }
  }
} else if (unitDirs.length) {
  fail('index.json', 'missing (the app discovers units through it)');
}

let audioCount = 0;
for (const id of unitDirs) {
  const where = `${id}/report.json`;
  let report;
  try {
    report = JSON.parse(readFileSync(join(root, id, 'report.json'), 'utf8'));
  } catch (e) {
    fail(where, `invalid JSON (${e.message})`);
    continue;
  }
  const errs = validateReport(report);
  errs.forEach((e) => fail(where, e));
  if (errs.length) continue;
  if (report.unit.id !== id) fail(where, `unit.id "${report.unit.id}" does not match directory "${id}"`);
  for (const [room, ref] of Object.entries(report.noise.audio ?? {})) {
    for (const k of ['closed', 'open']) {
      const p = join(root, id, ref[k]);
      if (!existsSync(p)) { fail(where, `noise.audio.${room}.${k}: file not found (${ref[k]})`); continue; }
      const head = readFileSync(p).subarray(0, 12);
      if (head.toString('ascii', 0, 4) !== 'RIFF' || head.toString('ascii', 8, 12) !== 'WAVE') {
        fail(where, `noise.audio.${room}.${k}: not a WAV file (${ref[k]})`);
      } else audioCount++;
    }
  }
}

if (!unitDirs.length && !allowEmpty) fail(root, 'no <unit_id>/report.json bundles found (run `make demo`, or pass --allow-empty)');

if (failures.length) {
  console.error(`check_bundle: FAILED (${failures.length} problem${failures.length === 1 ? '' : 's'})`);
  for (const f of failures.slice(0, 200)) console.error('  - ' + f);
  process.exit(1);
}
console.log(`check_bundle: OK — ${unitDirs.length} report(s), ${audioCount} audio file(s) in ${root}`);
