"""Data formats, loading/validation and the ground-truth definition for the M11 decision study.

Every CSV written by a real session (or by ``study.simulate``) follows the column lists below.
``study/README.md`` ("Data formats") documents the same columns for the experimenter.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

STUDY = Path(__file__).resolve().parent
DATA = STUDY / "data"

DIMS = ("quiet", "sunny", "cool")
# dimension -> (measured column in units_truth.csv, sign so that "higher z = better for the renter")
TARGET = {
    "quiet": ("night_laeq_db", -1.0),
    "sunny": ("winter_sun_h", +1.0),
    "cool": ("summer_peak_c", -1.0),
}
# Coverage factor applied to the combined standard uncertainty when flagging a measured tie.
TIE_K = 2.0
# z of the two-sided 90 % interval (reports show 90 % intervals)
Z90 = 1.6448536269514722

SCHEDULE_COLS = [
    "participant_id",
    "trial",
    "pair_id",
    "unit_a",
    "unit_b",
    "condition",
    "probe",
    "probe_dim",
    "schedule_seed",
]
RESPONSE_COLS = [
    "participant_id",
    "trial",
    "pair_id",
    "unit_a",
    "unit_b",
    "condition",
    "chosen_unit",
    "confidence",
    "probe_dim",
    "probe_p_a",
]
PARTICIPANT_COLS = [
    "participant_id",
    "session_date",
    "w_quiet",
    "w_sunny",
    "w_cool",
    "rank_quiet",
    "rank_sunny",
    "rank_cool",
    "useful_1",
    "useful_2",
    "useful_3",
    "trust_1",
    "trust_2",
    "trust_3",
    "trust_4",
    "attention_pass",
    "knows_a_unit",
    "session_complete",
    "notes",
]
TRUTH_COLS = [
    "unit_id",
    "consent_d",
    "winter_sun_h",
    "winter_sun_h_u",
    "night_laeq_db",
    "night_laeq_db_u",
    "summer_peak_c",
    "summer_peak_c_u",
    "peak_source",
]
REPORT_COLS = [
    "unit_id",
    "winter_sun_h_pred",
    "winter_sun_h_lo",
    "winter_sun_h_hi",
    "night_laeq_db_pred",
    "night_laeq_db_lo",
    "night_laeq_db_hi",
    "summer_peak_c_pred",
    "summer_peak_c_lo",
    "summer_peak_c_hi",
]
USEFUL_ITEMS = ["useful_1", "useful_2", "useful_3"]
TRUST_ITEMS = ["trust_1", "trust_2", "trust_3", "trust_4"]
REVERSE_ITEMS = {"trust_3"}  # reverse-keyed ("I would double-check everything the report said myself")

FILES = {
    "responses": "responses.csv",
    "participants": "participants.csv",
    "units_truth": "units_truth.csv",
    "units_report": "units_report.csv",
}
COLS = {
    "responses": RESPONSE_COLS,
    "participants": PARTICIPANT_COLS,
    "units_truth": TRUTH_COLS,
    "units_report": REPORT_COLS,
}


class FormatError(ValueError):
    pass


@dataclass
class StudyData:
    responses: pd.DataFrame
    participants: pd.DataFrame
    units_truth: pd.DataFrame
    units_report: pd.DataFrame

    def paths_in(self, folder: Path) -> list[Path]:
        return [folder / f for f in FILES.values()]


def _bool(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.lower().isin({"1", "true", "yes", "y"})


def write_data(d: StudyData, folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for key, fname in FILES.items():
        df = getattr(d, key)[COLS[key]]
        p = folder / fname
        df.to_csv(p, index=False, float_format="%.6g")
        out.append(p)
    return out


def load_data(folder: Path) -> StudyData:
    dfs = {}
    for key, fname in FILES.items():
        p = folder / fname
        if not p.exists():
            raise FormatError(f"missing {p}")
        df = pd.read_csv(
            p,
            dtype={
                "participant_id": str,
                "unit_id": str,
                "pair_id": str,
                "unit_a": str,
                "unit_b": str,
                "chosen_unit": str,
                "notes": str,
                "probe_dim": str,
            },
        )
        missing = [c for c in COLS[key] if c not in df.columns]
        if missing:
            raise FormatError(f"{p.name}: missing columns {missing}")
        dfs[key] = df[COLS[key]].copy()
    d = StudyData(**dfs)
    validate(d)
    return d


def validate(d: StudyData) -> None:
    r, p, t, rep = d.responses, d.participants, d.units_truth, d.units_report
    for col in ("attention_pass", "knows_a_unit", "session_complete"):
        p[col] = _bool(p[col])
    t["consent_d"] = _bool(t["consent_d"])
    r["probe_dim"] = r["probe_dim"].fillna("").astype(str).replace("nan", "")
    p["notes"] = p["notes"].fillna("").astype(str)
    if not t["consent_d"].all():
        bad = t.loc[~t["consent_d"], "unit_id"].tolist()
        raise FormatError(f"units without consent code D must not be shown: {bad}")
    units = set(t["unit_id"])
    if set(rep["unit_id"]) != units:
        raise FormatError("units_report.csv and units_truth.csv list different units")
    if not set(r["unit_a"]).union(r["unit_b"]) <= units:
        raise FormatError("responses reference units not in units_truth.csv")
    if not set(r["participant_id"]) <= set(p["participant_id"]):
        raise FormatError("responses reference participants not in participants.csv")
    if not r["condition"].isin(["video", "report"]).all():
        raise FormatError("condition must be 'video' or 'report'")
    answered = r["chosen_unit"].notna()
    ok = r.loc[answered].apply(lambda x: x["chosen_unit"] in (x["unit_a"], x["unit_b"]), axis=1)
    if not ok.all():
        raise FormatError("chosen_unit must equal unit_a or unit_b")
    conf = r["confidence"].dropna()
    if not conf.between(1, 7).all():
        raise FormatError("confidence must be 1..7")
    pr = r["probe_p_a"].dropna()
    if not pr.between(0, 100).all():
        raise FormatError("probe_p_a must be 0..100")
    if not r["probe_dim"].isin(["", *DIMS]).all():
        raise FormatError(f"probe_dim must be empty or one of {DIMS}")
    w = p[["w_quiet", "w_sunny", "w_cool"]]
    if ((w < 0).any(axis=1) | ((w.sum(axis=1) - 100).abs() > 0.5)).any():
        raise FormatError("preference points must be >= 0 and sum to 100")
    if r.duplicated(["participant_id", "trial"]).any():
        raise FormatError("duplicate (participant_id, trial) rows")


# ---------------------------------------------------------------- ground truth


def unit_z(truth: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
    """Standardise measured targets across the pool; sign so that higher = better (quieter/sunnier/cooler)."""
    z = pd.DataFrame(index=truth["unit_id"].values)
    sds = {}
    for dim, (col, sign) in TARGET.items():
        x = truth[col].to_numpy(float)
        sd = float(np.std(x, ddof=1)) if len(x) > 1 else 1.0
        sd = sd if sd > 0 else 1.0
        sds[dim] = sd
        z[dim] = sign * (x - x.mean()) / sd
    return z, sds


def annotate(d: StudyData) -> pd.DataFrame:
    """One row per answered trial with ground truth, tie flag, report-interval overlap and probe truth.

    Ground truth: for participant weights w (points / 100) the measured score of unit u is
    S_u = sum_d w_d z_ud. The preference-consistent unit is argmax S over the pair. The trial is a
    *tie* if |S_a - S_b| < TIE_K * u_S with u_S^2 = sum_d (w_d / sd_d)^2 (u_ad^2 + u_bd^2), i.e. the
    measured difference is within the expanded (k=2) measurement uncertainty.
    """
    t = d.units_truth.set_index("unit_id")
    rep = d.units_report.set_index("unit_id")
    z, sds = unit_z(d.units_truth)
    p = d.participants.set_index("participant_id")
    r = d.responses.loc[d.responses["chosen_unit"].notna()].copy()
    w = p.loc[r["participant_id"], ["w_quiet", "w_sunny", "w_cool"]].to_numpy(float) / 100.0
    za = z.loc[r["unit_a"], list(DIMS)].to_numpy()
    zb = z.loc[r["unit_b"], list(DIMS)].to_numpy()
    s_a, s_b = (w * za).sum(1), (w * zb).sum(1)
    u2 = np.zeros(len(r))
    for j, dim in enumerate(DIMS):
        col = TARGET[dim][0]
        ua = t.loc[r["unit_a"], f"{col}_u"].to_numpy(float)
        ub = t.loc[r["unit_b"], f"{col}_u"].to_numpy(float)
        u2 += (w[:, j] / sds[dim]) ** 2 * (ua**2 + ub**2)
    r["score_diff"] = s_a - s_b
    r["score_u"] = np.sqrt(u2)
    r["tie"] = np.abs(r["score_diff"]) < TIE_K * r["score_u"]
    r["best_unit"] = np.where(s_a >= s_b, r["unit_a"], r["unit_b"])
    r["consistent"] = (r["chosen_unit"] == r["best_unit"]).astype(int)
    r["report"] = (r["condition"] == "report").astype(int)
    # top-weighted dimension (ties in points broken by the forced ranking)
    ranks = p.loc[r["participant_id"], ["rank_quiet", "rank_sunny", "rank_cool"]].to_numpy(float)
    key = w * 1000 - ranks
    r["top_dim"] = np.array(DIMS)[np.argmax(key, axis=1)]
    # do the report's 90 % intervals overlap on the top dimension?
    ov = []
    for ua, ub, dim in zip(r["unit_a"], r["unit_b"], r["top_dim"], strict=True):
        col = TARGET[dim][0]
        ov.append(
            not (rep.at[ua, f"{col}_hi"] < rep.at[ub, f"{col}_lo"] or rep.at[ub, f"{col}_hi"] < rep.at[ua, f"{col}_lo"])
        )
    r["overlap_top"] = np.array(ov, dtype=int)
    # probability probe truth: is unit A better (quieter / sunnier / cooler) on probe_dim, measured?
    pa_true, ptie, p_dwell = [], [], []
    for ua, ub, dim in zip(r["unit_a"], r["unit_b"], r["probe_dim"], strict=True):
        if dim not in DIMS:
            pa_true.append(np.nan), ptie.append(False), p_dwell.append(np.nan)
            continue
        col, sign = TARGET[dim]
        diff = sign * (t.at[ua, col] - t.at[ub, col])
        u = np.hypot(t.at[ua, f"{col}_u"], t.at[ub, f"{col}_u"])
        pa_true.append(float(diff > 0))
        ptie.append(bool(abs(diff) < TIE_K * u))
        # probability implied by the report (normal approx. of the 90 % intervals)
        sa = (rep.at[ua, f"{col}_hi"] - rep.at[ua, f"{col}_lo"]) / (2 * Z90)
        sb = (rep.at[ub, f"{col}_hi"] - rep.at[ub, f"{col}_lo"]) / (2 * Z90)
        dp = sign * (rep.at[ua, f"{col}_pred"] - rep.at[ub, f"{col}_pred"])
        p_dwell.append(float(norm.cdf(dp / max(np.hypot(sa, sb), 1e-9))))
    r["probe_truth_a"] = pa_true
    r["probe_tie"] = ptie
    r["probe_p_dwell"] = p_dwell
    return r.reset_index(drop=True)


def exclusions(d: StudyData, k_expected: int | None = None) -> tuple[list[str], dict[str, str]]:
    """Pre-registered participant exclusions. Returns (kept ids, {excluded id: reason})."""
    p = d.participants
    r = d.responses
    k = k_expected or int(r.groupby("participant_id")["trial"].count().max())
    answered = r.dropna(subset=["chosen_unit"]).groupby("participant_id")["trial"].count()
    why: dict[str, str] = {}
    for _, row in p.iterrows():
        pid = row["participant_id"]
        if not row["attention_pass"]:
            why[pid] = "failed attention check"
        elif row["knows_a_unit"]:
            why[pid] = "recognised / knows a pool unit"
        elif answered.get(pid, 0) < int(np.ceil(0.75 * k)):
            why[pid] = "fewer than 75 % of pairs answered"
        elif not row["session_complete"]:
            why[pid] = "session not completed"
    kept = [pid for pid in p["participant_id"] if pid not in why]
    return kept, why
