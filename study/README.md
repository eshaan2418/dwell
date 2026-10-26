# M11 decision study: protocol, session script, data formats

> **Status: pre-registration draft. No participant data exist yet.** Every number in this file comes
> from **simulated** data (`python -m study.analysis --dry-run` writes `results/m11/study_dryrun.json`,
> `data_kind = "synthetic"`). None of it is evidence about Dwell.
>
> **Ethics first.** Do not run a session until a research ethics board (REB/IRB) has approved this
> protocol and `consent_participant.md`. Participants see only units whose occupants signed
> consent code **D** (`HUMAN_TODO.md` §2). Data are stored pseudonymously (see §11).

Files in this folder:

| File | What it is |
|---|---|
| `README.md` | this protocol + session script + data formats |
| `consent_participant.md` | participant information sheet and consent form (template for the board) |
| `materials/questionnaire.md`, `materials/questionnaire.json` | every item read to participants, mapped to CSV columns |
| `randomize.py` | balanced, seeded schedule → `study/data/schedule.csv` |
| `simulate.py` | synthetic participants/responses in the real CSV format (dry run, power, tests) |
| `schema.py` | CSV formats, validation, **ground-truth definition**, exclusions |
| `models.py` | the pre-registered statistical models |
| `analysis.py` | CLI: `python -m study.analysis [--dry-run]` |
| `data/templates/` | header-only CSVs to copy into `study/data/` |

---

## 1. Aims

Does a Dwell report (per-room winter sun hours, night-time noise and summer peak temperature, each with
a 90 % interval) change renters' choices toward units that actually match their stated preferences?
And do people calibrate their trust to the uncertainty the report shows?

## 2. Pre-registered hypotheses

- **H1 (primary).** The rate of preference-consistent choices is higher with *video tour + Dwell
  report* than with *video tour only*. Test: report log-odds ratio in the mixed logistic model (§8.1).
  Supported if the 95 % credible interval lies above 0.
- **H2 (trust calibration: confidence).** In report trials, confidence is lower when the two units'
  90 % intervals overlap on the participant's top-weighted quality than when they do not. The
  over-trust index is negative. Test: MixedLM coefficient of `overlap_top` in report trials, 95 % CI
  < 0. Video-only trials, where the intervals are not shown, give a placebo contrast that should be about 0.
- **H3 (trust calibration: probabilities).** Participants' probability judgements about pairwise
  comparisons have a Brier score better than the uninformed 0.25 when scored against sensor-measured
  truth. Test: participant-cluster bootstrap 95 % CI of the Brier score < 0.25. We also report, without
  a hypothesis, how far the participants' Brier score is from the probabilities the report itself
  implies.

Exploratory (no confirmatory claim): confidence by condition; usefulness and trust scales; H1 with
trial position as a covariate; choices on tie pairs.

## 3. Design

- **Within-subject, two conditions:** `video` (video tour only) and `report` (video tour plus Dwell report).
- **N = 30 analysable participants** (target; the protocol allows 15–30, see §10). Each states
  preference weights, then completes **K pairwise comparisons** of real, consented volunteer units.
- **Pool and pairs.** The pool has at least 4 units with consent D. The pairs are all C(n, 2)
  combinations of pool units, or a curated list (`--pairs`). K = 6 needs at least 4 units; **K = 8 (preferred)
  needs at least 5 units**; K = 12 needs at least 6. Each participant sees K *distinct* pairs, half in each condition.
- **Pool curation (important).** Choose pool units whose *measured* targets differ clearly, with
  trade-offs (for example sunny but loud versus quiet but dark). Pairs whose measured difference lies within
  measurement uncertainty are "ties" and do not count toward H1 (§7). In simulated 4–5-unit pools
  drawn *at random* (uniform over city-wide ranges), 44 % of trials were ties on average (p10 22 %,
  p90 67 %; dry run). The power table assumes 20 %, which is only achievable with a **curated** pool.
  Before the first session, run `python -m study.analysis` on a pilot or `responses.csv` copy, or
  compute the pairwise measured differences, and replace near-duplicate units.
- Units are presented as A (first) and B (second). The order is randomised per trial.

## 4. Materials

- Per unit: the volunteer's 2-minute walkthrough video, blurred (faces, documents, screens, photos),
  trimmed to about 90 s, with no audio commentary and no address cues (street signs, house numbers, window views
  that identify the building are blurred). The same cut is used in both conditions.
