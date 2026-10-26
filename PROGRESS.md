# PROGRESS

Status legend: `todo` · `in-progress` · `done` · `blocked-with-fallback` · `awaiting-human`.
Every number lives in `results/` (see `results/INDEX.md`); this file links, it does not restate.

| Milestone | Status | Evidence |
|---|---|---|
| M0 Bootstrap + prior work | in-progress | `docs/PRIOR_WORK.md`, `ENVIRONMENT.md`, `DECISIONS.md` D-001…D-016, `Makefile`, `.github/workflows/ci.yml`, `Dockerfile` |
| M1 Sensor kit + firmware + ingestion | done (hardware `awaiting-human`) | `firmware/` (pio build, host tests, no-raw-audio checker), `ingest/`, `tests/test_ingest_*`, `results/m1/target_derivation.json` |
| M2 Synthetic world + harness | done | `synth/`, `bench/synth_dataset.py`, `hybrid/evaluate.py`, frozen split `data/synthetic/world_v1_split.json`; real test-unit freeze `awaiting-human` (`bench/freeze_real_test_units.py`) |
| M3 Walkthrough → geometry + semantics | blocked-with-fallback / awaiting-human | `recon/` (floor plan from point cloud, manual floor plan, COLMAP wrapper), `semantics/redact.py`, `results/m3/recon_synthetic.json`; tape-measured real accuracy `awaiting-human` |
| M4 Geolocation, orientation, obstruction | done on synthetic + real geodata; real compass check `awaiting-human` | `locate/` (OSM, Toronto 3D massing, counts, GTFS), `results/m4/locate.json` |
| M5 Daylight & sun | in-progress | `physics/sun/`, `results/m5/sun.json` (synthetic); real `awaiting-human` |
| M6 Night noise + auralization | in-progress | `physics/acoustics/`, `hybrid/auralize.py`, `results/m6/noise.json` (synthetic) |
| M7 Summer heat | in-progress | `physics/thermal/`, `results/m7/heat.json` (synthetic) |
| M8 Hidden properties + hybrid + uncertainty | in-progress | `hybrid/priors.py`, `hybrid/conformal.py`, `hybrid/sensitivity.py`, `results/m8/` |
| M9 Wi-Fi (optional) | todo (skipped unless time) | — |
| M10 App | in-progress (agent) | `app/` |
| M11 Decision study package | in-progress (agent) | `study/` |
| M12 Integration, release, write-up | todo | — |

## Current plan (M5–M8 synthetic evaluation)
1. `bench/m8_hybrid.py`: method comparison per target (physics default / inferred / hybrid / pure ML / single-purpose),
   CV+ intervals, group-conditional + Mondrian coverage, ablations (−each feature family, −inference, −obstruction, −transit).
2. `bench/train_models.py` → model bundle; `bench/m8_sobol.py` → Sobol shares over test units.
3. `bench/make_report.py` / `bench/demo.py` → report bundles for the app; `make demo`.
4. Templates → README / paper / bullets with `bench/check_numbers.py`.

## Single next action
Finish the M8 run (`make m5-m8`), then train models and generate demo reports.
