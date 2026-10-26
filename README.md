# Dwell

**What is it like to *live* here?** From a 2-minute phone walkthrough plus public geodata, Dwell predicts
per-room direct sun across the year, night-time noise, and summer heat — each with an uncertainty range —
and is built to be validated against weeks of in-home sensor measurements.

> **Not an inspection.** Dwell produces estimates with uncertainty. It is not a building inspection, a
> mould/structural assessment, or a legal disclosure.

> **Status (honest).** Every accuracy number below is on **synthetic** apartments (procedural generator +
> simulated sensors, `synth/`). Real-home validation is prepared — firmware, protocol, ingestion, analysis —
> and is waiting for volunteer deployments (`HUMAN_TODO.md`, `DATA_STATUS.md`).

## Pipeline

```
 phone walkthrough ──► redaction (faces/text/screens) ──► geometry: SfM point cloud │ manual floor plan
                                                              │   (rooms, windows, orientation)
 public geodata: Toronto 3D massing / OSM, traffic counts, TTC GTFS, ECCC + NASA POWER weather
                                                              ▼
 hidden-property prior  (glazing · frame seal · wall)  ──►  physics ensemble
        sun: NREL SPA + horizon ray casting + aperture      noise: road/transit sources → façade R → room
        heat: ISO 13790 5R1C with window solar gains
                                                              ▼
            learned residual (gradient boosting)  ──►  CV+ conformal intervals (building-grouped)
                                                              ▼
       report bundle (JSON + illustrative "night listen" audio) ──► local-first web app (viewer · capture)
                                                              ▲
            validation: ESP32 kits (lux · temp/RH · dB levels only, never audio) for 2–4 weeks
```

## Accuracy summary (synthetic held-out buildings)

| Target | Hybrid MAE (95 % CI) | Physics with inferred properties | Single-purpose tool | 90 % interval coverage | Target set in advance |
|---|---|---|---|---|---|
| Direct-sun hours/day at main-window sill | 0.79 (0.66–0.92) | 0.82 | 1.48 | 86% | MAE ≤ 1 h |
| Night L_Aeq 23–07, closed windows (dB) | 0.92 (0.77–1.09) | 1.18 | 1.39 | 96% | ≤ 3 dB |
| Daily peak indoor temperature (°C) | 1.00 (0.78–1.26) | 2.41 | 5.08 | 92% | ≤ 1.5 °C |

Caveats: synthetic results reflect the simulator's assumptions; the noise target is dominated by the
microphone self-noise floor in quiet rooms (only 15 of
110 held-out rooms are mostly above it). Details: `paper/paper.md`,
`results/INDEX.md`.

## Example (synthetic) report

`make demo` generates reports for two contrasting synthetic units and a hypothetical unit on real Toronto
geodata, then builds the app (`app/`). Each room card shows winter/summer sun hours, night noise with
windows closed and ajar, typical-summer and heat-wave peak temperature, each with a 90 % interval, plus
"what we couldn't see" (glazing/frame/wall posteriors and their share of the uncertainty) and an
illustrative night-listen clip. Script for a live demo: `DEMO.md`.

## Quick start

```
make setup            # uv venv + pinned deps
make test             # unit/golden tests (physics vs analytic cases, ingestion contract, privacy)
make firmware         # ESP32 DSP host tests + no-raw-audio checker (+ `make firmware-build` with PlatformIO)
make reproduce-quick  # synthetic world → all experiments → figures → number check
make demo             # reports + app build
make paper            # render README/paper/bullets from results/ (zero hand-typed numbers)
```

Real data: follow `HUMAN_TODO.md` (recruit, consent, build kits, calibrate, deploy, film), then
`make ingest UNIT=U03`, `make recon UNIT=U03`, `make freeze-test-units` (once), `make validate`.

## Repository map

`firmware/` sensor kit · `ingest/` logs → targets · `recon/` walkthrough → geometry · `semantics/` redaction ·
`locate/` geodata & orientation · `physics/` sun, acoustics, thermal · `hybrid/` priors, residual models,
conformal, Sobol, report · `synth/` synthetic world · `bench/` experiments · `study/` decision study ·
`app/` web app · `paper/` draft · `results/` every number.

## Limitations

Synthetic-only accuracy so far; MEMS mic floor censors quiet bedrooms; real deployments from late October
give winter data first (heat validation later); single-aspect manual floor plans; no AR metric scale yet;
convenience sample of volunteers. See `FINAL_REVIEW.md`.

## Licences and attribution

Map data © OpenStreetMap contributors (ODbL). Contains information licensed under the Open Government
Licence – Toronto (3D Massing, traffic counts, TTC GTFS). Weather: Environment and Climate Change Canada
(Open Government Licence – Canada) and NASA POWER. Face-detection model: OpenCV Zoo YuNet.
