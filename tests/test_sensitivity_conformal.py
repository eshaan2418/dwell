import numpy as np
import pytest

from hybrid.conformal import coverage, cv_plus_intervals, weighted_quantile
from hybrid.sensitivity import categorical, ishigami, sobol_indices


def test_ishigami_sobol_analytic():
    a, b = 7.0, 0.1
    v = a**2 / 8 + b * np.pi**4 / 5 + b**2 * np.pi**8 / 18 + 0.5
    v1 = 0.5 * (1 + b * np.pi**4 / 5) ** 2
    v2 = a**2 / 8
    v13 = b**2 * np.pi**8 * (1 / 18 - 1 / 50)
    r = sobol_indices(ishigami, 3, 20000, seed=1, n_boot=20)
    assert r["S1"] == pytest.approx([v1 / v, v2 / v, 0.0], abs=0.03)
    assert r["ST"] == pytest.approx([(v1 + v13) / v, v2 / v, v13 / v], abs=0.03)


def test_categorical_inverse_cdf():
    u = np.linspace(0, 0.999, 1000)
    c = categorical(u, np.array([0.2, 0.5, 0.3]))
    assert np.bincount(c).tolist() == [200, 500, 300]


def test_weighted_quantile_uniform_weights():
    x = np.arange(1, 101, dtype=float)[None, :]
    assert weighted_quantile(x, np.ones(100), 0.9)[0] == 90


def test_cv_plus_covers_gaussian_noise():
    rng = np.random.default_rng(0)
    n_cal, n_test = 2000, 3000
    groups = np.repeat(np.arange(400), 5)
    scores = np.abs(rng.normal(size=n_cal))
    pred = np.zeros((n_test, n_cal))
    lo, hi = cv_plus_intervals(pred, scores, np.ones(n_test), groups, alpha=0.1)
    y = rng.normal(size=n_test)
    assert coverage(y, lo, hi) == pytest.approx(0.9, abs=0.025)
