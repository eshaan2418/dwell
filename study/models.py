"""Statistical models for the M11 decision study (pre-registered in study/README.md)."""

from __future__ import annotations

import contextlib
import warnings

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.genmod import cov_struct, families
from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM
from statsmodels.genmod.generalized_estimating_equations import GEE
from statsmodels.regression.mixed_linear_model import MixedLM

from study.schema import TRUST_ITEMS, USEFUL_ITEMS

Z95 = 1.959963984540054


@contextlib.contextmanager
def _quiet():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        yield


# ---------------------------------------------------------------- primary: consistent choice


GLMM_FE_PRIOR_SD = 1.0


def glmm(df: pd.DataFrame, seed: int = 0, fe_prior_sd: float = GLMM_FE_PRIOR_SD) -> dict:
    """Bayesian mixed logistic regression, random intercepts for participant and pair (crossed).

    statsmodels ``BinomialBayesMixedGLM`` fitted by variational Bayes (``fit_vb``). Priors: fixed effects
    N(0, 1) on the logit scale (``fe_p=1``; weakly informative: an odds ratio of e^2 ~ 7 is at +2 SD),
    log-SD of each variance component N(0, 1) (``vcp_p=1``, default). The statsmodels default ``fe_p=2``
    gave 87 % coverage and +0.17 bias in our 200-dataset check (VB is unstable near separation);
    ``fe_p=1`` gave ~95 % coverage with negligible bias (see study/README.md, "Analysis plan").
    The 95 % credible interval is mean +- 1.96 posterior SD (the VB posterior is Gaussian).
    """
    with _quiet():
        m = BinomialBayesMixedGLM.from_formula(
            "consistent ~ report",
            {"participant": "0 + C(participant_id)", "pair": "0 + C(pair_id)"},
            df,
            fe_p=fe_prior_sd,
        )
        r = m.fit_vb()
    j = m.exog_names.index("report")
    mean, sd = float(r.fe_mean[j]), float(r.fe_sd[j])
    vc = dict(zip(m.vcp_names, np.exp(r.vcp_mean).tolist(), strict=True))
    return {
        "method": "BinomialBayesMixedGLM.fit_vb, consistent ~ report + (1|participant) + (1|pair), "
        f"fixed-effect prior N(0, {fe_prior_sd}^2)",
        "log_or": mean,
        "post_sd": sd,
        "ci95": [mean - Z95 * sd, mean + Z95 * sd],
        "odds_ratio": float(np.exp(mean)),
        "p_positive": float(stats.norm.cdf(mean / sd)),
        "intercept": float(r.fe_mean[m.exog_names.index("Intercept")]),
        "vc_sd_posterior_mean": vc,
    }


def gee_arrays(y: np.ndarray, x: np.ndarray, groups: np.ndarray, cov_type: str = "bias_reduced"):
    exog = np.column_stack([np.ones_like(x, dtype=float), x.astype(float)])
    with _quiet():
        r = GEE(y, exog, groups=groups, family=families.Binomial(), cov_struct=cov_struct.Exchangeable()).fit(
            cov_type=cov_type
        )
        return float(r.params[1]), float(r.bse[1]), r


def gee(df: pd.DataFrame, extra: str = "") -> dict:
    """Population-averaged logistic GEE, exchangeable working correlation, clustered on participant.

    Primary SE: Mancl-DeRouen bias-reduced sandwich (``cov_type="bias_reduced"``), because the robust
    sandwich is anti-conservative with 15-30 clusters; the plain robust SE is reported alongside.
    """
    if extra:
        with _quiet():
            r = GEE.from_formula(
                f"consistent ~ report{extra}",
                groups="participant_id",
                data=df,
                family=families.Binomial(),
                cov_struct=cov_struct.Exchangeable(),
            ).fit(cov_type="bias_reduced")
        b, se = float(r.params["report"]), float(r.bse["report"])
        rho = float(r.model.cov_struct.dep_params)
        se_rob = float("nan")
    else:
        y = df["consistent"].to_numpy(float)
        x = df["report"].to_numpy(float)
        g = pd.factorize(df["participant_id"])[0]
        b, se, r = gee_arrays(y, x, g)
        rho = float(r.model.cov_struct.dep_params)
        se_rob = gee_arrays(y, x, g, "robust")[1]
    if not (np.isfinite(b) and np.isfinite(se) and se > 0 and abs(b) < 20):
        # quasi-complete separation (e.g. every non-tie report trial consistent): GEE has no finite MLE
        return {
            "method": f"GEE logit, exchangeable, groups=participant: consistent ~ report{extra}",
            "failed": "separation / non-finite estimate",
            "log_or": float("nan"),
            "ci95": [float("nan"), float("nan")],
            "p_two_sided": float("nan"),
        }
    p = 2 * stats.norm.sf(abs(b / se))
    return {
        "method": f"GEE logit, exchangeable, groups=participant: consistent ~ report{extra}",
        "log_or": b,
        "se_bias_reduced": se,
        "se_robust": se_rob,
        "ci95": [b - Z95 * se, b + Z95 * se],
        "odds_ratio": float(np.exp(b)),
        "p_two_sided": float(p),
        "working_correlation": rho,
    }


