# Datasheet — Dwell room-level dataset

Following the "Datasheets for Datasets" questions (Gebru et al.), abbreviated.

**Motivation.** Evaluate whether a phone walkthrough + public geodata can predict per-room lived conditions
(direct sun at the main window, night-time indoor noise, daily peak temperature) against in-home sensors.

**Composition.**
- `dwell_rooms_synthetic.csv`: one row per room of the synthetic world `world_v1` (procedural Toronto-like
  apartments simulated with assumptions in `synth/`); targets derived from simulated sensor minutes with the
  same code as real data. Not real homes.
- `dwell_rooms_real.csv` (only once volunteers exist and consented to release, code R): one row per room with
  aggregated targets, coarse location (orientation, floor band, building-age band, building type) and season.
  No addresses, coordinates, unit numbers, raw sensor logs, audio (none is ever recorded), video, frames or
  exact geometry.

**Collection process.** ESP32 kits (BH1750 lux, SHT31/BME280 temp/RH, INMP441 dB-only levels) on the main
window sill (light, sound) with the temperature probe on an interior wall, 2–4 weeks per unit, 24 h
co-location calibration of all kits beforehand; window diary for open-window nights. Protocol:
`HUMAN_TODO.md`, `firmware/README.md`.

**Known limitations.** MEMS microphone self-noise (~33 dBA) censors quiet bedrooms (column
`frac_minutes_at_mic_floor`); sun target is defined at the sill point and is affected by blinds use; season
coverage of real data is whatever months the deployments ran (column `season_start_month`); small number of
units → wide confidence intervals; volunteers are a convenience sample (friends/family), not representative
of Toronto's rental stock.

**Consent and ethics.** Written consent per unit with separate scopes (S, V, R, F, D); withdrawal honoured
by deleting the unit and regenerating the release. Research use requires ethics-board approval.

**Licence.** Code MIT-style per repository; derived geodata features carry OSM (ODbL) and City of Toronto
(Open Government Licence – Toronto) attribution; weather from ECCC (Open Government Licence – Canada) and
NASA POWER.
