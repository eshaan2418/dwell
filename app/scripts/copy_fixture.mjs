#!/usr/bin/env node
// Dev helper: copy the hand-written fixture reports into public/reports/ (git-ignored) and write
// placeholder WAVs for their audio references, so `npm run dev` has something to show before the
// Python pipeline (`make demo`) has produced real bundles.  Usage: node scripts/copy_fixture.mjs [--clean]
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { placeholderNoise, wavBytes } from './wav.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, '..', 'test', 'fixtures', 'reports');
const dst = join(here, '..', 'public', 'reports');

/** @param {string} srcDir @param {string} dstDir */
export function writeFixtureBundle(srcDir, dstDir) {
  mkdirSync(dstDir, { recursive: true });
  cpSync(srcDir, dstDir, { recursive: true });
  let seed = 1;
  for (const id of readdirSync(dstDir)) {
    const rp = join(dstDir, id, 'report.json');
    if (!existsSync(rp)) continue;
    const report = JSON.parse(readFileSync(rp, 'utf8'));
    for (const ref of Object.values(report.noise?.audio ?? {})) {
      for (const [kind, rel] of [['closed', ref.closed], ['open', ref.open]]) {
        const p = join(dstDir, id, rel);
        mkdirSync(dirname(p), { recursive: true });
        writeFileSync(p, wavBytes(placeholderNoise(3, kind === 'open' ? 0.25 : 0.06, 22050, seed++)));
      }
    }
  }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  if (process.argv.includes('--clean')) {
    for (const f of readdirSync(dst)) if (f !== '.gitkeep') rmSync(join(dst, f), { recursive: true, force: true });
    console.log(`removed fixture copies from ${dst}`);
  } else {
    writeFixtureBundle(src, dst);
    console.log(`fixture reports copied to ${dst} (git-ignored; remove with --clean)`);
  }
}
