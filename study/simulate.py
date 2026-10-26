"""Simulated participants and responses with known effect sizes (dry run / power / tests).

Produces a :class:`study.schema.StudyData` whose CSVs are byte-for-byte the same format a real session
produces (``responses.csv``, ``participants.csv``, ``units_truth.csv``, ``units_report.csv``).
Everything here is SYNTHETIC: units, participants and answers are invented.

Generative model (conditional on random effects; logit scale):

    logit P(consistent) = b0 + b1 * report + u_participant + v_pair,
    b0 = logit(p_base), b1 = logit(p_report) - logit(p_base),
    u ~ N(0, sd_participant^2), v ~ N(0, sd_pair^2).

The chosen unit is the measured-best unit if "consistent", else the other one. Confidence (1-7) is a
rounded latent normal with a report effect, a consistent-choice effect and (report trials) an
interval-overlap effect; probability probes are a noisy, gain-scaled copy of the report-implied
probability.

CLI::

    python -m study.simulate --out study/data/simulated --n-participants 24 --seed 1
"""

from __future__ import annotations

import argparse
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from study.randomize import all_pairs, make_schedule
from study.schema import PARTICIPANT_COLS, RESPONSE_COLS, Z90, StudyData, annotate, write_data


@dataclass
class SimParams:
    n_participants: int = 24
    k: int = 6
    n_units: int | None = None  # default: smallest pool with >= k pairs (4 for K=6, 5 for K=8)
    p_base: float = 0.60  # P(consistent | video-only) at u = v = 0
    p_report: float = 0.75  # P(consistent | report)      at u = v = 0
    sd_participant: float = 0.5
    sd_pair: float = 0.3
    conf_base: float = 4.3
    conf_report: float = 0.4
    conf_consistent: float = 0.3
    conf_overlap_report: float = -0.6  # calibrated trust: less confident when the 90 % intervals overlap
    conf_sd_participant: float = 0.7
    conf_sd_resid: float = 1.0
    probe_gain: float = 0.6  # participants' probabilities = sigmoid(gain*logit(p_dwell) + noise)
    probe_noise: float = 1.0
    p_attention_fail: float = 0.0
    seed: int = 1

    @property
    def b0(self) -> float:
        return _logit(self.p_base)

    @property
    def b1(self) -> float:
        return _logit(self.p_report) - _logit(self.p_base)

    def pool_size(self) -> int:
        if self.n_units:
            return self.n_units
        n = 2
        while n * (n - 1) // 2 < self.k:
            n += 1
        return max(n, 4)


def _logit(p: float) -> float:
    return math.log(p / (1 - p))


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def true_effects(sp: SimParams, n_mc: int = 400_000, seed: int = 12345) -> dict[str, float]:
    """Conditional (GLMM) and population-averaged (GEE / raw-rate) truths implied by ``sp``."""
    rng = np.random.default_rng(seed)
    re = rng.normal(0, sp.sd_participant, n_mc) + rng.normal(0, sp.sd_pair, n_mc)
    p0 = float(_sigmoid(sp.b0 + re).mean())
    p1 = float(_sigmoid(sp.b0 + sp.b1 + re).mean())
    return {
        "conditional_log_or": sp.b1,
        "marginal_p_video": p0,
        "marginal_p_report": p1,
        "marginal_log_or": _logit(p1) - _logit(p0),
        "marginal_risk_diff": p1 - p0,
    }


def make_units(n: int, rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame]:
    ids = [f"U{i + 1:02d}" for i in range(n)]
    truth = pd.DataFrame(
        {
            "unit_id": ids,
            "consent_d": True,
            "winter_sun_h": rng.uniform(0.2, 4.5, n).round(2),
            "winter_sun_h_u": 0.3,
            "night_laeq_db": rng.uniform(24, 42, n).round(1),
            "night_laeq_db_u": 1.5,
            "summer_peak_c": rng.uniform(25, 31, n).round(2),
            "summer_peak_c_u": 0.4,
            "peak_source": "summer",
        }
    )
    rep = {"unit_id": ids}
    for col, sig in (("winter_sun_h", 0.6), ("night_laeq_db", 2.5), ("summer_peak_c", 0.9)):
        pred = truth[col].to_numpy() + rng.normal(0, sig, n)
        half = Z90 * sig * rng.uniform(0.8, 1.2, n)
        if col == "winter_sun_h":
            pred = np.clip(pred, 0, None)
        rep[f"{col}_pred"] = pred.round(2)
        rep[f"{col}_lo"] = (np.clip(pred - half, 0, None) if col == "winter_sun_h" else pred - half).round(2)
        rep[f"{col}_hi"] = (pred + half).round(2)
    return truth, pd.DataFrame(rep)


