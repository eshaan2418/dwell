"""Evaluation harness: methods, leave-one-building-out (LOBO) CV+, metrics with building bootstrap CIs.

Every method produces a point prediction and a 90 % interval. Learned methods are refit in each of
K=16 building-grouped folds of the TRAIN split (CV+); fixed (physics/baseline) methods use their train
residuals. Leave-one-building-out (LOBO) MAE on the train split is reported for the headline methods.
Test-split rows are never used for fitting or calibration.
"""

from __future__ import annotations

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
    return HistGradientBoostingRegressor(
        max_depth=3, learning_rate=0.05, max_iter=250, min_samples_leaf=20, l2_regularization=1.0, random_state=0
    )


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


def fold_of(buildings: np.ndarray, k: int | None, seed: int = 0) -> np.ndarray:
    """Building -> fold id. k=None means leave-one-building-out."""
    u = np.unique(buildings)
    if k is None or k >= len(u):
        f = {b: i for i, b in enumerate(u)}
    else:
        perm = np.random.default_rng(seed).permutation(len(u))
        f = {u[i]: j % k for j, i in enumerate(perm)}
    return np.array([f[b] for b in buildings])


def lobo(
    m: Method, train: pd.DataFrame, test: pd.DataFrame, max_workers: int = 4, k: int | None = None
) -> dict[str, np.ndarray]:
    """Building-grouped CV over the train split (k folds; k=None -> leave-one-building-out). Returns OOF
    predictions on train and, for every train row, the prediction at each test row of the model that held it out."""
    folds = fold_of(train["building"].to_numpy(), k)
    blds = np.unique(folds)
    oof = np.full(len(train), np.nan)
    at_test = np.zeros((len(test), len(train)))
    tr_b = folds

    def one(b: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        idx = tr_b == b
        tr, ho = train[~idx], train[idx]
        both = pd.concat([ho, test])
        p = fit_predict(m, tr, both) if len(both) else np.zeros(0)
        return idx, p[: idx.sum()], p[idx.sum() :]

    if m.kind == "fixed":
        oof = train[m.base_col].to_numpy(float)
        at_test = np.repeat(test[m.base_col].to_numpy(float)[:, None], len(train), axis=1)
        full = test[m.base_col].to_numpy(float)
        return {"oof": oof, "at_test": at_test, "full": full}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for idx, p_ho, p_te in ex.map(one, blds):
            oof[idx] = p_ho
            at_test[:, idx] = p_te[:, None]
    full = fit_predict(m, train, test) if len(test) else np.zeros(0)
    return {"oof": oof, "at_test": at_test, "full": full}


def bootstrap_ci(df: pd.DataFrame, values: np.ndarray, n: int = 1000, seed: int = 0) -> list[float]:
    """Percentile CI of a row-mean statistic, resampling BUILDINGS (the unit of independence)."""
    rng = np.random.default_rng(seed)
    codes, uniq = pd.factorize(df["building"])
    sums = np.bincount(codes, weights=values, minlength=len(uniq))
    cnts = np.bincount(codes, minlength=len(uniq)).astype(float)
    pick = rng.integers(0, len(uniq), (n, len(uniq)))
    stats = sums[pick].sum(1) / cnts[pick].sum(1)
    return [float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))]


def metrics(df: pd.DataFrame, y: str = "y") -> dict[str, float | list[float]]:
    err = df["pred"] - df[y]
    cover = (df[y] >= df["lo"]) & (df[y] <= df["hi"])
    sigma = np.maximum((df["hi"] - df["lo"]) / (2 * norm.ppf(1 - ALPHA / 2)), 1e-6)
    z = (df[y] - df["pred"]) / sigma
    crps = sigma * (z * (2 * norm.cdf(z) - 1) + 2 * norm.pdf(z) - 1 / np.sqrt(np.pi))
    unit_mae = df.assign(ae=err.abs()).groupby("unit")["ae"].mean()
    room = df.groupby("room").agg(pred=("pred", "mean"), y=(y, "mean"), building=("building", "first"))
    return {
        "n_rows": int(len(df)),
        "n_units": int(df["unit"].nunique()),
        "n_buildings": int(df["building"].nunique()),
        "mae": float(err.abs().mean()),
        "rmse": float(np.sqrt((err**2).mean())),
        "bias": float(err.mean()),
        "mae_ci95": bootstrap_ci(df, err.abs().to_numpy(float)),
        "mae_unit_mean": float(unit_mae.mean()),
        "mae_room_mean_target": float((room["pred"] - room["y"]).abs().mean()),
        "coverage90": float(cover.mean()),
        "coverage90_ci95": bootstrap_ci(df, cover.to_numpy(float)),
        "width90": float((df["hi"] - df["lo"]).mean()),
        "crps_gauss": float(crps.mean()),
    }


