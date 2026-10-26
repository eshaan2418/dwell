"""M11 decision-study package: randomisation, simulation, format round-trip, analysis CLI (fast)."""

from __future__ import annotations

import pandas as pd
import pytest

from study import analysis, randomize
from study.randomize import all_pairs, balance_report, make_schedule
from study.schema import (
    PARTICIPANT_COLS,
    RESPONSE_COLS,
    FormatError,
    StudyData,
    annotate,
    load_data,
    write_data,
)
from study.simulate import SimParams, simulate

UNITS4 = ["U01", "U02", "U03", "U04"]
UNITS5 = UNITS4 + ["U05"]


def _ids(n):
    return [f"P{i:02d}" for i in range(1, n + 1)]


def test_schedule_balance_even_n_full_pool():
    s = make_schedule(_ids(24), all_pairs(UNITS4), k=6, seed=7)
    b = balance_report(s)
    assert len(s) == 24 * 6
    assert b["max_pair_condition_imbalance"] == 0
    assert b["participants_with_unequal_split"] == 0
    assert b["max_position_condition_imbalance"] == 0
    assert b["first_trial_condition_counts"] == {"report": 12, "video": 12}
    # each participant sees K distinct pairs; conditions alternate; probes exactly on report trials
    for _, g in s.groupby("participant_id"):
        assert g["pair_id"].nunique() == 6
        c = g.sort_values("trial")["condition"].tolist()
        assert all(a != b for a, b in zip(c, c[1:], strict=False))
    assert (s["probe"] == (s["condition"] == "report")).all()
    assert set(s.loc[s["probe"], "probe_dim"]) == {"quiet", "sunny", "cool"}
    # unit order within pair is randomised but always the pair's two units
    pairs = all_pairs(UNITS4).set_index("pair_id")
    for _, r in s.iterrows():
        assert {r["unit_a"], r["unit_b"]} == set(pairs.loc[r["pair_id"]])


def test_schedule_subset_pool_and_odd_n():
    s = make_schedule(_ids(15), all_pairs(UNITS5), k=8, seed=3)
    b = balance_report(s)
    assert b["participants_with_unequal_split"] == 0
    assert b["max_pair_condition_imbalance"] <= 1  # only the unpaired 15th participant can unbalance
    lo, hi = b["pair_exposure_range"]
    assert hi - lo <= 2


def test_schedule_reproducible_and_seed_sensitive():
    p = all_pairs(UNITS4)
    a = make_schedule(_ids(10), p, 6, seed=1)
    pd.testing.assert_frame_equal(a, make_schedule(_ids(10), p, 6, seed=1))
    assert not a.equals(make_schedule(_ids(10), p, 6, seed=2))
    with pytest.raises(ValueError):
        make_schedule(_ids(4), p, k=8)  # 4 units only give 6 pairs
    with pytest.raises(ValueError):
        make_schedule(_ids(4), p, k=5)  # K must be even


def test_randomize_cli_consent_guard(tmp_path):
    out = tmp_path / "schedule.csv"
    assert randomize.main(["--n-participants", "4", "--units", *UNITS4, "--out", str(out)]) == 2
    assert not out.exists()
    assert (
        randomize.main(["--n-participants", "4", "--units", *UNITS4, "--consent-d-confirmed", "--out", str(out)]) == 0
    )
    s = pd.read_csv(out)
    assert len(s) == 24 and s["schedule_seed"].nunique() == 1
    assert (
        randomize.main(["--n-participants", "4", "--units", *UNITS4, "--consent-d-confirmed", "--out", str(out)]) == 2
    )  # no silent overwrite


def test_format_round_trip(tmp_path):
    d = simulate(SimParams(n_participants=6, seed=11))
    write_data(d, tmp_path)
    assert pd.read_csv(tmp_path / "responses.csv").columns.tolist() == RESPONSE_COLS
    assert pd.read_csv(tmp_path / "participants.csv").columns.tolist() == PARTICIPANT_COLS
    d2 = load_data(tmp_path)
    for key in ("responses", "participants", "units_truth", "units_report"):
        a, b = getattr(d, key).reset_index(drop=True), getattr(d2, key).reset_index(drop=True)
        assert a.shape == b.shape
        for c in a.columns:
            if pd.api.types.is_numeric_dtype(a[c]) and not pd.api.types.is_bool_dtype(a[c]):
                pd.testing.assert_series_equal(a[c].astype(float), b[c].astype(float), check_names=False, rtol=1e-5)
            else:
                assert a[c].fillna("").astype(str).tolist() == b[c].fillna("").astype(str).tolist(), c
    pd.testing.assert_frame_equal(annotate(d), annotate(d2), check_dtype=False, rtol=1e-5)


