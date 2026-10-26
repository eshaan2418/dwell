# Dwell app (local-first web app / PWA)

Viewer for Dwell report bundles and a guided walkthrough recorder. It is a plain web app (Vite + TypeScript +
three.js) rather than native apps (DECISIONS.md D-011). Everything is bundled: at runtime there are **no
requests to third-party services** (no CDNs, fonts, analytics, or uploads). A Content-Security-Policy in
`index.html` limits every request to the app's own origin.

## Run

```bash
cd app
npm ci
npm run fixture        # optional: copy the test fixtures into public/reports/ (git-ignored) for dev
npm run dev            # http://localhost:5173
npm run dev:lan        # HTTPS + --host, so you can open it on a phone on the same Wi-Fi
npm run build          # tsc --noEmit && vite build  → dist/
npm test               # vitest
npm run lint           # tsc --noEmit && eslint
npm run check-bundle   # validate public/reports (same as: node scripts/check_bundle.mjs public/reports)
npm run fixture -- --clean   # remove the dev fixture copies again
```

**Phone on the LAN:** run `npm run dev:lan` and open the `https://<your-ip>:5173/` URL it prints. Accept the
self-signed certificate warning (the cert is generated locally). HTTPS is required because phone browsers only
allow the camera and compass on secure origins. A plain `npm run dev -- --host` works for the viewer but not
for capture. To install it as a PWA, use `npm run build && npx vite preview --host` behind HTTPS, or open it
on `localhost`.

## Data

The binding contract is [`docs/REPORT_SCHEMA.md`](../docs/REPORT_SCHEMA.md) (`dwell-report/1`). The pipeline
writes:

```
app/public/reports/index.json                 [{"id": ..., "label": ..., "data_kind": "synthetic"|"real"}]
app/public/reports/<unit_id>/report.json
app/public/reports/<unit_id>/audio/<room_id>_0200_{closed,open}.wav
```

`app/public/reports/` is git-ignored except for `.gitkeep`, so no numbers get committed there. If there is no
index, the app shows "No reports yet — run `make demo`". You can also open any `report.json` with the file
picker; it is read with the File API and never leaves the device. Night-listen audio only plays for served
bundles, because a single opened file has no audio next to it.

`scripts/check_bundle.mjs <dir> [--allow-empty]` validates every bundle offline with the hand-written
validator in `src/data/validate.js` (shared with the browser). It checks that the index and the directories
match, that `unit.id` equals the directory name, and that every referenced WAV exists and has a RIFF/WAVE
header. It exits 1 on any problem, and also when the directory has no bundles unless `--allow-empty` is given.

Dev fixtures live in `test/fixtures/reports/`. They are two small units with illustrative numbers, labelled
FIXTURE in their disclaimer and provenance. They are not model output. `npm run fixture` copies them and
generates placeholder WAVs (quiet synthetic rumble).

## Routes

| Route | What |
|---|---|
| `#/viewer[?unit=<id>]` (default) | Unit picker or file picker; 3D view (rooms, translucent windows, context buildings, roads, trees, orbit controls); sun date and hour slider showing the sun direction and the floor sun patches from `sun.patches`; per-room cards with 90 % interval bands on fixed per-metric scales, the WHO note (only if the report has `who_guideline_note`), night listen, and "What we couldn't see". |
| `#/compare` | Pick two units for side-by-side cards on the same scales. The summary asks "sunnier / quieter / cooler?" for the sunniest room, the loudest bedroom and the hottest room. A unit only wins when the two 90 % intervals do not overlap; otherwise the answer is "too close to call". |
| `#/capture` | A guided 2-minute walkthrough using `getUserMedia` (rear camera) and `MediaRecorder`, with a timer, step prompts and compass headings (`DeviceOrientationEvent`, with the iOS permission prompt) logged every second during window steps and on "Mark window". |

A disclaimer banner is always visible. Units with `data_kind: "synthetic"` get a **SYNTHETIC DEMO UNIT** badge.

## Privacy design

- Nothing is uploaded. The walkthrough is saved only as local downloads:
  `dwell_walkthrough_<timestamp>.webm|mp4` plus `dwell_walkthrough_<timestamp>.json` (prompt timestamps,
  compass readings, mime type, user agent).
- Audio is not recorded. The capture screen asks people not to film people, documents or screens.
- There is no analytics, no remote fonts and no CDN. The service worker (`sw.js`, generated at build time by a
  small plugin in `vite.config.ts`) only caches the app's own files. Reports are fetched network-first, with
  the cache as an offline fallback.

## Layout

`src/data/validate.js` (validator, plain JS shared with Node) · `src/data/schema.ts` (types and loading) ·
`src/geo.ts` (ENU→three.js, sun vector, slider mapping) · `src/viewer3d.ts` · `src/cards.ts` · `src/compare.ts` ·
`src/capture.ts` · `src/main.ts` (router) · `src/styles.css`.
Coordinates: report ENU (x east, y north, z up) maps to three.js as X = east, Y = up, Z = −north.

## Limitations

- There is no WebXR / AR pose capture yet, so the walkthrough has no metric scale. The video and compass log
  are inputs for the offline pipeline (capture rung 2 is future work).
- Compass headings are device-reported. They are often magnetic and uncorrected, noisy, and unavailable on
  desktop browsers.
- The 3D view is schematic. Sun patches are drawn exactly as the report gives them; the scene has no shadows
  of its own.
- The "too close to call" rule (non-overlap of 90 % intervals) is deliberately conservative and is not a
  formal test of the difference.
- Safari records `mp4`, Chrome and Firefox record `webm`. Some older iOS versions cannot use `MediaRecorder`.