def _weights(rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    w = rng.dirichlet([2.0, 2.0, 2.0]) * 20
    w5 = np.floor(w).astype(int)
    for i in np.argsort(-(w - w5))[: 20 - w5.sum()]:
        w5[i] += 1
    pts = w5 * 5
    rank = np.empty(3, int)
    rank[np.lexsort((rng.random(3), -pts))] = np.arange(1, 4)
    return pts, rank


def simulate(sp: SimParams) -> StudyData:
    rng = np.random.default_rng(sp.seed)
    truth, rep = make_units(sp.pool_size(), rng)
    pids = [f"P{i + 1:02d}" for i in range(sp.n_participants)]
    pairs = all_pairs(truth["unit_id"].tolist())
    sched = make_schedule(pids, pairs, sp.k, seed=sp.seed)

    prow = []
    for pid in pids:
        pts, rank = _weights(rng)
        trait = rng.normal(0, 0.8)
        lik = lambda m, t=trait: int(np.clip(np.rint(m + t + rng.normal(0, 0.7)), 1, 7))  # noqa: E731
        prow.append(
            {
                "participant_id": pid,
                "session_date": "2026-01-01",
                "w_quiet": pts[0],
                "w_sunny": pts[1],
                "w_cool": pts[2],
                "rank_quiet": rank[0],
                "rank_sunny": rank[1],
                "rank_cool": rank[2],
                "useful_1": lik(5.2),
                "useful_2": lik(5.0),
                "useful_3": lik(4.8),
                "trust_1": lik(4.8),
                "trust_2": lik(4.6),
                "trust_3": 8 - lik(4.6),
                "trust_4": lik(4.7),
                "attention_pass": bool(rng.random() >= sp.p_attention_fail),
                "knows_a_unit": False,
                "session_complete": True,
                "notes": "synthetic",
            }
        )
    participants = pd.DataFrame(prow)

    # draft responses (choice placeholder = unit_a) to get ground truth / overlaps from the same code path
    resp = sched.drop(columns=["probe", "schedule_seed"]).copy()
    resp["chosen_unit"] = resp["unit_a"]
    resp["confidence"] = 4
    resp["probe_p_a"] = np.where(resp["probe_dim"] != "", 50.0, np.nan)
    draft = StudyData(resp, participants, truth, rep)
    ann = annotate(draft)

    u = dict(zip(pids, rng.normal(0, sp.sd_participant, len(pids)), strict=True))
    pair_ids = sorted(pairs["pair_id"])
    v = dict(zip(pair_ids, rng.normal(0, sp.sd_pair, len(pair_ids)), strict=True))
    cu = dict(zip(pids, rng.normal(0, sp.conf_sd_participant, len(pids)), strict=True))
    eta = sp.b0 + sp.b1 * ann["report"] + ann["participant_id"].map(u) + ann["pair_id"].map(v)
    cons = rng.random(len(ann)) < _sigmoid(eta.to_numpy())
    other = np.where(ann["best_unit"] == ann["unit_a"], ann["unit_b"], ann["unit_a"])
    resp["chosen_unit"] = np.where(cons, ann["best_unit"], other)
    lat = (
        sp.conf_base
        + sp.conf_report * ann["report"]
        + sp.conf_consistent * cons
        + sp.conf_overlap_report * ann["report"] * ann["overlap_top"]
        + ann["participant_id"].map(cu)
        + rng.normal(0, sp.conf_sd_resid, len(ann))
    )
    resp["confidence"] = np.clip(np.rint(lat), 1, 7).astype(int)
    pd_ = ann["probe_p_dwell"].clip(0.01, 0.99)
    lp = sp.probe_gain * np.log(pd_ / (1 - pd_)) + rng.normal(0, sp.probe_noise, len(ann))
    probe = np.round(_sigmoid(lp) * 20) * 5  # participants answer in steps of 5 %
    resp["probe_p_a"] = np.where(ann["probe_dim"] != "", probe, np.nan)
    return StudyData(resp[RESPONSE_COLS].reset_index(drop=True), participants[PARTICIPANT_COLS], truth, rep)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True, help="output folder (never study/data itself)")
    for f, val in asdict(SimParams()).items():
        if f == "n_units":
            ap.add_argument("--n-units", type=int, default=None)
        else:
            ap.add_argument(f"--{f.replace('_', '-')}", type=type(val), default=val)
    a = ap.parse_args(argv)
    if a.out.resolve() == (Path(__file__).resolve().parent / "data"):
        ap.error("refusing to write simulated data into study/data/ (that folder is for real sessions)")
    kw = {f: getattr(a, f) for f in asdict(SimParams())}
    paths = write_data(simulate(SimParams(**kw)), a.out)
    print("wrote", *[str(p) for p in paths], sep="\n  ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