- Per unit: the Dwell report (app view of `reports/<unit_id>/report.json`) showing the three targets
  with 90 % intervals. **Real units only**: no SYNTHETIC badge may appear. If a unit's report is
  synthetic it may not be used. The values shown are recorded in `units_report.csv`.
- `materials/questionnaire.md`: all items. A laptop or tablet that plays the videos side by side
  or sequentially, and the schedule printout for the participant's ID.

## 5. Randomisation

`python -m study.randomize --n-participants 34 --units-file study/data/units_truth.csv --k 8 --seed <S>`
(or `--units U01 U02 ... --consent-d-confirmed`). Generate the schedule **once, before session 1**,
for the maximum enrolment, and never regenerate it. The CLI refuses to overwrite without `--force`.
Record the seed. The algorithm:

1. Participants are processed in *twin blocks* of two consecutive IDs. Both twins get the same K
   pairs (the K least-exposed pairs so far, random tie-break). The twins get *complementary* condition
   splits: twin 1's report pairs are twin 2's video pairs. So for every complete block each pair
   appears equally often in each condition. Pair–condition assignment is exactly balanced for even N
   (±1 for odd N), and every participant has exactly K/2 trials per condition.
2. Conditions **alternate** trial by trial (R V R V… or V R V R…). The starting condition alternates
   across blocks and is opposite between twins. Condition is therefore balanced at every serial
   position and never confounded with fatigue or learning (a Latin-square-like counterbalancing of
   condition × position). Pair order within each condition is random.
3. A/B presentation order is random per trial.
4. Every report trial carries one probability probe. The probed quality rotates quiet → sunny → cool.

The CLI prints balance diagnostics: pair–condition imbalance, unequal splits, position imbalance,
first-trial counts, pair exposure range and probe counts. `tests/test_study.py` asserts them.

## 6. Measures

Per trial (`responses.csv`): choice, confidence 1–7, and on probe trials P(A better on `probe_dim`)
0–100. End of session (`participants.csv`): usefulness (3 items) and trust (4 items, `trust_3`
reverse-keyed) on 1–7 Likert scales, an attention check, and a recognition check. All wording is in
`materials/questionnaire.md`.

## 7. Ground truth: "preference-consistent choice"

Implemented in `study/schema.py::annotate`.

1. **Measured per-unit targets** (`units_truth.csv`, from the in-home sensors after ingest, `make validate`):
   - `winter_sun_h`: living room (main room) mean direct-sun hours/day, Dec–Feb (or the winter
     months measured), higher is better.
   - `night_laeq_db`: bedroom nightly L_Aeq 23:00–07:00, closed-window nights where the diary allows,
     lower is better.
   - `summer_peak_c`: mean daily indoor peak temperature, Jun–Aug, of the warmer measured room. If the
     deployment did not cover summer, use the hottest available period and set `peak_source =
     available`. Lower is better.
   - each with a **standard uncertainty** `<col>_u` (calibration uncertainty from co-location ⊕
     sampling SE of the mean; see `results/m1/colocation_*.json`).
2. **Standardise across the pool:** z_ud = sign_d · (x_ud − mean_d) / sd_d, with sd taken over the
   pool units and the sign set so that higher = quieter / sunnier / cooler.
3. **Score** per participant: S_u = Σ_d (w_d / 100) · z_ud with the participant's points w.
4. **Consistent** = the participant chose argmax(S_A, S_B).
5. **Tie:** |S_A − S_B| < 2 · u_S with u_S² = Σ_d (w_d / 100 / sd_d)² (u_Ad² + u_Bd²). That is, the
   measured difference lies within the expanded (k = 2) measurement uncertainty. Ties are
   participant-specific because weights differ. They are **excluded from H1** and reported
   separately (`ties_descriptive`).
6. **Probe truth:** A is better on `probe_dim` by the measured value. Probes whose single-quality
   difference is within 2·u are excluded from the Brier score (counted in `n_probe_ties_excluded`).
7. **Overlap (H2):** the report's 90 % intervals (`units_report.csv`) of A and B overlap on the
   participant's top-weighted quality. Equal points are broken by the forced ranking.
8. **Report-implied probability:** Φ(Δpred / √(σ_A² + σ_B²)) with σ = (hi − lo) / (2 · 1.645).

## 8. Analysis plan

Run with `python -m study.analysis`. All tests are two-sided at α = 0.05 or use 95 % intervals.
Analysis is on non-tie trials of non-excluded participants unless stated otherwise.

### 8.1 Primary (H1)