def test_validation_rejects_bad_data(tmp_path):
    d = simulate(SimParams(n_participants=4, seed=2))
    bad = d.responses.copy()
    bad.loc[0, "chosen_unit"] = "U99"
    write_data(StudyData(bad, d.participants, d.units_truth, d.units_report), tmp_path)
    with pytest.raises(FormatError):
        load_data(tmp_path)
    t = d.units_truth.copy()
    t.loc[0, "consent_d"] = False
    write_data(StudyData(d.responses, d.participants, t, d.units_report), tmp_path)
    with pytest.raises(FormatError, match="consent"):
        load_data(tmp_path)


def test_ground_truth_and_tie_flag():
    d = simulate(SimParams(n_participants=2, seed=5))
    t = d.units_truth.copy()
    t[["winter_sun_h", "night_laeq_db", "summer_peak_c"]] = [
        [4.0, 25.0, 25.0],
        [0.5, 40.0, 30.0],
        [2.0, 30.0, 27.0],
        [2.0, 30.0, 27.01],
    ]
    d = StudyData(d.responses, d.participants, t, d.units_report)
    a = annotate(d)
    row = a[(a[["unit_a", "unit_b"]].isin(["U01", "U02"]).all(axis=1))].iloc[0]
    assert row["best_unit"] == "U01" and not row["tie"]  # U01 better on every dimension
    row = a[(a[["unit_a", "unit_b"]].isin(["U03", "U04"]).all(axis=1))].iloc[0]
    assert row["tie"]  # identical within measurement uncertainty


def test_simulate_analyse_recovers_strong_effect():
    d = simulate(SimParams(n_participants=30, p_base=0.5, p_report=0.95, seed=3))
    r = analysis.analyse(d, n_boot=200)
    p = r["primary_H1"]
    assert p["glmm"]["log_or"] > 0 and p["glmm"]["ci95"][0] > 0
    assert p["gee"]["log_or"] > 0
    assert p["paired_per_participant"]["mean_diff"] > 0
    # permutation test skipped for speed (n_perm=0) -> no confirmatory decision is made
    assert r["hypotheses"]["H1_report_increases_consistent_choice"]["supported"] is None
    assert r["secondary"]["overtrust_index_H2"]["report"]["index_raw"] < 0  # simulated calibrated trust


def test_analysis_without_real_data_exits_cleanly(tmp_path, capsys):
    assert analysis.main(["--data-dir", str(tmp_path)]) == 0
    assert "no real data yet" in capsys.readouterr().out


def test_analysis_refuses_simulated_data_as_real(tmp_path):
    write_data(simulate(SimParams(n_participants=4, seed=1)), tmp_path)
    assert analysis.main(["--data-dir", str(tmp_path)]) == 1


def test_questionnaire_columns_match_schema():
    import json
    from pathlib import Path

    from study.schema import PARTICIPANT_COLS, RESPONSE_COLS

    q = json.loads((Path(__file__).resolve().parents[1] / "study/materials/questionnaire.json").read_text())
    cols = set()
    for sec in q["sections"]:
        for it in sec["items"]:
            cols |= {it[k] for k in ("column", "dim_column") if k in it}
            cols |= {o["column"] for o in it.get("options", []) if isinstance(o, dict) and "column" in o}
    assert cols <= set(PARTICIPANT_COLS) | set(RESPONSE_COLS)
    assert {"w_quiet", "rank_cool", "chosen_unit", "confidence", "probe_p_a", "trust_3"} <= cols


def test_glmm_permutation_test_runs():
    a = annotate(simulate(SimParams(n_participants=10, p_base=0.5, p_report=0.95, seed=4)))
    r = analysis.glmm_permutation_test(a[~a["tie"]], n_perm=9, seed=1, workers=1)
    assert r["z_obs"] > 0 and r["n_perm"] == 9 and 0.1 - 1e-12 <= r["p_two_sided"] <= 1
