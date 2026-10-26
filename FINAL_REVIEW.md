# FINAL REVIEW

*Rendered from `docs/templates/FINAL_REVIEW.tmpl.md` by `make paper`; every number comes from `results/`
(see `FINAL_REVIEW.md.numbers.json`).*

## Answer to the research question (per target)

**Real-data scale: zero units so far.** No volunteer has deployed a kit yet (B-001,
`results/real/validation.json` status: awaiting-human). The question *as posed* — accuracy
against multi-week in-home sensors, and whether reports change renters' decisions — is therefore **not
answered yet**. What is answered rigorously is the synthetic, internal-consistency version. Everything
needed to answer the real version is built, tested and documented in `HUMAN_TODO.md`.

| Target | Synthetic verdict (held-out buildings) | Real-sensor verdict | Season coverage |
|---|---|---|---|
| Sun (sill-point direct-sun h/day) | **Meets target**: hybrid MAE 0.79 h (95 % CI 0.66–0.92) vs MAE ≤ 1 h; coverage 86%. The residual adds little over physics with default materials (0.82 h): the physics carries the sun prediction. | not yet measured | synthetic deployments span the year; real deployments from late October (winter sun first) |
| Night L_Aeq (closed windows) | **MAE meets target, but the result is weakly informative**: MAE 0.92 dB; coverage 96% is just above the 85–95 % band (conservative). The adaptive-interval variant is inside the band at 89%. Only 15 of 110 held-out rooms are mostly above the mic floor; on those, MAE is 2.52 dB. | not yet measured | any season |
| Daily peak indoor temperature | **Meets target only with the residual model**: hybrid MAE 1.00 °C (CI 0.78–1.26), coverage 92%. Physics with inferred properties alone is 2.41 °C, and pure ML without physics is 1.25 °C. | not yet measured; summer validation deferred (B-005) | synthetic all seasons; real summer data at the earliest next summer |

Decision study: prepared and dry-run on simulated participants only. At 30
participants × 8 pairs, the simulated power is
0.73, so the study as specified is underpowered for a 15-point effect.

## Strongest claims

1. The hybrid model is the best method on all three synthetic targets, and its intervals are close to
   nominal marginally (above). Leave-one-building-out MAE on the train split agrees with the held-out
   numbers (sun 0.65 h, noise 1.19 dB,
   heat 1.10 °C).
2. Hidden-property inference matters for heat. Removing it raises the hybrid heat MAE to
   1.57 °C, and Sobol attributes
   43% of heat-wave peak variance to glazing, frame and wall.
3. The obstruction model matters for sun. Without it the hybrid sun MAE is
   1.03 h.
4. Privacy by construction: the firmware has no raw-audio path (static check plus host tests in CI), and the
   history-wide privacy scan passes (`results/privacy/scan.json`: ok = True).

## Weakest claims

1. **All accuracy is synthetic.** The simulator encodes our own assumptions (D-012). Hidden-property accuracy is
   optimistic by construction, because the generator samples from the priors the model learns.
2. **Noise.** Most held-out bedrooms sit at the MEMS microphone floor, so the headline noise MAE mostly measures
   prediction of a floor plus occupant events. In the synthetic world, transit sources never dominate a test room
   (share 0.00).
3. **Group-conditional coverage is uneven.** For south-facing rooms, marginal CV+ sun coverage is only
   74%. Mondrian conditioning raises it to
   85%, at the cost of wider intervals. West-facing heat
   coverage is 82%. These groups contain few
   buildings, so their coverage estimates are themselves noisy.
4. Scan geometry: point-cloud window recall is
   44% on synthetic scans, so users must
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
(F1 0.40) unless the diary is used; seasonal
confounding (autumn-only real data); geodata staleness (3D massing, traffic counts); orientation from an
assumed compass error model.

## What a city-scale product would require

Real validation at scale (hundreds of units across building eras and street types) with summer data; an
AR-pose capture path (ARKit/ARCore) for metric scale; full CNOSSOS-EU road emission and city-wide traffic
volumes; calibrated class-1/2 reference meters for a noise subset; regular geodata refresh; per-group
recalibration of conformal intervals on real data; a legal review of disclosure risk (estimates must never read
as an inspection); and an on-device or self-hosted processing story that keeps videos off third-party clouds.
