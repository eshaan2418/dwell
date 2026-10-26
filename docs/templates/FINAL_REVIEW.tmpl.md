# FINAL REVIEW

*Rendered from `docs/templates/FINAL_REVIEW.tmpl.md` by `make paper`; every number comes from `results/`
(see `FINAL_REVIEW.md.numbers.json`).*

## Answer to the research question (per target)

**Real-data scale: zero units so far.** No volunteer has deployed a kit yet (B-001,
`results/real/validation.json` status: {{ real/validation.json#status }}). The question *as posed* — accuracy
against multi-week in-home sensors, and whether reports change renters' decisions — is therefore **not
answered yet**. What is answered rigorously is the synthetic, internal-consistency version. Everything
needed to answer the real version is built, tested and documented in `HUMAN_TODO.md`.

| Target | Synthetic verdict (held-out buildings) | Real-sensor verdict | Season coverage |
|---|---|---|---|
| Sun (sill-point direct-sun h/day) | **Meets target**: hybrid MAE {{ m5/sun.json#methods.hybrid.marginal.mae | .2f }} h (95 % CI {{ m5/sun.json#methods.hybrid.marginal.mae_ci95 | ci.2f }}) vs MAE ≤ 1 h; coverage {{ m5/sun.json#methods.hybrid.marginal.coverage90 | pct }}. The residual adds little over physics with default materials ({{ m5/sun.json#methods.physics_default.marginal.mae | .2f }} h): the physics carries the sun prediction. | not yet measured | synthetic deployments span the year; real deployments from late October (winter sun first) |
| Night L_Aeq (closed windows) | **MAE meets target, but the result is weakly informative**: MAE {{ m6/noise.json#methods.hybrid.marginal.mae | .2f }} dB; coverage {{ m6/noise.json#methods.hybrid.marginal.coverage90 | pct }} is just above the 85–95 % band (conservative). The adaptive-interval variant is inside the band at {{ m6/noise.json#methods.hybrid_normalised.marginal.coverage90 | pct }}. Only {{ m6/noise.json#censoring.test_rooms_above_floor | int }} of {{ m6/noise.json#censoring.test_rooms | int }} held-out rooms are mostly above the mic floor; on those, MAE is {{ m6/noise.json#above_floor.hybrid.mae | .2f }} dB. | not yet measured | any season |
| Daily peak indoor temperature | **Meets target only with the residual model**: hybrid MAE {{ m7/heat.json#methods.hybrid.marginal.mae | .2f }} °C (CI {{ m7/heat.json#methods.hybrid.marginal.mae_ci95 | ci.2f }}), coverage {{ m7/heat.json#methods.hybrid.marginal.coverage90 | pct }}. Physics with inferred properties alone is {{ m7/heat.json#methods.physics_inferred.marginal.mae | .2f }} °C, and pure ML without physics is {{ m7/heat.json#methods.pure_ml.marginal.mae | .2f }} °C. | not yet measured; summer validation deferred (B-005) | synthetic all seasons; real summer data at the earliest next summer |

Decision study: prepared and dry-run on simulated participants only. At {{ m11/study_dryrun.json#power.table.5.N | int }}
participants × {{ m11/study_dryrun.json#power.table.5.K | int }} pairs, the simulated power is
{{ m11/study_dryrun.json#power.table.5.power_glmm_perm | .2f }}, so the study as specified is underpowered for a 15-point effect.

## Strongest claims

1. The hybrid model is the best method on all three synthetic targets, and its intervals are close to
   nominal marginally (above). Leave-one-building-out MAE on the train split agrees with the held-out
   numbers (sun {{ m5/sun.json#methods.hybrid.lobo_train.mae | .2f }} h, noise {{ m6/noise.json#methods.hybrid.lobo_train.mae | .2f }} dB,
   heat {{ m7/heat.json#methods.hybrid.lobo_train.mae | .2f }} °C).
2. Hidden-property inference matters for heat. Removing it raises the hybrid heat MAE to
   {{ m7/heat.json#ablations.hybrid_minus_inference.mae | .2f }} °C, and Sobol attributes
   {{ m8/sobol.json#heat.hidden_property_share_mean | pct }} of heat-wave peak variance to glazing, frame and wall.
3. The obstruction model matters for sun. Without it the hybrid sun MAE is
   {{ m8/comparison.json#variant_ablations.sun_no_obstruction.hybrid.mae | .2f }} h.
4. Privacy by construction: the firmware has no raw-audio path (static check plus host tests in CI), and the
   history-wide privacy scan passes (`results/privacy/scan.json`: ok = {{ privacy/scan.json#ok }}).

## Weakest claims

1. **All accuracy is synthetic.** The simulator encodes our own assumptions (D-012). Hidden-property accuracy is
   optimistic by construction, because the generator samples from the priors the model learns.
2. **Noise.** Most held-out bedrooms sit at the MEMS microphone floor, so the headline noise MAE mostly measures
   prediction of a floor plus occupant events. In the synthetic world, transit sources never dominate a test room
   (share {{ m6/noise.json#attribution.share_rooms_transit_dominant | .2f }}).
3. **Group-conditional coverage is uneven.** For south-facing rooms, marginal CV+ sun coverage is only
   {{ m5/sun.json#methods.hybrid.group_coverage.g_orient.S.coverage90 | pct }}. Mondrian conditioning raises it to
   {{ m5/sun.json#methods.hybrid.mondrian.g_orient.S.coverage90 | pct }}, at the cost of wider intervals. West-facing heat
   coverage is {{ m7/heat.json#methods.hybrid.group_coverage.g_orient.W.coverage90 | pct }}. These groups contain few
   buildings, so their coverage estimates are themselves noisy.
4. Scan geometry: point-cloud window recall is
   {{ m3/recon_synthetic.json#table.nominal_120s__good__door_scale.window_recall | pct }} on synthetic scans, so users must
   confirm windows. No real tape-measured comparison exists yet.

## Novelty position (relative to `docs/PRIOR_WORK.md`)

No individual component is new: solar geometry, façade insulation, 5R1C, gradient-boosted residuals, CV+
conformal intervals, envelope inference from imagery, and low-cost sensing all have prior art. The defensible
position, worded "within the literature we searched", is the combination: an interior-walkthrough-conditioned
prior over hidden envelope properties, propagated jointly into per-room sun, noise and heat predictions with
coverage-checked intervals, and a privacy-preserving in-home validation protocol. That claim stays
provisional until real-data coverage is shown.

## Privacy risks

- Walkthrough frames can contain faces, mail, screens and photos. Redaction fails closed (frames are dropped
  when detectors are unavailable), but OCR- and face-detector recall is imperfect. Figures use synthetic scenes only.
- Re-identification from released aggregates (orientation + floor band + age band) is low but non-zero in small
  buildings, so real rows are released only with consent code R.
- The sensor kit stores dB levels, which still reveal occupancy patterns. The consent form says so, and raw logs
  stay in `data/private/`.

## Threats to validity

Simulator–reality gap; convenience sample of volunteers (likely Toronto, rental, mid-rise); sensor placement
effects (sill point vs room); mic floor censoring; window-open nights detected with a weak heuristic
(F1 {{ m1/target_derivation.json#open_window_heuristic_validation.f1 | .2f }}) unless the diary is used; seasonal
confounding (autumn-only real data); geodata staleness (3D massing, traffic counts); orientation from an
assumed compass error model.

## What a city-scale product would require

Real validation at scale (hundreds of units across building eras and street types) with summer data; an
AR-pose capture path (ARKit/ARCore) for metric scale; full CNOSSOS-EU road emission and city-wide traffic
volumes; calibrated class-1/2 reference meters for a noise subset; regular geodata refresh; per-group
recalibration of conformal intervals on real data; a legal review of disclosure risk (estimates must never read
as an inspection); and an on-device or self-hosted processing story that keeps videos off third-party clouds.
