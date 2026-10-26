"""M11 decision-study analysis (pre-registered plan: study/README.md, "Analysis plan").

    python -m study.analysis --dry-run   # simulated -> results/m11/study_dryrun.json (data_kind synthetic)
    python -m study.analysis             # real data in study/data/ -> results/m11/study_results.json
                                         # (data_kind real-sensor); prints "no real data yet" and exits 0
                                         # if study/data/responses.csv does not exist.

The dry run (1) simulates one study in the exact real-data CSV format, writes it to
``study/data/simulated/`` and runs the full pipeline on it; (2) checks effect recovery / CI coverage over
many simulated studies; (3) simulates power for N in {15, 20, 30} x K in {6, 8}; (4) saves figures to
``results/m11/figs/``.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import pandas as pd

from core.provenance import RESULTS, hash_paths, write_result
from study import models as M
from study.schema import DATA, FILES, FormatError, StudyData, annotate, exclusions, load_data, write_data
from study.simulate import SimParams, simulate, true_effects

SIM_DIR = DATA / "simulated"
FIG_DIR = RESULTS / "m11" / "figs"
POWER_N = (15, 20, 30)
POWER_K = (6, 8)
POWER_TIE_RATE = 0.20  # assumes a curated pool; random simulated pools give ~44 % (reported in the dry run)
# extra "what would it take" cells (N, K, p_report) beyond the requested 3 x 2 grid
POWER_EXTRA = ((40, 8, 0.75), (30, 12, 0.75), (30, 8, 0.80))
ALPHA = 0.05

# palette (validated reference palette, light mode): series 1 blue, series 2 orange, text greys
C_REPORT, C_VIDEO = "#2a78d6", "#eb6834"
C_TEXT, C_MUTED, C_GRID, C_SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


# ---------------------------------------------------------------- full analysis of one dataset


def _perm_chunk(args: tuple[pd.DataFrame, list[int]]) -> list[float]:
    df, seeds = args
    out = []
    for s in seeds:
        rng = np.random.default_rng(s)
        x = df.copy()
        x["report"] = x.groupby("participant_id")["report"].transform(lambda r, g=rng: g.permutation(r.to_numpy()))
        try:
            g = M.glmm(x)
            out.append(g["log_or"] / g["post_sd"])
        except Exception:
            out.append(0.0)
    return out


def glmm_permutation_test(nt: pd.DataFrame, n_perm: int, seed: int, workers: int) -> dict:
    """Primary H1 test: within-participant permutation (randomisation) test of the GLMM z = posterior
    mean / posterior SD of the report log-OR. Condition labels are permuted among each participant's
    non-tie trials, matching the within-subject randomisation. Needed because the VB posterior SD is too
    small: nominal 95 % CrIs reject a true null ~13 % of the time in our simulations."""
    obs = M.glmm(nt)
    z_obs = obs["log_or"] / obs["post_sd"]
    df = nt[["participant_id", "pair_id", "report", "consistent"]].reset_index(drop=True)
    seeds = [seed * 100_003 + i for i in range(n_perm)]
    n_chunks = max(1, min(len(seeds), 4 * max(1, workers)))
    jobs = [(df, seeds[c::n_chunks]) for c in range(n_chunks)]
    z = np.concatenate([np.asarray(r, float) for r in _pmap(_perm_chunk, jobs, workers)])
    p = float((1 + np.sum(np.abs(z) >= abs(z_obs))) / (n_perm + 1))
    return {
        "method": "within-participant permutation test of GLMM z (two-sided)",
        "z_obs": float(z_obs),
        "n_perm": int(n_perm),
        "p_two_sided": p,
        "perm_abs_z_95": float(np.quantile(np.abs(z), 0.95)),
    }


def analyse(d: StudyData, n_boot: int = 2000, seed: int = 0, n_perm: int = 0, workers: int = 1) -> dict:
    kept, why = exclusions(d)
    d = StudyData(
        d.responses[d.responses["participant_id"].isin(kept)].copy(),
        d.participants[d.participants["participant_id"].isin(kept)].copy(),
        d.units_truth,
        d.units_report,
    )
    a = annotate(d)
    nt = a[~a["tie"]].copy()
    ties = a[a["tie"]]
    k = int(d.responses.groupby("participant_id")["trial"].count().max()) if len(d.responses) else 0
    out: dict = {
        "n_participants_enrolled": int(len(kept) + len(why)),
        "n_participants_analysed": int(len(kept)),
        "exclusions": why,
        "n_units": int(len(d.units_truth)),
        "k_pairs_per_participant": k,
        "n_trials_answered": int(len(a)),
        "n_trials_tie": int(len(ties)),
        "n_trials_non_tie": int(len(nt)),
        "tie_rate": float(a["tie"].mean()) if len(a) else None,
    }
    prim: dict = {"rates_by_condition": M.condition_rates(nt, n_boot, seed)}
    for name, fn in (
        ("glmm", lambda: M.glmm(nt, seed)),
        (
            "glmm_permutation_test",
            lambda: glmm_permutation_test(nt, n_perm, seed, workers) if n_perm else {"note": "skipped (n_perm = 0)"},
        ),
        ("gee", lambda: M.gee(nt)),
        ("gee_plus_trial_position", lambda: M.gee(nt, extra=" + trial")),
        ("paired_per_participant", lambda: M.paired_rates(nt)),
    ):
        try:
            prim[name] = fn()
        except Exception as e:  # keep the report going on degenerate real data
            prim[name] = {"error": f"{type(e).__name__}: {e}"}
    out["primary_H1"] = prim
    out["ties_descriptive"] = {
        c: {
            "n": int((ties["condition"] == c).sum()),
            "rate_chose_measured_best": float(ties.loc[ties["condition"] == c, "consistent"].mean())
            if (ties["condition"] == c).any()
            else None,
        }
        for c in ("video", "report")
    }
    sec: dict = {}
    for name, fn in (
        ("confidence_by_condition", lambda: M.confidence_model(a)),
        ("overtrust_index_H2", lambda: M.overtrust(a)),
        ("probe_brier_H3", lambda: M.brier(a, n_boot, seed)),
        ("usefulness_trust_likert", lambda: M.likert(d.participants)),
    ):
        try:
            sec[name] = fn()
        except Exception as e:
            sec[name] = {"error": f"{type(e).__name__}: {e}"}
    out["secondary"] = sec
    out["hypotheses"] = decide(out)
    return out


def decide(o: dict) -> dict:
    g = o["primary_H1"].get("glmm", {})
    gp = o["primary_H1"].get("glmm_permutation_test", {})
    gee = o["primary_H1"].get("gee", {})
    ot = o["secondary"].get("overtrust_index_H2", {}).get("report", {})
    br = o["secondary"].get("probe_brier_H3", {})
    h1 = None if "p_two_sided" not in gp or "log_or" not in g else bool(gp["p_two_sided"] < ALPHA and g["log_or"] > 0)
    h2 = None if "ci95" not in ot else bool(ot["ci95"][1] < 0)
    h3 = None if "ci95_participants" not in br else bool(br["ci95_participants"][1] < 0.25)
    return {
        "H1_report_increases_consistent_choice": {
            "supported": h1,
            "rule": "GLMM report log-OR > 0 and within-participant permutation p < 0.05",
            "gee_agrees": None
            if h1 is None or not np.isfinite(gee.get("ci95", [np.nan])[0])
            else bool(gee["ci95"][0] > 0) == h1,
        },
        "H2_confidence_lower_when_intervals_overlap": {
            "supported": h2,
            "rule": "report-trial MixedLM overlap 95% CI < 0",
        },
        "H3_probe_brier_better_than_uninformed": {"supported": h3, "rule": "cluster-bootstrap 95% CI < 0.25"},
    }


# ---------------------------------------------------------------- effect recovery / coverage


def _recovery_one(args: tuple[dict, int, bool]) -> dict:
    spd, seed, do_glmm = args
    sp = SimParams(**{**spd, "seed": seed})
    a = annotate(simulate(sp))
    nt = a[~a["tie"]]
    nan = {
        "log_or": float("nan"),
        "ci95": [float("nan")] * 2,
        "p_two_sided": float("nan"),
        "mean_diff": float("nan"),
        "ci95_t": [float("nan")] * 2,
        "p_paired_t": float("nan"),
    }
    fns = {"gee": lambda: M.gee(nt), "paired": lambda: M.paired_rates(nt)}
    if do_glmm:
        fns["glmm"] = lambda: M.glmm(nt, seed)
    r: dict = {"tie_rate": float(a["tie"].mean())}
    for k, fn in fns.items():
        try:
            r[k] = {**nan, **fn()}
        except Exception as e:  # degenerate simulated study (e.g. every non-tie choice consistent)
            r[k] = {**nan, "failed": f"{type(e).__name__}: {e}"}
    return r


def coverage(sp: SimParams, n_sims: int, n_glmm: int, seed0: int, workers: int) -> dict:
    te = true_effects(sp)
    jobs = [(asdict(sp), seed0 + i, i < n_glmm) for i in range(n_sims)]
    res = _pmap(_recovery_one, jobs, workers)

    def summ(vals, cis, truth, pvals=None):
        v, c = np.array(vals, float), np.array(cis, float)
        ok = np.isfinite(v) & np.isfinite(c).all(1)
        # failed fits (separation) count as NOT covering -> conservative coverage
        cov = float(np.mean(ok & (c[:, 0] <= truth) & (truth <= c[:, 1])))
        v = v[ok]
        d = {
            "n_datasets": len(ok),
            "n_failed_fits": int((~ok).sum()),
            "true": truth,
            "mean_estimate": float(v.mean()),
            "median_estimate": float(np.median(v)),
            "bias": float(v.mean() - truth),
            "empirical_sd": float(v.std(ddof=1)),
            "ci95_coverage": cov,
            "coverage_mc_se": float(math.sqrt(max(cov * (1 - cov), 1e-12) / len(v))),
            "rejection_rate_ci_excludes_0": float(np.mean(c[ok, 0] > 0) + np.mean(c[ok, 1] < 0)),
        }
        if pvals is not None:
            d["rejection_rate_p_lt_0.05"] = float(np.mean(np.array(pvals) < ALPHA))
        return d

    tr = np.array([r["tie_rate"] for r in res])
    out = {
        "truth": te,
        "tie_rate_across_datasets": {
            "mean": float(tr.mean()),
            "p10": float(np.quantile(tr, 0.1)),
            "p90": float(np.quantile(tr, 0.9)),
        },
        "gee_marginal_log_or": summ(
            [r["gee"]["log_or"] for r in res],
            [r["gee"]["ci95"] for r in res],
            te["marginal_log_or"],
            [r["gee"]["p_two_sided"] for r in res],
        ),
        "paired_rate_diff": summ(
            [r["paired"]["mean_diff"] for r in res],
            [r["paired"]["ci95_t"] for r in res],
            te["marginal_risk_diff"],
            [r["paired"]["p_paired_t"] for r in res],
        ),
    }
    gl = [r["glmm"] for r in res if "glmm" in r]
    if gl:
        out["glmm_conditional_log_or"] = summ(
            [g["log_or"] for g in gl], [g["ci95"] for g in gl], te["conditional_log_or"]
        )
    return out


# ---------------------------------------------------------------- power


def _power_chunk(args: tuple[int, int, float, dict, int, int, int]) -> dict:
    """One chunk of simulated studies for one (N, K, p_report) cell (fast numpy generator, no files)."""
    n, k, p_rep, spd, n_sims, n_glmm, seed = args
    sp = SimParams(**{**spd, "n_participants": n, "k": k, "p_report": p_rep})
    rng = np.random.default_rng(seed)
    m = math.comb(sp.pool_size(), 2)
    rej_gee = rej_t = 0
    z_glmm: list[float] = []
    for i in range(n_sims):
        u = rng.normal(0, sp.sd_participant, n)
        v = rng.normal(0, sp.sd_pair, m)
        pid = np.repeat(np.arange(n), k)
        pair = np.concatenate([rng.choice(m, k, replace=False) for _ in range(n)])
        rep = np.concatenate([rng.permutation(np.r_[np.ones(k // 2), np.zeros(k // 2)]) for _ in range(n)])
        y = (rng.random(n * k) < 1 / (1 + np.exp(-(sp.b0 + sp.b1 * rep + u[pid] + v[pair])))).astype(float)
        keep = rng.random(n * k) >= POWER_TIE_RATE
        y, rep, pid, pair = y[keep], rep[keep], pid[keep], pair[keep]
        b, se, _ = M.gee_arrays(y, rep, pid)
        ok = np.isfinite(b) and np.isfinite(se) and se > 0 and abs(b) < 20
        rej_gee += int(ok and abs(b / se) > M.Z95)  # separation -> counted as no rejection (conservative)
        df = pd.DataFrame({"participant_id": pid, "condition": np.where(rep == 1, "report", "video"), "consistent": y})
        pr = M.paired_rates(df)
        rej_t += int(pr.get("p_paired_t", 1.0) < ALPHA)
        if i < n_glmm:
            try:
                g = M.glmm(df.assign(report=rep, pair_id=pair))
                z_glmm.append(g["log_or"] / g["post_sd"])
            except Exception:
                z_glmm.append(0.0)  # degenerate dataset -> no rejection
    return {"n": n_sims, "rej_gee": rej_gee, "rej_t": rej_t, "z_glmm": z_glmm}


def power_table(
    sp: SimParams, n_sims: int, n_glmm: int, seed: int, workers: int, extra: bool = True, chunks: int = 4
) -> list[dict]:
    """Power per cell + the same cell under the null (p_report = p_video) for type-I error and for the
    size-adjusted GLMM power: VB posterior SDs are too small (null type-I ~ 13 %), so the primary test is a
    within-participant permutation test of the GLMM z; its power is approximated by
    P(|z_alt| > 95th percentile of |z_null|) in the same design."""
    req = [(n, k, sp.p_report) for k in POWER_K for n in POWER_N]
    cells = req + (list(POWER_EXTRA) if extra else [])
    n_glmm = min(n_glmm, n_sims)
    jobs, keys = [], []
    for i, (n, k, p) in enumerate(cells):
        for null in (False, True):
            for c in range(chunks):
                lo, hi = c * n_sims // chunks, (c + 1) * n_sims // chunks
                g = max(0, min(hi, n_glmm) - lo)
                jobs.append((n, k, sp.p_base if null else p, asdict(sp), hi - lo, g, seed + 1000 * i + 10 * c + null))
                keys.append((i, null))
    res = _pmap(_power_chunk, jobs, workers)
    agg: dict = {}
    for key, r in zip(keys, res, strict=True):
        a = agg.setdefault(key, {"n": 0, "rej_gee": 0, "rej_t": 0, "z_glmm": []})
        a["n"] += r["n"]
        a["rej_gee"] += r["rej_gee"]
        a["rej_t"] += r["rej_t"]
        a["z_glmm"] += r["z_glmm"]
    rows = []
    for i, (n, k, p) in enumerate(cells):
        alt, nul = agg[(i, False)], agg[(i, True)]
        za, zn = np.abs(alt["z_glmm"]), np.abs(nul["z_glmm"])
        crit = float(np.quantile(zn, 0.95)) if len(zn) else float("nan")
        rows.append(
            {
                "N": n,
                "K": k,
                "p_video": sp.p_base,
                "p_report": p,
                "n_units_needed": SimParams(k=k).pool_size(),
                "grid": "requested" if (n, k, p) in req else "extra",
                "n_sims": alt["n"],
                "n_sims_glmm": len(za),
                "power_glmm_perm": float(np.mean(za > crit)) if len(za) else None,
                "power_gee": alt["rej_gee"] / alt["n"],
                "power_paired_t": alt["rej_t"] / alt["n"],
                "power_glmm_vb_nominal": float(np.mean(za > M.Z95)) if len(za) else None,
                "type1_gee": nul["rej_gee"] / nul["n"],
                "type1_paired_t": nul["rej_t"] / nul["n"],
                "type1_glmm_vb_nominal": float(np.mean(zn > M.Z95)) if len(zn) else None,
                "glmm_null_critical_abs_z": crit,
                "mc_se_max": math.sqrt(0.25 / alt["n"]),
                "mc_se_max_glmm": math.sqrt(0.25 / len(za)) if len(za) else None,
            }
        )
    return rows


def _pmap(fn, jobs, workers):
    if workers <= 1:
        return [fn(j) for j in jobs]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(fn, jobs, chunksize=max(1, len(jobs) // (4 * workers))))


# ---------------------------------------------------------------- figures


def _style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(C_MUTED)
    ax.tick_params(colors=C_MUTED, labelsize=9)
    ax.yaxis.grid(True, color=C_GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_facecolor(C_SURF)


def fig_consistency(nt: pd.DataFrame, rates: dict, path: Path, title_suffix: str) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(5.2, 4.2), facecolor=C_SURF)
    _style(ax)
    pr = nt.groupby(["participant_id", "condition"])["consistent"].mean().unstack().dropna()
    for _, row in pr.iterrows():
        ax.plot([0, 1], [row["video"], row["report"]], color=C_GRID, linewidth=1, zorder=1)
    for x, cond, col, lab in (
        (0, "video", C_VIDEO, "Video only"),
        (1, "report", C_REPORT, "Video + Dwell report"),
    ):
        r = rates[cond]
        lo, hi = r["ci95_cluster_bootstrap"]
        ax.errorbar(
            [x],
            [r["rate"]],
            yerr=[[r["rate"] - lo], [hi - r["rate"]]],
            fmt="o",
            color=col,
            markersize=9,
            capsize=0,
            elinewidth=2,
            markeredgecolor=C_SURF,
            markeredgewidth=2,
            zorder=3,
        )
        ax.annotate(
            f"{lab}\n{r['rate']:.0%} [{lo:.0%}, {hi:.0%}]",
            (x, r["rate"]),
            xytext=(14 if x == 0 else -14, 0),
            textcoords="offset points",
            ha="left" if x == 0 else "right",
            va="center",
            fontsize=9,
            color=C_TEXT,
        )
    ax.set_xlim(-0.6, 1.6)
    ax.set_ylim(0, 1.05)
    ax.set_xticks([0, 1], ["Video only", "Video + report"])
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.set_ylabel("Preference-consistent choices (non-tie pairs)", color=C_MUTED, fontsize=9)
    ax.set_title(f"Consistent-choice rate by condition{title_suffix}", color=C_TEXT, fontsize=10, loc="left")
    fig.text(
        0.01,
        0.01,
        "Dots: pooled rate, 95% participant-cluster bootstrap CI. Grey lines: participants.",
        fontsize=7,
        color=C_MUTED,
    )
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, facecolor=C_SURF)
    plt.close(fig)
    return path


def fig_power(table: list[dict], path: Path, sp: SimParams) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(5.2, 4.0), facecolor=C_SURF)
    _style(ax)
    for k, col in zip(POWER_K, (C_VIDEO, C_REPORT), strict=True):
        rows = sorted((r for r in table if r["K"] == k and r["grid"] == "requested"), key=lambda r: r["N"])
        xs, ys = [r["N"] for r in rows], [r["power_glmm_perm"] for r in rows]
        ax.plot(
            xs,
            ys,
            color=col,
            linewidth=2,
            marker="o",
            markersize=8,
            markeredgecolor=C_SURF,
            markeredgewidth=2,
            label=f"K = {k} pairs",
        )
        ax.annotate(
            f"K = {k}",
            (xs[-1], ys[-1]),
            xytext=(8, 0),
            textcoords="offset points",
            va="center",
            fontsize=9,
            color=C_TEXT,
        )
    ax.axhline(0.8, color=C_MUTED, linewidth=1, linestyle=(0, (4, 3)))
    ax.annotate("80%", (POWER_N[0], 0.8), xytext=(0, 4), textcoords="offset points", fontsize=8, color=C_MUTED)
    ax.set_xticks(list(POWER_N))
    ax.set_xlim(POWER_N[0] - 2, POWER_N[-1] + 4)
    ax.set_ylim(0, 1)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.set_xlabel("Participants (N)", color=C_MUTED, fontsize=9)
    ax.set_ylabel("Power (primary GLMM permutation test)", color=C_MUTED, fontsize=9)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    ax.set_title(
        f"Simulated power: {sp.p_base:.0%} -> {sp.p_report:.0%}, participant SD {sp.sd_participant}",
        color=C_TEXT,
        fontsize=10,
        loc="left",
    )
    fig.text(
        0.01,
        0.01,
        f"{table[0]['n_sims_glmm']} simulated studies per point; {POWER_TIE_RATE:.0%} tie trials "
        f"dropped; pair SD {sp.sd_pair}.",
        fontsize=7,
        color=C_MUTED,
    )
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, dpi=150, facecolor=C_SURF)
    plt.close(fig)
    return path


# ---------------------------------------------------------------- CLI


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(RESULTS.parent))
    except ValueError:
        return str(p)


def run_dry(a: argparse.Namespace) -> int:
    t0 = time.time()
    sp = SimParams(n_participants=a.n_participants, seed=a.seed)
    d = simulate(sp)
    paths = write_data(d, SIM_DIR)
    d = load_data(SIM_DIR)  # exercise the real-data loader / validator on the written CSVs
    res = analyse(d, seed=a.seed, n_perm=a.n_perm, workers=a.workers)
    te = true_effects(sp)
    g, gee, pr = (res["primary_H1"][k] for k in ("glmm", "gee", "paired_per_participant"))
    single = {
        "glmm_conditional_log_or": {
            "true": te["conditional_log_or"],
            "estimate": g["log_or"],
            "ci95": g["ci95"],
            "ci_covers_true": bool(g["ci95"][0] <= te["conditional_log_or"] <= g["ci95"][1]),
        },
        "gee_marginal_log_or": {
            "true": te["marginal_log_or"],
            "estimate": gee["log_or"],
            "ci95": gee["ci95"],
            "ci_covers_true": bool(gee["ci95"][0] <= te["marginal_log_or"] <= gee["ci95"][1]),
        },
        "paired_rate_diff": {
            "true": te["marginal_risk_diff"],
            "estimate": pr["mean_diff"],
            "ci95": pr["ci95_t"],
            "ci_covers_true": bool(pr["ci95_t"][0] <= te["marginal_risk_diff"] <= pr["ci95_t"][1]),
        },
    }
    print(f"[1/3] analysed one simulated study ({time.time() - t0:.0f}s)", flush=True)
    cov = coverage(sp, a.n_coverage, a.n_coverage_glmm, a.seed + 1000, a.workers)
    print(f"[2/3] coverage over {a.n_coverage} simulated studies ({time.time() - t0:.0f}s)", flush=True)
    sp_pow = replace(sp, seed=a.seed)
    ptab = power_table(sp_pow, a.n_power, a.n_power_glmm, a.seed + 5000, a.workers)
    print(f"[3/3] power table ({time.time() - t0:.0f}s)", flush=True)
    a_ = annotate(d)
    figs = [
        fig_consistency(
            a_[~a_["tie"]],
            res["primary_H1"]["rates_by_condition"],
            FIG_DIR / "dryrun_consistency_by_condition.png",
            " (SIMULATED)",
        ),
        fig_power(ptab, FIG_DIR / "power_curve.png", sp_pow),
    ]
    payload = {
        "mode": "dry-run (SIMULATED participants, units and responses; not evidence about Dwell)",
        "simulation_params": asdict(sp),
        "simulated_data_dir": _rel(SIM_DIR),
        "analysis_of_one_simulated_study": res,
        "effect_recovery": {"single_dataset": single, "coverage_check": cov},
        "power": {
            "assumptions": {
                "p_video": sp.p_base,
                "p_report": sp.p_report,
                "sd_participant_logit": sp.sd_participant,
                "sd_pair_logit": sp.sd_pair,
                "tie_rate_dropped": POWER_TIE_RATE,
                "tests": "power_glmm_perm: primary GLMM permutation test, approximated by size-adjusted power "
                "P(|z_alt| > 95th pct of |z_null|) over the first n_sims_glmm datasets of matched alt/null cells; "
                "power_glmm_vb_nominal / type1_glmm_vb_nominal: nominal VB 95% CrI (anti-conservative; "
                "reported, not used); power_gee: GEE bias-reduced-SE Wald, two-sided alpha 0.05; "
                "power_paired_t: paired t on per-participant rates",
                "n_sims_per_cell": a.n_power,
                "n_sims_glmm_per_cell": a.n_power_glmm,
            },
            "table": ptab,
        },
        "figures": [_rel(f) for f in figs],
        "runtime_s": round(time.time() - t0, 1),
    }
    cfg = {
        "n_coverage": a.n_coverage,
        "n_coverage_glmm": a.n_coverage_glmm,
        "n_power": a.n_power,
        "n_power_glmm": a.n_power_glmm,
        "power_tie_rate": POWER_TIE_RATE,
        "power_extra": POWER_EXTRA,
        "power_N": POWER_N,
        "power_K": POWER_K,
        "sim": asdict(sp),
    }
    out = write_result(
        "m11/study_dryrun.json",
        payload,
        seed=a.seed,
        config=cfg,
        data_hash=hash_paths(paths),
        data_kind="synthetic",
    )
    print(f"wrote {out}")
    _print_summary(single, cov, ptab)
    return 0


def _print_summary(single, cov, ptab):
    print("\nEffect recovery (single simulated study):")
    for k, v in single.items():
        print(
            f"  {k:26s} true {v['true']:+.3f}  est {v['estimate']:+.3f}  CI [{v['ci95'][0]:+.3f}, "
            f"{v['ci95'][1]:+.3f}]  covers={v['ci_covers_true']}"
        )
    print("Coverage check:")
    for k, v in cov.items():
        if k in ("truth", "tie_rate_across_datasets"):
            continue
        print(
            f"  {k:26s} n={v['n_datasets']:3d} true {v['true']:+.3f} mean est {v['mean_estimate']:+.3f} "
            f"bias {v['bias']:+.3f} coverage {v['ci95_coverage']:.3f} "
            f"reject {v['rejection_rate_ci_excludes_0']:.3f}"
            f" failed {v['n_failed_fits']}"
        )
    print("Power (glmm_perm = size-adjusted GLMM permutation test, primary; type-I from matched null cells):")
    print("    N   K  p_vid p_rep units | glmm_perm    gee  paired_t | type1: glmm_vb_nominal    gee  paired_t | grid")
    for r in ptab:
        print(
            f"  {r['N']:3d} {r['K']:3d}  {r['p_video']:.2f}  {r['p_report']:.2f}  {r['n_units_needed']:3d}  |"
            f" {r['power_glmm_perm']:9.3f} {r['power_gee']:6.3f} {r['power_paired_t']:9.3f} |"
            f" {r['type1_glmm_vb_nominal']:22.3f} {r['type1_gee']:6.3f} {r['type1_paired_t']:9.3f} | {r['grid']}"
        )


def run_real(a: argparse.Namespace) -> int:
    folder: Path = a.data_dir
    if not (folder / FILES["responses"]).exists():
        print(f"no real data yet ({folder / FILES['responses']} not found)")
        return 0
    try:
        d = load_data(folder)
    except FormatError as e:
        print(f"data format error: {e}", file=sys.stderr)
        return 1
    if d.participants["notes"].str.contains("synthetic", case=False).any():
        print(
            "refusing: participants.csv contains simulated rows (notes == 'synthetic'); real data only",
            file=sys.stderr,
        )
        return 1
    res = analyse(d, seed=a.seed, n_perm=a.n_perm, workers=a.workers)
    a_ = annotate(d)
    figs = [
        fig_consistency(
            a_[~a_["tie"]],
            res["primary_H1"]["rates_by_condition"],
            FIG_DIR / "consistency_by_condition.png",
            "",
        )
    ]
    inputs = [folder / f for f in FILES.values()] + (
        [folder / "schedule.csv"] if (folder / "schedule.csv").exists() else []
    )
    res["figures"] = [_rel(f) for f in figs]
    res["mode"] = "real study data (human participants; ground truth from in-home sensors)"
    out = write_result(
        "m11/study_results.json",
        res,
        seed=a.seed,
        config={"data_dir": _rel(folder)},
        data_hash=hash_paths(inputs),
        data_kind="real-sensor",
    )
    print(f"wrote {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="simulate data, check recovery + power")
    ap.add_argument("--data-dir", type=Path, default=DATA, help="folder with real CSVs (default study/data)")
    ap.add_argument("--seed", type=int, default=20261024)
    ap.add_argument("--n-participants", type=int, default=24, help="dry run: simulated N")
    ap.add_argument("--n-coverage", type=int, default=200, help="dry run: datasets for the GEE/paired coverage check")
    ap.add_argument("--n-coverage-glmm", type=int, default=200, help="dry run: of those, how many also fit the GLMM")
    ap.add_argument("--n-power", type=int, default=500, help="dry run: simulated studies per power cell")
    ap.add_argument("--n-perm", type=int, default=1000, help="permutations for the primary H1 test")
    ap.add_argument("--n-power-glmm", type=int, default=200, help="dry run: of those, how many also fit the GLMM")
    ap.add_argument("--workers", type=int, default=max(1, min(8, (os.cpu_count() or 2) - 1)))
    a = ap.parse_args(argv)
    return run_dry(a) if a.dry_run else run_real(a)


if __name__ == "__main__":
    raise SystemExit(main())