**Model.** Mixed-effects logistic regression `consistent ~ report + (1 | participant) + (1 | pair)`
with crossed random intercepts, fitted with statsmodels `BinomialBayesMixedGLM.fit_vb` (variational
Bayes). Priors: fixed effects N(0, 1) on the logit scale (`fe_p = 1`, weakly informative: an odds ratio
of 7.4 sits at +2 SD) and log-SD of each variance component N(0, 1). The estimate is the posterior
mean of the report log-OR (conditional on the random effects). The "VB 95 % CrI" is mean ± 1.96
posterior SD.

**Test (decision rule).** H1 is supported if the log-OR is > 0 **and** a **within-participant
permutation test** of the GLMM z-statistic (posterior mean / posterior SD) gives two-sided p < 0.05.
The test uses 1000 permutations of the condition labels among each participant's non-tie trials, which
mirrors the within-subject randomisation. **Why a permutation test:** in our simulations the VB
posterior SD was about 20 % too small, so the nominal VB 95 % CrI rejected a true null about 13 % of
the time (see the `type1` columns below). The permutation test holds its size by construction. Two
prior choices were also checked on 200 simulated studies. The default `fe_p = 2` gave 87 % CrI
coverage and +0.17 log-OR bias, because VB is unstable near separation. `fe_p = 1` gave 94 % coverage
and +0.02 bias. Laplace (`fit_map`) did not converge in most fits.

**Robustness checks:**
- GEE logit, exchangeable working correlation, clustered on participant, with **Mancl–DeRouen
  bias-reduced sandwich SE**, because the plain robust SE is anti-conservative with 15–30 clusters (also reported). This estimates
  the *population-averaged* log-OR, which is slightly smaller than the GLMM's conditional log-OR by
  construction. If every non-tie report choice is consistent (separation), GEE has no finite
  estimate and is reported as failed. The GLMM prior handles this case.
- GEE plus trial position (`+ trial`).
- Paired per-participant comparison: the rate difference (report − video), using a paired t-test
  with 95 % CI and a Wilcoxon signed-rank test. Only participants with at least 1 non-tie trial in each
  condition are included.
- Pooled rates per condition with participant-cluster bootstrap CIs (2000 resamples). This is the figure.

### 8.2 Secondary

- **Confidence:** linear mixed model `confidence ~ report + C(pair_id) + (1 | participant)` (REML).
  The 1–7 rating is treated as interval. This is a documented simplification: statsmodels has no
  mixed cumulative-link model. An ordinal sensitivity check can be added later. Pair is a fixed effect
  because there are few pairs. All trials, ties included.
- **Over-trust index (H2):** mean confidence when the intervals overlap on the top quality minus
  mean confidence when they do not, in report trials. Raw, plus MixedLM `confidence ~ overlap_top +
  (1 | participant)` with 95 % CI. The same contrast in video trials serves as a placebo. A
  calibrated participant gives an index below 0. An index of 0 or more suggests the uncertainty is
  ignored.
- **Brier (H3):** mean (p − truth)² over non-tie probes, with a participant-cluster bootstrap CI,
  compared with 0.25 (uninformed) and with the report-implied Brier. Also broken down by quality.
- **Likert:** usefulness and trust scale means (trust_3 reversed), with Cronbach's α.

### 8.3 Power (simulated; `--dry-run`)

Assumptions: P(consistent) is 60 % with video only and 75 % with the report (conditional, at random
effect 0). Participant SD is 0.5 and pair SD 0.3 on the logit scale. 20 % of trials are dropped as ties,
and K/2 trials per condition. Each cell has 500 simulated studies for GEE and paired t, and the first
200 of them also fit the GLMM. Every cell is paired with a matching **null** cell (p_report = p_video),
which gives the type-I error columns. `glmm_perm` (the primary test) is the *size-adjusted* power
P(|z_alt| > 95th percentile of |z_null|). This approximates the permutation test without running
1000 permutations per simulated study. Monte-Carlo SE is at most 2.2 points (500 sims) or 3.5 points
(200 sims).

*(copied from `results/m11/study_dryrun.json`, `power.table`)*