def paired_rates(df: pd.DataFrame) -> dict:
    """Per-participant consistent-choice rate in each condition (non-tie trials) and their difference."""
    t = df.groupby(["participant_id", "condition"])["consistent"].mean().unstack()
    t = t.dropna(subset=[c for c in ("report", "video") if c in t.columns])
    if not {"report", "video"} <= set(t.columns) or len(t) < 2:
        return {"n_participants": int(len(t)), "note": "not enough participants with both conditions"}
    d = (t["report"] - t["video"]).to_numpy()
    n = len(d)
    m, se = float(d.mean()), float(d.std(ddof=1) / np.sqrt(n))
    tq = stats.t.ppf(0.975, n - 1)
    try:
        wil = stats.wilcoxon(d, zero_method="zsplit")
        wp = float(wil.pvalue)
    except ValueError:
        wp = float("nan")
    return {
        "method": "per-participant rate difference (report - video), paired t and Wilcoxon signed-rank",
        "n_participants": n,
        "mean_rate_video": float(t["video"].mean()),
        "mean_rate_report": float(t["report"].mean()),
        "mean_diff": m,
        "ci95_t": [float(m - tq * se), float(m + tq * se)],
        "p_paired_t": float(2 * stats.t.sf(abs(m / se), n - 1)) if se > 0 else float("nan"),
        "p_wilcoxon": wp,
    }


def _cluster_boot(df: pd.DataFrame, cols: list[str], n_boot: int, seed: int) -> np.ndarray:
    """Participant-cluster bootstrap of pooled means of ``cols`` -> array (n_boot, len(cols))."""
    rng = np.random.default_rng(seed)
    g = df.groupby("participant_id")
    sums = g[cols].sum().to_numpy(float)
    cnts = g[cols].count().to_numpy(float)
    idx = rng.integers(0, len(sums), size=(n_boot, len(sums)))
    with np.errstate(invalid="ignore", divide="ignore"):
        return sums[idx].sum(1) / cnts[idx].sum(1)


def condition_rates(df: pd.DataFrame, n_boot: int = 2000, seed: int = 0) -> dict:
    """Pooled consistent-choice rate per condition with participant-cluster bootstrap 95 % CIs."""
    x = df.assign(
        video=df["consistent"].where(df["condition"] == "video"),
        report=df["consistent"].where(df["condition"] == "report"),
    )
    bs = _cluster_boot(x, ["video", "report"], n_boot, seed)
    out = {}
    for j, cond in enumerate(("video", "report")):
        sub = df[df["condition"] == cond]
        b = bs[:, j][np.isfinite(bs[:, j])]
        out[cond] = {
            "rate": float(sub["consistent"].mean()) if len(sub) else float("nan"),
            "n_trials": int(len(sub)),
            "ci95_cluster_bootstrap": [float(np.quantile(b, 0.025)), float(np.quantile(b, 0.975))],
        }
    return out


# ---------------------------------------------------------------- secondary


def confidence_model(df: pd.DataFrame) -> dict:
    """Linear mixed model on the 1-7 confidence rating (treated as interval; documented choice).

    confidence ~ report + C(pair_id), random intercept for participant (pair as fixed effect: few pairs).
    """
    with _quiet():
        r = MixedLM.from_formula("confidence ~ report + C(pair_id)", df, groups=df["participant_id"]).fit(reml=True)
    b, se = float(r.params["report"]), float(r.bse["report"])
    return {
        "method": "MixedLM (REML): confidence ~ report + C(pair_id) + (1|participant)",
        "report_effect": b,
        "se": se,
        "ci95": [b - Z95 * se, b + Z95 * se],
        "p_two_sided": float(2 * stats.norm.sf(abs(b / se))),
        "mean_video": float(df.loc[df["report"] == 0, "confidence"].mean()),
        "mean_report": float(df.loc[df["report"] == 1, "confidence"].mean()),
    }


