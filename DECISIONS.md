# DECISIONS

Dated decisions with rationale. IDs are referenced from code/docs.

- **D-001 (2026-10-24) Python 3.12 + uv, single repo-level package set.** Top-level packages follow the
  prescribed layout (`ingest/ recon/ semantics/ locate/ physics/ hybrid/ bench/ study/`) plus `core/`
  (schema, provenance) and `synth/` (synthetic world) — the layout lists `data/synthetic/` for data but
  no home for generator code.
- **D-002 (2026-10-24) "CI" = GitHub Actions workflow + identical local `make ci`.** The repo has no
  remote; CI green is asserted by running `make ci` locally (same commands as `.github/workflows/ci.yml`).
- **D-003 (2026-10-24) Fallback rungs chosen in M0** (see ENVIRONMENT.md): real sensor data = rung 3
  (synthetic + public data only; real validation `awaiting-human`); capture = rung 2/3 (plain video +
  known-object scale; manual floor plan); recon = rung 2 (COLMAP sparse on CPU via Homebrew; no CUDA →
  no Gaussian splatting / COLMAP dense); obstruction = rung 1/2 (Toronto 3D massing + OSM); noise sources
  = rung 1/2 (Toronto counts + GTFS where available, OSM class proxies otherwise); ML = CPU.
- **D-004 (2026-10-24) Weather = ECCC TORONTO CITY hourly (temp/RH) + NASA POWER hourly (CERES
  irradiance GHI/DNI/DHI + clear-sky).** ECCC hourly has no irradiance; NASA POWER is free and global.
  Sunshine probability per hour = clip(DNI / DNI_clear, 0, 1). 2016–2025 merged file committed
  (`data/weather/toronto_hourly_2016_2025.csv.gz`) so reproduction does not need network.
- **D-005 (2026-10-24) Coordinates/azimuths.** Local ENU metres; azimuth clockwise from true north;
  facade azimuth = outward normal.
- **D-006 (2026-10-24) Sun target defined at the sensor point.** Sensors can only validate light at
  their location, so the validated quantity is "direct-sun hours/day at the main-window sill point"
  (placement guide fixes the location). The app also reports a room-level quantity (hours with
  ≥ 0.1 m² sunlit glazing), which is not directly validated.
- **D-007 (2026-10-24) Road emission model.** A compact rolling+propulsion per-vehicle A-weighted
  sound-power approximation (not full CNOSSOS-EU coefficients) with an explicit uncertain
  `emission_offset_db`; residual models absorb bias. Full CNOSSOS-EU is future work.
- **D-008 (2026-10-24) Facade insulation incidence term** `C_inc` ∈ [0, 6] dB (diffuse vs normal
  plane-wave incidence, derived from first principles), default 3 dB, treated as uncertain in Sobol
  analysis instead of quoting a standard's constant we could not verify offline.
- **D-009 (2026-10-24) Thermal = ISO 13790 5R1C per room, party walls adiabatic** in the fast model.
- **D-010 (2026-10-24) Noise target.** Primary = nightly L_Aeq,23–07 (as specified); secondary = L_A90 and
  5 %-trimmed L_Aeq. The MEMS mic self-noise (~33 dBA) censors quiet bedrooms; predictions are compared
  after energetically adding the kit's estimated floor (documented in evaluation).
- **D-011 (2026-10-24) App = local-first web app (PWA)** instead of native Android/iOS: no Android SDK /
  Java on this machine, and a PWA runs on both platforms' browsers with camera capture and no cloud.
  AR poses (WebXR) are future work → capture rung 2.
- **D-012 (2026-10-24) Synthetic world assumptions** (`synth/priors.py`, `synth/truth.py`) are
  assumptions, not Toronto statistics. Synthetic results measure internal consistency and the value
  of each modelling component under these assumptions only; they are never blended with real results.
- **D-013 (2026-10-24) Contribution wording** adopted from docs/PRIOR_WORK.md "What is and isn't new":
  no "first" claims; scoped "to our knowledge, within the literature we searched" statements.
