"""Regenerate every figure from results/ (+ cached synthetic evaluation frames). All figures are synthetic.

Style: reference data-viz palette (fixed categorical order), thin marks, recessive axes, one axis per chart,
method identity on the axis (not by colour alone).
"""

from __future__ import annotations

import json
import pickle

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from bench.common import ROOT  # noqa: E402

RES = ROOT / "results"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
MUTED = "#a8a7a1"
INK, INK2 = "#0b0b0b", "#52514e"
SURFACE = "#fcfcfb"
LABEL = {
    "single_purpose_baseline": "Single-purpose tool",
    "physics_default": "Physics, default materials",
    "physics_inferred": "Physics, inferred properties",
    "pure_ml": "Pure ML (no physics)",
    "hybrid": "Hybrid (physics + residual)",
    "hybrid_normalised": "Hybrid, adaptive intervals",
}
UNITS = {"sun": "h/day", "noise": "dB(A)", "heat": "°C"}
TITLES = {
    "sun": "Direct-sun hours at the sill",
    "noise": "Night L_Aeq (closed windows)",
    "heat": "Daily peak indoor temperature",
}


def _style(ax) -> None:
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(MUTED)
        ax.spines[s].set_linewidth(0.8)
    ax.tick_params(colors=INK2, labelsize=8)
    ax.xaxis.label.set_color(INK2)
    ax.yaxis.label.set_color(INK2)
    ax.set_facecolor(SURFACE)
    ax.grid(axis="x", color="#e6e5e0", linewidth=0.6)
    ax.set_axisbelow(True)


def _load(p: str) -> dict:
    return json.loads((RES / p).read_text())


def method_mae() -> None:
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.2), facecolor=SURFACE)
    for ax, (t, path) in zip(
        axes, [("sun", "m5/sun.json"), ("noise", "m6/noise.json"), ("heat", "m7/heat.json")], strict=True
    ):
        d = _load(path)["methods"]
        names = [n for n in LABEL if n in d]
        mae = [d[n]["marginal"]["mae"] for n in names]
        ci = np.array([d[n]["marginal"]["mae_ci95"] for n in names])
        y = np.arange(len(names))[::-1]
        cols = [SERIES[0] if n.startswith("hybrid") else MUTED for n in names]
        ax.barh(y, mae, height=0.55, color=cols, edgecolor=SURFACE, linewidth=2)
        ax.errorbar(
            mae,
            y,
            xerr=[np.array(mae) - ci[:, 0], ci[:, 1] - np.array(mae)],
            fmt="none",
            ecolor=INK,
            elinewidth=1,
            capsize=2,
        )
        ax.set_yticks(y, [LABEL[n] for n in names] if ax is axes[0] else [""] * len(names))
        ax.set_xlabel(f"MAE ({UNITS[t]}), 95% CI over test buildings")
        ax.set_title(TITLES[t], fontsize=9, color=INK, loc="left")
        _style(ax)
    fig.suptitle("Method comparison on held-out synthetic buildings", fontsize=10, color=INK, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(RES / "m8" / "figs" / "method_mae.png", dpi=180)
    plt.close(fig)


def coverage() -> None:
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.2), facecolor=SURFACE, sharex=True)
    for ax, (t, path) in zip(
        axes, [("sun", "m5/sun.json"), ("noise", "m6/noise.json"), ("heat", "m7/heat.json")], strict=True
    ):
        d = _load(path)["methods"]
        names = [n for n in LABEL if n in d]
        cov = [d[n]["marginal"]["coverage90"] for n in names]
        ci = np.array([d[n]["marginal"]["coverage90_ci95"] for n in names])
        y = np.arange(len(names))[::-1]
        ax.axvspan(0.85, 0.95, color="#e9f1fb", zorder=0)
        ax.axvline(0.9, color=SERIES[0], linewidth=1, linestyle="--")
        ax.errorbar(
            cov,
            y,
            xerr=[np.array(cov) - ci[:, 0], ci[:, 1] - np.array(cov)],
            fmt="o",
            color=INK,
            markersize=5,
            elinewidth=1,
            capsize=2,
        )
        ax.set_yticks(y, [LABEL[n] for n in names] if ax is axes[0] else [""] * len(names))
        ax.set_xlim(0.6, 1.0)
        ax.set_xlabel("Empirical coverage of 90% intervals")
        ax.set_title(TITLES[t], fontsize=9, color=INK, loc="left")
        _style(ax)
    fig.suptitle("Interval calibration (shaded: 85–95% target band)", fontsize=10, color=INK, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(RES / "m8" / "figs" / "coverage.png", dpi=180)
    plt.close(fig)


def scatter() -> None:
    p = ROOT / "data" / "synthetic" / "cache" / "world_v1_m8_frames.pkl"
    if not p.exists():
        return
    frames = pickle.loads(p.read_bytes())
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.4), facecolor=SURFACE)
    for ax, t in zip(axes, ("sun", "noise", "heat"), strict=True):
        for k, (name, col) in enumerate((("physics_inferred", MUTED), ("hybrid", SERIES[0]))):
            f = frames[t][name].groupby("room").agg(pred=("pred", "mean"), y=("y", "mean"))
            ax.scatter(
                f["y"],
                f["pred"],
                s=12,
                color=col,
                alpha=0.8,
                edgecolors=SURFACE,
                linewidths=0.5,
                label=LABEL[name],
                zorder=2 + k,
            )
        lo = min(ax.get_xlim()[0], ax.get_ylim()[0])
        hi = max(ax.get_xlim()[1], ax.get_ylim()[1])
        ax.plot([lo, hi], [lo, hi], color=INK2, linewidth=0.8)
        ax.set_xlabel(f"Sensor-derived target, room mean ({UNITS[t]})")
        ax.set_ylabel(f"Predicted ({UNITS[t]})")
        ax.set_title(TITLES[t], fontsize=9, color=INK, loc="left")
        _style(ax)
        ax.grid(True, color="#e6e5e0", linewidth=0.6)
    axes[0].legend(fontsize=7, frameon=False)
    fig.tight_layout()
    fig.savefig(RES / "m8" / "figs" / "pred_vs_measured.png", dpi=180)
    plt.close(fig)