| N | K | units | p_video → p_report | **glmm_perm (primary)** | gee | paired_t | type-I glmm VB nominal | type-I gee | type-I paired_t | grid |
|---|---|---|---|---|---|---|---|---|---|---|
| 15 | 6 | 4 | 0.60 → 0.75 | **0.330** | 0.252 | 0.214 | 0.110 | 0.048 | 0.058 | requested |
| 20 | 6 | 4 | 0.60 → 0.75 | **0.330** | 0.298 | 0.274 | 0.135 | 0.050 | 0.046 | requested |
| 30 | 6 | 4 | 0.60 → 0.75 | **0.570** | 0.436 | 0.412 | 0.095 | 0.028 | 0.026 | requested |
| 15 | 8 | 5 | 0.60 → 0.75 | **0.385** | 0.338 | 0.312 | 0.115 | 0.052 | 0.046 | requested |
| 20 | 8 | 5 | 0.60 → 0.75 | **0.420** | 0.384 | 0.332 | 0.165 | 0.036 | 0.038 | requested |
| 30 | 8 | 5 | 0.60 → 0.75 | **0.730** | 0.580 | 0.556 | 0.125 | 0.058 | 0.048 | requested |
| 40 | 8 | 5 | 0.60 → 0.75 | **0.770** | 0.678 | 0.634 | 0.130 | 0.040 | 0.034 | extra |
| 30 | 12 | 6 | 0.60 → 0.75 | **0.795** | 0.718 | 0.672 | 0.115 | 0.058 | 0.050 | extra |
| 30 | 8 | 5 | 0.60 → 0.80 | **0.885** | 0.824 | 0.800 | 0.110 | 0.040 | 0.050 | extra |

**Reading:** no cell of the requested grid (N ≤ 30, K ≤ 8) reaches 80 % power for a +15-point effect.
The best is N = 30, K = 8 at 73 %. N = 30, K = 12 (6 units) gives 80 %, and +20 points at N = 30,
K = 8 gives 89 %. The GEE and paired-t robustness checks are less powerful, and both hold their size
(type-I error 3–6 %). The nominal VB CrI does not (10–17 %), which is why the decision uses the
permutation test. Pre-registered design: **N = 30 analysable, K = 8 (pool ≥ 5 units)**. **K = 12 if
6 consented units exist.** With only 4 units (K = 6, 57 %) the study is framed as powered for about +20
points. The power also assumes 20 % ties: an uncurated pool (about 44 % ties) loses roughly a quarter
of the informative trials, and power drops accordingly. A null H1 result from this study is weak
evidence of no effect.

### 8.4 Effect recovery check (dry run)

The dry run simulates one study in the real CSV format (`study/data/simulated/`), loads it back
through the real-data loader and validator, and analyses it. It then repeats this for 200 simulated
studies (all 200 also fit the GLMM; about 1 s each). It reports the true effect, the mean estimate,
the bias, the 95 % CI coverage and the rejection rate. True values: the GLMM targets the *conditional*
log-OR b1. GEE targets the *marginal* log-OR and the paired test the marginal risk difference, both
computed by Monte Carlo over the random effects (`simulate.true_effects`). Failed fits count as
not covering. Note that the VB CrI covers 94 % under this alternative but is anti-conservative at the
null (type-I columns above). Hence the permutation test.

*(copied from `results/m11/study_dryrun.json`, `effect_recovery`)*

Single simulated study (N = 24, K = 6, seed 20261024):

| estimand | true | estimate | 95 % interval | covers |
|---|---|---|---|---|
| glmm_conditional_log_or | +0.693 | +0.875 | [+0.227, +1.523] | True |
| gee_marginal_log_or | +0.647 | +0.912 | [-0.189, +2.013] | True |
| paired_rate_diff | +0.143 | +0.222 | [-0.025, +0.469] | True |

Primary permutation test on that study: z = 2.647, p = 0.0260 (1000 permutations). H1 decision: True.

Coverage over 200 simulated studies (tie rate mean 0.438, p10 0.222, p90 0.674):

| estimator | n | true | mean estimate | bias | empirical SD | 95 % coverage | CI excludes 0 | failed fits |
|---|---|---|---|---|---|---|---|---|
| glmm_conditional_log_or | 200 | +0.693 | +0.710 | +0.017 | 0.408 | 0.940 | 0.480 | 0 |
| gee_marginal_log_or | 200 | +0.647 | +0.750 | +0.103 | 0.562 | 0.960 | 0.280 | 0 |
| paired_rate_diff | 200 | +0.143 | +0.155 | +0.013 | 0.135 | 0.950 | 0.231 | 1 |

## 9. Exclusion criteria (pre-registered)

Participant-level, applied before any analysis (`schema.exclusions`):
1. failed the attention check (`attention_pass = FALSE`);
2. recognised or knows an occupant of a pool unit (`knows_a_unit = TRUE`);
3. answered fewer than 75 % of their scheduled pairs;
4. session not completed (`session_complete = FALSE`, for example withdrew). Their data are deleted if
   they withdraw consent. Otherwise they are excluded and counted.