def _fixed_interval(
    pred: np.ndarray, scores: np.ndarray, s_te: np.ndarray, cal_b: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    w = building_weights(cal_b)
    q = min((1 - ALPHA) * (1 + 1 / len(np.unique(cal_b))), 1.0)
    from hybrid.conformal import weighted_quantile

    half = weighted_quantile(scores[None, :], w, q)[0]
    return pred - half * s_te, pred + half * s_te


CV_FOLDS = 16


def lobo_mae(m: Method, train: pd.DataFrame) -> dict[str, float]:
    """True leave-one-building-out MAE on the train split (no intervals)."""
    r = lobo(m, train, train.iloc[:0], k=None)
    return {
        "mae": float(np.nanmean(np.abs(train["y"].to_numpy(float) - r["oof"]))),
        "n_buildings": int(train["building"].nunique()),
    }


def run_methods(
    train: pd.DataFrame,
    test: pd.DataFrame,
    methods: list[Method],
    mondrian: bool = True,
    k: int | None = CV_FOLDS,
    lobo_for: tuple[str, ...] = (),
) -> tuple[dict, dict[str, pd.DataFrame]]:
    results, frames = {}, {}
    for m in methods:
        r = lobo(m, train, test, k=k)
        s_tr, s_te = _scale(m, train), _scale(m, test)
        scores = np.abs(train["y"].to_numpy(float) - r["oof"]) / s_tr
        ok = np.isfinite(scores)
        cal_b = train["building"].to_numpy()[ok]
        if m.kind == "fixed":  # same prediction in every fold -> closed form (pred +- q * s)
            lo, hi = _fixed_interval(r["full"], scores[ok], s_te, cal_b)
        else:
            lo, hi = cv_plus_intervals(r["at_test"][:, ok], scores[ok], s_te, cal_b, ALPHA)
        out = test.assign(pred=r["full"], lo=lo, hi=hi)
        res = {"marginal": metrics(out), "group_coverage": {}}
        for g in GROUPINGS:
            res["group_coverage"][g] = {
                str(k): {
                    "coverage90": float(((v.y >= v.lo) & (v.y <= v.hi)).mean()),
                    "n_rows": int(len(v)),
                    "n_units": int(v.unit.nunique()),
                }
                for k, v in out.groupby(g)
            }
        if mondrian:
            res["mondrian"] = {}
            for g in GROUPINGS:
                mask = test[g].to_numpy()[:, None] == train[g].to_numpy()[ok][None, :]
                if m.kind == "fixed":
                    mlo, mhi = np.empty(len(test)), np.empty(len(test))
                    for gv in np.unique(test[g].to_numpy()):
                        ti = test[g].to_numpy() == gv
                        ci = mask[np.argmax(ti)]
                        if ci.sum() < 10:
                            ci = np.ones_like(ci)
                        mlo[ti], mhi[ti] = _fixed_interval(r["full"][ti], scores[ok][ci], s_te[ti], cal_b[ci])
                else:
                    mlo, mhi = cv_plus_intervals(r["at_test"][:, ok], scores[ok], s_te, cal_b, ALPHA, cal_mask=mask)
                mo = test.assign(pred=r["full"], lo=mlo, hi=mhi)
                res["mondrian"][g] = {
                    str(k): {
                        "coverage90": float(((v.y >= v.lo) & (v.y <= v.hi)).mean()),
                        "width90": float((v.hi - v.lo).mean()),
                        "n_units": int(v.unit.nunique()),
                    }
                    for k, v in mo.groupby(g)
                }
        res["cv_train"] = {
            "mae": float(np.nanmean(np.abs(train["y"].to_numpy(float) - r["oof"]))),
            "folds": k or "lobo",
            "n_buildings": int(train["building"].nunique()),
        }
        if m.name in lobo_for or m.kind == "fixed":
            res["lobo_train"] = lobo_mae(m, train) if m.kind != "fixed" else res["cv_train"]
        results[m.name] = res
        frames[m.name] = out
    return results, frames


__all__ = ["Method", "run_methods", "metrics", "bootstrap_ci", "building_weights"]