def sobol() -> None:
    if not (RES / "m8" / "sobol.json").exists():
        return
    d = _load("m8/sobol.json")
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.0), facecolor=SURFACE)
    for ax, t in zip(axes, ("noise", "heat"), strict=True):
        sh = d[t]["mean_normalised_share"]
        names = list(sh)
        y = np.arange(len(names))[::-1]
        cols = [SERIES[1] if i < 3 else MUTED for i in range(len(names))]
        ax.barh(y, [sh[n] for n in names], height=0.55, color=cols, edgecolor=SURFACE, linewidth=2)
        ax.set_yticks(y, [n.replace("_", " ") for n in names])
        ax.set_xlabel("Share of variance (total-effect Sobol)")
        ax.set_title(
            f"{'Night noise' if t == 'noise' else 'Heat-wave peak temperature'} — hidden properties highlighted",
            fontsize=8,
            color=INK,
            loc="left",
        )
        _style(ax)
    fig.tight_layout()
    fig.savefig(RES / "m8" / "figs" / "sobol_shares.png", dpi=180)
    plt.close(fig)


def scan_quality() -> None:
    if not (RES / "m3" / "recon_synthetic.json").exists():
        return
    tab = _load("m3/recon_synthetic.json")["table"]
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.0), facecolor=SURFACE)
    durs = ["short_60s", "nominal_120s", "long_240s"]
    for ax, metric, xl in (
        (axes[0], "window_recall", "Window recall"),
        (axes[1], "room_area_abs_rel_err_median", "Median |room area error| (fraction)"),
    ):
        for i, (light, mode) in enumerate(
            (("good", "door_scale"), ("good", "AR"), ("dim", "door_scale"), ("dim", "AR"))
        ):
            vals = [tab[f"{d}__{light}__{mode}"][metric] or 0 for d in durs]
            ax.plot(
                [60, 120, 240],
                vals,
                marker="o",
                markersize=5,
                linewidth=2,
                color=SERIES[i],
                label=f"{light} light, {mode}",
            )
        ax.set_xticks([60, 120, 240], ["60 s", "120 s", "240 s"])
        ax.set_xlabel("Scan duration")
        ax.set_ylabel(xl)
        _style(ax)
        ax.grid(True, color="#e6e5e0", linewidth=0.6)
    axes[0].legend(fontsize=7, frameon=False)
    fig.tight_layout()
    fig.savefig(RES / "m3" / "figs" / "scan_quality.png", dpi=180)
    plt.close(fig)


def main() -> None:
    for sub in ("m8", "m3"):
        (RES / sub / "figs").mkdir(parents=True, exist_ok=True)
    method_mae()
    coverage()
    scatter()
    sobol()
    scan_quality()
    print("figures written")


if __name__ == "__main__":
    main()