Trial-level: unanswered trials are dropped. Tie trials are excluded from H1 only. Probe ties are
excluded from the Brier score. Excluded participants are listed with reasons in the results JSON.

## 10. Stopping rule

Fixed sample, no interim efficacy analyses. Enrol until **30 participants are analysable** or
`<end date>`, whichever comes first, with a hard cap of 34 enrolments. Generate the schedule for 34
IDs up front. Excluded participants are replaced by the next schedule ID. The minimum for running the
confirmatory analysis is 15 analysable participants. Below that, report descriptively only. One
optional look *for data quality only* (tie rate, format errors) after 4 participants, without
looking at H1.

## 11. Ethics notes

- **Requires REB/IRB approval before running.** Use `consent_participant.md`, adapted to the
  board's template. Get written consent before any data are collected.
- Participants view **only units with consent code D**. `randomize.py` and the analysis loader
  refuse units whose `consent_d` is not TRUE. Videos are blurred, and no addresses or identifying views are shown.
- **Pseudonymous storage:** participants are `P01…`, units `U01…`. Names exist only on signed
  consent forms, kept in `data/private/consent/study/` (git-ignored) or on paper. They are never in
  `study/data/`. `study/data/*.csv` contain no names, contact details, addresses or exact dates of
  birth. Free-text `notes` must not contain identifying information; scrub them before analysis.
  Whether coded `study/data/*.csv` may be committed or published depends on the board's approval and
  each participant's optional dataset consent. If in doubt, keep them out of the repository.
- Participants are told the units are not for rent and the reports are estimates.
- Withdrawal: delete that participant's rows from `participants.csv` and `responses.csv` and re-run.

## 12. Provenance and `data_kind`

`analysis.py` writes through `core.provenance.write_result` with `data_hash = hash_paths(<input CSVs>)`:
- dry run → `results/m11/study_dryrun.json`, `data_kind = "synthetic"`;
- real sessions → `results/m11/study_results.json`, `data_kind = "real-sensor"`. The study data are
  real human responses paired with real in-home sensor ground truth, so of the four allowed kinds
  (`synthetic`, `real-sensor`, `public-dataset`, `none`) `real-sensor` is the honest label. They are not
  synthetic, not a public dataset, and not data-free. This is a documented convention. The two kinds are
  never blended. The loader refuses to label data as real if `participants.csv` has rows marked
  `synthetic`.

Figures go to `results/m11/figs/`: `dryrun_consistency_by_condition.png`, `power_curve.png` (dry run),
and `consistency_by_condition.png` (real).

---

## 13. Session script (for the experimenter)

**Before the study (once):** ethics approval received; at least 4 (preferably 5 or more) units with consent D,
ingested and validated; `units_truth.csv` and `units_report.csv` filled in (§14); blurred video cuts
and real Dwell reports prepared per unit; schedule generated (§5) and printed per participant.

**Before each session (5 min):** open the participant's schedule rows (`participant_id` = next unused
ID). Queue the videos and reports. Have the consent form (2 copies) and the questionnaire ready.
Open the entry sheet (copies of `data/templates/responses.csv` / `participants.csv`).

**Session (about 30 min):**

1. **Welcome and consent (5 min).** "Thanks for coming. This study tests a research tool that
   estimates how quiet, sunny and hot apartments are. We're testing the tool, not you. There are no
   right answers." Go through the information sheet. Answer questions. Both sign. Write the participant
   code on both copies. Give one copy to the participant. If they decline, stop. No data are recorded.
2. **Preferences (2 min).** Read Part 1 of the questionnaire (points, then ranking). Resolve any
   points/ranking contradiction once, as instructed. Enter `w_*`, `rank_*`.
3. **Practice (1 min, not recorded).** Explain: "You'll see pairs of real apartments. For each pair
   you watch apartment A's tour, then apartment B's. For some pairs you'll also see a Dwell report
   for each apartment. Then I'll ask which you'd rather live in, at the same rent." For report
   trials, explain once, neutrally: "The report gives an estimate and a range. The true value is
   likely to be inside the range." **Do not** suggest that the report is accurate or should be used.
