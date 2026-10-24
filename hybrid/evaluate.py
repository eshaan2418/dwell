"""Evaluation harness: methods, leave-one-building-out (LOBO) CV+, metrics with building bootstrap CIs.

Every method produces a point prediction and a 90 % interval. Learned methods are refit in each
LOBO fold of the TRAIN split (jackknife+ at building level); fixed (physics/baseline) methods use
their own LOBO residuals for calibration. Test-split rows are never used for fitting or calibration.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.ensemble import HistGradientBoostingRegressor

from hybrid.conformal import building_weights, cv_plus_intervals
from hybrid.features import FAMILIES, feature_columns

ALPHA = 0.1
GROUPINGS = ("g_orient", "g_floor", "g_era")


def gbm() -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=250, min_samples_leaf=20,
                                         l2_regularization=1.0, random_state=0)


@dataclass
class Method:
    name: str
    kind: str  # fixed | residual | direct
    base_col: str | None = None  # fixed prediction / physics base for residual
    families: tuple[str, ...] = FAMILIES
    scale_col: str | None = None  # normalised conformal scores


def fit_predict(m: Method, tr: pd.DataFrame, te: pd.DataFrame) -> np.ndarray:
    if m.kind == "fixed":
        return te[m.base_col].to_numpy(float)
    cols = feature_columns(tr, m.families)
    model = gbm()
    if m.kind == "residual":
        model.fit(tr[cols], tr["y"] - tr[m.base_col])
        return te[m.base_col].to_numpy(float) + model.predict(te[cols])
    model.fit(tr[cols], tr["y"])
    return model.predict(te[cols])


def _scale(m: Method, df: pd.DataFrame) -> np.ndarray:
    if m.scale_col is None:
        return np.ones(len(df))
    s = df[m.scale_col].to_numpy(float)
    return s + np.nanmedian(s) + 1e-3


def lobo(m: Method, train: pd.DataFrame, test: pd.DataFrame, max_workers: int = 8) -> dict[str, np.ndarray]:
    """LOBO over train buildings. Returns OOF predictions on train, and per-fold predictions at test rows."""
    blds = train["building"].unique()
    oof = np.full(len(train), np.nan)
    at_test = np.zeros((len(test), len(train)))
    tr_b = train["building"].to_numpy()

    def one(b: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        idx = tr_b == b
        tr, ho = train[~idx], train[idx]
        both = pd.concat([ho, test])
        p = fit_predict(m, tr, both)
        return idx, p[: idx.sum()], p[idx.sum():]

    if m.kind == "fixed":
        oof = train[m.base_col].to_numpy(float)
        at_test = np.repeat(test[m.base_col].to_numpy(float)[:, None], len(train), axis=1)
        full = test[m.base_col].to_numpy(float)
        return {"oof": oof, "at_test": at_test, "full": full}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for idx, p_ho, p_te in ex.map(one, blds):
            oof[idx] = p_ho
            at_test[:, idx] = p_te[:, None]
    full = fit_predict(m, train, test)
    return {"oof": oof, "at_test": at_test, "full": full}


def bootstrap_ci(df: pd.DataFrame, stat: Callable[[pd.DataFrame], float], n: int = 1000, seed: int = 0) -> list[float]:
    """Percentile CI resampling BUILDINGS (the unit of independence)."""
    rng = np.random.default_rng(seed)
    groups = {b: g for b, g in df.groupby("building")}
    keys = list(groups)
    vals = []
    for _ in range(n):
        pick = rng.choice(len(keys), len(keys))
        vals.append(stat(pd.concat([groups[keys[i]] for i in pick])))
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


def metrics(df: pd.DataFrame, y: str = "y") -> dict[str, float | list[float]]:
    err = df["pred"] - df[y]
    cover = (df[y] >= df["lo"]) & (df[y] <= df["hi"])
    sigma = np.maximum((df["hi"] - df["lo"]) / (2 * norm.ppf(1 - ALPHA / 2)), 1e-6)
    z = (df[y] - df["pred"]) / sigma
    crps = sigma * (z * (2 * norm.cdf(z) - 1) + 2 * norm.pdf(z) - 1 / np.sqrt(np.pi))
    unit_mae = df.assign(ae=err.abs()).groupby("unit")["ae"].mean()
    room = df.groupby("room").agg(pred=("pred", "mean"), y=(y, "mean"), building=("building", "first"))
    return {
        "n_rows": int(len(df)), "n_units": int(df["unit"].nunique()), "n_buildings": int(df["building"].nunique()),
        "mae": float(err.abs().mean()), "rmse": float(np.sqrt((err**2).mean())), "bias": float(err.mean()),
        "mae_ci95": bootstrap_ci(df, lambda d: float((d["pred"] - d[y]).abs().mean())),
        "mae_unit_mean": float(unit_mae.mean()),
        "mae_room_mean_target": float((room["pred"] - room["y"]).abs().mean()),
        "coverage90": float(cover.mean()),
        "coverage90_ci95": bootstrap_ci(df, lambda d: float(((d[y] >= d["lo"]) & (d[y] <= d["hi"])).mean())),
        "width90": float((df["hi"] - df["lo"]).mean()), "crps_gauss": float(crps.mean()),
    }


def run_methods(train: pd.DataFrame, test: pd.DataFrame, methods: list[Method], mondrian: bool = True
                ) -> tuple[dict, dict[str, pd.DataFrame]]:
    results, frames = {}, {}
    for m in methods:
        r = lobo(m, train, test)
        s_tr, s_te = _scale(m, train), _scale(m, test)
        scores = np.abs(train["y"].to_numpy(float) - r["oof"]) / s_tr
        ok = np.isfinite(scores)
        lo, hi = cv_plus_intervals(r["at_test"][:, ok], scores[ok], s_te, train["building"].to_numpy()[ok], ALPHA)
        out = test.assign(pred=r["full"], lo=lo, hi=hi)
        res = {"marginal": metrics(out), "group_coverage": {}}
        for g in GROUPINGS:
            res["group_coverage"][g] = {str(k): {"coverage90": float(((v.y >= v.lo) & (v.y <= v.hi)).mean()),
                                                 "n_rows": int(len(v)), "n_units": int(v.unit.nunique())}
                                        for k, v in out.groupby(g)}
        if mondrian:
            res["mondrian"] = {}
            for g in GROUPINGS:
                mask = test[g].to_numpy()[:, None] == train[g].to_numpy()[ok][None, :]
                mlo, mhi = cv_plus_intervals(r["at_test"][:, ok], scores[ok], s_te, train["building"].to_numpy()[ok],
                                             ALPHA, cal_mask=mask)
                mo = test.assign(pred=r["full"], lo=mlo, hi=mhi)
                res["mondrian"][g] = {str(k): {"coverage90": float(((v.y >= v.lo) & (v.y <= v.hi)).mean()),
                                               "width90": float((v.hi - v.lo).mean()), "n_units": int(v.unit.nunique())}
                                      for k, v in mo.groupby(g)}
        res["lobo_train"] = {"mae": float(np.nanmean(np.abs(train["y"].to_numpy(float) - r["oof"]))),
                             "n_buildings": int(train["building"].nunique())}
        results[m.name] = res
        frames[m.name] = out
    return results, frames


__all__ = ["Method", "run_methods", "metrics", "bootstrap_ci", "building_weights"]
