# PROGRESS

Status legend: `todo` · `in-progress` · `done` · `blocked-with-fallback` · `awaiting-human`.
Every number lives in `results/` (see `results/INDEX.md`); this file links, it does not restate.

| Milestone | Status | Evidence |
|---|---|---|
| M0 Bootstrap + prior work | done | `docs/PRIOR_WORK.md`, `ENVIRONMENT.md`, `DECISIONS.md`, `Makefile`, `.github/workflows/ci.yml`, `Dockerfile`; `make ci` green locally (no git remote configured, D-019) |
| M1 Sensor kit + firmware + ingestion | done (hardware `awaiting-human`) | `firmware/` (pio build, host tests, no-raw-audio checker), `ingest/`, `tests/test_ingest_*`, `results/m1/target_derivation.json` |
| M2 Synthetic world + harness | done | `synth/`, `bench/synth_dataset.py`, `hybrid/evaluate.py`, frozen split `data/synthetic/world_v1_split.json`; real test-unit freeze `awaiting-human` (`make freeze-test-units`) |
| M3 Walkthrough → geometry + semantics | blocked-with-fallback (2.5D, B-002) + awaiting-human (tape-measured units) | `recon/`, `semantics/redact.py`, `results/m3/recon_synthetic.json`, `results/m3/figs/scan_quality.png` |
| M4 Geolocation, orientation, obstruction | done on synthetic + real geodata; real compass check `awaiting-human` | `locate/`, `results/m4/locate.json` |
| M5 Daylight & sun | done on synthetic; real validation `awaiting-human` | `physics/sun/`, `results/m5/sun.json`, app sun slider |
| M6 Night noise + auralization | done on synthetic; real validation `awaiting-human` | `physics/acoustics/`, `hybrid/auralize.py`, `results/m6/noise.json` (attribution, censoring) |
| M7 Summer heat | done on synthetic; real summer validation `awaiting-human` (B-005) | `physics/thermal/`, `results/m7/heat.json` |
| M8 Hidden properties + hybrid + uncertainty | done on synthetic; real adaptation `awaiting-human` | `hybrid/`, `results/m8/{comparison,hidden_properties,sobol}.json`, `results/m8/figs/` |
| M9 Wi-Fi (optional) | skipped (D-020) | — |
| M10 App | done | `app/` (lint, tests, build), `make demo`, `results/m10/demo_timing.json` |
| M11 Decision study package | done (running it `awaiting-human`) | `study/`, `results/m11/study_dryrun.json`, `results/m11/figs/` |
| M12 Integration, release, write-up | done (real-data parts `awaiting-human`) | `README.md`, `paper/paper.md`, `RESUME_BULLETS.md`, `FINAL_REVIEW.md`, `DEMO.md`, `release/`, `docs/DATASHEET.md`, `results/m12/release.json` |

## Definition of Done checklist
1. Milestones: all `done` / `blocked-with-fallback` / `awaiting-human` (above).
2. `make ci` green; `make reproduce-quick` from a clean clone (see `results/INDEX.md` and D-018); `make demo` passes.
3. Per-target answer with scale and season: `FINAL_REVIEW.md` (synthetic answered; real = 0 units, `awaiting-human`).
4. Zero unbacked numbers: `make check-numbers` (templates in `docs/templates/`).
5. Privacy: `make privacy-scan`, `make firmware` (no-raw-audio checker).
6. `FINAL_REVIEW.md` written.

## Single next action
Human: recruit units and deploy kits (`HUMAN_TODO.md` §1–§6). Agent, once ≥ 3 units have ingested data:
`make ingest UNIT=…` → `make freeze-test-units` → `make validate` → `make paper`.
