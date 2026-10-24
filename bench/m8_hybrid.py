"""M5-M8 on synthetic data: per-target method comparison, coverage, group-conditional coverage, ablations.

Writes results/m5/sun.json, results/m6/noise.json, results/m7/heat.json, results/m8/comparison.json and
figures in results/m8/figs/. ALL numbers here are `synthetic` (D-012).
"""

from __future__ import annotations

import pickle
from dataclasses import replace

import numpy as np
import pandas as pd

from bench.common import ROOT, weather
from bench.synth_dataset import load, load_split
from core.provenance import hash_paths, write_result
from hybrid.evaluate import Method, run_methods
from hybrid.features import FAMILIES, build_tables

NAME = "world_v1"
CACHE = ROOT / "data" / "synthetic" / "cache"


def methods_for(target: str) -> list[Method]:
    if target == "sun":
        fixed_default, fixed_inf, base_single, scale = "phys_nominal", "phys_mc_mean", "base_sunpath_only", "phys_mc_std"
    elif target == "noise":
        fixed_default, fixed_inf, base_single, scale = "phys_default", "phys_mc_mean", "base_noisemap_only", "phys_mc_std"
    else:
        fixed_default, fixed_inf, base_single, scale = "phys_default", "phys_mc_mean", "base_outdoor_max", "phys_mc_std"
    return [
        Method("single_purpose_baseline", "fixed", base_single),
        Method("physics_default", "fixed", fixed_default),
        Method("physics_inferred", "fixed", fixed_inf),
        Method("pure_ml", "direct", None, tuple(f for f in FAMILIES if f != "physics")),
        Method("hybrid", "residual", fixed_inf, FAMILIES),
        Method("hybrid_normalised", "residual", fixed_inf, FAMILIES, scale_col=scale),
    ]


def ablations(target: str) -> list[Method]:
    h = methods_for(target)[4]
    out = [replace(h, name=f"hybrid_minus_{f}", families=tuple(x for x in FAMILIES if x != f))
           for f in FAMILIES if f != "physics"]
    if target != "sun":  # hidden-property inference only affects noise/heat
        out.append(Method("hybrid_minus_inference", "residual", "phys_default", ("geometry", "meta", "geo", "weather")))
    return out


def tables(tag: str) -> dict[str, pd.DataFrame]:
    recs = load(NAME)
    with open(CACHE / f"{NAME}_pred_{tag}.pkl", "rb") as f:
        preds = pickle.load(f)
    return build_tables(recs, preds, weather(), set(load_split(NAME)["test_buildings"]))


def prepare(target: str, df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(subset=["y"]).reset_index(drop=True)
    if target == "noise":
        df = df[~df["open_heur"]].reset_index(drop=True)
    return df


def main() -> None:
    tabs = tables("main")
    data_hash = hash_paths([ROOT / "data" / "synthetic" / f"{NAME}_split.json", ROOT / "synth", ROOT / "physics",
                            ROOT / "hybrid", ROOT / "data" / "weather" / "toronto_hourly_2016_2025.csv.gz"])
    cfg = {"world": NAME, "alpha": 0.1, "cv": "LOBO (train buildings) CV+, building-weighted quantiles"}
    summary = {}
    figs_data = {}
    for target, out in [("sun", "m5/sun.json"), ("noise", "m6/noise.json"), ("heat", "m7/heat.json")]:
        df = prepare(target, tabs[target])
        tr, te = df[df.split == "train"].reset_index(drop=True), df[df.split == "test"].reset_index(drop=True)
        res, frames = run_methods(tr, te, methods_for(target))
        abl, _ = run_methods(tr, te, ablations(target), mondrian=False)
        payload = {"target": target, "n_train_rows": len(tr), "n_test_rows": len(te),
                   "methods": res, "ablations": {k: v["marginal"] for k, v in abl.items()}}
        if target == "noise":
            # rooms whose nights are mostly above the mic floor (non-censored)
            above = te.groupby("room")["floor_frac"].mean() < 0.5
            keep = set(above[above].index)
            payload["above_floor"] = {}
            from hybrid.evaluate import metrics
            for name, fr in frames.items():
                sub = fr[fr.room.isin(keep)]
                if sub["building"].nunique() >= 3:
                    payload["above_floor"][name] = metrics(sub)
            payload["censoring"] = {"test_rooms": int(te.room.nunique()), "test_rooms_above_floor": len(keep),
                                    "mean_floor_frac": float(te.floor_frac.mean())}
            # secondary targets with the hybrid method
            for ycol in ("y_la90", "y_trim"):
                d2 = df.assign(y=df[ycol])
                tr2, te2 = d2[d2.split == "train"].reset_index(drop=True), d2[d2.split == "test"].reset_index(drop=True)
                r2, _ = run_methods(tr2, te2, [methods_for("noise")[2], methods_for("noise")[4]], mondrian=False)
                payload[f"secondary_{ycol}"] = {k: v["marginal"] for k, v in r2.items()}
            # source attribution summary (test rooms)
            payload["attribution"] = {
                "median_road_db": float(te.groupby("room")["phys_attr_road"].first().median()),
                "share_rooms_transit_dominant": float((te.groupby("room")["phys_attr_transit"].first()
                                                       > te.groupby("room")["phys_attr_road"].first()).mean()),
            }
            # window-open heuristic vs truth over all nights
            allr = tabs["noise"]
            payload["open_window_detection"] = {
                "tp": int((allr.open_heur & allr.open_true).sum()), "fp": int((allr.open_heur & ~allr.open_true).sum()),
                "fn": int((~allr.open_heur & allr.open_true).sum()), "tn": int((~allr.open_heur & ~allr.open_true).sum())}
        if target == "sun":
            payload["target_noise_vs_world_truth"] = {
                "mae_h": float((te["y"] - te["y_true_world"]).abs().mean()),
                "bias_h": float((te["y"] - te["y_true_world"]).mean())}
        write_result(out, payload, seed=7, config=cfg, data_hash=data_hash, data_kind="synthetic")
        summary[target] = {k: {"mae": v["marginal"]["mae"], "mae_ci95": v["marginal"]["mae_ci95"],
                               "coverage90": v["marginal"]["coverage90"], "width90": v["marginal"]["width90"]}
                           for k, v in res.items()}
        figs_data[target] = frames
        print(target, {k: round(v["mae"], 3) for k, v in summary[target].items()})
        print("  cov", {k: round(v["coverage90"], 3) for k, v in summary[target].items()})
    # ---- variant ablations (obstruction, transit) from separate prediction runs
    var = {}
    for tag, target in [("no_obstruction", "sun"), ("no_transit", "noise")]:
        p = CACHE / f"{NAME}_pred_{tag}.pkl"
        if not p.exists():
            continue
        df = prepare(target, tables(tag)[target])
        tr, te = df[df.split == "train"].reset_index(drop=True), df[df.split == "test"].reset_index(drop=True)
        r, _ = run_methods(tr, te, [methods_for(target)[2], methods_for(target)[4]], mondrian=False)
        var[f"{target}_{tag}"] = {k: v["marginal"] for k, v in r.items()}
    write_result("m8/comparison.json", {"summary": summary, "variant_ablations": var}, seed=7, config=cfg,
                 data_hash=data_hash, data_kind="synthetic")
    with open(CACHE / f"{NAME}_m8_frames.pkl", "wb") as f:
        pickle.dump(figs_data, f)
    print("variants", {k: {m: round(x["mae"], 3) for m, x in v.items()} for k, v in var.items()})


if __name__ == "__main__":
    np.seterr(all="ignore")
    main()
