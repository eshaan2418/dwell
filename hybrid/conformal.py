"""Conformal prediction intervals for grouped (building-clustered) data.

CV+ (Barber et al., "Predictive inference with the jackknife+", 2021) with K building-grouped folds,
optional normalised scores (|y - yhat| / s(x)), building-weighted quantiles (each calibration
building has total weight 1, so buildings with many room-days do not dominate), and Mondrian
(group-conditional) calibration.
"""

from __future__ import annotations

import numpy as np


def weighted_quantile(values: np.ndarray, weights: np.ndarray, q: float, axis: int = -1) -> np.ndarray:
    """Weighted quantile along the last axis (values: (..., n), weights: (n,))."""
    order = np.argsort(values, axis=axis)
    v = np.take_along_axis(values, order, axis=axis)
    w = weights[order]
    cw = np.cumsum(w, axis=axis)
    cw = cw / cw[..., -1:]
    idx = np.argmax(cw >= q, axis=axis)
    return np.take_along_axis(v, idx[..., None], axis=axis)[..., 0]


def building_weights(groups: np.ndarray) -> np.ndarray:
    _, inv, counts = np.unique(groups, return_inverse=True, return_counts=True)
    return 1.0 / counts[inv]


def cv_plus_intervals(
    oof_pred_at_test: np.ndarray,  # (n_test, n_cal): prediction at each test x by the model that held out cal i
    oof_scores: np.ndarray,  # (n_cal,): |y_i - yhat_{-k(i)}(x_i)| / s(x_i)
    s_test: np.ndarray,  # (n_test,) scale at test points (ones for absolute scores)
    cal_groups: np.ndarray,
    alpha: float = 0.1,
    cal_mask: np.ndarray | None = None,  # (n_test, n_cal) Mondrian restriction
) -> tuple[np.ndarray, np.ndarray]:
    w = building_weights(cal_groups)
    n_test = oof_pred_at_test.shape[0]
    n_eff = len(np.unique(cal_groups))
    q_hi = min((1 - alpha) * (1 + 1 / n_eff), 1.0)
    q_lo = 1 - q_hi
    lows = oof_pred_at_test - oof_scores[None, :] * s_test[:, None]
    highs = oof_pred_at_test + oof_scores[None, :] * s_test[:, None]
    if cal_mask is None:
        return weighted_quantile(lows, w, q_lo), weighted_quantile(highs, w, q_hi)
    lo = np.empty(n_test)
    hi = np.empty(n_test)
    for i in range(n_test):
        m = cal_mask[i]
        if m.sum() < 10:
            m = np.ones_like(m)
        ww = w[m]
        lo[i] = weighted_quantile(lows[i, m][None, :], ww, q_lo)[0]
        hi[i] = weighted_quantile(highs[i, m][None, :], ww, q_hi)[0]
    return lo, hi


def coverage(y: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> float:
    return float(np.mean((y >= lo) & (y <= hi)))
