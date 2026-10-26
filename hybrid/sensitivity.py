"""Variance-based (Sobol) sensitivity analysis.

Saltelli (2002/2010) sampling with the Jansen estimator for total effects and the Saltelli 2010
estimator for first-order effects. Inputs are specified as samplers mapping U(0,1) columns to
parameter values (so categorical hidden properties are handled by inverse-CDF on their posterior).
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np


def sobol_indices(
    f: Callable[[np.ndarray], np.ndarray], d: int, n: int, seed: int = 0, n_boot: int = 200
) -> dict[str, np.ndarray]:
    """f maps an (m, d) array of U(0,1) inputs to (m,) outputs. Returns S1, ST and bootstrap SDs."""
    rng = np.random.default_rng(seed)
    a = rng.random((n, d))
    b = rng.random((n, d))
    fa, fb = f(a), f(b)
    fab = np.empty((d, n))
    for i in range(d):
        ab = a.copy()
        ab[:, i] = b[:, i]
        fab[i] = f(ab)

    def est(idx: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        ya, yb, yab = fa[idx], fb[idx], fab[:, idx]
        var = np.var(np.concatenate([ya, yb]))
        if var <= 0:
            return np.zeros(d), np.zeros(d)
        s1 = np.mean(yb[None, :] * (yab - ya[None, :]), axis=1) / var
        st = 0.5 * np.mean((ya[None, :] - yab) ** 2, axis=1) / var
        return s1, st

    s1, st = est(np.arange(n))
    boots = [est(rng.integers(0, n, n)) for _ in range(n_boot)]
    return {
        "S1": s1,
        "ST": st,
        "S1_sd": np.std([b[0] for b in boots], axis=0),
        "ST_sd": np.std([b[1] for b in boots], axis=0),
        "var": float(np.var(np.concatenate([fa, fb]))),
    }


def categorical(u: np.ndarray, probs: np.ndarray) -> np.ndarray:
    """Inverse-CDF map of U(0,1) to category indices."""
    c = np.cumsum(probs) / np.sum(probs)
    return np.minimum(np.searchsorted(c, u, side="right"), len(probs) - 1)


def ishigami(x: np.ndarray, a: float = 7.0, b: float = 0.1) -> np.ndarray:
    z = -np.pi + 2 * np.pi * x
    return np.sin(z[:, 0]) + a * np.sin(z[:, 1]) ** 2 + b * z[:, 2] ** 4 * np.sin(z[:, 0])