4. **Pairs (K × about 2.5 min).** For each schedule row in `trial` order:
   - Show A's video, then B's (`unit_a` first). If `condition = report`, show A's and B's reports
     **after** the videos and leave them visible while the participant answers.
   - Ask 2a (choice) and 2b (confidence). If `probe = True`, ask 2c for `probe_dim`. Read the wording
     for that quality, A versus B.
   - Enter `chosen_unit` (unit ID), `confidence`, `probe_dim`, `probe_p_a` straight away.
   - Stay neutral. If asked "which is better?", answer "I can't say. Please go with your own judgement."
     Do not comment on choices.
5. **End questionnaire (3 min).** Part 3 items, the attention check, the recognition question, and comments.
   Enter `useful_*`, `trust_*`, `attention_pass`, `knows_a_unit`, `notes`.
6. **Debrief (2 min).** "Thanks! The reports are research estimates. In this study we compare
   people's choices with sensor measurements from the apartments. Please don't share details of
   the apartments." Give compensation if any. Set `session_complete = TRUE` and `session_date`.
7. **After the session:** save the CSVs, check them (`python -m study.analysis` validates the format
   and prints an error if any value is out of range), and back up to the encrypted drive. File the
   signed consent form separately from the data.

**If something goes wrong:** a video fails, or the participant gets the wrong unit: leave
`chosen_unit` empty for that trial and note it. The participant wants to stop: thank them, set
`session_complete = FALSE`, and keep the data only if they agree. Otherwise delete their rows.

---

## 14. Data formats (drop real data into `study/data/`)

Copy the header-only files from `study/data/templates/` into `study/data/` and fill them in. Real
analysis runs automatically when `study/data/responses.csv` exists. `python -m study.analysis`
prints `no real data yet` and exits 0 otherwise. `study.simulate` writes exactly the same format (to
`study/data/simulated/`, never to `study/data/` itself). Booleans are `TRUE`/`FALSE` (also accepts
`1/0`, `yes/no`).

**`schedule.csv`** (written by `randomize.py`): `participant_id, trial, pair_id, unit_a, unit_b,
condition (video|report), probe (bool), probe_dim (quiet|sunny|cool|empty), schedule_seed`.

**`responses.csv`**: one row per scheduled trial.

| column | type | meaning |
|---|---|---|
| participant_id | str | `P01`… (from the schedule) |
| trial | int | 1..K, serial position |
| pair_id, unit_a, unit_b, condition | | copied from the schedule (unit_a = shown first) |
| chosen_unit | str / empty | unit ID chosen (must be unit_a or unit_b); empty = not answered |
| confidence | int 1–7 | item 2b |
| probe_dim | str / empty | copied from the schedule when probe = True |
| probe_p_a | 0–100 / empty | item 2c: P(A better than B on probe_dim), in % |

**`participants.csv`**: one row per enrolled participant (including excluded ones).
`participant_id, session_date (YYYY-MM-DD), w_quiet, w_sunny, w_cool (points, sum 100), rank_quiet,
rank_sunny, rank_cool (1–3), useful_1..3, trust_1..4 (1–7), attention_pass, knows_a_unit,
session_complete (bool), notes (free text, no identifying info)`.

**`units_truth.csv`**: one row per pool unit, sensor-measured.
`unit_id, consent_d (must be TRUE), winter_sun_h, winter_sun_h_u, night_laeq_db, night_laeq_db_u,
summer_peak_c, summer_peak_c_u, peak_source (summer|available)` (definitions in §7; `_u` = standard
uncertainty, same units).

**`units_report.csv`**: one row per pool unit, the values **shown** in its Dwell report.
`unit_id, winter_sun_h_pred, winter_sun_h_lo, winter_sun_h_hi, night_laeq_db_pred, night_laeq_db_lo,
night_laeq_db_hi, summer_peak_c_pred, summer_peak_c_lo, summer_peak_c_hi` (90 % intervals; same room
and target definitions as the truth file: living-room winter sun, bedroom closed-window night L_Aeq,
summer typical peak).

## 15. Commands

```bash
.venv/bin/python -m study.randomize --n-participants 34 --units-file study/data/units_truth.csv --k 8 --seed 20261024
.venv/bin/python -m study.simulate --out /tmp/sim --n-participants 24 --seed 1     # synthetic CSVs
.venv/bin/python -m study.analysis --dry-run        # ~13 min (8 workers): one study + 1000-perm test + 200-study coverage + power
.venv/bin/python -m study.analysis                  # real data in study/data/ (or "no real data yet")
.venv/bin/pytest -q tests/test_study.py
```
`HUMAN_TODO.md` §9 mentions `make study-analysis`. If the Makefile target does not exist yet, use the
command above.