def overtrust(df_all: pd.DataFrame) -> dict:
    """Over-trust index: mean confidence when the report's 90 % intervals overlap on the participant's
    top-weighted dimension minus when they do not (report trials). Calibrated trust -> negative.
    The same contrast in video-only trials (intervals not shown) is a placebo. Ties are included
    (trust calibration concerns what was shown, not the measured truth)."""
    out = {}
    for cond in ("report", "video"):
        sub = df_all[df_all["condition"] == cond]
        c1 = sub.loc[sub["overlap_top"] == 1, "confidence"]
        c0 = sub.loc[sub["overlap_top"] == 0, "confidence"]
        res = {
            "mean_conf_overlap": float(c1.mean()) if len(c1) else None,
            "mean_conf_no_overlap": float(c0.mean()) if len(c0) else None,
            "n_overlap": int(len(c1)),
            "n_no_overlap": int(len(c0)),
        }
        if len(c1) and len(c0):
            res["index_raw"] = float(c1.mean() - c0.mean())
            try:
                with _quiet():
                    r = MixedLM.from_formula("confidence ~ overlap_top", sub, groups=sub["participant_id"]).fit(
                        reml=True
                    )
                b, se = float(r.params["overlap_top"]), float(r.bse["overlap_top"])
                res.update(
                    {
                        "index_mixedlm": b,
                        "ci95": [b - Z95 * se, b + Z95 * se],
                        "p_two_sided": float(2 * stats.norm.sf(abs(b / se))),
                    }
                )
            except Exception as e:  # pragma: no cover - degenerate real data
                res["error"] = str(e)
        out[cond] = res
    return out


def brier(df_all: pd.DataFrame, n_boot: int = 2000, seed: int = 0) -> dict:
    """Brier score of the probability probes vs the sensor-measured truth (measured ties excluded)."""
    sub = df_all[(df_all["probe_dim"] != "") & df_all["probe_p_a"].notna() & ~df_all["probe_tie"]].copy()
    if sub.empty:
        return {"n_probes": 0}
    sub["p"] = sub["probe_p_a"] / 100
    sub["bs_part"] = (sub["p"] - sub["probe_truth_a"]) ** 2
    sub["bs_dwell"] = (sub["probe_p_dwell"] - sub["probe_truth_a"]) ** 2
    bs = _cluster_boot(sub, ["bs_part", "bs_dwell"], n_boot, seed)
    bp, bd = float(sub["bs_part"].mean()), float(sub["bs_dwell"].mean())
    return {
        "n_probes": int(len(sub)),
        "n_probe_ties_excluded": int(((df_all["probe_dim"] != "") & df_all["probe_tie"]).sum()),
        "brier_participants": bp,
        "ci95_participants": np.quantile(bs[:, 0], [0.025, 0.975]).tolist(),
        "brier_report_implied": bd,
        "brier_uninformed": 0.25,
        "skill_vs_uninformed": 1 - bp / 0.25,
        "diff_participants_minus_report": bp - bd,
        "ci95_diff": np.quantile(bs[:, 0] - bs[:, 1], [0.025, 0.975]).tolist(),
        "by_dim": {k: float(v) for k, v in sub.groupby("probe_dim")["bs_part"].mean().items()},
    }


def cronbach_alpha(x: np.ndarray) -> float:
    x = np.asarray(x, float)
    k = x.shape[1]
    if k < 2 or len(x) < 2:
        return float("nan")
    tv = x.sum(1).var(ddof=1)
    return float(k / (k - 1) * (1 - x.var(axis=0, ddof=1).sum() / tv)) if tv > 0 else float("nan")


def likert(p: pd.DataFrame) -> dict:
    tr = p[TRUST_ITEMS].astype(float).copy()
    tr["trust_3"] = 8 - tr["trust_3"]
    us = p[USEFUL_ITEMS].astype(float)
    return {
        "usefulness_scale_mean": float(us.mean(axis=1).mean()),
        "usefulness_scale_sd": float(us.mean(axis=1).std(ddof=1)),
        "usefulness_alpha": cronbach_alpha(us.to_numpy()),
        "trust_scale_mean": float(tr.mean(axis=1).mean()),
        "trust_scale_sd": float(tr.mean(axis=1).std(ddof=1)),
        "trust_alpha": cronbach_alpha(tr.to_numpy()),
        "item_means": {c: float(p[c].mean()) for c in USEFUL_ITEMS + TRUST_ITEMS},
    }
