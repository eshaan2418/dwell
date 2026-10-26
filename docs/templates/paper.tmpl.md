# Dwell: Predicting Per-Room Sun, Night Noise and Summer Heat from a Phone Walkthrough and Public Geodata — a Hybrid Physics–ML System with Calibrated Uncertainty

*Draft. Every number in this document is generated from `results/` by `make paper`; the source file of
each value is listed in `paper/paper.md.numbers.json`. All quantitative results in this draft are on
**synthetic data** (procedurally generated apartments with simulated sensors); real in-home validation
is prepared but not yet run (Section 8).*

## Abstract

Renters choose homes after a short visit at one time of day in one season. We ask whether a two-minute
phone walkthrough plus public geodata can predict what living in a home is like — per-room direct sun
across the year, night-time indoor noise, and summer peak temperature — accurately enough, and with
calibrated uncertainty, to inform that choice. Dwell combines fast physics (solar geometry with
obstruction ray casting; façade sound insulation and indoor level; an ISO 13790 5R1C thermal network)
with a learned prior over properties a video cannot see (glazing, frame airtightness, wall construction),
learned residual corrections, and building-grouped conformal prediction intervals. On a held-out set of
{{ m5/sun.json#methods.hybrid.marginal.n_buildings | int }} synthetic buildings, the hybrid model's error is
{{ m5/sun.json#methods.hybrid.marginal.mae | .2f }} h/day for sill-point direct-sun hours,
{{ m6/noise.json#methods.hybrid.marginal.mae | .2f }} dB for night L_Aeq (as measured by the sensor), and
{{ m7/heat.json#methods.hybrid.marginal.mae | .2f }} °C for daily peak indoor temperature, with empirical 90 %
interval coverage of {{ m5/sun.json#methods.hybrid.marginal.coverage90 | pct }},
{{ m6/noise.json#methods.hybrid.marginal.coverage90 | pct }} and {{ m7/heat.json#methods.hybrid.marginal.coverage90 | pct }}.
These are internal-consistency results under our simulator's assumptions, not evidence of real-world
accuracy. We also contribute a privacy-preserving sensor kit (on-device dB levels only), its validation
protocol, and a pre-registered renter decision study, both ready to run.

## 1 Introduction

A listing photo and a ten-minute viewing reveal little about winter light, 2 am street noise, or a July
heat wave. Each of these depends on geometry the visit does show (window size and orientation, floor,
neighbouring buildings, streets) and on properties it does not (glazing, seals, wall mass). Dwell turns
the visible part into physics inputs, infers the invisible part probabilistically, and reports each
prediction with an interval whose coverage is checked empirically.

**Research question.** From a short phone walkthrough and public geodata, can a physics-informed learned
model predict per-room daylight, night-time noise and peak summer temperature accurately enough — with
calibrated uncertainty — to change a renter's decision, as validated against multi-week in-home sensor
measurements? Targets set in advance: direct-sun MAE ≤ 1 h/day, night L_Aeq MAE ≤ 3 dB, daily peak
temperature MAE ≤ 1.5 °C, and 90 % intervals with 85–95 % empirical coverage.

**Contributions** (wording scoped per the prior-work review, `docs/PRIOR_WORK.md`):
1. A prior over hidden envelope properties conditioned on interior-walkthrough cues and public building
   metadata, propagated through façade-acoustic and thermal models with Sobol sensitivity analysis.
   Prior work infers envelope parameters (window-to-wall ratio, age, energy class) from exterior street
   imagery at building scale; within the literature we searched we did not find work conditioning such
   priors on an interior scan and propagating them jointly to room-level acoustic and thermal predictions.
2. A hybrid physics + learned-residual model with building-grouped CV+ conformal intervals, applied jointly
   to per-room sun, night noise and summer heat. Hybrid physics–ML with conformal calibration has been
   shown for building indoor temperature; our contribution is the joint, room-level, phone-scan setting
   with coverage reported per target and per group.
3. A privacy-preserving in-home validation protocol (ESP32 kit; light, temperature/RH, and dB levels
   computed on-device with a CI-enforced no-raw-audio guarantee) and a decision-study package.

## 2 Prior work

Summarised from `docs/PRIOR_WORK.md` (entries verified by web search on 2026-10-24): consumer sun tools
(sun-path AR apps, Shadowmap / Redfin Sunscore for listings), strategic noise maps (EU END, CNOSSOS-EU,
US national transportation noise map) and noise scores for housing, scanning apps (RoomPlan, Polycam,
Matterport), daylight/thermal simulation (Radiance, DAYSIM, Ladybug/Honeybee, EnergyPlus, ISO 13790/52016
RC models, pvlib/NREL SPA), envelope inference from street imagery, grey-box building models, hybrid
physics–ML with conformal uncertainty, and low-cost indoor sensing. No individual component is new; the
combination and the room-level, phone-scan, multi-target validation are what we test.

## 3 System

**Capture and geometry.** A guided walkthrough (local-first web app; no upload) yields frames, which pass a
fail-closed redaction layer (faces, text/documents, screens, framed photos) before storage. Geometry comes
from SfM point clouds when available, with a door-height metric scale, or a manual floor plan (fallback). On
synthetic scans of held-out rooms at the nominal 2-minute setting with door-height scale, the median
room-area error is {{ m3/recon_synthetic.json#table.nominal_120s__good__door_scale.room_area_abs_rel_err_median | pct1 }}
and point-cloud window detection recall is only
{{ m3/recon_synthetic.json#table.nominal_120s__good__door_scale.window_recall | pct }} (precision
{{ m3/recon_synthetic.json#table.nominal_120s__good__door_scale.window_precision | pct }}), so the app asks the
user to confirm windows (Figure 5).

**Location and orientation.** Buildings come from the City of Toronto 3D Massing (fallback: OSM
footprints × levels), roads from OSM with Toronto midblock counts, and streetcar frequencies from TTC GTFS.
Facade azimuth is the averaged compass reading snapped to the nearest footprint edge normal: median error
{{ m4/locate.json#orientation.footprint_snap.median_abs_deg | .1f }}° vs
{{ m4/locate.json#orientation.compass_averaged.median_abs_deg | .1f }}° for the compass alone (synthetic,
assumed compass error model).

**Physics.** *Sun:* NREL SPA solar position; per-window horizon profiles from extruded footprints (exact for
prisms); closed-form sunlit aperture through reveals and overhangs; tree canopies with seasonal porosity;
hourly sunshine probability from NASA POWER DNI/clear-sky DNI. *Noise:* road (hourly flow × light/heavy
sound power) and transit pass-by line sources, ISO 9613-1 air absorption, Maekawa screening over buildings,
octave-band composite façade insulation (glazing, frames, leaks, mass-law walls), diffuse-field indoor level
with Sabine absorption. *Heat:* ISO 13790 5R1C per room driven by ECCC hourly temperature and solar gains
through the same window model.

## 4 Hidden-property inference

A Dirichlet-smoothed Bayesian network: P(glazing | era, building type) × Π P(cue | glazing) for pane-count
reflections, low-e tint and frame material; P(frame | glazing) × P(draft cue | frame); P(wall | type, era) ×
wall-thickness and radiator/brick cues. On held-out synthetic units, glazing accuracy is
{{ m8/hidden_properties.json#full.glazing_acc | pct }} (no cues: {{ m8/hidden_properties.json#no_cues.glazing_acc | pct }};
no metadata: {{ m8/hidden_properties.json#no_metadata.glazing_acc | pct }}; default "double glazing":
{{ m8/hidden_properties.json#default_materials.glazing_acc | pct }}) and wall-type accuracy is
{{ m8/hidden_properties.json#full.wall_acc | pct }} (default: {{ m8/hidden_properties.json#default_materials.wall_acc | pct }}).
Because the generator encodes our assumed priors, these accuracies are optimistic by construction for the
metadata part.

**Sensitivity.** Normalised total-effect Sobol shares over held-out rooms attribute on average
{{ m8/sobol.json#noise.hidden_property_share_mean | pct }} of night-noise prediction variance and
{{ m8/sobol.json#heat.hidden_property_share_mean | pct }} of heat-wave peak-temperature variance to the three
hidden properties (the rest to traffic volume, emission, incidence term, internal gains, blinds, wall U-value;
Figure 4). These shares drive the app's "what we couldn't see" explanations.

## 5 Hybrid models and uncertainty

For each target, a gradient-boosting residual model is trained on physics ensemble outputs plus geometry,
metadata, geodata and weather features (target minus physics ensemble mean). Intervals: CV+ with 16
building-grouped folds and building-weighted quantiles; Mondrian variants condition on orientation, floor band
and building age. Baselines: single-purpose tools (sun path without obstructions; city-noise-map style
façade level minus a generic insulation; outdoor daily maximum temperature), physics with default materials,
physics with inferred properties, and pure ML without physics features.

## 6 Synthetic evaluation

**Data.** {{ m8/hidden_properties.json#n_train_units | int }} training and {{ m8/hidden_properties.json#n_test_units | int }}
test units (frozen by building, checksum in `data/synthetic/world_v1_split.json`), 21-day simulated deployments
with 2025 Toronto weather. The simulator deliberately includes effects the fast physics omits (cloud
intermittency, blinds, occupant noise, mic self-noise, party-wall heat exchange, window opening, sensor
placement), so residual learning is non-trivial — but its magnitudes are our assumptions.

**Targets derived like real data.** The lux→sun rule was calibrated on separate synthetic units; its own
error against simulator truth is {{ m1/target_derivation.json#validation.daily_sun_hours_abs_err_mean_h | .2f }}
h/day. The sensor-only open-window heuristic is weak (F1 {{ m1/target_derivation.json#open_window_heuristic_validation.f1 | .2f }}),
hence the protocol's window diary.

**Results (Table 1, Figures 1–3).**

| Target | Single-purpose tool | Physics, default | Physics, inferred | Pure ML | Hybrid | Hybrid coverage (90 % PI) |
|---|---|---|---|---|---|---|
| Sun (h/day) | {{ m5/sun.json#methods.single_purpose_baseline.marginal.mae | .2f }} | {{ m5/sun.json#methods.physics_default.marginal.mae | .2f }} | {{ m5/sun.json#methods.physics_inferred.marginal.mae | .2f }} | {{ m5/sun.json#methods.pure_ml.marginal.mae | .2f }} | {{ m5/sun.json#methods.hybrid.marginal.mae | .2f }} ({{ m5/sun.json#methods.hybrid.marginal.mae_ci95 | ci.2f }}) | {{ m5/sun.json#methods.hybrid.marginal.coverage90 | pct }} |
| Night L_Aeq (dB) | {{ m6/noise.json#methods.single_purpose_baseline.marginal.mae | .2f }} | {{ m6/noise.json#methods.physics_default.marginal.mae | .2f }} | {{ m6/noise.json#methods.physics_inferred.marginal.mae | .2f }} | {{ m6/noise.json#methods.pure_ml.marginal.mae | .2f }} | {{ m6/noise.json#methods.hybrid.marginal.mae | .2f }} ({{ m6/noise.json#methods.hybrid.marginal.mae_ci95 | ci.2f }}) | {{ m6/noise.json#methods.hybrid.marginal.coverage90 | pct }} |
| Peak temp (°C) | {{ m7/heat.json#methods.single_purpose_baseline.marginal.mae | .2f }} | {{ m7/heat.json#methods.physics_default.marginal.mae | .2f }} | {{ m7/heat.json#methods.physics_inferred.marginal.mae | .2f }} | {{ m7/heat.json#methods.pure_ml.marginal.mae | .2f }} | {{ m7/heat.json#methods.hybrid.marginal.mae | .2f }} ({{ m7/heat.json#methods.hybrid.marginal.mae_ci95 | ci.2f }}) | {{ m7/heat.json#methods.hybrid.marginal.coverage90 | pct }} |

*MAE per room-day (room-night for noise) on held-out synthetic buildings; parentheses: 95 % CI from a
building bootstrap.*

**Noise censoring.** Only {{ m6/noise.json#censoring.test_rooms_above_floor | int }} of
{{ m6/noise.json#censoring.test_rooms | int }} held-out rooms have nights mostly above the microphone self-noise
floor; for them the hybrid MAE is {{ m6/noise.json#above_floor.hybrid.mae | .2f }} dB. The noise result therefore
mostly measures how well we predict a noise floor plus occupant events, and the intrusive-noise estimate
shown to users is a physics ensemble whose interval is not empirically calibrated.

**Ablations (Table 2).** Each row refits the hybrid residual model without one input family, or replaces
a physics component, and reports held-out MAE.

| Hybrid variant | Sun (h/day) | Night L_Aeq (dB) | Peak temp (°C) |
|---|---|---|---|
| Full hybrid | {{ m5/sun.json#methods.hybrid.marginal.mae | .2f }} | {{ m6/noise.json#methods.hybrid.marginal.mae | .2f }} | {{ m7/heat.json#methods.hybrid.marginal.mae | .2f }} |
| − geometry features | {{ m5/sun.json#ablations.hybrid_minus_geometry.mae | .2f }} | {{ m6/noise.json#ablations.hybrid_minus_geometry.mae | .2f }} | {{ m7/heat.json#ablations.hybrid_minus_geometry.mae | .2f }} |
| − building metadata | {{ m5/sun.json#ablations.hybrid_minus_meta.mae | .2f }} | {{ m6/noise.json#ablations.hybrid_minus_meta.mae | .2f }} | {{ m7/heat.json#ablations.hybrid_minus_meta.mae | .2f }} |
| − geodata features | {{ m5/sun.json#ablations.hybrid_minus_geo.mae | .2f }} | {{ m6/noise.json#ablations.hybrid_minus_geo.mae | .2f }} | {{ m7/heat.json#ablations.hybrid_minus_geo.mae | .2f }} |
| − weather features | {{ m5/sun.json#ablations.hybrid_minus_weather.mae | .2f }} | {{ m6/noise.json#ablations.hybrid_minus_weather.mae | .2f }} | {{ m7/heat.json#ablations.hybrid_minus_weather.mae | .2f }} |
| − hidden-property inference (default materials as physics base) | n/a (sun does not depend on them) | {{ m6/noise.json#ablations.hybrid_minus_inference.mae | .2f }} | {{ m7/heat.json#ablations.hybrid_minus_inference.mae | .2f }} |
| − obstruction model | {{ m8/comparison.json#variant_ablations.sun_no_obstruction.hybrid.mae | .2f }} | — | — |
| − transit sources | — | {{ m8/comparison.json#variant_ablations.noise_no_transit.hybrid.mae | .2f }} | — |
| − all physics features (pure ML) | {{ m5/sun.json#methods.pure_ml.marginal.mae | .2f }} | {{ m6/noise.json#methods.pure_ml.marginal.mae | .2f }} | {{ m7/heat.json#methods.pure_ml.marginal.mae | .2f }} |

Three readings. (i) For sun, the physics does almost all the work: the residual improves on physics with
default materials only marginally ({{ m5/sun.json#methods.physics_default.marginal.mae | .2f }} → {{ m5/sun.json#methods.hybrid.marginal.mae | .2f }} h/day),
while removing the obstruction model costs much more. (ii) For heat, the physics alone is biased
({{ m7/heat.json#methods.physics_inferred.marginal.bias | .2f }} °C mean error with inferred properties), and
pure ML is competitive. The hybrid is best, and hidden-property inference is its most valuable input. (iii) For
noise, the hybrid improves on physics mainly by learning the microphone floor and occupant events. Removing
transit sources has little effect because, in the synthetic world, no held-out room is transit-dominated (share
{{ m6/noise.json#attribution.share_rooms_transit_dominant | .2f }}). This is a property of our generator and should
not be read as a statement about Toronto streetcar corridors.

**Leave-one-building-out.** On the train split, LOBO MAE of the hybrid is
{{ m5/sun.json#methods.hybrid.lobo_train.mae | .2f }} h/day, {{ m6/noise.json#methods.hybrid.lobo_train.mae | .2f }} dB and
{{ m7/heat.json#methods.hybrid.lobo_train.mae | .2f }} °C over {{ m5/sun.json#methods.hybrid.lobo_train.n_buildings | int }}
buildings; for pure ML it is {{ m5/sun.json#methods.pure_ml.lobo_train.mae | .2f }}, {{ m6/noise.json#methods.pure_ml.lobo_train.mae | .2f }}
and {{ m7/heat.json#methods.pure_ml.lobo_train.mae | .2f }}.

**Group-conditional coverage (Table 3).** Marginal coverage hides uneven groups. By façade orientation
(N / E / S / W), the hybrid's empirical 90 % coverage with marginal CV+ intervals and with Mondrian
(orientation-conditional) intervals is:

| Target | Marginal CV+: N / E / S / W | Mondrian: N / E / S / W |
|---|---|---|
| Sun | {{ m5/sun.json#methods.hybrid.group_coverage.g_orient.N.coverage90 | pct }} / {{ m5/sun.json#methods.hybrid.group_coverage.g_orient.E.coverage90 | pct }} / {{ m5/sun.json#methods.hybrid.group_coverage.g_orient.S.coverage90 | pct }} / {{ m5/sun.json#methods.hybrid.group_coverage.g_orient.W.coverage90 | pct }} | {{ m5/sun.json#methods.hybrid.mondrian.g_orient.N.coverage90 | pct }} / {{ m5/sun.json#methods.hybrid.mondrian.g_orient.E.coverage90 | pct }} / {{ m5/sun.json#methods.hybrid.mondrian.g_orient.S.coverage90 | pct }} / {{ m5/sun.json#methods.hybrid.mondrian.g_orient.W.coverage90 | pct }} |
| Noise | {{ m6/noise.json#methods.hybrid.group_coverage.g_orient.N.coverage90 | pct }} / {{ m6/noise.json#methods.hybrid.group_coverage.g_orient.E.coverage90 | pct }} / {{ m6/noise.json#methods.hybrid.group_coverage.g_orient.S.coverage90 | pct }} / {{ m6/noise.json#methods.hybrid.group_coverage.g_orient.W.coverage90 | pct }} | {{ m6/noise.json#methods.hybrid.mondrian.g_orient.N.coverage90 | pct }} / {{ m6/noise.json#methods.hybrid.mondrian.g_orient.E.coverage90 | pct }} / {{ m6/noise.json#methods.hybrid.mondrian.g_orient.S.coverage90 | pct }} / {{ m6/noise.json#methods.hybrid.mondrian.g_orient.W.coverage90 | pct }} |
| Heat | {{ m7/heat.json#methods.hybrid.group_coverage.g_orient.N.coverage90 | pct }} / {{ m7/heat.json#methods.hybrid.group_coverage.g_orient.E.coverage90 | pct }} / {{ m7/heat.json#methods.hybrid.group_coverage.g_orient.S.coverage90 | pct }} / {{ m7/heat.json#methods.hybrid.group_coverage.g_orient.W.coverage90 | pct }} | {{ m7/heat.json#methods.hybrid.mondrian.g_orient.N.coverage90 | pct }} / {{ m7/heat.json#methods.hybrid.mondrian.g_orient.E.coverage90 | pct }} / {{ m7/heat.json#methods.hybrid.mondrian.g_orient.S.coverage90 | pct }} / {{ m7/heat.json#methods.hybrid.mondrian.g_orient.W.coverage90 | pct }} |

South-facing sun is the clearest under-coverage. South windows have the largest and most weather-dependent
sun hours, so a single marginal score quantile is too narrow for them. Mondrian conditioning fixes most of it, at
the cost of wider intervals (mean south width {{ m5/sun.json#methods.hybrid.mondrian.g_orient.S.width90 | .2f }} h).
Each group holds only a handful of buildings, so these per-group estimates carry wide sampling error. The app
currently shows marginal room-level intervals; switching it to orientation-conditional intervals is planned work.

## 7 Sensor protocol

**Kit.** ESP32 dev board, BH1750 lux sensor (sill, facing up), SHT31 or BME280 temperature/RH probe on a
cable (interior wall, shaded, 1.1–1.7 m), and an INMP441 I²S MEMS microphone. The firmware applies an IEC 61672
A-weighting filter on-device and logs only levels: 1-s L_Aeq (optional), and per-minute L_Aeq, L_Amax and L_A90
(optionally octave bands). Audio sample buffers live only inside the level DSP and are never written to the SD card
or sent over Wi-Fi. A static checker in CI verifies that raw I²S samples reach only the DSP functions, and host
tests check the A-weighting response against the IEC table and the level statistics against analytic cases.
Time comes from NTP when Wi-Fi is available; between syncs the firmware keeps time on the ESP32's system clock.

**Calibration.** All kits are co-located for 24 h before deployment, covering a quiet night, with a reference
tone or pink-noise level from a class-2 meter or a calibrated phone app. The co-location run gives per-kit offsets
for temperature, dB and lux, and the kit's own noise floor. Inter-kit agreement is written to `results/m1/`.
That report does not exist yet, because no kits have been built.

**Placement and diary.** One kit per main room (bedroom + living room minimum) on the sill of the largest
window for 2–4 weeks. Occupants keep a one-tap window/blind diary, because the sensor-only open-window heuristic
is weak (above).

**Targets.** Direct-sun hours/day at the sill come from lux thresholding against a clear-sky beam model behind
glass (D-014). Night L_Aeq,23–07 is computed on closed-window nights, with the kit floor added energetically to
predictions (D-010). Daily peak indoor temperature comes from the wall probe. Evaluation splits by unit and
building, freezes the real test units with a checksum once three exist, and bootstraps CIs over buildings.

**Privacy.** Addresses, videos and raw logs stay in a git-ignored private directory. Released data are per-room
aggregates with coarse location only (orientation, floor band, age band), and real rows are included only with
release consent. Synthetic rows are released now (`release/`, `docs/DATASHEET.md`).

## 8 Real-world validation and decision study (prepared, not yet run)

**Real validation.** `make validate` evaluates the frozen model bundle against ingested real targets per room,
with leave-one-building-out conformal recalibration on real residuals, building-bootstrap CIs, and the months
covered by the data stated per target. Its current status is
"{{ real/validation.json#status }}" with zero units.

**Decision study.** Within-subject design: participants state weights for quiet, sun and coolness, then choose
between pairs of real consented units, first with a video tour only and then with a video tour plus the Dwell
report (order and pairs randomised). The ground truth for each pair is which unit better matches the participant's
stated preferences according to sensor data. The primary outcome is the preference-consistent choice rate,
analysed with a mixed-effects logistic regression (participant and pair random effects). Secondary outcomes are
confidence, perceived usefulness and trust calibration (do people over-trust narrow intervals?). The full analysis
runs on simulated participants. A simulation-based power analysis shows that
{{ m11/study_dryrun.json#power.table.5.N | int }} participants with {{ m11/study_dryrun.json#power.table.5.K | int }}
pairs each give power {{ m11/study_dryrun.json#power.table.5.power_glmm_perm | .2f }} for a 15-point improvement, below the
conventional 0.8. Power reaches {{ m11/study_dryrun.json#power.table.7.power_glmm_perm | .2f }} with
{{ m11/study_dryrun.json#power.table.7.K | int }} pairs, so the study should use more pairs per participant than the
brief's minimum.

## 9 Limitations, privacy and ethics

All accuracy numbers are synthetic; they bound internal consistency under our assumptions (priors in
`synth/priors.py`, behaviours in `synth/truth.py`) and say nothing yet about Toronto homes. The MEMS microphone
floor (~33 dBA) censors quiet bedrooms. Real deployments starting in autumn give no summer data for months.
Volunteers will be a convenience sample. Dwell is not an inspection; reports say so. Privacy: addresses,
videos and raw logs stay in a git-ignored private directory; the firmware never stores or transmits audio;
frames are redacted fail-closed; released data are aggregated with coarse location only; a history-wide
privacy scan runs in CI.

## Figures

All figures show synthetic data and are regenerated by `make figures` (`bench/figures.py`).

![Figure 1](../results/m8/figs/method_mae.png)

*Figure 1. MAE by method and target.*

![Figure 2](../results/m8/figs/coverage.png)

*Figure 2. Interval coverage vs nominal.*

![Figure 3](../results/m8/figs/pred_vs_measured.png)

*Figure 3. Room-mean predicted vs sensor-derived targets.*

![Figure 4](../results/m8/figs/sobol_shares.png)

*Figure 4. Variance shares by hidden property / input.*

![Figure 5](../results/m3/figs/scan_quality.png)

*Figure 5. Scan-quality ablation.*

![Figure 6](../results/m11/figs/power_curve.png)

*Figure 6. Decision-study power.*
